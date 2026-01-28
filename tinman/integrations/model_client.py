"""Abstract model client interface."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional

from ..utils import generate_id, utc_now


@dataclass
class ModelResponse:
    """Response from a model call."""
    id: str = field(default_factory=generate_id)
    content: str = ""
    model: str = ""

    # Token usage
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0

    # Tool calls
    tool_calls: list[dict[str, Any]] = field(default_factory=list)

    # Metadata
    finish_reason: str = ""
    latency_ms: int = 0

    # Raw response for debugging
    raw: Optional[dict[str, Any]] = None


class ModelClient(ABC):
    """
    Abstract base class for model clients.

    Provides a unified interface for calling different LLM providers.
    """

    def __init__(self,
                 api_key: Optional[str] = None,
                 default_model: Optional[str] = None,
                 **kwargs):
        self.api_key = api_key
        self.default_model = default_model
        self.config = kwargs

    @property
    @abstractmethod
    def provider(self) -> str:
        """Provider name (e.g., 'openai', 'anthropic')."""
        pass

    @abstractmethod
    async def complete(self,
                       messages: list[dict[str, str]],
                       model: Optional[str] = None,
                       temperature: float = 0.7,
                       max_tokens: int = 4096,
                       tools: Optional[list[dict]] = None,
                       **kwargs) -> ModelResponse:
        """
        Send a completion request.

        Args:
            messages: List of message dicts with 'role' and 'content'
            model: Model identifier (uses default if None)
            temperature: Sampling temperature
            max_tokens: Maximum tokens in response
            tools: Optional list of tool definitions
            **kwargs: Provider-specific options

        Returns:
            ModelResponse with completion result
        """
        pass

    @abstractmethod
    async def stream(self,
                     messages: list[dict[str, str]],
                     model: Optional[str] = None,
                     temperature: float = 0.7,
                     max_tokens: int = 4096,
                     **kwargs):
        """
        Stream a completion response.

        Yields chunks of the response as they arrive.
        """
        pass

    def format_messages(self,
                        system: Optional[str] = None,
                        messages: Optional[list[dict]] = None,
                        user: Optional[str] = None) -> list[dict[str, str]]:
        """
        Helper to format messages consistently.

        Can take a system prompt, list of messages, and/or a user message.
        """
        result = []

        if system:
            result.append({"role": "system", "content": system})

        if messages:
            result.extend(messages)

        if user:
            result.append({"role": "user", "content": user})

        return result
