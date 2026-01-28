"""OpenAI model client implementation."""

import os
from typing import Any, Optional

from .model_client import ModelClient, ModelResponse
from ..utils import utc_now, get_logger

logger = get_logger("openai_client")


class OpenAIClient(ModelClient):
    """
    OpenAI API client.

    Supports GPT-4, GPT-3.5-turbo, and other OpenAI models.
    """

    DEFAULT_MODEL = "gpt-4-turbo-preview"

    def __init__(self,
                 api_key: Optional[str] = None,
                 base_url: Optional[str] = None,
                 organization: Optional[str] = None,
                 default_model: Optional[str] = None,
                 **kwargs):
        api_key = api_key or os.environ.get("OPENAI_API_KEY")
        super().__init__(api_key=api_key, default_model=default_model, **kwargs)

        self.base_url = base_url
        self.organization = organization
        self._client = None
        self.default_model = default_model or self.DEFAULT_MODEL

    @property
    def provider(self) -> str:
        return "openai"

    def _get_client(self):
        """Lazy initialization of OpenAI client."""
        if self._client is None:
            try:
                from openai import AsyncOpenAI

                kwargs = {"api_key": self.api_key}
                if self.base_url:
                    kwargs["base_url"] = self.base_url
                if self.organization:
                    kwargs["organization"] = self.organization

                self._client = AsyncOpenAI(**kwargs)
            except ImportError:
                raise ImportError(
                    "OpenAI client requires 'openai' package. "
                    "Install with: pip install openai"
                )

        return self._client

    async def complete(self,
                       messages: list[dict[str, str]],
                       model: Optional[str] = None,
                       temperature: float = 0.7,
                       max_tokens: int = 4096,
                       tools: Optional[list[dict]] = None,
                       **kwargs) -> ModelResponse:
        """Send a completion request to OpenAI."""
        client = self._get_client()
        model = model or self.default_model

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
                    tool_calls.append({
                        "id": tc.id,
                        "type": tc.type,
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    })

            return ModelResponse(
                content=content or "",
                model=response.model,
                prompt_tokens=response.usage.prompt_tokens if response.usage else 0,
                completion_tokens=response.usage.completion_tokens if response.usage else 0,
                total_tokens=response.usage.total_tokens if response.usage else 0,
                tool_calls=tool_calls,
                finish_reason=choice.finish_reason if choice else "",
                latency_ms=latency_ms,
                raw=response.model_dump() if hasattr(response, 'model_dump') else None,
            )

        except Exception as e:
            logger.error(f"OpenAI API error: {e}")
            raise

    async def stream(self,
                     messages: list[dict[str, str]],
                     model: Optional[str] = None,
                     temperature: float = 0.7,
                     max_tokens: int = 4096,
                     **kwargs):
        """Stream a completion response."""
        client = self._get_client()
        model = model or self.default_model

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
            logger.error(f"OpenAI streaming error: {e}")
            raise

    def _format_tools(self, tools: list[dict]) -> list[dict]:
        """Format tools for OpenAI API."""
        formatted = []
        for tool in tools:
            formatted.append({
                "type": "function",
                "function": {
                    "name": tool.get("name", ""),
                    "description": tool.get("description", ""),
                    "parameters": tool.get("parameters", {}),
                },
            })
        return formatted
