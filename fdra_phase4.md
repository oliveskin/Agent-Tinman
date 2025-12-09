# 🔒 PHASE 4 — HUMAN INTERLOCK + GOVERNANCE + APPROVAL SYSTEM

**FDRA-C+ Low-Level Design — Enterprise & Regulatory Grade**

---

## 1. PURPOSE OF THE HUMAN INTERLOCK LAYER

This layer exists to ensure:

* **Human authority over irreversible risk**
* **Separation of powers** between:

  * Autonomous agents
  * Operators
  * Safety officers
* **Legal defensibility** of decisions
* **Non-repudiation** for approvals
* **Controlled override**, not constant babysitting

> Humans are **not in the loop by default**.
> They are **on the loop when impact, irreversibility, or law demands it**.

---

## 2. GOVERNANCE PHILOSOPHY

FDRA governance follows **four core principles**:

1. **Risk-Proportional Oversight**
   → Oversight only increases with severity.

2. **Least-Authority Approval**
   → Only the minimum role set can approve.

3. **Separation of Concerns**
   → No single human can both:

   * Propose
   * Approve
   * Deploy

4. **Forensic Non-Repudiation**
   → Every approval is:

   * Cryptographically signed
   * Time-stamped
   * Immutable

---

## 3. APPROVAL OBJECT MODEL (FORMAL)

Every gated action creates an **Approval Object**.

```json
{
  "approval_id": "uuid",
  "tenant_id": "uuid",
  "action_id": "uuid",
  "intervention_id": "uuid",
  "requested_by": "agent:ISE",
  "risk_snapshot": {
    "severity": "S3",
    "risk_axes": {
      "safety": 0.74,
      "legal": 0.61,
      "financial": 0.18,
      "operational": 0.44,
      "behavioral": 0.52,
      "irreversibility": 0.71
    }
  },
  "impact_summary": {
    "expected_gains": {...},
    "expected_regressions": {...}
  },
  "rollback_plan_hash": "sha256",
  "state": "PENDING | APPROVED | REJECTED | EXPIRED",
  "approval_policy_id": "POLICY-S3-PROD",
  "created_at": "utc",
  "expires_at": "utc"
}
```

---

## 4. ROLE-BASED APPROVAL MODEL (RBAM)

Each tenant defines roles:

| Role             | Authority                    |
| ---------------- | ---------------------------- |
| `OPS_ADMIN`      | Operational risk             |
| `SAFETY_OFFICER` | Safety & alignment           |
| `LEGAL_OFFICER`  | Regulatory & compliance      |
| `PLATFORM_OWNER` | Strategic production control |
| `AUDITOR`        | Read-only forensic           |

---

### 4.1 Separation Rules (Hard-Enforced)

| Rule                               | Reason                |
| ---------------------------------- | --------------------- |
| Proposer ≠ Approver                | Prevent self-approval |
| Safety must approve S3+            | Alignment enforcement |
| Legal must approve S3+ legal risk  | Regulatory defense    |
| Ops must approve production deploy | Operational integrity |

---

## 5. MULTI-SIG APPROVAL POLICIES

Policies are defined as **boolean satisfaction graphs**, not linear rules.

### 5.1 Example Policy: `POLICY-S3-PROD`

```yaml
severity: S3
surface: PRODUCTION
required_signatures:
  - role: SAFETY_OFFICER
  - role: OPS_ADMIN
timeout_minutes: 240
rejection_policy: ANY_REJECT_BLOCKS
```

---

### 5.2 Example Policy: `POLICY-S4-GLOBAL`

```yaml
severity: S4
surface: ANY
required_signatures:
  - role: SAFETY_OFFICER
  - role: LEGAL_OFFICER
  - role: PLATFORM_OWNER
timeout_minutes: 60
rejection_policy: ANY_REJECT_ESCALATES
```

---

## 6. APPROVAL LIFECYCLE FSM

Each approval request follows this **formal state machine**:

