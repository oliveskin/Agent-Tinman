# Agents

This document provides complete documentation for each autonomous agent in Tinman's research system.

---

## Table of Contents

1. [Overview](#overview)
2. [BaseAgent Framework](#baseagent-framework)
3. [HypothesisEngine](#hypothesisengine)
4. [ExperimentArchitect](#experimentarchitect)
5. [ExperimentExecutor](#experimentexecutor)
6. [FailureDiscoveryAgent](#failurediscoveryagent)
7. [InterventionEngine](#interventionengine)
8. [SimulationEngine](#simulationengine)
9. [Agent Orchestration](#agent-orchestration)

---

## Overview

Tinman uses six autonomous agents that work together to conduct failure research:

```
┌─────────────────────────────────────────────────────────────────┐
│                     AGENT PIPELINE                               │
│                                                                  │
│   ┌───────────────┐      ┌───────────────┐                      │
│   │   Hypothesis  │─────▶│   Experiment  │                      │
│   │    Engine     │      │   Architect   │                      │
│   └───────────────┘      └───────┬───────┘                      │
│                                  │                               │
│                                  ▼                               │
│                          ┌───────────────┐                      │
│                          │   Experiment  │                      │
│                          │   Executor    │                      │
│                          └───────┬───────┘                      │
│                                  │                               │
│                                  ▼                               │
│                          ┌───────────────┐                      │
│                          │   Failure     │                      │
│                          │   Discovery   │                      │
│                          └───────┬───────┘                      │
│                                  │                               │
│                                  ▼                               │
│   ┌───────────────┐      ┌───────────────┐                      │
│   │   Simulation  │◀─────│ Intervention  │                      │
│   │    Engine     │      │    Engine     │                      │
│   └───────────────┘      └───────────────┘                      │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### Agent Summary

| Agent | Purpose | Inputs | Outputs |
|-------|---------|--------|---------|
| **HypothesisEngine** | Generate failure hypotheses | Observations, prior failures | Hypotheses |
| **ExperimentArchitect** | Design experiments | Hypotheses | Experiment designs |
| **ExperimentExecutor** | Run experiments | Experiment designs | Experiment results |
| **FailureDiscoveryAgent** | Classify failures | Experiment results | Discovered failures |
| **InterventionEngine** | Design fixes | Discovered failures | Interventions |
| **SimulationEngine** | Validate fixes | Interventions | Simulation results |

---

## BaseAgent Framework

All agents inherit from `BaseAgent`, which provides common functionality.

### Agent States

```python
class AgentState(str, Enum):
    """Agent lifecycle states."""
    IDLE = "idle"         # Not running
    RUNNING = "running"   # Executing
    PAUSED = "paused"     # Temporarily stopped
    COMPLETED = "completed"  # Finished successfully
    FAILED = "failed"     # Encountered error
```

### AgentContext

Context passed to all agent operations:

```python
@dataclass
class AgentContext:
    """Context passed to agent operations."""
    mode: OperatingMode           # LAB/SHADOW/PRODUCTION
    session_id: str               # Unique session ID
    parent_id: Optional[str]      # Parent agent ID
    metadata: dict[str, Any]      # Additional context
    started_at: datetime          # When session started
```

### AgentResult

Standard result structure returned by all agents:

```python
@dataclass
class AgentResult:
    """Result from an agent operation."""
    agent_id: str                 # ID of the agent
    agent_type: str               # Type name
    success: bool                 # Whether operation succeeded
    data: dict[str, Any]          # Output data
    error: Optional[str]          # Error message if failed
    duration_ms: int              # Execution duration
    created_at: datetime          # When result was created
```

### Common Methods

```python
class BaseAgent(ABC):
    """Base class for all Tinman agents."""

    @property
    @abstractmethod
    def agent_type(self) -> str:
        """Unique identifier for this agent type."""
        pass

    @abstractmethod
    async def execute(self, context: AgentContext, **kwargs) -> AgentResult:
        """Execute the agent's primary function."""
        pass

    async def run(self, context: AgentContext, **kwargs) -> AgentResult:
        """Run agent with lifecycle management."""
        # Handles state transitions, event publishing, error handling

    def pause(self) -> None:
        """Pause agent execution."""

    def resume(self) -> None:
        """Resume paused agent."""
```

---

## HypothesisEngine

**Purpose:** Generate testable hypotheses about potential failure modes.

**Agent Type:** `hypothesis_engine`

### Description

The HypothesisEngine doesn't use templates—it uses genuine LLM reasoning to:

- Analyze past failures and find patterns
- Identify unexplored attack surfaces
- Generate novel hypotheses based on observations
- Prioritize based on learned priors

### Inputs

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| None required | - | - | Uses internal sources (memory graph, adaptive memory) |

### Outputs

```python
{
    "hypothesis_count": int,          # Number generated
    "hypotheses": [                   # List of hypotheses
        {
            "id": str,
            "target_surface": str,    # What to test
            "expected_failure": str,  # What might fail
            "failure_class": str,     # Taxonomy class
            "confidence": float,      # 0-1
            "priority": str,          # low/medium/high/critical
            "rationale": str,         # Why this hypothesis
            "suggested_experiment": str,
        }
    ],
    "used_llm_reasoning": bool,       # Whether LLM was used
}
```

### Hypothesis Structure

```python
@dataclass
class Hypothesis:
    """A hypothesis about potential failure modes."""
    id: str
    target_surface: str       # What we're testing
    expected_failure: str     # What failure we expect
    failure_class: FailureClass
    confidence: float         # 0-1 confidence
    priority: str             # low, medium, high, critical
    rationale: str
    suggested_experiment: str
    evidence: list[str]
    metadata: dict[str, Any]
```

### Sources of Hypotheses

1. **LLM Reasoning** - When LLM backbone is available, generates creative hypotheses
2. **Prior Failures** - Patterns from past discoveries
3. **Adaptive Memory** - What has worked before
4. **Attack Surface Analysis** - Systematic enumeration of surfaces
5. **Failure Taxonomy** - Derivation from known failure classes

### Example Usage

```python
from tinman.agents.hypothesis_engine import HypothesisEngine, Hypothesis
from tinman.agents.base import AgentContext
from tinman.config.modes import Mode

engine = HypothesisEngine(
    graph=memory_graph,
    llm_backbone=llm,
    adaptive_memory=adaptive_memory,
)

context = AgentContext(mode=Mode.LAB)
result = await engine.run(context)

for hypothesis in result.data["hypotheses"]:
    print(f"Hypothesis: {hypothesis['expected_failure']}")
    print(f"Confidence: {hypothesis['confidence']}")
    print(f"Priority: {hypothesis['priority']}")
```

---

## ExperimentArchitect

**Purpose:** Design experiments to test hypotheses.

**Agent Type:** `experiment_architect`

### Description

Converts hypotheses into concrete experiment designs with:

- Specific test cases and prompts
- Stress parameters tailored to the failure class
- Success/failure criteria
- Resource estimates

### Inputs

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `hypotheses` | `list[Hypothesis]` | Yes | Hypotheses to design experiments for |

### Outputs

```python
{
    "experiment_count": int,
    "experiments": [
        {
            "id": str,
            "hypothesis_id": str,
            "name": str,
            "description": str,
            "stress_type": str,
            "mode": str,              # single, iterative, adversarial
            "parameters": dict,
            "estimated_runs": int,
            "estimated_tokens": int,
        }
    ],
    "used_llm_design": bool,
}
```

### ExperimentDesign Structure

```python
@dataclass
class ExperimentDesign:
    """Design specification for an experiment."""
    id: str
    hypothesis_id: str
    name: str
    description: str
    stress_type: str          # prompt_injection, context_overflow, etc.
    mode: str                 # single, iterative, adversarial

    parameters: dict[str, Any]
    constraints: dict[str, Any]

    success_criteria: list[str]
    failure_indicators: list[str]

    test_cases: list[dict[str, Any]]  # Actual prompts to run

    estimated_runs: int
    estimated_tokens: int
    timeout_seconds: int
```

### Stress Types by Failure Class

| Failure Class | Stress Types |
|---------------|--------------|
| REASONING | `logical_chain`, `goal_conflict` |
| LONG_CONTEXT | `context_overflow`, `attention_dilution` |
| TOOL_USE | `tool_injection`, `tool_chain` |
| FEEDBACK_LOOP | `output_recursion`, `amplification` |
| DEPLOYMENT | `state_desync`, `resource_exhaustion` |

### Example Usage

```python
from tinman.agents.experiment_architect import ExperimentArchitect

architect = ExperimentArchitect(
    graph=memory_graph,
    llm_backbone=llm,
)

result = await architect.run(
    context,
    hypotheses=hypotheses,  # From HypothesisEngine
)

for experiment in result.data["experiments"]:
    print(f"Experiment: {experiment['name']}")
    print(f"Stress type: {experiment['stress_type']}")
    print(f"Estimated runs: {experiment['estimated_runs']}")
```

---

## ExperimentExecutor

**Purpose:** Run experiments by actually probing models.

**Agent Type:** `experiment_executor`

### Description

The core research capability—takes experiment designs and runs them against target models, collecting real behavioral data.

**Key capabilities:**
- Run test cases against models via ModelClient
- Analyze responses for failure indicators using LLM
- Collect traces, timing, and behavioral data
- Detect failures through pattern matching and LLM analysis

### Inputs

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `experiments` | `list[ExperimentDesign]` | Yes | Experiments to run |
| `skip_approval` | `bool` | No | Skip approval check |

### Outputs

```python
{
    "experiment_count": int,
    "skipped_count": int,
    "skipped_experiments": list[str],
    "total_runs": int,
    "failures_found": int,
    "results": [
        {
            "id": str,
            "experiment_id": str,
            "hypothesis_id": str,
            "total_runs": int,
            "failures_triggered": int,
            "reproduction_rate": float,
            "hypothesis_validated": bool,
            "confidence": float,
            "notes": str,
            "total_tokens": int,
            "total_duration_ms": int,
        }
    ],
}
```

### Mode-Based Run Limits

| Mode | Runs | Description |
|------|------|-------------|
| LAB | Full | Run all estimated runs |
| SHADOW | 50% | Run half the estimated runs (min 3) |
| PRODUCTION | Min | Run minimal runs (max 3) |

### Approval Integration

In PRODUCTION mode, experiments require human approval before execution:

```python
# Approval is requested via ApprovalHandler
approved = await self.approval_handler.approve_experiment(
    experiment_name=experiment.name,
    hypothesis=experiment.hypothesis_id,
    estimated_runs=experiment.estimated_runs,
    estimated_cost_usd=estimated_cost,
    stress_type=experiment.stress_type,
)
```

### Example Usage

```python
from tinman.agents.experiment_executor import ExperimentExecutor

executor = ExperimentExecutor(
    graph=memory_graph,
    model_client=model_client,
    llm_backbone=llm,
    approval_handler=approval_handler,
)

result = await executor.run(
    context,
    experiments=experiments,  # From ExperimentArchitect
)

print(f"Total runs: {result.data['total_runs']}")
print(f"Failures found: {result.data['failures_found']}")
```

---

## FailureDiscoveryAgent

**Purpose:** Discover and classify failures from experiment results.

**Agent Type:** `failure_discovery`

### Description

Analyzes experiment results to extract, classify, and understand failures. Uses LLM for deep analysis when available.

**Analysis capabilities:**
- What actually went wrong (deep analysis)
- Why it went wrong (root cause)
- What it means (implications)
- What to do about it (recommendations)

### Inputs

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `results` | `list[ExperimentResult]` | Yes | Experiment results to analyze |

### Outputs

```python
{
    "failures_discovered": int,
    "novel_failures": int,
    "failures": [
        {
            "id": str,
            "primary_class": str,
            "secondary_class": str,
            "severity": str,           # S0-S4
            "description": str,
            "trigger_signature": list[str],
            "reproducibility": float,
            "is_novel": bool,
            "classification_confidence": float,
            "llm_analysis": str,
            "contributing_factors": list[str],
            "key_insight": str,
        }
    ],
    "used_llm_analysis": bool,
}
```

### DiscoveredFailure Structure

```python
@dataclass
class DiscoveredFailure:
    """A newly discovered failure mode."""
    id: str

    # Classification
    primary_class: FailureClass
    secondary_class: Optional[str]
    severity: Severity

    # Details
    description: str
    trigger_signature: list[str]
    reproducibility: float

    # Source
    experiment_id: str
    run_ids: list[str]

    # Analysis
    classification_confidence: float
    causal_analysis: Optional[dict[str, Any]]

    # LLM-generated insights
    llm_analysis: str
    contributing_factors: list[str]
    key_insight: str

    # Status
    is_novel: bool
    parent_failure_id: Optional[str]
```

### LLM Analysis Modes

When LLM is available, performs two analysis passes:

1. **Failure Analysis** - Classify and understand what went wrong
2. **Root Cause Analysis** - Identify underlying causes

### Example Usage

```python
from tinman.agents.failure_discovery import FailureDiscoveryAgent

discovery = FailureDiscoveryAgent(
    graph=memory_graph,
    llm_backbone=llm,
    adaptive_memory=adaptive_memory,
)

result = await discovery.run(
    context,
    results=experiment_results,  # From ExperimentExecutor
)

for failure in result.data["failures"]:
    print(f"[{failure['severity']}] {failure['primary_class']}")
    print(f"Description: {failure['description']}")
    print(f"Novel: {failure['is_novel']}")
```

---

## InterventionEngine

**Purpose:** Design fixes for discovered failures.

**Agent Type:** `intervention_engine`

### Description

Proposes concrete interventions to address discovered failures. Uses LLM for creative intervention design when available.

**Intervention types:**
- Prompt patches
- Guardrails
- Parameter tuning
- Tool restrictions
- Circuit breakers
- Human escalation

### Inputs

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `failures` | `list[DiscoveredFailure]` | Yes | Failures to address |

### Outputs

```python
{
    "intervention_count": int,
    "by_risk_tier": {
        "safe": int,
        "review": int,
        "block": int,
    },
    "interventions": [
        {
            "id": str,
            "failure_id": str,
            "type": str,
            "name": str,
            "description": str,
            "risk_tier": str,
            "requires_approval": bool,
            "expected_gains": dict,
            "expected_regressions": dict,
        }
    ],
    "used_llm_design": bool,
}
```

### Intervention Types

```python
class InterventionType(str, Enum):
    """Types of interventions."""
    PROMPT_PATCH = "prompt_patch"         # Modify system prompt
    GUARDRAIL = "guardrail"               # Add input/output filter
    PARAMETER_TUNE = "parameter_tune"     # Adjust model parameters
    TOOL_RESTRICTION = "tool_restriction" # Restrict tool access
    CONTEXT_LIMIT = "context_limit"       # Limit context window
    RETRY_POLICY = "retry_policy"         # Change retry behavior
    CIRCUIT_BREAKER = "circuit_breaker"   # Add failure circuit breaker
    HUMAN_REVIEW = "human_review"         # Route to human review
```

### Intervention Structure

```python
@dataclass
class Intervention:
    """A proposed intervention to address a failure."""
    id: str
    failure_id: str

    intervention_type: InterventionType
    name: str
    description: str
    payload: dict[str, Any]      # The actual fix

    expected_gains: dict[str, float]
    expected_regressions: dict[str, float]

    risk_tier: RiskTier
    risk_factors: list[str]

    rationale: str
    requires_approval: bool
    reversible: bool
```

### Deployment with Approval

```python
# Deploy intervention with HITL approval
result = await engine.deploy_intervention(
    context,
    intervention=intervention,
    skip_approval=False,
)

if result["deployed"]:
    print("Intervention deployed successfully")
else:
    print(f"Deployment failed: {result['status']}")
```

### Example Usage

```python
from tinman.agents.intervention_engine import InterventionEngine

intervention_engine = InterventionEngine(
    graph=memory_graph,
    llm_backbone=llm,
    approval_handler=approval_handler,
)

result = await intervention_engine.run(
    context,
    failures=discovered_failures,  # From FailureDiscoveryAgent
)

for intervention in result.data["interventions"]:
    print(f"Intervention: {intervention['name']}")
    print(f"Type: {intervention['type']}")
    print(f"Risk: {intervention['risk_tier']}")
```

---

## SimulationEngine

**Purpose:** Validate interventions via counterfactual replay.

**Agent Type:** `simulation_engine`

### Description

Simulates interventions before deployment by replaying historical failure traces with the intervention applied.

**Capabilities:**
- Replay prompts through model with intervention applied
- Use LLM to analyze whether intervention improved behavior
- Build statistical confidence in intervention effectiveness

### Inputs

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `interventions` | `list[Intervention]` | Yes | Interventions to simulate |
| `num_runs` | `int` | No | Number of simulation runs (default: 5) |
| `skip_approval` | `bool` | No | Skip approval check |

### Outputs

```python
{
    "simulations_run": int,
    "skipped_count": int,
    "skipped_interventions": list[str],
    "improved": int,
    "deploy_recommended": int,
    "results": [
        {
            "id": str,
            "intervention_id": str,
            "outcome": str,           # improved/no_change/degraded/side_effect/inconclusive
            "confidence": float,
            "avg_failure_rate_improvement": float,
            "avg_latency_impact": float,
            "side_effects": list[str],
            "regressions": list[str],
            "deploy_recommended": bool,
            "recommendation_reason": str,
            "run_count": int,
        }
    ],
}
```

### Simulation Outcomes

```python
class SimulationOutcome(str, Enum):
    """Possible simulation outcomes."""
    IMPROVED = "improved"         # Intervention helps
    NO_CHANGE = "no_change"       # No effect
    DEGRADED = "degraded"         # Made things worse
    SIDE_EFFECT = "side_effect"   # Unintended consequence
    INCONCLUSIVE = "inconclusive" # Can't determine
```

### Simulation Modes

| Scenario | Behavior |
|----------|----------|
| ModelClient + LLM | Full replay with real model, LLM analyzes results |
| LLM only | LLM estimates intervention effect without replay |
| Neither | Heuristic simulation based on intervention type |

### Deployment Recommendations

Production mode has strict criteria:
- Outcome must be IMPROVED
- Confidence must be >= 0.7
- No regressions observed
- Latency impact < 500ms

### Example Usage

```python
from tinman.agents.simulation_engine import SimulationEngine

simulation = SimulationEngine(
    graph=memory_graph,
    model_client=model_client,
    llm_backbone=llm,
)

result = await simulation.run(
    context,
    interventions=interventions,  # From InterventionEngine
    num_runs=10,
)

for sim in result.data["results"]:
    print(f"Intervention: {sim['intervention_id']}")
    print(f"Outcome: {sim['outcome']}")
    print(f"Deploy recommended: {sim['deploy_recommended']}")
    print(f"Reason: {sim['recommendation_reason']}")
```

---

## Agent Orchestration

The `Tinman` class orchestrates all agents through a research cycle.

### Research Cycle Flow

```python
async def research_cycle(
    self,
    focus: str = "",
    max_hypotheses: int = 10,
    max_experiments: int = 5,
    max_interventions: int = 5,
) -> ResearchCycleResult:
    """Run a complete research cycle."""

    # Phase 1: Generate hypotheses
    hyp_result = await self.hypothesis_engine.run(context)
    hypotheses = hyp_result.data["hypotheses"][:max_hypotheses]

    # Phase 2: Design experiments
    exp_design_result = await self.experiment_architect.run(
        context, hypotheses=hypotheses
    )
    experiments = exp_design_result.data["experiments"][:max_experiments]

    # Phase 3: Execute experiments
    exec_result = await self.experiment_executor.run(
        context, experiments=experiments
    )

    # Phase 4: Discover failures
    discovery_result = await self.failure_discovery.run(
        context, results=exec_result.data["results"]
    )
    failures = discovery_result.data["failures"]

    # Phase 5: Design interventions
    intervention_result = await self.intervention_engine.run(
        context, failures=failures
    )
    interventions = intervention_result.data["interventions"][:max_interventions]

    # Phase 6: Simulate interventions
    sim_result = await self.simulation_engine.run(
        context, interventions=interventions
    )

    # Phase 7: Learn (update adaptive memory)
    if self.adaptive_memory:
        self._update_learning(cycle_results)

    return ResearchCycleResult(...)
```

### Agent Dependencies

```
┌─────────────────────────────────────────────────────────────────┐
│                     AGENT DEPENDENCIES                           │
│                                                                  │
│                    ┌───────────────┐                            │
│                    │ Memory Graph  │                            │
│                    └───────┬───────┘                            │
│                            │                                     │
│                            ▼                                     │
│  ┌─────────────────────────┴─────────────────────────┐         │
│  │                                                    │         │
│  ▼          ▼          ▼          ▼          ▼       ▼         │
│ Hyp       ExpArch    ExpExec    Fail       Int      Sim        │
│ Engine    itect      utor       Disc       Engine   Engine     │
│  │          │          │          │          │        │         │
│  └──────────┴──────────┴──────────┴──────────┴────────┘         │
│                            │                                     │
│                            ▼                                     │
│                    ┌───────────────┐                            │
│                    │ LLM Backbone  │                            │
│                    └───────────────┘                            │
│                                                                  │
│  Approval Handler: ExperimentExecutor, InterventionEngine,      │
│                    SimulationEngine                              │
│                                                                  │
│  Model Client: ExperimentExecutor, SimulationEngine             │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### Creating Agents

```python
from tinman.agents import (
    HypothesisEngine,
    ExperimentArchitect,
    ExperimentExecutor,
    FailureDiscoveryAgent,
    InterventionEngine,
    SimulationEngine,
)

# Create with all dependencies
hypothesis_engine = HypothesisEngine(
    graph=memory_graph,
    llm_backbone=llm_backbone,
    adaptive_memory=adaptive_memory,
    event_bus=event_bus,
)

experiment_architect = ExperimentArchitect(
    graph=memory_graph,
    llm_backbone=llm_backbone,
    event_bus=event_bus,
)

experiment_executor = ExperimentExecutor(
    graph=memory_graph,
    model_client=model_client,
    llm_backbone=llm_backbone,
    approval_handler=approval_handler,
    event_bus=event_bus,
)

failure_discovery = FailureDiscoveryAgent(
    graph=memory_graph,
    llm_backbone=llm_backbone,
    adaptive_memory=adaptive_memory,
    event_bus=event_bus,
)

intervention_engine = InterventionEngine(
    graph=memory_graph,
    llm_backbone=llm_backbone,
    approval_handler=approval_handler,
    event_bus=event_bus,
)

simulation_engine = SimulationEngine(
    graph=memory_graph,
    model_client=model_client,
    llm_backbone=llm_backbone,
    approval_handler=approval_handler,
    event_bus=event_bus,
)
```

---

## Summary

| Agent | Role in Cycle | LLM-Enhanced |
|-------|---------------|--------------|
| **HypothesisEngine** | Generate testable hypotheses | Creative hypothesis generation |
| **ExperimentArchitect** | Design experiments | Custom test case generation |
| **ExperimentExecutor** | Run experiments | Response analysis for failures |
| **FailureDiscoveryAgent** | Classify failures | Deep failure analysis, RCA |
| **InterventionEngine** | Design fixes | Creative intervention design |
| **SimulationEngine** | Validate fixes | Replay analysis |

All agents follow the same patterns:
- Inherit from BaseAgent
- Use AgentContext for mode-aware operation
- Return standardized AgentResult
- Integrate with MemoryGraph for knowledge persistence
- Support HITL via ApprovalHandler where appropriate

---

## Next Steps

- [MEMORY.md](MEMORY.md) - Memory graph used by agents
- [HITL.md](HITL.md) - Approval integration details
- [CONFIGURATION.md](CONFIGURATION.md) - Agent configuration options
