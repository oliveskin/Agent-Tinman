"""Generic JSON trace adapter.

This adapter handles a simple, flexible JSON format for traces,
useful for custom integrations and testing.
"""

from collections.abc import Iterator
from datetime import datetime, timezone
from typing import Any

from ..utils import get_logger
from .base import (
    Span,
    SpanEvent,
    SpanLink,
    SpanStatus,
    Trace,
    TraceAdapter,
)

logger = get_logger("ingest.json")


class JSONAdapter(TraceAdapter):
    """Adapter for generic JSON trace format.

    This adapter accepts a flexible JSON structure that maps
    closely to Tinman's canonical model. It's useful for:
    - Custom integrations
    - Testing
    - Manual trace creation
    - Migrations from other formats

    Expected format:
    {
        "traces": [
            {
                "trace_id": "abc123",
                "spans": [
                    {
                        "span_id": "span1",
                        "name": "operation",
                        "start_time": "2024-01-01T00:00:00Z",
                        "end_time": "2024-01-01T00:00:01Z",
                        "parent_span_id": null,
                        "status": "ok",
                        "service_name": "my-service",
                        "attributes": {"key": "value"},
                        "events": [...],
                        "links": [...]
                    }
                ],
                "metadata": {"key": "value"}
            }
        ]
    }
    """

    @property
    def name(self) -> str:
        return "json"

    @property
    def supported_formats(self) -> list[str]:
        return ["json", "generic", "tinman"]

    def validate(self, data: Any) -> tuple[bool, list[str]]:
        """Validate generic JSON trace data."""
        errors: list[str] = []

        if not isinstance(data, dict):
            return False, ["Data must be a dictionary"]

        if "traces" not in data:
            errors.append("Missing 'traces' field")
            return False, errors

        traces = data["traces"]
        if not isinstance(traces, list):
            errors.append("'traces' must be a list")
            return False, errors

        for i, trace in enumerate(traces):
            if not isinstance(trace, dict):
                errors.append(f"traces[{i}] must be a dictionary")
                continue

            if "trace_id" not in trace:
                errors.append(f"traces[{i}] missing 'trace_id'")

            if "spans" not in trace:
                errors.append(f"traces[{i}] missing 'spans'")
                continue

            spans = trace["spans"]
            if not isinstance(spans, list):
                errors.append(f"traces[{i}].spans must be a list")
                continue

            for j, span in enumerate(spans):
                span_errors = self._validate_span(span, i, j)
                errors.extend(span_errors)

        return len(errors) == 0, errors

    def _validate_span(
        self,
        span: Any,
        trace_idx: int,
        span_idx: int,
    ) -> list[str]:
        """Validate a single span."""
        errors: list[str] = []
        prefix = f"traces[{trace_idx}].spans[{span_idx}]"

        if not isinstance(span, dict):
            return [f"{prefix} must be a dictionary"]

        required = ["span_id", "name"]
        for field in required:
            if field not in span:
                errors.append(f"{prefix} missing '{field}'")

        # Validate time fields if present
        for field in ["start_time", "end_time"]:
            if field in span:
                value = span[field]
                if not isinstance(value, (str, int, float)):
                    errors.append(f"{prefix}.{field} must be string (ISO8601) or number")

        return errors

    def parse(self, data: Any) -> Iterator[Trace]:
        """Parse generic JSON trace data into Trace objects."""
        for trace_data in data.get("traces", []):
            trace_id = str(trace_data.get("trace_id", ""))

            spans = [
                self._parse_span(span_data, trace_id) for span_data in trace_data.get("spans", [])
            ]

            yield Trace(
                trace_id=trace_id,
                spans=spans,
                source=self.name,
                ingested_at=datetime.now(timezone.utc),
                metadata=trace_data.get("metadata", {}),
            )

    def _parse_span(
        self,
        data: dict[str, Any],
        trace_id: str,
    ) -> Span:
        """Parse a single span from JSON."""
        span_id = str(data.get("span_id", ""))
        parent_id = data.get("parent_span_id")

        # Parse timestamps
        start_time = self._parse_time(data.get("start_time"))
        end_time = self._parse_time(data.get("end_time"), default=start_time)

        # Parse status
        status = self._parse_status(data.get("status", "unset"))

        # Parse events
        events = [self._parse_event(e) for e in data.get("events", [])]

        # Parse links
        links = [self._parse_link(link) for link in data.get("links", [])]

        return Span(
            trace_id=trace_id,
            span_id=span_id,
            parent_span_id=str(parent_id) if parent_id else None,
            name=data.get("name", "unknown"),
            start_time=start_time,
            end_time=end_time,
            status=status,
            status_message=data.get("status_message"),
            kind=data.get("kind", "internal"),
            service_name=data.get("service_name"),
            attributes=data.get("attributes", {}),
            events=events,
            links=links,
            resource_attributes=data.get("resource_attributes", {}),
        )

    def _parse_event(self, data: dict[str, Any]) -> SpanEvent:
        """Parse a span event."""
        return SpanEvent(
            name=data.get("name", ""),
            timestamp=self._parse_time(data.get("timestamp")),
            attributes=data.get("attributes", {}),
        )

    def _parse_link(self, data: dict[str, Any]) -> SpanLink:
        """Parse a span link."""
        return SpanLink(
            trace_id=str(data.get("trace_id", "")),
            span_id=str(data.get("span_id", "")),
            attributes=data.get("attributes", {}),
        )

    def _parse_time(
        self,
        value: str | int | float | None,
        default: datetime | None = None,
    ) -> datetime:
        """Parse a timestamp value."""
        if value is None:
            return default or datetime.now(timezone.utc)

        if isinstance(value, (int, float)):
            # Assume epoch seconds
            return datetime.fromtimestamp(value, tz=timezone.utc)

        if isinstance(value, str):
            # Try ISO8601
            try:
                # Handle various ISO formats
                if value.endswith("Z"):
                    value = value[:-1] + "+00:00"
                return datetime.fromisoformat(value)
            except ValueError:
                pass

            # Try epoch as string
            try:
                return datetime.fromtimestamp(float(value), tz=timezone.utc)
            except ValueError:
                pass

        return default or datetime.now(timezone.utc)

    def _parse_status(self, value: str) -> SpanStatus:
        """Parse status string to SpanStatus."""
        value_lower = value.lower()
        if value_lower in ("ok", "success", "succeeded"):
            return SpanStatus.OK
        if value_lower in ("error", "failed", "failure"):
            return SpanStatus.ERROR
        return SpanStatus.UNSET


