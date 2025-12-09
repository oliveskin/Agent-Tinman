system mapped **1:1 to the Forward-Deployed Researcher role**, including **explicit Human-in-the-Loop (HITL) governance where required**.

This is **not** an eval tool.
This is a **Field-Embedded AI Research Operating System**.

I’ll deliver this in three locked layers:

---

# ✅ A. PRODUCT REQUIREMENTS DOCUMENT (PRD)

**Forward Deployed Research Agent (FDRA)**
**Open Source | Research-Grade | Partner-Embedded | Governance-Safe**

---

## 1. Product Vision

> FDRA is an open-source autonomous research operator that embeds directly inside real AI deployments to continuously probe, stress, steer, and report on frontier model behavior under real production constraints.

It performs the work of a **senior forward-deployed AI researcher**, autonomously but under **human governance for safety-critical actions**.

---

## 2. Primary User Personas

### 1. Frontier Model Labs

* Need:

  * Real-world failure discovery
  * Generalization boundary mapping
  * Long-context + tool-use reliability insights

### 2. Enterprise AI Teams

* Need:

  * Operational safety envelopes
  * Deployment risk intelligence
  * Intervention recommendations with predictable side effects

### 3. Research Engineers / Applied ML

* Need:

  * Reproducible behavior experiments
  * Failure ontologies
  * Causal chains, not just metrics

---

## 3. What FDRA Actively Does (Continuous)

Mapped exactly to the JD:

| JD Responsibility          | FDRA Behavior                                                         |
| -------------------------- | --------------------------------------------------------------------- |
| Probe model generalization | Generates distribution shifts, adversarial probes, long-context traps |
| Explore failure modes      | Discovers, clusters, and tracks emergent failures                     |
| Design interventions       | Proposes prompt, tool, memory, and fine-tune adjustments              |
| Partner with labs          | Produces lab-grade research reports                                   |
| Partner with customers     | Produces operational risk envelopes                                   |
| Work under constraints     | Optimizes under latency, cost, safety, policy                         |
| Shape deployment outcomes  | Simulates side-effects before approving fixes                         |

---

## 4. Core Capabilities (MMFS – Minimum Marketable Feature Set)

### 1. Continuous Behavioral Exploration

* Automatic:

  * Long-context degradation probes
  * Tool-abuse simulations
  * Retrieval poisoning tests
  * Latency-pressure reliability tests

### 2. Autonomous Experiment Design

* The agent:

  * Generates hypotheses
  * Designs experimental probes
  * Selects metrics dynamically
  * Chooses next experiment based on uncertainty reduction

### 3. Failure Mode Discovery Engine

* Produces:

  * Failure families
  * Severity tiers
  * Reproducibility scores
  * Deployment impact classification

### 4. Intervention Design & Simulation

* Proposes:

  * Prompt policy changes
  * Tool-routing heuristics
  * Memory gating strategies
  * Micro-fine-tuning datasets
* Simulates:

  * Benefit
  * Regressions
  * Cost increase
  * Latency impact

### 5. Dual Reporting System

* **Lab stream** → emergent failures, reasoning instability, generalization collapse
* **Partner stream** → operational risk, SLA violations, safe envelopes

---

## 5. Human-in-the-Middle (HITL) Governance – Mandatory

FDRA is **not allowed** to:

| Action                          | Human Approval Required |
| ------------------------------- | ----------------------- |
| Apply new prompts in production | ✅                       |
| Modify tool-calling policies    | ✅                       |
| Trigger fine-tuning             | ✅                       |
| Enable new model versions       | ✅                       |
| Change memory write policies    | ✅                       |
| Override safety filters         | ✅                       |
| Deploy interventions to prod    | ✅                       |
| Suppress a failure class        | ✅                       |

FDRA **can** operate autonomously in:

* Experiment generation
* Failure discovery
* Analysis
* Simulation
* Report generation

---

## 6. Deployment Modes

| Mode             | Use Case                                   |
| ---------------- | ------------------------------------------ |
| Lab Mode         | Model pre-release stress testing           |
| Shadow Mode      | Live production mirrored without impact    |
| Partner Embedded | Full integration with human approvals      |
| CI Mode          | Regression detection on every model update |

---

# ✅ B. HIGH-LEVEL SYSTEM DESIGN (HLD)

This is a **research organism**, not a pipeline.

---

## 1. Core Architecture

