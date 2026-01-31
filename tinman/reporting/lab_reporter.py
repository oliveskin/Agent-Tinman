"""Lab Reporter - detailed reports for research analysis."""

from dataclasses import dataclass, field
from datetime import datetime

from ..memory.graph import MemoryGraph
from ..memory.models import NodeType
from ..utils import generate_id, get_logger, utc_now

logger = get_logger("lab_reporter")


@dataclass
class FailureSummary:
    """Summary of a failure for reporting."""

    id: str
    primary_class: str
    secondary_class: str | None
    severity: str
    description: str
    reproducibility: float
    is_novel: bool
    is_synthetic: bool
    trigger_signature: list[str]
    discovered_at: datetime


@dataclass
class ExperimentSummary:
    """Summary of an experiment for reporting."""

    id: str
    hypothesis_id: str
    stress_type: str
    total_runs: int
    failures_found: int
    reproduction_rate: float
    hypothesis_validated: bool


@dataclass
class InterventionSummary:
    """Summary of an intervention for reporting."""

    id: str
    failure_id: str
    intervention_type: str
    risk_tier: str
    expected_improvement: float
    simulation_outcome: str | None
    deploy_recommended: bool


@dataclass
class LabReport:
    """Complete lab report for a research session."""

    id: str = field(default_factory=generate_id)
    generated_at: datetime = field(default_factory=utc_now)

    # Time range
    period_start: datetime | None = None
    period_end: datetime | None = None

    # Summary stats
    hypotheses_tested: int = 0
    experiments_run: int = 0
    failures_discovered: int = 0
    novel_failures: int = 0
    interventions_proposed: int = 0
    simulations_run: int = 0

    # Details
    failures: list[FailureSummary] = field(default_factory=list)
    experiments: list[ExperimentSummary] = field(default_factory=list)
    interventions: list[InterventionSummary] = field(default_factory=list)

    # Key findings
    key_findings: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)


