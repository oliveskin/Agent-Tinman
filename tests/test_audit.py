"""Tests for audit logging system."""

import pytest
from datetime import datetime, timedelta

from tinman.db.audit import (
    AuditLog,
    AuditEventType,
    ApprovalDecision,
    ModeTransition,
    ToolExecution,
    AuditLogger,
)


class TestAuditEventTypes:
    """Test audit event type enumeration."""

    def test_approval_events_defined(self):
        """Approval event types should be defined."""
        assert AuditEventType.APPROVAL_REQUESTED.value == "approval_requested"
        assert AuditEventType.APPROVAL_GRANTED.value == "approval_granted"
        assert AuditEventType.APPROVAL_DENIED.value == "approval_denied"
        assert AuditEventType.APPROVAL_TIMEOUT.value == "approval_timeout"

    def test_mode_events_defined(self):
        """Mode event types should be defined."""
        assert AuditEventType.MODE_TRANSITION.value == "mode_transition"
        assert AuditEventType.MODE_TRANSITION_BLOCKED.value == "mode_transition_blocked"

    def test_tool_events_defined(self):
        """Tool event types should be defined."""
        assert AuditEventType.TOOL_EXECUTION_START.value == "tool_execution_start"
        assert AuditEventType.TOOL_EXECUTION_SUCCESS.value == "tool_execution_success"
        assert AuditEventType.TOOL_EXECUTION_FAILURE.value == "tool_execution_failure"
        assert AuditEventType.TOOL_EXECUTION_BLOCKED.value == "tool_execution_blocked"


class TestAuditLogger:
    """Test the AuditLogger class."""

    def test_log_event(self, db_session):
        """Should log basic events."""
        logger = AuditLogger(db_session)
        logger.set_context("session-123", "lab")

        entry = logger.log_event(
            event_type=AuditEventType.SYSTEM_START,
            actor_type="system",
            event_data={"version": "1.0.0"},
        )

        db_session.commit()

        assert entry.id is not None
        assert entry.event_type == "system_start"
        assert entry.session_id == "session-123"
        assert entry.mode == "lab"
        assert entry.event_data["version"] == "1.0.0"

    def test_log_approval_decision(self, db_session):
        """Should log approval decisions."""
        logger = AuditLogger(db_session)
        logger.set_context("session-456", "production")

        decision = logger.log_approval_decision(
            request_id="req-001",
            action_type="prompt_mutation",
            action_description="Modify system prompt",
            risk_tier="review",
            severity="S2",
            decision="approved",
            decided_by="human@example.com",
            decision_reason="Looks safe",
            estimated_cost_usd=0.50,
        )

        db_session.commit()

        assert decision.id is not None
        assert decision.request_id == "req-001"
        assert decision.decision == "approved"
        assert decision.decided_by == "human@example.com"
        assert decision.mode == "production"

    def test_log_mode_transition(self, db_session):
        """Should log mode transitions."""
        logger = AuditLogger(db_session)
        logger.set_context("session-789", "lab")

        transition = logger.log_mode_transition(
            from_mode="lab",
            to_mode="shadow",
            success=True,
            initiated_by="admin@example.com",
            reason="Ready for shadow testing",
        )

        db_session.commit()

        assert transition.id is not None
        assert transition.from_mode == "lab"
        assert transition.to_mode == "shadow"
        assert transition.success is True

    def test_log_tool_execution(self, db_session):
        """Should log tool executions."""
        logger = AuditLogger(db_session)
        logger.set_context("session-abc", "lab")

        execution = logger.log_tool_execution(
            execution_id="exec-001",
            tool_name="delete_user",
            action_type="destructive_tool_call",
            description="Delete user account",
            mode="lab",
            input_params={"user_id": "123"},
            risk_tier="block",
            severity="S4",
            success=False,
            blocked=True,
            block_reason="Destructive calls blocked",
        )

        db_session.commit()

        assert execution.id is not None
        assert execution.tool_name == "delete_user"
        assert execution.blocked is True
        assert execution.success is False

    def test_sanitize_sensitive_params(self, db_session):
        """Should sanitize sensitive parameters."""
        logger = AuditLogger(db_session)

        sensitive_params = {
            "user_id": "123",
            "password": "secret123",
            "api_key": "sk-12345",
            "data": {
                "token": "jwt-token",
                "name": "visible",
            },
        }

        execution = logger.log_tool_execution(
            execution_id="exec-002",
            tool_name="auth_tool",
            action_type="config_change",
            description="Auth operation",
            mode="lab",
            input_params=sensitive_params,
            success=True,
        )

        db_session.commit()

        # Check that sensitive fields are redacted
        params = execution.input_params
        assert params["user_id"] == "123"  # Not sensitive
        assert params["password"] == "[REDACTED]"
        assert params["api_key"] == "[REDACTED]"
        assert params["data"]["token"] == "[REDACTED]"
        assert params["data"]["name"] == "visible"


