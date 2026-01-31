"""Failure Discovery Agent - discovers and classifies failures using LLM analysis."""

from dataclasses import dataclass, field
from typing import Any

from ..memory.graph import MemoryGraph
from ..reasoning.adaptive_memory import AdaptiveMemory
from ..reasoning.llm_backbone import LLMBackbone, ReasoningContext, ReasoningMode
from ..taxonomy.causal_linker import CausalLinker
from ..taxonomy.classifiers import ClassificationResult, FailureClassifier
from ..taxonomy.failure_types import FailureClass, Severity
from ..utils import generate_id, get_logger
from .base import AgentContext, AgentResult, BaseAgent
from .experiment_executor import ExperimentResult, RunResult

logger = get_logger("failure_discovery")


def safe_get(data: dict, *keys, default=None):
    """Safely get nested dictionary values."""
    for key in keys:
        if isinstance(data, dict):
            data = data.get(key, default)
        else:
            return default
    return data


@dataclass
class DiscoveredFailure:
    """A newly discovered failure mode."""

    id: str = field(default_factory=generate_id)

    # Classification
    primary_class: FailureClass = FailureClass.REASONING
    secondary_class: str | None = None
    severity: Severity = Severity.S2

    # Details
    description: str = ""
    trigger_signature: list[str] = field(default_factory=list)
    reproducibility: float = 0.0

    # Source
    experiment_id: str = ""
    run_ids: list[str] = field(default_factory=list)

    # Analysis
    classification_confidence: float = 0.0
    causal_analysis: dict[str, Any] | None = None

    # LLM-generated insights
    llm_analysis: str = ""
    contributing_factors: list[str] = field(default_factory=list)
    key_insight: str = ""

    # Status
    is_novel: bool = False  # First time we've seen this
    parent_failure_id: str | None = None  # If evolved from another


