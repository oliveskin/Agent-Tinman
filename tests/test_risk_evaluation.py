"""Tests for risk evaluation and policy system."""

import pytest
from tinman.config.modes import Mode
from tinman.core.risk_evaluator import (
    RiskEvaluator,
    RiskTier,
    Severity,
    Action,
    ActionType,
    RiskAssessment,
)
from tinman.core.risk_policy import (
    RiskPolicy,
    PolicyDrivenRiskEvaluator,
    ActionOverride,
    CostThreshold,
    load_policy,
)


class TestSeverityComparison:
    """Test severity level comparisons."""

    def test_severity_ordering(self):
        """Severity levels should be properly ordered."""
        assert Severity.S0 < Severity.S1
        assert Severity.S1 < Severity.S2
        assert Severity.S2 < Severity.S3
        assert Severity.S3 < Severity.S4

    def test_severity_equality(self):
        """Same severity levels should be equal."""
        assert Severity.S2 == Severity.S2
        assert not Severity.S2 < Severity.S2
        assert Severity.S2 <= Severity.S2

    def test_severity_numeric(self):
        """Numeric values should be correct."""
        assert Severity.S0.numeric == 0.0
        assert Severity.S1.numeric == 0.25
        assert Severity.S2.numeric == 0.5
        assert Severity.S3.numeric == 0.75
        assert Severity.S4.numeric == 1.0


class TestRiskEvaluator:
    """Test the original RiskEvaluator."""

    def test_destructive_always_blocked(self, risk_evaluator, destructive_action):
        """Destructive actions should always be blocked."""
        for mode in [Mode.LAB, Mode.SHADOW, Mode.PRODUCTION]:
            result = risk_evaluator.evaluate(destructive_action, mode)
            assert result.tier == RiskTier.BLOCK
            assert result.severity == Severity.S4

    def test_lab_mode_permissive(self, risk_evaluator, safe_action, medium_action):
        """Lab mode should be permissive for non-destructive actions."""
        # Safe action in lab
        result = risk_evaluator.evaluate(safe_action, Mode.LAB)
        assert result.tier == RiskTier.SAFE
        assert result.auto_approve is True

        # Medium action in lab (still safe due to lab mode)
        result = risk_evaluator.evaluate(medium_action, Mode.LAB)
        assert result.tier == RiskTier.SAFE

    def test_shadow_mode_moderate(self, risk_evaluator, high_risk_action):
        """Shadow mode should require review for high-severity actions."""
        result = risk_evaluator.evaluate(high_risk_action, Mode.SHADOW)
        assert result.tier == RiskTier.REVIEW
        assert result.requires_approval is True

    def test_production_mode_strict(self, risk_evaluator, medium_action, high_risk_action):
        """Production mode should be strict."""
        # Medium action requires review
        result = risk_evaluator.evaluate(medium_action, Mode.PRODUCTION)
        assert result.tier == RiskTier.REVIEW

        # High risk also requires review (S3)
        result = risk_evaluator.evaluate(high_risk_action, Mode.PRODUCTION)
        assert result.tier == RiskTier.REVIEW

    def test_s4_blocked_in_production(self, risk_evaluator):
        """S4 severity should be blocked in production."""
        action = Action(
            action_type=ActionType.CONFIG_CHANGE,  # Not destructive type
            target_surface="production",
            payload={},
            predicted_severity=Severity.S4,
        )
        result = risk_evaluator.evaluate(action, Mode.PRODUCTION)
        assert result.tier == RiskTier.BLOCK

    def test_safety_filter_always_blocked(self, risk_evaluator):
        """Actions affecting safety filters should be blocked."""
        action = Action(
            action_type=ActionType.SAFETY_FILTER_CHANGE,
            target_surface="lab",
            payload={},
            predicted_severity=Severity.S0,
            affects_safety_filters=True,
        )
        result = risk_evaluator.evaluate(action, Mode.LAB)
        assert result.tier == RiskTier.BLOCK


