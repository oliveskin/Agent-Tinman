

# 🔒 PHASE 2 — RESEARCH MEMORY GRAPH (RMG) + FAILURE ONTOLOGY ENGINE

**FDRA-C+ Low-Level Design — Enterprise Grade**

---

## 1. PURPOSE OF THE RESEARCH MEMORY GRAPH (RMG)

The RMG is **not a log store**.
It is a **causal behavior intelligence graph** that provides:

* Long-term memory of:

  * Model behavior evolution
  * Failure emergence
  * Intervention side effects
* Forensic reconstruction:

  * “Why did this model break now?”
* Predictive capability:

  * “This action class historically causes regressions”
* Regulatory evidence:

  * Deterministic replay for audits & legal discovery

> **Every hypothesis, experiment, failure, intervention, approval, deployment, rollback — is a first-class node.**

---

## 2. GRAPH MODEL TYPE

RMG is a **temporal property graph** with:

* **Nodes** (typed entities)
* **Edges** (typed causal & temporal relations)
* **Temporal versioning**
* **Tenant isolation at the graph layer**

Supported backends:

* Default: **SQLite/Postgres + adjacency tables**
* Optional: **Neo4j / TigerGraph**
* Optional: **Immutable event-sourced DAG**

---

## 3. FORMAL NODE TAXONOMY

All nodes share a **common base envelope**:

```json
{
  "node_id": "uuid",
  "node_type": "ENUM",
  "tenant_id": "uuid",
  "created_at": "utc",
  "created_by": "agent_id | human_id",
  "hash": "sha256(payload)",
  "is_immutable": true | false,
  "metadata": {}
}
```

---

### 3.1 Primary Node Types

| Node Type          | Purpose               |
| ------------------ | --------------------- |
| `ModelVersionNode` | Tracks model identity |
| `HypothesisNode`   | Behavioral prediction |
| `ExperimentNode`   | Designed probe        |
| `RunNode`          | Concrete execution    |
| `FailureModeNode`  | Discovered failure    |
| `InterventionNode` | Proposed correction   |
| `SimulationNode`   | Pre-deployment replay |
| `ApprovalNode`     | Human governance      |
| `DeploymentNode`   | Live application      |
| `RollbackNode`     | Reversion action      |
| `AlertNode`        | Control-plane warning |

---

### 3.2 Example: FailureModeNode (Full Payload)

```json
{
  "node_type": "FailureModeNode",
  "failure_id": "uuid",
  "primary_class": "LONG_CONTEXT_DEGRADATION",
  "secondary_class": "ATTENTION_DILUTION",
  "trigger_signature": [
    "context_tokens > 9000",
    "rag_enabled = true"
  ],
  "impact_surface": ["legal_summary", "contracts"],
  "severity": "S3",
  "reproducibility_score": 0.91,
  "first_seen_model_version": "v1.22",
  "confidence": 0.87,
  "is_persistent": true,
  "is_resolved": false
}
```

---

## 4. EDGE RELATION ONTOLOGY (CAUSAL GRAMMAR)

Edges are **typed, directional, and semantically enforced**.

| Relation         | Meaning                   |
| ---------------- | ------------------------- |
| `GENERATED`      | Agent created node        |
| `TESTED_IN`      | Hypothesis → Experiment   |
| `EXECUTED_AS`    | Experiment → Run          |
| `OBSERVED_IN`    | Failure → Run             |
| `CAUSED_BY`      | Failure → Root cause      |
| `ADDRESSED_BY`   | Failure → Intervention    |
| `SIMULATED_BY`   | Intervention → Simulation |
| `APPROVED_BY`    | Intervention → Approval   |
| `DEPLOYED_AS`    | Intervention → Deployment |
| `ROLLED_BACK_BY` | Deployment → Rollback     |
| `REGRESSED_AS`   | Deployment → Failure      |
| `BLOCKED_BY`     | Action → Policy           |

---

## 5. TEMPORAL VERSIONING & LINEAGE RULES

Every mutable concept is **versioned, not overwritten**:

* Prompt versions
* Tool policies
* Memory schemas
* Model routing rules

### 5.1 Temporal Guarantees

* All nodes have:

  * `valid_from`
  * `valid_to`
* No destructive mutation.
* Rollbacks create **new branches**, not erasure.

This enables:

* “What did the system believe at time T?”
* “Which deployment caused this regression?”

---

## 6. FAILURE ONTOLOGY ENGINE (FOE)

This is a **formal behavior classification system**, not a label set.

---

### 6.1 Failure Class Hierarchy (Formal)

