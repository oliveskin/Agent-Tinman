"""ID generation utilities."""

import uuid
from datetime import datetime


def generate_id() -> str:
    """Generate a unique UUID4 identifier."""
    return str(uuid.uuid4())


def generate_short_id() -> str:
    """Generate a short, human-readable identifier."""
    timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    suffix = uuid.uuid4().hex[:6]
    return f"{timestamp}-{suffix}"
