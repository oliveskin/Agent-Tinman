"""Together AI model client implementation.

Together AI provides fast inference for open models with free credits:
- Llama 3.x
- Qwen 2.5
- DeepSeek
- Mixtral
- And many more

Get your API key at: https://api.together.xyz
Free tier: $25 in credits for new accounts
"""

import os

from ..utils import get_logger, utc_now
from .model_client import ModelClient, ModelResponse

logger = get_logger("together_client")


class TogetherClient(ModelClient):
    """
    Together AI API client.

    Together offers fast inference with generous free credits ($25 for new accounts).
    Great for experimentation with open models.

    Usage:
        client = TogetherClient(api_key="...")

        # Use Llama 3.1
        response = await client.complete(
            messages=[{"role": "user", "content": "Hello"}],
            model="llama-3.1-70b",
        )

        # Use DeepSeek Coder
        response = await client.complete(
            messages=[{"role": "user", "content": "Hello"}],
            model="deepseek-coder-33b",
        )
    """

    BASE_URL = "https://api.together.xyz/v1"

    # Popular models on Together
    MODELS = {
        # Llama 3.x
        "llama-3.1-405b": "meta-llama/Meta-Llama-3.1-405B-Instruct-Turbo",
        "llama-3.1-70b": "meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo",
        "llama-3.1-8b": "meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo",
        "llama-3.3-70b": "meta-llama/Llama-3.3-70B-Instruct-Turbo",
        # Qwen
        "qwen-2.5-72b": "Qwen/Qwen2.5-72B-Instruct-Turbo",
        "qwen-2.5-7b": "Qwen/Qwen2.5-7B-Instruct-Turbo",
        "qwen-2.5-coder-32b": "Qwen/Qwen2.5-Coder-32B-Instruct",
        # DeepSeek
        "deepseek-v3": "deepseek-ai/DeepSeek-V3",
        "deepseek-r1": "deepseek-ai/DeepSeek-R1",
        "deepseek-r1-distill-llama-70b": "deepseek-ai/DeepSeek-R1-Distill-Llama-70B",
        "deepseek-coder-33b": "deepseek-ai/deepseek-coder-33b-instruct",
        # Mixtral
        "mixtral-8x22b": "mistralai/Mixtral-8x22B-Instruct-v0.1",
        "mixtral-8x7b": "mistralai/Mixtral-8x7B-Instruct-v0.1",
        # Other
        "gemma-2-27b": "google/gemma-2-27b-it",
        "gemma-2-9b": "google/gemma-2-9b-it",
        "dbrx": "databricks/dbrx-instruct",
    }

    DEFAULT_MODEL = "meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo"

    def __init__(
        self, api_key: str | None = None, default_model: str | None = None, **kwargs
    ):
        """
        Initialize Together client.

        Args:
            api_key: Together API key (or set TOGETHER_API_KEY env var)
        """
        api_key = api_key or os.environ.get("TOGETHER_API_KEY")
        super().__init__(api_key=api_key, default_model=default_model, **kwargs)
        self._client = None
        self.default_model = default_model or self.DEFAULT_MODEL

    @property
    def provider(self) -> str:
        return "together"

    def _get_client(self):
        """Lazy initialization of OpenAI client pointed at Together."""
        if self._client is None:
            try:
                from openai import AsyncOpenAI

                self._client = AsyncOpenAI(
                    api_key=self.api_key,
                    base_url=self.BASE_URL,
                )
            except ImportError:
                raise ImportError(
                    "Together client requires 'openai' package. Install with: pip install openai"
                )

        return self._client

    def _resolve_model(self, model: str | None) -> str:
        """Resolve model shorthand to full Together model ID."""
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
        """Send a completion request to Together."""
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
            logger.error(f"Together API error: {e}")
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
            logger.error(f"Together streaming error: {e}")
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
