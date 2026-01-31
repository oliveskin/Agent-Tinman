"""Technical Analysis Report generator.

Provides detailed technical reports suitable for engineering teams,
including root cause analysis, reproduction steps, and technical details.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from ..memory.graph import MemoryGraph
from ..utils import get_logger, utc_now
from .base import (
    Report,
    ReportGenerator,
    ReportMetadata,
    ReportSection,
    ReportType,
)

logger = get_logger("reporting.technical")


@dataclass
class FailureDetail:
    """Detailed failure information."""

    id: str
    primary_class: str
    secondary_class: str | None
    severity: str
    description: str
    reproducibility: float
    trigger_signature: list[str]
    context: dict[str, Any]
    hypothesis_id: str | None
    experiment_ids: list[str]
    intervention_ids: list[str]
    is_resolved: bool
    resolution_notes: str | None


@dataclass
class TechnicalData:
    """Data specific to technical reports."""

    failures: list[FailureDetail] = field(default_factory=list)
    failure_by_class: dict[str, int] = field(default_factory=dict)
    failure_by_severity: dict[str, int] = field(default_factory=dict)
    experiments_total: int = 0
    experiments_validated: int = 0
    reproduction_rate_avg: float = 0.0
    common_triggers: list[tuple[str, int]] = field(default_factory=list)
    affected_surfaces: list[tuple[str, int]] = field(default_factory=list)


class TechnicalAnalysisReport(ReportGenerator):
    """Generator for technical analysis reports.

    These reports are designed for engineering teams and include:
    - Detailed failure breakdowns
    - Root cause analysis
    - Reproduction steps and triggers
    - Affected attack surfaces
    - Technical recommendations

    Usage:
        generator = TechnicalAnalysisReport(graph=memory_graph)
        report = await generator.generate(
            period_start=last_week,
            period_end=now,
            include_resolved=True,
        )
    """

    def __init__(self, graph: MemoryGraph | None = None):
        self.graph = graph

    @property
    def report_type(self) -> ReportType:
        return ReportType.TECHNICAL_ANALYSIS

    @property
    def name(self) -> str:
        return "Technical Analysis"

    async def generate(
        self,
        period_start: datetime | None = None,
        period_end: datetime | None = None,
        include_resolved: bool = True,
        severity_filter: list[str] | None = None,
        class_filter: list[str] | None = None,
        **kwargs,
    ) -> Report[TechnicalData]:
        """Generate technical analysis report."""
        period_end = period_end or utc_now()
        period_start = period_start or (period_end - timedelta(days=7))

        report = Report[TechnicalData](
            metadata=ReportMetadata(
                type=self.report_type,
                title="Technical Analysis Report",
                description="Detailed technical analysis of discovered failures",
                period_start=period_start,
                period_end=period_end,
                confidentiality="confidential",
            ),
            raw_data=TechnicalData(),
        )

        data = report.raw_data

        await self._gather_failures(
            data, period_start, period_end, include_resolved, severity_filter, class_filter
        )
        await self._gather_experiments(data, period_start, period_end)
        await self._analyze_patterns(data)

        report.summary = self._build_summary(data)
        report.sections = [
            self._build_overview_section(data),
            self._build_failures_section(data),
            self._build_patterns_section(data),
            self._build_surfaces_section(data),
            self._build_technical_recommendations(data),
        ]

        return report

    async def _gather_failures(
        self,
        data: TechnicalData,
        start: datetime,
        end: datetime,
        include_resolved: bool,
        severity_filter: list[str] | None,
        class_filter: list[str] | None,
    ) -> None:
        """Gather detailed failure information."""
        if not self.graph:
            return

        failures = self.graph.get_failures(valid_only=False)

        for failure in failures:
            # Time filter
            if not (start <= failure.created_at <= end):
                continue

            fdata = failure.data
            is_resolved = fdata.get("is_resolved", False)

            # Resolution filter
            if not include_resolved and is_resolved:
                continue

            # Severity filter
            severity = fdata.get("severity", "S2")
            if severity_filter and severity not in severity_filter:
                continue

            # Class filter
            primary_class = fdata.get("primary_class", "unknown")
            if class_filter and primary_class not in class_filter:
                continue

            # Get related entities
            experiment_ids = []
            for edge in self.graph.repo.get_edges_from(failure.id):
                if edge.relation == "discovered_by":
                    experiment_ids.append(edge.target_id)

            intervention_ids = []
            for edge in self.graph.repo.get_edges_to(failure.id):
                if edge.relation == "addresses":
                    intervention_ids.append(edge.source_id)

            detail = FailureDetail(
                id=failure.id,
                primary_class=primary_class,
                secondary_class=fdata.get("secondary_class"),
                severity=severity,
                description=fdata.get("description", ""),
                reproducibility=fdata.get("reproducibility", 0.0),
                trigger_signature=fdata.get("trigger_signature", []),
                context=fdata.get("context", {}),
                hypothesis_id=fdata.get("hypothesis_id"),
                experiment_ids=experiment_ids,
                intervention_ids=intervention_ids,
                is_resolved=is_resolved,
                resolution_notes=fdata.get("resolution_notes"),
            )
            data.failures.append(detail)

            # Count by class
            data.failure_by_class[primary_class] = data.failure_by_class.get(primary_class, 0) + 1

            # Count by severity
            data.failure_by_severity[severity] = data.failure_by_severity.get(severity, 0) + 1

    async def _gather_experiments(
        self,
        data: TechnicalData,
        start: datetime,
        end: datetime,
    ) -> None:
        """Gather experiment statistics."""
        if not self.graph:
            return

        experiments = self.graph.get_experiments(valid_only=False)

        period_experiments = [e for e in experiments if start <= e.created_at <= end]

        data.experiments_total = len(period_experiments)
        data.experiments_validated = sum(
            1 for e in period_experiments if e.data.get("hypothesis_validated", False)
        )

        # Calculate average reproduction rate
        repro_rates = [
            e.data.get("reproduction_rate", 0)
            for e in period_experiments
            if "reproduction_rate" in e.data
        ]
        if repro_rates:
            data.reproduction_rate_avg = sum(repro_rates) / len(repro_rates)

    async def _analyze_patterns(self, data: TechnicalData) -> None:
        """Analyze patterns in failures."""
        # Common triggers
        trigger_counts: dict[str, int] = {}
        surface_counts: dict[str, int] = {}

        for failure in data.failures:
            # Count triggers
            for trigger in failure.trigger_signature:
                trigger_counts[trigger] = trigger_counts.get(trigger, 0) + 1

            # Count surfaces from context
            surface = failure.context.get("target_surface", "unknown")
            surface_counts[surface] = surface_counts.get(surface, 0) + 1

        data.common_triggers = sorted(
            trigger_counts.items(),
            key=lambda x: x[1],
            reverse=True,
        )[:10]

        data.affected_surfaces = sorted(
            surface_counts.items(),
            key=lambda x: x[1],
            reverse=True,
        )[:10]

    def _build_summary(self, data: TechnicalData) -> str:
        """Build technical summary."""
        total = len(data.failures)
        resolved = sum(1 for f in data.failures if f.is_resolved)
        critical = data.failure_by_severity.get("S3", 0) + data.failure_by_severity.get("S4", 0)

        return (
            f"This report covers {total} failure(s) discovered during the "
            f"reporting period. {critical} are classified as critical severity. "
            f"{resolved} have been resolved. Average reproduction rate across "
            f"experiments is {data.reproduction_rate_avg:.0%}."
        )

    def _build_overview_section(self, data: TechnicalData) -> ReportSection:
        """Build overview section."""
        return ReportSection(
            title="Overview",
            order=1,
            level=1,
            tables=[
                {
                    "title": "Failure Distribution by Severity",
                    "headers": ["Severity", "Count", "Description"],
                    "rows": [
                        ["S4", data.failure_by_severity.get("S4", 0), "Safety-critical"],
                        ["S3", data.failure_by_severity.get("S3", 0), "High impact"],
                        ["S2", data.failure_by_severity.get("S2", 0), "Moderate impact"],
                        ["S1", data.failure_by_severity.get("S1", 0), "Low impact"],
                        ["S0", data.failure_by_severity.get("S0", 0), "Informational"],
                    ],
                },
                {
                    "title": "Failure Distribution by Class",
                    "headers": ["Class", "Count"],
                    "rows": sorted(
                        data.failure_by_class.items(),
                        key=lambda x: x[1],
                        reverse=True,
                    ),
                },
            ],
        )

    def _build_failures_section(self, data: TechnicalData) -> ReportSection:
        """Build detailed failures section."""
        # Sort by severity
        severity_order = {"S4": 0, "S3": 1, "S2": 2, "S1": 3, "S0": 4}
        sorted_failures = sorted(
            data.failures,
            key=lambda f: (severity_order.get(f.severity, 5), -f.reproducibility),
        )

        subsections = []
        for i, failure in enumerate(sorted_failures[:20]):  # Top 20
            subsection = ReportSection(
                title=f"{failure.severity}: {failure.primary_class}",
                order=i,
                level=2,
                content=f"""