```text
CREATED → PENDING → (APPROVED | REJECTED | EXPIRED)
APPROVED → DEPLOYED
REJECTED → CLOSED
EXPIRED → ESCALATED
```

---

### 6.1 Expiration Behavior

If `expires_at` is hit:

* Policy may specify:

  * Auto-reject
  * Auto-escalate to higher authority
  * Emergency Lockdown

---

## 7. DISPUTE & DEADLOCK RESOLUTION

If approvers disagree:

* FDRA enters **DISPUTE STATE**
* Automatically:

  * Freezes related deployments
  * Preserves full forensic snapshot
* Escalates to:

  * `PLATFORM_OWNER` or predefined arbitration role

Deadlock timeout triggers:

* Automatic **EMERGENCY LOCKDOWN** if unresolved for critical S4 paths

---

## 8. CRYPTOGRAPHIC SIGNING & NON-REPUDIATION

Each approval action is:

* Signed with:

  * Hardware key (YubiKey / HSM)
  * Or enterprise SSO + cryptographic token
* Stored with:

  * Payload hash
  * Role proof
  * Time proof

This ensures:

* Approvals are **legally admissible**
* No approval can be forged or retroactively altered

---

## 9. EMERGENCY OVERRIDE AUTHORITY

Separate from normal approvals.

### 9.1 Emergency Override Powers

Only these roles may override:

* `PLATFORM_OWNER`
* `LEGAL_OFFICER` (safety/legal lockdown)

Override can:

* Force rollback
* Force lockdown
* Suspend FDRA autonomy
* Freeze memory writes

---

### 9.2 Override Forensics

Overrides create:

```json
{
  "override_id": "uuid",
  "issued_by": "human_id",
  "reason": "text",
  "scope": "TENANT | GLOBAL",
  "duration_minutes": 720,
  "forensic_snapshot_hash": "sha256"
}
```

---

## 10. OPTIONAL HUMAN-IN-THE-LOOP (HITL) MODE

Tenants may enable **continuous human review**, even at S0–S1:

* For:

  * Highly regulated industries
  * Early pilots
  * Public-facing AI

In HITL-forced mode:

* All:

  * Prompt mutations
  * Tool routing changes
  * Memory gating updates
* Require at least **one human signature**

---

## 11. LEGAL & COMPLIANCE INTEGRATION

The Governance layer supports:

* SOC2 change-management mapping
* ISO-27001 access control evidence
* FDA / EMA model lifecycle evidence (medtech)
* Financial audit trails (SOX-style)

Each approval → becomes a **compliance artifact** automatically.

---

## 12. AUDIT & DISCOVERY INTERFACE

Auditors can query:

* ✅ Who approved what
* ✅ Under what risk snapshot
* ✅ With which simulation evidence
* ✅ With what rollback contingency
* ✅ Which regressions followed

This is **first-class API**, not log scraping.

---

## 13. GOVERNANCE FAILURE MODES & DEFENSES

| Failure Mode             | Defense                        |
| ------------------------ | ------------------------------ |
| Stolen approval key      | Multi-sig + role separation    |
| Compromised ops user     | Legal + safety still required  |
| Silent unsafe deployment | Risk engine blocks             |
| Approval spam attack     | Rate-limited approval creation |
| Governance deadlock      | Auto-escalation + lockdown     |
| Retroactive denial       | Hash-chained approvals         |

---

## ✅ WHAT PHASE 4 NOW GIVES YOU

You now have:

✅ A **formal human authority model**
✅ A **cryptographically secure approval system**
✅ A **multi-sig governance engine**
✅ A **dispute & deadlock resolution model**
✅ A **legal-grade non-repudiation layer**
✅ A **true emergency override system**
✅ A **switchable HITL enterprise mode**

At this point, FDRA-C+ is now:

> ✅ **Autonomous**
> ✅ **Governable**
> ✅ **Legally defensible**
> ✅ **Enterprise-deployable**

