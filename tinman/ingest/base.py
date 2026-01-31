"""Base types and abstract adapter for trace ingestion.

This module defines the canonical trace model that all adapters
transform external formats into.
"""

from abc import ABC, abstractmethod
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from ..utils import get_logger

logger = get_logger("ingest")


class SpanStatus(str, Enum):
    """Status of a span execution."""

    UNSET = "unset"
    OK = "ok"
    ERROR = "error"


@dataclass
class SpanEvent:
    """An event within a span (e.g., exception, log message)."""

    name: str
    timestamp: datetime
    attributes: dict[str, Any] = field(default_factory=dict)

    def is_exception(self) -> bool:
        """Check if this event represents an exception."""
        return (
            self.name == "exception"
            or "exception.type" in self.attributes
            or "exception.message" in self.attributes
        )

    def get_exception_info(self) -> dict[str, Any] | None:
        """Extract exception information if this is an exception event."""
        if not self.is_exception():
            return None
        return {
            "type": self.attributes.get("exception.type"),
            "message": self.attributes.get("exception.message"),
            "stacktrace": self.attributes.get("exception.stacktrace"),
        }


@dataclass
class SpanLink:
    """A link from one span to another (cross-trace reference)."""

    trace_id: str
    span_id: str
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass
class Span:
    """A single span within a trace.

    This is Tinman's canonical span representation. All adapter
    implementations must transform their native format into this.
    """

    trace_id: str
    span_id: str
    name: str
    start_time: datetime
    end_time: datetime
    parent_span_id: str | None = None
    status: SpanStatus = SpanStatus.UNSET
    status_message: str | None = None
    kind: str = "internal"  # client, server, producer, consumer, internal
    service_name: str | None = None
    attributes: dict[str, Any] = field(default_factory=dict)
    events: list[SpanEvent] = field(default_factory=list)
    links: list[SpanLink] = field(default_factory=list)
    resource_attributes: dict[str, Any] = field(default_factory=dict)

    @property
    def duration_ms(self) -> float:
        """Duration in milliseconds."""
        delta = self.end_time - self.start_time
        return delta.total_seconds() * 1000

    @property
    def is_root(self) -> bool:
        """Check if this is a root span."""
        return self.parent_span_id is None

    @property
    def is_error(self) -> bool:
        """Check if this span has an error status."""
        return self.status == SpanStatus.ERROR

    def has_exception(self) -> bool:
        """Check if this span contains an exception event."""
        return any(e.is_exception() for e in self.events)

    def get_exceptions(self) -> list[dict[str, Any]]:
        """Get all exception information from events."""
        return [info for e in self.events if (info := e.get_exception_info()) is not None]

    def get_attribute(self, key: str, default: Any = None) -> Any:
        """Get an attribute value with fallback to resource attributes."""
        if key in self.attributes:
            return self.attributes[key]
        return self.resource_attributes.get(key, default)


@dataclass
class Trace:
    """A complete trace consisting of multiple spans.

    Tinman's canonical trace representation.
    """

    trace_id: str
    spans: list[Span] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    source: str = "unknown"  # Which adapter produced this
    ingested_at: datetime | None = None

    @property
    def root_span(self) -> Span | None:
        """Get the root span of this trace."""
        for span in self.spans:
            if span.is_root:
                return span
        return None

    @property
    def duration_ms(self) -> float | None:
        """Total trace duration in milliseconds."""
        root = self.root_span
        return root.duration_ms if root else None

    @property
    def span_count(self) -> int:
        """Number of spans in this trace."""
        return len(self.spans)

    @property
    def error_spans(self) -> list[Span]:
        """Get all spans with errors."""
        return [s for s in self.spans if s.is_error]

    @property
    def has_errors(self) -> bool:
        """Check if any span in the trace has errors."""
        return any(s.is_error for s in self.spans)

    @property
    def services(self) -> set[str]:
        """Get all unique service names in this trace."""
        return {s.service_name for s in self.spans if s.service_name}

    def get_spans_by_service(self, service_name: str) -> list[Span]:
        """Get all spans for a specific service."""
        return [s for s in self.spans if s.service_name == service_name]

    def get_span_by_id(self, span_id: str) -> Span | None:
        """Get a span by its ID."""
        for span in self.spans:
            if span.span_id == span_id:
                return span
        return None

    def get_children(self, span_id: str) -> list[Span]:
        """Get direct children of a span."""
        return [s for s in self.spans if s.parent_span_id == span_id]

    def build_tree(self) -> dict[str, list[Span]]:
        """Build a tree structure of spans (parent_id -> children)."""
        tree: dict[str, list[Span]] = {}
        for span in self.spans:
            parent = span.parent_span_id or "root"
            if parent not in tree:
                tree[parent] = []
            tree[parent].append(span)
        return tree