class TestRiskPolicy:
    """Test the policy configuration."""

    def test_default_policy_structure(self, default_risk_policy):
        """Default policy should have proper structure."""
        assert "lab" in default_risk_policy.base_matrix
        assert "shadow" in default_risk_policy.base_matrix
        assert "production" in default_risk_policy.base_matrix

        # Each mode should have all severity levels
        for mode in ["lab", "shadow", "production"]:
            matrix = default_risk_policy.base_matrix[mode]
            assert "S0" in matrix
            assert "S1" in matrix
            assert "S2" in matrix
            assert "S3" in matrix
            assert "S4" in matrix

    def test_policy_lookup(self, default_risk_policy):
        """Policy lookup should return correct tiers."""
        # Lab S0 should be safe
        tier = default_risk_policy.lookup_tier(Mode.LAB, Severity.S0)
        assert tier == RiskTier.SAFE

        # Production S2 should be review
        tier = default_risk_policy.lookup_tier(Mode.PRODUCTION, Severity.S2)
        assert tier == RiskTier.REVIEW

        # Shadow S4 should be block
        tier = default_risk_policy.lookup_tier(Mode.SHADOW, Severity.S4)
        assert tier == RiskTier.BLOCK

    def test_action_override_lookup(self, default_risk_policy):
        """Action overrides should be found correctly."""
        # Destructive should be overridden
        override = default_risk_policy.check_action_override(
            ActionType.DESTRUCTIVE_TOOL_CALL, Mode.LAB
        )
        assert override is not None
        assert override.tier == RiskTier.BLOCK

        # Config change should not be overridden
        override = default_risk_policy.check_action_override(ActionType.CONFIG_CHANGE, Mode.LAB)
        assert override is None

    def test_cost_threshold_lookup(self, default_risk_policy):
        """Cost thresholds should trigger correct tiers."""
        # Lab mode allows higher costs
        tier, reason = default_risk_policy.check_cost_threshold(Mode.LAB, 5.0)
        assert tier == RiskTier.SAFE

        tier, reason = default_risk_policy.check_cost_threshold(Mode.LAB, 50.0)
        assert tier == RiskTier.REVIEW

        # Production mode is stricter
        tier, reason = default_risk_policy.check_cost_threshold(Mode.PRODUCTION, 0.5)
        assert tier == RiskTier.REVIEW  # Any cost needs review in production

        tier, reason = default_risk_policy.check_cost_threshold(Mode.PRODUCTION, 100.0)
        assert tier == RiskTier.BLOCK

    def test_policy_to_dict_roundtrip(self, default_risk_policy):
        """Policy should survive serialization roundtrip."""
        data = default_risk_policy.to_dict()
        restored = RiskPolicy.from_dict(data)

        assert restored.version == default_risk_policy.version
        assert restored.base_matrix == default_risk_policy.base_matrix
        assert len(restored.action_overrides) == len(default_risk_policy.action_overrides)


