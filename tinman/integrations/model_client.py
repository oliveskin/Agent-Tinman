"""Abstract model client interface."""

import asyncio
import functools
import random
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, TypeVar

import structlog

from ..utils import generate_id

logger = structlog.get_logger(__name__)

F = TypeVar("F", bound=Callable[..., Any])


def async_retry(
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
) -> Callable[[F], F]:
    """
    Decorator for async functions that implements retry logic with exponential backoff.

    Args:
        max_retries: Maximum number of retry attempts (default: 3)
        base_delay: Initial delay in seconds between retries (default: 1.0)
        max_delay: Maximum delay in seconds between retries (default: 60.0)

    Retries on:
        - asyncio.TimeoutError
        - ConnectionError
        - HTTP 429 (rate limit) errors
        - HTTP 5xx (server) errors

    The delay between retries follows exponential backoff with jitter:
        delay = min(base_delay * (2 ** attempt) + jitter, max_delay)
    """

    def decorator(func: F) -> F:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            last_exception: Exception | None = None

            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except (TimeoutError, ConnectionError) as e:
                    last_exception = e
                    if attempt < max_retries:
                        delay = _calculate_delay(attempt, base_delay, max_delay)
                        logger.warning(
                            "Retrying after error",
                            error=str(e),
                            error_type=type(e).__name__,
                            attempt=attempt + 1,
                            max_retries=max_retries,
                            delay=delay,
                            function=func.__name__,
                        )
                        await asyncio.sleep(delay)
                    else:
                        logger.error(
                            "Max retries exceeded",
                            error=str(e),
                            error_type=type(e).__name__,
                            max_retries=max_retries,
                            function=func.__name__,
                        )
                        raise
                except Exception as e:
                    # Check for HTTP 429 or 5xx errors
                    if _is_retryable_http_error(e):
                        last_exception = e
                        if attempt < max_retries:
                            delay = _calculate_delay(attempt, base_delay, max_delay)
                            logger.warning(
                                "Retrying after HTTP error",
                                error=str(e),
                                error_type=type(e).__name__,
                                attempt=attempt + 1,
                                max_retries=max_retries,
                                delay=delay,
                                function=func.__name__,
                            )
                            await asyncio.sleep(delay)
                        else:
                            logger.error(
                                "Max retries exceeded",
                                error=str(e),
                                error_type=type(e).__name__,
                                max_retries=max_retries,
                                function=func.__name__,
                            )
                            raise
                    else:
                        # Non-retryable error, raise immediately
                        raise

            # Should not reach here, but raise last exception if we do
            if last_exception:
                raise last_exception

        return wrapper  # type: ignore

    return decorator


def _calculate_delay(attempt: int, base_delay: float, max_delay: float) -> float:
    """Calculate delay with exponential backoff and jitter."""
    # Exponential backoff: base_delay * 2^attempt
    exponential_delay = base_delay * (2**attempt)
    # Add jitter: random value between 0 and half the delay
    jitter = random.uniform(0, exponential_delay * 0.5)
    # Cap at max_delay
    return min(exponential_delay + jitter, max_delay)


def _is_retryable_http_error(e: Exception) -> bool:
    """Check if an exception represents a retryable HTTP error (429 or 5xx)."""
    # Check for status_code attribute (common in HTTP client libraries)
    status_code = getattr(e, "status_code", None)
    if status_code is not None:
        return status_code == 429 or (500 <= status_code < 600)

    # Check for status attribute (alternative naming)
    status = getattr(e, "status", None)
    if status is not None:
        return status == 429 or (500 <= status < 600)

    # Check error message for status codes
    error_str = str(e).lower()
    if "429" in error_str or "rate limit" in error_str:
        return True
    if any(f"{code}" in error_str for code in range(500, 600)):
        return True

    return False


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
    raw: dict[str, Any] | None = None


class ModelClient(ABC):
    """
    Abstract base class for model clients.

    Provides a unified interface for calling different LLM providers.

    Retry Behavior:
        Model clients support automatic retry with exponential backoff for
        transient failures. Use the `@async_retry` decorator on methods that
        make API calls. The retry logic handles:

        - asyncio.TimeoutError: Network timeouts
        - ConnectionError: Connection failures
        - HTTP 429: Rate limit exceeded (with backoff)
        - HTTP 5xx: Server errors

        Retries use exponential backoff with jitter to prevent thundering herd:
            delay = min(base_delay * (2 ** attempt) + jitter, max_delay)

    Args:
        api_key: API key for the provider
        default_model: Default model identifier to use
        max_retries: Maximum retry attempts for transient failures (default: 3)
        retry_base_delay: Base delay in seconds for exponential backoff (default: 1.0)
        **kwargs: Additional provider-specific configuration
    """

    def __init__(
        self,
        api_key: str | None = None,
        default_model: str | None = None,
        max_retries: int = 3,
        retry_base_delay: float = 1.0,
        **kwargs,
    ):
        self.api_key = api_key
        self.default_model = default_model
        self.max_retries = max_retries
        self.retry_base_delay = retry_base_delay
        self.config = kwargs

    @property
    @abstractmethod
    def provider(self) -> str:
        """Provider name (e.g., 'openai', 'anthropic')."""
        pass

    @abstractmethod
    async def complete(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        tools: list[dict] | None = None,
        **kwargs,
    ) -> ModelResponse:
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
    async def stream(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        **kwargs,
    ):
        """
        Stream a completion response.

        Yields chunks of the response as they arrive.
        """
        pass

    def format_messages(
        self,
        system: str | None = None,
        messages: list[dict] | None = None,
        user: str | None = None,
    ) -> list[dict[str, str]]:
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
