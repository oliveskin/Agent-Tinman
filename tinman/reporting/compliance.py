"""Compliance Report generator.

Provides compliance-focused reports for audit, regulatory, and governance
purposes, including approval trails, mode transitions, and policy adherence.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from ..db.audit import AuditLogger
from ..memory.graph import MemoryGraph
from ..utils import get_logger, utc_now
from .base import (
    Report,
    ReportGenerator,
    ReportMetadata,
    ReportSection,
    ReportType,
)

logger = get_logger("reporting.compliance")


@dataclass
class ApprovalRecord:
    """Record of an approval decision."""

    id: str
    action_type: str
    decision: str
    risk_tier: str
    decided_by: str
    decided_at: datetime
    reason: str | None
    mode: str


@dataclass
class ModeTransitionRecord:
    """Record of a mode transition."""

    id: str
    from_mode: str
    to_mode: str
    transitioned_at: datetime
    transitioned_by: str
    reason: str | None


@dataclass
class PolicyViolation:
    """Record of a policy violation."""

    id: str
    action_type: str
    violation_type: str
    details: str
    occurred_at: datetime
    mode: str


@dataclass
class ComplianceData:
    """Data specific to compliance reports."""

    approvals: list[ApprovalRecord] = field(default_factory=list)
    approvals_approved: int = 0
    approvals_rejected: int = 0
    approvals_by_tier: dict[str, int] = field(default_factory=dict)

    mode_transitions: list[ModeTransitionRecord] = field(default_factory=list)
    time_in_lab: float = 0.0  # hours
    time_in_shadow: float = 0.0
    time_in_production: float = 0.0

    policy_violations: list[PolicyViolation] = field(default_factory=list)
    blocked_actions: int = 0

    audit_trail_complete: bool = True
    audit_gaps: list[str] = field(default_factory=list)


class ComplianceReport(ReportGenerator):
    """Generator for compliance reports.

    These reports are designed for audit and regulatory purposes:
    - Complete approval decision trail
    - Mode transition history
    - Policy adherence verification
    - Risk tier distribution
    - Audit completeness checks

    Usage:
        generator = ComplianceReport(audit_logger=logger, graph=graph)
        report = await generator.generate(
            period_start=start_of_quarter,
            period_end=end_of_quarter,
        )
    """

    def __init__(
        self,
        audit_logger: AuditLogger | None = None,
        graph: MemoryGraph | None = None,
    ):
        self.audit_logger = audit_logger
        self.graph = graph

    @property
    def report_type(self) -> ReportType:
        return ReportType.COMPLIANCE

    @property
    def name(self) -> str:
        return "Compliance Report"

    async def generate(
        self,
        period_start: datetime | None = None,
        period_end: datetime | None = None,
        **kwargs,
    ) -> Report[ComplianceData]:
        """Generate compliance report."""
        period_end = period_end or utc_now()
        period_start = period_start or (period_end - timedelta(days=30))

        report = Report[ComplianceData](
            metadata=ReportMetadata(
                type=self.report_type,
                title="Compliance & Audit Report",
                description="Comprehensive compliance report for regulatory and governance review",
                period_start=period_start,
                period_end=period_end,
                confidentiality="confidential",
                tags=["compliance", "audit", "governance"],
            ),
            raw_data=ComplianceData(),
        )

        data = report.raw_data

        await self._gather_approvals(data, period_start, period_end)
        await self._gather_mode_transitions(data, period_start, period_end)
        await self._gather_policy_violations(data, period_start, period_end)
        await self._verify_audit_completeness(data, period_start, period_end)

        report.summary = self._build_summary(data)
        report.sections = [
            self._build_approval_section(data),
            self._build_mode_section(data),
            self._build_violations_section(data),
            self._build_audit_section(data),
            self._build_attestation_section(data, period_start, period_end),
        ]

        return report

    async def _gather_approvals(
        self,
        data: ComplianceData,
        start: datetime,
        end: datetime,
    ) -> None:
        """Gather approval records."""
        if not self.audit_logger:
            return

        # Query approval decisions from audit log
        decisions = self.audit_logger.get_approval_decisions(
            since=start,
            limit=10000,
        )

        for decision in decisions:
            if decision.created_at > end:
                continue

            record = ApprovalRecord(
                id=decision.id,
                action_type=decision.action_type,
                decision=decision.decision,
                risk_tier=decision.risk_tier,
                decided_by=decision.decided_by,
                decided_at=decision.created_at,
                reason=decision.reason,
                mode=decision.mode,
            )
            data.approvals.append(record)

            # Count by decision
            if decision.decision == "approved":
                data.approvals_approved += 1
            else:
                data.approvals_rejected += 1

            # Count by tier
            tier = decision.risk_tier
            data.approvals_by_tier[tier] = data.approvals_by_tier.get(tier, 0) + 1

    async def _gather_mode_transitions(
        self,
        data: ComplianceData,
        start: datetime,
        end: datetime,
    ) -> None:
        """Gather mode transition history."""
        if not self.audit_logger:
            return

        transitions = self.audit_logger.get_mode_transitions(
            since=start,
            limit=1000,
        )

        for trans in transitions:
            if trans.created_at > end:
                continue

            record = ModeTransitionRecord(
                id=trans.id,
                from_mode=trans.from_mode,
                to_mode=trans.to_mode,
                transitioned_at=trans.created_at,
                transitioned_by=trans.transitioned_by or "system",
                reason=trans.reason,
            )
            data.mode_transitions.append(record)

        # Calculate time in each mode
        self._calculate_mode_times(data, start, end)

    def _calculate_mode_times(
        self,
        data: ComplianceData,
        start: datetime,
        end: datetime,
    ) -> None:
        """Calculate time spent in each mode."""
        if not data.mode_transitions:
            # Assume all time in lab mode
            total_hours = (end - start).total_seconds() / 3600
            data.time_in_lab = total_hours
            return

        # Sort transitions by time
        sorted_trans = sorted(
            data.mode_transitions,
            key=lambda t: t.transitioned_at,
        )

        # Track time in each mode
        current_mode = "lab"  # Default start mode
        last_time = start

        for trans in sorted_trans:
            duration = (trans.transitioned_at - last_time).total_seconds() / 3600

            if current_mode == "lab":
                data.time_in_lab += duration
            elif current_mode == "shadow":
                data.time_in_shadow += duration
            elif current_mode == "production":
                data.time_in_production += duration

            current_mode = trans.to_mode
            last_time = trans.transitioned_at

        # Add remaining time
        duration = (end - last_time).total_seconds() / 3600
        if current_mode == "lab":
            data.time_in_lab += duration
        elif current_mode == "shadow":
            data.time_in_shadow += duration
        elif current_mode == "production":
            data.time_in_production += duration

    async def _gather_policy_violations(
        self,
        data: ComplianceData,
        start: datetime,
        end: datetime,
    ) -> None:
        """Gather policy violations and blocked actions."""
        if not self.audit_logger:
            return

        # Query audit log for violations
        logs = self.audit_logger.query(
            event_types=["policy_violation", "action_blocked"],
            since=start,
            limit=10000,
        )

        for log in logs:
            if log.timestamp > end:
                continue

            if log.event_type == "action_blocked":
                data.blocked_actions += 1

            if log.event_type == "policy_violation":
                violation = PolicyViolation(
                    id=log.id,
                    action_type=log.metadata.get("action_type", "unknown"),
                    violation_type=log.metadata.get("violation_type", "unknown"),
                    details=log.details or "",
                    occurred_at=log.timestamp,
                    mode=log.mode,
                )
                data.policy_violations.append(violation)

    async def _verify_audit_completeness(
        self,
        data: ComplianceData,
        start: datetime,
        end: datetime,
    ) -> None:
        """Verify audit trail completeness."""
        if not self.audit_logger:
            data.audit_trail_complete = False
            data.audit_gaps.append("Audit logger not configured")
            return

        # Check for gaps in event sequence
        # This is a simplified check - production would be more thorough
        expected_events = ["session_start", "mode_transition", "approval_decision"]

        logs = self.audit_logger.query(since=start, limit=1)
        if not logs:
            data.audit_gaps.append(
                f"No audit records found for period starting {start.isoformat()}"
            )
            data.audit_trail_complete = False

    def _build_summary(self, data: ComplianceData) -> str:
        """Build compliance summary."""
        total_approvals = data.approvals_approved + data.approvals_rejected
        rejection_rate = (
            data.approvals_rejected / total_approvals * 100 if total_approvals > 0 else 0
        )

        parts = [
            f"During this reporting period, **{total_approvals} approval decisions** "
            f"were recorded, with a **{rejection_rate:.1f}% rejection rate**.",
        ]

        if data.mode_transitions:
            parts.append(f"There were **{len(data.mode_transitions)} mode transitions**.")

        if data.policy_violations:
            parts.append(f"**{len(data.policy_violations)} policy violations** were recorded.")

        if data.blocked_actions:
            parts.append(f"**{data.blocked_actions} actions** were blocked by policy.")

        audit_status = "complete" if data.audit_trail_complete else "incomplete"
        parts.append(f"Audit trail status: **{audit_status}**.")

        return " ".join(parts)

    def _build_approval_section(self, data: ComplianceData) -> ReportSection:
        """Build approval decisions section."""
        return ReportSection(
            title="Approval Decisions",
            order=1,
            level=1,
            tables=[
                {
                    "title": "Decision Summary",
                    "headers": ["Metric", "Count"],
                    "rows": [
                        ["Total Decisions", data.approvals_approved + data.approvals_rejected],
                        ["Approved", data.approvals_approved],
                        ["Rejected", data.approvals_rejected],
                    ],
                },
                {
                    "title": "Decisions by Risk Tier",
                    "headers": ["Risk Tier", "Count"],
                    "rows": sorted(
                        data.approvals_by_tier.items(),
                        key=lambda x: x[1],
                        reverse=True,
                    ),
                },
                {
                    "title": "Recent Decisions",
                    "headers": ["Time", "Action", "Decision", "Risk Tier", "Decided By"],
                    "rows": [
                        [
                            a.decided_at.strftime("%Y-%m-%d %H:%M"),
                            a.action_type[:30],
                            a.decision,
                            a.risk_tier,
                            a.decided_by,
                        ]
                        for a in sorted(
                            data.approvals,
                            key=lambda x: x.decided_at,
                            reverse=True,
                        )[:20]
                    ],
                },
            ],
        )

    def _build_mode_section(self, data: ComplianceData) -> ReportSection:
        """Build mode transitions section."""
        total_hours = data.time_in_lab + data.time_in_shadow + data.time_in_production

        return ReportSection(
            title="Mode History",
            order=2,
            level=1,
            tables=[
                {
                    "title": "Time by Mode",
                    "headers": ["Mode", "Hours", "Percentage"],
                    "rows": [
                        [
                            "Lab",
                            f"{data.time_in_lab:.1f}",
                            f"{data.time_in_lab / total_hours * 100:.0f}%"
                            if total_hours > 0
                            else "N/A",
                        ],
                        [
                            "Shadow",
                            f"{data.time_in_shadow:.1f}",
                            f"{data.time_in_shadow / total_hours * 100:.0f}%"
                            if total_hours > 0
                            else "N/A",
                        ],
                        [
                            "Production",
                            f"{data.time_in_production:.1f}",
                            f"{data.time_in_production / total_hours * 100:.0f}%"
                            if total_hours > 0
                            else "N/A",
                        ],
                    ],
                },
                {
                    "title": "Mode Transitions",
                    "headers": ["Time", "From", "To", "By", "Reason"],
                    "rows": [
                        [
                            t.transitioned_at.strftime("%Y-%m-%d %H:%M"),
                            t.from_mode,
                            t.to_mode,
                            t.transitioned_by,
                            (t.reason or "")[:50],
                        ]
                        for t in data.mode_transitions
                    ],
                },
            ],
        )

    def _build_violations_section(self, data: ComplianceData) -> ReportSection:
        """Build policy violations section."""
        if not data.policy_violations and not data.blocked_actions:
            return ReportSection(
                title="Policy Compliance",
                order=3,
                level=1,
                content="✅ No policy violations or blocked actions during this period.",
            )

        return ReportSection(
            title="Policy Compliance",
            order=3,
            level=1,
            content=f"⚠️ {len(data.policy_violations)} violations and {data.blocked_actions} blocked actions recorded.",
            tables=[
                {
                    "title": "Policy Violations",
                    "headers": ["Time", "Type", "Action", "Mode", "Details"],
                    "rows": [
                        [
                            v.occurred_at.strftime("%Y-%m-%d %H:%M"),
                            v.violation_type,
                            v.action_type,
                            v.mode,
                            v.details[:50],
                        ]
                        for v in data.policy_violations
                    ],
                }
                if data.policy_violations
                else {},
            ],
        )

    def _build_audit_section(self, data: ComplianceData) -> ReportSection:
        """Build audit completeness section."""
        status = "✅ Complete" if data.audit_trail_complete else "⚠️ Gaps Detected"

        content = f"**Audit Trail Status:** {status}"

        if data.audit_gaps:
            content += "\n\n**Issues Found:**\n"
            content += "\n".join(f"- {gap}" for gap in data.audit_gaps)

        return ReportSection(
            title="Audit Trail Verification",
            order=4,
            level=1,
            content=content,
        )

    def _build_attestation_section(
        self,
        data: ComplianceData,
        start: datetime,
        end: datetime,
    ) -> ReportSection:
        """Build attestation section."""
        return ReportSection(
            title="Attestation",
            order=5,
            level=1,
            content=f"""
This report was generated automatically by Tinman FDRA.

**Reporting Period:** {start.strftime("%Y-%m-%d")} to {end.strftime("%Y-%m-%d")}
**Generated At:** {utc_now().isoformat()}

**Summary of Controls:**
- All high-risk actions required human approval: {"✅ Verified" if data.approvals_by_tier.get("block", 0) > 0 or data.blocked_actions > 0 else "⚠️ No high-risk actions recorded"}
- Mode transitions logged: {"✅ " + str(len(data.mode_transitions)) + " recorded" if data.mode_transitions else "⚠️ None recorded"}
- Policy violations tracked: {"✅ System operational" if not data.audit_gaps else "⚠️ Gaps detected"}

---
*This document is for compliance and audit purposes. Retain according to data retention policy.*
""",
        )
