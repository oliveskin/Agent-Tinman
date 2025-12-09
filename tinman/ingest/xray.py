"""AWS X-Ray trace adapter.

This adapter handles traces from AWS X-Ray format.
"""

from datetime import datetime, timezone
from typing import Any, Iterator, Optional

from .base import (
    TraceAdapter,
    Trace,
    Span,
    SpanEvent,
    SpanStatus,
)
from ..utils import get_logger

logger = get_logger("ingest.xray")


class XRayAdapter(TraceAdapter):
    """Adapter for AWS X-Ray traces.

    X-Ray traces consist of segments and subsegments with a
    hierarchical structure.

    Usage:
        adapter = XRayAdapter()
        traces = list(adapter.parse(xray_data))
    """

    @property
    def name(self) -> str:
        return "xray"

    @property
    def supported_formats(self) -> list[str]:
        return ["xray", "aws-xray", "x-ray"]

    def validate(self, data: Any) -> tuple[bool, list[str]]:
        """Validate X-Ray trace data structure."""
        errors: list[str] = []

        # X-Ray format can be:
        # 1. Single segment/trace document
        # 2. Array of segments
        # 3. Batch format with "Traces" key

        if isinstance(data, dict):
            if "Traces" in data:
                # Batch format
                traces = data["Traces"]
                if not isinstance(traces, list):
                    errors.append("'Traces' must be a list")
            elif "trace_id" not in data and "TraceId" not in data:
                # Single segment needs trace_id
                if "Id" not in data:
                    errors.append(
                        "Single segment must have 'trace_id', 'TraceId', or 'Id'"
                    )
        elif isinstance(data, list):
            for i, item in enumerate(data):
                if not isinstance(item, dict):
                    errors.append(f"Item {i} must be a dictionary")
        else:
            errors.append("Data must be a dictionary or list")

        return len(errors) == 0, errors

    def parse(self, data: Any) -> Iterator[Trace]:
        """Parse X-Ray trace data into Trace objects."""
        # Normalize to list of segments
        segments: list[dict[str, Any]]

        if isinstance(data, dict):
            if "Traces" in data:
                # Batch format - flatten all segments
                segments = []
                for trace in data["Traces"]:
                    segments.extend(trace.get("Segments", []))
            else:
                segments = [data]
        else:
            segments = data

        # Group segments by trace ID
        traces_by_id: dict[str, list[dict[str, Any]]] = {}

        for segment in segments:
            trace_id = self._get_trace_id(segment)
            if trace_id:
                if trace_id not in traces_by_id:
                    traces_by_id[trace_id] = []
                traces_by_id[trace_id].append(segment)

        # Parse each trace
        for trace_id, trace_segments in traces_by_id.items():
            spans = self._parse_segments(trace_segments, trace_id)

            yield Trace(
                trace_id=trace_id,
                spans=spans,
                source=self.name,
                ingested_at=datetime.now(timezone.utc),
            )

    def _get_trace_id(self, segment: dict[str, Any]) -> Optional[str]:
        """Extract trace ID from segment."""
        # X-Ray trace IDs can be in multiple formats
        trace_id = segment.get("trace_id") or segment.get("TraceId")

        if trace_id:
            # X-Ray format: 1-{hex timestamp}-{96 bit random}
            # Normalize to hex string
            return trace_id.replace("-", "")

        return None

    def _parse_segments(
        self,
        segments: list[dict[str, Any]],
        trace_id: str,
    ) -> list[Span]:
        """Parse X-Ray segments and subsegments into Spans."""
        spans: list[Span] = []

        for segment in segments:
            # Parse main segment
            main_span = self._parse_segment(segment, trace_id, None)
            spans.append(main_span)

            # Parse subsegments recursively
            self._parse_subsegments(
                segment.get("subsegments", []),
                trace_id,
                main_span.span_id,
                spans,
            )

        return spans

    def _parse_subsegments(
        self,
        subsegments: list[dict[str, Any]],
        trace_id: str,
        parent_id: str,
        spans: list[Span],
    ) -> None:
        """Recursively parse subsegments."""
        for subseg in subsegments:
            span = self._parse_segment(subseg, trace_id, parent_id)
            spans.append(span)

            # Recurse into nested subsegments
            self._parse_subsegments(
                subseg.get("subsegments", []),
                trace_id,
                span.span_id,
                spans,
            )

    def _parse_segment(
        self,
        data: dict[str, Any],
        trace_id: str,
        parent_id: Optional[str],
    ) -> Span:
        """Parse a single X-Ray segment or subsegment."""
        span_id = data.get("id") or data.get("Id", "")

        # X-Ray uses epoch seconds for timestamps
        start_time = datetime.fromtimestamp(
            data.get("start_time", 0),
            tz=timezone.utc
        )
        end_time = datetime.fromtimestamp(
            data.get("end_time", data.get("start_time", 0)),
            tz=timezone.utc
        )

        # Determine status
        is_error = data.get("error", False)
        is_fault = data.get("fault", False)
        is_throttle = data.get("throttle", False)

        if is_fault or is_error:
            status = SpanStatus.ERROR
        elif is_throttle:
            status = SpanStatus.ERROR
        else:
            status = SpanStatus.OK

        # Build attributes
        attributes: dict[str, Any] = {}

        # Add annotations (indexed metadata)
        annotations = data.get("annotations", {})
        for k, v in annotations.items():
            attributes[f"annotation.{k}"] = v

        # Add metadata (non-indexed)
        metadata = data.get("metadata", {})
        for namespace, values in metadata.items():
            if isinstance(values, dict):
                for k, v in values.items():
                    attributes[f"metadata.{namespace}.{k}"] = v

        # Add HTTP data if present
        http_data = data.get("http", {})
        if http_data:
            request = http_data.get("request", {})
            response = http_data.get("response", {})

            if request:
                attributes["http.method"] = request.get("method")
                attributes["http.url"] = request.get("url")
                attributes["http.user_agent"] = request.get("user_agent")
                attributes["http.client_ip"] = request.get("client_ip")

            if response:
                attributes["http.status_code"] = response.get("status")
                attributes["http.response_content_length"] = response.get(
                    "content_length"
                )

        # Add AWS data if present
        aws_data = data.get("aws", {})
        if aws_data:
            attributes["aws.operation"] = aws_data.get("operation")
            attributes["aws.region"] = aws_data.get("region")
            attributes["aws.request_id"] = aws_data.get("request_id")
            attributes["aws.table_name"] = aws_data.get("table_name")
            attributes["aws.queue_url"] = aws_data.get("queue_url")

        # Add SQL data if present
        sql_data = data.get("sql", {})
        if sql_data:
            attributes["db.statement"] = sql_data.get("sanitized_query")
            attributes["db.url"] = sql_data.get("url")
            attributes["db.user"] = sql_data.get("user")

        # Parse events from cause (exceptions)
        events: list[SpanEvent] = []
        cause = data.get("cause", {})
        if cause:
            exceptions = cause.get("exceptions", [])
            for exc in exceptions:
                events.append(SpanEvent(
                    name="exception",
                    timestamp=start_time,
                    attributes={
                        "exception.type": exc.get("type", "Exception"),
                        "exception.message": exc.get("message", ""),
                        "exception.id": exc.get("id"),
                        "exception.remote": exc.get("remote", False),
                    },
                ))

        # Determine span kind
        kind = self._determine_kind(data)

        # Get service name
        service_name = data.get("name") or data.get("origin")

        return Span(
            trace_id=trace_id,
            span_id=span_id,
            parent_span_id=parent_id,
            name=data.get("name", "unknown"),
            start_time=start_time,
            end_time=end_time,
            status=status,
            status_message=self._get_status_message(data),
            kind=kind,
            service_name=service_name,
            attributes=attributes,
            events=events,
            resource_attributes={
                "xray.origin": data.get("origin", ""),
                "xray.namespace": data.get("namespace", ""),
            },
        )

    def _determine_kind(self, data: dict[str, Any]) -> str:
        """Determine span kind from X-Ray segment data."""
        origin = data.get("origin", "")
        namespace = data.get("namespace", "")

        if origin in ["AWS::EC2::Instance", "AWS::Lambda::Function"]:
            return "server"
        if namespace == "remote":
            return "client"
        if namespace == "aws":
            return "client"
        if "http" in data and "request" in data["http"]:
            return "server" if not data.get("parent_id") else "client"

        return "internal"

    def _get_status_message(self, data: dict[str, Any]) -> Optional[str]:
        """Extract status message from segment."""
        cause = data.get("cause", {})
        if cause:
            exceptions = cause.get("exceptions", [])
            if exceptions:
                return exceptions[0].get("message")
            return cause.get("message")
        return None