class SimplifiedJSONAdapter(TraceAdapter):
    """Adapter for simplified JSON trace format.

    This is an even simpler format for quick testing:
    [
        {
            "name": "operation",
            "duration_ms": 100,
            "error": false,
            "service": "my-service"
        }
    ]

    All spans are assumed to be in a single trace.
    """

    @property
    def name(self) -> str:
        return "json_simple"

    @property
    def supported_formats(self) -> list[str]:
        return ["json_simple", "simple"]

    def validate(self, data: Any) -> tuple[bool, list[str]]:
        """Validate simplified JSON format."""
        if not isinstance(data, list):
            return False, ["Data must be a list of spans"]

        errors: list[str] = []
        for i, span in enumerate(data):
            if not isinstance(span, dict):
                errors.append(f"spans[{i}] must be a dictionary")
                continue
            if "name" not in span:
                errors.append(f"spans[{i}] missing 'name'")

        return len(errors) == 0, errors

    def parse(self, data: Any) -> Iterator[Trace]:
        """Parse simplified JSON into a single trace."""
        import uuid

        trace_id = str(uuid.uuid4()).replace("-", "")
        now = datetime.now(timezone.utc)
        spans: list[Span] = []

        for i, span_data in enumerate(data):
            span_id = str(uuid.uuid4()).replace("-", "")[:16]
            duration_ms = span_data.get("duration_ms", 0)

            start_time = now
            end_time = now

            # Calculate times based on duration
            if duration_ms > 0:
                from datetime import timedelta

                end_time = start_time + timedelta(milliseconds=duration_ms)

            is_error = span_data.get("error", False)
            status = SpanStatus.ERROR if is_error else SpanStatus.OK

            spans.append(
                Span(
                    trace_id=trace_id,
                    span_id=span_id,
                    parent_span_id=spans[-1].span_id if spans else None,
                    name=span_data.get("name", f"span_{i}"),
                    start_time=start_time,
                    end_time=end_time,
                    status=status,
                    status_message=span_data.get("error_message"),
                    kind=span_data.get("kind", "internal"),
                    service_name=span_data.get("service"),
                    attributes=span_data.get("attributes", {}),
                )
            )

        if spans:
            yield Trace(
                trace_id=trace_id,
                spans=spans,
                source=self.name,
                ingested_at=now,
            )
