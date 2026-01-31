"""Anthropic model client implementation."""

import os

from ..utils import get_logger, utc_now
from .model_client import ModelClient, ModelResponse

logger = get_logger("anthropic_client")


class AnthropicClient(ModelClient):
    """
    Anthropic API client.

    Supports Claude 3 family of models.
    """

    DEFAULT_MODEL = "claude-3-5-sonnet-20241022"

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        default_model: str | None = None,
        **kwargs,
    ):
        api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        super().__init__(api_key=api_key, default_model=default_model, **kwargs)

        self.base_url = base_url
        self._client = None
        self.default_model = default_model or self.DEFAULT_MODEL

    @property
    def provider(self) -> str:
        return "anthropic"

    def _get_client(self):
        """Lazy initialization of Anthropic client."""
        if self._client is None:
            try:
                from anthropic import AsyncAnthropic

                kwargs = {"api_key": self.api_key}
                if self.base_url:
                    kwargs["base_url"] = self.base_url

                self._client = AsyncAnthropic(**kwargs)
            except ImportError:
                raise ImportError(
                    "Anthropic client requires 'anthropic' package. "
                    "Install with: pip install anthropic"
                )

        return self._client

    async def complete(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        tools: list[dict] | None = None,
        **kwargs,
    ) -> ModelResponse:
        """Send a completion request to Anthropic."""
        client = self._get_client()
        model = model or self.default_model

        start_time = utc_now()

        # Extract system message if present
        system = None
        user_messages = []

        for msg in messages:
            if msg["role"] == "system":
                system = msg["content"]
            else:
                user_messages.append(msg)

        # Build request
        request_kwargs = {
            "model": model,
            "messages": user_messages,
            "max_tokens": max_tokens,
        }

        if system:
            request_kwargs["system"] = system

        # Anthropic doesn't have temperature in same range
        # but we pass it through if provided
        if temperature != 0.7:  # Only override if not default
            request_kwargs["temperature"] = temperature

        # Add tools if provided
        if tools:
            request_kwargs["tools"] = self._format_tools(tools)

        # Add any extra kwargs
        request_kwargs.update(kwargs)

        try:
            response = await client.messages.create(**request_kwargs)

            latency_ms = int((utc_now() - start_time).total_seconds() * 1000)

            # Extract content
            content = ""
            tool_calls = []

            for block in response.content:
                if block.type == "text":
                    content += block.text
                elif block.type == "tool_use":
                    tool_calls.append(
                        {
                            "id": block.id,
                            "type": "tool_use",
                            "function": {
                                "name": block.name,
                                "arguments": block.input,
                            },
                        }
                    )

            return ModelResponse(
                content=content,
                model=response.model,
                prompt_tokens=response.usage.input_tokens,
                completion_tokens=response.usage.output_tokens,
                total_tokens=response.usage.input_tokens + response.usage.output_tokens,
                tool_calls=tool_calls,
                finish_reason=response.stop_reason or "",
                latency_ms=latency_ms,
                raw=response.model_dump() if hasattr(response, "model_dump") else None,
            )

        except Exception as e:
            logger.error(f"Anthropic API error: {e}")
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
        model = model or self.default_model

        # Extract system message
        system = None
        user_messages = []

        for msg in messages:
            if msg["role"] == "system":
                system = msg["content"]
            else:
                user_messages.append(msg)

        request_kwargs = {
            "model": model,
            "messages": user_messages,
            "max_tokens": max_tokens,
        }

        if system:
            request_kwargs["system"] = system

        try:
            async with client.messages.stream(**request_kwargs) as stream:
                async for text in stream.text_stream:
                    yield text

        except Exception as e:
            logger.error(f"Anthropic streaming error: {e}")
            raise

    def _format_tools(self, tools: list[dict]) -> list[dict]:
        """Format tools for Anthropic API."""
        formatted = []
        for tool in tools:
            formatted.append(
                {
                    "name": tool.get("name", ""),
                    "description": tool.get("description", ""),
                    "input_schema": tool.get("parameters", {}),
                }
            )
        return formatted
