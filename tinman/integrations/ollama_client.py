"""Ollama model client implementation.

Ollama runs open models locally - completely free, no API keys needed.
Supports Llama, Qwen, DeepSeek, Mistral, and many others.

Install Ollama: https://ollama.ai
Then: ollama pull llama3.1
"""

import os

from ..utils import get_logger, utc_now
from .model_client import ModelClient, ModelResponse

logger = get_logger("ollama_client")


class OllamaClient(ModelClient):
    """
    Ollama client for local model inference.

    Run models locally with no API costs. Great for:
    - Development and testing
    - Privacy-sensitive workloads
    - Offline operation
    - Unlimited experimentation

    Usage:
        # Start Ollama server: ollama serve
        # Pull a model: ollama pull llama3.1

        client = OllamaClient()

        response = await client.complete(
            messages=[{"role": "user", "content": "Hello"}],
            model="llama3.1",
        )
    """

    DEFAULT_BASE_URL = "http://localhost:11434/v1"

    # Popular Ollama models
    MODELS = {
        # Llama 3.x
        "llama3.1": "llama3.1",
        "llama3.1:70b": "llama3.1:70b",
        "llama3.1:8b": "llama3.1:8b",
        "llama3.2": "llama3.2",
        "llama3.2:3b": "llama3.2:3b",
        "llama3.2:1b": "llama3.2:1b",
        # Qwen
        "qwen2.5": "qwen2.5",
        "qwen2.5:72b": "qwen2.5:72b",
        "qwen2.5:32b": "qwen2.5:32b",
        "qwen2.5:14b": "qwen2.5:14b",
        "qwen2.5:7b": "qwen2.5:7b",
        "qwen2.5-coder": "qwen2.5-coder",
        "qwen2.5-coder:32b": "qwen2.5-coder:32b",
        # DeepSeek
        "deepseek-coder-v2": "deepseek-coder-v2",
        "deepseek-r1": "deepseek-r1",
        "deepseek-r1:70b": "deepseek-r1:70b",
        "deepseek-r1:32b": "deepseek-r1:32b",
        "deepseek-r1:14b": "deepseek-r1:14b",
        "deepseek-r1:8b": "deepseek-r1:8b",
        # Mistral
        "mistral": "mistral",
        "mixtral": "mixtral",
        "mistral-nemo": "mistral-nemo",
        # Code models
        "codellama": "codellama",
        "codegemma": "codegemma",
        "starcoder2": "starcoder2",
        # Small/fast models
        "phi3": "phi3",
        "phi3:mini": "phi3:mini",
        "gemma2": "gemma2",
        "gemma2:9b": "gemma2:9b",
        "gemma2:2b": "gemma2:2b",
    }

    DEFAULT_MODEL = "llama3.1"

    def __init__(
        self, base_url: str | None = None, default_model: str | None = None, **kwargs
    ):
        """
        Initialize Ollama client.

        Args:
            base_url: Ollama server URL (default: http://localhost:11434/v1)
        """
        # Ollama doesn't need an API key
        super().__init__(api_key="ollama", default_model=default_model, **kwargs)
        self.base_url = base_url or os.environ.get("OLLAMA_BASE_URL", self.DEFAULT_BASE_URL)
        self._client = None
        self.default_model = default_model or self.DEFAULT_MODEL

    @property
    def provider(self) -> str:
        return "ollama"

    def _get_client(self):
        """Lazy initialization of OpenAI client pointed at Ollama."""
        if self._client is None:
            try:
                from openai import AsyncOpenAI

                self._client = AsyncOpenAI(
                    api_key="ollama",  # Ollama doesn't check this
                    base_url=self.base_url,
                )
            except ImportError:
                raise ImportError(
                    "Ollama client requires 'openai' package. Install with: pip install openai"
                )

        return self._client

    def _resolve_model(self, model: str | None) -> str:
        """Resolve model shorthand to Ollama model name."""
        if model is None:
            return self.default_model

        # Check if it's a shorthand
        if model in self.MODELS:
            return self.MODELS[model]

        # Otherwise assume it's a valid Ollama model name
        return model

    async def complete(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        tools: list[dict] | None = None,
        **kwargs,
    ) -> ModelResponse:
        """Send a completion request to Ollama."""
        client = self._get_client()
        model = self._resolve_model(model)

        start_time = utc_now()

        # Build request
        request_kwargs = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        # Add tools if provided (Ollama supports tools for some models)
        if tools:
            request_kwargs["tools"] = self._format_tools(tools)

        # Add any extra kwargs
        request_kwargs.update(kwargs)

        try:
            response = await client.chat.completions.create(**request_kwargs)

            latency_ms = int((utc_now() - start_time).total_seconds() * 1000)

            # Extract response data
            choice = response.choices[0] if response.choices else None
            content = choice.message.content if choice else ""

            # Extract tool calls
            tool_calls = []
            if choice and hasattr(choice.message, "tool_calls") and choice.message.tool_calls:
                for tc in choice.message.tool_calls:
                    tool_calls.append(
                        {
                            "id": tc.id,
                            "type": tc.type,
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments,
                            },
                        }
                    )

            # Ollama may not return usage stats
            usage = response.usage if hasattr(response, "usage") and response.usage else None

            return ModelResponse(
                content=content or "",
                model=model,
                prompt_tokens=usage.prompt_tokens if usage else 0,
                completion_tokens=usage.completion_tokens if usage else 0,
                total_tokens=usage.total_tokens if usage else 0,
                tool_calls=tool_calls,
                finish_reason=choice.finish_reason if choice else "",
                latency_ms=latency_ms,
                raw=response.model_dump() if hasattr(response, "model_dump") else None,
            )

        except Exception as e:
            logger.error(f"Ollama API error: {e}")
            raise

    async def stream(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        **kwargs,
    ):
        """Stream a completion response."""
        client = self._get_client()
        model = self._resolve_model(model)

        try:
            stream = await client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                stream=True,
                **kwargs,
            )

            async for chunk in stream:
                if chunk.choices:
                    delta = chunk.choices[0].delta
                    if delta.content:
                        yield delta.content

        except Exception as e:
            logger.error(f"Ollama streaming error: {e}")
            raise

    def _format_tools(self, tools: list[dict]) -> list[dict]:
        """Format tools for OpenAI-compatible API."""
        formatted = []
        for tool in tools:
            formatted.append(
                {
                    "type": "function",
                    "function": {
                        "name": tool.get("name", ""),
                        "description": tool.get("description", ""),
                        "parameters": tool.get("parameters", {}),
                    },
                }
            )
        return formatted

    @classmethod
    def list_models(cls) -> dict[str, str]:
        """List available model shorthands."""
        return cls.MODELS.copy()

    async def list_local_models(self) -> list[str]:
        """List models available on the local Ollama server."""
        import aiohttp

        # Use the Ollama native API for listing models
        base = self.base_url.replace("/v1", "")
        url = f"{base}/api/tags"

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status == 200:
                        data = await response.json()
                        return [m["name"] for m in data.get("models", [])]
                    else:
                        logger.warning(f"Failed to list Ollama models: {response.status}")
                        return []
        except Exception as e:
            logger.error(f"Error listing Ollama models: {e}")
            return []
