"""Adapter registry for trace ingestion.

This module provides a central registry for trace adapters,
enabling automatic format detection and adapter selection.
"""

from typing import Any, Optional, Type

from .base import TraceAdapter, Trace, IngestResult
from ..utils import get_logger

logger = get_logger("ingest.registry")


class AdapterRegistry:
    """Registry for trace ingestion adapters.

    The registry maintains a mapping of format identifiers to adapter
    classes, enabling automatic adapter selection based on data format.

    Usage:
        registry = AdapterRegistry()

        # Register adapters
        registry.register(OTLPAdapter)
        registry.register(DatadogAdapter)

        # Get adapter by format
        adapter = registry.get_adapter("otlp")

        # Auto-detect and parse
        traces = list(registry.parse_auto(data))
    """

    def __init__(self):
        self._adapters: dict[str, Type[TraceAdapter]] = {}
        self._instances: dict[str, TraceAdapter] = {}

    def register(
        self,
        adapter_class: Type[TraceAdapter],
        override: bool = False,
    ) -> None:
        """Register an adapter class.

        Args:
            adapter_class: TraceAdapter subclass to register
            override: If True, override existing registrations
        """
        # Create instance to get format info
        instance = adapter_class()

        for format_id in instance.supported_formats:
            if format_id in self._adapters and not override:
                logger.warning(
                    f"Format '{format_id}' already registered to "
                    f"{self._adapters[format_id].__name__}, skipping"
                )
                continue

            self._adapters[format_id] = adapter_class
            logger.debug(
                f"Registered adapter {adapter_class.__name__} for '{format_id}'"
            )

    def unregister(self, format_id: str) -> bool:
        """Unregister an adapter by format ID.

        Returns:
            True if adapter was unregistered, False if not found
        """
        if format_id in self._adapters:
            del self._adapters[format_id]
            if format_id in self._instances:
                del self._instances[format_id]
            return True
        return False

    def get_adapter(self, format_id: str) -> Optional[TraceAdapter]:
        """Get an adapter instance by format ID.

        Args:
            format_id: Format identifier (e.g., "otlp", "datadog")

        Returns:
            TraceAdapter instance or None if not found
        """
        format_id = format_id.lower()

        if format_id not in self._adapters:
            return None

        # Cache instances
        if format_id not in self._instances:
            self._instances[format_id] = self._adapters[format_id]()

        return self._instances[format_id]

    def detect_format(self, data: Any) -> Optional[str]:
        """Attempt to detect the format of trace data.

        Args:
            data: Raw trace data

        Returns:
            Format identifier if detected, None otherwise
        """
        if not isinstance(data, dict):
            # Could be Datadog array format
            if isinstance(data, list) and data:
                first = data[0]
                if isinstance(first, list):
                    # Datadog: list of trace arrays
                    return "datadog"
                if isinstance(first, dict):
                    # Could be simplified JSON
                    if "trace_id" in first:
                        return "json"
                    if "name" in first and "span_id" not in first:
                        return "json_simple"
            return None

        # OTLP format
        if "resourceSpans" in data:
            return "otlp"

        # X-Ray batch format
        if "Traces" in data:
            return "xray"

        # X-Ray single segment
        if "trace_id" in data or "TraceId" in data:
            if "subsegments" in data or "origin" in data:
                return "xray"

        # Datadog v2
        if "traces" in data:
            traces = data["traces"]
            if traces and isinstance(traces[0], dict):
                if "spans" in traces[0]:
                    return "datadog_v2"
            # Generic JSON format
            return "json"

        return None

    def parse_auto(
        self,
        data: Any,
        format_hint: Optional[str] = None,
    ) -> list[Trace]:
        """Automatically detect format and parse traces.

        Args:
            data: Raw trace data
            format_hint: Optional format hint to try first

        Returns:
            List of parsed Trace objects

        Raises:
            ValueError: If format cannot be detected or parsed
        """
        # Try hint first
        if format_hint:
            adapter = self.get_adapter(format_hint)
            if adapter:
                is_valid, errors = adapter.validate(data)
                if is_valid:
                    return list(adapter.parse(data))
                logger.debug(
                    f"Format hint '{format_hint}' validation failed: {errors}"
                )

        # Auto-detect
        detected = self.detect_format(data)
        if detected:
            adapter = self.get_adapter(detected)
            if adapter:
                is_valid, errors = adapter.validate(data)
                if is_valid:
                    return list(adapter.parse(data))
                logger.warning(
                    f"Detected format '{detected}' but validation failed: {errors}"
                )

        # Try all adapters
        for format_id, adapter_class in self._adapters.items():
            adapter = self.get_adapter(format_id)
            if adapter:
                is_valid, _ = adapter.validate(data)
                if is_valid:
                    return list(adapter.parse(data))

        raise ValueError(
            "Could not detect or parse trace format. "
            "Try specifying format_hint."
        )

    async def ingest_auto(
        self,
        data: Any,
        storage: Optional[Any] = None,
        format_hint: Optional[str] = None,
    ) -> IngestResult:
        """Automatically detect format and ingest traces.

        Args:
            data: Raw trace data
            storage: Optional storage backend
            format_hint: Optional format hint

        Returns:
            IngestResult with counts and any errors
        """
        # Try hint first
        if format_hint:
            adapter = self.get_adapter(format_hint)
            if adapter:
                is_valid, _ = adapter.validate(data)
                if is_valid:
                    return await adapter.ingest(data, storage)

        # Auto-detect
        detected = self.detect_format(data)
        if detected:
            adapter = self.get_adapter(detected)
            if adapter:
                is_valid, _ = adapter.validate(data)
                if is_valid:
                    return await adapter.ingest(data, storage)

        return IngestResult.failure_result(
            "Could not detect or parse trace format"
        )

    @property
    def registered_formats(self) -> list[str]:
        """Get list of registered format identifiers."""
        return sorted(self._adapters.keys())

    @property
    def registered_adapters(self) -> dict[str, str]:
        """Get mapping of formats to adapter class names."""
        return {
            fmt: cls.__name__
            for fmt, cls in self._adapters.items()
        }


