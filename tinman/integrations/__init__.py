"""Integrations - model clients and pipeline adapters."""

from .anthropic_client import AnthropicClient
from .google_client import GoogleClient
from .groq_client import GroqClient
from .model_client import ModelClient, ModelResponse
from .ollama_client import OllamaClient
from .openai_client import OpenAIClient
from .openrouter_client import OpenRouterClient
from .pipeline_adapter import PipelineAdapter, PipelineHook
from .together_client import TogetherClient

try:  # optional dependencies
    from .langchain import TinmanLangChainCallbackHandler
except Exception:  # pragma: no cover - optional
    TinmanLangChainCallbackHandler = None

try:  # optional dependencies
    from .crewai import TinmanCrewHook
except Exception:  # pragma: no cover - optional
    TinmanCrewHook = None

from .fastapi import create_fastapi_adapter, record_llm_interaction

__all__ = [
    # Base
    "ModelClient",
    "ModelResponse",
    # Proprietary
    "OpenAIClient",
    "AnthropicClient",
    # Open model providers
    "OpenRouterClient",  # DeepSeek, Qwen, Llama, Mistral - many free tiers
    "GoogleClient",  # Gemini models
    "GroqClient",  # Ultra-fast inference, generous free tier
    "OllamaClient",  # Local models, completely free
    "TogetherClient",  # $25 free credits for new accounts
    # Pipeline
    "PipelineAdapter",
    "PipelineHook",
    # Optional integrations
    "TinmanLangChainCallbackHandler",
    "TinmanCrewHook",
    "create_fastapi_adapter",
    "record_llm_interaction",
]