class FailureDiscoveryAgent(BaseAgent):
    """
    Discovers and classifies failure modes using LLM-powered analysis.

    This agent doesn't just pattern-match - it reasons about:
    - What actually went wrong (deep analysis)
    - Why it went wrong (root cause)
    - What it means (implications)
    - What to do about it (recommendations)
    """

    def __init__(
        self,
        graph: MemoryGraph | None = None,
        classifier: FailureClassifier | None = None,
        causal_linker: CausalLinker | None = None,
        llm_backbone: LLMBackbone | None = None,
        adaptive_memory: AdaptiveMemory | None = None,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.graph = graph
        self.classifier = classifier or FailureClassifier()
        self.causal_linker = causal_linker or CausalLinker()
        self.llm = llm_backbone
        self.adaptive_memory = adaptive_memory

    @property
    def agent_type(self) -> str:
        return "failure_discovery"

    async def execute(self, context: AgentContext, **kwargs) -> AgentResult:
        """Discover failures from experiment results."""
        results = kwargs.get("results", [])

        if not results:
            return AgentResult(
                agent_id=self.id,
                agent_type=self.agent_type,
                success=False,
                error="No experiment results provided",
            )

        discoveries = []
        for result in results:
            if result.failures_triggered > 0:
                failure = await self._analyze_failure(result)
                if failure:
                    discoveries.append(failure)

        # Deduplicate and merge similar failures
        discoveries = self._merge_similar(discoveries)

        # Record to memory graph and adaptive memory
        if self.graph:
            for failure in discoveries:
                self._record_failure(failure, context)

        if self.adaptive_memory:
            for failure in discoveries:
                self.adaptive_memory.record_failure_signature(failure.trigger_signature)

        return AgentResult(
            agent_id=self.id,
            agent_type=self.agent_type,
            success=True,
            data={
                "failures_discovered": len(discoveries),
                "novel_failures": sum(1 for f in discoveries if f.is_novel),
                "failures": [self._failure_to_dict(f) for f in discoveries],
                "used_llm_analysis": self.llm is not None,
            },
        )

    async def _analyze_failure(self, result: ExperimentResult) -> DiscoveredFailure | None:
        """Analyze experiment result and extract failure with deep understanding."""
        # Get runs that triggered failures
        failure_runs = [r for r in result.runs if r.failure_triggered]
        if not failure_runs:
            return None

        # Aggregate failure descriptions
        descriptions = [r.failure_description for r in failure_runs if r.failure_description]

        if not descriptions:
            return None

        combined_description = "; ".join(set(descriptions))

        # Use LLM for deep analysis if available
        if self.llm:
            failure = await self._analyze_with_llm(combined_description, failure_runs, result)
        else:
            failure = self._analyze_heuristic(combined_description, failure_runs, result)

        return failure

    async def _analyze_with_llm(
        self, description: str, runs: list[RunResult], result: ExperimentResult
    ) -> DiscoveredFailure:
        """Perform deep failure analysis using LLM."""
        # Build observations from runs
        observations = [
            f"Failure description: {description}",
            f"Reproduction rate: {result.reproduction_rate:.0%}",
            f"Total runs: {result.total_runs}",
        ]

        for run in runs[:5]:  # Limit to avoid context overflow
            trace = run.trace
            observations.append(f"Run {run.run_number}: {run.failure_description}")
            if trace.get("errors"):
                observations.append(f"  Errors: {trace['errors']}")
            if trace.get("tool_calls"):
                observations.append(f"  Tool calls: {trace['tool_calls']}")

        # First pass: failure analysis
        analysis_context = ReasoningContext(
            mode=ReasoningMode.FAILURE_ANALYSIS,
            observations=observations,
        )

        analysis_result = await self.llm.reason(analysis_context)
        analysis = analysis_result.structured_output

        try:
            # Validate structured output exists and is a dict
            if not isinstance(analysis, dict):
                logger.warning(
                    "LLM analysis output is not a dict, falling back to heuristic analysis"
                )
                return self._analyze_heuristic(description, runs, result)

            # Extract classification from LLM with safe access
            classification = analysis.get("classification", {})
            if not isinstance(classification, dict):
                logger.warning("LLM 'classification' is not a dict, using empty dict")
                classification = {}

            primary_class_str = safe_get(classification, "primary_class", default="reasoning")
            if not isinstance(primary_class_str, str):
                primary_class_str = "reasoning"
            primary_class_str = primary_class_str.lower()

            try:
                primary_class = FailureClass(primary_class_str)
            except ValueError:
                logger.warning(f"Invalid failure class '{primary_class_str}', using REASONING")
                primary_class = FailureClass.REASONING

            severity_str = safe_get(classification, "severity", default="S2")
            if not isinstance(severity_str, str):
                severity_str = "S2"
            try:
                severity = Severity[severity_str]
            except KeyError:
                logger.warning(f"Invalid severity '{severity_str}', using S2")
                severity = Severity.S2

            # Safely extract other fields
            analysis_text = analysis.get("analysis", "")
            if not isinstance(analysis_text, str):
                analysis_text = str(analysis_text) if analysis_text else ""

            contributing_factors = analysis.get("contributing_factors", [])
            if not isinstance(contributing_factors, list):
                logger.warning("LLM 'contributing_factors' is not a list, using empty list")
                contributing_factors = []

            key_insight = analysis.get("key_insight", "")
            if not isinstance(key_insight, str):
                key_insight = str(key_insight) if key_insight else ""

            # Second pass: root cause analysis
            rca_context = ReasoningContext(
                mode=ReasoningMode.ROOT_CAUSE_ANALYSIS,
                observations=observations + [f"Initial analysis: {analysis_text}"],
            )

            rca_result = await self.llm.reason(rca_context)
            rca = rca_result.structured_output

            # Validate RCA output
            if not isinstance(rca, dict):
                logger.warning("LLM RCA output is not a dict, using empty dict")
                rca = {}

            # Build failure object
            trigger_sig = self._extract_trigger_signature(runs)
            is_novel, parent_id = self._check_novelty_llm(primary_class, trigger_sig, description)

            # Safely get is_novel from classification
            is_novel_from_llm = classification.get("is_novel")
            if isinstance(is_novel_from_llm, bool):
                is_novel = is_novel_from_llm

            secondary_class = classification.get("secondary_class")
            if secondary_class is not None and not isinstance(secondary_class, str):
                secondary_class = str(secondary_class)

            failure = DiscoveredFailure(
                primary_class=primary_class,
                secondary_class=secondary_class,
                severity=severity,
                description=description,
                trigger_signature=trigger_sig,
                reproducibility=result.reproduction_rate,
                experiment_id=result.experiment_id,
                run_ids=[r.id for r in runs],
                classification_confidence=analysis_result.confidence,
                is_novel=is_novel,
                parent_failure_id=parent_id,
                llm_analysis=analysis_text,
                contributing_factors=contributing_factors,
                key_insight=key_insight,
                causal_analysis=rca,
            )

            return failure

        except Exception as e:
            logger.warning(
                f"Failed to parse LLM failure analysis output: {e}, falling back to heuristic analysis"
            )
            return self._analyze_heuristic(description, runs, result)

    def _analyze_heuristic(
        self, description: str, runs: list[RunResult], result: ExperimentResult
    ) -> DiscoveredFailure:
        """Fallback heuristic analysis without LLM."""
        # Classify using heuristic classifier
        classification = self.classifier.classify(
            output=description,
            context=self._build_classification_context(runs),
        )

        severity = self._assess_severity(classification, result)
        trigger_sig = self._extract_trigger_signature(runs)
        is_novel, parent_id = self._check_novelty(classification, trigger_sig)

        failure = DiscoveredFailure(
            primary_class=classification.primary_class,
            secondary_class=classification.secondary_class,
            severity=severity,
            description=description,
            trigger_signature=trigger_sig,
            reproducibility=result.reproduction_rate,
            experiment_id=result.experiment_id,
            run_ids=[r.id for r in runs],
            classification_confidence=classification.confidence,
            is_novel=is_novel,
            parent_failure_id=parent_id,
        )

        # Perform causal analysis
        combined_trace = self._combine_traces(runs)
        failure.causal_analysis = self.causal_linker.export_graph(
            self.causal_linker.analyze(failure.id, description, combined_trace).failure_id
        )

        return failure

    def _build_classification_context(self, runs: list[RunResult]) -> dict:
        """Build context for classification from runs."""
        context = {
            "run_count": len(runs),
            "errors": [],
            "tool_calls": 0,
        }

        for run in runs:
            trace = run.trace
            if trace.get("errors"):
                context["errors"].extend(trace["errors"])
            context["tool_calls"] += trace.get("tool_calls", 0)

        return context

    def _assess_severity(
        self, classification: ClassificationResult, result: ExperimentResult
    ) -> Severity:
        """Assess failure severity."""
        from ..taxonomy.failure_types import FAILURE_TAXONOMY

        info = FAILURE_TAXONOMY.get(classification.primary_class)
        base_severity = info.base_severity if info else Severity.S2

        # Adjust based on reproducibility
        if result.reproduction_rate >= 0.8:
            return Severity(min(base_severity.value + 1, 4))
        elif result.reproduction_rate <= 0.2:
            return Severity(max(base_severity.value - 1, 0))

        return base_severity

    def _extract_trigger_signature(self, runs: list[RunResult]) -> list[str]:
        """Extract trigger signature from failing runs."""
        signatures = set()

        for run in runs:
            trace = run.trace

            if trace.get("stress_type"):
                signatures.add(f"stress:{trace['stress_type']}")

            for error in trace.get("errors", []):
                error_key = str(error)[:50].replace(" ", "_")
                signatures.add(f"error:{error_key}")

            if trace.get("tool_calls", 0) > 3:
                signatures.add("high_tool_usage")

        return list(signatures)[:10]

    def _combine_traces(self, runs: list[RunResult]) -> dict:
        """Combine all traces for analysis."""
        combined = {
            "errors": [],
            "tool_calls": 0,
            "context_length": 0,
        }

        for run in runs:
            trace = run.trace
            combined["errors"].extend(trace.get("errors", []))
            combined["tool_calls"] += trace.get("tool_calls", 0)
            combined["context_length"] = max(
                combined["context_length"], trace.get("context_length", 0)
            )

        return combined

    def _check_novelty(
        self, classification: ClassificationResult, trigger_sig: list[str]
    ) -> tuple[bool, str | None]:
        """Check if failure is novel using graph."""
        if not self.graph:
            return True, None

        existing = self.graph.search(
            {"primary_class": classification.primary_class.value},
            node_type=None,
            limit=20,
        )

        for node in existing:
            if node.node_type.value != "failure_mode":
                continue

            existing_sig = node.data.get("trigger_signature", [])
            overlap = len(set(trigger_sig) & set(existing_sig))
            if overlap >= len(trigger_sig) * 0.5:
                return False, node.id

        return True, None

    def _check_novelty_llm(
        self, primary_class: FailureClass, trigger_sig: list[str], description: str
    ) -> tuple[bool, str | None]:
        """Check novelty - could use LLM for semantic similarity in future."""
        # For now, use heuristic check
        return self._check_novelty(ClassificationResult(primary_class=primary_class), trigger_sig)

    def _merge_similar(self, failures: list[DiscoveredFailure]) -> list[DiscoveredFailure]:
        """Merge similar failures discovered in same batch."""
        if len(failures) <= 1:
            return failures

        merged = []
        used = set()

        for i, f1 in enumerate(failures):
            if i in used:
                continue

            similar = [f1]
            for j, f2 in enumerate(failures[i + 1 :], i + 1):
                if j in used:
                    continue
                if self._are_similar(f1, f2):
                    similar.append(f2)
                    used.add(j)

            if len(similar) > 1:
                merged.append(self._merge_failures(similar))
            else:
                merged.append(f1)
            used.add(i)

        return merged

    def _are_similar(self, f1: DiscoveredFailure, f2: DiscoveredFailure) -> bool:
        """Check if two failures are similar enough to merge."""
        if f1.primary_class != f2.primary_class:
            return False

        sig_overlap = len(set(f1.trigger_signature) & set(f2.trigger_signature))
        min_sig = min(len(f1.trigger_signature), len(f2.trigger_signature))

        if min_sig > 0 and sig_overlap / min_sig >= 0.5:
            return True

        return False

    def _merge_failures(self, failures: list[DiscoveredFailure]) -> DiscoveredFailure:
        """Merge multiple similar failures into one."""
        primary = failures[0]

        all_sigs = set()
        for f in failures:
            all_sigs.update(f.trigger_signature)

        avg_repro = sum(f.reproducibility for f in failures) / len(failures)

        all_runs = []
        for f in failures:
            all_runs.extend(f.run_ids)

        # Use best analysis
        best_analysis = max(failures, key=lambda f: len(f.llm_analysis))

        return DiscoveredFailure(
            primary_class=primary.primary_class,
            secondary_class=primary.secondary_class,
            severity=max(f.severity for f in failures),
            description=primary.description,
            trigger_signature=list(all_sigs)[:10],
            reproducibility=avg_repro,
            experiment_id=primary.experiment_id,
            run_ids=all_runs,
            classification_confidence=max(f.classification_confidence for f in failures),
            is_novel=primary.is_novel,
            parent_failure_id=primary.parent_failure_id,
            llm_analysis=best_analysis.llm_analysis,
            contributing_factors=best_analysis.contributing_factors,
            key_insight=best_analysis.key_insight,
            causal_analysis=primary.causal_analysis,
        )

    def _record_failure(self, failure: DiscoveredFailure, context: AgentContext) -> None:
        """Record failure to memory graph."""
        if not self.graph:
            return

        run_id = failure.run_ids[0] if failure.run_ids else failure.experiment_id
        self.graph.record_failure(
            run_id=run_id,
            primary_class=failure.primary_class.value,
            secondary_class=failure.secondary_class or "",
            severity=failure.severity.name,
            trigger_signature=failure.trigger_signature,
            reproducibility=failure.reproducibility,
            parent_failure_id=failure.parent_failure_id,
            description=failure.description,
            is_novel=failure.is_novel,
            key_insight=failure.key_insight,
            contributing_factors=failure.contributing_factors,
            llm_analysis=failure.llm_analysis,
            causal_analysis=failure.causal_analysis,
        )

    def _failure_to_dict(self, failure: DiscoveredFailure) -> dict:
        """Convert failure to dictionary."""
        return {
            "id": failure.id,
            "primary_class": failure.primary_class.value,
            "secondary_class": failure.secondary_class,
            "severity": failure.severity.name,
            "description": failure.description,
            "trigger_signature": failure.trigger_signature,
            "reproducibility": failure.reproducibility,
            "is_novel": failure.is_novel,
            "classification_confidence": failure.classification_confidence,
            "llm_analysis": failure.llm_analysis,
            "contributing_factors": failure.contributing_factors,
            "key_insight": failure.key_insight,
        }
