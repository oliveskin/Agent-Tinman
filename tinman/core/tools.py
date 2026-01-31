"""Guarded tool execution - the critical safety layer.

This module provides the `guarded_call` wrapper that ensures ALL
tool executions go through the risk evaluation and approval flow.

Usage:
    from tinman.core.tools import guarded_call, ToolRegistry

    # Register a tool
    registry = ToolRegistry()
    registry.register("delete_file", delete_file_fn, risk_level="destructive")

    # Execute with guards
    result = await guarded_call(
        tool_fn=my_tool,
        action_type=ActionType.DESTRUCTIVE_TOOL_CALL,
        description="Delete user data file",
        approval_handler=handler,
        mode=Mode.PRODUCTION,
        payload={"file": "/data/users.db"},
    )
"""

import asyncio
import collections
import functools
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Generic, TypeVar

from ..config.modes import Mode
from ..utils import generate_id, get_logger, utc_now
from .approval_handler import ApprovalContext, ApprovalHandler
from .risk_evaluator import Action, ActionType, RiskAssessment, RiskTier, Severity

logger = get_logger("tools")

T = TypeVar("T")


class ToolRiskLevel(str, Enum):
    """Predefined risk levels for tools."""

    SAFE = "safe"  # Read-only, no side effects
    LOW = "low"  # Minor side effects, easily reversible
    MEDIUM = "medium"  # Significant side effects, reversible
    HIGH = "high"  # Major side effects, difficult to reverse
    DESTRUCTIVE = "destructive"  # Irreversible, data loss possible


@dataclass
class ToolMetadata:
    """Metadata for a registered tool."""

    name: str
    description: str
    risk_level: ToolRiskLevel
    action_type: ActionType
    is_reversible: bool = True
    rollback_fn: Callable | None = None
    estimated_cost_usd: float = 0.0
    estimated_latency_ms: int = 0
    affected_systems: list[str] = field(default_factory=list)
    requires_approval_override: bool | None = None  # Force approval regardless of risk


@dataclass
class ToolExecutionResult(Generic[T]):
    """Result of a guarded tool execution."""

    success: bool
    result: T | None = None
    error: str | None = None
    execution_id: str = field(default_factory=generate_id)
    started_at: datetime = field(default_factory=utc_now)
    completed_at: datetime | None = None
    approval_required: bool = False
    approval_granted: bool = False
    risk_assessment: RiskAssessment | None = None
    blocked: bool = False
    block_reason: str | None = None


@dataclass
class ToolExecutionContext:
    """Context for tool execution, used for audit trail."""

    execution_id: str
    tool_name: str
    action_type: ActionType
    description: str
    payload: dict[str, Any]
    mode: Mode
    requester_agent: str
    requester_session: str
    risk_assessment: RiskAssessment | None
    approval_context: ApprovalContext | None
    started_at: datetime
    completed_at: datetime | None = None
    success: bool = False
    error: str | None = None
    result_summary: str | None = None


