"""Tests for guarded tool execution."""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock

from tinman.config.modes import Mode
from tinman.core.risk_evaluator import ActionType, Severity, RiskTier
from tinman.core.approval_handler import ApprovalHandler, ApprovalMode
from tinman.core.tools import (
    guarded_call,
    ToolRegistry,
    ToolRiskLevel,
    ToolMetadata,
    ToolExecutionResult,
    tool,
)
from tinman.core.event_bus import EventBus


class TestToolRegistry:
    """Test the tool registry."""

    def test_register_tool(self, tool_registry):
        """Tools should be registerable."""

        async def my_tool(**kwargs):
            return "done"

        tool_registry.register(
            name="my_tool",
            fn=my_tool,
            description="A test tool",
            risk_level=ToolRiskLevel.LOW,
        )

        entry = tool_registry.get("my_tool")
        assert entry is not None
        fn, metadata = entry
        assert metadata.name == "my_tool"
        assert metadata.risk_level == ToolRiskLevel.LOW

    def test_unregistered_tool_returns_none(self, tool_registry):
        """Unregistered tools should return None."""
        entry = tool_registry.get("nonexistent")
        assert entry is None

    def test_list_tools(self, tool_registry):
        """Should list all registered tools."""

        async def tool_a(**kwargs):
            return "a"

        async def tool_b(**kwargs):
            return "b"

        tool_registry.register("tool_a", tool_a, "Tool A", ToolRiskLevel.SAFE)
        tool_registry.register("tool_b", tool_b, "Tool B", ToolRiskLevel.HIGH)

        tools = tool_registry.list_tools()
        assert len(tools) == 2
        names = [t.name for t in tools]
        assert "tool_a" in names
        assert "tool_b" in names

    def test_risk_level_to_action_type_mapping(self, tool_registry):
        """Risk levels should map to appropriate action types."""

        async def dummy(**kwargs):
            return None

        # Register tools with different risk levels
        tool_registry.register("safe_tool", dummy, "Safe", ToolRiskLevel.SAFE)
        tool_registry.register("destructive_tool", dummy, "Destructive", ToolRiskLevel.DESTRUCTIVE)

        _, safe_meta = tool_registry.get("safe_tool")
        _, dest_meta = tool_registry.get("destructive_tool")

        assert safe_meta.action_type == ActionType.CONFIG_CHANGE
        assert dest_meta.action_type == ActionType.DESTRUCTIVE_TOOL_CALL


