"""Human approval gate for high-risk actions."""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional, Callable
import threading

from ..utils import generate_id, utc_now, get_logger
from .event_bus import EventBus, Topics
from .risk_evaluator import RiskAssessment

logger = get_logger("approval_gate")


class ApprovalStatus(str, Enum):
    """Status of an approval request."""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"


@dataclass
class ApprovalRequest:
    """A request for human approval."""
    id: str = field(default_factory=generate_id)
    intervention_id: str = ""
    risk_summary: str = ""
    impact_summary: str = ""
    rollback_plan: str = ""
    risk_assessment: Optional[RiskAssessment] = None
    status: ApprovalStatus = ApprovalStatus.PENDING
    created_at: datetime = field(default_factory=utc_now)
    expires_at: Optional[datetime] = None
    decided_at: Optional[datetime] = None
    decided_by: Optional[str] = None
    decision_reason: Optional[str] = None


class ApprovalGate:
    """
    Simple human approval gate for high-risk interventions.

    Features:
    - Queue pending approval requests
    - Approve/reject with reason tracking
    - Optional expiration
    - Callback notifications
    """

    def __init__(self, event_bus: Optional[EventBus] = None,
                 default_ttl_hours: int = 24):
        self.event_bus = event_bus
        self.default_ttl_hours = default_ttl_hours
        self._pending: dict[str, ApprovalRequest] = {}
        self._history: list[ApprovalRequest] = []
        self._lock = threading.Lock()
        self._approval_callbacks: list[Callable[[ApprovalRequest], None]] = []
        self._rejection_callbacks: list[Callable[[ApprovalRequest], None]] = []

    def request_approval(self,
                         intervention_id: str,
                         risk_summary: str,
                         impact_summary: str = "",
                         rollback_plan: str = "",
                         risk_assessment: Optional[RiskAssessment] = None,
                         ttl_hours: Optional[int] = None) -> ApprovalRequest:
        """
        Create a new approval request.

        Returns the created ApprovalRequest.
        """
        ttl = ttl_hours or self.default_ttl_hours
        expires_at = utc_now() + timedelta(hours=ttl) if ttl > 0 else None

        request = ApprovalRequest(
            intervention_id=intervention_id,
            risk_summary=risk_summary,
            impact_summary=impact_summary,
            rollback_plan=rollback_plan,
            risk_assessment=risk_assessment,
            expires_at=expires_at,
        )

        with self._lock:
            self._pending[request.id] = request

        logger.info(f"Approval request created: {request.id} for intervention {intervention_id}")
        return request

    def approve(self, request_id: str,
                approved_by: str,
                reason: Optional[str] = None) -> Optional[ApprovalRequest]:
        """
        Approve a pending request.

        Returns the updated request, or None if not found/already decided.
        """
        with self._lock:
            request = self._pending.get(request_id)
            if not request:
                logger.warning(f"Approval request not found: {request_id}")
                return None

            if request.status != ApprovalStatus.PENDING:
                logger.warning(f"Request already decided: {request_id}")
                return None

            # Check expiration
            if request.expires_at and utc_now() > request.expires_at:
                request.status = ApprovalStatus.EXPIRED
                self._move_to_history(request)
                logger.warning(f"Request expired: {request_id}")
                return None

            # Approve
            request.status = ApprovalStatus.APPROVED
            request.decided_at = utc_now()
            request.decided_by = approved_by
            request.decision_reason = reason
            self._move_to_history(request)

        logger.info(f"Request approved: {request_id} by {approved_by}")

        # Publish event
        if self.event_bus:
            self.event_bus.publish(
                Topics.INTERVENTION_APPROVED,
                {
                    "approval_id": request.id,
                    "intervention_id": request.intervention_id,
                    "approved_by": approved_by,
                    "reason": reason,
                },
            )

        # Notify callbacks
        for callback in self._approval_callbacks:
            try:
                callback(request)
            except Exception as e:
                logger.error(f"Error in approval callback: {e}")

        return request

    def reject(self, request_id: str,
               rejected_by: str,
               reason: str) -> Optional[ApprovalRequest]:
        """
        Reject a pending request.

        Returns the updated request, or None if not found/already decided.
        """
        with self._lock:
            request = self._pending.get(request_id)
            if not request:
                logger.warning(f"Approval request not found: {request_id}")
                return None

            if request.status != ApprovalStatus.PENDING:
                logger.warning(f"Request already decided: {request_id}")
                return None

            # Reject
            request.status = ApprovalStatus.REJECTED
            request.decided_at = utc_now()
            request.decided_by = rejected_by
            request.decision_reason = reason
            self._move_to_history(request)

        logger.info(f"Request rejected: {request_id} by {rejected_by}: {reason}")

        # Publish event
        if self.event_bus:
            self.event_bus.publish(
                Topics.INTERVENTION_REJECTED,
                {
                    "approval_id": request.id,
                    "intervention_id": request.intervention_id,
                    "rejected_by": rejected_by,
                    "reason": reason,
                },
            )

        # Notify callbacks
        for callback in self._rejection_callbacks:
            try:
                callback(request)
            except Exception as e:
                logger.error(f"Error in rejection callback: {e}")

        return request

    def _move_to_history(self, request: ApprovalRequest) -> None:
        """Move request from pending to history."""
        if request.id in self._pending:
            del self._pending[request.id]
        self._history.append(request)

    def get_pending(self) -> list[ApprovalRequest]:
        """Get all pending approval requests."""
        with self._lock:
            # Check for expired requests
            now = utc_now()
            expired = []
            for req in self._pending.values():
                if req.expires_at and now > req.expires_at:
                    req.status = ApprovalStatus.EXPIRED
                    expired.append(req)

            for req in expired:
                self._move_to_history(req)

            return list(self._pending.values())

    def get_request(self, request_id: str) -> Optional[ApprovalRequest]:
        """Get a specific request by ID."""
        with self._lock:
            if request_id in self._pending:
                return self._pending[request_id]
            for req in self._history:
                if req.id == request_id:
                    return req
            return None

    def get_history(self, limit: int = 100) -> list[ApprovalRequest]:
        """Get recent approval history."""
        with self._lock:
            return self._history[-limit:]

    def on_approval(self, callback: Callable[[ApprovalRequest], None]) -> None:
        """Register callback for approval events."""
        self._approval_callbacks.append(callback)

    def on_rejection(self, callback: Callable[[ApprovalRequest], None]) -> None:
        """Register callback for rejection events."""
        self._rejection_callbacks.append(callback)

    def get_stats(self) -> dict:
        """Get approval gate statistics."""
        with self._lock:
            approved = sum(1 for r in self._history if r.status == ApprovalStatus.APPROVED)
            rejected = sum(1 for r in self._history if r.status == ApprovalStatus.REJECTED)
            expired = sum(1 for r in self._history if r.status == ApprovalStatus.EXPIRED)

            return {
                "pending": len(self._pending),
                "approved": approved,
                "rejected": rejected,
                "expired": expired,
                "total_processed": len(self._history),
            }
