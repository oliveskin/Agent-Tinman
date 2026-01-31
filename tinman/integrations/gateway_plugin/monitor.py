"""Gateway event monitor with trace buffering and analysis.

This module provides the main monitoring loop that:
1. Subscribes to gateway events via an adapter
2. Buffers events and converts them to Traces
3. Periodically runs Tinman analysis on buffered traces
4. Dispatches findings via alerters
"""

import asyncio
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Callable

from ...ingest.base import Span, SpanEvent, SpanStatus, Trace
from ...utils import generate_id, get_logger, utc_now
from .alerter import AlertDispatcher, Finding
from .base import EventSeverity, EventType, GatewayAdapter, GatewayEvent

logger = get_logger("gateway_monitor")


@dataclass
class MonitorConfig:
    """Configuration for the gateway monitor."""

    # Buffering
    max_events: int = 10000
    max_traces: int = 1000
    session_timeout_seconds: int = 3600  # 1 hour

    # Analysis
    analysis_interval_seconds: int = 300  # 5 minutes
    min_events_for_analysis: int = 10

    # Connection
    reconnect_delay_seconds: float = 5.0
    max_reconnect_attempts: int = 10

    # Filtering
    event_types: list[EventType] | None = None  # None = all
    min_severity: EventSeverity = EventSeverity.INFO


@dataclass
class SessionBuffer:
    """Buffer for events within a single session."""

    session_id: str
    channel: str | None = None
    user_id: str | None = None
    events: list[GatewayEvent] = field(default_factory=list)
    started_at: datetime = field(default_factory=utc_now)
    last_event_at: datetime = field(default_factory=utc_now)

    def add_event(self, event: GatewayEvent) -> None:
        """Add an event to the buffer."""
        self.events.append(event)
        self.last_event_at = event.timestamp
        if not self.channel and event.channel:
            self.channel = event.channel
        if not self.user_id and event.user_id:
            self.user_id = event.user_id

    def is_stale(self, timeout_seconds: int) -> bool:
        """Check if session has timed out."""
        return (utc_now() - self.last_event_at).total_seconds() > timeout_seconds

    def to_trace(self) -> Trace:
        """Convert buffered events to a Tinman Trace."""
        trace_id = self.session_id or generate_id()
        spans: list[Span] = []
        current_span_id: str | None = None

        for event in sorted(self.events, key=lambda e: e.timestamp):
            span = self._event_to_span(event, trace_id, current_span_id)
            if span:
                spans.append(span)
                # Tool calls create child spans
                if event.event_type == EventType.TOOL_CALL_START:
                    current_span_id = span.span_id
                elif event.event_type == EventType.TOOL_CALL_END:
                    current_span_id = None

        return Trace(
            trace_id=trace_id,
            spans=spans,
            metadata={
                "channel": self.channel,
                "user_id": self.user_id,
                "event_count": len(self.events),
            },
            source="gateway_plugin",
            ingested_at=utc_now(),
        )

    def _event_to_span(
        self,
        event: GatewayEvent,
        trace_id: str,
        parent_span_id: str | None,
    ) -> Span | None:
        """Convert a single event to a Span."""
        # Skip events that don't map well to spans
        if event.event_type in (EventType.SESSION_START, EventType.SESSION_END):
            return None

        span_name = self._get_span_name(event)
        status = SpanStatus.OK
        status_message = None

        if event.error_type or event.error_message:
            status = SpanStatus.ERROR
            status_message = event.error_message

        if event.event_type == EventType.TOOL_BLOCKED:
            status = SpanStatus.ERROR
            status_message = "Tool blocked by policy"

        # Use short duration for point-in-time events
        end_time = event.timestamp + timedelta(milliseconds=1)

        span = Span(
            trace_id=trace_id,
            span_id=event.event_id,
            name=span_name,
            start_time=event.timestamp,
            end_time=end_time,
            parent_span_id=parent_span_id,
            status=status,
            status_message=status_message,
            kind=self._get_span_kind(event),
            service_name=event.channel or "unknown",
            attributes=self._get_span_attributes(event),
        )

        # Add events for errors
        if event.error_type:
            span.events.append(
                SpanEvent(
                    name="exception",
                    timestamp=event.timestamp,
                    attributes={
                        "exception.type": event.error_type,
                        "exception.message": event.error_message,
                    },
                )
            )

        return span

    def _get_span_name(self, event: GatewayEvent) -> str:
        """Get span name from event."""
        if event.tool_name:
            return f"tool.{event.tool_name}"
        if event.message_role:
            return f"message.{event.message_role}"
        return event.event_type.value

    def _get_span_kind(self, event: GatewayEvent) -> str:
        """Get span kind from event type."""
        if event.event_type in (EventType.LLM_REQUEST, EventType.TOOL_CALL_START):
            return "client"
        if event.event_type in (EventType.LLM_RESPONSE, EventType.TOOL_CALL_END):
            return "server"
        return "internal"

    def _get_span_attributes(self, event: GatewayEvent) -> dict[str, Any]:
        """Extract span attributes from event."""
        attrs: dict[str, Any] = {
            "event.type": event.event_type.value,
            "event.severity": event.severity.value,
        }

        if event.tool_name:
            attrs["tool.name"] = event.tool_name
        if event.tool_args:
            attrs["tool.args"] = str(event.tool_args)[:500]  # Truncate
        if event.message_role:
            attrs["message.role"] = event.message_role
        if event.message_content:
            attrs["message.content"] = event.message_content[:1000]  # Truncate
        if event.user_id:
            attrs["user.id"] = event.user_id

        return attrs