class TestGuardedCall:
    """Test the guarded_call function."""

    @pytest.mark.asyncio
    async def test_safe_tool_executes(self, approval_handler, sample_tools):
        """Safe tools should execute successfully in lab mode."""
        result = await guarded_call(
            tool_fn=sample_tools["safe"],
            action_type=ActionType.CONFIG_CHANGE,
            description="Run safe tool",
            approval_handler=approval_handler,
            mode=Mode.LAB,
            payload={"test": "value"},
            predicted_severity=Severity.S0,
        )

        assert result.success is True
        assert "test" in str(result.result)
        assert result.blocked is False

    @pytest.mark.asyncio
    async def test_destructive_tool_blocked(self, approval_handler, sample_tools):
        """Destructive tools should be blocked."""
        result = await guarded_call(
            tool_fn=sample_tools["safe"],  # The function itself doesn't matter
            action_type=ActionType.DESTRUCTIVE_TOOL_CALL,
            description="Run destructive tool",
            approval_handler=approval_handler,
            mode=Mode.LAB,
            payload={},
            predicted_severity=Severity.S4,
        )

        assert result.success is False
        assert result.blocked is True
        assert result.risk_assessment is not None
        assert result.risk_assessment.tier == RiskTier.BLOCK

    @pytest.mark.asyncio
    async def test_failing_tool_captures_error(self, approval_handler, sample_tools):
        """Failing tools should capture errors."""
        result = await guarded_call(
            tool_fn=sample_tools["failing"],
            action_type=ActionType.CONFIG_CHANGE,
            description="Run failing tool",
            approval_handler=approval_handler,
            mode=Mode.LAB,
            payload={},
            predicted_severity=Severity.S0,
        )

        assert result.success is False
        assert result.blocked is False
        assert "Tool failure" in result.error

    @pytest.mark.asyncio
    async def test_timeout_handling(self, approval_handler):
        """Slow tools should timeout."""

        async def very_slow_tool(**kwargs):
            await asyncio.sleep(100)
            return "done"

        result = await guarded_call(
            tool_fn=very_slow_tool,
            action_type=ActionType.CONFIG_CHANGE,
            description="Run slow tool",
            approval_handler=approval_handler,
            mode=Mode.LAB,
            payload={},
            predicted_severity=Severity.S0,
            timeout_seconds=1,  # 1 second timeout
        )

        assert result.success is False
        assert "timeout" in result.error.lower()

    @pytest.mark.asyncio
    async def test_approval_required_in_production(self, strict_approval_handler, sample_tools):
        """Medium-risk actions in production should require approval."""
        # strict_approval_handler is set to AUTO_REJECT, so this should fail
        result = await guarded_call(
            tool_fn=sample_tools["safe"],
            action_type=ActionType.PROMPT_MUTATION,
            description="Modify prompt",
            approval_handler=strict_approval_handler,
            mode=Mode.PRODUCTION,
            payload={},
            predicted_severity=Severity.S2,
        )

        # Should fail because approval was rejected (AUTO_REJECT mode)
        assert result.success is False
        assert result.approval_required is True
        assert result.approval_granted is False

    @pytest.mark.asyncio
    async def test_execution_has_id_and_timestamps(self, approval_handler, sample_tools):
        """Execution results should have IDs and timestamps."""
        result = await guarded_call(
            tool_fn=sample_tools["safe"],
            action_type=ActionType.CONFIG_CHANGE,
            description="Test tool",
            approval_handler=approval_handler,
            mode=Mode.LAB,
            payload={},
        )

        assert result.execution_id is not None
        assert result.started_at is not None
        assert result.completed_at is not None
        assert result.completed_at >= result.started_at

    @pytest.mark.asyncio
    async def test_risk_assessment_captured(self, approval_handler, sample_tools):
        """Risk assessment should be captured in result."""
        result = await guarded_call(
            tool_fn=sample_tools["safe"],
            action_type=ActionType.CONFIG_CHANGE,
            description="Test tool",
            approval_handler=approval_handler,
            mode=Mode.LAB,
            payload={},
            predicted_severity=Severity.S1,
        )

        assert result.risk_assessment is not None
        assert result.risk_assessment.severity == Severity.S1


class TestToolRegistryExecution:
    """Test executing tools through the registry."""

    @pytest.mark.asyncio
    async def test_execute_registered_tool(self, tool_registry, approval_handler):
        """Should execute registered tools with guards."""

        async def my_tool(**kwargs):
            return f"Processed: {kwargs.get('input', 'none')}"

        tool_registry.register(
            name="my_tool",
            fn=my_tool,
            description="Process input",
            risk_level=ToolRiskLevel.LOW,
        )

        result = await tool_registry.execute(
            name="my_tool",
            approval_handler=approval_handler,
            mode=Mode.LAB,
            payload={"input": "test_data"},
        )

        assert result.success is True
        assert "test_data" in str(result.result)

    @pytest.mark.asyncio
    async def test_execute_unregistered_tool_fails(self, tool_registry, approval_handler):
        """Should fail for unregistered tools."""
        result = await tool_registry.execute(
            name="nonexistent_tool",
            approval_handler=approval_handler,
            mode=Mode.LAB,
            payload={},
        )

        assert result.success is False
        assert result.blocked is True
        assert "not registered" in result.error.lower()

    @pytest.mark.asyncio
    async def test_execution_history_recorded(self, tool_registry, approval_handler):
        """Execution history should be recorded."""

        async def tracked_tool(**kwargs):
            return "tracked"

        tool_registry.register(
            name="tracked_tool",
            fn=tracked_tool,
            description="Tracked tool",
            risk_level=ToolRiskLevel.SAFE,
        )

        await tool_registry.execute(
            name="tracked_tool",
            approval_handler=approval_handler,
            mode=Mode.LAB,
            payload={},
        )

        history = tool_registry.get_execution_history()
        assert len(history) >= 1
        assert history[-1].tool_name == "tracked_tool"


