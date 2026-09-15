"""
Observability module for LangFuse and Logfire integration.
Centralized context manager and decorators across all agents and services.
"""

import os
import logging
from contextlib import contextmanager
from typing import Optional

logger = logging.getLogger("alex.observability")

@contextmanager
def observe(service_name: Optional[str] = None):
    """
    Context manager for observability with LangFuse and Logfire.
    
    Args:
        service_name: Name of the service/agent (defaults to SERVICE_NAME env var or 'alex_agent')
    """
    svc_name = service_name or os.getenv("SERVICE_NAME", "alex_agent")
    has_langfuse = bool(os.getenv("LANGFUSE_SECRET_KEY"))
    has_openai = bool(os.getenv("OPENAI_API_KEY"))

    if not has_langfuse:
        logger.debug(f"LangFuse not configured for {svc_name}, skipping tracing")
        yield
        return

    if not has_openai:
        logger.warning(f"OPENAI_API_KEY not set for {svc_name}, traces may not export properly")

    langfuse_client = None
    try:
        import logfire
        from langfuse import get_client

        logfire.configure(
            service_name=svc_name,
            send_to_logfire=False,
            inspect_arguments=False
        )

        langfuse_client = get_client()
        langfuse_client.auth_check()
        logger.info(f"✅ LangFuse observability active for {svc_name}")
    except Exception as e:
        logger.warning(f"⚠️ Failed to initialize LangFuse for {svc_name}: {e}")

    try:
        yield
    finally:
        if langfuse_client:
            try:
                langfuse_client.flush()
            except Exception as e:
                logger.error(f"Error flushing LangFuse traces: {e}")

def setup_observability(service_name: Optional[str] = None):
    """Helper to configure observability at startup."""
    svc = service_name or os.getenv("SERVICE_NAME", "alex_agent")
    os.environ["SERVICE_NAME"] = svc
    return svc