**ID:** `{failure.id}`

**Description:** {failure.description[:500]}

**Reproducibility:** {failure.reproducibility:.0%}

**Triggers:**
{chr(10).join(f"- `{t}`" for t in failure.trigger_signature[:5]) or "- None identified"}

**Status:** {"✅ Resolved" if failure.is_resolved else "⚠️ Open"}
{f"**Resolution:** {failure.resolution_notes}" if failure.resolution_notes else ""}
""",
            )
            subsections.append(subsection)

        return ReportSection(
            title="Failure Details",
            order=2,
            level=1,
            content=f"Showing {len(subsections)} of {len(data.failures)} failures.",
            subsections=subsections,
        )

    def _build_patterns_section(self, data: TechnicalData) -> ReportSection:
        """Build patterns analysis section."""
        return ReportSection(
            title="Pattern Analysis",
            order=3,
            level=1,
            tables=[
                {
                    "title": "Common Trigger Patterns",
                    "headers": ["Trigger", "Occurrences"],
                    "rows": data.common_triggers,
                },
            ],
            content=(
                "These triggers appeared most frequently across discovered failures. "
                "Consider implementing detection mechanisms for these patterns."
            )
            if data.common_triggers
            else "No common patterns identified.",
        )

    def _build_surfaces_section(self, data: TechnicalData) -> ReportSection:
        """Build affected surfaces section."""
        return ReportSection(
            title="Affected Attack Surfaces",
            order=4,
            level=1,
            tables=[
                {
                    "title": "Target Surfaces",
                    "headers": ["Surface", "Failure Count"],
                    "rows": data.affected_surfaces,
                },
            ],
            content=(
                "These surfaces were most frequently affected by failures. "
                "Prioritize hardening efforts accordingly."
            )
            if data.affected_surfaces
            else "No surface data available.",
        )

    def _build_technical_recommendations(self, data: TechnicalData) -> ReportSection:
        """Build technical recommendations."""
        recommendations = []

        # Based on severity distribution
        critical = data.failure_by_severity.get("S3", 0) + data.failure_by_severity.get("S4", 0)
        if critical > 0:
            recommendations.append(
                f"**Critical Priority:** Address {critical} S3+ severity failures immediately"
            )

        # Based on reproduction rate
        if data.reproduction_rate_avg < 0.5:
            recommendations.append(
                "**Investigation Needed:** Low reproduction rate suggests intermittent issues. "
                "Consider increasing experiment runs or refining trigger conditions."
            )
        elif data.reproduction_rate_avg > 0.8:
            recommendations.append(
                "**High Reproducibility:** Failures are consistently reproducible. "
                "Good candidates for automated regression testing."
            )

        # Based on common triggers
        if data.common_triggers:
            top_trigger, count = data.common_triggers[0]
            if count > 3:
                recommendations.append(
                    f"**Pattern Alert:** Trigger `{top_trigger}` appears in {count} failures. "
                    "Implement input validation or guardrails for this pattern."
                )

        # Based on unresolved failures
        unresolved = sum(1 for f in data.failures if not f.is_resolved)
        if unresolved > 0:
            recommendations.append(
                f"**Resolution Backlog:** {unresolved} failures remain unresolved. "
                "Prioritize by severity and reproducibility."
            )

        if not recommendations:
            recommendations.append("No immediate technical actions required.")

        return ReportSection(
            title="Technical Recommendations",
            order=5,
            level=1,
            content="\n\n".join(recommendations),
        )
