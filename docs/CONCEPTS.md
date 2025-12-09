# Core Concepts

This document explains the fundamental concepts and mental model behind Tinman. Understanding these concepts will help you use the system effectively and contribute to its development.

---

## Table of Contents

1. [What is a Forward-Deployed Research Agent?](#what-is-a-forward-deployed-research-agent)
2. [The Research Methodology](#the-research-methodology)
3. [Core Abstractions](#core-abstractions)
4. [The Research Cycle](#the-research-cycle)
5. [Knowledge Accumulation](#knowledge-accumulation)
6. [Risk and Safety Model](#risk-and-safety-model)

---

## What is a Forward-Deployed Research Agent?

Tinman is not a testing framework. It's not a monitoring tool. It's a **research agent**—an autonomous system that conducts ongoing scientific inquiry into how your AI system can fail.

### The Key Insight

Traditional approaches to AI reliability are **reactive**:
- Wait for failures to occur
- Investigate root causes
- Implement fixes
- Hope the same failure doesn't happen again

This approach has two fundamental problems:

1. **You only learn about failures after they hurt users**
2. **You only test for failures you've already imagined**

Tinman inverts this:

| Traditional | Tinman |
|-------------|--------|
| Wait for failure | Actively seek failure |
| Test known patterns | Generate novel hypotheses |
| Fix then forget | Learn and compound |
| Human-driven investigation | Autonomous research |

### "Forward-Deployed" Meaning

**Forward-deployed** means Tinman operates where your AI system operates:

- **In your development environment** (LAB mode) - Aggressive exploration
- **Alongside your production traffic** (SHADOW mode) - Passive observation
- **Within your production system** (PRODUCTION mode) - Active protection

It's not a separate analysis tool you run occasionally. It's a persistent research agent that continuously explores your system's behavior.

### The Research Frame

Think of Tinman as an AI researcher assigned to study your system:

- It forms **hypotheses** about potential weaknesses
- It designs **experiments** to test those hypotheses
- It **discovers** failures and classifies them
- It proposes **interventions** to address them
- It **learns** from each cycle to improve future research

This is the scientific method, automated and deployed continuously.

---

## The Research Methodology

Tinman embodies a specific methodology for AI reliability research:

### 1. Hypothesis-Driven Exploration

Every action Tinman takes starts with a hypothesis:

```
"I hypothesize that this system will produce inconsistent outputs
when given long conversations with interleaved topics."
```

Hypotheses are:
- **Testable** - Can be verified through experimentation
- **Specific** - Target a particular failure mode
- **Grounded** - Based on observed behavior or known failure patterns

This is different from random fuzzing or exhaustive testing. Every experiment has a purpose.

### 2. Controlled Experimentation

Hypotheses are tested through controlled experiments:

```python
# Example experiment design
{
    "hypothesis_id": "hyp_001",
    "stress_type": "CONTEXT_INTERLEAVING",
    "parameters": {
        "topic_count": 5,
        "switches_per_topic": 3,
        "context_length": 8000
    },
    "expected_failure_class": "LONG_CONTEXT",
    "runs": 10
}
```

Experiments are:
- **Reproducible** - Same parameters yield comparable results
- **Measurable** - Clear success/failure criteria
- **Bounded** - Cost and time limits prevent runaway exploration

### 3. Systematic Classification

When failures are discovered, they're classified using a structured taxonomy:

```
Failure:
  Class: LONG_CONTEXT
  Subtype: ATTENTION_DILUTION
  Severity: S2 (Business Risk)
  Reproducibility: 7/10 runs
  Root Cause: Model loses track of early instructions
               when conversation exceeds 4000 tokens
```

Classification enables:
- **Pattern recognition** across failures
- **Prioritization** based on severity
- **Targeted interventions** for each failure class

### 4. Intervention Design

For each failure, Tinman designs concrete interventions:

```python
# Example intervention
{
    "failure_id": "fail_001",
    "type": "PROMPT_MUTATION",
    "description": "Add periodic instruction reinforcement",
    "implementation": {
        "inject_at": "every_5_turns",
        "content": "Remember: {original_instructions}"
    },
    "estimated_effectiveness": 0.75,
    "reversibility": True
}
```

Interventions are:
- **Specific** - Address a particular failure
- **Testable** - Can be validated before deployment
- **Reversible** - Can be rolled back if ineffective

### 5. Validation Through Simulation

Before deploying interventions, they're validated through **counterfactual simulation**:

1. Take historical traces where the failure occurred
2. Replay them with the intervention applied
3. Measure whether the failure is prevented

This answers: "Would this fix have worked on past failures?"

### 6. Continuous Learning

Each research cycle informs the next:

- Successful hypotheses inform future hypothesis generation
- Failed experiments refine the understanding of system behavior
- Effective interventions become baseline protections
- The memory graph accumulates institutional knowledge

---

## Core Abstractions

Tinman is built around these core abstractions:

### Agents

Autonomous components that perform specific research tasks:

| Agent | Responsibility |
|-------|----------------|
| **HypothesisEngine** | Generate testable failure hypotheses |
| **ExperimentArchitect** | Design experiments to test hypotheses |
| **ExperimentExecutor** | Run experiments with approval gates |
| **FailureDiscovery** | Classify discovered failures |
| **InterventionEngine** | Design fixes for failures |
| **SimulationEngine** | Validate interventions via replay |

Agents are:
- **Autonomous** - Operate without constant human direction
- **Stateless** - Don't maintain internal state between calls
- **Composable** - Can be combined in different workflows

### Memory Graph

A temporal knowledge graph that stores all research findings:

```
┌─────────────────────────────────────────────────────────────┐
│                     MEMORY GRAPH                             │
│                                                              │
│   Hypothesis ──tests_in──▶ Experiment                       │
│       │                         │                            │
│       │                    produces                          │
│       │                         ▼                            │
│       └─────────────────▶ Failure ◀────── addresses ────┐   │
│                              │                           │   │
│                         caused_by                        │   │
│                              ▼                           │   │
│                          RootCause ───leads_to──▶ Intervention │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

The graph is:
- **Temporal** - Query "what did we know at time T?"
- **Relational** - Track causal links between entities
- **Persistent** - Survives restarts, accumulates knowledge
- **Queryable** - Find patterns, lineage, evolution

### Operating Mode

The mode determines safety boundaries:

```
LAB ──────────▶ SHADOW ──────────▶ PRODUCTION
 │                │                    │
 │                │                    │
 ▼                ▼                    ▼
Unrestricted   Observation         Strict Control
Exploration    Only                 Human Approval
```

Modes are:
- **Progressive** - Move from LAB → SHADOW → PRODUCTION
- **Constrained** - Cannot skip modes
- **Behavioral** - Same code, different permissions

### Risk Evaluator

Assesses actions and assigns risk tiers:

```
Action ──▶ RiskEvaluator ──▶ SAFE | REVIEW | BLOCK
                │
                └── Considers:
                    - Action type
                    - Operating mode
                    - Predicted severity
                    - Cost estimate
                    - Reversibility
```

### Approval Handler

Coordinates human-in-the-loop decisions:

```
Agent Request ──▶ ApprovalHandler
                        │
              ┌─────────┴─────────┐
              ▼                   ▼
         Risk Tier            UI Callback
              │                   │
              └───────┬───────────┘
                      ▼
               Approved / Rejected
```

### Failure Taxonomy

Structured classification of failure modes:

```
FailureClass
├── REASONING
│   ├── LOGICAL_ERROR
│   ├── GOAL_DRIFT
│   ├── HALLUCINATION
│   └── ...
├── LONG_CONTEXT
│   ├── ATTENTION_DILUTION
│   ├── INSTRUCTION_AMNESIA
│   └── ...
├── TOOL_USE
│   ├── PARAMETER_ERROR
│   ├── WRONG_TOOL_SELECTION
│   └── ...
├── FEEDBACK_LOOP
│   ├── ERROR_AMPLIFICATION
│   ├── REPETITION_LOCK
│   └── ...
└── DEPLOYMENT
    ├── LATENCY_DEGRADATION
    ├── RESOURCE_EXHAUSTION
    └── ...
```

---

## The Research Cycle

A single research cycle follows this flow:

### Phase 1: Hypothesis Generation

**Input:** Prior knowledge (memory graph), system observations, failure taxonomy

**Process:**
1. Query memory graph for recent failures and patterns
2. Analyze system behavior for anomalies
3. Generate hypotheses based on known failure classes
4. Prioritize by potential severity and confidence

**Output:** Ranked list of hypotheses to test

```python
hypotheses = [
    Hypothesis(
        target_surface="reasoning",
        expected_failure="goal_drift",
        confidence=0.7,
        rationale="System showed inconsistent objectives in long conversations"
    ),
    ...
]
```

### Phase 2: Experiment Design

**Input:** Hypotheses from Phase 1

**Process:**
1. For each hypothesis, design experiments that would confirm/refute it
2. Determine stress parameters (intensity, duration, variation)
3. Define success/failure criteria
4. Estimate cost and risk

**Output:** Experiment designs ready for execution

```python
experiments = [
    ExperimentDesign(
        hypothesis_id="hyp_001",
        stress_type="GOAL_INJECTION",
        parameters={"conflicting_goals": 3, "injection_point": "mid"},
        expected_outcome="goal_drift_detected",
        estimated_cost_usd=0.50
    ),
    ...
]
```

### Phase 3: Experiment Execution

**Input:** Experiment designs from Phase 2

**Process:**
1. **Approval gate** - Check if experiment needs human approval
2. Execute experiment against target system
3. Collect results (outputs, metrics, traces)
4. Detect anomalies and potential failures

**Output:** Experiment results with detected issues

```python
results = [
    ExperimentResult(
        experiment_id="exp_001",
        runs=10,
        failures_detected=7,
        traces=[...],
        anomalies=[...]
    ),
    ...
]
```

### Phase 4: Failure Discovery

**Input:** Experiment results from Phase 3

**Process:**
1. Analyze results for failure patterns
2. Classify failures using taxonomy
3. Assess severity (S0-S4)
4. Identify root causes
5. Link to hypotheses (confirmed/refuted)

**Output:** Classified failures with root cause analysis

```python
failures = [
    DiscoveredFailure(
        id="fail_001",
        failure_class=FailureClass.REASONING,
        subtype="GOAL_DRIFT",
        severity=Severity.S2,
        root_cause="Model prioritizes recent instructions over system prompt",
        reproducibility=0.7
    ),
    ...
]
```

### Phase 5: Intervention Design

**Input:** Failures from Phase 4

**Process:**
1. **Approval gate** - High-severity failures may need human review
2. For each failure, generate candidate interventions
3. Estimate effectiveness and side effects
4. Plan rollback procedures
5. Risk-assess each intervention

**Output:** Proposed interventions

```python
interventions = [
    Intervention(
        failure_id="fail_001",
        type=InterventionType.PROMPT_MUTATION,
        description="Reinforce system prompt every 5 turns",
        estimated_effectiveness=0.8,
        risk_tier=RiskTier.REVIEW,
        rollback_plan="Remove injection logic"
    ),
    ...
]
```

### Phase 6: Simulation

**Input:** Interventions from Phase 5

**Process:**
1. **Approval gate** - Simulation may have cost implications
2. Retrieve historical traces where failure occurred
3. Replay traces with intervention applied
4. Measure whether failure is prevented
5. Detect any new issues introduced

**Output:** Simulation results with effectiveness metrics

```python
simulations = [
    SimulationResult(
        intervention_id="int_001",
        traces_replayed=50,
        failures_prevented=42,
        new_issues_detected=1,
        effectiveness=0.84
    ),
    ...
]
```

### Phase 7: Learning

**Input:** All results from the cycle

**Process:**
1. Update memory graph with new knowledge
2. Adjust hypothesis generation based on outcomes
3. Mark effective interventions for deployment consideration
4. Update adaptive memory patterns

**Output:** Updated system state, ready for next cycle

---

## Knowledge Accumulation

Tinman's power comes from **compounding knowledge** across research cycles.

### The Memory Graph

Every finding is recorded in a persistent knowledge graph:

```python
# Adding a discovered failure
graph.add_node(
    type=NodeType.FAILURE,
    data={
        "class": "REASONING",
        "subtype": "GOAL_DRIFT",
        "severity": "S2",
        "root_cause": "..."
    }
)

# Linking to the experiment that found it
graph.add_edge(
    source=experiment_id,
    target=failure_id,
    relation=EdgeRelation.DISCOVERED_IN
)

# Linking to the intervention that addresses it
graph.add_edge(
    source=failure_id,
    target=intervention_id,
    relation=EdgeRelation.ADDRESSED_BY
)
```

### Temporal Queries

The graph supports temporal queries:

```python
# What failures did we know about when we deployed version 2.0?
deployment_time = datetime(2024, 1, 15, 10, 30)
known_failures = graph.snapshot_at(deployment_time, node_type=NodeType.FAILURE)

# Did we miss anything?
failures_after = graph.get_nodes(
    node_type=NodeType.FAILURE,
    created_after=deployment_time
)
```

This enables:
- **Forensic analysis** - What did we know when?
- **Deployment auditing** - Were known issues addressed?
- **Trend analysis** - Are failures increasing/decreasing?

### Adaptive Learning

The `AdaptiveMemory` component tracks patterns:

```python
# Example learned patterns
{
    "hypothesis_success_rates": {
        "REASONING.GOAL_DRIFT": 0.7,   # 70% confirmed
        "TOOL_USE.PARAMETER_ERROR": 0.3  # Only 30% confirmed
    },
    "intervention_effectiveness": {
        "PROMPT_MUTATION": 0.65,
        "GUARDRAIL_ADDITION": 0.80
    },
    "failure_correlations": {
        ("LONG_CONTEXT", "REASONING"): 0.4  # Often co-occur
    }
}
```

This informs future cycles:
- Prioritize hypothesis types that are more likely to be confirmed
- Prefer intervention types that have been effective
- Look for correlated failures when one is found

---

## Risk and Safety Model

Tinman operates with safety as a core concern.

### The Three-Tier Risk Model

Every action is classified into one of three tiers:

| Tier | Meaning | Approval | Example |
|------|---------|----------|---------|
| **SAFE** | Low risk, proceed | Automatic | Running a read-only experiment |
| **REVIEW** | Medium risk | Human approval | Deploying a prompt mutation |
| **BLOCK** | High risk | Always rejected | Destructive action in production |

### Risk Factors

Risk is computed based on:

1. **Action Type**
   - Observation → Low risk
   - Prompt mutation → Medium risk
   - Tool policy change → High risk

2. **Operating Mode**
   - LAB → Most actions allowed
   - SHADOW → Observation only
   - PRODUCTION → Strict controls

3. **Predicted Severity**
   - S0-S1 → Usually SAFE
   - S2-S3 → Usually REVIEW
   - S4 → Often BLOCK

4. **Reversibility**
   - Reversible → Lower risk tier
   - Irreversible → Higher risk tier

5. **Cost**
   - Below threshold → No additional review
   - Above threshold → Requires approval

### Mode Constraints

Each mode has specific constraints:

**LAB Mode:**
- All experiment types allowed
- Auto-approve most actions
- No connection to production data

**SHADOW Mode:**
- Read-only access to production traffic
- Cannot modify system behavior
- Review required for S3+ findings

**PRODUCTION Mode:**
- Human approval for all interventions
- Destructive actions blocked
- Full audit trail required

### The Approval Flow

When approval is needed:

```
1. Agent requests approval
2. ApprovalHandler evaluates risk
3. If SAFE → auto-approve
4. If REVIEW → present to human
5. If BLOCK → auto-reject
6. Human decision recorded
7. Agent proceeds or aborts
```

See [HITL.md](HITL.md) for complete approval flow documentation.

---

## Summary

Tinman's conceptual model:

1. **Research, not testing** - Actively discover unknown failures
2. **Hypothesis-driven** - Every action has a purpose
3. **Systematic classification** - Structured taxonomy for all failures
4. **Compounding knowledge** - Learning accumulates over time
5. **Risk-aware** - Safety boundaries adapt to operating mode
6. **Human oversight** - Autonomy where safe, humans where it matters

Understanding these concepts is essential for:
- Effective use of the system
- Appropriate mode selection
- Interpreting findings
- Contributing to development

---

## Next Steps

- [ARCHITECTURE.md](ARCHITECTURE.md) - System design and components
- [TAXONOMY.md](TAXONOMY.md) - Complete failure classification
- [MODES.md](MODES.md) - Operating mode details
- [HITL.md](HITL.md) - Human-in-the-loop approval
