"""Hypothesis Engine - generates failure hypotheses using LLM reasoning."""

from dataclasses import dataclass, field
from typing import Any

from ..memory.graph import MemoryGraph
from ..reasoning.adaptive_memory import AdaptiveMemory
from ..reasoning.llm_backbone import LLMBackbone, ReasoningContext, ReasoningMode
from ..taxonomy.failure_types import FAILURE_TAXONOMY, FailureClass
from ..utils import generate_id, get_logger
from .base import AgentContext, AgentResult, BaseAgent

logger = get_logger("hypothesis_engine")


def safe_get(data: dict, *keys, default=None):
    """Safely get nested dictionary values."""
    for key in keys:
        if isinstance(data, dict):
            data = data.get(key, default)
        else:
            return default
    return data


@dataclass
class Hypothesis:
    """A hypothesis about potential failure modes."""

    id: str = field(default_factory=generate_id)
    target_surface: str = ""  # What we're testing
    expected_failure: str = ""  # What failure we expect
    failure_class: FailureClass = FailureClass.REASONING
    confidence: float = 0.5  # 0-1 confidence in hypothesis
    priority: str = "medium"  # low, medium, high, critical
    rationale: str = ""
    suggested_experiment: str = ""
    evidence: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


class HypothesisEngine(BaseAgent):
    """
    Generates hypotheses about potential failure modes using LLM reasoning.

    This is not template-driven - it uses genuine reasoning to:
    - Analyze past failures and find patterns
    - Identify unexplored attack surfaces
    - Generate novel hypotheses based on observations
    - Prioritize based on learned priors

    Sources of hypotheses:
    1. LLM reasoning about observations
    2. Prior failures - patterns from past discoveries
    3. Adaptive memory - what has worked before
    4. Attack surface analysis - systematic enumeration
    """

    def __init__(
        self,
        graph: MemoryGraph | None = None,
        llm_backbone: LLMBackbone | None = None,
        adaptive_memory: AdaptiveMemory | None = None,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.graph = graph
        self.llm = llm_backbone
        self.adaptive_memory = adaptive_memory

    @property
    def agent_type(self) -> str:
        return "hypothesis_engine"

    async def execute(self, context: AgentContext, **kwargs) -> AgentResult:
        """Generate hypotheses based on available information."""
        hypotheses = []

        # Gather observations for LLM reasoning
        observations = self._gather_observations()

        # If we have an LLM backbone, use it for intelligent hypothesis generation
        if self.llm:
            llm_hypotheses = await self._generate_with_llm(observations)
            if llm_hypotheses:
                hypotheses.extend(llm_hypotheses)
            else:
                # Fallback to template-based generation if LLM output is empty/unparseable
                hypotheses.extend(self._hypotheses_from_attack_surface())
                hypotheses.extend(self._hypotheses_from_taxonomy())
        else:
            # Fallback to template-based generation
            hypotheses.extend(self._hypotheses_from_attack_surface())
            hypotheses.extend(self._hypotheses_from_taxonomy())

        # Generate from prior failures (always useful)
        if self.graph:
            prior_hypotheses = self._hypotheses_from_prior_failures()
            hypotheses.extend(prior_hypotheses)

        # Apply adaptive memory priors
        if self.adaptive_memory:
            hypotheses = self._apply_priors(hypotheses)

        # Deduplicate and prioritize
        hypotheses = self._deduplicate(hypotheses)
        hypotheses = self._prioritize(hypotheses)

        # Record to memory graph if available
        if self.graph:
            model_meta = self._model_metadata()
            for h in hypotheses:
                self.graph.record_hypothesis(
                    target_surface=h.target_surface,
                    expected_failure=h.expected_failure,
                    confidence=h.confidence,
                    priority=h.priority,
                    hypothesis_id=h.id,
                    failure_class=h.failure_class.value,
                    rationale=h.rationale,
                    suggested_experiment=h.suggested_experiment,
                    evidence=h.evidence,
                    **model_meta,
                )

        return AgentResult(
            agent_id=self.id,
            agent_type=self.agent_type,
            success=True,
            data={
                "hypothesis_count": len(hypotheses),
                "hypotheses": [self._hypothesis_to_dict(h) for h in hypotheses],
                "used_llm_reasoning": self.llm is not None,
            },
        )

    def _model_metadata(self) -> dict[str, Any]:
        """Return model metadata if available."""
        if not self.llm or not getattr(self.llm, "client", None):
            return {}
        client = self.llm.client
        return {
            "model_provider": client.provider,
            "model_name": client.default_model,
        }

    def _gather_observations(self) -> list[dict[str, Any]]:
        """Gather observations for LLM reasoning."""
        observations = []

        if self.graph:
            # Recent failures
            failures = self.graph.get_failures(valid_only=True, limit=20)
            for f in failures:
                observations.append(
                    {
                        "type": "failure",
                        "description": f"Observed {f.data.get('severity', 'S2')} {f.data.get('primary_class', 'unknown')} failure with trigger {f.data.get('trigger_signature', [])}",
                        "data": f.data,
                    }
                )

            # Recent experiments
            experiments = self.graph.get_experiments(valid_only=True, limit=10)
            for e in experiments:
                observations.append(
                    {
                        "type": "experiment",
                        "description": f"Ran {e.data.get('stress_type', 'unknown')} experiment targeting {e.data.get('hypothesis_id', 'unknown')}",
                        "data": e.data,
                    }
                )

        # Add adaptive memory context
        if self.adaptive_memory:
            memory_context = self.adaptive_memory.get_context_for_reasoning()
            for suggestion in memory_context.get("research_suggestions", []):
                observations.append(
                    {
                        "type": "suggestion",
                        "description": suggestion,
                    }
                )

        return observations

    async def _generate_with_llm(self, observations: list[dict]) -> list[Hypothesis]:
        """Generate hypotheses using LLM reasoning."""
        hypotheses = []

        # Build reasoning context
        prior_knowledge = []
        if self.adaptive_memory:
            for belief in self.adaptive_memory.get_strong_beliefs():
                prior_knowledge.append(f"Belief (strength {belief.strength:.0%}): {belief.belief}")

        reasoning_context = ReasoningContext(
            mode=ReasoningMode.HYPOTHESIS_GENERATION,
            observations=observations,
            prior_knowledge=prior_knowledge,
            focus_areas=[
                "novel failure modes we haven't tested",
                "variations of known failures",
                "adversarial attack vectors",
                "edge cases in tool use",
                "context window limitations",
            ],
        )

        # Call LLM
        result = await self.llm.reason(reasoning_context)

        # Parse hypotheses from structured output with validation
        output = result.structured_output

        try:
            # Validate structured output exists and is a dict
            if not isinstance(output, dict):
                logger.warning("LLM output is not a dict, returning empty hypotheses list")
                return hypotheses

            llm_hypotheses = output.get("hypotheses", [])
            if not isinstance(llm_hypotheses, list):
                logger.warning(
                    "LLM output 'hypotheses' is not a list, returning empty hypotheses list"
                )
                return hypotheses

            if not llm_hypotheses:
                logger.warning("LLM output 'hypotheses' is empty, returning empty hypotheses list")
                return hypotheses

            for h_data in llm_hypotheses:
                # Validate each hypothesis entry is a dict
                if not isinstance(h_data, dict):
                    logger.warning(f"Skipping non-dict hypothesis entry: {type(h_data)}")
                    continue

                # Map to failure class with safe access
                target = h_data.get("target_surface", "general")
                if not isinstance(target, str):
                    target = "general"

                expected_failure = h_data.get("expected_failure", "")
                if not isinstance(expected_failure, str):
                    expected_failure = ""

                failure_class = self._infer_failure_class(target, expected_failure)

                # Safely parse confidence
                raw_confidence = h_data.get("confidence", 0.5)
                try:
                    confidence = float(raw_confidence)
                    # Clamp to valid range
                    confidence = max(0.0, min(1.0, confidence))
                except (ValueError, TypeError):
                    logger.warning(f"Invalid confidence value '{raw_confidence}', using 0.5")
                    confidence = 0.5

                rationale = h_data.get("rationale", "")
                if not isinstance(rationale, str):
                    rationale = str(rationale) if rationale else ""

                suggested_experiment = h_data.get("suggested_experiment", "")
                if not isinstance(suggested_experiment, str):
                    suggested_experiment = str(suggested_experiment) if suggested_experiment else ""

                hypothesis = Hypothesis(
                    target_surface=target,
                    expected_failure=expected_failure,
                    failure_class=failure_class,
                    confidence=confidence,
                    priority=self._infer_priority(confidence),
                    rationale=rationale,
                    suggested_experiment=suggested_experiment,
                    evidence=["LLM reasoning"],
                )
                hypotheses.append(hypothesis)

        except Exception as e:
            logger.warning(f"Failed to parse LLM hypothesis output: {e}, returning partial results")

        logger.info(f"LLM generated {len(hypotheses)} hypotheses")

        return hypotheses

    def _infer_failure_class(self, target: str, expected_failure: str) -> FailureClass:
        """Infer failure class from target and expected failure."""
        combined = f"{target} {expected_failure}".lower()

        if any(word in combined for word in ["tool", "parameter", "api", "call"]):
            return FailureClass.TOOL_USE
        if any(word in combined for word in ["context", "long", "attention", "memory"]):
            return FailureClass.LONG_CONTEXT
        if any(word in combined for word in ["loop", "recursive", "amplif", "feedback"]):
            return FailureClass.FEEDBACK_LOOP
        if any(word in combined for word in ["deploy", "scale", "resource", "infra"]):
            return FailureClass.DEPLOYMENT
        return FailureClass.REASONING

    def _infer_priority(self, confidence: float) -> str:
        """Infer priority from confidence."""
        if confidence >= 0.8:
            return "high"
        if confidence >= 0.5:
            return "medium"
        return "low"

    def _apply_priors(self, hypotheses: list[Hypothesis]) -> list[Hypothesis]:
        """Apply adaptive memory priors to adjust confidence."""
        for h in hypotheses:
            prior = self.adaptive_memory.get_hypothesis_prior(
                h.failure_class.value, h.target_surface
            )

            # Bayesian-style update
            h.confidence = 0.6 * h.confidence + 0.4 * prior

            # Adjust priority based on updated confidence
            h.priority = self._infer_priority(h.confidence)

        return hypotheses

    def _hypotheses_from_prior_failures(self) -> list[Hypothesis]:
        """Generate hypotheses from past failure patterns."""
        hypotheses = []

        if not self.graph:
            return hypotheses

        # Get recent failures
        failures = self.graph.get_failures(valid_only=True, limit=50)

        for failure in failures:
            data = failure.data

            # If failure was resolved, hypothesize it might recur
            if data.get("is_resolved"):
                hypotheses.append(
                    Hypothesis(
                        target_surface=data.get("trigger_signature", ["unknown"])[0]
                        if data.get("trigger_signature")
                        else "unknown",
                        expected_failure=f"Recurrence of {data.get('primary_class', 'unknown')} failure",
                        failure_class=FailureClass(data.get("primary_class", "reasoning")),
                        confidence=0.3,
                        priority="medium",
                        rationale="Previously resolved failures may recur",
                        evidence=[f"Prior failure: {failure.id}"],
                    )
                )

            # Hypothesize related failures
            secondary = data.get("secondary_class")
            if secondary:
                hypotheses.append(
                    Hypothesis(
                        target_surface=data.get("trigger_signature", ["unknown"])[0]
                        if data.get("trigger_signature")
                        else "unknown",
                        expected_failure=f"Related {secondary} failure",
                        failure_class=FailureClass(data.get("primary_class", "reasoning")),
                        confidence=0.4,
                        priority="medium",
                        rationale="Related failure modes often co-occur",
                        evidence=[f"Related to: {failure.id}"],
                    )
                )

        return hypotheses

    def _hypotheses_from_attack_surface(self) -> list[Hypothesis]:
        """Generate hypotheses from systematic attack surface analysis."""
        hypotheses = []

        # Standard attack surfaces for LLM agents
        surfaces = [
            ("tool_use", "Tool parameter injection", FailureClass.TOOL_USE),
            ("tool_use", "Tool result manipulation", FailureClass.TOOL_USE),
            ("context_window", "Context overflow", FailureClass.LONG_CONTEXT),
            ("context_window", "Attention dilution", FailureClass.LONG_CONTEXT),
            ("reasoning_chain", "Logical inconsistency", FailureClass.REASONING),
            ("reasoning_chain", "Goal drift", FailureClass.REASONING),
            ("feedback_loop", "Output as input attack", FailureClass.FEEDBACK_LOOP),
            ("feedback_loop", "Amplification cascade", FailureClass.FEEDBACK_LOOP),
            ("deployment", "State desync", FailureClass.DEPLOYMENT),
            ("deployment", "Resource exhaustion", FailureClass.DEPLOYMENT),
        ]

        for surface, expected, failure_class in surfaces:
            hypotheses.append(
                Hypothesis(
                    target_surface=surface,
                    expected_failure=expected,
                    failure_class=failure_class,
                    confidence=0.5,
                    priority="medium",
                    rationale="Standard attack surface enumeration",
                    evidence=["Systematic surface analysis"],
                )
            )

        return hypotheses

    def _hypotheses_from_taxonomy(self) -> list[Hypothesis]:
        """Generate hypotheses from failure taxonomy."""
        hypotheses = []

        for class_name, info in FAILURE_TAXONOMY.items():
            # Generate hypothesis for each failure type
            hypotheses.append(
                Hypothesis(
                    target_surface=info.typical_triggers[0] if info.typical_triggers else "general",
                    expected_failure=info.description[:100],
                    failure_class=class_name,
                    confidence=0.4,
                    priority="medium" if info.base_severity.value <= 2 else "high",
                    rationale="Derived from failure taxonomy",
                    evidence=[f"Taxonomy: {class_name.value}"],
                )
            )

        return hypotheses

    def _deduplicate(self, hypotheses: list[Hypothesis]) -> list[Hypothesis]:
        """Remove duplicate hypotheses."""
        seen = set()
        unique = []

        for h in hypotheses:
            key = (h.target_surface, h.expected_failure)
            if key not in seen:
                seen.add(key)
                unique.append(h)

        return unique

    def _prioritize(self, hypotheses: list[Hypothesis]) -> list[Hypothesis]:
        """Sort hypotheses by priority and confidence."""
        priority_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        return sorted(
            hypotheses,
            key=lambda h: (priority_order.get(h.priority, 2), -h.confidence),
        )

    def _hypothesis_to_dict(self, h: Hypothesis) -> dict:
        """Convert hypothesis to dictionary."""
        return {
            "id": h.id,
            "target_surface": h.target_surface,
            "expected_failure": h.expected_failure,
            "failure_class": h.failure_class.value,
            "confidence": h.confidence,
            "priority": h.priority,
            "rationale": h.rationale,
            "suggested_experiment": h.suggested_experiment,
        }