class ToolRegistry:
    """Registry for tools with their risk metadata.

    The registry ensures all tools are documented with their risk levels,
    making it impossible to call a tool without proper risk assessment.
    """

    def __init__(self, max_history_size: int = 1000):
        self._tools: dict[str, tuple[Callable, ToolMetadata]] = {}
        self._execution_history: collections.deque[ToolExecutionContext] = collections.deque(
            maxlen=max_history_size
        )

    def register(
        self,
        name: str,
        fn: Callable,
        description: str,
        risk_level: ToolRiskLevel = ToolRiskLevel.MEDIUM,
        action_type: ActionType | None = None,
        is_reversible: bool = True,
        rollback_fn: Callable | None = None,
        estimated_cost_usd: float = 0.0,
        estimated_latency_ms: int = 0,
        affected_systems: list[str] | None = None,
        requires_approval_override: bool | None = None,
    ) -> None:
        """Register a tool with its metadata."""
        # Auto-determine action type from risk level if not specified
        if action_type is None:
            action_type = self._risk_level_to_action_type(risk_level)

        metadata = ToolMetadata(
            name=name,
            description=description,
            risk_level=risk_level,
            action_type=action_type,
            is_reversible=is_reversible,
            rollback_fn=rollback_fn,
            estimated_cost_usd=estimated_cost_usd,
            estimated_latency_ms=estimated_latency_ms,
            affected_systems=affected_systems or [],
            requires_approval_override=requires_approval_override,
        )

        self._tools[name] = (fn, metadata)
        logger.info(f"Registered tool: {name} (risk_level={risk_level.value})")

    def _risk_level_to_action_type(self, risk_level: ToolRiskLevel) -> ActionType:
        """Map risk level to default action type."""
        mapping = {
            ToolRiskLevel.SAFE: ActionType.CONFIG_CHANGE,
            ToolRiskLevel.LOW: ActionType.CONFIG_CHANGE,
            ToolRiskLevel.MEDIUM: ActionType.TOOL_POLICY_CHANGE,
            ToolRiskLevel.HIGH: ActionType.TOOL_POLICY_CHANGE,
            ToolRiskLevel.DESTRUCTIVE: ActionType.DESTRUCTIVE_TOOL_CALL,
        }
        return mapping.get(risk_level, ActionType.CONFIG_CHANGE)

    def get(self, name: str) -> tuple[Callable, ToolMetadata] | None:
        """Get a tool and its metadata by name."""
        return self._tools.get(name)

    def list_tools(self) -> list[ToolMetadata]:
        """List all registered tools."""
        return [meta for _, meta in self._tools.values()]

    def record_execution(self, context: ToolExecutionContext) -> None:
        """Record a tool execution for audit trail."""
        self._execution_history.append(context)

    def get_execution_history(self, limit: int = 100) -> list[ToolExecutionContext]:
        """Get recent execution history."""
        history_list = list(self._execution_history)
        return history_list[-limit:]

    async def execute(
        self,
        name: str,
        approval_handler: ApprovalHandler,
        mode: Mode,
        payload: dict[str, Any] | None = None,
        requester_agent: str = "",
        requester_session: str = "",
        timeout_seconds: int = 300,
        **kwargs,
    ) -> ToolExecutionResult:
        """Execute a registered tool with full safety guards."""
        tool_entry = self.get(name)
        if not tool_entry:
            return ToolExecutionResult(
                success=False,
                error=f"Tool not registered: {name}",
                blocked=True,
                block_reason="unregistered_tool",
            )

        fn, metadata = tool_entry

        return await guarded_call(
            tool_fn=fn,
            action_type=metadata.action_type,
            description=metadata.description,
            approval_handler=approval_handler,
            mode=mode,
            payload=payload or {},
            is_reversible=metadata.is_reversible,
            rollback_plan=f"Call rollback function: {metadata.rollback_fn.__name__}"
            if metadata.rollback_fn
            else "",
            estimated_cost_usd=metadata.estimated_cost_usd,
            estimated_latency_ms=metadata.estimated_latency_ms,
            affected_systems=metadata.affected_systems,
            requester_agent=requester_agent,
            requester_session=requester_session,
            timeout_seconds=timeout_seconds,
            tool_registry=self,
            tool_name=name,
            requires_approval_override=metadata.requires_approval_override,
            **kwargs,
        )


# Default global registry
_default_registry: ToolRegistry | None = None


def get_tool_registry() -> ToolRegistry:
    """Get the default tool registry."""
    global _default_registry
    if _default_registry is None:
        _default_registry = ToolRegistry()
    return _default_registry


def set_tool_registry(registry: ToolRegistry) -> None:
    """Set the default tool registry."""
    global _default_registry
    _default_registry = registry


