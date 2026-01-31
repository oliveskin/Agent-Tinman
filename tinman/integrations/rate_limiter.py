"""Rate limiting infrastructure for model API calls."""

import asyncio
import time
from dataclasses import dataclass

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class RateLimitConfig:
    """Configuration for rate limiting."""

    requests_per_minute: float = 60.0
    tokens_per_minute: float = 100000.0
    max_burst: float = 10.0  # Allow burst up to this many requests


class TokenBucketRateLimiter:
    """Token bucket rate limiter for API calls.

    Implements the token bucket algorithm for smooth rate limiting
    with burst support.
    """

    def __init__(self, config: RateLimitConfig | None = None):
        self.config = config or RateLimitConfig()
        self._tokens = self.config.max_burst
        self._last_update = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self, tokens: float = 1.0) -> float:
        """Acquire tokens, waiting if necessary.

        Args:
            tokens: Number of tokens to acquire (default 1 for one request)

        Returns:
            Wait time in seconds (0 if no wait needed)
        """
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_update
            self._last_update = now

            # Refill bucket based on elapsed time
            refill_rate = self.config.requests_per_minute / 60.0
            self._tokens = min(self.config.max_burst, self._tokens + elapsed * refill_rate)

            if self._tokens >= tokens:
                self._tokens -= tokens
                return 0.0

            # Calculate wait time
            deficit = tokens - self._tokens
            wait_time = deficit / refill_rate

            logger.debug(
                "Rate limit wait",
                wait_time=wait_time,
                tokens_needed=tokens,
                tokens_available=self._tokens,
            )

            await asyncio.sleep(wait_time)
            self._tokens = 0  # All tokens consumed after wait
            return wait_time

    def try_acquire(self, tokens: float = 1.0) -> bool:
        """Try to acquire tokens without waiting.

        Returns:
            True if tokens were acquired, False if rate limited
        """
        # Note: This is a sync check, doesn't refill bucket
        if self._tokens >= tokens:
            self._tokens -= tokens
            return True
        return False


# Default rate limiters per provider
_provider_limiters: dict[str, TokenBucketRateLimiter] = {}


def get_rate_limiter(
    provider: str, config: RateLimitConfig | None = None
) -> TokenBucketRateLimiter:
    """Get or create a rate limiter for a provider.

    Args:
        provider: Provider name (e.g., "openai", "anthropic")
        config: Optional custom config, uses defaults if not provided

    Returns:
        Rate limiter instance for the provider
    """
    if provider not in _provider_limiters:
        _provider_limiters[provider] = TokenBucketRateLimiter(config)
    return _provider_limiters[provider]


def reset_rate_limiters() -> None:
    """Reset all rate limiters. Useful for testing."""
    _provider_limiters.clear()
