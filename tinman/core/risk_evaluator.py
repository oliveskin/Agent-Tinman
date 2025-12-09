"""Risk evaluation for actions and interventions."""

from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional

from ..config import Mode
from ..utils import get_logger

logger = get_logger("risk_evaluator")


class RiskTier(str, Enum):
    """Three-tier risk classification."""
    SAFE = "safe"      # Proceed autonomously
    REVIEW = "review"  # Needs human review
    BLOCK = "block"    # Cannot proceed


class Severity(str, Enum):
    """Failure/action severity levels (S0-S4)."""
    S0 = "S0"  # Benign
    S1 = "S1"  # UX degradation
    S2 = "S2"  # Business risk
    S3 = "S3"  # Serious risk
    S4 = "S4"  # Critical/catastrophic

    @property
    def numeric(self) -> float:
        """Get numeric value for comparisons."""
        return {"S0": 0.0, "S1": 0.25, "S2": 0.5, "S3": 0.75, "S4": 1.0}[self.value]

    def __lt__(self, other: "Severity") -> bool:
        return self.numeric < other.numeric

    def __le__(self, other: "Severity") -> bool:
        return self.numeric <= other.numeric

    def __gt__(self, other: "Severity") -> bool:
        return self.numeric > other.numeric

    def __ge__(self, other: "Severity") -> bool:
        return self.numeric >= other.numeric


class ActionType(str, Enum):
    """Types of actions that can be risk-evaluated."""
    PROMPT_MUTATION = "prompt_mutation"
    TOOL_POLICY_CHANGE = "tool_policy_change"
    MEMORY_GATING = "memory_gating"
    FINE_TUNE = "fine_tune"
    CONFIG_CHANGE = "config_change"
    DESTRUCTIVE_TOOL_CALL = "destructive_tool_call"
    SAFETY_FILTER_CHANGE = "safety_filter_change"


@dataclass
class Action:
    """An action to be risk-evaluated."""
    action_type: ActionType
    target_surface: str  # lab, shadow, production
    payload: dict[str, Any]
    predicted_severity: Severity = Severity.S0
    estimated_cost: float = 0.0
    estimated_latency_ms: int = 0
    affects_safety_filters: bool = False
    is_reversible: bool = True


@dataclass
class RiskAssessment:
    """Result of risk evaluation."""
    tier: RiskTier
    severity: Severity
    reasoning: str
    requires_approval: bool
    auto_approve: bool
    details: dict[str, Any]


