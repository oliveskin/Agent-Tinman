"""Gateway event monitoring plugin for AI gateways.

This module provides a generic framework for monitoring AI gateways
in real-time. Gateway-specific adapters convert events to a canonical
format, which is then buffered, analyzed, and alerted on.

Architecture:
    GatewayAdapter (abstract)
        └── OpenClawAdapter, LangServeAdapter, etc.
                    │
                    ▼
            GatewayMonitor
                    │
          ┌─────────┼─────────┐
          ▼         ▼         ▼
     TraceBuffer  Analyzer  AlertDispatcher
                              │
                    ┌─────────┼─────────┐
                    ▼         ▼         ▼
               Console     File     Webhook

Usage:
    from tinman.integrations.gateway_plugin import (
        GatewayMonitor,
        GatewayAdapter,
        MonitorConfig,
        ConsoleAlerter,
        FileAlerter,
    )

    # With a specific adapter (e.g., from tinman-openclaw-eval)
    from tinman_openclaw_eval.adapters.openclaw import OpenClawAdapter

    adapter = OpenClawAdapter("ws://127.0.0.1:18789")
    monitor = GatewayMonitor(adapter, MonitorConfig(
        analysis_interval_seconds=300,
        min_severity=EventSeverity.WARNING,
    ))
    monitor.add_alerter(ConsoleAlerter())
    monitor.add_alerter(FileAlerter("~/findings.md"))

    await monitor.start()
"""

from .alerter import (
    AlertDispatcher,
    Alerter,
    CallbackAlerter,
    ConsoleAlerter,
    FileAlerter,
    Finding,
    WebhookAlerter,
)
from .base import (
    ConnectionState,
    EventSeverity,
    EventType,
    GatewayAdapter,
    GatewayEvent,
)
from .monitor import (
    GatewayMonitor,
    MonitorConfig,
    SessionBuffer,
    TraceBuffer,
)

__all__ = [
    # Base types
    "GatewayAdapter",
    "GatewayEvent",
    "EventType",
    "EventSeverity",
    "ConnectionState",
    # Monitor
    "GatewayMonitor",
    "MonitorConfig",
    "SessionBuffer",
    "TraceBuffer",
    # Alerting
    "AlertDispatcher",
    "Alerter",
    "Finding",
    "ConsoleAlerter",
    "FileAlerter",
    "WebhookAlerter",
    "CallbackAlerter",
]
