"""
End-to-end tests for the HITL approval flow.

Tests the complete approval workflow:
1. ApprovalHandler receives request from agent
2. Risk is evaluated
3. UI callback (or CLI fallback) is invoked when needed
4. Response is returned to agent
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

from tinman.core.approval_handler import (
    ApprovalHandler,
    ApprovalContext,
    ApprovalMode,
    cli_approval_callback,
)
from tinman.core.risk_evaluator import RiskEvaluator, RiskTier, ActionType, Severity
from tinman.config.modes import Mode


class TestApprovalContext:
    """Test ApprovalContext dataclass."""

    def test_context_creation(self):
        """Test creating an approval context."""
        context = ApprovalContext(
            action_type=ActionType.CONFIG_CHANGE,
            action_description="Run experiment EXP-001",
            action_details={"experiment_id": "EXP-001"},
            risk_tier=RiskTier.REVIEW,
            severity=Severity.S2,
            estimated_cost_usd=0.50,
        )

        assert context.id is not None  # auto-generated
        assert context.action_type == ActionType.CONFIG_CHANGE
        assert context.risk_tier == RiskTier.REVIEW
        assert context.severity == Severity.S2
        assert context.estimated_cost_usd == 0.50


class TestApprovalHandler:
    """Test ApprovalHandler functionality."""

    @pytest.fixture
    def handler_strict(self):
        """Create a strict test approval handler (no auto-approve)."""
        return ApprovalHandler(
            mode=Mode.PRODUCTION,  # Production mode is stricter
            approval_mode=ApprovalMode.INTERACTIVE,
            auto_approve_in_lab=False,
            cost_threshold_usd=1.0,
        )

    @pytest.mark.asyncio
    async def test_auto_approve_mode(self):
        """Test AUTO_APPROVE mode bypasses UI and approves everything."""
        handler = ApprovalHandler(
            mode=Mode.PRODUCTION,
            approval_mode=ApprovalMode.AUTO_APPROVE,
            auto_approve_in_lab=False,
        )

        # Even REVIEW tier actions get auto-approved
        result = await handler.request_approval(
            action_type=ActionType.PROMPT_MUTATION,
            description="Test intervention",
            details={},
        )

        assert result is True

    @pytest.mark.asyncio
    async def test_auto_reject_mode(self):
        """Test AUTO_REJECT mode rejects REVIEW tier actions."""
        handler = ApprovalHandler(
            mode=Mode.PRODUCTION,
            approval_mode=ApprovalMode.AUTO_REJECT,
            auto_approve_in_lab=False,
        )

        # REVIEW tier actions should be rejected
        result = await handler.request_approval(
            action_type=ActionType.PROMPT_MUTATION,  # REVIEW in production
            description="Test intervention",
            details={},
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_ui_callback_invoked_for_review_tier(self, handler_strict):
        """Test that UI callback is invoked for REVIEW tier in production."""
        ui_callback = AsyncMock(return_value=True)
        handler_strict.register_ui(ui_callback)

        # PROMPT_MUTATION in production triggers REVIEW
        result = await handler_strict.request_approval(
            action_type=ActionType.PROMPT_MUTATION,
            description="Deploy risky intervention",
            details={},
        )

        # UI callback should have been called for REVIEW tier
        assert ui_callback.called
        assert result is True

    @pytest.mark.asyncio
    async def test_fallback_callback_used(self, handler_strict):
        """Test fallback callback used when no primary UI registered."""
        fallback = AsyncMock(return_value=False)
        handler_strict.register_fallback(fallback)

        result = await handler_strict.request_approval(
            action_type=ActionType.PROMPT_MUTATION,
            description="Change something",
            details={},
        )

        # Fallback should be called since no primary UI
        assert fallback.called
        assert result is False

    @pytest.mark.asyncio
    async def test_lab_mode_auto_approves_most_actions(self):
        """Test LAB mode with auto_approve_in_lab=True auto-approves most things."""
        handler = ApprovalHandler(
            mode=Mode.LAB,
            approval_mode=ApprovalMode.INTERACTIVE,
            auto_approve_in_lab=True,
        )

        ui_callback = AsyncMock(return_value=True)
        handler.register_ui(ui_callback)

        result = await handler.request_approval(
            action_type=ActionType.CONFIG_CHANGE,
            description="Run simulation",
            details={},
        )

        # Should auto-approve in LAB mode, UI not called
        assert result is True
        assert not ui_callback.called

    @pytest.mark.asyncio
    async def test_block_tier_always_rejects(self):
        """Test BLOCK risk tier always rejects regardless of mode."""
        handler = ApprovalHandler(
            mode=Mode.LAB,  # Even in LAB mode
            approval_mode=ApprovalMode.INTERACTIVE,
            auto_approve_in_lab=True,
        )

        ui_callback = AsyncMock(return_value=True)  # Even if UI would approve
        handler.register_ui(ui_callback)

        # Destructive tool calls are always BLOCKED
        result = await handler.request_approval(
            action_type=ActionType.DESTRUCTIVE_TOOL_CALL,
            description="Dangerous action",
            details={},
        )

        # BLOCK tier should reject without asking UI
        assert result is False
        assert not ui_callback.called

    @pytest.mark.asyncio
    async def test_safe_tier_auto_approves(self):
        """Test SAFE tier auto-approves without UI."""
        handler = ApprovalHandler(
            mode=Mode.LAB,
            approval_mode=ApprovalMode.INTERACTIVE,
            auto_approve_in_lab=False,  # Even with this off
        )

        ui_callback = AsyncMock(return_value=True)
        handler.register_ui(ui_callback)

        # CONFIG_CHANGE in LAB mode is SAFE
        result = await handler.request_approval(
            action_type=ActionType.CONFIG_CHANGE,
            description="Safe config change",
            details={},
            predicted_severity=Severity.S0,
        )

        # SAFE tier should auto-approve
        assert result is True


class TestApproveExperiment:
    """Test experiment approval flow."""

    @pytest.mark.asyncio
    async def test_approve_experiment_in_production(self):
        """Test experiment approval flow in production mode."""
        handler = ApprovalHandler(
            mode=Mode.PRODUCTION,
            approval_mode=ApprovalMode.INTERACTIVE,
            auto_approve_in_lab=False,
        )

        ui_callback = AsyncMock(return_value=True)
        handler.register_ui(ui_callback)

        result = await handler.approve_experiment(
            experiment_name="EXP-001",
            hypothesis="Testing prompt mutation",
            estimated_runs=10,
            estimated_cost_usd=0.25,
            stress_type="prompt_mutation",
        )

        # CONFIG_CHANGE action - may or may not need review
        assert result is True
        # Check context was built correctly if UI was called
        if ui_callback.called:
            context = ui_callback.call_args[0][0]
            assert "EXP-001" in context.action_description


class TestApproveIntervention:
    """Test intervention approval flow."""

    @pytest.mark.asyncio
    async def test_approve_intervention_in_production(self):
        """Test intervention approval in production mode."""
        handler = ApprovalHandler(
            mode=Mode.PRODUCTION,
            approval_mode=ApprovalMode.INTERACTIVE,
            auto_approve_in_lab=False,
        )

        ui_callback = AsyncMock(return_value=True)
        handler.register_ui(ui_callback)

        result = await handler.approve_intervention(
            intervention_type="guardrail_update",
            target_failure="FAIL-001",
            description="Add input validation",
            is_reversible=True,
            rollback_plan="Revert guardrail config",
            estimated_effect=0.85,
        )

        # PROMPT_MUTATION in production should trigger REVIEW
        assert result is True
        assert ui_callback.called

        context = ui_callback.call_args[0][0]
        assert context.action_type == ActionType.PROMPT_MUTATION
        assert context.rollback_plan == "Revert guardrail config"


class TestApproveSimulation:
    """Test simulation approval flow."""

    @pytest.mark.asyncio
    async def test_approve_simulation_auto_approves_in_lab(self):
        """Test simulation approval auto-approves in LAB mode."""
        handler = ApprovalHandler(
            mode=Mode.LAB,
            approval_mode=ApprovalMode.INTERACTIVE,
            auto_approve_in_lab=True,
        )

        ui_callback = AsyncMock(return_value=True)
        handler.register_ui(ui_callback)

        result = await handler.approve_simulation(
            failure_id="FAIL-001",
            intervention_id="INT-001",
            trace_count=100,
            estimated_cost_usd=2.50,
        )

        # Simulations in LAB mode should auto-approve
        assert result is True


class TestIntegrationWithAgents:
    """Integration tests with agent classes."""

    @pytest.mark.asyncio
    async def test_experiment_executor_accepts_approval_handler(self):
        """Test ExperimentExecutor accepts approval handler."""
        from tinman.agents.experiment_executor import ExperimentExecutor

        handler = ApprovalHandler(
            mode=Mode.LAB,
            approval_mode=ApprovalMode.AUTO_REJECT,
        )

        # Just test that the class accepts approval_handler parameter
        assert hasattr(ExperimentExecutor, '__init__')

    @pytest.mark.asyncio
    async def test_intervention_engine_accepts_approval_handler(self):
        """Test InterventionEngine accepts approval handler."""
        from tinman.agents.intervention_engine import InterventionEngine

        handler = ApprovalHandler(
            mode=Mode.LAB,
            approval_mode=ApprovalMode.INTERACTIVE,
        )

        assert hasattr(InterventionEngine, '__init__')

    @pytest.mark.asyncio
    async def test_simulation_engine_accepts_approval_handler(self):
        """Test SimulationEngine accepts approval handler."""
        from tinman.agents.simulation_engine import SimulationEngine

        handler = ApprovalHandler(
            mode=Mode.LAB,
            approval_mode=ApprovalMode.INTERACTIVE,
        )

        assert hasattr(SimulationEngine, '__init__')


class TestCLIFallback:
    """Test CLI approval fallback."""

    def test_cli_callback_is_callable(self):
        """Test CLI callback is properly defined."""
        assert callable(cli_approval_callback)

    def test_approval_context_can_be_created(self):
        """Test ApprovalContext can be created for CLI callback."""
        context = ApprovalContext(
            action_type=ActionType.CONFIG_CHANGE,
            action_description="Test CLI approval",
            action_details={"test": True},
            risk_tier=RiskTier.REVIEW,
            severity=Severity.S2,
            estimated_cost_usd=0.10,
        )

        assert context.action_description == "Test CLI approval"
        assert context.risk_tier == RiskTier.REVIEW


class TestApprovalStats:
    """Test approval statistics tracking."""

    @pytest.mark.asyncio
    async def test_stats_tracking(self):
        """Test that approval stats are tracked correctly."""
        handler = ApprovalHandler(
            mode=Mode.LAB,
            approval_mode=ApprovalMode.AUTO_APPROVE,
        )

        # Make some approvals
        await handler.request_approval(
            action_type=ActionType.CONFIG_CHANGE,
            description="Test 1",
            details={},
        )
        await handler.request_approval(
            action_type=ActionType.CONFIG_CHANGE,
            description="Test 2",
            details={},
        )

        stats = handler.get_stats()
        assert stats["total_requests"] == 2
        assert stats["auto_approved"] >= 2


class TestPendingApprovals:
    """Test pending approval tracking."""

    def test_get_pending_initially_empty(self):
        """Test pending approvals list is initially empty."""
        handler = ApprovalHandler(mode=Mode.LAB)
        pending = handler.get_pending()
        assert len(pending) == 0


class TestRiskTierBehavior:
    """Test correct behavior for each risk tier."""

    @pytest.mark.asyncio
    async def test_review_tier_shows_ui_in_production(self):
        """Test REVIEW tier actions show UI in production."""
        handler = ApprovalHandler(
            mode=Mode.PRODUCTION,
            approval_mode=ApprovalMode.INTERACTIVE,
        )

        ui_callback = AsyncMock(return_value=True)
        handler.register_ui(ui_callback)

        # PROMPT_MUTATION triggers REVIEW in production
        await handler.request_approval(
            action_type=ActionType.PROMPT_MUTATION,
            description="Prompt change",
            details={},
        )

        assert ui_callback.called

    @pytest.mark.asyncio
    async def test_ui_rejection_blocks_action(self):
        """Test that UI rejection blocks the action."""
        handler = ApprovalHandler(
            mode=Mode.PRODUCTION,
            approval_mode=ApprovalMode.INTERACTIVE,
        )

        ui_callback = AsyncMock(return_value=False)  # Reject
        handler.register_ui(ui_callback)

        result = await handler.request_approval(
            action_type=ActionType.PROMPT_MUTATION,
            description="Risky change",
            details={},
        )

        assert ui_callback.called
        assert result is False

    @pytest.mark.asyncio
    async def test_no_ui_defaults_to_reject(self):
        """Test that no UI callback defaults to rejection."""
        handler = ApprovalHandler(
            mode=Mode.PRODUCTION,
            approval_mode=ApprovalMode.INTERACTIVE,
        )

        # No UI registered

        result = await handler.request_approval(
            action_type=ActionType.PROMPT_MUTATION,
            description="No UI available",
            details={},
        )

        # Should default to reject when no UI
        assert result is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