async def guarded_call(
    tool_fn: Callable[..., Coroutine[Any, Any, T]],
    action_type: ActionType,
    description: str,
    approval_handler: ApprovalHandler,
    mode: Mode,
    payload: dict[str, Any] | None = None,
    is_reversible: bool = True,
    rollback_plan: str = "",
    estimated_cost_usd: float = 0.0,
    estimated_latency_ms: int = 0,
    affected_systems: list[str] | None = None,
    requester_agent: str = "",
    requester_session: str = "",
    predicted_severity: Severity = Severity.S1,
    timeout_seconds: int = 300,
    tool_registry: ToolRegistry | None = None,
    tool_name: str = "",
    requires_approval_override: bool | None = None,
    **kwargs,
) -> ToolExecutionResult[T]:
    """
    Execute a tool function with full risk evaluation and approval flow.

    This is THE critical function for production safety. Every tool call
    that has side effects MUST go through this wrapper.

    Flow:
    1. Build Action from parameters
    2. Evaluate risk via RiskEvaluator
    3. If BLOCK tier -> reject immediately
    4. If REVIEW tier -> request human approval
    5. If approved or SAFE tier -> execute tool
    6. Record execution for audit trail
    7. Return result with full context

    Args:
        tool_fn: The async function to execute
        action_type: Type of action (from ActionType enum)
        description: Human-readable description
        approval_handler: Handler for HITL approvals
        mode: Current operating mode
        payload: Tool parameters (passed to tool_fn as kwargs)
        is_reversible: Whether action can be undone
        rollback_plan: How to rollback if needed
        estimated_cost_usd: Estimated cost
        estimated_latency_ms: Estimated duration
        affected_systems: Systems affected by this action
        requester_agent: Which agent is requesting
        requester_session: Session ID
        predicted_severity: Predicted severity (S0-S4)
        timeout_seconds: Timeout for approval + execution
        tool_registry: Registry for audit trail
        tool_name: Name of tool (for audit)
        requires_approval_override: Force approval requirement
        **kwargs: Additional args passed to tool_fn

    Returns:
        ToolExecutionResult with success/failure and full context
    """
    execution_id = generate_id()
    started_at = utc_now()
    payload = payload or {}

    logger.info(f"Guarded call started: {tool_name or description} (execution_id={execution_id})")

    # Build action for risk evaluation
    action = Action(
        action_type=action_type,
        target_surface=mode.value,
        payload=payload,
        predicted_severity=predicted_severity,
        estimated_cost=estimated_cost_usd,
        estimated_latency_ms=estimated_latency_ms,
        is_reversible=is_reversible,
    )

    # Evaluate risk
    risk_evaluator = approval_handler.risk_evaluator
    risk_assessment = risk_evaluator.evaluate(action, mode)

    logger.info(
        f"Risk assessment: tier={risk_assessment.tier.value}, "
        f"severity={risk_assessment.severity.value}, "
        f"requires_approval={risk_assessment.requires_approval}"
    )

    # Create execution context for audit
    exec_context = ToolExecutionContext(
        execution_id=execution_id,
        tool_name=tool_name or "anonymous",
        action_type=action_type,
        description=description,
        payload=payload,
        mode=mode,
        requester_agent=requester_agent,
        requester_session=requester_session,
        risk_assessment=risk_assessment,
        approval_context=None,
        started_at=started_at,
    )

    # Check for BLOCK tier - BLOCK can NEVER be bypassed, even with override
    if risk_assessment.tier == RiskTier.BLOCK:
        # Log warning if someone attempted to override a BLOCK decision
        if requires_approval_override is False:
            logger.warning(
                "Cannot override BLOCK tier decision",
                tool_name=tool_name or "anonymous",
                risk_tier=risk_assessment.tier.value,
            )

        logger.warning(f"Tool call BLOCKED: {description} (reason: {risk_assessment.reasoning})")

        exec_context.completed_at = utc_now()
        exec_context.success = False
        exec_context.error = f"Blocked: {risk_assessment.reasoning}"

        if tool_registry:
            tool_registry.record_execution(exec_context)

        return ToolExecutionResult(
            success=False,
            execution_id=execution_id,
            started_at=started_at,
            completed_at=exec_context.completed_at,
            blocked=True,
            block_reason=risk_assessment.reasoning,
            risk_assessment=risk_assessment,
        )

    # Check if approval is needed
    needs_approval = (
        risk_assessment.requires_approval
        or risk_assessment.tier == RiskTier.REVIEW
        or requires_approval_override is True
    )

    # Override can skip approval for REVIEW tier (acceptable), but NEVER for BLOCK tier
    # BLOCK tier is already handled above and will always be blocked
    if requires_approval_override is False and risk_assessment.tier == RiskTier.REVIEW:
        # REVIEW tier CAN be bypassed with override - this is acceptable
        needs_approval = False
    elif requires_approval_override is False and risk_assessment.tier == RiskTier.SAFE:
        # SAFE tier doesn't need override anyway
        needs_approval = False

    approval_granted = False

    if needs_approval:
        logger.info(f"Requesting approval for: {description}")

        try:
            approval_granted = await approval_handler.request_approval(
                action_type=action_type,
                description=description,
                details=payload,
                estimated_cost_usd=estimated_cost_usd,
                estimated_duration_ms=estimated_latency_ms,
                affected_systems=affected_systems,
                is_reversible=is_reversible,
                rollback_plan=rollback_plan,
                requester_agent=requester_agent,
                requester_session=requester_session,
                predicted_severity=predicted_severity,
                timeout_seconds=timeout_seconds,
                force_approval=requires_approval_override is True,
            )
        except Exception as e:
            logger.error(f"Approval request failed: {e}")
            approval_granted = False

        if not approval_granted:
            logger.info(f"Approval denied for: {description}")

            exec_context.completed_at = utc_now()
            exec_context.success = False
            exec_context.error = "Approval denied by human"

            if tool_registry:
                tool_registry.record_execution(exec_context)

            return ToolExecutionResult(
                success=False,
                execution_id=execution_id,
                started_at=started_at,
                completed_at=exec_context.completed_at,
                approval_required=True,
                approval_granted=False,
                risk_assessment=risk_assessment,
            )
    else:
        # Auto-approved (SAFE tier or lab mode)
        approval_granted = True
        logger.info(f"Auto-approved (tier={risk_assessment.tier.value}): {description}")

    # Execute the tool
    logger.info(f"Executing tool: {tool_name or description}")

    try:
        # Merge payload with kwargs for the actual call
        call_kwargs = {**payload, **kwargs}

        # Handle both sync and async functions
        if asyncio.iscoroutinefunction(tool_fn):
            result = await asyncio.wait_for(
                tool_fn(**call_kwargs),
                timeout=timeout_seconds,
            )
        else:
            # Wrap sync function in executor
            loop = asyncio.get_event_loop()
            result = await asyncio.wait_for(
                loop.run_in_executor(None, functools.partial(tool_fn, **call_kwargs)),
                timeout=timeout_seconds,
            )

        completed_at = utc_now()

        exec_context.completed_at = completed_at
        exec_context.success = True
        exec_context.result_summary = str(result)[:500] if result else None

        if tool_registry:
            tool_registry.record_execution(exec_context)

        logger.info(f"Tool execution successful: {tool_name or description}")

        return ToolExecutionResult(
            success=True,
            result=result,
            execution_id=execution_id,
            started_at=started_at,
            completed_at=completed_at,
            approval_required=needs_approval,
            approval_granted=approval_granted,
            risk_assessment=risk_assessment,
        )

    except (asyncio.TimeoutError, TimeoutError):
        logger.error(f"Tool execution timed out: {tool_name or description}")

        exec_context.completed_at = utc_now()
        exec_context.success = False
        exec_context.error = f"Timeout after {timeout_seconds}s"

        if tool_registry:
            tool_registry.record_execution(exec_context)

        return ToolExecutionResult(
            success=False,
            error=f"Timeout: execution timed out after {timeout_seconds} seconds",
            execution_id=execution_id,
            started_at=started_at,
            completed_at=exec_context.completed_at,
            approval_required=needs_approval,
            approval_granted=approval_granted,
            risk_assessment=risk_assessment,
        )

    except Exception as e:
        logger.error(f"Tool execution failed: {tool_name or description} - {e}")

        exec_context.completed_at = utc_now()
        exec_context.success = False
        exec_context.error = str(e)

        if tool_registry:
            tool_registry.record_execution(exec_context)

        return ToolExecutionResult(
            success=False,
            error=str(e),
            execution_id=execution_id,
            started_at=started_at,
            completed_at=exec_context.completed_at,
            approval_required=needs_approval,
            approval_granted=approval_granted,
            risk_assessment=risk_assessment,
        )


