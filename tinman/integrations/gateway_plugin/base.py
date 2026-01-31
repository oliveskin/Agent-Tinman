"""Base types for gateway event monitoring.

This module defines the abstract interface that gateway adapters implement.
Each adapter connects to a specific AI gateway (OpenClaw, LangServe, etc.)
and converts events into Tinman's canonical format.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, AsyncIterator

from ...utils import generate_id, utc_now


class EventType(str, Enum):
    """Types of events from AI gateways."""

    # Message events
    MESSAGE_RECEIVED = "message_received"
    MESSAGE_SENT = "message_sent"

    # Tool events
    TOOL_CALL_START = "tool_call_start"
    TOOL_CALL_END = "tool_call_end"
    TOOL_BLOCKED = "tool_blocked"

    # Session events
    SESSION_START = "session_start"
    SESSION_END = "session_end"

    # Model events
    LLM_REQUEST = "llm_request"
    LLM_RESPONSE = "llm_response"
    LLM_ERROR = "llm_error"

    # Security events
    APPROVAL_REQUESTED = "approval_requested"
    APPROVAL_GRANTED = "approval_granted"
    APPROVAL_DENIED = "approval_denied"

    # Generic
    UNKNOWN = "unknown"


class EventSeverity(str, Enum):
    """Severity levels for events."""

    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class GatewayEvent:
    """A single event from an AI gateway.

    This is the canonical event format that all adapters convert to.
    Events are buffered and periodically converted to Traces for analysis.
    """

    event_id: str = field(default_factory=generate_id)
    event_type: EventType = EventType.UNKNOWN
    timestamp: datetime = field(default_factory=utc_now)
    severity: EventSeverity = EventSeverity.INFO

    # Session context
    session_id: str | None = None
    channel: str | None = None  # e.g., "telegram", "discord", "api"
    user_id: str | None = None

    # Event payload
    payload: dict[str, Any] = field(default_factory=dict)

    # Tool-specific fields
    tool_name: str | None = None
    tool_args: dict[str, Any] | None = None
    tool_result: Any = None

    # Message-specific fields
    message_role: str | None = None  # "user", "assistant", "system"
    message_content: str | None = None

    # Error info
    error_type: str | None = None
    error_message: str | None = None

    # Metadata
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "event_id": self.event_id,
            "event_type": self.event_type.value,
            "timestamp": self.timestamp.isoformat(),
            "severity": self.severity.value,
            "session_id": self.session_id,
            "channel": self.channel,
            "user_id": self.user_id,
            "payload": self.payload,
            "tool_name": self.tool_name,
            "tool_args": self.tool_args,
            "tool_result": self.tool_result,
            "message_role": self.message_role,
            "message_content": self.message_content,
            "error_type": self.error_type,
            "error_message": self.error_message,
            "metadata": self.metadata,
        }


@dataclass
class ConnectionState:
    """State of the gateway connection."""

    connected: bool = False
    last_event_at: datetime | None = None
    reconnect_count: int = 0
    error_count: int = 0
    last_error: str | None = None


class GatewayAdapter(ABC):
    """Abstract base class for gateway adapters.

    Each adapter connects to a specific AI gateway and converts
    its events into GatewayEvent objects.

    Usage:
        adapter = OpenClawAdapter("ws://127.0.0.1:18789")
        async for event in adapter.stream():
            process(event)
    """

    def __init__(self, url: str, **config: Any):
        """Initialize the adapter.

        Args:
            url: Gateway connection URL
            **config: Adapter-specific configuration
        """
        self.url = url
        self.config = config
        self._state = ConnectionState()

    @property
    @abstractmethod
    def name(self) -> str:
        """Adapter name for identification."""
        pass

    @property
    def state(self) -> ConnectionState:
        """Get current connection state."""
        return self._state

    @abstractmethod
    async def connect(self) -> None:
        """Establish connection to the gateway.

        Raises:
            ConnectionError: If connection fails
        """
        pass

    @abstractmethod
    async def disconnect(self) -> None:
        """Close the gateway connection."""
        pass

    @abstractmethod
    async def stream(self) -> AsyncIterator[GatewayEvent]:
        """Stream events from the gateway.

        Yields:
            GatewayEvent objects as they arrive

        Note:
            Implementations should handle reconnection internally.
        """
        pass

    @abstractmethod
    def parse_event(self, raw_event: dict[str, Any]) -> GatewayEvent:
        """Parse a raw gateway event into canonical format.

        Args:
            raw_event: Raw event data from the gateway

        Returns:
            Parsed GatewayEvent
        """
        pass

    async def health_check(self) -> bool:
        """Check if the gateway connection is healthy.

        Returns:
            True if connected and responsive
        """
        return self._state.connected

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}({self.name}, url={self.url})>"
