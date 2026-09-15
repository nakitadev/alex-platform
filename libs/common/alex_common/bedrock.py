"""
AWS Bedrock and LiteLLM configuration helper.
Ensures LiteLLM's required AWS_REGION_NAME environment variable is set consistently.
"""

import os
import logging

logger = logging.getLogger("alex.bedrock")

def configure_litellm_bedrock(region: str = None) -> str:
    """
    Set required environment variables for LiteLLM to connect with Bedrock.
    LiteLLM specifically requires AWS_REGION_NAME.
    """
    bedrock_region = region or os.getenv("BEDROCK_REGION") or os.getenv("AWS_REGION") or "us-west-2"
    os.environ["AWS_REGION_NAME"] = bedrock_region
    logger.info(f"LiteLLM Bedrock configured with region: {bedrock_region}")
    return bedrock_region

def get_bedrock_region() -> str:
    """Get configured Bedrock region."""
    return os.getenv("AWS_REGION_NAME") or os.getenv("BEDROCK_REGION") or "us-west-2"
