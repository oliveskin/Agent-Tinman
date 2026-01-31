"""Base agent class for all Tinman agents."""

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from ..config.modes import OperatingMode
from ..core.event_bus import EventBus
from ..utils import generate_id, get_logger, utc_now


class AgentState(str, Enum):
    """Agent lifecycle states."""

    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class AgentContext:
    """Context passed to agent operations."""

    mode: OperatingMode
    session_id: str = field(default_factory=generate_id)
    parent_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    started_at: datetime = field(default_factory=utc_now)
    timeout_seconds: float = 300.0


@dataclass
class AgentResult:
    """Result from an agent operation."""

    agent_id: str
    agent_type: str
    success: bool
    data: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    duration_ms: int = 0
    created_at: datetime = field(default_factory=utc_now)


class BaseAgent(ABC):
    """
    Base class for all Tinman agents.

    Provides common functionality:
    - Lifecycle management
    - Event publishing
    - Logging
    - Context handling
    """

    def __init__(self, event_bus: EventBus | None = None):
        self.id = generate_id()
        self.state = AgentState.IDLE
        self.event_bus = event_bus
        self.logger = get_logger(self.__class__.__name__)
        self._context: AgentContext | None = None

    @property
    @abstractmethod
    def agent_type(self) -> str:
        """Unique identifier for this agent type."""
        pass

    @abstractmethod
    async def execute(self, context: AgentContext, **kwargs) -> AgentResult:
        """Execute the agent's primary function."""
        pass

    async def run(self, context: AgentContext, **kwargs) -> AgentResult:
        """
        Run the agent with lifecycle management.

        Handles state transitions and event publishing.
        """
        self._context = context
        self.state = AgentState.RUNNING
        start_time = utc_now()

        self._publish_event(
            "agent.started",
            {
                "agent_id": self.id,
                "agent_type": self.agent_type,
                "context": {
                    "mode": context.mode.value,
                    "session_id": context.session_id,
                },
            },
        )

        try:
            result = await asyncio.wait_for(
                self.execute(context, **kwargs),
                timeout=context.timeout_seconds,
            )
            self.state = AgentState.COMPLETED

            duration_ms = int((utc_now() - start_time).total_seconds() * 1000)
            result.duration_ms = duration_ms

            self._publish_event(
                "agent.completed",
                {
                    "agent_id": self.id,
                    "agent_type": self.agent_type,
                    "success": result.success,
                    "duration_ms": duration_ms,
                },
            )

            return result

        except TimeoutError:
            self.state = AgentState.FAILED
            duration_ms = int((utc_now() - start_time).total_seconds() * 1000)
            error_msg = f"Agent execution timed out after {context.timeout_seconds} seconds"
            self.logger.error(error_msg)

            self._publish_event(
                "agent.failed",
                {
                    "agent_id": self.id,
                    "agent_type": self.agent_type,
                    "error": error_msg,
                    "duration_ms": duration_ms,
                },
            )

            return AgentResult(
                agent_id=self.id,
                agent_type=self.agent_type,
                success=False,
                error=error_msg,
                duration_ms=duration_ms,
            )

        except Exception as e:
            self.state = AgentState.FAILED
            self.logger.error(f"Agent failed: {e}")

            duration_ms = int((utc_now() - start_time).total_seconds() * 1000)

            self._publish_event(
                "agent.failed",
                {
                    "agent_id": self.id,
                    "agent_type": self.agent_type,
                    "error": str(e),
                    "duration_ms": duration_ms,
                },
            )

            return AgentResult(
                agent_id=self.id,
                agent_type=self.agent_type,
                success=False,
                error=str(e),
                duration_ms=duration_ms,
            )

    def pause(self) -> None:
        """Pause agent execution."""
        if self.state == AgentState.RUNNING:
            self.state = AgentState.PAUSED
            self._publish_event("agent.paused", {"agent_id": self.id})

    def resume(self) -> None:
        """Resume paused agent."""
        if self.state == AgentState.PAUSED:
            self.state = AgentState.RUNNING
            self._publish_event("agent.resumed", {"agent_id": self.id})

    def _publish_event(self, event_type: str, data: dict[str, Any]) -> None:
        """Publish an event if event bus is available."""
        if self.event_bus:
            self.event_bus.publish(event_type, data)

    def _check_mode_allowed(
        self, context: AgentContext, required_modes: list[OperatingMode]
    ) -> bool:
        """Check if operation is allowed in current mode."""
        return context.mode in required_modes
