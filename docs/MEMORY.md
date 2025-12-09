# Memory Graph

This document provides complete documentation for Tinman's Research Memory Graph—the temporal knowledge store that tracks all discoveries, relationships, and behavioral lineages.

---

## Table of Contents

1. [Overview](#overview)
2. [Graph Model](#graph-model)
3. [Node Types](#node-types)
4. [Edge Relations](#edge-relations)
5. [Temporal Versioning](#temporal-versioning)
6. [Core Operations](#core-operations)
7. [Query Operations](#query-operations)
8. [Lineage Tracking](#lineage-tracking)
9. [Recording Findings](#recording-findings)
10. [Examples](#examples)

---

## Overview

The Memory Graph is Tinman's central knowledge store. It tracks:

- **Model behavior evolution** - How behavior changes over time
- **Failure emergence and evolution** - New failures and their mutations
- **Intervention effects** - What fixes worked and what didn't
- **Causal relationships** - What caused what

### Key Capabilities

```
┌─────────────────────────────────────────────────────────────────┐
│                     MEMORY GRAPH CAPABILITIES                    │
│                                                                  │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐  │
│  │    Temporal     │  │    Lineage      │  │     Search      │  │
│  │    Versioning   │  │    Tracking     │  │                 │  │
│  │                 │  │                 │  │                 │  │
│  │ "What did we    │  │ "What caused    │  │ "Find all S3+   │  │
│  │  know at T?"    │  │  this failure?" │  │  failures"      │  │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘  │
│                                                                  │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐  │
│  │   Persistence   │  │   Evolution     │  │  Relationships  │  │
│  │                 │  │   Tracking      │  │                 │  │
│  │                 │  │                 │  │                 │  │
│  │ PostgreSQL or   │  │ "How did this   │  │ Hypothesis ->   │  │
│  │ SQLite backed   │  │  failure evolve?"│ │ Experiment ->   │  │
│  │                 │  │                 │  │ Failure -> Fix  │  │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘  │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### Design Principles

1. **Temporal** - Every node has a validity period
2. **Relational** - Edges capture causal and logical relationships
3. **Persistent** - Survives restarts, accumulates knowledge
4. **Queryable** - Find patterns, lineage, evolution

---

## Graph Model

The Memory Graph is a directed graph with typed nodes and edges.

```
┌─────────────────────────────────────────────────────────────────┐
│                       GRAPH STRUCTURE                            │
│                                                                  │
│   ┌────────────┐   TESTED_IN    ┌────────────┐                  │
│   │ Hypothesis ├───────────────▶│ Experiment │                  │
│   └────────────┘                └──────┬─────┘                  │
│                                        │ EXECUTED_AS            │
│                                        ▼                        │
│                                 ┌────────────┐                  │
│                                 │    Run     │                  │
│                                 └──────┬─────┘                  │
│                                        │ OBSERVED_IN            │
│                                        ▼                        │
│   ┌────────────┐                ┌────────────┐                  │
│   │  Failure   │◀───────────────│  Failure   │                  │
│   │ (parent)   │   EVOLVED_INTO │            │                  │
│   └────────────┘                └──────┬─────┘                  │
│                                        │ ADDRESSED_BY           │
│                                        ▼                        │
│   ┌────────────┐   DEPLOYED_AS  ┌────────────┐                  │
│   │ Deployment │◀───────────────│Intervention│                  │
│   └──────┬─────┘                └────────────┘                  │
│          │ ROLLED_BACK_BY                                       │
│          ▼                                                      │
│   ┌────────────┐                                                │
│   │  Rollback  │                                                │
│   └────────────┘                                                │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Node Types

Nodes represent entities in the research process.

```python
class NodeType(str, Enum):
    """Types of nodes in the memory graph."""
    MODEL_VERSION = "model_version"   # Target model version
    HYPOTHESIS = "hypothesis"         # Failure hypothesis
    EXPERIMENT = "experiment"         # Experiment design
    RUN = "run"                       # Single experiment run
    FAILURE_MODE = "failure_mode"     # Discovered failure
    INTERVENTION = "intervention"     # Proposed fix
    SIMULATION = "simulation"         # Counterfactual simulation
    DEPLOYMENT = "deployment"         # Deployed intervention
    ROLLBACK = "rollback"             # Rolled back deployment
```

### Node Structure

```python
@dataclass
class Node:
    """A node in the Research Memory Graph."""
    id: str                        # Unique identifier
    node_type: NodeType            # Type of node
    created_at: datetime           # When created
    valid_from: datetime           # When validity starts
    valid_to: Optional[datetime]   # When validity ends (null = still valid)
    data: dict[str, Any]           # Node-specific data
```

### Node Type Details

#### HYPOTHESIS

Represents a testable hypothesis about potential failures.

```python
{
    "node_type": "hypothesis",
    "data": {
        "target_surface": "tool_use",
        "expected_failure": "parameter_injection",
        "confidence": 0.7,
        "priority": "high",
        "rationale": "Tool parameters not validated",
    }
}
```

#### EXPERIMENT

Represents an experiment design to test a hypothesis.

```python
{
    "node_type": "experiment",
    "data": {
        "hypothesis_id": "hyp_123",
        "stress_type": "tool_injection",
        "mode": "single",
        "constraints": {
            "max_tokens": 100000,
            "timeout_seconds": 300,
        },
    }
}
```

#### RUN

Represents a single experiment run with results.

```python
{
    "node_type": "run",
    "data": {
        "experiment_id": "exp_456",
        "run_number": 3,
        "failure_triggered": true,
        "tokens_used": 15000,
        "latency_ms": 2500,
        "trace": {...},
    }
}
```

#### FAILURE_MODE

Represents a discovered failure.

```python
{
    "node_type": "failure_mode",
    "data": {
        "primary_class": "tool_use",
        "secondary_class": "parameter_error",
        "severity": "S2",
        "trigger_signature": ["stress:tool_injection", "error:validation"],
        "reproducibility": 0.8,
        "is_resolved": false,
    }
}
```

#### INTERVENTION

Represents a proposed fix for a failure.

```python
{
    "node_type": "intervention",
    "data": {
        "intervention_type": "guardrail",
        "payload": {
            "validation_type": "schema",
            "reject_on_fail": true,
        },
        "expected_gains": {"failure_reduction": 0.6},
        "expected_regressions": {"latency_increase": 0.2},
        "risk_tier": "review",
    }
}
```

#### DEPLOYMENT

Represents a deployed intervention.

```python
{
    "node_type": "deployment",
    "data": {
        "intervention_id": "int_789",
        "mode": "production",
        "rollback_state": {...},
        "status": "active",
    }
}
```

---

## Edge Relations

Edges represent relationships between nodes.

```python
class EdgeRelation(str, Enum):
    """Types of edges in the memory graph."""
    TESTED_IN = "tested_in"           # Hypothesis -> Experiment
    EXECUTED_AS = "executed_as"       # Experiment -> Run
    OBSERVED_IN = "observed_in"       # Failure -> Run
    CAUSED_BY = "caused_by"           # Effect -> Cause
    ADDRESSED_BY = "addressed_by"     # Failure -> Intervention
    SIMULATED_BY = "simulated_by"     # Intervention -> Simulation
    DEPLOYED_AS = "deployed_as"       # Intervention -> Deployment
    ROLLED_BACK_BY = "rolled_back_by" # Deployment -> Rollback
    REGRESSED_AS = "regressed_as"     # Deployment -> Failure
    EVOLVED_INTO = "evolved_into"     # Failure -> Failure (evolution)
```

### Edge Structure

```python
@dataclass
class Edge:
    """An edge in the Research Memory Graph."""
    id: str                        # Unique identifier
    src_id: str                    # Source node ID
    dst_id: str                    # Destination node ID
    relation: EdgeRelation         # Relationship type
    created_at: datetime           # When created
    metadata: dict[str, Any]       # Edge-specific data
```

### Relationship Semantics

| Relation | From | To | Meaning |
|----------|------|-----|---------|
| `TESTED_IN` | Hypothesis | Experiment | Hypothesis is tested by this experiment |
| `EXECUTED_AS` | Experiment | Run | Experiment was executed as this run |
| `OBSERVED_IN` | Failure | Run | Failure was observed in this run |
| `CAUSED_BY` | Effect | Cause | Effect was caused by this cause |
| `ADDRESSED_BY` | Failure | Intervention | Failure is addressed by intervention |
| `SIMULATED_BY` | Intervention | Simulation | Intervention was simulated |
| `DEPLOYED_AS` | Intervention | Deployment | Intervention was deployed |
| `ROLLED_BACK_BY` | Deployment | Rollback | Deployment was rolled back |
| `REGRESSED_AS` | Deployment | Failure | Deployment caused this regression |
| `EVOLVED_INTO` | Failure | Failure | Failure evolved into a new form |

---

## Temporal Versioning

Every node has a validity period, enabling temporal queries.

### Validity Period

```python
node.valid_from  # When the node became valid
node.valid_to    # When the node stopped being valid (null = still valid)
node.is_valid    # Check if currently valid
```

### Invalidating Nodes

When findings are superseded or corrected:

```python
# Mark node as no longer valid
graph.invalidate_node(node_id)

# This sets valid_to = now
# Node is still queryable but marked as historical
```

### Temporal Queries

Query the graph state at any point in time:

```python
# What failures did we know about on Jan 15?
deployment_time = datetime(2024, 1, 15, 10, 30)
known_failures = graph.snapshot_at(
    deployment_time,
    node_type=NodeType.FAILURE_MODE
)

# What was the graph state when we deployed?
graph_state = graph.snapshot_at(deployment_time)
```

### Use Cases for Temporal Queries

1. **Forensic Analysis**: "What did we know when the incident occurred?"
2. **Deployment Auditing**: "Were known issues addressed before release?"
3. **Trend Analysis**: "Are failures increasing or decreasing?"
4. **Compliance**: "What was our risk posture at audit time?"

---

## Core Operations

### Node Operations

```python
from tinman.memory.graph import MemoryGraph
from tinman.memory.models import Node, NodeType

# Add a node
node = Node(
    node_type=NodeType.HYPOTHESIS,
    data={"target_surface": "reasoning", "expected_failure": "goal_drift"}
)
node_id = graph.add_node(node)

# Get a node
node = graph.get_node(node_id)

# Invalidate a node (soft delete)
graph.invalidate_node(node_id)
```

### Edge Operations

```python
from tinman.memory.models import Edge, EdgeRelation

# Add an edge
edge = Edge(
    src_id=hypothesis_id,
    dst_id=experiment_id,
    relation=EdgeRelation.TESTED_IN
)
edge_id = graph.add_edge(edge)

# Or use the convenience method
edge = graph.link(
    src_id=hypothesis_id,
    dst_id=experiment_id,
    relation=EdgeRelation.TESTED_IN,
    metadata={"design_version": 1}
)

# Get an edge
edge = graph.get_edge(edge_id)
```

---

## Query Operations

### Get by Type

```python
# Get all hypotheses
hypotheses = graph.get_hypotheses(valid_only=True, limit=100)

# Get all experiments
experiments = graph.get_experiments(valid_only=True)

# Get all failures
failures = graph.get_failures(valid_only=True)

# Get all interventions
interventions = graph.get_interventions(valid_only=True)
```

### Get Neighbors

```python
# Get nodes connected by outgoing edges
related = graph.get_neighbors(
    node_id=failure_id,
    relation=EdgeRelation.ADDRESSED_BY,
    direction="outgoing"
)

# Get nodes connected by incoming edges
causes = graph.get_neighbors(
    node_id=failure_id,
    relation=EdgeRelation.CAUSED_BY,
    direction="incoming"
)
```

### Search by Data

```python
# Find all S3 severity failures
critical_failures = graph.search(
    data_filter={"severity": "S3"},
    node_type=NodeType.FAILURE_MODE
)

# Find interventions with block risk tier
blocked = graph.search(
    data_filter={"risk_tier": "block"},
    node_type=NodeType.INTERVENTION
)

# Find unresolved failures
unresolved = graph.find_unresolved_failures()

# Find high-severity failures
severe = graph.find_failures_by_severity(min_severity="S3")

# Find interventions by risk
risky = graph.find_interventions_by_risk(risk_tier="review")
```

### Temporal Queries

```python
from datetime import datetime

# Get state at a specific time
past_failures = graph.snapshot_at(
    timestamp=datetime(2024, 1, 15),
    node_type=NodeType.FAILURE_MODE
)

# Track failure evolution
evolution = graph.get_failure_evolution(failure_class="goal_drift")
```

---

## Lineage Tracking

Track the causal chain from effect to root cause.

### Get Lineage

```python
# Get full causal lineage
lineage = graph.get_lineage(failure_id, max_depth=10)

# Returns: [(node, edge), (node, edge), ...]
# Starting from the failure back to root causes

for node, edge in lineage:
    print(f"{node.node_type}: {node.data}")
    print(f"  via: {edge.relation}")
```

### Failure Evolution

Track how failures mutate over time:

```python
# Get evolution of a failure class
evolution = graph.get_failure_evolution("goal_drift")

# Shows: Original failure -> Mutation 1 -> Mutation 2 -> ...
for failure in evolution:
    print(f"{failure.created_at}: {failure.data['severity']}")
```

### Example: Full Lineage

```
Failure: goal_drift_v3 (S3)
    │
    ├── EVOLVED_INTO from: goal_drift_v2 (S2)
    │   │
    │   └── EVOLVED_INTO from: goal_drift_v1 (S1)
    │       │
    │       └── OBSERVED_IN: run_exp_001_5
    │           │
    │           └── EXECUTED_AS: experiment_001
    │               │
    │               └── TESTED_IN: hypothesis_goal_drift
```

---

## Recording Findings

Convenience methods for recording research findings.

### Record Hypothesis

```python
node = graph.record_hypothesis(
    target_surface="context_window",
    expected_failure="attention_dilution",
    confidence=0.7,
    priority="high"
)
```

### Record Experiment

```python
node = graph.record_experiment(
    hypothesis_id=hypothesis.id,
    stress_type="context_overflow",
    mode="iterative",
    constraints={
        "max_tokens": 200000,
        "timeout_seconds": 600,
    }
)
# Automatically links to hypothesis via TESTED_IN edge
```

### Record Failure

```python
node = graph.record_failure(
    run_id=run.id,
    primary_class="long_context",
    secondary_class="attention_dilution",
    severity="S2",
    trigger_signature=["stress:context_overflow", "high_tool_usage"],
    reproducibility=0.8,
    parent_failure_id=None  # Set if this evolved from another
)
# Automatically links to run via OBSERVED_IN edge
```

### Record Intervention

```python
node = graph.record_intervention(
    failure_id=failure.id,
    intervention_type="context_limit",
    payload={
        "max_tokens": 100000,
        "strategy": "recency_weighted"
    },
    expected_gains={"failure_reduction": 0.5},
    expected_regressions={"capability_reduction": 0.2},
    risk_tier="review"
)
# Automatically links to failure via ADDRESSED_BY edge
```

### Record Deployment

```python
node = graph.record_deployment(
    intervention_id=intervention.id,
    mode="production",
    rollback_state={"previous_config": {...}}
)
# Automatically links to intervention via DEPLOYED_AS edge
```

### Record Rollback

```python
node = graph.record_rollback(
    deployment_id=deployment.id,
    reason="Latency regression detected",
    regression_failure_id=new_failure.id  # Optional
)
# Links deployment -> rollback and deployment -> regression failure
```

---

## Examples

### Complete Research Cycle Recording

```python
from tinman.memory.graph import MemoryGraph
from tinman.memory.models import NodeType, EdgeRelation
from sqlalchemy.orm import Session

# Initialize graph with database session
graph = MemoryGraph(session)

# 1. Record hypothesis
hypothesis = graph.record_hypothesis(
    target_surface="tool_use",
    expected_failure="parameter_injection",
    confidence=0.7,
    priority="high"
)
print(f"Hypothesis: {hypothesis.id}")

# 2. Record experiment
experiment = graph.record_experiment(
    hypothesis_id=hypothesis.id,
    stress_type="tool_injection",
    mode="adversarial",
    constraints={"max_retries": 3}
)
print(f"Experiment: {experiment.id}")

# 3. Record failure discovered in experiment
failure = graph.record_failure(
    run_id=experiment.id,  # Simplified - normally would link to Run
    primary_class="tool_use",
    secondary_class="parameter_error",
    severity="S2",
    trigger_signature=["injection:path_traversal"],
    reproducibility=0.6
)
print(f"Failure: {failure.id}")

# 4. Record intervention
intervention = graph.record_intervention(
    failure_id=failure.id,
    intervention_type="guardrail",
    payload={"validation": "strict_schema"},
    expected_gains={"failure_reduction": 0.7},
    expected_regressions={"latency_increase": 0.1},
    risk_tier="safe"
)
print(f"Intervention: {intervention.id}")

# 5. Record deployment
deployment = graph.record_deployment(
    intervention_id=intervention.id,
    mode="production",
    rollback_state={"previous_validation": "none"}
)
print(f"Deployment: {deployment.id}")

# Query the complete lineage
lineage = graph.get_lineage(failure.id)
print("\nFailure Lineage:")
for node, edge in lineage:
    print(f"  {node.node_type.value}: {node.id}")
```

### Temporal Analysis

```python
from datetime import datetime, timedelta

# Get failures known at deployment time
deployment_time = datetime(2024, 1, 15, 10, 0)
known_failures = graph.snapshot_at(
    deployment_time,
    node_type=NodeType.FAILURE_MODE
)

print(f"Failures known at deployment: {len(known_failures)}")

# Get failures discovered after deployment
now = datetime.utcnow()
recent_failures = graph.search(
    {"created_after": deployment_time.isoformat()},
    node_type=NodeType.FAILURE_MODE
)

print(f"New failures since deployment: {len(recent_failures)}")

# Check if any deployed intervention caused regression
deployments = graph.get_interventions(valid_only=True)
for dep in deployments:
    regressions = graph.get_neighbors(
        dep.id,
        relation=EdgeRelation.REGRESSED_AS,
        direction="outgoing"
    )
    if regressions:
        print(f"Deployment {dep.id} caused {len(regressions)} regressions")
```

### Finding Related Failures

```python
# Find all failures in the goal_drift family
goal_drift_failures = graph.search(
    {"primary_class": "reasoning", "secondary_class": "goal_drift"},
    node_type=NodeType.FAILURE_MODE
)

# Track their evolution
for failure in goal_drift_failures:
    # Find what this failure evolved from
    parents = graph.get_neighbors(
        failure.id,
        relation=EdgeRelation.EVOLVED_INTO,
        direction="incoming"
    )

    # Find what this failure evolved into
    children = graph.get_neighbors(
        failure.id,
        relation=EdgeRelation.EVOLVED_INTO,
        direction="outgoing"
    )

    print(f"Failure {failure.id}:")
    print(f"  Evolved from: {[p.id for p in parents]}")
    print(f"  Evolved into: {[c.id for c in children]}")
```

### Graph Statistics

```python
stats = graph.get_stats()
print("Memory Graph Statistics:")
for node_type, count in stats.items():
    print(f"  {node_type}: {count}")

# Output:
# Memory Graph Statistics:
#   hypothesis: 45
#   experiment: 120
#   run: 600
#   failure_mode: 32
#   intervention: 28
#   deployment: 15
#   rollback: 3
```

---

## Summary

The Memory Graph provides:

| Capability | Description |
|------------|-------------|
| **Node Storage** | Typed nodes for all research entities |
| **Edge Relations** | Causal and logical relationships |
| **Temporal Versioning** | Query state at any point in time |
| **Lineage Tracking** | Trace from effect to root cause |
| **Search** | Find nodes by data attributes |
| **Evolution Tracking** | See how failures mutate |

This enables:
- **Forensic Analysis** - What did we know when?
- **Knowledge Accumulation** - Learn from all research
- **Pattern Recognition** - Find recurring failures
- **Audit Trail** - Complete history of findings

---

## Next Steps

- [AGENTS.md](AGENTS.md) - How agents use the memory graph
- [ARCHITECTURE.md](ARCHITECTURE.md) - System design overview
- [CONFIGURATION.md](CONFIGURATION.md) - Database configuration
