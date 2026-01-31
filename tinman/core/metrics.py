"""Prometheus metrics for Tinman FDRA.

This module provides comprehensive observability through Prometheus metrics,
covering research operations, approvals, costs, and system health.

Usage:
    from tinman.core.metrics import metrics

    # Record a research cycle
    metrics.research_cycles_total.labels(mode="lab", focus="tool_use").inc()

    # Record a failure
    metrics.failures_discovered_total.labels(
        severity="S3",
        failure_class="TOOL_USE"
    ).inc()

    # Record approval decision
    metrics.approval_decisions_total.labels(
        decision="approved",
        risk_tier="review",
        mode="production"
    ).inc()
"""

import threading
from collections.abc import Generator
from contextlib import contextmanager
from typing import Optional

from ..utils import get_logger

logger = get_logger("metrics")

# Try to import prometheus_client, provide fallback if not available
try:
    from prometheus_client import (
        CONTENT_TYPE_LATEST,
        CollectorRegistry,
        Counter,
        Gauge,
        Histogram,
        Info,
        Summary,
        generate_latest,
        start_http_server,
    )

    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False
    logger.warning("prometheus_client not installed - metrics will be no-ops")


class NoOpMetric:
    """No-op metric when prometheus_client is not available."""

    def __init__(self, *args, **kwargs):
        pass

    def labels(self, *args, **kwargs):
        return self

    def inc(self, *args, **kwargs):
        pass

    def dec(self, *args, **kwargs):
        pass

    def set(self, *args, **kwargs):
        pass

    def observe(self, *args, **kwargs):
        pass

    def time(self):
        @contextmanager
        def noop():
            yield

        return noop()

    def info(self, *args, **kwargs):
        pass


