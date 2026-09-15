"""Alex Common Shared Library"""
from .observability import observe, setup_observability
from .bedrock import get_bedrock_region, configure_litellm_bedrock
from .logger import get_logger

__all__ = [
    "observe",
    "setup_observability",
    "get_bedrock_region",
    "configure_litellm_bedrock",
    "get_logger"
]