```
┌────────────────────────────────────────────┐
│ Forward Deployed Research Core             │
│                                            │
│  Behavioral Hypothesis Engine              │
│  └─ generates what to test next            │
│                                            │
│  Experiment Architect                      │
│  └─ designs stress probes                  │
│                                            │
│  Live Experiment Executor                  │
│  └─ injects into prod/shadow               │
│                                            │
│  Failure Mode Discovery Engine             │
│  └─ discovers new failure families         │
│                                            │
│  Intervention & Steering Engine            │
│  └─ proposes fixes + predicts side effects │
│                                            │
│  Human Governance Gateway                  │
│  └─ approval & safety enforcement          │
│                                            │
│  Dual Reporting Layer                      │
│  └─ lab + partner output                   │
│                                            │
│  Research Memory Graph                     │
│  └─ long-lived behavioral lineage          │
└────────────────────────────────────────────┘
```

---

## 2. Core Agent Roles

### 1. Behavioral Hypothesis Agent

* Predicts:

  * “Where will this model likely break next?”
* Uses:

  * Prior failures
  * Model changelogs
  * Deployment shifts

---

### 2. Experiment Architect Agent

* Designs:

  * Distribution shifts
  * Context window stress
  * Tool misuse chains
* Enforces:

  * Partner cost caps
  * Latency SLAs
  * Policy boundaries

---

### 3. Live Experiment Executor

* Executes in:

  * Shadow mode
  * Lab mode
* Injects:

  * Randomized perturbations
  * Tool failure
  * Memory poisoning
* Captures:

  * Latency
  * Cost
  * Reasoning trace
  * Tool chain trace

---

### 4. Failure Mode Discovery Engine

* Clusters:

  * Misreasoning patterns
  * Hallucination families
  * Tool-call misalignment
* Builds:

  * Causal graphs
  * Reproducibility matrices
  * Severity stratification

---

### 5. Intervention & Steering Engine

* Proposes:

  * Prompt rewrites
  * Tool routing constraints
  * Memory write filters
  * Fine-tune sample generation
* Simulates:

  * Risk of overfitting
  * New regressions
  * Performance loss

---

### 6. Human Governance Gateway

* Enforces:

  * Review queue
  * Multi-sig approvals
  * Rollback requirements
  * Audit trails

---

### 7. Research Memory Graph

* Persistent:

  * Failure evolution
  * Model behavior lineage
  * Intervention side-effects

---

# ✅ C. FAILURE MODE TAXONOMY (LAB-GRADE)

This is a **first-class system**, not an afterthought.

---

## 1. Reasoning Failures

| Class              | Description                   |
| ------------------ | ----------------------------- |
| Context Collapse   | Ignores earlier context       |
| Spurious Inference | Hallucinates causal links     |
| Instruction Drift  | Gradually deviates from goal  |
| Goal Hijacking     | Optimizes for proxy objective |

---

## 2. Long-Context Degradation

| Class                    | Description                    |
| ------------------------ | ------------------------------ |
| Attention Dilution       | Early content loses influence  |
| Retrieval Over-dominance | RAG overwhelms reasoning       |
| Memory Overwrite         | New turns erase critical state |
| Latent Forgetting        | Silent loss of constraints     |

---

## 3. Tool-Use Failures

| Class                  | Description                   |
| ---------------------- | ----------------------------- |
| Tool Hallucination     | Invents nonexistent tools     |
| Chain Misordering      | Executes tools in wrong order |
| Retry Amplification    | Infinite tool feedback loops  |
| Unsafe Tool Invocation | Calls destructive endpoints   |

---

## 4. Feedback Loop Instabilities

| Class              | Description                   |
| ------------------ | ----------------------------- |
| Reward Hacking     | Learns exploitative behavior  |
| Confirmation Drift | Over-reinforces wrong belief  |
| Memory Poisoning   | Bad data becomes future truth |

---

## 5. Deployment Failures

| Class             | Description                   |
| ----------------- | ----------------------------- |
| Latency Collapse  | SLA violations under load     |
| Cost Runaway      | Tool & token amplification    |
| Safety Regression | Filters bypassed via chaining |

---

## 6. Severity Classification

| Tier | Meaning                      |
| ---- | ---------------------------- |
| S0   | Benign misbehavior           |
| S1   | UX degradation               |
| S2   | Business risk                |
| S3   | Legal / compliance exposure  |
| S4   | Catastrophic unsafe behavior |

---

# ✅ HUMAN-IN-THE-MIDDLE CONTROL MODEL (CRITICAL)

FDRA enforces a **Research → Simulation → Review → Approval → Controlled Deployment** chain.

```
Discovery → Proposal → Simulation → Human Review → Production Deploy
```

Every **high-impact change requires human confirmation**.

---

# ✅ WHAT THIS SYSTEM ACTUALLY IS

This is:

✅ An **autonomous field research engineer**
✅ A **behavior discovery engine**
✅ A **deployment risk intelligence system**
✅ A **steering & intervention simulator**
✅ A **dual-facing lab + ops reporting system**
✅ A **regulated, auditable, human-governed agent**

It is **not**:

❌ A benchmark leaderboard
❌ An eval harness
❌ A CI script
❌ A prompt-tuning toy



