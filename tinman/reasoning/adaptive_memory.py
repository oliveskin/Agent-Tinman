"""Adaptive Memory - learns from discoveries to improve over time."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional
from collections import defaultdict

from ..utils import generate_id, utc_now, get_logger

logger = get_logger("adaptive_memory")


@dataclass
class LearnedPattern:
    """A pattern learned from research."""
    id: str = field(default_factory=generate_id)
    pattern_type: str = ""  # hypothesis, failure, intervention
    description: str = ""
    confidence: float = 0.5
    evidence_count: int = 1
    success_rate: float = 0.0  # For hypotheses/interventions
    created_at: datetime = field(default_factory=utc_now)
    last_seen: datetime = field(default_factory=utc_now)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class PriorBelief:
    """A belief about model behavior that informs hypothesis generation."""
    id: str = field(default_factory=generate_id)
    belief: str = ""
    strength: float = 0.5  # 0-1, how strongly held
    evidence_for: list[str] = field(default_factory=list)
    evidence_against: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)


class AdaptiveMemory:
    """
    Learns from research to improve Tinman's effectiveness over time.

    This is what makes Tinman get smarter, not just run the same
    templates repeatedly. It tracks:

    - Which hypotheses turned out to be true
    - Which intervention types work for which failures
    - Patterns that recur across experiments
    - Beliefs about model behavior that should inform future research
    """

    def __init__(self):
        self._patterns: dict[str, LearnedPattern] = {}
        self._beliefs: dict[str, PriorBelief] = {}

        # Track success rates by category
        self._hypothesis_outcomes: dict[str, list[bool]] = defaultdict(list)
        self._intervention_outcomes: dict[str, list[bool]] = defaultdict(list)

        # Track failure patterns
        self._failure_signatures: dict[str, int] = defaultdict(int)
        self._failure_cooccurrence: dict[tuple[str, str], int] = defaultdict(int)

    def record_hypothesis_outcome(self,
                                   hypothesis_type: str,
                                   target_surface: str,
                                   validated: bool,
                                   confidence: float) -> None:
        """Record whether a hypothesis was validated."""
        key = f"{hypothesis_type}:{target_surface}"
        self._hypothesis_outcomes[key].append(validated)

        # Update or create pattern
        if key in self._patterns:
            pattern = self._patterns[key]
            pattern.evidence_count += 1
            pattern.last_seen = utc_now()
            # Update success rate with exponential moving average
            pattern.success_rate = 0.7 * pattern.success_rate + 0.3 * (1.0 if validated else 0.0)
            pattern.confidence = min(0.95, pattern.confidence + 0.05 * (1.0 if validated else -0.5))
        else:
            self._patterns[key] = LearnedPattern(
                pattern_type="hypothesis",
                description=f"Hypothesis about {target_surface}",
                confidence=confidence,
                success_rate=1.0 if validated else 0.0,
            )

        logger.info(f"Recorded hypothesis outcome: {key} = {validated}")

    def record_intervention_outcome(self,
                                     intervention_type: str,
                                     failure_class: str,
                                     effective: bool) -> None:
        """Record whether an intervention was effective."""
        key = f"{intervention_type}:{failure_class}"
        self._intervention_outcomes[key].append(effective)

        # Update pattern
        if key in self._patterns:
            pattern = self._patterns[key]
            pattern.evidence_count += 1
            pattern.last_seen = utc_now()
            pattern.success_rate = 0.7 * pattern.success_rate + 0.3 * (1.0 if effective else 0.0)
        else:
            self._patterns[key] = LearnedPattern(
                pattern_type="intervention",
                description=f"{intervention_type} for {failure_class}",
                success_rate=1.0 if effective else 0.0,
            )

        logger.info(f"Recorded intervention outcome: {key} = {effective}")

    def record_failure_signature(self, signature: list[str]) -> None:
        """Record a failure signature to track patterns."""
        sig_key = ":".join(sorted(signature))
        self._failure_signatures[sig_key] += 1

        # Track co-occurrence
        for i, s1 in enumerate(signature):
            for s2 in signature[i+1:]:
                pair = tuple(sorted([s1, s2]))
                self._failure_cooccurrence[pair] += 1

    def update_belief(self,
                      belief_text: str,
                      evidence: str,
                      supports: bool) -> PriorBelief:
        """Update a belief based on new evidence."""
        # Find existing belief or create new
        belief_key = belief_text[:100]  # Use truncated text as key

        if belief_key in self._beliefs:
            belief = self._beliefs[belief_key]
        else:
            belief = PriorBelief(belief=belief_text)
            self._beliefs[belief_key] = belief

        # Update evidence
        if supports:
            belief.evidence_for.append(evidence)
            belief.strength = min(0.95, belief.strength + 0.1)
        else:
            belief.evidence_against.append(evidence)
            belief.strength = max(0.05, belief.strength - 0.1)

        belief.updated_at = utc_now()

        return belief

    def get_hypothesis_prior(self, hypothesis_type: str, target_surface: str) -> float:
        """Get prior probability for a hypothesis based on past experience."""
        key = f"{hypothesis_type}:{target_surface}"

        if key in self._patterns:
            return self._patterns[key].success_rate

        # Check for partial matches
        for pattern_key, pattern in self._patterns.items():
            if hypothesis_type in pattern_key or target_surface in pattern_key:
                return pattern.success_rate * 0.8  # Discount for partial match

        return 0.5  # No prior information

    def get_intervention_prior(self, intervention_type: str, failure_class: str) -> float:
        """Get prior probability for intervention effectiveness."""
        key = f"{intervention_type}:{failure_class}"

        if key in self._patterns:
            return self._patterns[key].success_rate

        # Check if this intervention type has worked for other failures
        type_outcomes = [
            outcomes for key, outcomes in self._intervention_outcomes.items()
            if key.startswith(f"{intervention_type}:")
        ]

        if type_outcomes:
            flat_outcomes = [o for outcomes in type_outcomes for o in outcomes]
            return sum(flat_outcomes) / len(flat_outcomes)

        return 0.5

    def get_likely_failure_patterns(self, top_k: int = 5) -> list[tuple[str, int]]:
        """Get most common failure patterns."""
        sorted_patterns = sorted(
            self._failure_signatures.items(),
            key=lambda x: x[1],
            reverse=True
        )
        return sorted_patterns[:top_k]

    def get_correlated_failures(self, failure_sig: str, min_cooccurrence: int = 2) -> list[str]:
        """Get failures that often co-occur with the given signature."""
        correlated = []

        for (s1, s2), count in self._failure_cooccurrence.items():
            if count >= min_cooccurrence:
                if s1 == failure_sig:
                    correlated.append(s2)
                elif s2 == failure_sig:
                    correlated.append(s1)

        return correlated

    def get_strong_beliefs(self, min_strength: float = 0.7) -> list[PriorBelief]:
        """Get beliefs held with high confidence."""
        return [
            b for b in self._beliefs.values()
            if b.strength >= min_strength
        ]

    def get_research_suggestions(self) -> list[str]:
        """Generate research suggestions based on learned patterns."""
        suggestions = []

        # Suggest investigating successful hypothesis patterns
        high_success_hypotheses = [
            p for p in self._patterns.values()
            if p.pattern_type == "hypothesis" and p.success_rate > 0.7 and p.evidence_count >= 3
        ]

        for pattern in high_success_hypotheses[:3]:
            suggestions.append(
                f"Continue investigating: {pattern.description} "
                f"(success rate: {pattern.success_rate:.0%})"
            )

        # Suggest trying effective interventions elsewhere
        high_success_interventions = [
            p for p in self._patterns.values()
            if p.pattern_type == "intervention" and p.success_rate > 0.6
        ]

        for pattern in high_success_interventions[:3]:
            suggestions.append(
                f"Consider applying: {pattern.description} to other failures"
            )

        # Suggest investigating common failure patterns
        common_failures = self.get_likely_failure_patterns(3)
        for sig, count in common_failures:
            if count >= 3:
                suggestions.append(
                    f"Investigate recurring failure pattern: {sig} ({count} occurrences)"
                )

        # Suggest revisiting uncertain beliefs
        uncertain_beliefs = [
            b for b in self._beliefs.values()
            if 0.3 < b.strength < 0.7 and len(b.evidence_for) + len(b.evidence_against) >= 2
        ]

        for belief in uncertain_beliefs[:2]:
            suggestions.append(
                f"Gather more evidence on: {belief.belief[:100]}"
            )

        return suggestions

    def get_context_for_reasoning(self) -> dict[str, Any]:
        """Get adaptive memory context to inform reasoning."""
        return {
            "strong_beliefs": [
                {"belief": b.belief, "strength": b.strength}
                for b in self.get_strong_beliefs()
            ],
            "successful_patterns": [
                {"description": p.description, "success_rate": p.success_rate}
                for p in self._patterns.values()
                if p.success_rate > 0.6 and p.evidence_count >= 2
            ],
            "common_failures": [
                {"signature": sig, "count": count}
                for sig, count in self.get_likely_failure_patterns(5)
            ],
            "research_suggestions": self.get_research_suggestions()[:5],
        }

    def export(self) -> dict[str, Any]:
        """Export adaptive memory state."""
        return {
            "patterns": {
                k: {
                    "pattern_type": p.pattern_type,
                    "description": p.description,
                    "confidence": p.confidence,
                    "evidence_count": p.evidence_count,
                    "success_rate": p.success_rate,
                }
                for k, p in self._patterns.items()
            },
            "beliefs": {
                k: {
                    "belief": b.belief,
                    "strength": b.strength,
                    "evidence_for_count": len(b.evidence_for),
                    "evidence_against_count": len(b.evidence_against),
                }
                for k, b in self._beliefs.items()
            },
            "failure_signatures": dict(self._failure_signatures),
        }

    def import_state(self, state: dict[str, Any]) -> None:
        """Import adaptive memory state."""
        for k, p_data in state.get("patterns", {}).items():
            self._patterns[k] = LearnedPattern(
                pattern_type=p_data["pattern_type"],
                description=p_data["description"],
                confidence=p_data["confidence"],
                evidence_count=p_data["evidence_count"],
                success_rate=p_data["success_rate"],
            )

        for k, b_data in state.get("beliefs", {}).items():
            self._beliefs[k] = PriorBelief(
                belief=b_data["belief"],
                strength=b_data["strength"],
            )

        for sig, count in state.get("failure_signatures", {}).items():
            self._failure_signatures[sig] = count