class RiskEvaluator:
    """
    Evaluates risk of actions and determines appropriate tier.

    Simple 3-tier model:
    - SAFE: Low risk, proceed autonomously
    - REVIEW: Medium risk, needs human review
    - BLOCK: High risk, cannot proceed

    Optional detailed mode provides S0-S4 severity scoring.
    """

    # Actions that are always blocked
    BLOCKED_ACTIONS = {
        ActionType.DESTRUCTIVE_TOOL_CALL,
    }

    # Actions that always require review in production
    REVIEW_REQUIRED_IN_PROD = {
        ActionType.PROMPT_MUTATION,
        ActionType.TOOL_POLICY_CHANGE,
        ActionType.SAFETY_FILTER_CHANGE,
        ActionType.FINE_TUNE,
    }

    def __init__(self, detailed_mode: bool = False,
                 auto_approve_safe: bool = True,
                 block_on_destructive: bool = True):
        self.detailed_mode = detailed_mode
        self.auto_approve_safe = auto_approve_safe
        self.block_on_destructive = block_on_destructive

    def evaluate(self, action: Action, mode: Mode) -> RiskAssessment:
        """
        Evaluate risk of an action given the current operating mode.

        Returns RiskAssessment with tier, severity, and reasoning.
        """
        # Hard blocks (always)
        if self.block_on_destructive and action.action_type in self.BLOCKED_ACTIONS:
            return RiskAssessment(
                tier=RiskTier.BLOCK,
                severity=Severity.S4,
                reasoning=f"Action type {action.action_type.value} is blocked",
                requires_approval=False,
                auto_approve=False,
                details={"blocked_by": "action_type_blocklist"},
            )

        # Safety filter changes are always S4
        if action.affects_safety_filters:
            return RiskAssessment(
                tier=RiskTier.BLOCK,
                severity=Severity.S4,
                reasoning="Actions affecting safety filters are blocked",
                requires_approval=False,
                auto_approve=False,
                details={"blocked_by": "safety_filter_protection"},
            )

        # Lab mode: almost everything is safe
        if mode == Mode.LAB:
            return self._evaluate_lab_mode(action)

        # Shadow mode: moderate restrictions
        if mode == Mode.SHADOW:
            return self._evaluate_shadow_mode(action)

        # Production mode: strict restrictions
        return self._evaluate_production_mode(action)

    def _evaluate_lab_mode(self, action: Action) -> RiskAssessment:
        """Lab mode: full autonomy except hard blocks."""
        severity = action.predicted_severity

        return RiskAssessment(
            tier=RiskTier.SAFE,
            severity=severity,
            reasoning="Lab mode allows autonomous execution",
            requires_approval=False,
            auto_approve=self.auto_approve_safe,
            details={"mode": "lab"},
        )

    def _evaluate_shadow_mode(self, action: Action) -> RiskAssessment:
        """Shadow mode: review high-severity actions."""
        severity = action.predicted_severity

        if severity >= Severity.S3:
            return RiskAssessment(
                tier=RiskTier.REVIEW,
                severity=severity,
                reasoning=f"Severity {severity.value} requires review in shadow mode",
                requires_approval=True,
                auto_approve=False,
                details={"mode": "shadow", "triggered_by": "severity"},
            )

        return RiskAssessment(
            tier=RiskTier.SAFE,
            severity=severity,
            reasoning="Shadow mode allows autonomous execution for low severity",
            requires_approval=False,
            auto_approve=self.auto_approve_safe,
            details={"mode": "shadow"},
        )

    def _evaluate_production_mode(self, action: Action) -> RiskAssessment:
        """Production mode: strict risk gating."""
        severity = action.predicted_severity

        # S3/S4 are blocked in production
        if severity >= Severity.S3:
            tier = RiskTier.BLOCK if severity == Severity.S4 else RiskTier.REVIEW
            return RiskAssessment(
                tier=tier,
                severity=severity,
                reasoning=f"Severity {severity.value} is {'blocked' if tier == RiskTier.BLOCK else 'requires review'} in production",
                requires_approval=tier == RiskTier.REVIEW,
                auto_approve=False,
                details={"mode": "production", "triggered_by": "severity"},
            )

        # Certain action types always need review in prod
        if action.action_type in self.REVIEW_REQUIRED_IN_PROD:
            return RiskAssessment(
                tier=RiskTier.REVIEW,
                severity=severity,
                reasoning=f"Action type {action.action_type.value} requires review in production",
                requires_approval=True,
                auto_approve=False,
                details={"mode": "production", "triggered_by": "action_type"},
            )

        # S2 needs review in production
        if severity == Severity.S2:
            return RiskAssessment(
                tier=RiskTier.REVIEW,
                severity=severity,
                reasoning="S2 severity requires review in production",
                requires_approval=True,
                auto_approve=False,
                details={"mode": "production", "triggered_by": "severity"},
            )

        # S0/S1 are safe in production
        return RiskAssessment(
            tier=RiskTier.SAFE,
            severity=severity,
            reasoning="Low severity action in production",
            requires_approval=False,
            auto_approve=self.auto_approve_safe,
            details={"mode": "production"},
        )

    def compute_severity(self,
                         failure_class: str,
                         reproducibility: float,
                         impact_scope: list[str],
                         is_safety_related: bool) -> Severity:
        """
        Compute severity based on failure characteristics.

        Used when detailed_mode is enabled.
        """
        score = 0.0

        # Safety-related failures are automatically higher severity
        if is_safety_related:
            score += 0.5

        # Reproducibility increases severity (consistent failures are worse)
        score += reproducibility * 0.2

        # Impact scope affects severity
        if len(impact_scope) > 3:
            score += 0.2
        elif len(impact_scope) > 1:
            score += 0.1

        # Certain failure classes are inherently higher severity
        high_severity_classes = {
            "DESTRUCTIVE_CALL", "SAFETY_REGRESSION", "MEMORY_POISONING",
            "REWARD_HACKING", "TOOL_HALLUCINATION"
        }
        if failure_class.upper() in high_severity_classes:
            score += 0.3

        # Map score to severity
        if score >= 0.8:
            return Severity.S4
        elif score >= 0.6:
            return Severity.S3
        elif score >= 0.4:
            return Severity.S2
        elif score >= 0.2:
            return Severity.S1
        else:
            return Severity.S0
