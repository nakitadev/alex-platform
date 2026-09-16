#!/usr/bin/env python3
"""
Unified Lambda Packaging Utility for Alex Platform
Replaces duplicate package_docker.py scripts across all agent directories.

Builds Lambda-compatible deployment zip archives using Docker:
- Exports dependencies from uv.lock
- Compiles / installs linux/amd64 wheels via official AWS SAM build image
- Bundles agent code and shared libraries (database, common observability)
- Outputs to dist/ and optionally mirrors to legacy agent folders for Terraform compatibility.

Usage:
    uv run scripts/build/package_lambda.py --target planner
    uv run scripts/build/package_lambda.py --all
    uv run scripts/build/package_lambda.py --all --output-dir dist/
"""

import os
import sys
import shutil
import tempfile
import subprocess
import zipfile
import argparse
from pathlib import Path
from typing import Dict, List, Optional

SUPPORTED_TARGETS = ["planner", "tagger", "reporter", "charter", "retirement", "api", "ingest"]
LAMBDA_DOCKER_IMAGE = "public.ecr.aws/sam/build-python3.12:latest"

def run_command(cmd: List[str], cwd: Optional[Path] = None) -> str:
    """Run shell command and return stdout or raise Exception."""
    print(f"  [RUN] {' '.join(str(c) for c in cmd)}")
    result = subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace"
    )
    if result.returncode != 0:
        print(f"  ❌ Command failed with return code {result.returncode}")
        if result.stdout:
            print(f"  Stdout:\n{result.stdout[:500]}")
        if result.stderr:
            print(f"  Stderr:\n{result.stderr[:500]}")
        raise RuntimeError(f"Command failed: {' '.join(str(c) for c in cmd)}")
    return result.stdout

