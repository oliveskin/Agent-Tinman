"""Insight Synthesizer - generates natural language findings and recommendations."""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from ..memory.graph import MemoryGraph
from ..utils import generate_id, get_logger, utc_now
from .adaptive_memory import AdaptiveMemory
from .llm_backbone import LLMBackbone, ReasoningContext, ReasoningMode

logger = get_logger("insight_synthesizer")


@dataclass
class Insight:
    """A synthesized research insight."""

    id: str = field(default_factory=generate_id)
    insight_type: str = ""  # discovery, pattern, recommendation, question
    title: str = ""
    content: str = ""
    evidence: list[str] = field(default_factory=list)
    confidence: float = 0.0
    priority: str = "medium"
    created_at: datetime = field(default_factory=utc_now)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ResearchBrief:
    """A synthesized research brief for communication."""

    id: str = field(default_factory=generate_id)
    title: str = ""
    executive_summary: str = ""
    key_insights: list[Insight] = field(default_factory=list)
    patterns: list[str] = field(default_factory=list)
    recommendations: list[dict[str, Any]] = field(default_factory=list)
    open_questions: list[str] = field(default_factory=list)
    narrative: str = ""
    created_at: datetime = field(default_factory=utc_now)
    period_start: datetime | None = None
    period_end: datetime | None = None


