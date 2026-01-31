"""Executive Summary Report generator.

Provides high-level summaries suitable for leadership and stakeholders,
focusing on key metrics, trends, and actionable insights.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from ..core.cost_tracker import CostTracker
from ..memory.graph import MemoryGraph
from ..utils import get_logger, utc_now
from .base import (
    Report,
    ReportGenerator,
    ReportMetadata,
    ReportSection,
    ReportType,
)

logger = get_logger("reporting.executive")


@dataclass
class ExecutiveData:
    """Data specific to executive reports."""

    total_failures: int = 0
    critical_failures: int = 0
    resolved_failures: int = 0
    resolution_rate: float = 0.0
    novel_findings: int = 0
    interventions_deployed: int = 0
    interventions_effective: int = 0
    cost_total_usd: float = 0.0
    cost_per_finding: float = 0.0
    trend_failures_week_over_week: float = 0.0
    trend_resolutions_week_over_week: float = 0.0
    top_failure_classes: list[tuple[str, int]] = field(default_factory=list)
    risk_score: float = 0.0  # 0-100 composite risk score


class ExecutiveSummaryReport(ReportGenerator):
    """Generator for executive summary reports.

    These reports are designed for leadership and provide:
    - High-level KPIs
    - Trend analysis
    - Risk assessment
    - Cost analysis
    - Actionable recommendations

    Usage:
        generator = ExecutiveSummaryReport(graph=memory_graph, cost_tracker=tracker)
        report = await generator.generate(
            period_start=last_week,
            period_end=now,
        )
        html = generator.format(report, ReportFormat.HTML)
    """

    def __init__(
        self,
        graph: MemoryGraph | None = None,
        cost_tracker: CostTracker | None = None,
    ):
        self.graph = graph
        self.cost_tracker = cost_tracker

    @property
    def report_type(self) -> ReportType:
        return ReportType.EXECUTIVE_SUMMARY

    @property
    def name(self) -> str:
        return "Executive Summary"

    async def generate(
        self,
        period_start: datetime | None = None,
        period_end: datetime | None = None,
        **kwargs,
    ) -> Report[ExecutiveData]:
        """Generate executive summary report."""
        period_end = period_end or utc_now()
        period_start = period_start or (period_end - timedelta(days=7))

        # Create report with metadata
        report = Report[ExecutiveData](
            metadata=ReportMetadata(
                type=self.report_type,
                title="Executive Summary Report",
                description="High-level overview of AI reliability findings and interventions",
                period_start=period_start,
                period_end=period_end,
                confidentiality="internal",
            ),
            raw_data=ExecutiveData(),
        )

        # Gather data
        data = report.raw_data
        await self._gather_failure_data(data, period_start, period_end)
        await self._gather_intervention_data(data, period_start, period_end)
        await self._gather_cost_data(data, period_start, period_end)
        await self._calculate_trends(data, period_start, period_end)
        await self._calculate_risk_score(data)

        # Build report sections
        report.summary = self._build_summary(data)
        report.sections = [
            self._build_kpi_section(data),
            self._build_failures_section(data),
            self._build_interventions_section(data),
            self._build_trends_section(data),
            self._build_recommendations_section(data),
        ]

        return report

    async def _gather_failure_data(
        self,
        data: ExecutiveData,
        start: datetime,
        end: datetime,
    ) -> None:
        """Gather failure-related metrics."""
        if not self.graph:
            return

        failures = self.graph.get_failures(valid_only=False)

        # Filter by period
        period_failures = [f for f in failures if start <= f.created_at <= end]

        data.total_failures = len(period_failures)

        # Count by severity
        data.critical_failures = sum(
            1 for f in period_failures if f.data.get("severity") in ("S3", "S4")
        )

        # Count resolved
        data.resolved_failures = sum(1 for f in period_failures if f.data.get("is_resolved", False))

        if data.total_failures > 0:
            data.resolution_rate = data.resolved_failures / data.total_failures

        # Novel findings
        data.novel_findings = sum(1 for f in period_failures if f.data.get("is_novel", False))

        # Top failure classes
        class_counts: dict[str, int] = {}
        for f in period_failures:
            cls = f.data.get("primary_class", "unknown")
            class_counts[cls] = class_counts.get(cls, 0) + 1

        data.top_failure_classes = sorted(
            class_counts.items(),
            key=lambda x: x[1],
            reverse=True,
        )[:5]

    async def _gather_intervention_data(
        self,
        data: ExecutiveData,
        start: datetime,
        end: datetime,
    ) -> None:
        """Gather intervention-related metrics."""
        if not self.graph:
            return

        interventions = self.graph.get_interventions(valid_only=False)

        # Filter by period
        period_interventions = [i for i in interventions if start <= i.created_at <= end]

        # Count deployed
        data.interventions_deployed = sum(
            1 for i in period_interventions if i.data.get("deployed", False)
        )

        # Count effective (based on simulation)
        data.interventions_effective = sum(
            1 for i in period_interventions if i.data.get("simulation_outcome") == "improved"
        )

    async def _gather_cost_data(
        self,
        data: ExecutiveData,
        start: datetime,
        end: datetime,
    ) -> None:
        """Gather cost metrics."""
        if not self.cost_tracker:
            return

        records = self.cost_tracker.get_records(since=start)
        data.cost_total_usd = sum(r.amount_usd for r in records)

        if data.total_failures > 0:
            data.cost_per_finding = data.cost_total_usd / data.total_failures

    async def _calculate_trends(
        self,
        data: ExecutiveData,
        start: datetime,
        end: datetime,
    ) -> None:
        """Calculate week-over-week trends."""
        if not self.graph:
            return

        period_days = (end - start).days
        if period_days < 7:
            return

        # Previous period
        prev_start = start - timedelta(days=period_days)
        prev_end = start

        failures = self.graph.get_failures(valid_only=False)

        # Current period count
        current_count = sum(1 for f in failures if start <= f.created_at <= end)

        # Previous period count
        prev_count = sum(1 for f in failures if prev_start <= f.created_at <= prev_end)

        if prev_count > 0:
            data.trend_failures_week_over_week = (current_count - prev_count) / prev_count * 100

        # Similar for resolutions
        current_resolved = sum(
            1 for f in failures if start <= f.created_at <= end and f.data.get("is_resolved")
        )
        prev_resolved = sum(
            1
            for f in failures
            if prev_start <= f.created_at <= prev_end and f.data.get("is_resolved")
        )

        if prev_resolved > 0:
            data.trend_resolutions_week_over_week = (
                (current_resolved - prev_resolved) / prev_resolved * 100
            )

    async def _calculate_risk_score(self, data: ExecutiveData) -> None:
        """Calculate composite risk score (0-100)."""
        score = 50.0  # Base score

        # Increase for unresolved critical failures
        unresolved_critical = data.critical_failures - (
            data.resolved_failures if data.resolution_rate > 0.5 else 0
        )
        score += min(unresolved_critical * 10, 30)

        # Decrease for high resolution rate
        if data.resolution_rate > 0.8:
            score -= 15
        elif data.resolution_rate > 0.6:
            score -= 10

        # Increase for upward failure trend
        if data.trend_failures_week_over_week > 50:
            score += 15
        elif data.trend_failures_week_over_week > 20:
            score += 10

        # Decrease for effective interventions
        if data.interventions_deployed > 0:
            effectiveness = data.interventions_effective / data.interventions_deployed
            score -= effectiveness * 10

        data.risk_score = max(0, min(100, score))

    def _build_summary(self, data: ExecutiveData) -> str:
        """Build executive summary text."""
        risk_level = (
            "LOW" if data.risk_score < 40 else ("MEDIUM" if data.risk_score < 70 else "HIGH")
        )

        summary_parts = [
            f"During this reporting period, Tinman discovered **{data.total_failures} "
            f"failure modes**, of which **{data.critical_failures}** were classified "
            f"as critical (S3+).",
        ]

        if data.novel_findings > 0:
            summary_parts.append(
                f"**{data.novel_findings} novel findings** were identified, "
                "representing previously unknown failure patterns."
            )

        summary_parts.append(
            f"The overall resolution rate stands at **{data.resolution_rate:.0%}**."
        )

        if data.interventions_deployed > 0:
            summary_parts.append(
                f"**{data.interventions_deployed} interventions** were deployed, "
                f"with **{data.interventions_effective}** showing measurable improvement."
            )

        summary_parts.append(
            f"Current risk assessment: **{risk_level}** (score: {data.risk_score:.0f}/100)."
        )

        return " ".join(summary_parts)

    def _build_kpi_section(self, data: ExecutiveData) -> ReportSection:
        """Build KPI section."""
        return ReportSection(
            title="Key Performance Indicators",
            order=1,
            level=1,
            tables=[
                {
                    "title": "Period Overview",
                    "headers": ["Metric", "Value", "Status"],
                    "rows": [
                        [
                            "Total Failures",
                            data.total_failures,
                            self._status_icon(data.total_failures < 10),
                        ],
                        [
                            "Critical Failures",
                            data.critical_failures,
                            self._status_icon(data.critical_failures < 3),
                        ],
                        [
                            "Resolution Rate",
                            f"{data.resolution_rate:.0%}",
                            self._status_icon(data.resolution_rate > 0.7),
                        ],
                        ["Novel Findings", data.novel_findings, "🔍"],
                        [
                            "Risk Score",
                            f"{data.risk_score:.0f}/100",
                            self._risk_icon(data.risk_score),
                        ],
                    ],
                }
            ],
        )

    def _build_failures_section(self, data: ExecutiveData) -> ReportSection:
        """Build failures analysis section."""
        return ReportSection(
            title="Failure Analysis",
            order=2,
            level=1,
            content=f"Discovered {data.total_failures} failures across {len(data.top_failure_classes)} categories.",
            tables=[
                {
                    "title": "Top Failure Classes",
                    "headers": ["Class", "Count", "% of Total"],
                    "rows": [
                        [
                            cls,
                            count,
                            f"{count / data.total_failures * 100:.0f}%"
                            if data.total_failures > 0
                            else "0%",
                        ]
                        for cls, count in data.top_failure_classes
                    ],
                }
            ]
            if data.top_failure_classes
            else [],
        )

    def _build_interventions_section(self, data: ExecutiveData) -> ReportSection:
        """Build interventions section."""
        return ReportSection(
            title="Interventions",
            order=3,
            level=1,
            tables=[
                {
                    "title": "Intervention Summary",
                    "headers": ["Metric", "Value"],
                    "rows": [
                        ["Interventions Deployed", data.interventions_deployed],
                        ["Interventions Effective", data.interventions_effective],
                        [
                            "Effectiveness Rate",
                            f"{data.interventions_effective / data.interventions_deployed * 100:.0f}%"
                            if data.interventions_deployed > 0
                            else "N/A",
                        ],
                    ],
                }
            ],
        )

    def _build_trends_section(self, data: ExecutiveData) -> ReportSection:
        """Build trends section."""
        failure_trend = data.trend_failures_week_over_week
        resolution_trend = data.trend_resolutions_week_over_week

        return ReportSection(
            title="Trends",
            order=4,
            level=1,
            tables=[
                {
                    "title": "Week-over-Week Changes",
                    "headers": ["Metric", "Change", "Direction"],
                    "rows": [
                        [
                            "Failures",
                            f"{abs(failure_trend):.0f}%",
                            "📈 Increasing" if failure_trend > 0 else "📉 Decreasing",
                        ],
                        [
                            "Resolutions",
                            f"{abs(resolution_trend):.0f}%",
                            "📈 Increasing" if resolution_trend > 0 else "📉 Decreasing",
                        ],
                    ],
                }
            ],
        )

    def _build_recommendations_section(self, data: ExecutiveData) -> ReportSection:
        """Build recommendations section."""
        recommendations = []

        if data.critical_failures > data.resolved_failures:
            recommendations.append("Prioritize resolution of critical (S3+) failures")

        if data.resolution_rate < 0.5:
            recommendations.append("Investigate bottlenecks in failure resolution process")

        if data.trend_failures_week_over_week > 30:
            recommendations.append("Analyze root causes for increasing failure rate")

        if data.novel_findings > 3:
            recommendations.append("Schedule deep-dive investigation of novel failure patterns")

        if data.interventions_deployed < data.critical_failures:
            recommendations.append("Develop interventions for unaddressed critical failures")

        if not recommendations:
            recommendations.append("Continue current monitoring and research cadence")

        return ReportSection(
            title="Recommendations",
            order=5,
            level=1,
            content="\n".join(f"- {rec}" for rec in recommendations),
        )

    def _status_icon(self, is_good: bool) -> str:
        """Return status icon."""
        return "✅" if is_good else "⚠️"

    def _risk_icon(self, score: float) -> str:
        """Return risk-appropriate icon."""
        if score < 40:
            return "🟢"
        if score < 70:
            return "🟡"
        return "🔴"
