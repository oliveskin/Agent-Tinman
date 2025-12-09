"""Integrations - model clients and pipeline adapters."""

from .model_client import ModelClient, ModelResponse
from .openai_client import OpenAIClient
from .anthropic_client import AnthropicClient
from .pipeline_adapter import PipelineAdapter, PipelineHook

__all__ = [
    "ModelClient",
    "ModelResponse",
    "OpenAIClient",
    "AnthropicClient",
    "PipelineAdapter",
    "PipelineHook",
]
