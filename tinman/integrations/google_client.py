"""Google Gemini model client implementation."""

import asyncio
import os
from typing import Any, Optional

from .model_client import ModelClient, ModelResponse
from ..utils import utc_now, get_logger

logger = get_logger("google_client")


class GoogleClient(ModelClient):
    """
    Google Gemini API client.

    Uses the Google Gen AI SDK (`google-genai`).
    """

    DEFAULT_MODEL = "gemini-2.5-flash"

    def __init__(
        self, api_key: Optional[str] = None, default_model: Optional[str] = None, **kwargs
    ):
        api_key = api_key or os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
        super().__init__(api_key=api_key, default_model=default_model, **kwargs)
        self._client = None
        self.default_model = default_model or self.DEFAULT_MODEL

    @property
    def provider(self) -> str:
        return "google"

    def _get_client(self):
        """Lazy initialization of Gen AI client."""
        if self._client is None:
            try:
                from google import genai

                if self.api_key:
                    self._client = genai.Client(api_key=self.api_key)
                else:
                    # Falls back to GEMINI_API_KEY / GOOGLE_API_KEY in the environment.
                    if not (os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")):
                        raise ValueError(
                            "GOOGLE_API_KEY (or GEMINI_API_KEY) is required for Gemini."
                        )
                    self._client = genai.Client()
            except ImportError:
                raise ImportError(
                    "Google Gemini client requires 'google-genai'. "
                    "Install with: pip install google-genai"
                )

        return self._client

    def _build_prompt(self, messages: list[dict[str, str]]) -> str:
        """Flatten chat messages into a single prompt for Gemini."""
        parts = []
        for msg in messages:
            role = msg.get("role", "user").upper()
            content = msg.get("content", "")
            parts.append(f"{role}: {content}")
        return "\n".join(parts)

    async def complete(
        self,
        messages: list[dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        tools: Optional[list[dict]] = None,
        **kwargs,
    ) -> ModelResponse:
        """Send a completion request to Gemini."""
        client = self._get_client()
        model_name = model or self.default_model

        if tools:
            logger.warning("Gemini client does not support tool calls yet; ignoring tools.")

        prompt = self._build_prompt(messages)
        start_time = utc_now()

        def _call():
            return client.models.generate_content(
                model=model_name,
                contents=prompt,
                config={
                    "temperature": temperature,
                    "max_output_tokens": max_tokens,
                },
                **kwargs,
            )

        response = await asyncio.to_thread(_call)
        latency_ms = int((utc_now() - start_time).total_seconds() * 1000)

        content = getattr(response, "text", "") or ""

        return ModelResponse(
            content=content,
            model=model_name,
            prompt_tokens=0,
            completion_tokens=0,
            total_tokens=0,
            tool_calls=[],
            finish_reason="",
            latency_ms=latency_ms,
            raw=response.to_dict() if hasattr(response, "to_dict") else None,
        )

    async def stream(
        self,
        messages: list[dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        **kwargs,
    ):
        """Stream a completion response (best-effort, non-streaming fallback)."""
        client = self._get_client()
        model_name = model or self.default_model
        prompt = self._build_prompt(messages)

        def _call_stream():
            return client.models.generate_content_stream(
                model=model_name,
                contents=prompt,
                config={
                    "temperature": temperature,
                    "max_output_tokens": max_tokens,
                },
                **kwargs,
            )

        stream = await asyncio.to_thread(_call_stream)
        for chunk in stream:
            text = getattr(chunk, "text", "")
            if text:
                yield text
