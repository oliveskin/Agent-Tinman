"""Tests for trace ingestion adapters."""

import pytest
from datetime import datetime, timezone

from tinman.ingest import (
    Trace,
    Span,
    SpanEvent,
    SpanStatus,
    OTLPAdapter,
    DatadogAdapter,
    XRayAdapter,
    JSONAdapter,
    AdapterRegistry,
    get_adapter,
    parse_traces,
)


class TestSpan:
    """Tests for Span data class."""

    def test_duration_ms(self):
        """Test duration calculation."""
        span = Span(
            trace_id="abc",
            span_id="123",
            name="test",
            start_time=datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc),
            end_time=datetime(2024, 1, 1, 0, 0, 1, 500000, tzinfo=timezone.utc),
        )
        assert span.duration_ms == 1500.0

    def test_is_root(self):
        """Test root span detection."""
        root = Span(
            trace_id="abc",
            span_id="123",
            name="root",
            start_time=datetime.now(timezone.utc),
            end_time=datetime.now(timezone.utc),
            parent_span_id=None,
        )
        child = Span(
            trace_id="abc",
            span_id="456",
            name="child",
            start_time=datetime.now(timezone.utc),
            end_time=datetime.now(timezone.utc),
            parent_span_id="123",
        )
        assert root.is_root is True
        assert child.is_root is False

    def test_is_error(self):
        """Test error status detection."""
        ok_span = Span(
            trace_id="abc",
            span_id="123",
            name="ok",
            start_time=datetime.now(timezone.utc),
            end_time=datetime.now(timezone.utc),
            status=SpanStatus.OK,
        )
        error_span = Span(
            trace_id="abc",
            span_id="456",
            name="error",
            start_time=datetime.now(timezone.utc),
            end_time=datetime.now(timezone.utc),
            status=SpanStatus.ERROR,
        )
        assert ok_span.is_error is False
        assert error_span.is_error is True

    def test_has_exception(self):
        """Test exception detection."""
        span_with_exc = Span(
            trace_id="abc",
            span_id="123",
            name="test",
            start_time=datetime.now(timezone.utc),
            end_time=datetime.now(timezone.utc),
            events=[
                SpanEvent(
                    name="exception",
                    timestamp=datetime.now(timezone.utc),
                    attributes={
                        "exception.type": "ValueError",
                        "exception.message": "test error",
                    },
                )
            ],
        )
        span_without_exc = Span(
            trace_id="abc",
            span_id="456",
            name="test",
            start_time=datetime.now(timezone.utc),
            end_time=datetime.now(timezone.utc),
        )
        assert span_with_exc.has_exception() is True
        assert span_without_exc.has_exception() is False


class TestTrace:
    """Tests for Trace data class."""

    def test_root_span(self):
        """Test root span retrieval."""
        spans = [
            Span(
                trace_id="abc",
                span_id="123",
                name="root",
                start_time=datetime.now(timezone.utc),
                end_time=datetime.now(timezone.utc),
                parent_span_id=None,
            ),
            Span(
                trace_id="abc",
                span_id="456",
                name="child",
                start_time=datetime.now(timezone.utc),
                end_time=datetime.now(timezone.utc),
                parent_span_id="123",
            ),
        ]
        trace = Trace(trace_id="abc", spans=spans)
        assert trace.root_span is not None
        assert trace.root_span.span_id == "123"

    def test_error_spans(self):
        """Test error span filtering."""
        spans = [
            Span(
                trace_id="abc",
                span_id="123",
                name="ok",
                start_time=datetime.now(timezone.utc),
                end_time=datetime.now(timezone.utc),
                status=SpanStatus.OK,
            ),
            Span(
                trace_id="abc",
                span_id="456",
                name="error",
                start_time=datetime.now(timezone.utc),
                end_time=datetime.now(timezone.utc),
                status=SpanStatus.ERROR,
            ),
        ]
        trace = Trace(trace_id="abc", spans=spans)
        assert len(trace.error_spans) == 1
        assert trace.error_spans[0].span_id == "456"
        assert trace.has_errors is True

    def test_services(self):
        """Test service enumeration."""
        spans = [
            Span(
                trace_id="abc",
                span_id="123",
                name="op1",
                start_time=datetime.now(timezone.utc),
                end_time=datetime.now(timezone.utc),
                service_name="service-a",
            ),
            Span(
                trace_id="abc",
                span_id="456",
                name="op2",
                start_time=datetime.now(timezone.utc),
                end_time=datetime.now(timezone.utc),
                service_name="service-b",
            ),
            Span(
                trace_id="abc",
                span_id="789",
                name="op3",
                start_time=datetime.now(timezone.utc),
                end_time=datetime.now(timezone.utc),
                service_name="service-a",
            ),
        ]
        trace = Trace(trace_id="abc", spans=spans)
        assert trace.services == {"service-a", "service-b"}


