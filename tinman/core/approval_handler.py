"""Approval Handler - bridges agents with human approval interfaces.

This is the central coordination point for all HITL (Human-in-the-Loop) approvals.
It connects:
- Agents that need approval for risky actions
- RiskEvaluator that determines what needs approval
- ApprovalGate that tracks pending/approved/rejected requests
- UI (TUI, CLI, or callbacks) that presents approvals to humans
"""

import asyncio
import threading
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from ..config.modes import Mode
from ..utils import generate_id, get_logger, utc_now
from .approval_gate import ApprovalGate, ApprovalStatus
from .event_bus import EventBus, Topics
from .risk_evaluator import Action, ActionType, RiskAssessment, RiskEvaluator, RiskTier, Severity

logger = get_logger("approval_handler")


class ApprovalMode(str, Enum):
    """How approvals are handled."""

    INTERACTIVE = "interactive"  # Block and wait for human (TUI/CLI)
    ASYNC = "async"  # Non-blocking, use callbacks
    AUTO_APPROVE = "auto_approve"  # Auto-approve everything (dangerous!)
    AUTO_REJECT = "auto_reject"  # Auto-reject everything (safe but limiting)


@dataclass
class ApprovalContext:
    """Full context for an approval request."""

    id: str = field(default_factory=generate_id)

    # What's being requested
    action_type: ActionType = ActionType.CONFIG_CHANGE
    action_description: str = ""
    action_details: dict[str, Any] = field(default_factory=dict)

    # Risk assessment
    risk_assessment: RiskAssessment | None = None
    risk_tier: RiskTier = RiskTier.SAFE
    severity: Severity = Severity.S0

    # Cost/impact estimates
    estimated_cost_usd: float | None = None
    estimated_duration_ms: int | None = None
    affected_systems: list[str] = field(default_factory=list)

    # Rollback info
    is_reversible: bool = True
    rollback_plan: str = ""

    # Source
    requester_agent: str = ""
    requester_session: str = ""

    # Timing
    created_at: datetime = field(default_factory=utc_now)
    timeout_seconds: int = 300  # 5 minute default timeout

    # Result (filled after decision)
    status: ApprovalStatus = ApprovalStatus.PENDING
    decided_at: datetime | None = None
    decided_by: str | None = None
    decision_reason: str | None = None


# Type for approval UI callback
ApprovalUICallback = Callable[[ApprovalContext], Awaitable[bool]]


