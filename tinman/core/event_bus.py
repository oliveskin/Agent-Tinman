"""Simple in-process event bus for agent communication."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Optional
from collections import defaultdict
import asyncio
import threading

from ..utils import generate_id, utc_now, get_logger

logger = get_logger("event_bus")


@dataclass
class Event:
    """Base event structure."""
    id: str = field(default_factory=generate_id)
    topic: str = ""
    timestamp: datetime = field(default_factory=utc_now)
    data: dict[str, Any] = field(default_factory=dict)
    correlation_id: Optional[str] = None
    causation_id: Optional[str] = None


EventHandler = Callable[[Event], None]
AsyncEventHandler = Callable[[Event], Any]


class EventBus:
    """
    Simple pub/sub event bus for in-process agent communication.

    Supports both sync and async handlers. Errors in handlers are logged
    but don't prevent other handlers from executing.
    """

    def __init__(self):
        self._sync_handlers: dict[str, list[EventHandler]] = defaultdict(list)
        self._async_handlers: dict[str, list[AsyncEventHandler]] = defaultdict(list)
        self._lock = threading.Lock()
        self._event_history: list[Event] = []
        self._max_history = 1000

    def subscribe(self, topic: str, handler: EventHandler) -> None:
        """Register a synchronous handler for a topic."""
        with self._lock:
            self._sync_handlers[topic].append(handler)
        logger.debug(f"Subscribed sync handler to topic: {topic}")

    def subscribe_async(self, topic: str, handler: AsyncEventHandler) -> None:
        """Register an async handler for a topic."""
        with self._lock:
            self._async_handlers[topic].append(handler)
        logger.debug(f"Subscribed async handler to topic: {topic}")

    def unsubscribe(self, topic: str, handler: EventHandler) -> None:
        """Remove a handler from a topic."""
        with self._lock:
            if handler in self._sync_handlers[topic]:
                self._sync_handlers[topic].remove(handler)
            if handler in self._async_handlers[topic]:
                self._async_handlers[topic].remove(handler)

    def publish(self, topic: str, data: dict[str, Any],
                correlation_id: Optional[str] = None,
                causation_id: Optional[str] = None) -> Event:
        """
        Publish an event to all subscribers.

        Returns the created Event object.
        """
        event = Event(
            topic=topic,
            data=data,
            correlation_id=correlation_id,
            causation_id=causation_id,
        )

        self._store_event(event)
        self._dispatch_sync(topic, event)

        logger.debug(f"Published event: {topic} (id={event.id})")
        return event

    async def publish_async(self, topic: str, data: dict[str, Any],
                           correlation_id: Optional[str] = None,
                           causation_id: Optional[str] = None) -> Event:
        """
        Publish an event and await async handlers.

        Returns the created Event object.
        """
        event = Event(
            topic=topic,
            data=data,
            correlation_id=correlation_id,
            causation_id=causation_id,
        )

        self._store_event(event)
        self._dispatch_sync(topic, event)
        await self._dispatch_async(topic, event)

        logger.debug(f"Published async event: {topic} (id={event.id})")
        return event

    def _store_event(self, event: Event) -> None:
        """Store event in history (bounded)."""
        with self._lock:
            self._event_history.append(event)
            if len(self._event_history) > self._max_history:
                self._event_history = self._event_history[-self._max_history:]

    def _dispatch_sync(self, topic: str, event: Event) -> None:
        """Dispatch to synchronous handlers."""
        with self._lock:
            handlers = list(self._sync_handlers[topic])

        for handler in handlers:
            try:
                handler(event)
            except Exception as e:
                logger.error(f"Error in sync handler for {topic}: {e}")

    async def _dispatch_async(self, topic: str, event: Event) -> None:
        """Dispatch to async handlers."""
        with self._lock:
            handlers = list(self._async_handlers[topic])

        tasks = []
        for handler in handlers:
            tasks.append(self._safe_call_async(handler, event, topic))

        if tasks:
            await asyncio.gather(*tasks)

    async def _safe_call_async(self, handler: AsyncEventHandler,
                               event: Event, topic: str) -> None:
        """Call async handler with error handling."""
        try:
            result = handler(event)
            if asyncio.iscoroutine(result):
                await result
        except Exception as e:
            logger.error(f"Error in async handler for {topic}: {e}")

    def get_history(self, topic: Optional[str] = None,
                    limit: int = 100) -> list[Event]:
        """Get recent event history, optionally filtered by topic."""
        with self._lock:
            events = self._event_history
            if topic:
                events = [e for e in events if e.topic == topic]
            return events[-limit:]

    def clear_history(self) -> None:
        """Clear event history."""
        with self._lock:
            self._event_history = []

    def get_subscriber_count(self, topic: str) -> int:
        """Get number of subscribers for a topic."""
        with self._lock:
            return (len(self._sync_handlers[topic]) +
                    len(self._async_handlers[topic]))


# Event topics used by the system
class Topics:
    """Standard event topics."""
    APPROVAL_REQUESTED = "approval.requested"
    HYPOTHESIS_CREATED = "hypothesis.created"
    EXPERIMENT_CREATED = "experiment.created"
    EXPERIMENT_RUN_COMPLETED = "experiment.run.completed"
    FAILURE_DISCOVERED = "failure.discovered"
    INTERVENTION_PROPOSED = "intervention.proposed"
    SIMULATION_COMPLETED = "simulation.completed"
    INTERVENTION_APPROVED = "intervention.approved"
    INTERVENTION_REJECTED = "intervention.rejected"
    DEPLOYMENT_COMPLETED = "deployment.completed"
    DEPLOYMENT_ROLLED_BACK = "deployment.rolled_back"
    REGRESSION_DETECTED = "regression.detected"
    MODEL_VERSION_CHANGED = "model.version.changed"
