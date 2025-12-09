"""Policy-driven risk matrix configuration.

This module provides YAML-configurable risk policies that determine
how actions are evaluated across different modes and severity levels.

The risk policy is the central configuration for safety behavior:
- What tier (SAFE/REVIEW/BLOCK) applies for each (mode, severity) pair
- Action type overrides (e.g., destructive calls always blocked)
- Cost thresholds for auto-approval
- Mode-specific behaviors
"""

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional
import os
import yaml

from .risk_evaluator import RiskTier, Severity, ActionType, Action, RiskAssessment
from ..config.modes import Mode
from ..utils import get_logger

logger = get_logger("risk_policy")


@dataclass
class ActionOverride:
    """Override for specific action types."""
    action_type: ActionType
    mode: Optional[Mode] = None  # None means "any mode"
    tier: RiskTier = RiskTier.BLOCK
    reason: str = ""


@dataclass
class CostThreshold:
    """Cost thresholds for auto-approval."""
    mode: Mode
    max_auto_approve_usd: float = 1.0
    max_with_review_usd: float = 10.0
    block_above_usd: float = 100.0


@dataclass
class RiskPolicy:
    """Complete risk policy configuration.

    This dataclass represents the full risk policy, which can be loaded
    from YAML or constructed programmatically.
    """
    # The base matrix: maps (mode, severity) -> tier
    # Structure: {mode.value: {severity.value: tier.value}}
    base_matrix: dict[str, dict[str, str]] = field(default_factory=dict)

    # Action type overrides (take precedence over base matrix)
    action_overrides: list[ActionOverride] = field(default_factory=list)

    # Cost thresholds per mode
    cost_thresholds: dict[str, CostThreshold] = field(default_factory=dict)

    # Whether to auto-approve SAFE tier actions
    auto_approve_safe: bool = True

    # Whether to block all destructive actions regardless of mode
    block_destructive_always: bool = True

    # Whether safety filter changes are always blocked
    block_safety_filter_changes: bool = True

    # Default tier when matrix lookup fails
    default_tier: RiskTier = RiskTier.REVIEW

    # Policy metadata
    version: str = "1.0"
    description: str = ""

    @classmethod
    def default(cls) -> "RiskPolicy":
        """Create default risk policy."""
        return cls(
            base_matrix={
                "lab": {
                    "S0": "safe",
                    "S1": "safe",
                    "S2": "safe",
                    "S3": "review",
                    "S4": "review",
                },
                "shadow": {
                    "S0": "safe",
                    "S1": "safe",
                    "S2": "safe",
                    "S3": "review",
                    "S4": "block",
                },
                "production": {
                    "S0": "safe",
                    "S1": "safe",
                    "S2": "review",
                    "S3": "review",
                    "S4": "block",
                },
            },
            action_overrides=[
                ActionOverride(
                    action_type=ActionType.DESTRUCTIVE_TOOL_CALL,
                    mode=None,  # Any mode
                    tier=RiskTier.BLOCK,
                    reason="Destructive tool calls are always blocked",
                ),
                ActionOverride(
                    action_type=ActionType.SAFETY_FILTER_CHANGE,
                    mode=Mode.PRODUCTION,
                    tier=RiskTier.BLOCK,
                    reason="Safety filter changes blocked in production",
                ),
                ActionOverride(
                    action_type=ActionType.FINE_TUNE,
                    mode=Mode.PRODUCTION,
                    tier=RiskTier.BLOCK,
                    reason="Fine-tuning blocked in production",
                ),
            ],
            cost_thresholds={
                "lab": CostThreshold(
                    mode=Mode.LAB,
                    max_auto_approve_usd=10.0,
                    max_with_review_usd=100.0,
                    block_above_usd=1000.0,
                ),
                "shadow": CostThreshold(
                    mode=Mode.SHADOW,
                    max_auto_approve_usd=1.0,
                    max_with_review_usd=10.0,
                    block_above_usd=100.0,
                ),
                "production": CostThreshold(
                    mode=Mode.PRODUCTION,
                    max_auto_approve_usd=0.0,  # Never auto-approve in production
                    max_with_review_usd=10.0,
                    block_above_usd=50.0,
                ),
            },
            auto_approve_safe=True,
            block_destructive_always=True,
            block_safety_filter_changes=True,
            default_tier=RiskTier.REVIEW,
            version="1.0",
            description="Default Tinman risk policy",
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RiskPolicy":
        """Create RiskPolicy from dictionary (e.g., loaded from YAML)."""
        # Parse base matrix
        base_matrix = data.get("base_matrix", data.get("default_matrix", {}))

        # Parse action overrides
        action_overrides = []
        for override_data in data.get("overrides", data.get("action_overrides", [])):
            try:
                action_type = ActionType(override_data.get("action_type", ""))
            except ValueError:
                logger.warning(f"Unknown action type: {override_data.get('action_type')}")
                continue

            mode_str = override_data.get("mode")
            mode = None if mode_str == "any" or mode_str is None else Mode(mode_str)

            tier = RiskTier(override_data.get("tier", "block"))

            action_overrides.append(ActionOverride(
                action_type=action_type,
                mode=mode,
                tier=tier,
                reason=override_data.get("reason", ""),
            ))

        # Parse cost thresholds
        cost_thresholds = {}
        for mode_str, threshold_data in data.get("cost_thresholds", {}).items():
            try:
                mode = Mode(mode_str)
                cost_thresholds[mode_str] = CostThreshold(
                    mode=mode,
                    max_auto_approve_usd=threshold_data.get("max_auto_approve_usd", 1.0),
                    max_with_review_usd=threshold_data.get("max_with_review_usd", 10.0),
                    block_above_usd=threshold_data.get("block_above_usd", 100.0),
                )
            except ValueError:
                logger.warning(f"Unknown mode in cost thresholds: {mode_str}")

        return cls(
            base_matrix=base_matrix,
            action_overrides=action_overrides,
            cost_thresholds=cost_thresholds,
            auto_approve_safe=data.get("auto_approve_safe", True),
            block_destructive_always=data.get("block_destructive_always", True),
            block_safety_filter_changes=data.get("block_safety_filter_changes", True),
            default_tier=RiskTier(data.get("default_tier", "review")),
            version=data.get("version", "1.0"),
            description=data.get("description", ""),
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "version": self.version,
            "description": self.description,
            "base_matrix": self.base_matrix,
            "overrides": [
                {
                    "action_type": o.action_type.value,
                    "mode": o.mode.value if o.mode else "any",
                    "tier": o.tier.value,
                    "reason": o.reason,
                }
                for o in self.action_overrides
            ],
            "cost_thresholds": {
                mode_str: {
                    "max_auto_approve_usd": t.max_auto_approve_usd,
                    "max_with_review_usd": t.max_with_review_usd,
                    "block_above_usd": t.block_above_usd,
                }
                for mode_str, t in self.cost_thresholds.items()
            },
            "auto_approve_safe": self.auto_approve_safe,
            "block_destructive_always": self.block_destructive_always,
            "block_safety_filter_changes": self.block_safety_filter_changes,
            "default_tier": self.default_tier.value,
        }

    def lookup_tier(self, mode: Mode, severity: Severity) -> RiskTier:
        """Look up the tier for a given mode and severity."""
        mode_matrix = self.base_matrix.get(mode.value, {})
        tier_str = mode_matrix.get(severity.value)

        if tier_str:
            try:
                return RiskTier(tier_str)
            except ValueError:
                logger.warning(f"Invalid tier in matrix: {tier_str}")

        return self.default_tier

    def check_action_override(self, action_type: ActionType, mode: Mode) -> Optional[ActionOverride]:
        """Check if there's an override for this action type."""
        for override in self.action_overrides:
            if override.action_type == action_type:
                # Check if mode matches (None means any mode)
                if override.mode is None or override.mode == mode:
                    return override
        return None

    def check_cost_threshold(self, mode: Mode, cost_usd: float) -> tuple[RiskTier, str]:
        """Check if cost triggers a tier change."""
        threshold = self.cost_thresholds.get(mode.value)
        if not threshold:
            return self.default_tier, ""

        if cost_usd > threshold.block_above_usd:
            return RiskTier.BLOCK, f"Cost ${cost_usd:.2f} exceeds block threshold ${threshold.block_above_usd:.2f}"

        if cost_usd > threshold.max_with_review_usd:
            return RiskTier.BLOCK, f"Cost ${cost_usd:.2f} exceeds max review threshold ${threshold.max_with_review_usd:.2f}"

        if cost_usd > threshold.max_auto_approve_usd:
            return RiskTier.REVIEW, f"Cost ${cost_usd:.2f} exceeds auto-approve threshold ${threshold.max_auto_approve_usd:.2f}"

        return RiskTier.SAFE, ""


class PolicyDrivenRiskEvaluator:
    """Risk evaluator that uses a configurable policy.

    This replaces the hard-coded logic in RiskEvaluator with
    policy-driven evaluation.
    """

    def __init__(self, policy: Optional[RiskPolicy] = None):
        self.policy = policy or RiskPolicy.default()
        logger.info(f"PolicyDrivenRiskEvaluator initialized (policy version: {self.policy.version})")

    def update_policy(self, policy: RiskPolicy) -> None:
        """Update the risk policy."""
        self.policy = policy
        logger.info(f"Risk policy updated (version: {policy.version})")

    def evaluate(self, action: Action, mode: Mode) -> RiskAssessment:
        """Evaluate risk using the policy."""
        # 1. Check for hard blocks (destructive calls)
        if self.policy.block_destructive_always:
            if action.action_type == ActionType.DESTRUCTIVE_TOOL_CALL:
                return RiskAssessment(
                    tier=RiskTier.BLOCK,
                    severity=Severity.S4,
                    reasoning="Destructive tool calls are blocked by policy",
                    requires_approval=False,
                    auto_approve=False,
                    details={"blocked_by": "policy_destructive_block"},
                )

        # 2. Check for safety filter changes
        if self.policy.block_safety_filter_changes and action.affects_safety_filters:
            return RiskAssessment(
                tier=RiskTier.BLOCK,
                severity=Severity.S4,
                reasoning="Safety filter changes are blocked by policy",
                requires_approval=False,
                auto_approve=False,
                details={"blocked_by": "policy_safety_filter_block"},
            )

        # 3. Check action type overrides
        override = self.policy.check_action_override(action.action_type, mode)
        if override:
            return RiskAssessment(
                tier=override.tier,
                severity=action.predicted_severity,
                reasoning=override.reason or f"Action type {action.action_type.value} override",
                requires_approval=override.tier == RiskTier.REVIEW,
                auto_approve=override.tier == RiskTier.SAFE and self.policy.auto_approve_safe,
                details={
                    "blocked_by": "action_override" if override.tier == RiskTier.BLOCK else None,
                    "override_reason": override.reason,
                },
            )

        # 4. Check cost thresholds
        if action.estimated_cost > 0:
            cost_tier, cost_reason = self.policy.check_cost_threshold(mode, action.estimated_cost)
            if cost_tier == RiskTier.BLOCK:
                return RiskAssessment(
                    tier=RiskTier.BLOCK,
                    severity=action.predicted_severity,
                    reasoning=cost_reason,
                    requires_approval=False,
                    auto_approve=False,
                    details={"blocked_by": "cost_threshold"},
                )
            elif cost_tier == RiskTier.REVIEW:
                # Cost triggers review, continue to check matrix for possible escalation
                pass

        # 5. Look up in base matrix
        base_tier = self.policy.lookup_tier(mode, action.predicted_severity)

        # 6. Determine if approval is needed
        requires_approval = base_tier == RiskTier.REVIEW
        auto_approve = (
            base_tier == RiskTier.SAFE
            and self.policy.auto_approve_safe
            and action.estimated_cost <= self.policy.cost_thresholds.get(
                mode.value, CostThreshold(mode=mode)
            ).max_auto_approve_usd
        )

        reasoning = f"Policy matrix: mode={mode.value}, severity={action.predicted_severity.value} -> tier={base_tier.value}"

        return RiskAssessment(
            tier=base_tier,
            severity=action.predicted_severity,
            reasoning=reasoning,
            requires_approval=requires_approval,
            auto_approve=auto_approve,
            details={
                "mode": mode.value,
                "severity": action.predicted_severity.value,
                "policy_version": self.policy.version,
            },
        )

    def compute_severity(
        self,
        failure_class: str,
        reproducibility: float,
        impact_scope: list[str],
        is_safety_related: bool,
    ) -> Severity:
        """Compute severity based on failure characteristics."""
        score = 0.0

        if is_safety_related:
            score += 0.5

        score += reproducibility * 0.2

        if len(impact_scope) > 3:
            score += 0.2
        elif len(impact_scope) > 1:
            score += 0.1

        high_severity_classes = {
            "DESTRUCTIVE_CALL", "SAFETY_REGRESSION", "MEMORY_POISONING",
            "REWARD_HACKING", "TOOL_HALLUCINATION"
        }
        if failure_class.upper() in high_severity_classes:
            score += 0.3

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


def load_policy(path: Optional[Path] = None) -> RiskPolicy:
    """Load risk policy from YAML file.

    Searches in order:
    1. Explicit path provided
    2. .tinman/risk_policy.yaml
    3. tinman_risk_policy.yaml
    4. TINMAN_RISK_POLICY env var

    Falls back to default policy if no file found.
    """
    search_paths = []

    if path:
        search_paths.append(path)

    # Standard locations
    search_paths.extend([
        Path(".tinman/risk_policy.yaml"),
        Path("tinman_risk_policy.yaml"),
        Path("risk_policy.yaml"),
    ])

    # Environment variable
    env_path = os.environ.get("TINMAN_RISK_POLICY")
    if env_path:
        search_paths.insert(0, Path(env_path))

    for p in search_paths:
        if p.exists():
            logger.info(f"Loading risk policy from: {p}")
            try:
                with open(p) as f:
                    data = yaml.safe_load(f)
                return RiskPolicy.from_dict(data.get("risk", data))
            except Exception as e:
                logger.error(f"Failed to load risk policy from {p}: {e}")

    logger.info("Using default risk policy")
    return RiskPolicy.default()


def save_policy(policy: RiskPolicy, path: Path) -> None:
    """Save risk policy to YAML file."""
    data = {"risk": policy.to_dict()}

    path.parent.mkdir(parents=True, exist_ok=True)

    with open(path, "w") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False)

    logger.info(f"Saved risk policy to: {path}")


