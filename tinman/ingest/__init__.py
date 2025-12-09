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
    TraceAdapter,
    Trace,
    Span,
    SpanEvent,
    SpanLink,
    SpanStatus,
    IngestResult,
)
from .otlp import OTLPAdapter
from .datadog import DatadogAdapter
from .xray import XRayAdapter
from .json_adapter import JSONAdapter
from .registry import AdapterRegistry, get_adapter, register_adapter

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
    "register_adapter",
]