```
FAILURE
 ├── REASONING_FAILURE
 │    ├── SPURIOUS_INFERENCE
 │    ├── GOAL_DRIFT
 │    └── CONTRADICTION_LOOP
 │
 ├── LONG_CONTEXT_FAILURE
 │    ├── ATTENTION_DILUTION
 │    ├── LATENT_FORGETTING
 │    └── RETRIEVAL_DOMINANCE
 │
 ├── TOOL_USE_FAILURE
 │    ├── TOOL_HALLUCINATION
 │    ├── CHAIN_MISORDER
 │    ├── RETRY_AMPLIFICATION
 │    └── DESTRUCTIVE_TOOL_CALL
 │
 ├── FEEDBACK_LOOP_FAILURE
 │    ├── REWARD_HACKING
 │    ├── CONFIRMATION_DRIFT
 │    └── MEMORY_POISONING
 │
 └── DEPLOYMENT_FAILURE
      ├── LATENCY_COLLAPSE
      ├── COST_RUNAWAY
      └── SAFETY_REGRESSION
```

This hierarchy is **extensible but inheritance-constrained**.

---

### 6.2 Automated Classification Pipeline

```
Raw Run Traces →
  Heuristic Detectors →
    Pattern Matchers →
      Embedding Similarity →
        Ontology Resolver →
          FailureModeNode
```

If classifier confidence < threshold:

→ Escalated to **Human Taxonomy Review**.

---

## 7. FAILURE INHERITANCE & EVOLUTION LOGIC

Failures evolve.

A failure can:

* Split into subclasses
* Merge into a parent class
* Become dormant
* Re-emerge after intervention

### 7.1 Evolution Example

```text
LONG_CONTEXT_DEGRADATION
  → ATTENTION_DILUTION (v1.22)
     → LATENT_FORGETTING (v1.26)
```

Edges:

```
ATTENTION_DILUTION → EVOLVED_INTO → LATENT_FORGETTING
```

This allows FDRA to:

* Track **behavioral drift across model versions**
* Detect **false fixes**

---

## 8. CAUSAL GRAPH CONSTRUCTION (ROOT CAUSE ENGINE)

Failures are not standalone.
FDRA builds a **causal graph** per failure family.

### 8.1 Root Cause Stack Example

```text
Failure: RETRY_AMPLIFICATION (S2)
  ← CAUSED_BY: Unbounded retry policy
     ← CAUSED_BY: Tool timeout > 6s
        ← CAUSED_BY: Regional network jitter
```

Each cause node is itself a typed entity:

* `PolicyCauseNode`
* `InfraCauseNode`
* `ModelBehaviorCauseNode`

---

## 9. FORENSIC REPLAY MODEL

For any incident, FDRA must be able to reconstruct:

* The exact:

  * Model version
  * Prompt
  * Tool routing
  * Memory state
  * Risk thresholds
* At the moment of failure

This requires:

* Immutable snapshots of:

  * Prompt trees
  * Tool policies
  * Memory schemas
* Hash-chain verification

Used for:

* Post-mortems
* Legal defense
* Safety audits
* Regulatory discovery

---

## 10. HOT vs COLD MEMORY STRATEGY

| Tier | Contains           | Storage                     |
| ---- | ------------------ | --------------------------- |
| Hot  | Last 30–90 days    | Postgres / Graph DB         |
| Warm | Last 6–12 months   | Object store + index        |
| Cold | Long-term forensic | Immutable blob store (WORM) |

Cold memory is **append-only, write-once**.

---

## 11. GRAPH QUERY PATTERNS (CRITICAL OPS QUERIES)

FDRA exposes standardized queries like:

* ✅ “Show all regressions caused by model v1.24”
* ✅ “Show all interventions that increased cost > 20%”
* ✅ “Show unresolved S3 failures in production”
* ✅ “Show which failure families re-emerged after a fix”
* ✅ “Show failure lineage across last 5 releases”

These are **first-class APIs**, not ad-hoc SQL.

---

## 12. MULTI-TENANT GRAPH ISOLATION

Tenant separation enforced at:

* Node level (`tenant_id`)
* Edge level
* Graph namespace
* Storage backend

Cross-tenant graph traversal is:

* **Cryptographically forbidden**
* Enforced at query planner

---

## 13. SECURITY & TAMPER PROTECTION

| Protection     | Mechanism                                   |
| -------------- | ------------------------------------------- |
| Node integrity | Hash-chained payload                        |
| Edge integrity | Parent-hash enforcement                     |
| Write control  | Signed agent or human identity              |
| Replay attacks | Nonce + timestamp                           |
| Deletion       | Forbidden outside cold-archive purge window |

---