class TestToolDecorator:
    """Test the @tool decorator."""

    def test_decorator_registers_tool(self):
        """Decorator should register the tool."""
        from tinman.core.tools import get_tool_registry, set_tool_registry

        # Create a fresh registry for this test
        test_registry = ToolRegistry()
        set_tool_registry(test_registry)

        @tool(
            name="decorated_tool",
            description="A decorated tool",
            risk_level=ToolRiskLevel.MEDIUM,
        )
        async def my_decorated_tool(param: str) -> str:
            return f"Got: {param}"

        # Check registration
        entry = test_registry.get("decorated_tool")
        assert entry is not None
        _, metadata = entry
        assert metadata.name == "decorated_tool"
        assert metadata.risk_level == ToolRiskLevel.MEDIUM

        # Check metadata attached to function
        assert hasattr(my_decorated_tool, "_tool_name")
        assert my_decorated_tool._tool_name == "decorated_tool"

    @pytest.mark.asyncio
    async def test_decorated_tool_callable_directly(self):
        """Decorated tools should be callable directly (for testing)."""
        from tinman.core.tools import get_tool_registry, set_tool_registry

        test_registry = ToolRegistry()
        set_tool_registry(test_registry)

        @tool(
            name="direct_call_tool",
            description="Direct call tool",
            risk_level=ToolRiskLevel.SAFE,
        )
        async def direct_tool(value: int) -> int:
            return value * 2

        # Direct call (without guards - for testing)
        result = await direct_tool(value=21)
        assert result == 42


class TestApprovalOverrides:
    """Test approval override behavior."""

    @pytest.mark.asyncio
    async def test_force_approval_override(self, approval_handler, sample_tools):
        """Should force approval even for safe actions when override is set."""
        # Create handler in production mode with auto-reject
        event_bus = EventBus()
        from tinman.core.risk_evaluator import RiskEvaluator

        strict_handler = ApprovalHandler(
            mode=Mode.PRODUCTION,
            approval_mode=ApprovalMode.AUTO_REJECT,
            risk_evaluator=RiskEvaluator(),
            event_bus=event_bus,
        )

        result = await guarded_call(
            tool_fn=sample_tools["safe"],
            action_type=ActionType.CONFIG_CHANGE,
            description="Safe but forced review",
            approval_handler=strict_handler,
            mode=Mode.PRODUCTION,
            payload={},
            predicted_severity=Severity.S0,
            requires_approval_override=True,  # Force approval
        )

        # Should require approval and fail (auto-reject)
        assert result.success is False
        assert result.approval_required is True
        assert result.approval_granted is False

    @pytest.mark.asyncio
    async def test_skip_approval_override(self, strict_approval_handler, sample_tools):
        """Should skip approval when override is False."""
        result = await guarded_call(
            tool_fn=sample_tools["safe"],
            action_type=ActionType.CONFIG_CHANGE,
            description="Skip approval",
            approval_handler=strict_approval_handler,
            mode=Mode.PRODUCTION,
            payload={},
            predicted_severity=Severity.S0,
            requires_approval_override=False,  # Skip approval
        )

        # Should succeed without needing approval
        assert result.success is True
        assert result.approval_required is False


class TestSyncToolSupport:
    """Test support for synchronous tools."""

    @pytest.mark.asyncio
    async def test_sync_tool_execution(self, approval_handler):
        """Should execute synchronous tools correctly."""

        def sync_tool(**kwargs):
            return f"Sync result: {kwargs.get('value', 'none')}"

        result = await guarded_call(
            tool_fn=sync_tool,
            action_type=ActionType.CONFIG_CHANGE,
            description="Sync tool",
            approval_handler=approval_handler,
            mode=Mode.LAB,
            payload={"value": "test"},
        )

        assert result.success is True
        assert "test" in str(result.result)
