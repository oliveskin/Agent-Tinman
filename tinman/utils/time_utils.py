"""Time and timestamp utilities."""

from datetime import datetime, timezone
from typing import Optional


def utc_now() -> datetime:
    """Get current UTC timestamp."""
    return datetime.now(timezone.utc)


def format_timestamp(dt: datetime) -> str:
    """Format datetime to ISO 8601 string."""
    return dt.isoformat()


def parse_timestamp(s: str) -> datetime:
    """Parse ISO 8601 string to datetime."""
    return datetime.fromisoformat(s)


def seconds_ago(seconds: int) -> datetime:
    """Get timestamp N seconds ago."""
    from datetime import timedelta
    return utc_now() - timedelta(seconds=seconds)


def days_ago(days: int) -> datetime:
    """Get timestamp N days ago."""
    from datetime import timedelta
    return utc_now() - timedelta(days=days)


def is_expired(dt: datetime, ttl_seconds: int) -> bool:
    """Check if timestamp has expired given TTL."""
    from datetime import timedelta
    return utc_now() > dt + timedelta(seconds=ttl_seconds)