class ApprovalHandler:
    """
    Central handler for all approval flows in Tinman.

    This class:
    1. Evaluates whether actions need approval (via RiskEvaluator)
    2. Creates approval requests (via ApprovalGate)
    3. Presents them to humans (via registered UI callback)
    4. Waits for and returns the decision

    Usage:
        handler = ApprovalHandler(mode=Mode.LAB)

        # Register UI (TUI or CLI will do this)
        handler.register_ui(my_approval_callback)

        # Agents call this before risky actions
        approved = await handler.request_approval(
            action_type=ActionType.PROMPT_MUTATION,
            description="Inject safety prefix into system prompt",
            details={"prefix": "Always be helpful..."},
            estimated_cost_usd=0.50,
            requester_agent="intervention_engine",
        )

        if approved:
            # Proceed with action
        else:
            # Abort or use fallback
    """

    def __init__(
        self,
        mode: Mode = Mode.LAB,
        approval_mode: ApprovalMode = ApprovalMode.INTERACTIVE,
        risk_evaluator: RiskEvaluator | None = None,
        approval_gate: ApprovalGate | None = None,
        event_bus: EventBus | None = None,
        auto_approve_in_lab: bool = True,
        cost_threshold_usd: float = 5.0,
    ):
        self.mode = mode
        self.approval_mode = approval_mode
        self.risk_evaluator = risk_evaluator or RiskEvaluator()
        self.approval_gate = approval_gate or ApprovalGate(event_bus=event_bus)
        self.event_bus = event_bus
        self.auto_approve_in_lab = auto_approve_in_lab
        self.cost_threshold_usd = cost_threshold_usd

        # UI callback for presenting approvals
        self._ui_callback: ApprovalUICallback | None = None
        self._fallback_callback: ApprovalUICallback | None = None

        # Pending approvals (for async mode)
        self._pending: dict[str, ApprovalContext] = {}
        self._pending_futures: dict[str, asyncio.Future] = {}
        self._lock = threading.Lock()

        # Statistics
        self._stats = {
            "total_requests": 0,
            "auto_approved": 0,
            "human_approved": 0,
            "human_rejected": 0,
            "auto_rejected": 0,
            "timed_out": 0,
            "blocked": 0,
        }

        logger.info(
            f"ApprovalHandler initialized: mode={mode.value}, approval_mode={approval_mode.value}"
        )

    def register_ui(self, callback: ApprovalUICallback) -> None:
        """
        Register the UI callback for presenting approvals.

        The callback receives an ApprovalContext and should:
        1. Present the approval request to the user
        2. Wait for user decision
        3. Return True (approved) or False (rejected)

        For TUI: This shows the modal dialog
        For CLI: This shows a prompt and waits for input
        """
        self._ui_callback = callback
        logger.info("UI callback registered for approvals")

    def register_fallback(self, callback: ApprovalUICallback) -> None:
        """Register fallback UI (e.g., CLI when TUI not available)."""
        self._fallback_callback = callback
        logger.info("Fallback callback registered for approvals")

    def unregister_ui(self) -> None:
        """Unregister the UI callback."""
        self._ui_callback = None
        logger.info("UI callback unregistered")

    async def request_approval(
        self,
        action_type: ActionType,
        description: str,
        details: dict[str, Any] | None = None,
        estimated_cost_usd: float | None = None,
        estimated_duration_ms: int | None = None,
        affected_systems: list[str] | None = None,
        is_reversible: bool = True,
        rollback_plan: str = "",
        requester_agent: str = "",
        requester_session: str = "",
        predicted_severity: Severity = Severity.S1,
        timeout_seconds: int = 300,
        force_approval: bool = False,
    ) -> bool:
        """
        Request approval for an action.

        This is the main entry point for agents. It:
        1. Evaluates risk
        2. Determines if approval is needed
        3. If needed, presents to human and waits
        4. Returns True (proceed) or False (abort)

        Args:
            action_type: Type of action (from ActionType enum)
            description: Human-readable description of what will happen
            details: Additional details dict
            estimated_cost_usd: Estimated cost in USD
            estimated_duration_ms: Estimated duration
            affected_systems: List of systems affected
            is_reversible: Whether action can be undone
            rollback_plan: Description of how to rollback
            requester_agent: Which agent is requesting
            requester_session: Session ID
            predicted_severity: Predicted severity (S0-S4)
            timeout_seconds: How long to wait for approval

        Returns:
            True if approved (proceed), False if rejected (abort)
        """
        self._stats["total_requests"] += 1

        # Build action for risk evaluation
        action = Action(
            action_type=action_type,
            target_surface=self.mode.value,
            payload=details or {},
            predicted_severity=predicted_severity,
            estimated_cost=estimated_cost_usd or 0.0,
            estimated_latency_ms=estimated_duration_ms or 0,
            is_reversible=is_reversible,
        )

        # Evaluate risk
        risk_assessment = self.risk_evaluator.evaluate(action, self.mode)

        logger.info(
            f"Risk evaluation: action={action_type.value}, "
            f"tier={risk_assessment.tier.value}, severity={risk_assessment.severity.value}"
        )

        # Handle based on tier
        if risk_assessment.tier == RiskTier.BLOCK:
            logger.warning(f"Action BLOCKED: {description}")
            self._stats["blocked"] += 1
            self._publish_event("blocked", action_type, description, risk_assessment)
            return False

        if risk_assessment.tier == RiskTier.SAFE and not force_approval:
            # Auto-approve safe actions (unless approval is explicitly forced)
            if risk_assessment.auto_approve:
                logger.info(f"Auto-approved (SAFE): {description}")
                self._stats["auto_approved"] += 1
                self._publish_event("auto_approved", action_type, description, risk_assessment)
                return True

        # REVIEW tier - needs human approval
        # But check if we should auto-approve in lab mode (unless approval is explicitly forced)
        if self.mode == Mode.LAB and self.auto_approve_in_lab and not force_approval:
            logger.info(f"Auto-approved (LAB mode): {description}")
            self._stats["auto_approved"] += 1
            self._publish_event("auto_approved", action_type, description, risk_assessment)
            return True

        # Check approval mode
        if self.approval_mode == ApprovalMode.AUTO_APPROVE:
            logger.warning(f"Auto-approved (AUTO_APPROVE mode): {description}")
            self._stats["auto_approved"] += 1
            return True

        if self.approval_mode == ApprovalMode.AUTO_REJECT:
            logger.info(f"Auto-rejected (AUTO_REJECT mode): {description}")
            self._stats["auto_rejected"] += 1
            return False

        # Build approval context
        context = ApprovalContext(
            action_type=action_type,
            action_description=description,
            action_details=details or {},
            risk_assessment=risk_assessment,
            risk_tier=risk_assessment.tier,
            severity=risk_assessment.severity,
            estimated_cost_usd=estimated_cost_usd,
            estimated_duration_ms=estimated_duration_ms,
            affected_systems=affected_systems or [],
            is_reversible=is_reversible,
            rollback_plan=rollback_plan,
            requester_agent=requester_agent,
            requester_session=requester_session,
            timeout_seconds=timeout_seconds,
        )

        # Create approval request in gate
        gate_request = self.approval_gate.request_approval(
            intervention_id=context.id,
            risk_summary=f"{risk_assessment.tier.value.upper()}: {risk_assessment.reasoning}",
            impact_summary=description,
            rollback_plan=rollback_plan,
            risk_assessment=risk_assessment,
            ttl_hours=timeout_seconds / 3600,
        )

        # Store pending
        with self._lock:
            self._pending[context.id] = context

        # Publish event
        self._publish_event("pending", action_type, description, risk_assessment, context.id)

        # Present to human
        try:
            approved = await self._present_to_human(context)
        except TimeoutError:
            logger.warning(f"Approval timed out: {description}")
            self._stats["timed_out"] += 1
            approved = False
        except Exception as e:
            logger.error(f"Approval error: {e}")
            approved = False
        finally:
            # Clean up pending
            with self._lock:
                self._pending.pop(context.id, None)

        # Update context and gate
        context.status = ApprovalStatus.APPROVED if approved else ApprovalStatus.REJECTED
        context.decided_at = utc_now()

        if approved:
            self.approval_gate.approve(gate_request.id, "human", context.decision_reason)
            self._stats["human_approved"] += 1
            self._publish_event("approved", action_type, description, risk_assessment, context.id)
            logger.info(f"APPROVED by human: {description}")
        else:
            self.approval_gate.reject(
                gate_request.id, "human", context.decision_reason or "Rejected"
            )
            self._stats["human_rejected"] += 1
            self._publish_event("rejected", action_type, description, risk_assessment, context.id)
            logger.info(f"REJECTED by human: {description}")

        return approved

    async def _present_to_human(self, context: ApprovalContext) -> bool:
        """Present approval request to human via registered UI."""
        # Try primary UI
        if self._ui_callback:
            try:
                return await asyncio.wait_for(
                    self._ui_callback(context),
                    timeout=context.timeout_seconds,
                )
            except Exception as e:
                logger.warning(f"Primary UI failed: {e}, trying fallback")

        # Try fallback UI
        if self._fallback_callback:
            try:
                return await asyncio.wait_for(
                    self._fallback_callback(context),
                    timeout=context.timeout_seconds,
                )
            except Exception as e:
                logger.error(f"Fallback UI also failed: {e}")

        # No UI available - use default behavior
        logger.warning("No UI available for approval - using default (reject)")
        return False

    def _publish_event(
        self,
        event_type: str,
        action_type: ActionType,
        description: str,
        risk_assessment: RiskAssessment,
        context_id: str | None = None,
    ) -> None:
        """Publish approval event to event bus."""
        if not self.event_bus:
            return

        topic_map = {
            "pending": Topics.APPROVAL_REQUESTED,
            "approved": Topics.INTERVENTION_APPROVED,
            "rejected": Topics.INTERVENTION_REJECTED,
            "auto_approved": Topics.INTERVENTION_APPROVED,
            "blocked": Topics.INTERVENTION_REJECTED,
        }

        topic = topic_map.get(event_type)
        if topic:
            self.event_bus.publish(
                topic,
                {
                    "event_type": event_type,
                    "action_type": action_type.value,
                    "description": description,
                    "risk_tier": risk_assessment.tier.value,
                    "severity": risk_assessment.severity.value,
                    "context_id": context_id,
                    "timestamp": utc_now().isoformat(),
                },
            )

    def get_pending(self) -> list[ApprovalContext]:
        """Get all pending approval requests."""
        with self._lock:
            return list(self._pending.values())

    def get_stats(self) -> dict[str, Any]:
        """Get approval statistics."""
        return {
            **self._stats,
            "pending_count": len(self._pending),
            "gate_stats": self.approval_gate.get_stats(),
        }

    # Convenience methods for common approval types

    async def approve_experiment(
        self,
        experiment_name: str,
        hypothesis: str,
        estimated_runs: int,
        estimated_cost_usd: float,
        stress_type: str,
        requester_agent: str = "experiment_executor",
    ) -> bool:
        """Request approval for running an experiment."""
        return await self.request_approval(
            action_type=ActionType.CONFIG_CHANGE,  # Experiments are config-level
            description=f"Run experiment: {experiment_name}",
            details={
                "experiment_name": experiment_name,
                "hypothesis": hypothesis,
                "estimated_runs": estimated_runs,
                "stress_type": stress_type,
            },
            estimated_cost_usd=estimated_cost_usd,
            is_reversible=True,
            rollback_plan="Experiment results can be discarded",
            requester_agent=requester_agent,
            predicted_severity=Severity.S1,
        )

    async def approve_intervention(
        self,
        intervention_type: str,
        target_failure: str,
        description: str,
        is_reversible: bool,
        rollback_plan: str,
        estimated_effect: float,
        requester_agent: str = "intervention_engine",
    ) -> bool:
        """Request approval for deploying an intervention."""
        # Interventions are higher risk
        severity = Severity.S2 if is_reversible else Severity.S3

        return await self.request_approval(
            action_type=ActionType.PROMPT_MUTATION,
            description=f"Deploy intervention: {description}",
            details={
                "intervention_type": intervention_type,
                "target_failure": target_failure,
                "estimated_effect": estimated_effect,
            },
            is_reversible=is_reversible,
            rollback_plan=rollback_plan,
            requester_agent=requester_agent,
            predicted_severity=severity,
        )

    async def approve_simulation(
        self,
        failure_id: str,
        intervention_id: str,
        trace_count: int,
        estimated_cost_usd: float,
        requester_agent: str = "simulation_engine",
    ) -> bool:
        """Request approval for running a simulation."""
        return await self.request_approval(
            action_type=ActionType.CONFIG_CHANGE,
            description=f"Run simulation: replay {trace_count} traces with intervention",
            details={
                "failure_id": failure_id,
                "intervention_id": intervention_id,
                "trace_count": trace_count,
            },
            estimated_cost_usd=estimated_cost_usd,
            is_reversible=True,
            rollback_plan="Simulation is read-only, no changes to revert",
            requester_agent=requester_agent,
            predicted_severity=Severity.S0,  # Simulations are safe
        )

    async def approve_tool_policy_change(
        self,
        tool_name: str,
        change_description: str,
        is_reversible: bool,
        requester_agent: str = "intervention_engine",
    ) -> bool:
        """Request approval for changing tool policies."""
        return await self.request_approval(
            action_type=ActionType.TOOL_POLICY_CHANGE,
            description=f"Change tool policy: {tool_name} - {change_description}",
            details={
                "tool_name": tool_name,
                "change": change_description,
            },
            is_reversible=is_reversible,
            rollback_plan="Revert to previous policy"
            if is_reversible
            else "Manual intervention required",
            requester_agent=requester_agent,
            predicted_severity=Severity.S3,  # Tool policy changes are high risk
        )