def check_docker() -> bool:
    """Verify Docker daemon is running."""
    try:
        subprocess.run(["docker", "info"], capture_output=True, check=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False

def package_target(
    target_name: str,
    project_root: Path,
    output_dir: Path
) -> Path:
    """Package a single target into a deployable zip."""
    print(f"\n📦 Packaging {target_name.upper()}...")

    # Locate source directory in services/
    possible_source_dirs = [
        project_root / "services" / "agents" / target_name,
        project_root / "services" / target_name,
    ]
    source_dir = next((d for d in possible_source_dirs if d.exists()), None)
    if not source_dir:
        raise FileNotFoundError(f"Source directory for {target_name} not found in {possible_source_dirs}")

    output_dir.mkdir(parents=True, exist_ok=True)
    zip_filename = f"{target_name}_lambda.zip"
    final_zip_path = output_dir / zip_filename

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp_dir:
        temp_path = Path(temp_dir)
        package_dir = temp_path / "package"
        package_dir.mkdir()

        # 1. Export requirements from uv.lock
        req_file = temp_path / "requirements.txt"
        if (source_dir / "uv.lock").exists() or (source_dir / "pyproject.toml").exists():
            print(f"  Exporting dependencies from {source_dir}...")
            req_output = run_command(
                ["uv", "export", "--no-hashes", "--no-emit-project"],
                cwd=source_dir
            )
            filtered_reqs = []
            for line in req_output.splitlines():
                if line.strip().startswith("pyperclip"):
                    continue
                filtered_reqs.append(line)
            req_file.write_text("\n".join(filtered_reqs))
        else:
            req_file.write_text("")

        # 2. Docker pip install (if requirements exist)
        if req_file.stat().st_size > 0:
            print("  Installing dependencies in Docker (linux/amd64)...")
            docker_cmd = [
                "docker", "run", "--rm",
                "--platform", "linux/amd64",
                "-v", f"{temp_path}:/var/task",
                LAMBDA_DOCKER_IMAGE,
                "pip", "install",
                "--no-cache-dir",
                "-r", "/var/task/requirements.txt",
                "-t", "/var/task/package"
            ]
            run_command(docker_cmd)

        # 3. Copy Shared Libraries (Database & Common)
        # Look for database package
        db_dirs = [
            project_root / "libs" / "database" / "alex_database",
            project_root / "libs" / "database" / "src",
        ]
        db_src = next((d for d in db_dirs if d.exists()), None)
        if db_src:
            shutil.copytree(db_src, package_dir / "src", dirs_exist_ok=True)
            shutil.copytree(db_src, package_dir / "alex_database", dirs_exist_ok=True)

        # Look for common library
        common_dirs = [
            project_root / "libs" / "common" / "alex_common",
            project_root / "libs" / "common",
        ]
        common_src = next((d for d in common_dirs if d.exists()), None)
        if common_src:
            shutil.copytree(common_src, package_dir / "alex_common", dirs_exist_ok=True)

        # 4. Copy Agent / Service Source Files
        print("  Copying application source code...")
        src_inner = source_dir / "src"
        search_dir = src_inner if src_inner.exists() else source_dir

        for item in search_dir.iterdir():
            if item.name.startswith((".", "_")) or item.name.endswith(".zip"):
                continue
            if item.name in ["tests", "build", "dist", "node_modules", "package_docker.py", "uv.lock"]:
                continue
            if item.is_dir():
                shutil.copytree(item, package_dir / item.name, dirs_exist_ok=True)
            elif item.is_file() and item.suffix == ".py" and not item.name.startswith("test_"):
                shutil.copy2(item, package_dir / item.name)

        # Ensure observability.py is present in root if needed
        if not (package_dir / "observability.py").exists() and (source_dir / "observability.py").exists():
            shutil.copy2(source_dir / "observability.py", package_dir / "observability.py")

        # 5. Build ZIP archive
        print(f"  Creating {final_zip_path.name}...")
        if final_zip_path.exists():
            final_zip_path.unlink()

        with zipfile.ZipFile(final_zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zipf:
            for root, dirs, files in os.walk(package_dir):
                # Filter out unwanted directories
                dirs[:] = [d for d in dirs if d not in ["__pycache__", ".git", ".pytest_cache", "tests"]]
                for file in files:
                    if file.endswith((".pyc", ".pyo")):
                        continue
                    file_path = Path(root) / file
                    arcname = file_path.relative_to(package_dir)
                    zipf.write(file_path, arcname)

        size_mb = final_zip_path.stat().st_size / (1024 * 1024)
        print(f"  ✅ Built: {final_zip_path} ({size_mb:.1f} MB)")

    return final_zip_path

def main():
    parser = argparse.ArgumentParser(description="Unified Lambda packager for Alex Platform")
    parser.add_argument("--target", choices=SUPPORTED_TARGETS, help="Target component to package")
    parser.add_argument("--all", action="store_true", help="Package all supported components")
    parser.add_argument("--output-dir", default="dist", help="Output directory for zip archives")
    args = parser.parse_args()

    if not args.target and not args.all:
        parser.print_help()
        sys.exit(1)

    if not check_docker():
        print("❌ Error: Docker is not running or not installed.")
        print("   Please start Docker Desktop and ensure `docker info` works.")
        sys.exit(1)

    project_root = Path(__file__).resolve().parent.parent.parent
    output_dir = project_root / args.output_dir

    targets = SUPPORTED_TARGETS if args.all else [args.target]
    summary = {}

    print("=" * 60)
    print("🚀 ALEX UNIFIED LAMBDA PACKAGER")
    print(f"Project root: {project_root}")
    print(f"Output directory: {output_dir}")
    print(f"Targets: {', '.join(targets)}")
    print("=" * 60)

    for target in targets:
        try:
            zip_path = package_target(
                target_name=target,
                project_root=project_root,
                output_dir=output_dir
            )
            size_mb = zip_path.stat().st_size / (1024 * 1024)
            summary[target] = f"✅ {size_mb:.1f} MB"
        except Exception as e:
            print(f"❌ Failed to package {target}: {e}")
            summary[target] = f"❌ Error: {e}"

    print("\n" + "=" * 60)
    print("PACKAGING SUMMARY")
    print("=" * 60)
    for target, status in summary.items():
        print(f"  {target.ljust(15)} : {status}")

if __name__ == "__main__":
    main()