class InsightSynthesizer:
    """
    Synthesizes research findings into natural language insights.

    This is Tinman's voice - how it communicates what it has learned
    to human collaborators. It can:

    - Summarize research findings
    - Identify patterns across failures
    - Generate actionable recommendations
    - Pose open questions for further research
    - Write narrative reports for stakeholders
    """

    def __init__(
        self,
        llm_backbone: LLMBackbone,
        graph: MemoryGraph | None = None,
        adaptive_memory: AdaptiveMemory | None = None,
    ):
        self.llm = llm_backbone
        self.graph = graph
        self.adaptive_memory = adaptive_memory

    async def synthesize_findings(
        self, findings: list[dict[str, Any]], focus: str | None = None
    ) -> list[Insight]:
        """Synthesize a list of findings into insights."""
        if not findings:
            return []

        context = ReasoningContext(
            mode=ReasoningMode.INSIGHT_SYNTHESIS,
            observations=[f.get("description", str(f)) for f in findings],
            task_description=focus or "Synthesize key insights from these findings",
        )

        # Add adaptive memory context if available
        if self.adaptive_memory:
            context.prior_knowledge = [
                f"Known pattern: {p['description']}"
                for p in self.adaptive_memory.get_context_for_reasoning().get(
                    "successful_patterns", []
                )
            ]

        result = await self.llm.reason(context)

        insights = []
        output = result.structured_output

        # Parse key insights
        for insight_data in output.get("key_insights", []):
            insight = Insight(
                insight_type="discovery",
                title=insight_data.get("insight", "")[:100],
                content=insight_data.get("insight", ""),
                evidence=[insight_data.get("evidence", "")],
                confidence=result.confidence,
            )

            # Set priority based on implication
            implication = insight_data.get("implication", "").lower()
            if any(word in implication for word in ["critical", "severe", "urgent", "immediately"]):
                insight.priority = "high"
            elif any(word in implication for word in ["minor", "low", "eventually"]):
                insight.priority = "low"

            insights.append(insight)

        # Add pattern insights
        for pattern in output.get("patterns", []):
            insights.append(
                Insight(
                    insight_type="pattern",
                    title=f"Pattern: {pattern[:50]}...",
                    content=pattern,
                    confidence=result.confidence,
                )
            )

        # Add recommendation insights
        for rec in output.get("recommendations", []):
            if isinstance(rec, dict):
                insights.append(
                    Insight(
                        insight_type="recommendation",
                        title=rec.get("action", "")[:100],
                        content=rec.get("rationale", rec.get("action", "")),
                        priority=rec.get("priority", "medium"),
                        confidence=result.confidence,
                    )
                )
            else:
                insights.append(
                    Insight(
                        insight_type="recommendation",
                        title=str(rec)[:100],
                        content=str(rec),
                        confidence=result.confidence,
                    )
                )

        # Add open questions
        for question in output.get("open_questions", []):
            insights.append(
                Insight(
                    insight_type="question",
                    title=f"Question: {question[:50]}...",
                    content=question,
                    confidence=0.5,  # Questions inherently uncertain
                )
            )

        return insights

    async def generate_brief(
        self, period_days: int = 7, title: str | None = None, exclude_demo_failures: bool = False
    ) -> ResearchBrief:
        """Generate a research brief for a time period."""
        brief = ResearchBrief(
            title=title or f"Research Brief - Last {period_days} Days",
            period_end=utc_now(),
            period_start=utc_now() - timedelta(days=period_days),
        )

        # Gather findings from graph
        findings = await self._gather_findings(
            brief.period_start,
            brief.period_end,
            exclude_demo_failures=exclude_demo_failures,
        )

        # Synthesize insights
        insights = await self.synthesize_findings(findings)
        brief.key_insights = [i for i in insights if i.insight_type == "discovery"]
        brief.patterns = [i.content for i in insights if i.insight_type == "pattern"]
        brief.recommendations = [
            {"action": i.title, "rationale": i.content, "priority": i.priority}
            for i in insights
            if i.insight_type == "recommendation"
        ]
        brief.open_questions = [i.content for i in insights if i.insight_type == "question"]

        # Generate executive summary
        brief.executive_summary = await self._generate_summary(findings, insights)

        # Generate narrative
        brief.narrative = await self._generate_narrative(findings, insights)

        return brief

    async def _gather_findings(
        self,
        start: datetime | None,
        end: datetime | None,
        exclude_demo_failures: bool = False,
    ) -> list[dict[str, Any]]:
        """Gather findings from the memory graph."""
        findings = []

        if not self.graph:
            return findings

        # Get failures
        failures = self.graph.get_failures(valid_only=False, limit=100)
        for f in failures:
            if start and f.created_at < start:
                continue
            if end and f.created_at > end:
                continue
            if exclude_demo_failures and f.data.get("is_synthetic"):
                continue
            findings.append(
                {
                    "type": "failure",
                    "description": f"Discovered {f.data.get('severity', 'S2')} {f.data.get('primary_class', 'unknown')} failure: {f.data.get('description', '')[:100]}",
                    "severity": f.data.get("severity"),
                    "data": f.data,
                }
            )

        # Get experiments
        experiments = self.graph.get_experiments(valid_only=False, limit=100)
        for e in experiments:
            if start and e.created_at < start:
                continue
            if end and e.created_at > end:
                continue
            total_runs = e.data.get("total_runs")
            failures_triggered = e.data.get("failures_triggered")
            reproduction_rate = e.data.get("reproduction_rate")
            hypothesis_validated = e.data.get("hypothesis_validated")
            details = []
            if total_runs is not None:
                details.append(f"runs={total_runs}")
            if failures_triggered is not None:
                details.append(f"failures={failures_triggered}")
            if reproduction_rate is not None:
                details.append(f"repro={reproduction_rate:.0%}")
            if hypothesis_validated is not None:
                details.append(f"validated={'yes' if hypothesis_validated else 'no'}")
            detail_text = f" ({', '.join(details)})" if details else ""
            findings.append(
                {
                    "type": "experiment",
                    "description": f"Ran {e.data.get('stress_type', 'unknown')} experiment{detail_text}",
                    "data": e.data,
                }
            )

        # Get interventions
        interventions = self.graph.get_interventions(valid_only=False, limit=100)
        for i in interventions:
            if start and i.created_at < start:
                continue
            if end and i.created_at > end:
                continue
            findings.append(
                {
                    "type": "intervention",
                    "description": f"Proposed {i.data.get('intervention_type', 'unknown')} intervention",
                    "risk_tier": i.data.get("risk_tier"),
                    "data": i.data,
                }
            )

        return findings

    async def _generate_summary(self, findings: list[dict], insights: list[Insight]) -> str:
        """Generate an executive summary."""
        # Count findings by type
        failure_count = sum(1 for f in findings if f["type"] == "failure")
        experiment_count = sum(1 for f in findings if f["type"] == "experiment")
        intervention_count = sum(1 for f in findings if f["type"] == "intervention")

        # Get high priority insights
        high_priority = [i for i in insights if i.priority == "high"]

        # Build summary
        summary_parts = []

        if failure_count > 0:
            severity_counts = {}
            for f in findings:
                if f["type"] == "failure":
                    sev = f.get("severity", "S2")
                    severity_counts[sev] = severity_counts.get(sev, 0) + 1

            summary_parts.append(
                f"Discovered {failure_count} failure(s) "
                f"({', '.join(f'{v} {k}' for k, v in sorted(severity_counts.items()))})"
            )

        if experiment_count > 0:
            summary_parts.append(f"Ran {experiment_count} experiment(s)")

        if intervention_count > 0:
            summary_parts.append(f"Proposed {intervention_count} intervention(s)")

        if high_priority:
            summary_parts.append(
                f"**{len(high_priority)} high-priority finding(s) require attention**"
            )

        return ". ".join(summary_parts) + "."

    async def _generate_narrative(self, findings: list[dict], insights: list[Insight]) -> str:
        """Generate a full narrative report using LLM."""
        if not findings:
            return "No findings were recorded in this period. Run experiments to generate findings."

        failure_count = sum(1 for f in findings if f["type"] == "failure")
        experiment_count = sum(1 for f in findings if f["type"] == "experiment")

        if failure_count == 0 and experiment_count > 0:
            return (
                "We executed experiments during this period, but no failures were "
                "recorded. The results suggest the current test cases did not trigger "
                "observable failure modes. Next steps: expand adversarial techniques, "
                "increase run counts, and add targeted probes to surface edge cases."
            )

        context = ReasoningContext(
            mode=ReasoningMode.INSIGHT_SYNTHESIS,
            observations=[f.get("description", str(f)) for f in findings],
            prior_knowledge=[f"Insight: {i.content}" for i in insights[:10]],
            task_description="""Write a research narrative for the team.

This should read like a research memo, not a list of bullet points.
Cover:
1. What we set out to investigate
2. What we found
3. What surprised us
4. What we recommend doing next

Write in clear, professional prose.""",
        )

        result = await self.llm.reason(context)

        # Extract narrative from response
        output = result.structured_output
        if "narrative" in output:
            return output["narrative"]

        return result.content

    async def answer_question(self, question: str) -> str:
        """Answer a question about research findings."""
        # Gather recent context
        if self.graph:
            recent_failures = self.graph.get_failures(limit=10)
            recent_interventions = self.graph.get_interventions(limit=5)

            observations = [
                f"Recent failure: {f.data.get('primary_class')} - {f.data.get('description', '')[:100]}"
                for f in recent_failures
            ] + [
                f"Recent intervention: {i.data.get('intervention_type')}"
                for i in recent_interventions
            ]
        else:
            observations = []

        context = ReasoningContext(
            mode=ReasoningMode.DIALOGUE,
            observations=observations,
            task_description=question,
        )

        if self.adaptive_memory:
            context.prior_knowledge = self.adaptive_memory.get_research_suggestions()

        result = await self.llm.reason(context)

        return result.content

    async def explain_failure(self, failure_id: str) -> str:
        """Generate an explanation of a specific failure."""
        if not self.graph:
            return "Cannot explain failure: no memory graph available."

        # Get failure node
        failure = self.graph.get_node(failure_id)
        if not failure:
            return f"Failure {failure_id} not found."

        # Get lineage
        lineage = self.graph.get_lineage(failure_id)

        context = ReasoningContext(
            mode=ReasoningMode.FAILURE_ANALYSIS,
            observations=[
                f"Failure: {failure.data.get('primary_class')} ({failure.data.get('severity')})",
                f"Description: {failure.data.get('description', 'No description')}",
                f"Trigger: {failure.data.get('trigger_signature', [])}",
                f"Reproducibility: {failure.data.get('reproducibility', 0):.0%}",
            ]
            + [f"Cause chain: {node.data}" for node, edge in lineage],
            task_description="Explain this failure in plain language. What happened? Why? What should we do?",
        )

        result = await self.llm.reason(context)

        return result.content

    async def suggest_next_steps(self) -> list[str]:
        """Suggest what to research next based on current state."""
        suggestions = []

        # Get adaptive memory suggestions
        if self.adaptive_memory:
            suggestions.extend(self.adaptive_memory.get_research_suggestions())

        # Get graph-based suggestions
        if self.graph:
            # Unresolved high-severity failures
            severe = self.graph.find_failures_by_severity("S3")
            unresolved = [f for f in severe if not f.data.get("is_resolved")]
            if unresolved:
                suggestions.append(
                    f"Investigate {len(unresolved)} unresolved high-severity failures"
                )

            # Interventions pending deployment
            interventions = self.graph.get_interventions(limit=20)
            safe_pending = [
                i
                for i in interventions
                if i.data.get("risk_tier") == "safe" and not i.data.get("deployed")
            ]
            if safe_pending:
                suggestions.append(f"Consider deploying {len(safe_pending)} safe interventions")

        # Use LLM to prioritize and add creative suggestions
        if suggestions:
            context = ReasoningContext(
                mode=ReasoningMode.DIALOGUE,
                observations=suggestions,
                task_description="""Given these potential research directions,
prioritize them and add any creative suggestions I might have missed.
What should Tinman focus on next?""",
            )

            result = await self.llm.reason(context)
            # Append LLM's suggestions
            suggestions.append(f"LLM recommendation: {result.content[:500]}")

        return suggestions
