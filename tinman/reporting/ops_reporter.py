"""Ops Reporter - operational reports for monitoring and alerting."""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any

from ..config.modes import OperatingMode
from ..memory.graph import MemoryGraph
from ..memory.models import NodeType
from ..utils import generate_id, get_logger, utc_now

logger = get_logger("ops_reporter")


class AlertSeverity(str, Enum):
    """Alert severity levels."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class Alert:
    """An operational alert."""

    id: str = field(default_factory=generate_id)
    severity: AlertSeverity = AlertSeverity.INFO
    title: str = ""
    description: str = ""
    source: str = ""
    created_at: datetime = field(default_factory=utc_now)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class HealthMetric:
    """A health metric for monitoring."""

    name: str
    value: float
    unit: str = ""
    status: str = "ok"  # ok, warning, critical
    threshold_warning: float | None = None
    threshold_critical: float | None = None


@dataclass
class OpsReport:
    """Operational health report."""

    id: str = field(default_factory=generate_id)
    generated_at: datetime = field(default_factory=utc_now)
    mode: OperatingMode = OperatingMode.LAB

    # Overall status
    overall_status: str = "healthy"  # healthy, degraded, unhealthy

    # Metrics
    metrics: list[HealthMetric] = field(default_factory=list)

    # Active alerts
    alerts: list[Alert] = field(default_factory=list)

    # Recent activity
    recent_failures: int = 0
    recent_interventions: int = 0
    recent_rollbacks: int = 0

    # System info
    uptime_hours: float = 0.0
    last_experiment: datetime | None = None
    last_failure: datetime | None = None


class OpsReporter:
    """
    Generates operational reports for monitoring.

    Ops reports are focused on:
    - System health
    - Active alerts
    - Recent activity
    - Key metrics
    """

    def __init__(
        self,
        graph: MemoryGraph | None = None,
        mode: OperatingMode = OperatingMode.LAB,
        start_time: datetime | None = None,
    ):
        self.graph = graph
        self.mode = mode
        self.start_time = start_time or utc_now()
        self._alert_handlers: list[callable] = []

    def register_alert_handler(self, handler: callable) -> None:
        """Register a handler to be called when alerts are generated."""
        self._alert_handlers.append(handler)

    def generate(self, lookback_hours: int = 24) -> OpsReport:
        """Generate an operational report."""
        report = OpsReport(
            mode=self.mode,
            uptime_hours=(utc_now() - self.start_time).total_seconds() / 3600,
        )

        cutoff = utc_now() - timedelta(hours=lookback_hours)

        if self.graph:
            self._gather_recent_activity(report, cutoff)
            self._gather_metrics(report)

        self._evaluate_health(report)
        self._generate_alerts(report)

        return report

    def _gather_recent_activity(self, report: OpsReport, cutoff: datetime) -> None:
        """Gather recent activity from memory graph."""
        # Recent failures
        failures = self.graph.get_failures(valid_only=False, limit=100)
        recent_failures = [f for f in failures if f.created_at >= cutoff]
        report.recent_failures = len(recent_failures)

        if recent_failures:
            report.last_failure = max(f.created_at for f in recent_failures)

        # Recent interventions
        interventions = self.graph.get_interventions(valid_only=False, limit=100)
        recent_interventions = [i for i in interventions if i.created_at >= cutoff]
        report.recent_interventions = len(recent_interventions)

        # Recent rollbacks
        rollbacks = self.graph.repo.get_nodes_by_type(
            NodeType.ROLLBACK, valid_only=False, limit=100
        )
        recent_rollbacks = [r for r in rollbacks if r.created_at >= cutoff]
        report.recent_rollbacks = len(recent_rollbacks)

        # Last experiment
        experiments = self.graph.get_experiments(valid_only=False, limit=1)
        if experiments:
            report.last_experiment = experiments[0].created_at

    def _gather_metrics(self, report: OpsReport) -> None:
        """Gather health metrics."""
        metrics = []

        # Failure rate (failures per hour in last 24h)
        if report.recent_failures > 0:
            failure_rate = report.recent_failures / 24.0
        else:
            failure_rate = 0.0

        metrics.append(
            HealthMetric(
                name="failure_rate",
                value=failure_rate,
                unit="per_hour",
                threshold_warning=1.0,
                threshold_critical=5.0,
            )
        )

        # Rollback rate
        if report.recent_rollbacks > 0:
            rollback_rate = report.recent_rollbacks / 24.0
        else:
            rollback_rate = 0.0

        metrics.append(
            HealthMetric(
                name="rollback_rate",
                value=rollback_rate,
                unit="per_hour",
                threshold_warning=0.5,
                threshold_critical=2.0,
            )
        )

        # Graph stats
        if self.graph:
            stats = self.graph.get_stats()
            total_nodes = sum(stats.values())
            metrics.append(
                HealthMetric(
                    name="total_graph_nodes",
                    value=float(total_nodes),
                    unit="nodes",
                )
            )

        # Uptime
        metrics.append(
            HealthMetric(
                name="uptime",
                value=report.uptime_hours,
                unit="hours",
            )
        )

        # Apply thresholds
        for metric in metrics:
            if metric.threshold_critical and metric.value >= metric.threshold_critical:
                metric.status = "critical"
            elif metric.threshold_warning and metric.value >= metric.threshold_warning:
                metric.status = "warning"
            else:
                metric.status = "ok"

        report.metrics = metrics

    def _evaluate_health(self, report: OpsReport) -> None:
        """Evaluate overall system health."""
        critical_metrics = [m for m in report.metrics if m.status == "critical"]
        warning_metrics = [m for m in report.metrics if m.status == "warning"]

        if critical_metrics:
            report.overall_status = "unhealthy"
        elif warning_metrics:
            report.overall_status = "degraded"
        else:
            report.overall_status = "healthy"

    def _generate_alerts(self, report: OpsReport) -> None:
        """Generate alerts based on metrics and activity."""
        alerts = []

        # Metric-based alerts
        for metric in report.metrics:
            if metric.status == "critical":
                alert = Alert(
                    severity=AlertSeverity.CRITICAL,
                    title=f"Critical: {metric.name}",
                    description=f"{metric.name} is {metric.value:.2f} {metric.unit} (threshold: {metric.threshold_critical})",
                    source="metric",
                    metadata={"metric": metric.name, "value": metric.value},
                )
                alerts.append(alert)
                self._dispatch_alert(alert)

            elif metric.status == "warning":
                alert = Alert(
                    severity=AlertSeverity.WARNING,
                    title=f"Warning: {metric.name}",
                    description=f"{metric.name} is {metric.value:.2f} {metric.unit} (threshold: {metric.threshold_warning})",
                    source="metric",
                    metadata={"metric": metric.name, "value": metric.value},
                )
                alerts.append(alert)
                self._dispatch_alert(alert)

        # Activity-based alerts
        if report.recent_rollbacks > 0:
            alert = Alert(
                severity=AlertSeverity.WARNING,
                title="Recent Rollbacks",
                description=f"{report.recent_rollbacks} rollback(s) in the last 24 hours",
                source="activity",
                metadata={"rollback_count": report.recent_rollbacks},
            )
            alerts.append(alert)
            self._dispatch_alert(alert)

        # High severity failure alerts
        if self.graph:
            severe_failures = self.graph.find_failures_by_severity("S3")
            unresolved = [f for f in severe_failures if not f.data.get("is_resolved")]
            if unresolved:
                alert = Alert(
                    severity=AlertSeverity.ERROR,
                    title="Unresolved High-Severity Failures",
                    description=f"{len(unresolved)} unresolved S3+ failure(s)",
                    source="failure",
                    metadata={"failure_ids": [f.id for f in unresolved[:5]]},
                )
                alerts.append(alert)
                self._dispatch_alert(alert)

        report.alerts = alerts

    def _dispatch_alert(self, alert: Alert) -> None:
        """Dispatch alert to registered handlers."""
        for handler in self._alert_handlers:
            try:
                handler(alert)
            except Exception as e:
                logger.error(f"Alert handler error: {e}")

    def to_json(self, report: OpsReport) -> dict:
        """Convert report to JSON-serializable dict."""
        return {
            "id": report.id,
            "generated_at": report.generated_at.isoformat(),
            "mode": report.mode.value,
            "overall_status": report.overall_status,
            "uptime_hours": report.uptime_hours,
            "metrics": [
                {
                    "name": m.name,
                    "value": m.value,
                    "unit": m.unit,
                    "status": m.status,
                }
                for m in report.metrics
            ],
            "alerts": [
                {
                    "id": a.id,
                    "severity": a.severity.value,
                    "title": a.title,
                    "description": a.description,
                }
                for a in report.alerts
            ],
            "recent_activity": {
                "failures": report.recent_failures,
                "interventions": report.recent_interventions,
                "rollbacks": report.recent_rollbacks,
            },
            "last_experiment": report.last_experiment.isoformat()
            if report.last_experiment
            else None,
            "last_failure": report.last_failure.isoformat() if report.last_failure else None,
        }

    def to_prometheus(self, report: OpsReport) -> str:
        """Export metrics in Prometheus format."""
        lines = [
            "# HELP tinman_uptime_hours Total uptime in hours",
            "# TYPE tinman_uptime_hours gauge",
            f"tinman_uptime_hours {report.uptime_hours:.2f}",
            "",
            "# HELP tinman_recent_failures Failures in last 24 hours",
            "# TYPE tinman_recent_failures gauge",
            f"tinman_recent_failures {report.recent_failures}",
            "",
            "# HELP tinman_recent_rollbacks Rollbacks in last 24 hours",
            "# TYPE tinman_recent_rollbacks gauge",
            f"tinman_recent_rollbacks {report.recent_rollbacks}",
            "",
            "# HELP tinman_active_alerts Number of active alerts",
            "# TYPE tinman_active_alerts gauge",
            f"tinman_active_alerts {len(report.alerts)}",
            "",
        ]

        # Export custom metrics
        for metric in report.metrics:
            safe_name = metric.name.replace(".", "_").replace("-", "_")
            lines.extend(
                [
                    f"# HELP tinman_{safe_name} {metric.name}",
                    f"# TYPE tinman_{safe_name} gauge",
                    f"tinman_{safe_name} {metric.value}",
                    "",
                ]
            )

        return "\n".join(lines)