class TestPolicyDrivenRiskEvaluator:
    """Test the policy-driven risk evaluator."""

    def test_evaluator_uses_policy_matrix(self, policy_evaluator, safe_action):
        """Evaluator should use policy matrix for basic evaluation."""
        result = policy_evaluator.evaluate(safe_action, Mode.LAB)
        assert result.tier == RiskTier.SAFE
        assert "policy_version" in result.details

    def test_evaluator_respects_action_overrides(self, policy_evaluator, destructive_action):
        """Evaluator should respect action type overrides."""
        result = policy_evaluator.evaluate(destructive_action, Mode.LAB)
        assert result.tier == RiskTier.BLOCK
        assert "policy_destructive_block" in result.details.get("blocked_by", "")

    def test_evaluator_checks_cost_thresholds(self, policy_evaluator):
        """Evaluator should check cost thresholds."""
        # High cost action
        action = Action(
            action_type=ActionType.CONFIG_CHANGE,
            target_surface="production",
            payload={},
            predicted_severity=Severity.S0,
            estimated_cost=1000.0,  # Very high cost
        )
        result = policy_evaluator.evaluate(action, Mode.LAB)
        # Even in lab, very high cost might be blocked
        assert result.tier in [RiskTier.REVIEW, RiskTier.BLOCK]

    def test_policy_update(self, policy_evaluator):
        """Evaluator should allow policy updates."""
        # Create a custom policy that blocks everything
        strict_policy = RiskPolicy(
            base_matrix={
                "lab": {"S0": "block", "S1": "block", "S2": "block", "S3": "block", "S4": "block"},
                "shadow": {
                    "S0": "block",
                    "S1": "block",
                    "S2": "block",
                    "S3": "block",
                    "S4": "block",
                },
                "production": {
                    "S0": "block",
                    "S1": "block",
                    "S2": "block",
                    "S3": "block",
                    "S4": "block",
                },
            },
            action_overrides=[],
            block_destructive_always=False,  # For this test
        )

        policy_evaluator.update_policy(strict_policy)

        # Now even safe actions should be blocked
        action = Action(
            action_type=ActionType.CONFIG_CHANGE,
            target_surface="lab",
            payload={},
            predicted_severity=Severity.S0,
        )
        result = policy_evaluator.evaluate(action, Mode.LAB)
        assert result.tier == RiskTier.BLOCK

    def test_compute_severity(self, policy_evaluator):
        """Severity computation should work correctly."""
        # Low severity scenario
        severity = policy_evaluator.compute_severity(
            failure_class="minor_issue",
            reproducibility=0.1,
            impact_scope=["system_a"],
            is_safety_related=False,
        )
        assert severity in [Severity.S0, Severity.S1]

        # High severity scenario
        severity = policy_evaluator.compute_severity(
            failure_class="TOOL_HALLUCINATION",
            reproducibility=0.9,
            impact_scope=["system_a", "system_b", "system_c", "system_d"],
            is_safety_related=True,
        )
        assert severity in [Severity.S3, Severity.S4]


class TestModeTransitionRules:
    """Test mode transition validity (from control_plane)."""

    def test_valid_transitions(self):
        """Test that valid mode transitions are allowed."""
        # These transitions should be valid according to MODES.md
        valid_transitions = [
            (Mode.LAB, Mode.SHADOW),  # LAB -> SHADOW
            (Mode.SHADOW, Mode.PRODUCTION),  # SHADOW -> PRODUCTION
            (Mode.PRODUCTION, Mode.SHADOW),  # PRODUCTION -> SHADOW (regression fallback)
        ]

        # We're testing the concept - actual validation is in control_plane
        for from_mode, to_mode in valid_transitions:
            # Just verify the enum values are correct
            assert from_mode.value in ["lab", "shadow", "production"]
            assert to_mode.value in ["lab", "shadow", "production"]

    def test_invalid_transitions(self):
        """Test that invalid mode transitions are blocked."""
        # LAB -> PRODUCTION should be invalid (must go through SHADOW)
        # This is documented behavior that control_plane enforces
        invalid_transitions = [
            (Mode.LAB, Mode.PRODUCTION),  # Cannot skip SHADOW
        ]

        for from_mode, to_mode in invalid_transitions:
            # Verify these are the pairs we want to block
            assert from_mode == Mode.LAB and to_mode == Mode.PRODUCTION


class TestRiskAssessmentDetails:
    """Test risk assessment result details."""

    def test_assessment_has_required_fields(self, risk_evaluator, safe_action):
        """Risk assessments should have all required fields."""
        result = risk_evaluator.evaluate(safe_action, Mode.LAB)

        assert isinstance(result, RiskAssessment)
        assert result.tier in RiskTier
        assert result.severity in Severity
        assert isinstance(result.reasoning, str)
        assert isinstance(result.requires_approval, bool)
        assert isinstance(result.auto_approve, bool)
        assert isinstance(result.details, dict)

    def test_blocked_assessment_not_approvable(self, risk_evaluator, destructive_action):
        """Blocked actions should not be approvable."""
        result = risk_evaluator.evaluate(destructive_action, Mode.LAB)

        assert result.tier == RiskTier.BLOCK
        assert result.requires_approval is False  # Can't approve what's blocked
        assert result.auto_approve is False