class TestAuditQueries:
    """Test audit query methods."""

    def test_get_recent_events(self, db_session):
        """Should retrieve recent events."""
        logger = AuditLogger(db_session)

        # Log several events
        for i in range(5):
            logger.log_event(
                event_type=AuditEventType.CONFIG_CHANGE,
                actor_type="system",
                event_data={"index": i},
            )

        db_session.commit()

        events = logger.get_recent_events(limit=3)
        assert len(events) == 3

    def test_get_events_by_type(self, db_session):
        """Should filter events by type."""
        logger = AuditLogger(db_session)

        logger.log_event(event_type=AuditEventType.SYSTEM_START, actor_type="system")
        logger.log_event(event_type=AuditEventType.CONFIG_CHANGE, actor_type="system")
        logger.log_event(event_type=AuditEventType.CONFIG_CHANGE, actor_type="system")

        db_session.commit()

        events = logger.get_recent_events(event_type=AuditEventType.CONFIG_CHANGE)
        assert len(events) == 2
        assert all(e.event_type == "config_change" for e in events)

    def test_get_approval_decisions_by_mode(self, db_session):
        """Should filter approvals by mode."""
        logger = AuditLogger(db_session)
        logger.set_context("s1", "lab")

        logger.log_approval_decision(
            request_id="r1",
            action_type="config_change",
            action_description="Lab change",
            risk_tier="safe",
            severity="S0",
            decision="approved",
        )

        logger.set_context("s2", "production")
        logger.log_approval_decision(
            request_id="r2",
            action_type="prompt_mutation",
            action_description="Prod change",
            risk_tier="review",
            severity="S2",
            decision="rejected",
        )

        db_session.commit()

        prod_decisions = logger.get_approval_decisions(mode="production")
        assert len(prod_decisions) == 1
        assert prod_decisions[0].mode == "production"

    def test_get_audit_summary(self, db_session):
        """Should generate audit summary."""
        logger = AuditLogger(db_session)
        logger.set_context("summary-session", "lab")

        # Create various events
        logger.log_event(event_type=AuditEventType.SYSTEM_START, actor_type="system")
        logger.log_approval_decision(
            request_id="r1",
            action_type="test",
            action_description="test",
            risk_tier="safe",
            severity="S0",
            decision="approved",
        )
        logger.log_tool_execution(
            execution_id="e1",
            tool_name="tool1",
            action_type="test",
            description="test",
            mode="lab",
            success=True,
        )

        db_session.commit()

        summary = logger.get_audit_summary()

        assert summary["total_events"] >= 2  # audit log entries
        assert "events_by_type" in summary
        assert "approval_decisions" in summary
        assert "tool_executions" in summary


class TestAuditImmutability:
    """Test audit log immutability guarantees."""

    def test_audit_log_has_timestamp(self, db_session):
        """Audit logs should have automatic timestamps."""
        logger = AuditLogger(db_session)

        before = datetime.utcnow()
        entry = logger.log_event(
            event_type=AuditEventType.SYSTEM_START,
            actor_type="system",
        )
        db_session.commit()
        after = datetime.utcnow()

        assert entry.timestamp >= before
        assert entry.timestamp <= after

    def test_approval_decision_links_to_audit(self, db_session):
        """Approval decisions should link to audit log."""
        logger = AuditLogger(db_session)

        decision = logger.log_approval_decision(
            request_id="r-link",
            action_type="test",
            action_description="test",
            risk_tier="safe",
            severity="S0",
            decision="approved",
        )

        db_session.commit()

        assert decision.audit_log_id is not None

        # Verify the linked audit log exists
        audit_entry = db_session.query(AuditLog).filter_by(id=decision.audit_log_id).first()
        assert audit_entry is not None


class TestToolExecutionAudit:
    """Test tool execution audit records."""

    def test_successful_execution_logged(self, db_session):
        """Successful executions should be logged."""
        logger = AuditLogger(db_session)

        start_time = datetime.utcnow()
        execution = logger.log_tool_execution(
            execution_id="success-001",
            tool_name="safe_tool",
            action_type="config_change",
            description="Safe operation",
            mode="lab",
            success=True,
            started_at=start_time,
            completed_at=datetime.utcnow(),
            duration_ms=150,
        )

        db_session.commit()

        assert execution.success is True
        assert execution.blocked is False
        assert execution.duration_ms == 150

    def test_blocked_execution_logged(self, db_session):
        """Blocked executions should be logged."""
        logger = AuditLogger(db_session)

        execution = logger.log_tool_execution(
            execution_id="blocked-001",
            tool_name="dangerous_tool",
            action_type="destructive_tool_call",
            description="Dangerous operation",
            mode="production",
            success=False,
            blocked=True,
            block_reason="Destructive calls blocked in production",
            risk_tier="block",
            severity="S4",
        )

        db_session.commit()

        assert execution.success is False
        assert execution.blocked is True
        assert "production" in execution.block_reason

    def test_query_tool_executions(self, db_session):
        """Should query tool executions with filters."""
        logger = AuditLogger(db_session)

        # Log some executions
        logger.log_tool_execution(
            execution_id="e1",
            tool_name="tool_a",
            action_type="test",
            description="test",
            mode="lab",
            success=True,
        )
        logger.log_tool_execution(
            execution_id="e2",
            tool_name="tool_a",
            action_type="test",
            description="test",
            mode="lab",
            success=False,
            error_message="Failed",
        )
        logger.log_tool_execution(
            execution_id="e3",
            tool_name="tool_b",
            action_type="test",
            description="test",
            mode="lab",
            success=True,
        )

        db_session.commit()

        # Query by tool name
        tool_a_execs = logger.get_tool_executions(tool_name="tool_a")
        assert len(tool_a_execs) == 2

        # Query by success
        successful = logger.get_tool_executions(success=True)
        assert len(successful) == 2

        # Query failed
        failed = logger.get_tool_executions(success=False)
        assert len(failed) == 1
