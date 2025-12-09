#!/usr/bin/env python3
"""
Event Monitoring Example

Demonstrates using Tinman's event system for real-time monitoring,
alerting, and integration with external systems.

Usage:
    export OPENAI_API_KEY="sk-..."
    python examples/event_monitoring.py
"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from tinman import create_tinman, OperatingMode
from tinman.integrations import OpenAIClient
from tinman.core.event_bus import EventBus


@dataclass
class Alert:
    """Represents an alert triggered by Tinman events."""
    timestamp: datetime
    severity: str
    event_type: str
    message: str
    data: dict = field(default_factory=dict)


class AlertManager:
    """
    Manages alerts triggered by Tinman events.

    In production, this would integrate with PagerDuty,
    Slack, email, or other alerting systems.
    """

    def __init__(self):
        self.alerts: list[Alert] = []
        self.alert_rules: dict[str, dict] = {}

    def add_rule(self, event_type: str, severity: str, condition: callable = None):
        """Add an alerting rule."""
        self.alert_rules[event_type] = {
            "severity": severity,
            "condition": condition or (lambda data: True),
        }

    def check_and_alert(self, event_type: str, data: dict):
        """Check if event triggers an alert."""
        rule = self.alert_rules.get(event_type)
        if not rule:
            return None

        if rule["condition"](data):
            alert = Alert(
                timestamp=datetime.utcnow(),
                severity=rule["severity"],
                event_type=event_type,
                message=self._format_message(event_type, data),
                data=data,
            )
            self.alerts.append(alert)
            self._send_alert(alert)
            return alert

        return None

    def _format_message(self, event_type: str, data: dict) -> str:
        """Format alert message."""
        if event_type == "failure.discovered":
            return (f"AI Failure Discovered: {data.get('failure_class', 'Unknown')} "
                    f"(Severity: {data.get('severity', 'Unknown')})")
        elif event_type == "approval.requested":
            return (f"Approval Required: {data.get('action', 'Unknown')} "
                    f"(Risk: {data.get('risk_tier', 'Unknown')})")
        elif event_type == "intervention.deployed":
            return f"Intervention Deployed: {data.get('name', 'Unknown')}"
        else:
            return f"Event: {event_type}"

    def _send_alert(self, alert: Alert):
        """Send alert to external system."""
        # In production, integrate with your alerting system
        severity_emoji = {
            "critical": "!!!",
            "high": "!!",
            "medium": "!",
            "low": "*",
        }
        print(f"\n{severity_emoji.get(alert.severity, '?')} ALERT [{alert.severity.upper()}]: "
              f"{alert.message}")


class MetricsCollector:
    """
    Collects metrics from Tinman events.

    In production, this would integrate with Prometheus,
    Datadog, CloudWatch, or other metrics systems.
    """

    def __init__(self):
        self.counters: dict[str, int] = {}
        self.gauges: dict[str, float] = {}
        self.histograms: dict[str, list[float]] = {}

    def increment(self, name: str, value: int = 1, tags: dict = None):
        """Increment a counter."""
        key = self._make_key(name, tags)
        self.counters[key] = self.counters.get(key, 0) + value

    def gauge(self, name: str, value: float, tags: dict = None):
        """Set a gauge value."""
        key = self._make_key(name, tags)
        self.gauges[key] = value

    def histogram(self, name: str, value: float, tags: dict = None):
        """Record a histogram value."""
        key = self._make_key(name, tags)
        if key not in self.histograms:
            self.histograms[key] = []
        self.histograms[key].append(value)

    def _make_key(self, name: str, tags: dict = None) -> str:
        """Create a metric key with tags."""
        if not tags:
            return name
        tag_str = ",".join(f"{k}={v}" for k, v in sorted(tags.items()))
        return f"{name}{{{tag_str}}}"

    def get_summary(self) -> dict:
        """Get metrics summary."""
        return {
            "counters": dict(self.counters),
            "gauges": dict(self.gauges),
            "histograms": {
                k: {
                    "count": len(v),
                    "min": min(v) if v else 0,
                    "max": max(v) if v else 0,
                    "avg": sum(v) / len(v) if v else 0,
                }
                for k, v in self.histograms.items()
            },
        }


async def main():
    print("=" * 60)
    print("Event Monitoring Example")
    print("=" * 60)

    # Create event bus and monitoring components
    event_bus = EventBus()
    alert_manager = AlertManager()
    metrics = MetricsCollector()

    # Configure alerting rules
    alert_manager.add_rule(
        "failure.discovered",
        severity="high",
        condition=lambda d: d.get("severity") in ["S3", "S4"],
    )
    alert_manager.add_rule(
        "failure.discovered",
        severity="medium",
        condition=lambda d: d.get("severity") == "S2",
    )
    alert_manager.add_rule(
        "approval.requested",
        severity="medium",
        condition=lambda d: d.get("risk_tier") in ["REVIEW", "BLOCK"],
    )
    alert_manager.add_rule(
        "intervention.deployed",
        severity="low",
    )

    # Register event handlers
    @event_bus.on("hypothesis.generated")
    async def on_hypothesis(data):
        metrics.increment("tinman.hypotheses.generated")
        print(f"  [EVENT] Hypothesis generated: {data.get('target_surface', 'Unknown')}")

    @event_bus.on("experiment.started")
    async def on_experiment_start(data):
        metrics.increment("tinman.experiments.started")
        print(f"  [EVENT] Experiment started: {data.get('id', 'Unknown')[:8]}...")

    @event_bus.on("experiment.completed")
    async def on_experiment_complete(data):
        metrics.increment("tinman.experiments.completed")
        metrics.histogram(
            "tinman.experiments.failures",
            data.get("failures_triggered", 0),
        )
        print(f"  [EVENT] Experiment completed: {data.get('failures_triggered', 0)} failures")

    @event_bus.on("failure.discovered")
    async def on_failure(data):
        severity = data.get("severity", "Unknown")
        failure_class = data.get("failure_class", "Unknown")

        metrics.increment("tinman.failures.discovered", tags={"severity": severity})
        metrics.increment("tinman.failures.by_class", tags={"class": failure_class})

        print(f"  [EVENT] Failure discovered: [{severity}] {failure_class}")

        # Check alerting rules
        alert_manager.check_and_alert("failure.discovered", data)

    @event_bus.on("intervention.proposed")
    async def on_intervention_proposed(data):
        metrics.increment("tinman.interventions.proposed")
        print(f"  [EVENT] Intervention proposed: {data.get('name', 'Unknown')}")

    @event_bus.on("intervention.deployed")
    async def on_intervention_deployed(data):
        metrics.increment("tinman.interventions.deployed")
        print(f"  [EVENT] Intervention deployed: {data.get('id', 'Unknown')[:8]}...")
        alert_manager.check_and_alert("intervention.deployed", data)

    @event_bus.on("approval.requested")
    async def on_approval_requested(data):
        metrics.increment("tinman.approvals.requested")
        print(f"  [EVENT] Approval requested: {data.get('action', 'Unknown')}")
        alert_manager.check_and_alert("approval.requested", data)

    @event_bus.on("approval.decided")
    async def on_approval_decided(data):
        approved = data.get("approved", False)
        metrics.increment(
            "tinman.approvals.decided",
            tags={"result": "approved" if approved else "rejected"},
        )
        result = "APPROVED" if approved else "REJECTED"
        print(f"  [EVENT] Approval decided: {result}")

    # Simulate events for demonstration
    print("\n" + "=" * 60)
    print("Simulating Tinman Events")
    print("=" * 60 + "\n")

    # Simulate a research cycle's events
    simulated_events = [
        ("hypothesis.generated", {
            "id": "hyp_001",
            "target_surface": "tool_use",
            "failure_class": "TOOL_USE",
        }),
        ("hypothesis.generated", {
            "id": "hyp_002",
            "target_surface": "reasoning",
            "failure_class": "REASONING",
        }),
        ("experiment.started", {
            "id": "exp_001",
            "hypothesis_id": "hyp_001",
            "total_runs": 5,
        }),
        ("experiment.completed", {
            "id": "exp_001",
            "failures_triggered": 2,
        }),
        ("failure.discovered", {
            "id": "fail_001",
            "failure_class": "TOOL_USE",
            "severity": "S2",
            "description": "Tool parameter injection vulnerability",
        }),
        ("failure.discovered", {
            "id": "fail_002",
            "failure_class": "REASONING",
            "severity": "S3",
            "description": "Critical reasoning failure under stress",
        }),
        ("approval.requested", {
            "id": "apr_001",
            "action": "intervention.deploy",
            "risk_tier": "REVIEW",
        }),
        ("approval.decided", {
            "id": "apr_001",
            "approved": True,
            "reason": "Approved by operator",
        }),
        ("intervention.proposed", {
            "id": "int_001",
            "name": "Prompt Guardrail",
            "type": "guardrail",
        }),
        ("intervention.deployed", {
            "id": "int_001",
            "name": "Prompt Guardrail",
            "status": "active",
        }),
    ]

    for event_type, data in simulated_events:
        await event_bus.emit(event_type, data)
        await asyncio.sleep(0.1)  # Small delay for readability

    # Display summary
    print("\n" + "=" * 60)
    print("Monitoring Summary")
    print("=" * 60)

    print("\nMetrics:")
    summary = metrics.get_summary()

    print("\n  Counters:")
    for key, value in summary["counters"].items():
        print(f"    {key}: {value}")

    print("\n  Histograms:")
    for key, stats in summary["histograms"].items():
        print(f"    {key}: count={stats['count']}, avg={stats['avg']:.2f}")

    print(f"\nAlerts Triggered: {len(alert_manager.alerts)}")
    for alert in alert_manager.alerts:
        print(f"  - [{alert.severity.upper()}] {alert.message}")

    print("\n" + "=" * 60)
    print("Integration Example: External Systems")
    print("=" * 60)

    print("""
In production, integrate with:

1. Alerting (PagerDuty, Slack, etc.):
   - Replace _send_alert() with actual API calls
   - Configure escalation policies

2. Metrics (Prometheus, Datadog, etc.):
   - Replace MetricsCollector with actual client
   - Set up dashboards and alerts

3. Logging (ELK, CloudWatch, etc.):
   - Add structured logging to event handlers
   - Configure log aggregation

Example Prometheus integration:

    from prometheus_client import Counter, Histogram

    FAILURES_COUNTER = Counter(
        'tinman_failures_total',
        'Total failures discovered',
        ['severity', 'failure_class']
    )

    @event_bus.on("failure.discovered")
    async def on_failure(data):
        FAILURES_COUNTER.labels(
            severity=data.get('severity'),
            failure_class=data.get('failure_class')
        ).inc()
""")


if __name__ == "__main__":
    asyncio.run(main())
