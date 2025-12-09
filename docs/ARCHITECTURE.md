# Architecture

This document describes Tinman's system architecture, component interactions, and data flow. It's intended for contributors and users who need to understand how the system works internally.

---

## Table of Contents

1. [System Overview](#system-overview)
2. [Component Architecture](#component-architecture)
3. [Data Flow](#data-flow)
4. [Agent System](#agent-system)
5. [Memory Graph](#memory-graph)
6. [HITL Infrastructure](#hitl-infrastructure)
7. [Event System](#event-system)
8. [Extension Points](#extension-points)

---

## System Overview

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                              TINMAN                                      │
│                                                                          │
│  ┌────────────────────────────────────────────────────────────────────┐ │
│  │                         User Interface                              │ │
│  │     ┌─────────┐      ┌─────────┐      ┌─────────────────┐         │ │
│  │     │   CLI   │      │   TUI   │      │   Python API    │         │ │
│  │     └────┬────┘      └────┬────┘      └────────┬────────┘         │ │
│  └──────────┼───────────────┼─────────────────────┼───────────────────┘ │
│             │               │                     │                      │
│             └───────────────┴──────────┬──────────┘                      │
│                                        │                                 │
│  ┌─────────────────────────────────────▼────────────────────────────┐   │
│  │                      Tinman Orchestrator                          │   │
│  │                        (tinman.py)                                │   │
│  └─────────────────────────────────────┬────────────────────────────┘   │
│                                        │                                 │
│       ┌────────────────────────────────┼────────────────────────────┐   │
│       │                                │                            │   │
│       ▼                                ▼                            ▼   │
│  ┌─────────────┐              ┌─────────────────┐          ┌──────────┐│
│  │   Agents    │              │  Infrastructure │          │ Reasoning ││
│  │             │              │                 │          │          ││
│  │ Hypothesis  │◀────────────▶│  Memory Graph   │◀────────▶│   LLM    ││
│  │ Architect   │              │  Event Bus      │          │ Backbone ││
│  │ Executor    │              │  Approval       │          │ Adaptive ││
│  │ Discovery   │              │  Risk Eval      │          │ Memory   ││
│  │ Intervene   │              │  Control Plane  │          │          ││
│  │ Simulate    │              │                 │          │          ││
│  └─────────────┘              └─────────────────┘          └──────────┘│
│                                        │                                 │
│                                        ▼                                 │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │                        Persistence Layer                          │   │
│  │        ┌──────────────┐              ┌──────────────┐            │   │
│  │        │  PostgreSQL  │              │ Model Clients │            │   │
│  │        │  (Knowledge) │              │ (OpenAI/etc) │            │   │
│  │        └──────────────┘              └──────────────┘            │   │
│  └──────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
```

### Key Design Principles

1. **Separation of Concerns**
   - Agents handle domain logic (research tasks)
   - Infrastructure handles cross-cutting concerns (approval, events, persistence)
   - Reasoning handles intelligence (LLM interaction, pattern learning)

2. **Event-Driven Communication**
   - Components communicate via EventBus
   - Loose coupling enables extensibility
   - Audit trail via event history

3. **Mode-Aware Behavior**
   - All components respect operating mode
   - Same code, different permissions
   - Progressive rollout supported

4. **Human-in-the-Loop by Design**
   - Approval gates at critical points
   - Risk evaluation for all actions
   - Configurable autonomy levels

---

## Component Architecture

### Directory Structure

```
tinman/
├── __init__.py              # Package exports
├── tinman.py                # Main orchestrator class
│
├── agents/                  # Autonomous research agents
│   ├── __init__.py
│   ├── base.py              # BaseAgent abstract class
│   ├── hypothesis_engine.py # Generates failure hypotheses
│   ├── experiment_architect.py # Designs experiments
│   ├── experiment_executor.py  # Runs experiments
│   ├── failure_discovery.py    # Classifies failures
│   ├── intervention_engine.py  # Proposes fixes
│   └── simulation_engine.py    # Validates interventions
│
├── config/                  # Configuration management
│   ├── __init__.py
│   ├── modes.py             # Operating modes (LAB/SHADOW/PRODUCTION)
│   └── settings.py          # Settings dataclasses
│
├── core/                    # Infrastructure components
│   ├── __init__.py
│   ├── approval_gate.py     # Tracks approval requests
│   ├── approval_handler.py  # Coordinates HITL approvals
│   ├── control_plane.py     # System state management
│   ├── event_bus.py         # Pub/sub event system
│   ├── risk_evaluator.py    # Risk tier assessment
│   ├── tools.py             # Guarded tool execution
│   ├── risk_policy.py       # Policy-driven risk matrix
│   ├── cost_tracker.py      # Budget enforcement
│   └── metrics.py           # Prometheus metrics
│
├── db/                      # Database layer
│   ├── __init__.py
│   ├── connection.py        # SQLAlchemy connection
│   ├── models.py            # ORM models
│   └── audit.py             # Durable audit trail (AuditLog, ApprovalDecision)
│
├── ingest/                  # Trace ingestion adapters
│   ├── __init__.py
│   ├── base.py              # TraceAdapter base class
│   ├── otlp.py              # OpenTelemetry OTLP adapter
│   ├── datadog.py           # Datadog APM adapter
│   ├── xray.py              # AWS X-Ray adapter
│   ├── json_adapter.py      # Generic JSON adapter
│   └── registry.py          # Auto-detection and registry
│
├── service/                 # HTTP API service
│   ├── __init__.py
│   ├── app.py               # FastAPI application
│   └── models.py            # Pydantic request/response models
│
├── integrations/            # External integrations
│   ├── __init__.py
│   ├── model_client.py      # Base model client
│   ├── openai_client.py     # OpenAI integration
│   ├── anthropic_client.py  # Anthropic integration
│   └── pipeline_adapter.py  # Hook into existing pipelines
│
├── memory/                  # Knowledge graph
│   ├── __init__.py
│   ├── graph.py             # MemoryGraph implementation
│   ├── models.py            # Node/Edge data models
│   └── repository.py        # Graph persistence
│
├── reasoning/               # LLM-powered reasoning
│   ├── __init__.py
│   ├── llm_backbone.py      # Core LLM reasoning
│   ├── adaptive_memory.py   # Pattern learning
│   ├── insight_synthesizer.py # Report generation
│   └── prompts.py           # Prompt templates
│
├── reporting/               # Partner-facing reports
│   ├── __init__.py
│   ├── base.py              # BaseReport class
│   ├── executive.py         # ExecutiveSummaryReport
│   ├── technical.py         # TechnicalAnalysisReport
│   ├── compliance.py        # ComplianceReport
│   └── export.py            # Multi-format export (JSON, MD, HTML, PDF, CSV)
│
├── taxonomy/                # Failure classification
│   ├── __init__.py
│   ├── failure_types.py     # FailureClass, Severity enums
│   ├── classifiers.py       # Classification logic
│   └── causal_linker.py     # Root cause analysis
│
├── tui/                     # Terminal UI
│   ├── __init__.py
│   ├── app.py               # Textual app
│   └── styles.tcss          # CSS styling
│
└── utils/                   # Utilities
    ├── __init__.py
    ├── id_gen.py            # ID generation
    ├── logging_setup.py     # Logging configuration
    └── time_utils.py        # Time utilities
```

### Component Responsibilities

| Component | Responsibility | Key Classes |
|-----------|---------------|-------------|
| **Orchestrator** | Coordinates research cycles | `Tinman` |
| **Agents** | Execute research tasks | `BaseAgent`, `HypothesisEngine`, etc. |
| **Memory** | Persistent knowledge store | `MemoryGraph`, `Node`, `Edge` |
| **Reasoning** | LLM-powered intelligence | `LLMBackbone`, `AdaptiveMemory` |
| **Core** | Infrastructure services | `ApprovalHandler`, `EventBus`, `RiskEvaluator`, `CostTracker`, `Metrics` |
| **Service** | HTTP API | `FastAPI app`, `Pydantic models` |
| **Ingest** | Trace ingestion | `OTLPAdapter`, `DatadogAdapter`, `XRayAdapter` |
| **Config** | Settings and modes | `Settings`, `Mode` |
| **Taxonomy** | Failure classification | `FailureClass`, `Severity` |
| **Integrations** | External systems | `ModelClient`, `PipelineAdapter` |

---

## Data Flow

### Research Cycle Data Flow

```
┌──────────────────────────────────────────────────────────────────────────┐
│                        RESEARCH CYCLE DATA FLOW                           │
└──────────────────────────────────────────────────────────────────────────┘

┌─────────────┐     observations      ┌─────────────────┐
│   Memory    │◀─────────────────────│    Hypothesis   │
│   Graph     │                       │     Engine      │
│             │─────hypotheses───────▶│                 │
└─────────────┘                       └────────┬────────┘
      ▲                                        │
      │                              List[Hypothesis]
      │                                        │
      │                                        ▼
      │                               ┌─────────────────┐
      │                               │   Experiment    │
      │◀──────experiments────────────│   Architect     │
      │                               │                 │
      │                               └────────┬────────┘
      │                                        │
      │                            List[ExperimentDesign]
      │                                        │
      │                                        ▼
      │                               ┌─────────────────┐
      │                        ┌─────│   Experiment    │
      │                        │     │   Executor      │──────┐
      │                        │     │                 │      │
      │                        │     └────────┬────────┘      │
      │                        │              │               │
      │                   [APPROVAL]    List[Result]     [LLM CALLS]
      │                        │              │               │
      │                        ▼              ▼               ▼
      │               ┌─────────────┐  ┌─────────────────┐  ┌─────────┐
      │               │  Approval   │  │     Failure     │  │  Model  │
      │               │  Handler    │  │   Discovery     │  │  Client │
      │               └─────────────┘  └────────┬────────┘  └─────────┘
      │                                         │
      │◀─────────failures────────List[DiscoveredFailure]
      │                                         │
      │                                         ▼
      │                               ┌─────────────────┐
      │                        ┌─────│  Intervention   │
      │                        │     │    Engine       │
      │                        │     └────────┬────────┘
      │                        │              │
      │                   [APPROVAL]   List[Intervention]
      │                        │              │
      │◀──────interventions────┘              ▼
      │                               ┌─────────────────┐
      │                               │   Simulation    │
      │                               │    Engine       │──────[APPROVAL]
      │                               └────────┬────────┘
      │                                        │
      │◀────────simulations─────List[SimulationResult]
      │
      ▼
┌─────────────┐
│   Updated   │
│   Graph     │
└─────────────┘
```

### Data Transformations

Each agent transforms data:

| Agent | Input | Output |
|-------|-------|--------|
| HypothesisEngine | Prior knowledge, observations | `List[Hypothesis]` |
| ExperimentArchitect | `List[Hypothesis]` | `List[ExperimentDesign]` |
| ExperimentExecutor | `List[ExperimentDesign]` | `List[ExperimentResult]` |
| FailureDiscovery | `List[ExperimentResult]` | `List[DiscoveredFailure]` |
| InterventionEngine | `List[DiscoveredFailure]` | `List[Intervention]` |
| SimulationEngine | `List[Intervention]` | `List[SimulationResult]` |

### Data Models

Key data structures:

```python
@dataclass
class Hypothesis:
    id: str
    target_surface: str      # e.g., "reasoning", "tool_use"
    expected_failure: str    # Predicted failure type
    failure_class: FailureClass
    confidence: float        # 0.0 - 1.0
    priority: int
    rationale: str
    suggested_experiment: str

@dataclass
class ExperimentDesign:
    id: str
    hypothesis_id: str
    stress_type: str
    parameters: dict
    expected_outcome: str
    estimated_runs: int
    estimated_cost_usd: float
    timeout_seconds: int

@dataclass
class DiscoveredFailure:
    id: str
    experiment_id: str
    failure_class: FailureClass
    subtype: str
    severity: Severity
    description: str
    root_cause: str
    reproducibility: float
    evidence: list[dict]

@dataclass
class Intervention:
    id: str
    failure_id: str
    type: InterventionType
    description: str
    implementation: dict
    estimated_effectiveness: float
    risk_tier: RiskTier
    rollback_plan: str
```

---

## Agent System

### Base Agent Design

All agents inherit from `BaseAgent`:

```python
class BaseAgent(ABC):
    """Abstract base class for all research agents."""

    def __init__(
        self,
        llm: Optional[LLMBackbone] = None,
        graph: Optional[MemoryGraph] = None,
        event_bus: Optional[EventBus] = None,
        approval_handler: Optional[ApprovalHandler] = None,
        config: Optional[dict] = None,
    ):
        self.llm = llm
        self.graph = graph
        self.event_bus = event_bus
        self.approval_handler = approval_handler
        self.config = config or {}
        self.state = AgentState.IDLE

    @property
    @abstractmethod
    def agent_type(self) -> str:
        """Return agent type identifier."""
        pass

    async def run(self, context: AgentContext, **kwargs) -> AgentResult:
        """Execute the agent with lifecycle management."""
        self.state = AgentState.RUNNING
        try:
            result = await self.execute(context, **kwargs)
            self.state = AgentState.COMPLETED
            return result
        except Exception as e:
            self.state = AgentState.FAILED
            raise

    @abstractmethod
    async def execute(self, context: AgentContext, **kwargs) -> AgentResult:
        """Implement agent-specific logic."""
        pass
```

### Agent Context

Agents receive context for execution:

```python
@dataclass
class AgentContext:
    mode: Mode                    # Operating mode
    session_id: str               # Research session
    cycle_id: Optional[str]       # Current cycle
    focus: Optional[str]          # Research focus area
    prior_results: dict           # Results from previous agents
    metadata: dict                # Additional context
```

### Agent Result

Agents return standardized results:

```python
@dataclass
class AgentResult:
    agent_type: str
    success: bool
    data: dict                    # Agent-specific output
    errors: list[str]
    warnings: list[str]
    metrics: dict                 # Performance metrics
    duration_ms: int
```

### Agent Communication

Agents communicate via:

1. **Direct data passing** - Orchestrator passes results between agents
2. **Memory Graph** - Persistent shared state
3. **Event Bus** - Async notifications

```python
# In research_cycle()
hypothesis_result = await self.hypothesis_engine.run(context)
hypotheses = hypothesis_result.data["hypotheses"]

# Pass to next agent
architect_result = await self.experiment_architect.run(
    context,
    hypotheses=hypotheses
)
```

---

## Memory Graph

### Graph Model

```
┌─────────────────────────────────────────────────────────────────┐
│                        MEMORY GRAPH MODEL                        │
│                                                                  │
│   Node Types:                                                    │
│   ┌────────────┐  ┌────────────┐  ┌────────────┐               │
│   │ HYPOTHESIS │  │ EXPERIMENT │  │  FAILURE   │               │
│   └────────────┘  └────────────┘  └────────────┘               │
│   ┌────────────┐  ┌────────────┐  ┌────────────┐               │
│   │INTERVENTION│  │ DEPLOYMENT │  │  ROLLBACK  │               │
│   └────────────┘  └────────────┘  └────────────┘               │
│                                                                  │
│   Edge Relations:                                                │
│   ─────────────────────────────────────────────────             │
│   TESTED_IN:     Hypothesis → Experiment                        │
│   OBSERVED_IN:   Failure → Experiment                           │
│   ADDRESSED_BY:  Failure → Intervention                         │
│   EVOLVED_INTO:  Failure → Failure                              │
│   DEPLOYED_AS:   Intervention → Deployment                      │
│   ROLLED_BACK_BY: Deployment → Rollback                         │
│   REGRESSED_AS:  Intervention → Failure                         │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### Temporal Semantics

Each node has temporal validity:

```python
@dataclass
class Node:
    id: str
    type: NodeType
    data: dict
    valid_from: datetime    # When knowledge became valid
    valid_to: Optional[datetime]  # When invalidated (None = still valid)
    created_at: datetime
    session_id: str
```

### Graph Operations

```python
class MemoryGraph:
    def add_node(self, type: NodeType, data: dict) -> str:
        """Add a node to the graph."""

    def add_edge(self, source: str, target: str, relation: EdgeRelation) -> str:
        """Add an edge between nodes."""

    def get_node(self, node_id: str) -> Optional[Node]:
        """Get node by ID."""

    def get_neighbors(self, node_id: str, relation: Optional[EdgeRelation] = None) -> list[Node]:
        """Get connected nodes."""

    def snapshot_at(self, timestamp: datetime, node_type: Optional[NodeType] = None) -> list[Node]:
        """Get all valid nodes at a point in time."""

    def get_lineage(self, node_id: str, direction: str = "both") -> list[Node]:
        """Trace causal chain from a node."""

    def invalidate_node(self, node_id: str) -> None:
        """Soft-delete by setting valid_to."""
```

### Example Queries

```python
# Get all unresolved failures
failures = graph.get_nodes(
    type=NodeType.FAILURE,
    filter=lambda n: n.data.get("status") != "resolved"
)

# Find what addressed a failure
interventions = graph.get_neighbors(
    failure_id,
    relation=EdgeRelation.ADDRESSED_BY
)

# Get historical state at deployment
deployment_snapshot = graph.snapshot_at(
    deployment_time,
    node_type=NodeType.FAILURE
)

# Trace failure lineage
lineage = graph.get_lineage(failure_id, direction="ancestors")
```

---

## HITL Infrastructure

### Approval Flow Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                      APPROVAL ARCHITECTURE                       │
│                                                                  │
│  Agent Request                                                   │
│       │                                                          │
│       ▼                                                          │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │                  ApprovalHandler                         │    │
│  │                                                          │    │
│  │   ┌─────────────┐    ┌─────────────┐                    │    │
│  │   │    Risk     │───▶│   Approval  │                    │    │
│  │   │  Evaluator  │    │    Gate     │                    │    │
│  │   └─────────────┘    └─────────────┘                    │    │
│  │          │                  │                            │    │
│  │          ▼                  ▼                            │    │
│  │   ┌─────────────┐    ┌─────────────┐                    │    │
│  │   │  Risk Tier  │    │   Pending   │                    │    │
│  │   │ SAFE/REVIEW │    │   Requests  │                    │    │
│  │   │   /BLOCK    │    │   Queue     │                    │    │
│  │   └──────┬──────┘    └─────────────┘                    │    │
│  │          │                                               │    │
│  │          ▼                                               │    │
│  │   ┌─────────────────────────────────────────────────┐   │    │
│  │   │              UI Callback Router                  │   │    │
│  │   │                                                  │   │    │
│  │   │   Primary: TUI Modal                             │   │    │
│  │   │   Fallback: CLI Prompt                           │   │    │
│  │   │   Custom: User-registered callback               │   │    │
│  │   └─────────────────────────────────────────────────┘   │    │
│  └─────────────────────────────────────────────────────────┘    │
│                           │                                      │
│                           ▼                                      │
│                    Approved / Rejected                           │
│                           │                                      │
│                           ▼                                      │
│                    Agent Proceeds / Aborts                       │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### Risk Evaluation

```python
class RiskEvaluator:
    def evaluate(self, action: Action, mode: Mode) -> RiskAssessment:
        """Evaluate risk and return tier."""

        # Check hard blocks
        if action.type in BLOCKED_ACTIONS:
            return RiskAssessment(tier=RiskTier.BLOCK, ...)

        # Check mode-specific rules
        if mode == Mode.PRODUCTION:
            if action.type in REVIEW_REQUIRED_IN_PROD:
                return RiskAssessment(tier=RiskTier.REVIEW, ...)

        # Evaluate based on factors
        score = self._compute_risk_score(action, mode)
        tier = self._score_to_tier(score)

        return RiskAssessment(
            tier=tier,
            severity=action.predicted_severity,
            reasoning=self._explain_decision(action, tier),
            auto_approve=(tier == RiskTier.SAFE),
        )
```

### Approval Context

```python
@dataclass
class ApprovalContext:
    id: str
    action_type: ActionType
    action_description: str
    action_details: dict
    risk_tier: RiskTier
    severity: Severity
    estimated_cost_usd: Optional[float]
    is_reversible: bool
    rollback_plan: str
    requester_agent: str
    timeout_seconds: int
    status: ApprovalStatus
```

---

## Event System

### Event Bus Architecture

```python
class EventBus:
    """Pub/sub event system for component communication."""

    def __init__(self):
        self._subscribers: dict[str, list[Callable]] = {}
        self._history: list[Event] = []

    def subscribe(self, topic: str, handler: Callable) -> None:
        """Subscribe to a topic."""

    def publish(self, topic: str, payload: dict) -> None:
        """Publish an event to a topic."""

    def get_history(self, topic: Optional[str] = None) -> list[Event]:
        """Get event history."""
```

### Standard Topics

```python
class Topics:
    # Hypothesis events
    HYPOTHESIS_CREATED = "hypothesis.created"

    # Experiment events
    EXPERIMENT_DESIGNED = "experiment.designed"
    EXPERIMENT_STARTED = "experiment.started"
    EXPERIMENT_COMPLETED = "experiment.completed"

    # Failure events
    FAILURE_DISCOVERED = "failure.discovered"
    FAILURE_CLASSIFIED = "failure.classified"

    # Intervention events
    INTERVENTION_PROPOSED = "intervention.proposed"
    INTERVENTION_APPROVED = "intervention.approved"
    INTERVENTION_REJECTED = "intervention.rejected"
    INTERVENTION_DEPLOYED = "intervention.deployed"

    # Approval events
    APPROVAL_REQUESTED = "approval.requested"
    APPROVAL_GRANTED = "approval.granted"
    APPROVAL_DENIED = "approval.denied"

    # System events
    CYCLE_STARTED = "cycle.started"
    CYCLE_COMPLETED = "cycle.completed"
    MODE_CHANGED = "mode.changed"
```

### Event Payload

```python
@dataclass
class Event:
    id: str
    topic: str
    payload: dict
    timestamp: datetime
    source: str              # Publishing component
    correlation_id: Optional[str]  # For tracing
```

---

## Extension Points

### Custom Model Client

```python
from tinman.integrations.model_client import ModelClient

class MyCustomClient(ModelClient):
    """Custom LLM provider integration."""

    async def complete(self, messages: list[dict], **kwargs) -> str:
        """Implement completion logic."""
        response = await my_api.chat(messages)
        return response.content

    async def complete_structured(
        self,
        messages: list[dict],
        schema: dict,
        **kwargs
    ) -> dict:
        """Implement structured output."""
        response = await my_api.chat(messages, response_format=schema)
        return json.loads(response.content)
```

### Custom Agent

```python
from tinman.agents.base import BaseAgent, AgentContext, AgentResult

class MyCustomAgent(BaseAgent):
    """Custom research agent."""

    @property
    def agent_type(self) -> str:
        return "my_custom_agent"

    async def execute(self, context: AgentContext, **kwargs) -> AgentResult:
        # Access shared resources
        observations = self.graph.get_nodes(type=NodeType.FAILURE)

        # Use LLM reasoning
        if self.llm:
            analysis = await self.llm.reason(
                mode=ReasoningMode.ANALYZE,
                context={"observations": observations}
            )

        # Request approval if needed
        if self.approval_handler:
            approved = await self.approval_handler.request_approval(
                action_type=ActionType.CONFIG_CHANGE,
                description="My custom action",
                details={...}
            )
            if not approved:
                return AgentResult(success=False, data={}, errors=["Not approved"])

        # Publish events
        if self.event_bus:
            self.event_bus.publish("my_agent.completed", {...})

        return AgentResult(
            agent_type=self.agent_type,
            success=True,
            data={"result": ...},
            errors=[],
            warnings=[],
            metrics={},
            duration_ms=100
        )
```

### Custom Approval UI

```python
from tinman.core.approval_handler import ApprovalContext

async def my_approval_callback(context: ApprovalContext) -> bool:
    """Custom approval UI implementation."""

    # Display approval request (e.g., Slack, web UI, etc.)
    message = f"""
    Approval Required:
    Action: {context.action_description}
    Risk: {context.risk_tier.value}
    Cost: ${context.estimated_cost_usd:.2f}
    """

    # Wait for human decision
    decision = await my_ui.prompt_user(message)

    return decision == "approve"

# Register with Tinman
tinman.register_approval_ui(my_approval_callback)
```

### Custom Failure Classifier

```python
from tinman.taxonomy.classifiers import BaseClassifier

class MyDomainClassifier(BaseClassifier):
    """Domain-specific failure classification."""

    def classify(self, failure_data: dict) -> tuple[FailureClass, str, Severity]:
        """Classify a failure."""

        # Your classification logic
        if "my_domain_pattern" in failure_data.get("description", ""):
            return (
                FailureClass.REASONING,
                "MY_DOMAIN_SPECIFIC_SUBTYPE",
                Severity.S2
            )

        # Fallback to base classifier
        return super().classify(failure_data)
```

---

## Configuration

### Settings Hierarchy

```python
@dataclass
class Settings:
    mode: Mode
    database: DatabaseSettings
    models: ModelSettings
    research: ResearchSettings
    experiments: ExperimentSettings
    risk: RiskSettings
    approval: ApprovalSettings
    shadow: ShadowSettings
    logging: LoggingSettings
```

### Loading Priority

1. Defaults (in code)
2. Config file (`.tinman/config.yaml`)
3. Environment variables (`${VAR}` substitution)
4. CLI arguments
5. Programmatic overrides

```python
# Config file with env var substitution
models:
  providers:
    openai:
      api_key: ${OPENAI_API_KEY}  # From environment
```

---

## Performance Considerations

### Async Execution

All agent operations are async:

```python
# Agents can run concurrently where appropriate
results = await asyncio.gather(
    agent1.run(context),
    agent2.run(context),
)
```

### Database Pooling

Connection pooling for efficiency:

```python
database:
  url: postgresql://localhost/tinman
  pool_size: 10
  max_overflow: 20
```

### LLM Cost Control

Built-in cost tracking and limits:

```python
experiments:
  cost_limit_usd: 10.0  # Per cycle limit

# Tracked in results
result.metrics["llm_cost_usd"]
```

---

## Service Mode Architecture

### FastAPI Service

Tinman can run as an HTTP service for production deployments:

```
┌─────────────────────────────────────────────────────────────────┐
│                     TINMAN SERVICE MODE                          │
│                                                                  │
│  HTTP Clients                                                    │
│       │                                                          │
│       ▼                                                          │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │                    FastAPI App                           │    │
│  │                                                          │    │
│  │   /health          - Health checks                       │    │
│  │   /ready           - Kubernetes readiness                │    │
│  │   /live            - Kubernetes liveness                 │    │
│  │   /status          - Current Tinman state                │    │
│  │   /research/cycle  - Run research cycle                  │    │
│  │   /approvals/*     - Manage approvals                    │    │
│  │   /discuss         - Interactive discussion              │    │
│  │   /mode            - Mode management                     │    │
│  │   /metrics         - Prometheus metrics                  │    │
│  └─────────────────────────────────────────────────────────┘    │
│                           │                                      │
│                           ▼                                      │
│                    Tinman Orchestrator                           │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### Starting the Service

```bash
# CLI command
tinman serve --host 0.0.0.0 --port 8000

# Or directly with uvicorn
uvicorn tinman.service.app:app --host 0.0.0.0 --port 8000
```

---

## Cost Tracking

### Budget Enforcement Architecture

```python
from tinman.core.cost_tracker import CostTracker, BudgetConfig, BudgetPeriod

# Configure budget
config = BudgetConfig(
    limit_usd=100.0,           # Max spend
    period=BudgetPeriod.DAILY,  # Reset daily
    warn_threshold=0.8,         # Warn at 80%
    hard_limit=True,            # Block when exceeded
)

tracker = CostTracker(budget_config=config)

# Enforce before operations
tracker.enforce_budget(estimated_cost=5.0)

# Record actual costs
tracker.record_cost(
    amount_usd=4.50,
    source="llm_call",
    model="claude-3-opus",
    operation="research",
)
```

### Cost Categories

| Source | Description |
|--------|-------------|
| `llm_call` | LLM API calls |
| `research_cycle` | Full research cycle |
| `experiment` | Individual experiment |
| `tool_call` | External tool invocation |

---

## Metrics & Observability

### Prometheus Metrics

Tinman exposes comprehensive Prometheus metrics:

```python
from tinman.core.metrics import start_metrics_server, get_metrics

# Start metrics server
start_metrics_server(port=9090)
```

**Key Metrics:**

| Metric | Type | Description |
|--------|------|-------------|
| `tinman_research_cycles_total` | Counter | Total research cycles |
| `tinman_failures_discovered_total` | Counter | Failures by severity/class |
| `tinman_approval_decisions_total` | Counter | Approvals by decision/tier |
| `tinman_cost_usd_total` | Counter | Costs by source/model |
| `tinman_llm_requests_total` | Counter | LLM requests by model/status |
| `tinman_llm_latency_seconds` | Histogram | LLM request latency |
| `tinman_tool_executions_total` | Counter | Tool calls by status |
| `tinman_pending_approvals` | Gauge | Current pending approvals |
| `tinman_current_mode` | Gauge | Active operating mode |

---

## Trace Ingestion

### Supported Formats

Tinman can ingest traces from multiple observability systems:

```
┌─────────────────────────────────────────────────────────────────┐
│                     TRACE INGESTION                              │
│                                                                  │
│  ┌───────────┐  ┌───────────┐  ┌───────────┐  ┌───────────┐   │
│  │   OTLP    │  │  Datadog  │  │  X-Ray    │  │   JSON    │   │
│  │  Traces   │  │   APM     │  │  Traces   │  │  Generic  │   │
│  └─────┬─────┘  └─────┬─────┘  └─────┬─────┘  └─────┬─────┘   │
│        │              │              │              │          │
│        └──────────────┴──────────────┴──────────────┘          │
│                           │                                     │
│                           ▼                                     │
│                  ┌─────────────────┐                           │
│                  │  Auto-Detect    │                           │
│                  │  Registry       │                           │
│                  └────────┬────────┘                           │
│                           │                                     │
│                           ▼                                     │
│                  ┌─────────────────┐                           │
│                  │  Unified Trace  │                           │
│                  │  Model          │                           │
│                  └────────┬────────┘                           │
│                           │                                     │
│                           ▼                                     │
│                  Tinman Analysis                                │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### Usage

```python
from tinman.ingest import parse_traces, OTLPAdapter

# Auto-detect format
traces = parse_traces(raw_data)

# Or use specific adapter
adapter = OTLPAdapter()
traces = list(adapter.parse(otlp_data))

# Analyze traces
for trace in traces:
    for span in trace.error_spans:
        print(f"Error: {span.name} - {span.status_message}")
```

---

## Audit Trail

### Durable Audit Logging

All consequential actions are persisted:

```python
from tinman.db.audit import AuditLogger

audit = AuditLogger(session)

# Query activity
logs = audit.query(
    event_types=["approval_decision", "mode_transition"],
    since=datetime.now() - timedelta(hours=24),
)
```

**Audit Tables:**

| Table | Purpose |
|-------|---------|
| `audit_logs` | Immutable event log |
| `approval_decisions` | Human approval records |
| `mode_transitions` | Mode change history |
| `tool_executions` | Tool call records |

---

## Risk Policy

### Policy-Driven Risk Evaluation

Risk decisions are configurable via YAML:

```yaml
# risk_policy.yaml
base_matrix:
  lab:
    S0: safe
    S1: safe
    S2: review
    S3: review
    S4: block
  shadow:
    S0: safe
    S1: review
    S2: review
    S3: block
    S4: block
  production:
    S0: review
    S1: review
    S2: block
    S3: block
    S4: block

action_overrides:
  DEPLOY_INTERVENTION:
    production: block
  DESTRUCTIVE_TEST:
    shadow: block
    production: block
```

### Guarded Tool Execution

All tool calls go through the safety pipeline:

```python
from tinman.core.tools import guarded_call, ToolRegistry

@ToolRegistry.register(
    name="search",
    risk_level=ToolRiskLevel.LOW,
)
async def search_tool(query: str) -> list[str]:
    return await do_search(query)

# Execution is automatically guarded
result = await guarded_call(
    search_tool,
    action_type=ActionType.TOOL_CALL,
    description="Search for relevant documents",
    approval_handler=handler,
    mode=Mode.PRODUCTION,
    query="AI safety",
)
```

---

## Next Steps

- [AGENTS.md](AGENTS.md) - Detailed agent documentation
- [MEMORY.md](MEMORY.md) - Memory graph deep dive
- [HITL.md](HITL.md) - Approval system details
- [INTEGRATION.md](INTEGRATION.md) - Integration patterns
- [PRODUCTION.md](PRODUCTION.md) - Production deployment guide
