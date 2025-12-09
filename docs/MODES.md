# Operating Modes

Tinman operates in three distinct modes that control safety boundaries, approval requirements, and available capabilities. This document provides a complete reference for each mode and their transitions.

---

## Table of Contents

1. [Overview](#overview)
2. [Mode Comparison](#mode-comparison)
3. [LAB Mode](#lab-mode)
4. [SHADOW Mode](#shadow-mode)
5. [PRODUCTION Mode](#production-mode)
6. [Mode Transitions](#mode-transitions)
7. [Configuration](#configuration)
8. [Best Practices](#best-practices)

---

## Overview

Operating modes are the primary safety mechanism in Tinman. They define:

- **What experiments can be run** - Destructive tests, stress tests, etc.
- **What approval is required** - Automatic vs. human-in-the-loop
- **What data can be accessed** - Synthetic vs. shadow vs. live
- **What interventions can be deployed** - Test vs. staging vs. production

### The Progressive Model

Modes follow a progressive deployment model:

```
LAB ──────────▶ SHADOW ──────────▶ PRODUCTION
 │                 │                    │
 │                 │                    │
 ▼                 ▼                    ▼
Development     Validation          Deployment
Environment     Environment         Environment
```

This progression ensures:
1. **Hypotheses are validated** in LAB before testing against real patterns
2. **Interventions are proven** in SHADOW before deployment
3. **Production impact is minimized** through human oversight

### Mode Properties

Each mode has three key properties:

| Property | LAB | SHADOW | PRODUCTION |
|----------|-----|--------|------------|
| `allows_destructive_testing` | Yes | No | No |
| `requires_approval_gate` | No | No | Yes |
| `is_autonomous` | Yes | Yes | No |

---

## Mode Comparison

### Complete Behavior Matrix

| Behavior | LAB | SHADOW | PRODUCTION |
|----------|-----|--------|------------|
| **Experimentation** ||||
| Run stress tests | ✅ Auto | ✅ Auto | ⚠️ Review |
| Run destructive tests | ✅ Auto | ❌ Blocked | ❌ Blocked |
| Generate hypotheses | ✅ Auto | ✅ Auto | ⚠️ Review |
| **Data Access** ||||
| Use synthetic data | ✅ | ✅ | ✅ |
| Mirror production traffic | ❌ | ✅ | ❌ |
| Access live traffic | ❌ | ❌ | ✅ |
| **Interventions** ||||
| Test in isolation | ✅ Auto | ✅ Auto | ⚠️ Review |
| Deploy to staging | ⚠️ Review | ✅ Auto | ⚠️ Review |
| Deploy to production | ❌ Blocked | ❌ Blocked | ⚠️ Review |
| **Approval** ||||
| S0-S1 findings | Auto | Auto | Auto |
| S2 findings | Auto | Auto | Review |
| S3 findings | Review | Review | Review |
| S4 findings | Review | Blocked | Blocked |
| **Autonomy** ||||
| Research cycles | Autonomous | Autonomous | Supervised |
| Memory updates | Auto | Auto | Review |
| Report generation | Auto | Auto | Auto |

**Legend:**
- ✅ Auto = Proceeds automatically
- ⚠️ Review = Requires human approval
- ❌ Blocked = Not allowed in this mode

---

## LAB Mode

**Purpose:** Unrestricted research and experimentation in isolated environments.

### Characteristics

```python
Mode.LAB.allows_destructive_testing  # True
Mode.LAB.requires_approval_gate      # False
Mode.LAB.is_autonomous               # True
```

### When to Use

- Initial hypothesis exploration
- Testing new experiment designs
- Validating detection algorithms
- Development and debugging
- Stress testing intervention logic

### Capabilities

**Experiments:**
- All experiment types allowed
- Destructive stress tests permitted
- No cost limits (configurable)
- Maximum parallelism

**Interventions:**
- All intervention types can be tested
- Simulation against synthetic traces
- No deployment to real systems

**Approval:**
- Most actions auto-approved
- Only S3+ findings require review
- Cost-based approval for expensive experiments

### Restrictions

- No access to production data
- No access to shadow traffic
- Cannot deploy interventions externally
- Results are for internal use only

### Example Configuration

```yaml
mode: lab

experiments:
  max_parallel: 10
  default_timeout_seconds: 600
  cost_limit_usd: 50.0  # Higher limit for exploration
  allow_destructive: true

risk:
  auto_approve_safe: true
  auto_approve_review_in_lab: true  # Lab-specific setting
```

### Example Usage

```python
from tinman import create_tinman
from tinman.config.modes import Mode

async def lab_research():
    tinman = await create_tinman(
        mode=Mode.LAB,
        db_url="postgresql://localhost/tinman_lab"
    )

    # Run aggressive research cycle
    results = await tinman.research_cycle(
        focus="edge case failures",
        max_hypotheses=20,  # Explore broadly
        max_experiments=10,
        allow_destructive=True
    )

    # All findings are internal - can be aggressive
    print(f"Discovered {len(results.failures)} failures")
```

---

## SHADOW Mode

**Purpose:** Observe production patterns without affecting users.

### Characteristics

```python
Mode.SHADOW.allows_destructive_testing  # False
Mode.SHADOW.requires_approval_gate      # False
Mode.SHADOW.is_autonomous               # True
```

### When to Use

- Validating LAB findings against real patterns
- Discovering production-specific failures
- Testing detection on real traffic
- Calibrating sensitivity thresholds
- Building confidence before PRODUCTION

### Capabilities

**Experiments:**
- Non-destructive tests only
- Mirror of production traffic
- Real pattern analysis
- No synthetic data mixing

**Interventions:**
- Counterfactual simulation against real traces
- Effectiveness estimation
- No actual deployment

**Approval:**
- Most actions auto-approved
- S3+ findings require review
- Cannot modify production behavior

### Restrictions

- No destructive experiments
- No intervention deployment
- Read-only access to traffic
- Cannot affect user experience

### Traffic Mirroring

Shadow mode mirrors production traffic for analysis:

```
Production Traffic ─────────────────────────▶ Users
        │
        │ (mirror)
        ▼
   Shadow System ──▶ Analysis ──▶ Findings
        │
        └── No response sent to users
```

### Example Configuration

```yaml
mode: shadow

experiments:
  max_parallel: 5
  default_timeout_seconds: 300
  cost_limit_usd: 20.0
  allow_destructive: false  # Always false in shadow

shadow:
  traffic_mirror_percent: 10  # Mirror 10% of production
  sampling_strategy: random   # or: error_biased, latency_biased
  retention_hours: 24

risk:
  auto_approve_safe: true
  review_s3_plus: true
```

### Example Usage

```python
from tinman import create_tinman
from tinman.config.modes import Mode

async def shadow_validation():
    tinman = await create_tinman(
        mode=Mode.SHADOW,
        db_url="postgresql://localhost/tinman_shadow"
    )

    # Validate LAB findings against real patterns
    results = await tinman.research_cycle(
        focus="goal drift",  # Specific focus from LAB
        max_hypotheses=5,
        max_experiments=3
    )

    # Check if LAB findings hold in production patterns
    for failure in results.failures:
        print(f"Confirmed in production: {failure.failure_class}")
```

---

## PRODUCTION Mode

**Purpose:** Active protection with human oversight.

### Characteristics

```python
Mode.PRODUCTION.allows_destructive_testing  # False
Mode.PRODUCTION.requires_approval_gate      # True
Mode.PRODUCTION.is_autonomous               # False
```

### When to Use

- Deploying validated interventions
- Active failure detection
- Real-time protection
- Compliance and audit requirements

### Capabilities

**Experiments:**
- Careful, approved experiments only
- Focus on monitoring, not exploration
- Minimal impact testing

**Interventions:**
- Approved interventions can deploy
- Full rollback support
- Audit trail required

**Approval:**
- Human approval for all significant actions
- S4 findings always blocked until review
- Change management integration

### Restrictions

- No destructive experiments
- No speculative research
- All interventions require approval
- Strict audit requirements

### Approval Flow in Production

```
Action Request
     │
     ▼
Risk Evaluation
     │
     ├── SAFE (S0-S1) ──▶ Auto-approve ──▶ Execute
     │
     ├── REVIEW (S2-S3) ──▶ Human Review ──┬──▶ Approved ──▶ Execute
     │                                      │
     │                                      └──▶ Rejected ──▶ Log & Skip
     │
     └── BLOCK (S4) ──▶ Blocked ──▶ Log & Alert
```

### Example Configuration

```yaml
mode: production

experiments:
  max_parallel: 2
  default_timeout_seconds: 60
  cost_limit_usd: 5.0
  allow_destructive: false

risk:
  auto_approve_safe: true
  detailed_mode: true  # More granular risk assessment

approval:
  mode: interactive  # TUI approval dialog
  timeout_seconds: 300
  require_comment: true  # Approver must explain decision
  notify_on_block: true

audit:
  enabled: true
  log_all_decisions: true
  retention_days: 90
```

### Example Usage

```python
from tinman import create_tinman
from tinman.config.modes import Mode

async def production_protection():
    tinman = await create_tinman(
        mode=Mode.PRODUCTION,
        db_url="postgresql://localhost/tinman_prod"
    )

    # Run focused research with approval gates
    results = await tinman.research_cycle(
        focus="known failure patterns",  # Focus on validated patterns
        max_hypotheses=3,
        max_experiments=2
    )

    # Deploy approved interventions
    for intervention in results.interventions:
        if intervention.status == "approved":
            await tinman.deploy_intervention(intervention.id)
```

---

## Mode Transitions

### Allowed Transitions

```
     ┌─────────────────────────────────┐
     │                                 │
     ▼                                 │
   LAB ─────────────▶ SHADOW ─────────▶│ PRODUCTION
     ▲                   │             │
     │                   │             │
     └───────────────────┘             │
            (fallback)                 │
                         ◀─────────────┘
                          (regression)
```

| From | To | Allowed | Use Case |
|------|-----|---------|----------|
| LAB | SHADOW | ✅ | Promote validated hypotheses |
| SHADOW | PRODUCTION | ✅ | Deploy proven interventions |
| SHADOW | LAB | ✅ | Return for more exploration |
| PRODUCTION | SHADOW | ✅ | Regression fallback |
| LAB | PRODUCTION | ❌ | **Not allowed** - must validate |
| PRODUCTION | LAB | ❌ | **Not allowed** - go through SHADOW |

### Transition Requirements

**LAB → SHADOW:**
- At least one successful research cycle in LAB
- No critical errors in LAB runs
- Database migration completed (if schema changed)

**SHADOW → PRODUCTION:**
- Validated findings in SHADOW mode
- Intervention effectiveness > configured threshold
- No S4 findings unaddressed
- Approval from authorized personnel

**PRODUCTION → SHADOW:**
- Any time (regression fallback)
- Recommended after incidents
- Audit log of reason required

### Code Example

```python
from tinman.config.modes import Mode

# Check if transition is allowed
can_promote = Mode.can_transition(Mode.LAB, Mode.SHADOW)
print(f"LAB → SHADOW allowed: {can_promote}")  # True

can_skip = Mode.can_transition(Mode.LAB, Mode.PRODUCTION)
print(f"LAB → PRODUCTION allowed: {can_skip}")  # False

# Programmatic transition
async def promote_to_shadow(tinman):
    if Mode.can_transition(tinman.mode, Mode.SHADOW):
        await tinman.transition_mode(Mode.SHADOW)
    else:
        raise ValueError(f"Cannot transition from {tinman.mode} to SHADOW")
```

---

## Configuration

### Setting the Mode

**Via Configuration File:**

```yaml
# .tinman/config.yaml
mode: lab  # or: shadow, production
```

**Via Environment Variable:**

```bash
export TINMAN_MODE=shadow
```

**Via Python API:**

```python
from tinman import create_tinman
from tinman.config.modes import Mode

tinman = await create_tinman(mode=Mode.SHADOW)
```

**Via CLI:**

```bash
# Override config file
tinman --mode shadow research

# Or
tinman research --mode production
```

### Mode-Specific Configuration

Each mode can have specific configuration overrides:

```yaml
mode: shadow

# Global defaults
experiments:
  max_parallel: 5
  cost_limit_usd: 20.0

# Mode-specific overrides
modes:
  lab:
    experiments:
      max_parallel: 10
      cost_limit_usd: 100.0
      allow_destructive: true

  shadow:
    experiments:
      max_parallel: 5
      cost_limit_usd: 20.0
    shadow:
      traffic_mirror_percent: 10

  production:
    experiments:
      max_parallel: 2
      cost_limit_usd: 5.0
    approval:
      require_comment: true
```

---

## Best Practices

### Development Workflow

1. **Start in LAB mode**
   - Explore broadly
   - Test aggressive hypotheses
   - Iterate quickly

2. **Validate in SHADOW mode**
   - Test against real patterns
   - Calibrate detection thresholds
   - Build confidence

3. **Deploy in PRODUCTION mode**
   - Human oversight
   - Careful rollout
   - Continuous monitoring

### Mode-Specific Tips

**LAB Mode:**
- Use synthetic data that represents edge cases
- Don't be afraid to test destructive scenarios
- Document all findings for SHADOW validation
- Set high cost limits for exploration

**SHADOW Mode:**
- Monitor for LAB findings that don't reproduce
- Pay attention to patterns unique to production
- Use findings to refine detection sensitivity
- Prepare intervention validation data

**PRODUCTION Mode:**
- Start with conservative interventions
- Have rollback plans ready
- Monitor intervention effectiveness
- Maintain audit trails

### Anti-Patterns to Avoid

| Anti-Pattern | Why It's Bad | Better Approach |
|--------------|--------------|-----------------|
| Skipping SHADOW | Unvalidated interventions may fail | Always validate in SHADOW |
| LAB with production data | Privacy risk, contamination | Use synthetic or anonymized data |
| Auto-approve in PRODUCTION | Bypasses safety gates | Use proper approval workflow |
| Permanent SHADOW | Never deploy findings | Progress to PRODUCTION when validated |
| Running all modes simultaneously | Confusion, data mixing | One mode per environment |

### Environment Isolation

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   LAB ENV       │     │  SHADOW ENV     │     │  PROD ENV       │
│                 │     │                 │     │                 │
│ - Synthetic DB  │     │ - Mirror DB     │     │ - Prod DB       │
│ - Test models   │     │ - Prod model    │     │ - Prod model    │
│ - No traffic    │     │ - Shadow traffic│     │ - Live traffic  │
│ - Full autonomy │     │ - Read-only     │     │ - Human HITL    │
└─────────────────┘     └─────────────────┘     └─────────────────┘
         │                       │                       │
         └───────────────────────┴───────────────────────┘
                    Findings flow forward
                    Regressions flow backward
```

---

## Summary

| Mode | Purpose | Autonomy | Destructive | Approval |
|------|---------|----------|-------------|----------|
| **LAB** | Exploration | Full | Allowed | Minimal |
| **SHADOW** | Validation | Full | Blocked | S3+ review |
| **PRODUCTION** | Protection | Supervised | Blocked | Required |

The mode system ensures:
- **Progressive validation** before production impact
- **Appropriate oversight** at each stage
- **Clear boundaries** for safe operation
- **Audit trail** for compliance

---

## Next Steps

- [HITL.md](HITL.md) - Detailed approval flow documentation
- [CONFIGURATION.md](CONFIGURATION.md) - Complete configuration reference
- [INTEGRATION.md](INTEGRATION.md) - Embedding Tinman in existing systems
