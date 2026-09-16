#!/usr/bin/env python3
"""
Deploy the Aurora Serverless v2 PostgreSQL Database for Alex Platform.
This script:
1. Runs Terraform in infra/modules/database to provision Aurora cluster & credentials
2. Retrieves the generated cluster ARN and secret ARN
3. Updates the local .env file
4. Updates AWS Lambda function configurations (alex-api, agents)
5. Executes database migrations and seeds initial test data
"""

import os
import sys
import json
import subprocess
from pathlib import Path
import boto3

IS_WINDOWS = sys.platform == "win32"

def run_command(cmd, cwd=None, check=True, capture_output=False, env=None):
    """Run a shell or process command."""
    print(f"Running: {' '.join(cmd) if isinstance(cmd, list) else cmd}")
    if capture_output:
        result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, shell=isinstance(cmd, str), env=env)
        if check and result.returncode != 0:
            print(f"❌ Error: {result.stderr}")
            sys.exit(1)
        return result.stdout.strip()
    else:
        result = subprocess.run(cmd, cwd=cwd, shell=isinstance(cmd, str), env=env)
        if check and result.returncode != 0:
            sys.exit(1)
        return None

def update_env_file(project_root: Path, cluster_arn: str, secret_arn: str):
    """Update AURORA_CLUSTER_ARN and AURORA_SECRET_ARN in .env."""
    env_file = project_root / ".env"
    if not env_file.exists():
        print("⚠️ .env file not found, creating from .env.example if available...")
        example = project_root / ".env.example"
        if example.exists():
            env_file.write_text(example.read_text())
        else:
            env_file.write_text("")

    content = env_file.read_text()
    lines = content.splitlines()
    cluster_found = False
    secret_found = False

    new_lines = []
    for line in lines:
        if line.startswith("AURORA_CLUSTER_ARN="):
            new_lines.append(f"AURORA_CLUSTER_ARN={cluster_arn}")
            cluster_found = True
        elif line.startswith("AURORA_SECRET_ARN="):
            new_lines.append(f"AURORA_SECRET_ARN={secret_arn}")
            secret_found = True
        else:
            new_lines.append(line)

    if not cluster_found:
        new_lines.append(f"AURORA_CLUSTER_ARN={cluster_arn}")
    if not secret_found:
        new_lines.append(f"AURORA_SECRET_ARN={secret_arn}")

    env_file.write_text("\n".join(new_lines) + "\n")
    print("✅ Updated .env with new Aurora ARNs")

def update_lambda_env(cluster_arn: str, secret_arn: str, region: str):
    """Update Lambda functions with new Aurora configuration."""
    print("\n🔄 Updating AWS Lambda configurations with new Database ARNs...")
    lambda_client = boto3.client("lambda", region_name=region)

    functions_to_update = [
        "alex-api",
        "alex-planner",
        "alex-tagger",
        "alex-reporter",
        "alex-charter",
        "alex-retirement",
        "alex-ingest"
    ]

    for func in functions_to_update:
        try:
            config = lambda_client.get_function_configuration(FunctionName=func)
            current_vars = config.get("Environment", {}).get("Variables", {})
            current_vars["AURORA_CLUSTER_ARN"] = cluster_arn
            current_vars["AURORA_SECRET_ARN"] = secret_arn
            current_vars["AURORA_DATABASE"] = "alex"

            lambda_client.update_function_configuration(
                FunctionName=func,
                Environment={"Variables": current_vars}
            )
            print(f"  ✓ Updated Lambda: {func}")
        except lambda_client.exceptions.ResourceNotFoundException:
            print(f"  ⚠️ Lambda {func} not found in AWS, skipping")
        except Exception as e:
            print(f"  ⚠️ Warning updating {func}: {e}")

def main():
    print("🚀 ALEX - Deploy Aurora Serverless v2 Database")
    print("=" * 60)

    project_root = Path(__file__).resolve().parent.parent.parent
    terraform_dir = project_root / "infra" / "modules" / "database"

    if not terraform_dir.exists():
        print(f"❌ Terraform directory not found: {terraform_dir}")
        sys.exit(1)

    region = os.getenv("DEFAULT_AWS_REGION", "ap-southeast-1")

    # 1. Terraform Init
    print("\n📦 Step 1: Initializing Terraform...")
    run_command(["terraform", "init"], cwd=terraform_dir)

    # 2. Terraform Apply
    print(f"\n🏗️  Step 2: Provisioning Aurora Serverless v2 in {region}...")
    print("   (This typically takes ~5-10 minutes on AWS)")
    run_command([
        "terraform", "apply",
        f"-var=aws_region={region}",
        "-auto-approve"
    ], cwd=terraform_dir)

    # 3. Read Outputs
    print("\n🔍 Step 3: Fetching Terraform outputs...")
    outputs_raw = run_command(
        ["terraform", "output", "-json"],
        cwd=terraform_dir,
        capture_output=True
    )
    outputs = json.loads(outputs_raw)

    cluster_arn = outputs["aurora_cluster_arn"]["value"]
    secret_arn = outputs["aurora_secret_arn"]["value"]

    print(f"  Cluster ARN: {cluster_arn}")
    print(f"  Secret ARN:  {secret_arn}")

    # 4. Update .env
    update_env_file(project_root, cluster_arn, secret_arn)

    # 5. Update Lambda configs
    update_lambda_env(cluster_arn, secret_arn, region)

    # 6. Run Migrations & Seed Data
    print("\n🗄️ Step 4: Running Database Migrations & Seeding Initial Data...")
    run_command(["uv", "run", "scripts/db/run_migrations.py"], cwd=project_root)
    run_command(["uv", "run", "scripts/db/reset_db.py", "--with-test-data"], cwd=project_root)

    print("\n" + "=" * 60)
    print("🎉 Database deployment & initialization complete!")
    print("=" * 60)

if __name__ == "__main__":
    main()