# Default registry instance
_default_registry: Optional[AdapterRegistry] = None


def get_default_registry() -> AdapterRegistry:
    """Get the default adapter registry with standard adapters registered."""
    global _default_registry

    if _default_registry is None:
        from .otlp import OTLPAdapter
        from .datadog import DatadogAdapter, DatadogV2Adapter
        from .xray import XRayAdapter
        from .json_adapter import JSONAdapter, SimplifiedJSONAdapter

        _default_registry = AdapterRegistry()
        _default_registry.register(OTLPAdapter)
        _default_registry.register(DatadogAdapter)
        _default_registry.register(DatadogV2Adapter)
        _default_registry.register(XRayAdapter)
        _default_registry.register(JSONAdapter)
        _default_registry.register(SimplifiedJSONAdapter)

    return _default_registry


def get_adapter(format_id: str) -> Optional[TraceAdapter]:
    """Get an adapter from the default registry."""
    return get_default_registry().get_adapter(format_id)


def register_adapter(
    adapter_class: Type[TraceAdapter],
    override: bool = False,
) -> None:
    """Register an adapter to the default registry."""
    get_default_registry().register(adapter_class, override)


def parse_traces(data: Any, format_hint: Optional[str] = None) -> list[Trace]:
    """Parse traces using the default registry."""
    return get_default_registry().parse_auto(data, format_hint)


async def ingest_traces(
    data: Any,
    storage: Optional[Any] = None,
    format_hint: Optional[str] = None,
) -> IngestResult:
    """Ingest traces using the default registry."""
    return await get_default_registry().ingest_auto(data, storage, format_hint)