def tool(
    name: str,
    description: str,
    risk_level: ToolRiskLevel = ToolRiskLevel.MEDIUM,
    action_type: ActionType | None = None,
    is_reversible: bool = True,
    estimated_cost_usd: float = 0.0,
    affected_systems: list[str] | None = None,
):
    """
    Decorator to register a function as a guarded tool.

    Usage:
        @tool(
            name="delete_user",
            description="Delete a user from the database",
            risk_level=ToolRiskLevel.HIGH,
            is_reversible=False,
        )
        async def delete_user(user_id: str) -> bool:
            # Implementation
            return True
    """

    def decorator(fn: Callable) -> Callable:
        registry = get_tool_registry()
        registry.register(
            name=name,
            fn=fn,
            description=description,
            risk_level=risk_level,
            action_type=action_type,
            is_reversible=is_reversible,
            estimated_cost_usd=estimated_cost_usd,
            affected_systems=affected_systems,
        )

        @functools.wraps(fn)
        async def wrapper(*args, **kwargs):
            # When called directly, execute without guards (for testing)
            # In production, use registry.execute() for guarded calls
            if asyncio.iscoroutinefunction(fn):
                return await fn(*args, **kwargs)
            else:
                return fn(*args, **kwargs)

        # Attach metadata for introspection
        wrapper._tool_metadata = registry.get(name)[1]  # type: ignore
        wrapper._tool_name = name  # type: ignore

        return wrapper

    return decorator