class LabReporter:
    """
    Generates detailed reports for research analysis.

    Lab reports are comprehensive and include:
    - All discovered failures with full details
    - Experiment methodology and results
    - Causal analysis
    - Intervention recommendations
    """

    def __init__(self, graph: MemoryGraph | None = None):
        self.graph = graph

    def generate(
        self,
        period_start: datetime | None = None,
        period_end: datetime | None = None,
        exclude_demo_failures: bool = False,
    ) -> LabReport:
        """Generate a lab report for the given period."""
        report = LabReport(
            period_start=period_start,
            period_end=period_end or utc_now(),
        )

        if not self.graph:
            return report

        # Gather data from memory graph
        self._gather_hypotheses(report)
        self._gather_experiments(report)
        self._gather_failures(report, exclude_demo_failures=exclude_demo_failures)
        self._gather_interventions(report)
        self._gather_simulations(report)

        # Generate insights
        self._generate_key_findings(report)
        self._generate_recommendations(report)

        return report

    def _gather_hypotheses(self, report: LabReport) -> None:
        """Gather hypothesis data."""
        hypotheses = self.graph.get_hypotheses(valid_only=False)
        report.hypotheses_tested = len(hypotheses)

    def _gather_experiments(self, report: LabReport) -> None:
        """Gather experiment data."""
        experiments = self.graph.get_experiments(valid_only=False)

        for exp in experiments:
            data = exp.data
            summary = ExperimentSummary(
                id=exp.id,
                hypothesis_id=data.get("hypothesis_id", ""),
                stress_type=data.get("stress_type", ""),
                total_runs=data.get("total_runs", 0),
                failures_found=data.get("failures_triggered", 0),
                reproduction_rate=data.get("reproduction_rate", 0.0),
                hypothesis_validated=data.get("hypothesis_validated", False),
            )
            report.experiments.append(summary)

        report.experiments_run = len(experiments)

    def _gather_failures(self, report: LabReport, exclude_demo_failures: bool = False) -> None:
        """Gather failure data."""
        failures = self.graph.get_failures(valid_only=False)

        for failure in failures:
            data = failure.data
            if exclude_demo_failures and data.get("is_synthetic"):
                continue
            summary = FailureSummary(
                id=failure.id,
                primary_class=data.get("primary_class", "unknown"),
                secondary_class=data.get("secondary_class"),
                severity=data.get("severity", "S2"),
                description=data.get("description", "")[:200],
                reproducibility=data.get("reproducibility", 0.0),
                is_novel=data.get("is_novel", False),
                is_synthetic=data.get("is_synthetic", False),
                trigger_signature=data.get("trigger_signature", []),
                discovered_at=failure.created_at,
            )
            report.failures.append(summary)

            if summary.is_novel:
                report.novel_failures += 1

        report.failures_discovered = len(failures)

    def _gather_interventions(self, report: LabReport) -> None:
        """Gather intervention data."""
        interventions = self.graph.get_interventions(valid_only=False)

        for intervention in interventions:
            data = intervention.data
            summary = InterventionSummary(
                id=intervention.id,
                failure_id=data.get("failure_id", ""),
                intervention_type=data.get("intervention_type", ""),
                risk_tier=data.get("risk_tier", "review"),
                expected_improvement=data.get("expected_gains", {}).get("failure_reduction", 0.0),
                simulation_outcome=None,  # Will be filled from simulation data
                deploy_recommended=False,
            )
            report.interventions.append(summary)

        report.interventions_proposed = len(interventions)

    def _gather_simulations(self, report: LabReport) -> None:
        """Gather simulation data and link to interventions."""
        simulations = self.graph.repo.get_nodes_by_type(NodeType.SIMULATION, valid_only=False)
        report.simulations_run = len(simulations)

        # Link simulation outcomes to interventions
        sim_by_intervention = {}
        for sim in simulations:
            data = sim.data
            intervention_id = data.get("intervention_id")
            if intervention_id:
                sim_by_intervention[intervention_id] = {
                    "outcome": data.get("outcome"),
                    "deploy_recommended": data.get("deploy_recommended", False),
                }

        for intervention in report.interventions:
            sim_data = sim_by_intervention.get(intervention.id)
            if sim_data:
                intervention.simulation_outcome = sim_data["outcome"]
                intervention.deploy_recommended = sim_data["deploy_recommended"]

    def _generate_key_findings(self, report: LabReport) -> None:
        """Generate key findings from the data."""
        findings = []

        # Novel failure findings
        if report.novel_failures > 0:
            findings.append(f"Discovered {report.novel_failures} novel failure mode(s)")

        # High severity findings
        high_severity = [f for f in report.failures if f.severity in ("S3", "S4")]
        if high_severity:
            findings.append(f"{len(high_severity)} high-severity failure(s) require attention")

        # Highly reproducible failures
        reproducible = [f for f in report.failures if f.reproducibility >= 0.7]
        if reproducible:
            findings.append(f"{len(reproducible)} failure(s) are highly reproducible (>70%)")

        # Effective interventions
        effective = [
            i
            for i in report.interventions
            if i.simulation_outcome == "improved" and i.deploy_recommended
        ]
        if effective:
            findings.append(f"{len(effective)} intervention(s) showed positive simulation results")

        # Hypothesis validation rate
        validated = sum(1 for e in report.experiments if e.hypothesis_validated)
        if report.experiments_run > 0:
            rate = validated / report.experiments_run
            findings.append(
                f"Hypothesis validation rate: {rate:.0%} ({validated}/{report.experiments_run})"
            )

        report.key_findings = findings

    def _generate_recommendations(self, report: LabReport) -> None:
        """Generate recommendations based on findings."""
        recommendations = []

        # Recommend deploying effective interventions
        deploy_ready = [
            i for i in report.interventions if i.deploy_recommended and i.risk_tier == "safe"
        ]
        if deploy_ready:
            recommendations.append(
                f"Consider deploying {len(deploy_ready)} safe, tested intervention(s)"
            )

        # Recommend more testing for high-severity failures
        untreated_severe = [
            f
            for f in report.failures
            if f.severity in ("S3", "S4")
            and not any(i.failure_id == f.id for i in report.interventions)
        ]
        if untreated_severe:
            recommendations.append(
                f"Develop interventions for {len(untreated_severe)} high-severity failure(s)"
            )

        # Recommend investigation of novel failures
        if report.novel_failures > 0:
            recommendations.append("Investigate novel failures for potential systemic issues")

        # Recommend more experiments if validation rate is low
        if report.experiments_run > 0:
            validated = sum(1 for e in report.experiments if e.hypothesis_validated)
            rate = validated / report.experiments_run
            if rate < 0.3:
                recommendations.append(
                    "Consider refining hypothesis generation to improve validation rate"
                )

        report.recommendations = recommendations

    def to_markdown(self, report: LabReport) -> str:
        """Convert report to markdown format."""
        lines = [
            "# Lab Report",
            "",
            f"**Generated:** {report.generated_at.isoformat()}",
            "",
            "## Summary",
            "",
            "| Metric | Count |",
            "|--------|-------|",
            f"| Hypotheses Tested | {report.hypotheses_tested} |",
            f"| Experiments Run | {report.experiments_run} |",
            f"| Failures Discovered | {report.failures_discovered} |",
            f"| Novel Failures | {report.novel_failures} |",
            f"| Interventions Proposed | {report.interventions_proposed} |",
            f"| Simulations Run | {report.simulations_run} |",
            "",
        ]

        # Key findings
        if report.key_findings:
            lines.extend(
                [
                    "## Key Findings",
                    "",
                ]
            )
            for finding in report.key_findings:
                lines.append(f"- {finding}")
            lines.append("")

        # Failures
        if report.failures:
            lines.extend(
                [
                    "## Discovered Failures",
                    "",
                    "| Severity | Class | Reproducibility | Novel | Synthetic |",
                    "|----------|-------|-----------------|-------|-----------|",
                ]
            )
            for f in sorted(report.failures, key=lambda x: x.severity, reverse=True):
                novel = "Yes" if f.is_novel else "No"
                synthetic = "Yes" if f.is_synthetic else "No"
                lines.append(
                    f"| {f.severity} | {f.primary_class} | {f.reproducibility:.0%} | {novel} | {synthetic} |"
                )
            lines.append("")

        # Recommendations
        if report.recommendations:
            lines.extend(
                [
                    "## Recommendations",
                    "",
                ]
            )
            for rec in report.recommendations:
                lines.append(f"- {rec}")
            lines.append("")

        return "\n".join(lines)

    def to_demo_markdown(self, report: LabReport) -> str:
        """Convert report to a concise demo-friendly markdown format."""
        lines = [
            "# Tinman Demo Report",
            "",
            f"**Generated:** {report.generated_at.isoformat()}",
            "",
            "## Snapshot",
            f"- Hypotheses tested: {report.hypotheses_tested}",
            f"- Experiments run: {report.experiments_run}",
            f"- Failures discovered: {report.failures_discovered}",
            f"- Interventions proposed: {report.interventions_proposed}",
            "",
        ]

        if report.key_findings:
            lines.append("## Key Findings")
            for finding in report.key_findings[:5]:
                lines.append(f"- {finding}")
            lines.append("")

        if report.failures:
            lines.append("## Top Failures")
            for failure in sorted(report.failures, key=lambda x: x.severity, reverse=True)[:5]:
                tag = " (synthetic)" if failure.is_synthetic else ""
                lines.append(
                    f"- [{failure.severity}] {failure.primary_class}: {failure.description}{tag}"
                )
            lines.append("")

        if report.interventions:
            lines.append("## Proposed Interventions")
            for intervention in report.interventions[:5]:
                lines.append(
                    f"- [{intervention.risk_tier}] {intervention.intervention_type} "
                    f"for {intervention.failure_id}"
                )
            lines.append("")

        if report.recommendations:
            lines.append("## Recommendations")
            for rec in report.recommendations[:5]:
                lines.append(f"- {rec}")
            lines.append("")

        lines.append("*Generated by Tinman FDRA*")
        return "\n".join(lines)

    def to_dict(self, report: LabReport) -> dict:
        """Convert report to dictionary."""
        return {
            "id": report.id,
            "generated_at": report.generated_at.isoformat(),
            "period_start": report.period_start.isoformat() if report.period_start else None,
            "period_end": report.period_end.isoformat() if report.period_end else None,
            "summary": {
                "hypotheses_tested": report.hypotheses_tested,
                "experiments_run": report.experiments_run,
                "failures_discovered": report.failures_discovered,
                "novel_failures": report.novel_failures,
                "interventions_proposed": report.interventions_proposed,
                "simulations_run": report.simulations_run,
            },
            "key_findings": report.key_findings,
            "recommendations": report.recommendations,
            "failures": [
                {
                    "id": f.id,
                    "primary_class": f.primary_class,
                    "severity": f.severity,
                    "reproducibility": f.reproducibility,
                    "is_novel": f.is_novel,
                }
                for f in report.failures
            ],
            "interventions": [
                {
                    "id": i.id,
                    "type": i.intervention_type,
                    "risk_tier": i.risk_tier,
                    "deploy_recommended": i.deploy_recommended,
                }
                for i in report.interventions
            ],
        }