# CLI approval callback (for when TUI is not available)
async def cli_approval_callback(context: ApprovalContext) -> bool:
    """
    CLI-based approval prompt.

    Shows approval request details and prompts user for Y/N.
    """

    print("\n" + "=" * 60)
    print("  APPROVAL REQUIRED")
    print("=" * 60)
    print(f"\nAction: {context.action_description}")
    print(f"Type: {context.action_type.value}")
    print(f"Risk: {context.risk_tier.value.upper()} (Severity: {context.severity.value})")

    if context.estimated_cost_usd:
        print(f"Estimated Cost: ${context.estimated_cost_usd:.2f}")

    if context.risk_assessment:
        print(f"Reasoning: {context.risk_assessment.reasoning}")

    if context.action_details:
        print(f"Details: {context.action_details}")

    if context.rollback_plan:
        print(f"Rollback: {context.rollback_plan}")

    print("\n" + "-" * 60)

    # Non-blocking input with timeout
    print("Approve? [y/N]: ", end="", flush=True)

    # Simple blocking input for CLI
    try:
        response = input().strip().lower()
        approved = response in ("y", "yes")
        context.decision_reason = "Approved by user" if approved else "Rejected by user"
        return approved
    except (EOFError, KeyboardInterrupt):
        print("\nApproval cancelled")
        context.decision_reason = "Cancelled by user"
        return False


# Default handler instance (can be replaced)
_default_handler: ApprovalHandler | None = None


def get_approval_handler() -> ApprovalHandler:
    """Get the default approval handler instance."""
    global _default_handler
    if _default_handler is None:
        _default_handler = ApprovalHandler()
    return _default_handler


def set_approval_handler(handler: ApprovalHandler) -> None:
    """Set the default approval handler instance."""
    global _default_handler
    _default_handler = handler
