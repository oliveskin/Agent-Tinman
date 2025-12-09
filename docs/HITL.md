# Human-in-the-Loop (HITL) Approval System

This document provides complete documentation for Tinman's human-in-the-loop approval system, which ensures appropriate oversight of AI research and intervention decisions.

---

## Table of Contents

1. [Overview](#overview)
2. [Risk Tiers](#risk-tiers)
3. [Risk Evaluation](#risk-evaluation)
4. [Approval Flow](#approval-flow)
5. [Approval Handler](#approval-handler)
6. [Approval Modes](#approval-modes)
7. [UI Integration](#ui-integration)
8. [Custom Approval Workflows](#custom-approval-workflows)
9. [Best Practices](#best-practices)

---

## Overview

The HITL system is Tinman's safety mechanism that ensures humans remain in control of consequential decisions while allowing low-risk actions to proceed autonomously.

### Core Principles

1. **Risk-Proportionate Oversight** - More risky actions require more oversight
2. **Mode-Aware** - Approval requirements vary by operating mode
3. **Transparent** - All decisions are logged with reasoning
4. **Configurable** - Teams can customize approval thresholds
5. **Fail-Safe** - When in doubt, require approval

### System Components

```
┌─────────────────────────────────────────────────────────────────┐
│                    HITL SYSTEM ARCHITECTURE                      │
│                                                                  │
│  ┌──────────┐    ┌───────────────┐    ┌─────────────────┐      │
│  │  Agent   │───▶│   Approval    │───▶│ Risk Evaluator  │      │
│  │ Request  │    │   Handler     │    │                 │      │
│  └──────────┘    └───────┬───────┘    └────────┬────────┘      │
│                          │                      │                │
│                          │                      ▼                │
│                          │            ┌─────────────────┐       │
│                          │            │   RiskAssessment │       │
│                          │            │  (tier, severity)│       │
│                          │            └────────┬────────┘       │
│                          │                     │                 │
│                          ▼                     ▼                 │
│                  ┌───────────────┐    ┌─────────────────┐       │
│                  │ Approval Gate │◀───│ Decision Logic  │       │
│                  │  (tracking)   │    │ (SAFE/REVIEW/   │       │
│                  └───────┬───────┘    │  BLOCK)         │       │
│                          │            └─────────────────┘       │
│                          │                                       │
│                          ▼                                       │
│                  ┌───────────────┐                               │
│                  │  UI Callback  │                               │
│                  │ (TUI/CLI/API) │                               │
│                  └───────────────┘                               │
└─────────────────────────────────────────────────────────────────┘
```

---

## Risk Tiers

Every action in Tinman is classified into one of three risk tiers:

### SAFE

**Definition:** Low-risk actions that can proceed autonomously.

**Behavior:**
- Auto-approved without human interaction
- Logged for audit trail
- Publish event for monitoring

**Examples:**
- Running read-only experiments
- Generating hypotheses
- Creating reports
- S0-S1 severity findings

```python
RiskTier.SAFE  # Proceed autonomously
```

### REVIEW

**Definition:** Medium-risk actions requiring human approval.

**Behavior:**
- Presented to human via UI
- Waits for explicit approval/rejection
- Timeout defaults to rejection
- Full context provided for decision

**Examples:**
- Deploying prompt mutations
- Running costly experiments
- S2-S3 severity findings
- Any action in PRODUCTION mode

```python
RiskTier.REVIEW  # Requires human approval
```

### BLOCK

**Definition:** High-risk actions that are never allowed.

**Behavior:**
- Automatically rejected
- No human override available
- Logged with warning
- Alert generated

**Examples:**
- Destructive tool calls
- Safety filter modifications
- S4 severity findings
- Skip-mode transitions (LAB → PRODUCTION)

```python
RiskTier.BLOCK  # Always rejected
```

### Tier Decision Matrix

| Severity | LAB | SHADOW | PRODUCTION |
|----------|-----|--------|------------|
| S0 | SAFE | SAFE | SAFE |
| S1 | SAFE | SAFE | SAFE |
| S2 | SAFE | SAFE | REVIEW |
| S3 | REVIEW | REVIEW | REVIEW |
| S4 | REVIEW | BLOCK | BLOCK |

---

## Risk Evaluation

The `RiskEvaluator` component assesses actions and assigns risk tiers.

### Evaluation Process

```
Action
  │
  ├── Is action type blocked?
  │   └── Yes → BLOCK (S4)
  │
  ├── Affects safety filters?
  │   └── Yes → BLOCK (S4)
  │
  ├── Mode-specific evaluation
  │   ├── LAB → Usually SAFE
  │   ├── SHADOW → Review S3+
  │   └── PRODUCTION → Review S2+, certain types
  │
  └── Return RiskAssessment
```

### Action Types

```python
class ActionType(str, Enum):
    """Types of actions that can be risk-evaluated."""
    PROMPT_MUTATION = "prompt_mutation"         # Modify prompts
    TOOL_POLICY_CHANGE = "tool_policy_change"   # Change tool permissions
    MEMORY_GATING = "memory_gating"             # Modify memory access
    FINE_TUNE = "fine_tune"                     # Fine-tuning operations
    CONFIG_CHANGE = "config_change"             # Configuration changes
    DESTRUCTIVE_TOOL_CALL = "destructive_tool_call"  # Dangerous operations
    SAFETY_FILTER_CHANGE = "safety_filter_change"    # Safety modifications
```

### Blocked Actions

These action types are always blocked:

```python
BLOCKED_ACTIONS = {
    ActionType.DESTRUCTIVE_TOOL_CALL,
}
```

### Production-Review Actions

These action types always require review in PRODUCTION mode:

```python
REVIEW_REQUIRED_IN_PROD = {
    ActionType.PROMPT_MUTATION,
    ActionType.TOOL_POLICY_CHANGE,
    ActionType.SAFETY_FILTER_CHANGE,
    ActionType.FINE_TUNE,
}
```

### RiskAssessment Structure

```python
@dataclass
class RiskAssessment:
    """Result of risk evaluation."""
    tier: RiskTier              # SAFE, REVIEW, or BLOCK
    severity: Severity          # S0-S4
    reasoning: str              # Why this tier was assigned
    requires_approval: bool     # Whether human approval needed
    auto_approve: bool          # Whether to auto-approve if SAFE
    details: dict[str, Any]     # Additional context
```

### Using the RiskEvaluator

```python
from tinman.core.risk_evaluator import (
    RiskEvaluator, Action, ActionType, Severity
)
from tinman.config.modes import Mode

evaluator = RiskEvaluator(
    detailed_mode=False,        # Simple 3-tier model
    auto_approve_safe=True,     # Auto-approve SAFE actions
    block_on_destructive=True,  # Block destructive actions
)

# Create action to evaluate
action = Action(
    action_type=ActionType.PROMPT_MUTATION,
    target_surface="production",
    payload={"prompt": "New system prompt"},
    predicted_severity=Severity.S2,
    estimated_cost=0.50,
    is_reversible=True,
)

# Evaluate risk
assessment = evaluator.evaluate(action, Mode.PRODUCTION)

print(f"Tier: {assessment.tier}")           # RiskTier.REVIEW
print(f"Severity: {assessment.severity}")   # Severity.S2
print(f"Reasoning: {assessment.reasoning}") # "Action type prompt_mutation requires review in production"
```

### Severity Computation

For detailed severity scoring:

```python
severity = evaluator.compute_severity(
    failure_class="GOAL_DRIFT",
    reproducibility=0.8,        # 80% reproducible
    impact_scope=["chat", "api", "webhook"],
    is_safety_related=False,
)
# Returns appropriate S0-S4 based on criteria
```

---

## Approval Flow

### Complete Flow Diagram

```
Agent Action Request
        │
        ▼
┌───────────────────┐
│ ApprovalHandler   │
│ request_approval()│
└─────────┬─────────┘
          │
          ▼
┌───────────────────┐
│  RiskEvaluator    │
│  evaluate()       │
└─────────┬─────────┘
          │
          ▼
    ┌─────────────┐
    │ Risk Tier?  │
    └──────┬──────┘
           │
    ┌──────┼──────┬──────────┐
    │      │      │          │
    ▼      ▼      ▼          ▼
  BLOCK  SAFE   REVIEW    LAB+safe?
    │      │      │          │
    │      │      │          │
    ▼      ▼      │          ▼
 Reject  Auto    │      Auto-approve
 (log)   Approve │       (lab)
           │      │          │
           │      ▼          │
           │ ┌──────────┐    │
           │ │ Present  │    │
           │ │ to Human │    │
           │ └────┬─────┘    │
           │      │          │
           │   ┌──┴──┐       │
           │   ▼     ▼       │
           │ Approve Reject  │
           │   │      │      │
           └───┼──────┼──────┘
               │      │
               ▼      ▼
            Execute  Abort
```

### Flow Steps

1. **Agent Request** - Agent calls `request_approval()` with action details
2. **Risk Evaluation** - RiskEvaluator assesses the action
3. **Tier Dispatch** - Different handling based on tier
4. **Human Presentation** - For REVIEW, present to UI
5. **Decision** - Human approves or rejects
6. **Execution** - If approved, proceed; if rejected, abort

### Request Lifecycle

```
CREATED → PENDING → [APPROVED | REJECTED | TIMED_OUT | BLOCKED]
```

---

## Approval Handler

The `ApprovalHandler` is the central coordination point for all HITL approvals.

### Initialization

```python
from tinman.core.approval_handler import ApprovalHandler, ApprovalMode
from tinman.config.modes import Mode

handler = ApprovalHandler(
    mode=Mode.PRODUCTION,
    approval_mode=ApprovalMode.INTERACTIVE,
    auto_approve_in_lab=True,
    cost_threshold_usd=5.0,
)
```

### Constructor Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `mode` | `Mode` | `LAB` | Operating mode |
| `approval_mode` | `ApprovalMode` | `INTERACTIVE` | How approvals are handled |
| `risk_evaluator` | `RiskEvaluator` | `None` | Custom evaluator (created if None) |
| `approval_gate` | `ApprovalGate` | `None` | Custom gate (created if None) |
| `event_bus` | `EventBus` | `None` | For publishing events |
| `auto_approve_in_lab` | `bool` | `True` | Auto-approve REVIEW in LAB |
| `cost_threshold_usd` | `float` | `5.0` | Cost threshold for review |

### Request Approval

```python
approved = await handler.request_approval(
    action_type=ActionType.PROMPT_MUTATION,
    description="Inject safety prefix into system prompt",
    details={"prefix": "Always be helpful..."},
    estimated_cost_usd=0.50,
    estimated_duration_ms=100,
    affected_systems=["chat_api"],
    is_reversible=True,
    rollback_plan="Remove prefix from prompt",
    requester_agent="intervention_engine",
    predicted_severity=Severity.S2,
    timeout_seconds=300,
)

if approved:
    # Proceed with action
    pass
else:
    # Abort or use fallback
    pass
```

### Convenience Methods

```python
# Approve experiment execution
approved = await handler.approve_experiment(
    experiment_name="goal_drift_test",
    hypothesis="System loses track of goals in long conversations",
    estimated_runs=10,
    estimated_cost_usd=2.50,
    stress_type="CONTEXT_INJECTION",
)

# Approve intervention deployment
approved = await handler.approve_intervention(
    intervention_type="PROMPT_MUTATION",
    target_failure="goal_drift",
    description="Add periodic goal reinforcement",
    is_reversible=True,
    rollback_plan="Remove injection logic",
    estimated_effect=0.75,
)

# Approve simulation run
approved = await handler.approve_simulation(
    failure_id="fail_001",
    intervention_id="int_001",
    trace_count=50,
    estimated_cost_usd=1.00,
)

# Approve tool policy change
approved = await handler.approve_tool_policy_change(
    tool_name="database_query",
    change_description="Add rate limiting",
    is_reversible=True,
)
```

### Statistics

```python
stats = handler.get_stats()
print(stats)
# {
#     "total_requests": 100,
#     "auto_approved": 75,
#     "human_approved": 15,
#     "human_rejected": 5,
#     "auto_rejected": 0,
#     "timed_out": 3,
#     "blocked": 2,
#     "pending_count": 1,
#     "gate_stats": {...}
# }
```

---

## Approval Modes

The `ApprovalMode` enum controls how the handler processes approvals:

### INTERACTIVE

**Description:** Block and wait for human decision via UI.

**Use When:** TUI is running or CLI prompts are acceptable.

```python
ApprovalMode.INTERACTIVE
```

**Behavior:**
- Calls registered UI callback
- Blocks until decision or timeout
- Default behavior for PRODUCTION mode

### ASYNC

**Description:** Non-blocking approval via callbacks.

**Use When:** Integrating with external approval systems.

```python
ApprovalMode.ASYNC
```

**Behavior:**
- Returns immediately with pending status
- Callback invoked when decision made
- Good for Slack/email approval workflows

### AUTO_APPROVE

**Description:** Automatically approve all requests.

**Use When:** Testing, development, or trusted environments.

```python
ApprovalMode.AUTO_APPROVE
```

**Behavior:**
- All REVIEW tier requests are approved
- BLOCK tier still rejected
- ⚠️ **Dangerous in production!**

### AUTO_REJECT

**Description:** Automatically reject all requests.

**Use When:** Read-only mode or emergency lockdown.

```python
ApprovalMode.AUTO_REJECT
```

**Behavior:**
- All REVIEW tier requests are rejected
- SAFE tier still approved
- BLOCK tier still rejected

---

## UI Integration

### Registering UI Callback

The approval handler needs a UI callback to present approvals to humans:

```python
async def my_approval_ui(context: ApprovalContext) -> bool:
    """Custom approval UI implementation."""
    # Display approval request to user
    print(f"Approve: {context.action_description}?")

    # Get user decision (implement your UI here)
    response = await get_user_response()

    # Record reason
    context.decision_reason = "User approved" if response else "User rejected"

    return response

# Register the callback
handler.register_ui(my_approval_ui)
```

### ApprovalContext Structure

```python
@dataclass
class ApprovalContext:
    """Full context for an approval request."""
    id: str                              # Unique request ID

    # What's being requested
    action_type: ActionType              # Type of action
    action_description: str              # Human-readable description
    action_details: dict[str, Any]       # Additional details

    # Risk assessment
    risk_assessment: RiskAssessment      # Full assessment
    risk_tier: RiskTier                  # SAFE/REVIEW/BLOCK
    severity: Severity                   # S0-S4

    # Cost/impact estimates
    estimated_cost_usd: float            # Estimated cost
    estimated_duration_ms: int           # Estimated duration
    affected_systems: list[str]          # Systems affected

    # Rollback info
    is_reversible: bool                  # Can be undone?
    rollback_plan: str                   # How to undo

    # Source
    requester_agent: str                 # Which agent requested
    requester_session: str               # Session ID

    # Timing
    created_at: datetime                 # When created
    timeout_seconds: int                 # Approval timeout

    # Result (filled after decision)
    status: ApprovalStatus               # PENDING/APPROVED/REJECTED
    decided_at: datetime                 # When decided
    decided_by: str                      # Who decided
    decision_reason: str                 # Why decided
```

### TUI Approval Dialog

The TUI provides a modal approval dialog:

```
┌─────────────────────────────────────────────────────────────┐
│                    APPROVAL REQUIRED                         │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  Action: Deploy intervention: Add goal reinforcement         │
│  Type: prompt_mutation                                       │
│  Risk: REVIEW (Severity: S2)                                │
│                                                              │
│  Estimated Cost: $0.50                                       │
│  Affected Systems: chat_api, webhook                         │
│                                                              │
│  Reasoning: Action type prompt_mutation requires review      │
│             in production                                    │
│                                                              │
│  Rollback Plan: Remove injection logic                       │
│                                                              │
├─────────────────────────────────────────────────────────────┤
│         [Y] Approve              [N] Reject                  │
└─────────────────────────────────────────────────────────────┘
```

### CLI Approval Prompt

For CLI-based approval (when TUI is not available):

```python
from tinman.core.approval_handler import cli_approval_callback

handler.register_fallback(cli_approval_callback)
```

Output:
```
============================================================
  APPROVAL REQUIRED
============================================================

Action: Deploy intervention: Add goal reinforcement
Type: prompt_mutation
Risk: REVIEW (Severity: S2)
Estimated Cost: $0.50
Reasoning: Action type prompt_mutation requires review in production
Details: {'intervention_type': 'PROMPT_MUTATION', ...}
Rollback: Remove injection logic

------------------------------------------------------------
Approve? [y/N]: _
```

---

## Custom Approval Workflows

### External Approval System

Integrate with external approval systems (Slack, email, ticketing):

```python
class SlackApprovalHandler:
    """Approval via Slack."""

    def __init__(self, webhook_url: str, channel: str):
        self.webhook_url = webhook_url
        self.channel = channel
        self._pending: dict[str, asyncio.Future] = {}

    async def approval_callback(self, context: ApprovalContext) -> bool:
        """Send approval request to Slack and wait for response."""
        # Send to Slack
        message = self._format_message(context)
        await self._send_to_slack(message)

        # Wait for response (via webhook)
        future = asyncio.get_event_loop().create_future()
        self._pending[context.id] = future

        try:
            return await asyncio.wait_for(
                future,
                timeout=context.timeout_seconds
            )
        except asyncio.TimeoutError:
            return False

    def handle_slack_callback(self, request_id: str, approved: bool):
        """Called when user clicks approve/reject in Slack."""
        if request_id in self._pending:
            self._pending[request_id].set_result(approved)

# Usage
slack_handler = SlackApprovalHandler(
    webhook_url="https://hooks.slack.com/...",
    channel="#approvals"
)
handler.register_ui(slack_handler.approval_callback)
```

### Multi-Approver Workflow

Require multiple approvals for high-severity actions:

```python
class MultiApproverHandler:
    """Require multiple approvers for critical decisions."""

    def __init__(self, required_approvals: int = 2):
        self.required_approvals = required_approvals

    async def approval_callback(self, context: ApprovalContext) -> bool:
        # High severity needs more approvers
        required = self.required_approvals
        if context.severity >= Severity.S3:
            required += 1

        approvals = 0
        rejections = 0

        for i in range(required):
            response = await self._get_approval(context, approver_num=i+1)
            if response:
                approvals += 1
            else:
                rejections += 1

            # Early exit on rejection
            if rejections > 0:
                context.decision_reason = f"Rejected by approver {i+1}"
                return False

        context.decision_reason = f"Approved by {approvals} approvers"
        return True
```

### Audit Trail Enhancement

Add enhanced audit logging:

```python
class AuditingApprovalHandler(ApprovalHandler):
    """Approval handler with enhanced audit logging."""

    def __init__(self, audit_log_path: str, **kwargs):
        super().__init__(**kwargs)
        self.audit_log_path = audit_log_path

    async def request_approval(self, **kwargs) -> bool:
        # Log request
        self._log_audit_event("REQUEST", kwargs)

        # Get decision
        result = await super().request_approval(**kwargs)

        # Log decision
        self._log_audit_event(
            "APPROVED" if result else "REJECTED",
            kwargs
        )

        return result

    def _log_audit_event(self, event_type: str, data: dict):
        import json
        from datetime import datetime

        entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "event_type": event_type,
            "data": data,
        }

        with open(self.audit_log_path, "a") as f:
            f.write(json.dumps(entry) + "\n")
```

---

## Best Practices

### Approval Request Design

1. **Clear Descriptions** - Make `action_description` understandable by non-engineers
2. **Include Rollback** - Always provide `rollback_plan` for reversible actions
3. **Accurate Estimates** - Provide realistic cost and duration estimates
4. **Appropriate Severity** - Don't over- or under-estimate severity

```python
# Good
await handler.request_approval(
    action_type=ActionType.PROMPT_MUTATION,
    description="Add safety prefix to prevent harmful outputs in chat",
    details={
        "prefix": "You are a helpful assistant...",
        "target": "chat_system_prompt",
    },
    estimated_cost_usd=0.00,  # No direct cost
    is_reversible=True,
    rollback_plan="Remove prefix via config update",
    predicted_severity=Severity.S2,
)

# Bad
await handler.request_approval(
    action_type=ActionType.PROMPT_MUTATION,
    description="Change prompt",  # Too vague
    # Missing details, estimates, rollback plan
)
```

### Mode Selection

| Scenario | Recommended Mode |
|----------|------------------|
| Local development | `AUTO_APPROVE` |
| CI/CD testing | `AUTO_REJECT` |
| Staging environment | `INTERACTIVE` |
| Production | `INTERACTIVE` |
| External integration | `ASYNC` |

### Timeout Configuration

```yaml
approval:
  timeout_seconds: 300  # 5 minutes default

  # Per-severity timeouts
  timeouts:
    S0: 60      # 1 minute
    S1: 120     # 2 minutes
    S2: 300     # 5 minutes
    S3: 600     # 10 minutes
    S4: 1800    # 30 minutes (though usually blocked)
```

### Handling Rejections

```python
approved = await handler.request_approval(...)

if not approved:
    # Log the rejection
    logger.warning(f"Action rejected: {description}")

    # Check if we have a fallback
    if has_fallback_action:
        await execute_fallback()
    else:
        # Inform the orchestrator
        raise ApprovalRejectedError(f"Action rejected: {description}")
```

### Testing Approval Flows

```python
import pytest
from unittest.mock import AsyncMock

@pytest.fixture
def approval_handler():
    handler = ApprovalHandler(
        mode=Mode.PRODUCTION,
        approval_mode=ApprovalMode.INTERACTIVE,
    )
    return handler

async def test_safe_action_auto_approved(approval_handler):
    """SAFE tier actions should auto-approve."""
    result = await approval_handler.request_approval(
        action_type=ActionType.CONFIG_CHANGE,
        description="Minor config update",
        predicted_severity=Severity.S0,
    )
    assert result is True

async def test_review_action_needs_human(approval_handler):
    """REVIEW tier actions should call UI."""
    mock_ui = AsyncMock(return_value=True)
    approval_handler.register_ui(mock_ui)

    result = await approval_handler.request_approval(
        action_type=ActionType.PROMPT_MUTATION,
        description="Modify system prompt",
        predicted_severity=Severity.S2,
    )

    assert mock_ui.called
    assert result is True

async def test_blocked_action_rejected(approval_handler):
    """BLOCK tier actions should be rejected."""
    result = await approval_handler.request_approval(
        action_type=ActionType.DESTRUCTIVE_TOOL_CALL,
        description="Delete database",
        predicted_severity=Severity.S4,
    )
    assert result is False
```

---

## Summary

The HITL approval system provides:

- **Three Risk Tiers**: SAFE (auto), REVIEW (human), BLOCK (never)
- **Severity-Based Gating**: S0-S4 severity drives approval requirements
- **Mode-Aware**: Different behavior per operating mode
- **Pluggable UI**: TUI, CLI, or custom approval interfaces
- **Audit Trail**: Complete logging of all decisions
- **Extensible**: Custom approval workflows supported

Use this system to maintain appropriate human oversight while allowing Tinman to operate autonomously where safe.

---

## Next Steps

- [MODES.md](MODES.md) - How modes affect approval requirements
- [TAXONOMY.md](TAXONOMY.md) - Severity level definitions
- [CONFIGURATION.md](CONFIGURATION.md) - Approval configuration options