class TinmanMetrics:
    """Container for all Tinman Prometheus metrics."""

    def __init__(self, registry: Optional["CollectorRegistry"] = None):
        """Initialize metrics.

        Args:
            registry: Optional custom registry. If None, uses default.
        """
        self.registry = registry

        if PROMETHEUS_AVAILABLE:
            self._init_prometheus_metrics()
        else:
            self._init_noop_metrics()

        logger.info(f"Metrics initialized (prometheus_available={PROMETHEUS_AVAILABLE})")

    def _init_prometheus_metrics(self):
        """Initialize real Prometheus metrics."""
        kwargs = {"registry": self.registry} if self.registry else {}

        # Research cycle metrics
        self.research_cycles_total = Counter(
            "tinman_research_cycles_total",
            "Total research cycles run",
            ["mode", "focus", "status"],
            **kwargs,
        )

        self.research_cycle_duration_seconds = Histogram(
            "tinman_research_cycle_duration_seconds",
            "Duration of research cycles",
            ["mode"],
            buckets=(1, 5, 10, 30, 60, 120, 300, 600),
            **kwargs,
        )

        # Hypothesis metrics
        self.hypotheses_generated_total = Counter(
            "tinman_hypotheses_generated_total",
            "Total hypotheses generated",
            ["failure_class", "target_surface"],
            **kwargs,
        )

        self.hypothesis_confidence = Histogram(
            "tinman_hypothesis_confidence",
            "Distribution of hypothesis confidence scores",
            ["failure_class"],
            buckets=(0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0),
            **kwargs,
        )

        # Experiment metrics
        self.experiments_run_total = Counter(
            "tinman_experiments_run_total",
            "Total experiments run",
            ["stress_type", "mode", "status"],
            **kwargs,
        )

        self.experiment_runs_total = Counter(
            "tinman_experiment_runs_total",
            "Total experiment runs (individual executions)",
            ["stress_type"],
            **kwargs,
        )

        self.experiment_duration_seconds = Histogram(
            "tinman_experiment_duration_seconds",
            "Duration of experiments",
            ["stress_type"],
            buckets=(0.1, 0.5, 1, 2, 5, 10, 30, 60),
            **kwargs,
        )

        # Failure metrics
        self.failures_discovered_total = Counter(
            "tinman_failures_discovered_total",
            "Total failures discovered",
            ["severity", "failure_class"],
            **kwargs,
        )

        self.failure_reproducibility = Histogram(
            "tinman_failure_reproducibility",
            "Reproducibility of discovered failures",
            ["failure_class"],
            buckets=(0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0),
            **kwargs,
        )

        self.active_failures = Gauge(
            "tinman_active_failures",
            "Number of active (unresolved) failures",
            ["severity"],
            **kwargs,
        )

        # Intervention metrics
        self.interventions_proposed_total = Counter(
            "tinman_interventions_proposed_total",
            "Total interventions proposed",
            ["intervention_type", "risk_tier"],
            **kwargs,
        )

        self.interventions_deployed_total = Counter(
            "tinman_interventions_deployed_total",
            "Total interventions deployed",
            ["intervention_type", "mode"],
            **kwargs,
        )

        # Approval metrics
        self.approval_decisions_total = Counter(
            "tinman_approval_decisions_total",
            "Total approval decisions",
            ["decision", "risk_tier", "mode"],
            **kwargs,
        )

        self.pending_approvals = Gauge(
            "tinman_pending_approvals",
            "Number of pending approval requests",
            ["risk_tier"],
            **kwargs,
        )

        self.approval_latency_seconds = Histogram(
            "tinman_approval_latency_seconds",
            "Time from approval request to decision",
            ["decision", "risk_tier"],
            buckets=(1, 5, 10, 30, 60, 120, 300, 600),
            **kwargs,
        )

        # Tool execution metrics
        self.tool_executions_total = Counter(
            "tinman_tool_executions_total",
            "Total tool executions",
            ["tool_name", "status", "mode"],
            **kwargs,
        )

        self.tool_execution_duration_seconds = Histogram(
            "tinman_tool_execution_duration_seconds",
            "Duration of tool executions",
            ["tool_name"],
            buckets=(0.01, 0.05, 0.1, 0.5, 1, 2, 5, 10),
            **kwargs,
        )

        self.tool_blocks_total = Counter(
            "tinman_tool_blocks_total",
            "Total tool executions blocked",
            ["tool_name", "reason"],
            **kwargs,
        )

        # Cost metrics
        self.cost_usd_total = Counter(
            "tinman_cost_usd_total",
            "Total cost in USD",
            ["source", "model", "operation"],
            **kwargs,
        )

        self.cost_budget_utilization = Gauge(
            "tinman_cost_budget_utilization",
            "Budget utilization (0-1)",
            ["period"],
            **kwargs,
        )

        self.cost_budget_remaining_usd = Gauge(
            "tinman_cost_budget_remaining_usd",
            "Remaining budget in USD",
            ["period"],
            **kwargs,
        )

        # LLM metrics
        self.llm_requests_total = Counter(
            "tinman_llm_requests_total",
            "Total LLM requests",
            ["model", "mode", "status"],
            **kwargs,
        )

        self.llm_tokens_total = Counter(
            "tinman_llm_tokens_total",
            "Total tokens processed",
            ["model", "direction"],  # direction: input/output
            **kwargs,
        )

        self.llm_latency_seconds = Histogram(
            "tinman_llm_latency_seconds",
            "LLM request latency",
            ["model"],
            buckets=(0.1, 0.5, 1, 2, 5, 10, 30),
            **kwargs,
        )

        # Mode metrics
        self.mode_transitions_total = Counter(
            "tinman_mode_transitions_total",
            "Total mode transitions",
            ["from_mode", "to_mode", "status"],
            **kwargs,
        )

        self.current_mode = Gauge(
            "tinman_current_mode",
            "Current operating mode (1=active)",
            ["mode"],
            **kwargs,
        )

        # System metrics
        self.info = Info(
            "tinman",
            "Tinman system information",
            **kwargs,
        )

        self.uptime_seconds = Gauge(
            "tinman_uptime_seconds",
            "Uptime in seconds",
            **kwargs,
        )

        self.active_sessions = Gauge(
            "tinman_active_sessions",
            "Number of active sessions",
            **kwargs,
        )

    def _init_noop_metrics(self):
        """Initialize no-op metrics for when prometheus is not available."""
        self.research_cycles_total = NoOpMetric()
        self.research_cycle_duration_seconds = NoOpMetric()
        self.hypotheses_generated_total = NoOpMetric()
        self.hypothesis_confidence = NoOpMetric()
        self.experiments_run_total = NoOpMetric()
        self.experiment_runs_total = NoOpMetric()
        self.experiment_duration_seconds = NoOpMetric()
        self.failures_discovered_total = NoOpMetric()
        self.failure_reproducibility = NoOpMetric()
        self.active_failures = NoOpMetric()
        self.interventions_proposed_total = NoOpMetric()
        self.interventions_deployed_total = NoOpMetric()
        self.approval_decisions_total = NoOpMetric()
        self.pending_approvals = NoOpMetric()
        self.approval_latency_seconds = NoOpMetric()
        self.tool_executions_total = NoOpMetric()
        self.tool_execution_duration_seconds = NoOpMetric()
        self.tool_blocks_total = NoOpMetric()
        self.cost_usd_total = NoOpMetric()
        self.cost_budget_utilization = NoOpMetric()
        self.cost_budget_remaining_usd = NoOpMetric()
        self.llm_requests_total = NoOpMetric()
        self.llm_tokens_total = NoOpMetric()
        self.llm_latency_seconds = NoOpMetric()
        self.mode_transitions_total = NoOpMetric()
        self.current_mode = NoOpMetric()
        self.info = NoOpMetric()
        self.uptime_seconds = NoOpMetric()
        self.active_sessions = NoOpMetric()

    def set_info(self, version: str, mode: str, **kwargs):
        """Set system info metric."""
        if PROMETHEUS_AVAILABLE:
            self.info.info(
                {
                    "version": version,
                    "mode": mode,
                    **kwargs,
                }
            )

    def set_mode(self, mode: str):
        """Update current mode metric."""
        if PROMETHEUS_AVAILABLE:
            for m in ["lab", "shadow", "production"]:
                self.current_mode.labels(mode=m).set(1 if m == mode else 0)

    @contextmanager
    def time_research_cycle(self, mode: str) -> Generator[None, None, None]:
        """Context manager to time research cycles."""
        if PROMETHEUS_AVAILABLE:
            with self.research_cycle_duration_seconds.labels(mode=mode).time():
                yield
        else:
            yield

    @contextmanager
    def time_experiment(self, stress_type: str) -> Generator[None, None, None]:
        """Context manager to time experiments."""
        if PROMETHEUS_AVAILABLE:
            with self.experiment_duration_seconds.labels(stress_type=stress_type).time():
                yield
        else:
            yield

    @contextmanager
    def time_tool_execution(self, tool_name: str) -> Generator[None, None, None]:
        """Context manager to time tool executions."""
        if PROMETHEUS_AVAILABLE:
            with self.tool_execution_duration_seconds.labels(tool_name=tool_name).time():
                yield
        else:
            yield

    @contextmanager
    def time_llm_request(self, model: str) -> Generator[None, None, None]:
        """Context manager to time LLM requests."""
        if PROMETHEUS_AVAILABLE:
            with self.llm_latency_seconds.labels(model=model).time():
                yield
        else:
            yield

    def export(self) -> bytes:
        """Export metrics in Prometheus format."""
        if PROMETHEUS_AVAILABLE:
            if self.registry:
                return generate_latest(self.registry)
            return generate_latest()
        return b"# prometheus_client not available\n"

    def get_content_type(self) -> str:
        """Get content type for metrics export."""
        if PROMETHEUS_AVAILABLE:
            return CONTENT_TYPE_LATEST
        return "text/plain"


# Default metrics instance
_metrics: TinmanMetrics | None = None
_metrics_lock = threading.Lock()


def get_metrics() -> TinmanMetrics:
    """Get the global metrics instance."""
    global _metrics
    with _metrics_lock:
        if _metrics is None:
            _metrics = TinmanMetrics()
        return _metrics


def set_metrics(metrics: TinmanMetrics) -> None:
    """Set the global metrics instance."""
    global _metrics
    with _metrics_lock:
        _metrics = metrics


# Convenience access to default metrics
metrics = get_metrics()


def start_metrics_server(port: int = 9090, addr: str = "0.0.0.0") -> None:
    """Start a standalone Prometheus metrics HTTP server.

    Args:
        port: Port to listen on
        addr: Address to bind to
    """
    if PROMETHEUS_AVAILABLE:
        start_http_server(port, addr)
        logger.info(f"Metrics server started on {addr}:{port}")
    else:
        logger.warning("Cannot start metrics server - prometheus_client not installed")
