"""OpenTelemetry (OTLP) trace adapter.

This adapter handles traces in OpenTelemetry Protocol format,
both protobuf and JSON representations.
"""

from datetime import datetime, timezone
from typing import Any, Iterator, Optional

from .base import (
    TraceAdapter,
    Trace,
    Span,
    SpanEvent,
    SpanLink,
    SpanStatus,
    IngestResult,
)
from ..utils import get_logger

logger = get_logger("ingest.otlp")


class OTLPAdapter(TraceAdapter):
    """Adapter for OpenTelemetry Protocol traces.

    Supports both JSON and protobuf-serialized OTLP data.

    Usage:
        adapter = OTLPAdapter()

        # From JSON
        traces = list(adapter.parse(otlp_json))

        # Validate first
        is_valid, errors = adapter.validate(data)
    """

    @property
    def name(self) -> str:
        return "otlp"

    @property
    def supported_formats(self) -> list[str]:
        return ["otlp", "opentelemetry", "otel"]

    def validate(self, data: Any) -> tuple[bool, list[str]]:
        """Validate OTLP data structure."""
        errors: list[str] = []

        if not isinstance(data, dict):
            return False, ["Data must be a dictionary"]

        # Check for resource spans (OTLP structure)
        if "resourceSpans" not in data:
            errors.append("Missing 'resourceSpans' field")
            return False, errors

        resource_spans = data["resourceSpans"]
        if not isinstance(resource_spans, list):
            errors.append("'resourceSpans' must be a list")
            return False, errors

        for i, rs in enumerate(resource_spans):
            if not isinstance(rs, dict):
                errors.append(f"resourceSpans[{i}] must be a dictionary")
                continue

            if "scopeSpans" not in rs and "instrumentationLibrarySpans" not in rs:
                errors.append(
                    f"resourceSpans[{i}] missing 'scopeSpans' or "
                    "'instrumentationLibrarySpans'"
                )

        return len(errors) == 0, errors

    def parse(self, data: Any) -> Iterator[Trace]:
        """Parse OTLP JSON data into Trace objects."""
        # Group spans by trace ID
        traces_by_id: dict[str, list[Span]] = {}
        resource_attrs_by_trace: dict[str, dict[str, Any]] = {}

        for resource_span in data.get("resourceSpans", []):
            resource = resource_span.get("resource", {})
            resource_attrs = self._parse_attributes(
                resource.get("attributes", [])
            )

            # Handle both scopeSpans and instrumentationLibrarySpans
            scope_spans_list = resource_span.get(
                "scopeSpans",
                resource_span.get("instrumentationLibrarySpans", [])
            )

            for scope_spans in scope_spans_list:
                for span_data in scope_spans.get("spans", []):
                    span = self._parse_span(span_data, resource_attrs)

                    if span.trace_id not in traces_by_id:
                        traces_by_id[span.trace_id] = []
                        resource_attrs_by_trace[span.trace_id] = resource_attrs

                    traces_by_id[span.trace_id].append(span)

        # Yield complete traces
        for trace_id, spans in traces_by_id.items():
            yield Trace(
                trace_id=trace_id,
                spans=spans,
                source=self.name,
                ingested_at=datetime.now(timezone.utc),
                metadata={
                    "resource_attributes": resource_attrs_by_trace.get(
                        trace_id, {}
                    )
                },
            )

    def _parse_span(
        self,
        data: dict[str, Any],
        resource_attrs: dict[str, Any],
    ) -> Span:
        """Parse a single span from OTLP format."""
        trace_id = self._decode_id(data.get("traceId", ""))
        span_id = self._decode_id(data.get("spanId", ""))
        parent_id = self._decode_id(data.get("parentSpanId", ""))

        # Parse timestamps (nanoseconds since epoch)
        start_time = self._parse_timestamp(data.get("startTimeUnixNano", 0))
        end_time = self._parse_timestamp(data.get("endTimeUnixNano", 0))

        # Parse status
        status_data = data.get("status", {})
        status = self._parse_status(status_data)

        # Parse span kind
        kind = self._parse_kind(data.get("kind", 0))

        # Parse attributes
        attributes = self._parse_attributes(data.get("attributes", []))

        # Parse events
        events = [
            self._parse_event(e)
            for e in data.get("events", [])
        ]

        # Parse links
        links = [
            self._parse_link(link)
            for link in data.get("links", [])
        ]

        # Get service name from resource attributes
        service_name = resource_attrs.get("service.name")

        return Span(
            trace_id=trace_id,
            span_id=span_id,
            parent_span_id=parent_id if parent_id else None,
            name=data.get("name", "unknown"),
            start_time=start_time,
            end_time=end_time,
            status=status,
            status_message=status_data.get("message"),
            kind=kind,
            service_name=service_name,
            attributes=attributes,
            events=events,
            links=links,
            resource_attributes=resource_attrs,
        )

    def _parse_event(self, data: dict[str, Any]) -> SpanEvent:
        """Parse a span event."""
        return SpanEvent(
            name=data.get("name", ""),
            timestamp=self._parse_timestamp(data.get("timeUnixNano", 0)),
            attributes=self._parse_attributes(data.get("attributes", [])),
        )

    def _parse_link(self, data: dict[str, Any]) -> SpanLink:
        """Parse a span link."""
        return SpanLink(
            trace_id=self._decode_id(data.get("traceId", "")),
            span_id=self._decode_id(data.get("spanId", "")),
            attributes=self._parse_attributes(data.get("attributes", [])),
        )

    def _parse_status(self, data: dict[str, Any]) -> SpanStatus:
        """Parse span status."""
        code = data.get("code", 0)
        # OTLP status codes: 0=UNSET, 1=OK, 2=ERROR
        if code == 1:
            return SpanStatus.OK
        if code == 2:
            return SpanStatus.ERROR
        return SpanStatus.UNSET

    def _parse_kind(self, kind: int) -> str:
        """Parse span kind from OTLP integer."""
        kinds = {
            0: "unspecified",
            1: "internal",
            2: "server",
            3: "client",
            4: "producer",
            5: "consumer",
        }
        return kinds.get(kind, "internal")

    def _parse_attributes(
        self,
        attrs: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Parse OTLP attribute array to dictionary."""
        result: dict[str, Any] = {}
        for attr in attrs:
            key = attr.get("key", "")
            value = attr.get("value", {})
            result[key] = self._parse_attribute_value(value)
        return result

    def _parse_attribute_value(self, value: dict[str, Any]) -> Any:
        """Parse an OTLP attribute value."""
        if "stringValue" in value:
            return value["stringValue"]
        if "intValue" in value:
            return int(value["intValue"])
        if "doubleValue" in value:
            return float(value["doubleValue"])
        if "boolValue" in value:
            return bool(value["boolValue"])
        if "arrayValue" in value:
            return [
                self._parse_attribute_value(v)
                for v in value["arrayValue"].get("values", [])
            ]
        if "kvlistValue" in value:
            return {
                kv["key"]: self._parse_attribute_value(kv.get("value", {}))
                for kv in value["kvlistValue"].get("values", [])
            }
        if "bytesValue" in value:
            return value["bytesValue"]
        return None

    def _parse_timestamp(self, nanos: int | str) -> datetime:
        """Parse nanosecond timestamp to datetime."""
        if isinstance(nanos, str):
            nanos = int(nanos)
        seconds = nanos / 1_000_000_000
        return datetime.fromtimestamp(seconds, tz=timezone.utc)

    def _decode_id(self, value: str) -> str:
        """Decode trace/span ID.

        IDs can be hex strings or base64 encoded bytes.
        """
        if not value:
            return ""

        # If it looks like hex, return as-is
        if all(c in "0123456789abcdefABCDEF" for c in value):
            return value.lower()

        # Try base64 decode
        try:
            import base64
            decoded = base64.b64decode(value)
            return decoded.hex()
        except Exception:
            return value