class TestOTLPAdapter:
    """Tests for OTLP adapter."""

    @pytest.fixture
    def adapter(self):
        return OTLPAdapter()

    @pytest.fixture
    def sample_otlp_data(self):
        return {
            "resourceSpans": [
                {
                    "resource": {
                        "attributes": [
                            {"key": "service.name", "value": {"stringValue": "test-service"}}
                        ]
                    },
                    "scopeSpans": [
                        {
                            "spans": [
                                {
                                    "traceId": "0123456789abcdef0123456789abcdef",
                                    "spanId": "0123456789abcdef",
                                    "name": "test-operation",
                                    "kind": 2,
                                    "startTimeUnixNano": "1704067200000000000",
                                    "endTimeUnixNano": "1704067201000000000",
                                    "status": {"code": 1},
                                    "attributes": [
                                        {"key": "http.method", "value": {"stringValue": "GET"}}
                                    ],
                                }
                            ]
                        }
                    ],
                }
            ]
        }

    def test_validate_valid(self, adapter, sample_otlp_data):
        """Test validation of valid OTLP data."""
        is_valid, errors = adapter.validate(sample_otlp_data)
        assert is_valid is True
        assert len(errors) == 0

    def test_validate_invalid(self, adapter):
        """Test validation of invalid data."""
        is_valid, errors = adapter.validate({})
        assert is_valid is False
        assert "Missing 'resourceSpans' field" in errors

    def test_parse(self, adapter, sample_otlp_data):
        """Test parsing OTLP data."""
        traces = list(adapter.parse(sample_otlp_data))
        assert len(traces) == 1

        trace = traces[0]
        assert trace.trace_id == "0123456789abcdef0123456789abcdef"
        assert len(trace.spans) == 1

        span = trace.spans[0]
        assert span.name == "test-operation"
        assert span.service_name == "test-service"
        assert span.kind == "server"
        assert span.status == SpanStatus.OK


class TestDatadogAdapter:
    """Tests for Datadog adapter."""

    @pytest.fixture
    def adapter(self):
        return DatadogAdapter()

    @pytest.fixture
    def sample_datadog_data(self):
        return [
            [
                {
                    "trace_id": 12345678901234567890,
                    "span_id": 9876543210987654321,
                    "name": "web.request",
                    "service": "my-service",
                    "resource": "/api/users",
                    "type": "web",
                    "start": 1704067200000000000,
                    "duration": 1000000000,
                    "error": 0,
                    "meta": {
                        "http.method": "GET",
                        "http.url": "/api/users",
                    },
                }
            ]
        ]

    def test_validate_valid(self, adapter, sample_datadog_data):
        """Test validation of valid Datadog data."""
        is_valid, errors = adapter.validate(sample_datadog_data)
        assert is_valid is True

    def test_validate_invalid(self, adapter):
        """Test validation of invalid data."""
        is_valid, errors = adapter.validate([[{"name": "incomplete"}]])
        assert is_valid is False
        assert any("missing required field" in e for e in errors)

    def test_parse(self, adapter, sample_datadog_data):
        """Test parsing Datadog data."""
        traces = list(adapter.parse(sample_datadog_data))
        assert len(traces) == 1

        trace = traces[0]
        assert len(trace.spans) == 1

        span = trace.spans[0]
        assert span.name == "web.request"
        assert span.service_name == "my-service"
        assert span.kind == "server"

    def test_parse_error_span(self, adapter):
        """Test parsing span with error."""
        data = [
            [
                {
                    "trace_id": 123,
                    "span_id": 456,
                    "name": "error.request",
                    "service": "test",
                    "start": 1704067200000000000,
                    "duration": 100000000,
                    "error": 1,
                    "meta": {
                        "error.type": "ValueError",
                        "error.msg": "test error",
                    },
                }
            ]
        ]
        traces = list(adapter.parse(data))
        span = traces[0].spans[0]
        assert span.is_error is True
        assert span.has_exception() is True


class TestXRayAdapter:
    """Tests for X-Ray adapter."""

    @pytest.fixture
    def adapter(self):
        return XRayAdapter()

    @pytest.fixture
    def sample_xray_data(self):
        return {
            "Traces": [
                {
                    "Segments": [
                        {
                            "trace_id": "1-5f84c7a5-abc123def456789012345678",
                            "id": "abc123def456",
                            "name": "my-lambda",
                            "start_time": 1704067200.0,
                            "end_time": 1704067201.0,
                            "origin": "AWS::Lambda::Function",
                            "http": {
                                "request": {
                                    "method": "GET",
                                    "url": "/api/test",
                                },
                                "response": {
                                    "status": 200,
                                },
                            },
                        }
                    ]
                }
            ]
        }

    def test_validate_valid(self, adapter, sample_xray_data):
        """Test validation of valid X-Ray data."""
        is_valid, errors = adapter.validate(sample_xray_data)
        assert is_valid is True

    def test_parse(self, adapter, sample_xray_data):
        """Test parsing X-Ray data."""
        traces = list(adapter.parse(sample_xray_data))
        assert len(traces) == 1

        span = traces[0].spans[0]
        assert span.name == "my-lambda"
        assert span.kind == "server"
        assert span.attributes.get("http.method") == "GET"


