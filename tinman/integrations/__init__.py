"""Integrations - model clients and pipeline adapters."""

from .model_client import ModelClient, ModelResponse
from .openai_client import OpenAIClient
from .anthropic_client import AnthropicClient
from .openrouter_client import OpenRouterClient
from .groq_client import GroqClient
from .ollama_client import OllamaClient
from .together_client import TogetherClient
from .pipeline_adapter import PipelineAdapter, PipelineHook

__all__ = [
    # Base
    "ModelClient",
    "ModelResponse",
    # Proprietary
    "OpenAIClient",
    "AnthropicClient",
    # Open model providers
    "OpenRouterClient",  # DeepSeek, Qwen, Llama, Mistral - many free tiers
    "GroqClient",        # Ultra-fast inference, generous free tier
    "OllamaClient",      # Local models, completely free
    "TogetherClient",    # $25 free credits for new accounts
    # Pipeline
    "PipelineAdapter",
    "PipelineHook",
]