# Default policy instance
_default_policy: Optional[RiskPolicy] = None


def get_risk_policy() -> RiskPolicy:
    """Get the default risk policy."""
    global _default_policy
    if _default_policy is None:
        _default_policy = load_policy()
    return _default_policy


def set_risk_policy(policy: RiskPolicy) -> None:
    """Set the default risk policy."""
    global _default_policy
    _default_policy = policy


# Generate default policy file for reference
DEFAULT_POLICY_YAML = """# Tinman Risk Policy Configuration
# This file defines how actions are evaluated for risk.

version: "1.0"
description: "Default Tinman risk policy"

# Base risk matrix: maps (mode, severity) -> tier
# Tiers: safe (auto-approve), review (human approval), block (reject)
base_matrix:
  lab:
    S0: safe
    S1: safe
    S2: safe
    S3: review
    S4: review
  shadow:
    S0: safe
    S1: safe
    S2: safe
    S3: review
    S4: block
  production:
    S0: safe
    S1: safe
    S2: review
    S3: review
    S4: block

# Action type overrides (take precedence over base matrix)
overrides:
  - action_type: destructive_tool_call
    mode: any
    tier: block
    reason: "Destructive tool calls are always blocked"

  - action_type: safety_filter_change
    mode: production
    tier: block
    reason: "Safety filter changes blocked in production"

  - action_type: fine_tune
    mode: production
    tier: block
    reason: "Fine-tuning blocked in production"

  - action_type: tool_policy_change
    mode: production
    tier: review
    reason: "Tool policy changes require review in production"

# Cost thresholds per mode (USD)
cost_thresholds:
  lab:
    max_auto_approve_usd: 10.0
    max_with_review_usd: 100.0
    block_above_usd: 1000.0
  shadow:
    max_auto_approve_usd: 1.0
    max_with_review_usd: 10.0
    block_above_usd: 100.0
  production:
    max_auto_approve_usd: 0.0  # Never auto-approve in production
    max_with_review_usd: 10.0
    block_above_usd: 50.0

# Global settings
auto_approve_safe: true
block_destructive_always: true
block_safety_filter_changes: true
default_tier: review
"""
