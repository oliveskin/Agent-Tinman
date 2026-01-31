"""Groq model client implementation.

Groq provides ultra-fast inference for open models with a generous free tier:
- Llama 3.x (8B, 70B)
- Mixtral 8x7B
- Gemma 2

Get your API key at: https://console.groq.com/keys
Free tier: 14,400 requests/day for smaller models
"""

import os

from ..utils import get_logger, utc_now
from .model_client import ModelClient, ModelResponse

logger = get_logger("groq_client")


class GroqClient(ModelClient):
    """
    Groq API client.

    Groq offers the fastest inference for open models with a generous free tier.
    Great for high-volume testing and experimentation.

    Usage:
        client = GroqClient(api_key="gsk_...")

        # Use Llama 3.1 70B (fast!)
        response = await client.complete(
            messages=[{"role": "user", "content": "Hello"}],
            model="llama-3.1-70b",
        )

        # Use Mixtral
        response = await client.complete(
            messages=[{"role": "user", "content": "Hello"}],
            model="mixtral-8x7b",
        )
    """

    BASE_URL = "https://api.groq.com/openai/v1"

    # Available models on Groq
    MODELS = {
        # Llama 3.3
        "llama-3.3-70b": "llama-3.3-70b-versatile",
        # Llama 3.1
        "llama-3.1-70b": "llama-3.1-70b-versatile",
        "llama-3.1-8b": "llama-3.1-8b-instant",
        # Llama 3.2
        "llama-3.2-90b-vision": "llama-3.2-90b-vision-preview",
        "llama-3.2-11b-vision": "llama-3.2-11b-vision-preview",
        "llama-3.2-3b": "llama-3.2-3b-preview",
        "llama-3.2-1b": "llama-3.2-1b-preview",
        # Mixtral
        "mixtral-8x7b": "mixtral-8x7b-32768",
        # Gemma
        "gemma-2-9b": "gemma2-9b-it",
        "gemma-7b": "gemma-7b-it",
        # DeepSeek (if available)
        "deepseek-r1-distill-llama-70b": "deepseek-r1-distill-llama-70b",
    }

    DEFAULT_MODEL = "llama-3.1-70b-versatile"

    def __init__(
        self, api_key: str | None = None, default_model: str | None = None, **kwargs
    ):
        """
        Initialize Groq client.

        Args:
            api_key: Groq API key (or set GROQ_API_KEY env var)
        """
        api_key = api_key or os.environ.get("GROQ_API_KEY")
        super().__init__(api_key=api_key, default_model=default_model, **kwargs)
        self._client = None
        self.default_model = default_model or self.DEFAULT_MODEL

    @property
    def provider(self) -> str:
        return "groq"

    def _get_client(self):
        """Lazy initialization of OpenAI client pointed at Groq."""
        if self._client is None:
            try:
                from openai import AsyncOpenAI

                self._client = AsyncOpenAI(
                    api_key=self.api_key,
                    base_url=self.BASE_URL,
                )
            except ImportError:
                raise ImportError(
                    "Groq client requires 'openai' package. Install with: pip install openai"
                )

        return self._client

    def _resolve_model(self, model: str | None) -> str:
        """Resolve model shorthand to full Groq model ID."""
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
        """Send a completion request to Groq."""
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
            logger.error(f"Groq API error: {e}")
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
            logger.error(f"Groq streaming error: {e}")
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
