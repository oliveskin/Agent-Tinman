"""Trace ingestion adapters for external observability data.

This module provides adapters for ingesting traces from various sources
into Tinman for failure analysis and hypothesis generation.

Supported formats:
- OpenTelemetry (OTLP)
- Datadog APM
- AWS X-Ray
- Generic JSON traces
"""

from .base import (
    IngestResult,
    Span,
    SpanEvent,
    SpanLink,
    SpanStatus,
    Trace,
    TraceAdapter,
)
from .datadog import DatadogAdapter
from .json_adapter import JSONAdapter
from .otlp import OTLPAdapter
from .registry import AdapterRegistry, get_adapter, parse_traces, register_adapter
from .xray import XRayAdapter

__all__ = [
    # Base types
    "TraceAdapter",
    "Trace",
    "Span",
    "SpanEvent",
    "SpanLink",
    "SpanStatus",
    "IngestResult",
    # Adapters
    "OTLPAdapter",
    "DatadogAdapter",
    "XRayAdapter",
    "JSONAdapter",
    # Registry
    "AdapterRegistry",
    "get_adapter",
    "parse_traces",
    "register_adapter",
]