@dataclass
class IngestResult:
    """Result of ingesting traces."""

    success: bool
    traces_ingested: int
    spans_ingested: int
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def success_result(
        cls,
        traces: int,
        spans: int,
        **metadata: Any,
    ) -> "IngestResult":
        """Create a success result."""
        return cls(
            success=True,
            traces_ingested=traces,
            spans_ingested=spans,
            metadata=metadata,
        )

    @classmethod
    def failure_result(cls, error: str, **metadata: Any) -> "IngestResult":
        """Create a failure result."""
        return cls(
            success=False,
            traces_ingested=0,
            spans_ingested=0,
            errors=[error],
            metadata=metadata,
        )


class TraceAdapter(ABC):
    """Abstract base class for trace ingestion adapters.

    Each adapter transforms a specific trace format (OTLP, Datadog, etc.)
    into Tinman's canonical Trace/Span model.

    Usage:
        adapter = OTLPAdapter()
        traces = list(adapter.parse(otlp_data))
        result = await adapter.ingest(otlp_data, storage)
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Adapter name for identification."""
        pass

    @property
    @abstractmethod
    def supported_formats(self) -> list[str]:
        """List of format identifiers this adapter supports."""
        pass

    @abstractmethod
    def parse(self, data: Any) -> Iterator[Trace]:
        """Parse raw data into Trace objects.

        Args:
            data: Raw data in the adapter's native format

        Yields:
            Trace objects
        """
        pass

    @abstractmethod
    def validate(self, data: Any) -> tuple[bool, list[str]]:
        """Validate that data is in the expected format.

        Args:
            data: Raw data to validate

        Returns:
            Tuple of (is_valid, list of error messages)
        """
        pass

    async def ingest(
        self,
        data: Any,
        storage: Any | None = None,
    ) -> IngestResult:
        """Parse and optionally store traces.

        Args:
            data: Raw trace data
            storage: Optional storage backend for persisting traces

        Returns:
            IngestResult with counts and any errors
        """
        # Validate first
        is_valid, errors = self.validate(data)
        if not is_valid:
            return IngestResult.failure_result(
                f"Validation failed: {'; '.join(errors)}",
                adapter=self.name,
            )

        # Parse traces
        traces_ingested = 0
        spans_ingested = 0
        ingest_errors: list[str] = []

        try:
            for trace in self.parse(data):
                traces_ingested += 1
                spans_ingested += len(trace.spans)

                if storage:
                    try:
                        await self._store_trace(trace, storage)
                    except Exception as e:
                        ingest_errors.append(f"Failed to store trace {trace.trace_id}: {e}")
        except Exception as e:
            return IngestResult.failure_result(
                f"Parse error: {e}",
                adapter=self.name,
                partial_traces=traces_ingested,
            )

        return IngestResult(
            success=len(ingest_errors) == 0,
            traces_ingested=traces_ingested,
            spans_ingested=spans_ingested,
            errors=ingest_errors,
            metadata={"adapter": self.name},
        )

    async def _store_trace(self, trace: Trace, storage: Any) -> None:
        """Store a trace in the backend.

        Override this method for custom storage logic.
        """
        if hasattr(storage, "store_trace"):
            await storage.store_trace(trace)
        elif hasattr(storage, "add"):
            storage.add(trace)

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}({self.name})>"
