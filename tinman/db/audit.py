"""Durable audit logging for Tinman FDRA.

This module provides persistent audit trails for:
- Approval decisions (who approved/rejected what, when, why)
- Mode transitions (when mode changed, by whom)
- Tool executions (what tools ran, with what parameters, what results)
- Risk assessments (what risks were identified, how they were handled)

The audit log is immutable - records can only be appended, never modified or deleted.
This provides a complete history for compliance, debugging, and analysis.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional
from enum import Enum
import json
import uuid

from sqlalchemy import (
    Column,
    String,
    Text,
    Float,
    Integer,
    Boolean,
    DateTime,
    Index,
    event,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy import JSON

JSONType = JSON().with_variant(JSONB, "postgresql")
from sqlalchemy.orm import Session

from .models import Base
from ..utils import get_logger, utc_now

logger = get_logger("audit")


def generate_uuid():
    return str(uuid.uuid4())


class AuditEventType(str, Enum):
    """Types of audit events."""
    # Approval events
    APPROVAL_REQUESTED = "approval_requested"
    APPROVAL_GRANTED = "approval_granted"
    APPROVAL_DENIED = "approval_denied"
    APPROVAL_TIMEOUT = "approval_timeout"
    APPROVAL_AUTO = "approval_auto"

    # Mode events
    MODE_TRANSITION = "mode_transition"
    MODE_TRANSITION_BLOCKED = "mode_transition_blocked"

    # Tool execution events
    TOOL_EXECUTION_START = "tool_execution_start"
    TOOL_EXECUTION_SUCCESS = "tool_execution_success"
    TOOL_EXECUTION_FAILURE = "tool_execution_failure"
    TOOL_EXECUTION_BLOCKED = "tool_execution_blocked"
    TOOL_EXECUTION_TIMEOUT = "tool_execution_timeout"

    # Risk events
    RISK_ASSESSMENT = "risk_assessment"
    RISK_ESCALATION = "risk_escalation"

    # Research cycle events
    RESEARCH_CYCLE_START = "research_cycle_start"
    RESEARCH_CYCLE_END = "research_cycle_end"
    HYPOTHESIS_GENERATED = "hypothesis_generated"
    EXPERIMENT_RUN = "experiment_run"
    FAILURE_DISCOVERED = "failure_discovered"
    INTERVENTION_PROPOSED = "intervention_proposed"
    SIMULATION_RUN = "simulation_run"

    # System events
    SYSTEM_START = "system_start"
    SYSTEM_SHUTDOWN = "system_shutdown"
    CONFIG_CHANGE = "config_change"
    POLICY_UPDATE = "policy_update"


class AuditLog(Base):
    """Immutable audit log table.

    This table stores all audit events with full context.
    Records cannot be modified or deleted (enforced by triggers if needed).
    """
    __tablename__ = "audit_log"

    id = Column(UUID(as_uuid=False), primary_key=True, default=generate_uuid)
    timestamp = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, index=True)
    event_type = Column(String(50), nullable=False, index=True)

    # Actor information
    actor_type = Column(String(50), nullable=False)  # human, agent, system
    actor_id = Column(String(100), nullable=True)  # user ID, agent name, etc.

    # Session context
    session_id = Column(String(100), nullable=True, index=True)
    mode = Column(String(20), nullable=True, index=True)

    # Event target
    target_type = Column(String(50), nullable=True)  # tool, approval, mode, etc.
    target_id = Column(String(100), nullable=True)

    # Event details
    severity = Column(String(5), nullable=True)
    risk_tier = Column(String(10), nullable=True)
    action_type = Column(String(50), nullable=True)

    # Full event data (JSON)
    event_data = Column(JSONType, nullable=False, default=dict)

    # Result information
    success = Column(Boolean, nullable=True)
    error_message = Column(Text, nullable=True)

    # Timing
    duration_ms = Column(Integer, nullable=True)

    # Cost tracking
    estimated_cost_usd = Column(Float, nullable=True)
    actual_cost_usd = Column(Float, nullable=True)

    __table_args__ = (
        Index("idx_audit_event_type", "event_type"),
        Index("idx_audit_timestamp", "timestamp"),
        Index("idx_audit_session", "session_id"),
        Index("idx_audit_actor", "actor_type", "actor_id"),
        Index("idx_audit_target", "target_type", "target_id"),
        Index("idx_audit_mode_time", "mode", "timestamp"),
    )


class ApprovalDecision(Base):
    """Dedicated table for approval decisions.

    This provides a focused view of all approval decisions,
    linked to the main audit log for full context.
    """
    __tablename__ = "approval_decisions"

    id = Column(UUID(as_uuid=False), primary_key=True, default=generate_uuid)
    audit_log_id = Column(UUID(as_uuid=False), nullable=True)  # Link to audit_log
    timestamp = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, index=True)

    # Request information
    request_id = Column(String(100), nullable=False, index=True)
    action_type = Column(String(50), nullable=False)
    action_description = Column(Text, nullable=False)

    # Risk assessment
    risk_tier = Column(String(10), nullable=False)
    severity = Column(String(5), nullable=False)
    risk_reasoning = Column(Text, nullable=True)

    # Decision
    decision = Column(String(20), nullable=False, index=True)  # approved, rejected, timeout, auto
    decided_by = Column(String(100), nullable=True)
    decided_at = Column(DateTime(timezone=True), nullable=True)
    decision_reason = Column(Text, nullable=True)

    # Context
    mode = Column(String(20), nullable=False)
    session_id = Column(String(100), nullable=True)
    requester_agent = Column(String(100), nullable=True)

    # Cost/impact
    estimated_cost_usd = Column(Float, nullable=True)
    affected_systems = Column(JSONType, nullable=True)
    rollback_plan = Column(Text, nullable=True)

    __table_args__ = (
        Index("idx_approval_decision", "decision"),
        Index("idx_approval_timestamp", "timestamp"),
        Index("idx_approval_request", "request_id"),
        Index("idx_approval_mode_time", "mode", "timestamp"),
    )


class ModeTransition(Base):
    """Record of mode transitions.

    Tracks when and why the system changed modes.
    """
    __tablename__ = "mode_transitions"

    id = Column(UUID(as_uuid=False), primary_key=True, default=generate_uuid)
    audit_log_id = Column(UUID(as_uuid=False), nullable=True)
    timestamp = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, index=True)

    # Transition details
    from_mode = Column(String(20), nullable=False)
    to_mode = Column(String(20), nullable=False)
    success = Column(Boolean, nullable=False)
    blocked_reason = Column(Text, nullable=True)

    # Actor
    initiated_by = Column(String(100), nullable=True)
    session_id = Column(String(100), nullable=True)

    # Context
    reason = Column(Text, nullable=True)
    transition_metadata = Column("metadata", JSONType, nullable=True)

    __table_args__ = (
        Index("idx_mode_transition_timestamp", "timestamp"),
        Index("idx_mode_transition_modes", "from_mode", "to_mode"),
    )


class ToolExecution(Base):
    """Record of tool executions.

    Tracks every guarded tool call with full context.
    """
    __tablename__ = "tool_executions"

    id = Column(UUID(as_uuid=False), primary_key=True, default=generate_uuid)
    audit_log_id = Column(UUID(as_uuid=False), nullable=True)
    execution_id = Column(String(100), nullable=False, index=True)
    timestamp = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, index=True)

    # Tool information
    tool_name = Column(String(100), nullable=False, index=True)
    action_type = Column(String(50), nullable=False)
    description = Column(Text, nullable=True)

    # Execution context
    mode = Column(String(20), nullable=False)
    session_id = Column(String(100), nullable=True)
    requester_agent = Column(String(100), nullable=True)

    # Input/output (sanitized - no secrets)
    input_params = Column(JSONType, nullable=True)
    output_summary = Column(Text, nullable=True)

    # Risk assessment
    risk_tier = Column(String(10), nullable=True)
    severity = Column(String(5), nullable=True)

    # Approval
    approval_required = Column(Boolean, nullable=False, default=False)
    approval_granted = Column(Boolean, nullable=True)
    approval_decision_id = Column(UUID(as_uuid=False), nullable=True)

    # Result
    success = Column(Boolean, nullable=False)
    error_message = Column(Text, nullable=True)
    blocked = Column(Boolean, nullable=False, default=False)
    block_reason = Column(Text, nullable=True)

    # Timing and cost
    started_at = Column(DateTime(timezone=True), nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    duration_ms = Column(Integer, nullable=True)
    estimated_cost_usd = Column(Float, nullable=True)
    actual_cost_usd = Column(Float, nullable=True)

    __table_args__ = (
        Index("idx_tool_exec_timestamp", "timestamp"),
        Index("idx_tool_exec_name", "tool_name"),
        Index("idx_tool_exec_mode", "mode"),
        Index("idx_tool_exec_success", "success"),
    )


class AuditLogger:
    """High-level interface for audit logging.

    This class provides a clean API for recording audit events,
    handling all the database operations internally.
    """

    def __init__(self, session: Session):
        self.session = session
        self._session_id: Optional[str] = None
        self._mode: Optional[str] = None

    def set_context(self, session_id: str, mode: str) -> None:
        """Set the current context for audit logs."""
        self._session_id = session_id
        self._mode = mode

    def log_event(
        self,
        event_type: AuditEventType,
        actor_type: str = "system",
        actor_id: Optional[str] = None,
        target_type: Optional[str] = None,
        target_id: Optional[str] = None,
        severity: Optional[str] = None,
        risk_tier: Optional[str] = None,
        action_type: Optional[str] = None,
        event_data: Optional[dict[str, Any]] = None,
        success: Optional[bool] = None,
        error_message: Optional[str] = None,
        duration_ms: Optional[int] = None,
        estimated_cost_usd: Optional[float] = None,
        actual_cost_usd: Optional[float] = None,
    ) -> AuditLog:
        """Log a generic audit event."""
        log_entry = AuditLog(
            event_type=event_type.value,
            actor_type=actor_type,
            actor_id=actor_id,
            session_id=self._session_id,
            mode=self._mode,
            target_type=target_type,
            target_id=target_id,
            severity=severity,
            risk_tier=risk_tier,
            action_type=action_type,
            event_data=event_data or {},
            success=success,
            error_message=error_message,
            duration_ms=duration_ms,
            estimated_cost_usd=estimated_cost_usd,
            actual_cost_usd=actual_cost_usd,
        )

        self.session.add(log_entry)
        self.session.flush()

        logger.debug(f"Audit log: {event_type.value} (id={log_entry.id})")

        return log_entry

    def log_approval_decision(
        self,
        request_id: str,
        action_type: str,
        action_description: str,
        risk_tier: str,
        severity: str,
        decision: str,
        decided_by: Optional[str] = None,
        decision_reason: Optional[str] = None,
        risk_reasoning: Optional[str] = None,
        requester_agent: Optional[str] = None,
        estimated_cost_usd: Optional[float] = None,
        affected_systems: Optional[list[str]] = None,
        rollback_plan: Optional[str] = None,
    ) -> ApprovalDecision:
        """Log an approval decision."""
        # First create audit log entry
        audit_entry = self.log_event(
            event_type=AuditEventType.APPROVAL_GRANTED if decision == "approved" else AuditEventType.APPROVAL_DENIED,
            actor_type="human" if decided_by else "system",
            actor_id=decided_by,
            target_type="approval",
            target_id=request_id,
            risk_tier=risk_tier,
            severity=severity,
            action_type=action_type,
            event_data={
                "action_description": action_description,
                "decision": decision,
                "decision_reason": decision_reason,
            },
            success=decision == "approved",
            estimated_cost_usd=estimated_cost_usd,
        )

        # Then create approval decision record
        decision_entry = ApprovalDecision(
            audit_log_id=audit_entry.id,
            request_id=request_id,
            action_type=action_type,
            action_description=action_description,
            risk_tier=risk_tier,
            severity=severity,
            risk_reasoning=risk_reasoning,
            decision=decision,
            decided_by=decided_by,
            decided_at=utc_now() if decided_by else None,
            decision_reason=decision_reason,
            mode=self._mode or "unknown",
            session_id=self._session_id,
            requester_agent=requester_agent,
            estimated_cost_usd=estimated_cost_usd,
            affected_systems=affected_systems,
            rollback_plan=rollback_plan,
        )

        self.session.add(decision_entry)
        self.session.flush()

        logger.info(f"Approval decision logged: {decision} for {request_id}")

        return decision_entry

    def log_mode_transition(
        self,
        from_mode: str,
        to_mode: str,
        success: bool,
        initiated_by: Optional[str] = None,
        reason: Optional[str] = None,
        blocked_reason: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> ModeTransition:
        """Log a mode transition."""
        event_type = AuditEventType.MODE_TRANSITION if success else AuditEventType.MODE_TRANSITION_BLOCKED

        audit_entry = self.log_event(
            event_type=event_type,
            actor_type="human" if initiated_by else "system",
            actor_id=initiated_by,
            target_type="mode",
            target_id=to_mode,
            event_data={
                "from_mode": from_mode,
                "to_mode": to_mode,
                "reason": reason,
                "blocked_reason": blocked_reason,
            },
            success=success,
            error_message=blocked_reason,
        )

        transition_entry = ModeTransition(
            audit_log_id=audit_entry.id,
            from_mode=from_mode,
            to_mode=to_mode,
            success=success,
            blocked_reason=blocked_reason,
            initiated_by=initiated_by,
            session_id=self._session_id,
            reason=reason,
            transition_metadata=metadata,
        )

        self.session.add(transition_entry)
        self.session.flush()

        logger.info(f"Mode transition logged: {from_mode} -> {to_mode} (success={success})")

        return transition_entry

    def log_tool_execution(
        self,
        execution_id: str,
        tool_name: str,
        action_type: str,
        description: str,
        mode: str,
        input_params: Optional[dict[str, Any]] = None,
        output_summary: Optional[str] = None,
        risk_tier: Optional[str] = None,
        severity: Optional[str] = None,
        approval_required: bool = False,
        approval_granted: Optional[bool] = None,
        approval_decision_id: Optional[str] = None,
        success: bool = False,
        error_message: Optional[str] = None,
        blocked: bool = False,
        block_reason: Optional[str] = None,
        started_at: Optional[datetime] = None,
        completed_at: Optional[datetime] = None,
        duration_ms: Optional[int] = None,
        estimated_cost_usd: Optional[float] = None,
        actual_cost_usd: Optional[float] = None,
        requester_agent: Optional[str] = None,
    ) -> ToolExecution:
        """Log a tool execution."""
        # Determine event type
        if blocked:
            event_type = AuditEventType.TOOL_EXECUTION_BLOCKED
        elif error_message and "timeout" in error_message.lower():
            event_type = AuditEventType.TOOL_EXECUTION_TIMEOUT
        elif success:
            event_type = AuditEventType.TOOL_EXECUTION_SUCCESS
        else:
            event_type = AuditEventType.TOOL_EXECUTION_FAILURE

        # Sanitize input params (remove potential secrets)
        safe_params = self._sanitize_params(input_params) if input_params else None

        audit_entry = self.log_event(
            event_type=event_type,
            actor_type="agent",
            actor_id=requester_agent,
            target_type="tool",
            target_id=tool_name,
            risk_tier=risk_tier,
            severity=severity,
            action_type=action_type,
            event_data={
                "execution_id": execution_id,
                "description": description,
                "blocked": blocked,
                "block_reason": block_reason,
            },
            success=success,
            error_message=error_message,
            duration_ms=duration_ms,
            estimated_cost_usd=estimated_cost_usd,
            actual_cost_usd=actual_cost_usd,
        )

        exec_entry = ToolExecution(
            audit_log_id=audit_entry.id,
            execution_id=execution_id,
            tool_name=tool_name,
            action_type=action_type,
            description=description,
            mode=mode,
            session_id=self._session_id,
            requester_agent=requester_agent,
            input_params=safe_params,
            output_summary=output_summary[:500] if output_summary else None,
            risk_tier=risk_tier,
            severity=severity,
            approval_required=approval_required,
            approval_granted=approval_granted,
            approval_decision_id=approval_decision_id,
            success=success,
            error_message=error_message,
            blocked=blocked,
            block_reason=block_reason,
            started_at=started_at or utc_now(),
            completed_at=completed_at,
            duration_ms=duration_ms,
            estimated_cost_usd=estimated_cost_usd,
            actual_cost_usd=actual_cost_usd,
        )

        self.session.add(exec_entry)
        self.session.flush()

        logger.debug(f"Tool execution logged: {tool_name} (success={success})")

        return exec_entry

    def _sanitize_params(self, params: dict[str, Any]) -> dict[str, Any]:
        """Remove potential secrets from parameters."""
        sensitive_keys = {
            "password", "secret", "token", "api_key", "apikey",
            "auth", "credential", "private", "key",
        }

        def sanitize(obj: Any, depth: int = 0) -> Any:
            if depth > 10:  # Prevent infinite recursion
                return "[TRUNCATED]"

            if isinstance(obj, dict):
                return {
                    k: "[REDACTED]" if any(s in k.lower() for s in sensitive_keys) else sanitize(v, depth + 1)
                    for k, v in obj.items()
                }
            elif isinstance(obj, list):
                return [sanitize(item, depth + 1) for item in obj[:100]]  # Limit list size
            elif isinstance(obj, str) and len(obj) > 1000:
                return obj[:1000] + "[TRUNCATED]"
            else:
                return obj

        return sanitize(params)

    # Query methods for retrieving audit data

    def get_recent_events(
        self,
        event_type: Optional[AuditEventType] = None,
        limit: int = 100,
    ) -> list[AuditLog]:
        """Get recent audit events."""
        query = self.session.query(AuditLog)

        if event_type:
            query = query.filter(AuditLog.event_type == event_type.value)

        return query.order_by(AuditLog.timestamp.desc()).limit(limit).all()

    def get_approval_decisions(
        self,
        mode: Optional[str] = None,
        decision: Optional[str] = None,
        since: Optional[datetime] = None,
        limit: int = 100,
    ) -> list[ApprovalDecision]:
        """Get approval decisions with filters."""
        query = self.session.query(ApprovalDecision)

        if mode:
            query = query.filter(ApprovalDecision.mode == mode)
        if decision:
            query = query.filter(ApprovalDecision.decision == decision)
        if since:
            query = query.filter(ApprovalDecision.timestamp >= since)

        return query.order_by(ApprovalDecision.timestamp.desc()).limit(limit).all()

    def get_mode_transitions(
        self,
        since: Optional[datetime] = None,
        limit: int = 100,
    ) -> list[ModeTransition]:
        """Get mode transitions."""
        query = self.session.query(ModeTransition)

        if since:
            query = query.filter(ModeTransition.timestamp >= since)

        return query.order_by(ModeTransition.timestamp.desc()).limit(limit).all()

    def get_tool_executions(
        self,
        tool_name: Optional[str] = None,
        success: Optional[bool] = None,
        since: Optional[datetime] = None,
        limit: int = 100,
    ) -> list[ToolExecution]:
        """Get tool executions with filters."""
        query = self.session.query(ToolExecution)

        if tool_name:
            query = query.filter(ToolExecution.tool_name == tool_name)
        if success is not None:
            query = query.filter(ToolExecution.success == success)
        if since:
            query = query.filter(ToolExecution.timestamp >= since)

        return query.order_by(ToolExecution.timestamp.desc()).limit(limit).all()

    def get_audit_summary(self, since: Optional[datetime] = None) -> dict[str, Any]:
        """Get summary statistics from audit log."""
        from sqlalchemy import func

        query = self.session.query(AuditLog)
        if since:
            query = query.filter(AuditLog.timestamp >= since)

        total = query.count()

        # Count by event type
        by_type = (
            query
            .with_entities(AuditLog.event_type, func.count(AuditLog.id))
            .group_by(AuditLog.event_type)
            .all()
        )

        # Count approvals
        approvals = self.session.query(ApprovalDecision)
        if since:
            approvals = approvals.filter(ApprovalDecision.timestamp >= since)

        approval_stats = (
            approvals
            .with_entities(ApprovalDecision.decision, func.count(ApprovalDecision.id))
            .group_by(ApprovalDecision.decision)
            .all()
        )

        # Count tool executions
        tools = self.session.query(ToolExecution)
        if since:
            tools = tools.filter(ToolExecution.timestamp >= since)

        tool_stats = {
            "total": tools.count(),
            "successful": tools.filter(ToolExecution.success == True).count(),
            "blocked": tools.filter(ToolExecution.blocked == True).count(),
        }

        return {
            "total_events": total,
            "events_by_type": dict(by_type),
            "approval_decisions": dict(approval_stats),
            "tool_executions": tool_stats,
            "since": since.isoformat() if since else "all_time",
        }


# Global audit logger instance
_audit_logger: Optional[AuditLogger] = None


def get_audit_logger(session: Optional[Session] = None) -> Optional[AuditLogger]:
    """Get the global audit logger instance."""
    global _audit_logger
    if session and _audit_logger is None:
        _audit_logger = AuditLogger(session)
    return _audit_logger


def set_audit_logger(audit_logger: AuditLogger) -> None:
    """Set the global audit logger instance."""
    global _audit_logger
    _audit_logger = audit_logger
