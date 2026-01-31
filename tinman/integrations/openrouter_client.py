"""OpenRouter model client implementation.

OpenRouter provides access to many open and frontier models including:
- DeepSeek (deepseek-chat, deepseek-coder)
- Qwen (qwen-2.5-72b, qwen-2.5-coder-32b)
- Llama 3.x (meta-llama/llama-3.1-405b, etc.)
- Mistral (mistral-large, mixtral-8x22b)
- Many others with free tiers

Get your API key at: https://openrouter.ai/keys
"""

import os

from ..utils import get_logger, utc_now
from .model_client import ModelClient, ModelResponse

logger = get_logger("openrouter_client")


class OpenRouterClient(ModelClient):
    """
    OpenRouter API client.

    Provides access to 100+ models including free tiers for:
    - DeepSeek Chat & Coder
    - Qwen 2.5 series
    - Llama 3.x series
    - Mistral/Mixtral
    - And many more

    Usage:
        client = OpenRouterClient(api_key="sk-or-...")

        # Use DeepSeek (free tier available)
        response = await client.complete(
            messages=[{"role": "user", "content": "Hello"}],
            model="deepseek/deepseek-chat",
        )

        # Use Qwen
        response = await client.complete(
            messages=[{"role": "user", "content": "Hello"}],
            model="qwen/qwen-2.5-72b-instruct",
        )
    """

    BASE_URL = "https://openrouter.ai/api/v1"

    # Popular free/cheap models
    MODELS = {
        # DeepSeek - excellent for coding, free tier
        "deepseek-chat": "deepseek/deepseek-chat",
        "deepseek-coder": "deepseek/deepseek-coder",
        "deepseek-r1": "deepseek/deepseek-r1",
        # Qwen - strong general purpose
        "qwen-2.5-72b": "qwen/qwen-2.5-72b-instruct",
        "qwen-2.5-coder-32b": "qwen/qwen-2.5-coder-32b-instruct",
        "qwen-2.5-7b": "qwen/qwen-2.5-7b-instruct",
        # Llama 3.x
        "llama-3.1-405b": "meta-llama/llama-3.1-405b-instruct",
        "llama-3.1-70b": "meta-llama/llama-3.1-70b-instruct",
        "llama-3.1-8b": "meta-llama/llama-3.1-8b-instruct",
        "llama-3.3-70b": "meta-llama/llama-3.3-70b-instruct",
        # Mistral
        "mistral-large": "mistralai/mistral-large",
        "mixtral-8x22b": "mistralai/mixtral-8x22b-instruct",
        "mistral-7b": "mistralai/mistral-7b-instruct",
        # Google (free tier)
        "gemma-2-27b": "google/gemma-2-27b-it",
        "gemma-2-9b": "google/gemma-2-9b-it",
        # Free models (no cost)
        "phi-3-mini": "microsoft/phi-3-mini-128k-instruct:free",
        "llama-3.2-3b": "meta-llama/llama-3.2-3b-instruct:free",
    }

    DEFAULT_MODEL = "deepseek/deepseek-chat"

    def __init__(
        self,
        api_key: str | None = None,
        site_url: str | None = None,
        site_name: str | None = None,
        default_model: str | None = None,
        **kwargs,
    ):
        """
        Initialize OpenRouter client.

        Args:
            api_key: OpenRouter API key (or set OPENROUTER_API_KEY env var)
            site_url: Your site URL (for rankings, optional)
            site_name: Your site name (for rankings, optional)
        """
        api_key = api_key or os.environ.get("OPENROUTER_API_KEY")
        super().__init__(api_key=api_key, default_model=default_model, **kwargs)

        self.site_url = site_url or os.environ.get("OPENROUTER_SITE_URL", "")
        self.site_name = site_name or os.environ.get("OPENROUTER_SITE_NAME", "Tinman")
        self._client = None
        self.default_model = default_model or self.DEFAULT_MODEL

    @property
    def provider(self) -> str:
        return "openrouter"

    def _get_client(self):
        """Lazy initialization of OpenAI client pointed at OpenRouter."""
        if self._client is None:
            try:
                from openai import AsyncOpenAI

                self._client = AsyncOpenAI(
                    api_key=self.api_key,
                    base_url=self.BASE_URL,
                    default_headers={
                        "HTTP-Referer": self.site_url,
                        "X-Title": self.site_name,
                    },
                )
            except ImportError:
                raise ImportError(
                    "OpenRouter client requires 'openai' package. Install with: pip install openai"
                )

        return self._client

    def _resolve_model(self, model: str | None) -> str:
        """Resolve model shorthand to full OpenRouter model ID."""
        if model is None:
            return self.default_model

        # Check if it's a shorthand
        if model in self.MODELS:
            return self.MODELS[model]

        # Otherwise assume it's a full model ID
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
        """Send a completion request to OpenRouter."""
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

        # Add tools if provided
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
            if choice and choice.message.tool_calls:
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

            return ModelResponse(
                content=content or "",
                model=response.model,
                prompt_tokens=response.usage.prompt_tokens if response.usage else 0,
                completion_tokens=response.usage.completion_tokens if response.usage else 0,
                total_tokens=response.usage.total_tokens if response.usage else 0,
                tool_calls=tool_calls,
                finish_reason=choice.finish_reason if choice else "",
                latency_ms=latency_ms,
                raw=response.model_dump() if hasattr(response, "model_dump") else None,
            )

        except Exception as e:
            logger.error(f"OpenRouter API error: {e}")
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
            logger.error(f"OpenRouter streaming error: {e}")
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