class TestJSONAdapter:
    """Tests for generic JSON adapter."""

    @pytest.fixture
    def adapter(self):
        return JSONAdapter()

    @pytest.fixture
    def sample_json_data(self):
        return {
            "traces": [
                {
                    "trace_id": "abc123",
                    "spans": [
                        {
                            "span_id": "span1",
                            "name": "root-operation",
                            "start_time": "2024-01-01T00:00:00Z",
                            "end_time": "2024-01-01T00:00:01Z",
                            "status": "ok",
                            "service_name": "test-service",
                            "attributes": {"custom.key": "value"},
                        },
                        {
                            "span_id": "span2",
                            "parent_span_id": "span1",
                            "name": "child-operation",
                            "start_time": "2024-01-01T00:00:00.5Z",
                            "end_time": "2024-01-01T00:00:00.9Z",
                            "status": "error",
                        },
                    ],
                    "metadata": {"env": "test"},
                }
            ]
        }

    def test_validate_valid(self, adapter, sample_json_data):
        """Test validation of valid JSON data."""
        is_valid, errors = adapter.validate(sample_json_data)
        assert is_valid is True

    def test_validate_invalid(self, adapter):
        """Test validation of invalid data."""
        is_valid, errors = adapter.validate({"traces": [{"spans": [{}]}]})
        assert is_valid is False

    def test_parse(self, adapter, sample_json_data):
        """Test parsing JSON data."""
        traces = list(adapter.parse(sample_json_data))
        assert len(traces) == 1

        trace = traces[0]
        assert trace.trace_id == "abc123"
        assert len(trace.spans) == 2
        assert trace.metadata == {"env": "test"}

        root_span = trace.spans[0]
        assert root_span.name == "root-operation"
        assert root_span.status == SpanStatus.OK

        child_span = trace.spans[1]
        assert child_span.parent_span_id == "span1"
        assert child_span.status == SpanStatus.ERROR


class TestAdapterRegistry:
    """Tests for adapter registry."""

    @pytest.fixture
    def registry(self):
        reg = AdapterRegistry()
        reg.register(OTLPAdapter)
        reg.register(DatadogAdapter)
        reg.register(JSONAdapter)
        return reg

    def test_get_adapter(self, registry):
        """Test getting adapter by format."""
        adapter = registry.get_adapter("otlp")
        assert adapter is not None
        assert adapter.name == "otlp"

    def test_get_nonexistent(self, registry):
        """Test getting nonexistent adapter."""
        adapter = registry.get_adapter("nonexistent")
        assert adapter is None

    def test_detect_format_otlp(self, registry):
        """Test format detection for OTLP."""
        data = {"resourceSpans": []}
        assert registry.detect_format(data) == "otlp"

    def test_detect_format_datadog(self, registry):
        """Test format detection for Datadog."""
        data = [[{"trace_id": 123}]]
        assert registry.detect_format(data) == "datadog"

    def test_detect_format_json(self, registry):
        """Test format detection for JSON."""
        data = {"traces": [{"trace_id": "abc", "spans": []}]}
        assert registry.detect_format(data) == "json"

    def test_parse_auto(self, registry):
        """Test automatic parsing."""
        data = {
            "traces": [
                {
                    "trace_id": "test",
                    "spans": [
                        {
                            "span_id": "1",
                            "name": "test",
                        }
                    ],
                }
            ]
        }
        traces = registry.parse_auto(data)
        assert len(traces) == 1

    def test_registered_formats(self, registry):
        """Test format listing."""
        formats = registry.registered_formats
        assert "otlp" in formats
        assert "datadog" in formats
        assert "json" in formats


class TestConvenienceFunctions:
    """Tests for module-level convenience functions."""

    def test_get_adapter(self):
        """Test get_adapter function."""
        adapter = get_adapter("otlp")
        assert adapter is not None
        assert adapter.name == "otlp"

    def test_parse_traces(self):
        """Test parse_traces function."""
        data = {
            "traces": [
                {
                    "trace_id": "test",
                    "spans": [{"span_id": "1", "name": "test"}],
                }
            ]
        }
        traces = parse_traces(data, format_hint="json")
        assert len(traces) == 1
