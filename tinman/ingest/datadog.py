"""Datadog APM trace adapter.

This adapter handles traces from Datadog's APM format.
"""

from datetime import datetime, timezone
from typing import Any, Iterator

from .base import (
    TraceAdapter,
    Trace,
    Span,
    SpanEvent,
    SpanStatus,
)
from ..utils import get_logger

logger = get_logger("ingest.datadog")


class DatadogAdapter(TraceAdapter):
    """Adapter for Datadog APM traces.

    Datadog traces are typically arrays of span arrays,
    where each inner array represents spans from a single trace.

    Usage:
        adapter = DatadogAdapter()
        traces = list(adapter.parse(datadog_traces))
    """

    @property
    def name(self) -> str:
        return "datadog"

    @property
    def supported_formats(self) -> list[str]:
        return ["datadog", "dd", "dd-apm"]

    def validate(self, data: Any) -> tuple[bool, list[str]]:
        """Validate Datadog trace data structure."""
        errors: list[str] = []

        # Datadog format: list of trace arrays
        if not isinstance(data, list):
            return False, ["Data must be a list of traces"]

        for i, trace_spans in enumerate(data):
            if not isinstance(trace_spans, list):
                errors.append(f"Trace {i} must be a list of spans")
                continue

            for j, span in enumerate(trace_spans):
                if not isinstance(span, dict):
                    errors.append(f"Trace {i} span {j} must be a dictionary")
                    continue

                # Required fields
                required = ["trace_id", "span_id", "name", "start", "duration"]
                for field in required:
                    if field not in span:
                        errors.append(
                            f"Trace {i} span {j} missing required field '{field}'"
                        )

        return len(errors) == 0, errors

    def parse(self, data: Any) -> Iterator[Trace]:
        """Parse Datadog trace data into Trace objects."""
        for trace_spans in data:
            if not trace_spans:
                continue

            # Get trace ID from first span
            first_span = trace_spans[0]
            trace_id = str(first_span.get("trace_id", ""))

            spans = [
                self._parse_span(span_data)
                for span_data in trace_spans
            ]

            yield Trace(
                trace_id=trace_id,
                spans=spans,
                source=self.name,
                ingested_at=datetime.now(timezone.utc),
            )

    def _parse_span(self, data: dict[str, Any]) -> Span:
        """Parse a single Datadog span."""
        trace_id = str(data.get("trace_id", ""))
        span_id = str(data.get("span_id", ""))
        parent_id = data.get("parent_id")

        # Datadog uses nanoseconds since epoch for start,
        # and duration in nanoseconds
        start_ns = data.get("start", 0)
        duration_ns = data.get("duration", 0)

        start_time = datetime.fromtimestamp(
            start_ns / 1_000_000_000,
            tz=timezone.utc
        )
        end_time = datetime.fromtimestamp(
            (start_ns + duration_ns) / 1_000_000_000,
            tz=timezone.utc
        )

        # Parse error status from meta or error field
        meta = data.get("meta", {})
        metrics = data.get("metrics", {})

        is_error = data.get("error", 0) == 1
        status = SpanStatus.ERROR if is_error else SpanStatus.OK

        # Build attributes from meta and metrics
        attributes: dict[str, Any] = {}
        attributes.update(meta)
        attributes.update({f"metric.{k}": v for k, v in metrics.items()})

        # Parse events from meta if present
        events: list[SpanEvent] = []
        if is_error:
            # Create error event from meta
            error_event = SpanEvent(
                name="exception",
                timestamp=start_time,
                attributes={
                    "exception.type": meta.get("error.type", "Error"),
                    "exception.message": meta.get("error.msg", ""),
                    "exception.stacktrace": meta.get("error.stack", ""),
                },
            )
            events.append(error_event)

        # Map Datadog span type to kind
        span_type = data.get("type", "")
        kind = self._map_span_type(span_type)

        return Span(
            trace_id=trace_id,
            span_id=span_id,
            parent_span_id=str(parent_id) if parent_id else None,
            name=data.get("name", "unknown"),
            start_time=start_time,
            end_time=end_time,
            status=status,
            status_message=meta.get("error.msg"),
            kind=kind,
            service_name=data.get("service"),
            attributes=attributes,
            events=events,
            resource_attributes={
                "dd.resource": data.get("resource", ""),
                "dd.type": span_type,
            },
        )

    def _map_span_type(self, span_type: str) -> str:
        """Map Datadog span type to OpenTelemetry span kind."""
        type_map = {
            "web": "server",
            "http": "client",
            "sql": "client",
            "cache": "client",
            "queue": "producer",
            "worker": "consumer",
            "custom": "internal",
        }
        return type_map.get(span_type.lower(), "internal")


class DatadogV2Adapter(TraceAdapter):
    """Adapter for Datadog v2 API trace format.

    The v2 format uses a different structure with explicit trace containers.
    """

    @property
    def name(self) -> str:
        return "datadog_v2"

    @property
    def supported_formats(self) -> list[str]:
        return ["datadog_v2", "dd_v2"]

    def validate(self, data: Any) -> tuple[bool, list[str]]:
        """Validate Datadog v2 trace data."""
        errors: list[str] = []

        if not isinstance(data, dict):
            return False, ["Data must be a dictionary"]

        if "traces" not in data:
            errors.append("Missing 'traces' field")

        return len(errors) == 0, errors

    def parse(self, data: Any) -> Iterator[Trace]:
        """Parse Datadog v2 format."""
        base_adapter = DatadogAdapter()

        traces_data = data.get("traces", [])
        for trace_data in traces_data:
            spans_data = trace_data.get("spans", [])
            if spans_data:
                # Use base adapter's parsing
                for trace in base_adapter.parse([spans_data]):
                    yield trace