class TraceBuffer:
    """Circular buffer for Traces awaiting analysis."""

    def __init__(self, max_size: int = 1000):
        self._traces: deque[Trace] = deque(maxlen=max_size)
        self._analyzed_ids: set[str] = set()

    def add(self, trace: Trace) -> None:
        """Add a trace to the buffer."""
        self._traces.append(trace)

    def get_unanalyzed(self) -> list[Trace]:
        """Get traces that haven't been analyzed yet."""
        return [t for t in self._traces if t.trace_id not in self._analyzed_ids]

    def mark_analyzed(self, trace_ids: list[str]) -> None:
        """Mark traces as analyzed."""
        self._analyzed_ids.update(trace_ids)
        # Cleanup old IDs
        current_ids = {t.trace_id for t in self._traces}
        self._analyzed_ids &= current_ids

    def clear(self) -> None:
        """Clear the buffer."""
        self._traces.clear()
        self._analyzed_ids.clear()

    def __len__(self) -> int:
        return len(self._traces)


# Type alias for analyzer function
AnalyzerFunc = Callable[[list[Trace]], list[Finding]]


class GatewayMonitor:
    """Main gateway event monitor.

    Connects to a gateway via an adapter, buffers events,
    converts to traces, and runs periodic analysis.

    Usage:
        adapter = OpenClawAdapter("ws://127.0.0.1:18789")
        monitor = GatewayMonitor(adapter)
        monitor.add_alerter(ConsoleAlerter())
        await monitor.start()
    """

    def __init__(
        self,
        adapter: GatewayAdapter,
        config: MonitorConfig | None = None,
        analyzer: AnalyzerFunc | None = None,
    ):
        """Initialize the monitor.

        Args:
            adapter: Gateway adapter to use
            config: Monitor configuration
            analyzer: Function that takes traces and returns findings.
                     If None, uses default Tinman FailureClassifier.
        """
        self.adapter = adapter
        self.config = config or MonitorConfig()
        self._analyzer = analyzer

        # State
        self._running = False
        self._session_buffers: dict[str, SessionBuffer] = {}
        self._trace_buffer = TraceBuffer(max_size=self.config.max_traces)
        self._alerter = AlertDispatcher()

        # Stats
        self._events_received = 0
        self._traces_created = 0
        self._findings_count = 0

    def add_alerter(self, alerter: Any) -> None:
        """Add an alerter for dispatching findings."""
        self._alerter.add_alerter(alerter)

    async def start(self) -> None:
        """Start the monitor.

        Connects to the gateway and begins processing events.
        Runs until stop() is called.
        """
        if self._running:
            logger.warning("Monitor already running")
            return

        self._running = True
        logger.info(f"Starting gateway monitor with {self.adapter.name}")

        try:
            await self.adapter.connect()
            logger.info(f"Connected to {self.adapter.url}")

            # Run event loop and analysis loop concurrently
            await asyncio.gather(
                self._event_loop(),
                self._analysis_loop(),
                self._cleanup_loop(),
            )
        except asyncio.CancelledError:
            logger.info("Monitor cancelled")
        except Exception as e:
            logger.error(f"Monitor error: {e}")
            raise
        finally:
            self._running = False
            await self.adapter.disconnect()

    async def stop(self) -> None:
        """Stop the monitor."""
        logger.info("Stopping gateway monitor")
        self._running = False

    async def _event_loop(self) -> None:
        """Main event processing loop."""
        reconnect_attempts = 0

        while self._running:
            try:
                async for event in self.adapter.stream():
                    if not self._running:
                        break

                    self._events_received += 1
                    reconnect_attempts = 0  # Reset on successful event

                    # Filter events
                    if not self._should_process(event):
                        continue

                    # Buffer by session
                    self._buffer_event(event)

            except ConnectionError as e:
                if not self._running:
                    break

                reconnect_attempts += 1
                if reconnect_attempts > self.config.max_reconnect_attempts:
                    logger.error(f"Max reconnect attempts reached: {e}")
                    raise

                delay = self.config.reconnect_delay_seconds * (2 ** (reconnect_attempts - 1))
                logger.warning(f"Connection lost, reconnecting in {delay}s...")
                await asyncio.sleep(delay)

                try:
                    await self.adapter.connect()
                except Exception:
                    continue

    def _should_process(self, event: GatewayEvent) -> bool:
        """Check if event should be processed."""
        # Type filter
        if self.config.event_types and event.event_type not in self.config.event_types:
            return False

        # Severity filter
        severity_order = list(EventSeverity)
        if severity_order.index(event.severity) < severity_order.index(self.config.min_severity):
            return False

        return True

    def _buffer_event(self, event: GatewayEvent) -> None:
        """Add event to session buffer."""
        session_id = event.session_id or "default"

        if session_id not in self._session_buffers:
            self._session_buffers[session_id] = SessionBuffer(
                session_id=session_id,
                channel=event.channel,
                user_id=event.user_id,
            )

        self._session_buffers[session_id].add_event(event)

        # Check buffer size limit
        if len(self._session_buffers) > self.config.max_events // 10:
            self._flush_oldest_session()

    def _flush_oldest_session(self) -> None:
        """Flush the oldest session to trace buffer."""
        if not self._session_buffers:
            return

        oldest_id = min(
            self._session_buffers.keys(),
            key=lambda k: self._session_buffers[k].started_at,
        )
        self._flush_session(oldest_id)

    def _flush_session(self, session_id: str) -> None:
        """Convert session buffer to trace and add to trace buffer."""
        if session_id not in self._session_buffers:
            return

        session = self._session_buffers.pop(session_id)
        if session.events:
            trace = session.to_trace()
            self._trace_buffer.add(trace)
            self._traces_created += 1
            logger.debug(f"Flushed session {session_id}: {len(session.events)} events")

    async def _analysis_loop(self) -> None:
        """Periodic analysis of buffered traces."""
        while self._running:
            await asyncio.sleep(self.config.analysis_interval_seconds)

            if not self._running:
                break

            # Flush stale sessions first
            stale_sessions = [
                sid
                for sid, buf in self._session_buffers.items()
                if buf.is_stale(self.config.session_timeout_seconds)
            ]
            for sid in stale_sessions:
                self._flush_session(sid)

            # Get unanalyzed traces
            traces = self._trace_buffer.get_unanalyzed()
            if len(traces) < self.config.min_events_for_analysis:
                continue

            logger.info(f"Analyzing {len(traces)} traces")

            try:
                findings = await self._analyze_traces(traces)
                if findings:
                    self._findings_count += len(findings)
                    await self._alerter.dispatch(findings)

                self._trace_buffer.mark_analyzed([t.trace_id for t in traces])

            except Exception as e:
                logger.error(f"Analysis error: {e}")

    async def _analyze_traces(self, traces: list[Trace]) -> list[Finding]:
        """Run analysis on traces.

        Uses custom analyzer if provided, otherwise uses Tinman FailureClassifier.
        """
        if self._analyzer:
            return self._analyzer(traces)

        # Default: use Tinman FailureClassifier
        try:
            from ...agents.failure_classifier import FailureClassifier

            classifier = FailureClassifier()
            findings: list[Finding] = []

            for trace in traces:
                result = await classifier.classify(trace)
                if result and result.failures:
                    for failure in result.failures:
                        findings.append(
                            Finding(
                                finding_id=generate_id(),
                                trace_id=trace.trace_id,
                                severity=failure.severity,
                                category=failure.primary_class,
                                title=failure.secondary_class,
                                description=failure.explanation,
                                evidence=[],
                                mitigation=None,
                                timestamp=utc_now(),
                            )
                        )

            return findings

        except ImportError:
            logger.warning("FailureClassifier not available, skipping analysis")
            return []

    async def _cleanup_loop(self) -> None:
        """Periodic cleanup of old data."""
        while self._running:
            await asyncio.sleep(self.config.session_timeout_seconds)

            if not self._running:
                break

            # Cleanup stale sessions
            stale = [
                sid
                for sid, buf in self._session_buffers.items()
                if buf.is_stale(self.config.session_timeout_seconds * 2)
            ]
            for sid in stale:
                self._flush_session(sid)

    def get_stats(self) -> dict[str, Any]:
        """Get monitor statistics."""
        return {
            "running": self._running,
            "events_received": self._events_received,
            "traces_created": self._traces_created,
            "findings_count": self._findings_count,
            "active_sessions": len(self._session_buffers),
            "buffered_traces": len(self._trace_buffer),
            "adapter": self.adapter.name,
            "connected": self.adapter.state.connected,
        }
