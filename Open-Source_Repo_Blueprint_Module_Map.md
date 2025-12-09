* Top-level repo layout
* Python package structure (`fdra/`)
* What lives in each module + key interfaces / data shapes
* Where autonomy, risk-gating, HITL, and memory graph live
* Clear extension points for contributors

No step-by-step usage tutorial; this is architecture + implementation map.

---

## 1. Top-Level Repository Layout

```text
forward-deployed-research-agent/
  README.md
  LICENSE
  CONTRIBUTING.md
  CODE_OF_CONDUCT.md
  ROADMAP.md
  SECURITY.md
  GOVERNANCE.md

  pyproject.toml          # or setup.cfg / setup.py
  fdra/                   # main Python package
  cli/                    # CLI entry points
  configs/                # default configs & policies
  docs/                   # docs site / specs
  examples/               # worked examples
  tests/                  # test suite
  .github/
    workflows/            # CI/CD pipelines
```

### Key top-level files

* **README.md** – project pitch, quickstart, high-level diagram.
* **GOVERNANCE.md** – how decisions are made, safety rules, escalation.
* **SECURITY.md** – responsible disclosure, how to report issues.
* **ROADMAP.md** – planned features (aligns with LLD phases).

---

## 2. Core Python Package Layout (`fdra/`)

```text
fdra/
  __init__.py

  config/
    __init__.py
    settings.py           # global config loading
    modes.py              # LAB_AUTONOMOUS, SHADOW_AUTONOMOUS, etc.

  events/
    __init__.py
    bus.py                # event bus abstraction
    models.py             # core event types (pydantic)
    topics.py             # topic names, routing keys

  control/
    __init__.py
    control_plane.py      # global state machine
    risk_evaluator.py     # risk scoring logic
    action_registry.py    # central registry of action types

  agents/
    __init__.py
    base.py               # base Agent class
    behavioral_hypothesis.py
    experiment_architect.py
    live_executor.py
    failure_discovery.py
    intervention_engine.py
    simulation_engine.py

  memory/
    __init__.py
    graph.py              # research memory graph core
    models.py             # node/edge dataclasses
    storage/
      __init__.py
      sqlite_backend.py
      neo4j_backend.py    # optional
      in_memory_backend.py

  risk/
    __init__.py
    models.py             # risk object schema
    rules.py              # rule-based thresholds
    predictors.py         # learned models (later)

  governance/
    __init__.py
    human_interlock.py    # approval queue, multi-sig
    policies.py           # org-level policies
    audit_log.py          # append-only audit trail

  evals/
    __init__.py
    schema.py             # Experiment, Run, Result
    registry.py           # registered eval types
    long_context.py
    tool_use.py
    rag_behavior.py
    latency_cost.py
    safety_behavior.py

  integrations/
    __init__.py
    models/
      __init__.py
      openai_client.py
      anthropic_client.py
      openrouter_client.py
      local_llm_client.py
    tools/
      __init__.py
      http_tool.py
      db_tool.py
      retriever_tool.py
      file_tool.py
    pipelines/
      __init__.py
      generic_llm_pipeline.py   # “target system” interface
      langchain_adapter.py      # optional
      llamaindex_adapter.py     # optional

  reporting/
    __init__.py
    lab_reports.py        # lab-facing
    partner_reports.py    # ops-facing
    templates/
      lab_report.md.j2
      partner_brief.md.j2
      failure_card.md.j2

  storage/
    __init__.py
    db.py                  # relational store (Postgres/SQLite)
    models.py              # ORM models for runs, failures, etc.

  logging/
    __init__.py
    setup.py               # structured logging setup
    hooks.py               # log event hooks

  utils/
    __init__.py
    id_gen.py
    time.py
    hashing.py
    serialization.py
    config_helpers.py
```

---

## 3. Events & Control Plane – The Nervous System

### 3.1 `events/models.py` – Core Event Types

Use Pydantic models to standardize messages between agents:

```python
# fdra/events/models.py
from pydantic import BaseModel
from typing import Dict, Any, List, Literal

class HypothesisEvent(BaseModel):
    hypothesis_id: str
    target_surface: Literal["LONG_CONTEXT", "TOOL_CHAIN", "RAG", "LATENCY", "SAFETY"]
    expected_failure: str
    confidence: float
    test_priority: Literal["LOW", "MEDIUM", "HIGH"]

class ExperimentDefinitionEvent(BaseModel):
    experiment_id: str
    hypothesis_id: str
    mode: Literal["LAB", "SHADOW", "PROD_GATED"]
    stress_type: str
    metrics: List[str]
    constraints: Dict[str, Any]

class ExperimentRunEvent(BaseModel):
    run_id: str
    experiment_id: str
    raw_inputs: List[Dict[str, Any]]
    raw_outputs: List[Dict[str, Any]]
    traces: Dict[str, Any]

class FailureModeEvent(BaseModel):
    failure_id: str
    run_id: str
    primary_class: str
    secondary_class: str
    severity: str
    trigger_conditions: List[str]

class InterventionProposalEvent(BaseModel):
    intervention_id: str
    failure_id: str
    type: str
    expected_gain: Dict[str, float]
    expected_regressions: Dict[str, float]
    cost_impact: float
    latency_impact_ms: float
    requires_human: bool
```

### 3.2 `events/bus.py` – Event Bus Abstraction

Single abstraction so later you can swap in Kafka/Redis/etc.

```python
# fdra/events/bus.py
from typing import Callable, Type, Dict, List
from .models import BaseModel

class EventBus:
    def __init__(self):
        self._subscribers: Dict[str, List[Callable[[BaseModel], None]]] = {}

    def subscribe(self, topic: str, handler: Callable[[BaseModel], None]):
        self._subscribers.setdefault(topic, []).append(handler)

    def publish(self, topic: str, event: BaseModel):
        for handler in self._subscribers.get(topic, []):
            handler(event)
```

---

## 4. Agents – The Research Organism

All agents inherit from `BaseAgent` and talk via events.

### 4.1 `agents/base.py`

```python
# fdra/agents/base.py
from abc import ABC, abstractmethod
from fdra.events.bus import EventBus

class BaseAgent(ABC):
    def __init__(self, bus: EventBus):
        self.bus = bus

    @abstractmethod
    def start(self):
        """Subscribe to events / start loops."""
        ...
```

### 4.2 Behavioral Hypothesis Agent

`agents/behavioral_hypothesis.py`

* Subscribes to:

  * `NEW_FAILURE_DISCOVERED`
  * `MODEL_VERSION_CHANGED`
  * `WORKLOAD_SHIFT_DETECTED`
* Publishes:

  * `HYPOTHESIS_CREATED`

Core responsibilities:

* Scan Research Memory Graph
* Propose new hypotheses with confidence scores

---

### 4.3 Experiment Architect Agent

`agents/experiment_architect.py`

* Subscribes to:

  * `HYPOTHESIS_CREATED`
* Publishes:

  * `EXPERIMENT_DEFINITION_CREATED`

Responsibilities:

* Map hypothesis → concrete experiment definition
* Select:

  * Stress method (synthetic vs replay)
  * Metrics
  * Constraints based on `config.modes` & policies

---

### 4.4 Live Experiment Executor

`agents/live_executor.py`

* Subscribes to:

  * `EXPERIMENT_DEFINITION_CREATED`
* Publishes:

  * `EXPERIMENT_RUN_COMPLETED`

Responsibilities:

* Run against:

  * Shadow pipeline
  * Lab pipeline
* Use:

  * `integrations.pipelines.generic_llm_pipeline`
* Attach:

  * latency, token, tool traces

---

### 4.5 Failure Mode Discovery Engine

`agents/failure_discovery.py`

* Subscribes to:

  * `EXPERIMENT_RUN_COMPLETED`
* Publishes:

  * `FAILURE_MODE_DISCOVERED`

Responsibilities:

* Cluster outputs / traces
* Compare to Failure Mode Taxonomy
* Assign:

  * Class, severity, reproducibility
* Write to:

  * `memory.graph`

---

### 4.6 Intervention & Steering Engine

`agents/intervention_engine.py`

* Subscribes to:

  * `FAILURE_MODE_DISCOVERED`
* Publishes:

  * `INTERVENTION_PROPOSED`

Responsibilities:

* Propose fixes:

  * Prompt policies
  * Tool routing
  * Memory gating
  * Fine-tune datasets
* Call:

  * `risk_evaluator` to tag `requires_human`

---

### 4.7 Simulation Engine

`agents/simulation_engine.py`

* Subscribes to:

  * `INTERVENTION_PROPOSED`
* Publishes:

  * `SIMULATION_COMPLETED`
  * Possibly `INTERVENTION_READY_FOR_APPROVAL`

Responsibilities:

* Replay interventions against:

  * Historical failures
  * Edge synthetic sets
* Produce:

  * Pass rate
  * Risk shift
  * New failures introduced

---

## 5. Control Plane & Risk Layer

### 5.1 `control/modes.py`

Defines:

```python
LAB_AUTONOMOUS = "LAB_AUTONOMOUS"
SHADOW_AUTONOMOUS = "SHADOW_AUTONOMOUS"
PRODUCTION_GATED = "PRODUCTION_GATED"
FULL_AUTONOMOUS_OVERRIDE = "FULL_AUTONOMOUS_OVERRIDE"
```

### 5.2 `risk/models.py`

```python
from pydantic import BaseModel
from typing import Dict

class ActionRiskAssessment(BaseModel):
    action_id: str
    action_type: str
    severity_predicted: str
    cost_delta_est: float
    latency_delta_est_ms: int
    policy_conflict: bool
    requires_human: bool
    metadata: Dict[str, str] = {}
```

### 5.3 `control/risk_evaluator.py`

Pure function / class:

```python
def evaluate_action_risk(action) -> ActionRiskAssessment:
    # inspect type, severity, mode, policies
    ...
    return assessment
```

Agents call this before emitting “ready to deploy” actions.

---

## 6. Human Interlock & Governance

### 6.1 `governance/human_interlock.py`

* Exposes:

```python
class ApprovalStatus(str, Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"

class ApprovalRequest(BaseModel):
    approval_id: str
    intervention_id: str
    risk_summary: str
    impact_summary: str
    rollback_plan: str
    approvers: List[str]
    status: ApprovalStatus
```

* Provides:

  * `queue_approval_request()`
  * `mark_approved()`
  * `mark_rejected()`

### 6.2 `governance/policies.py`

YAML-driven policies, e.g.:

```yaml
S3_or_higher:
  requires_human: true
  required_approvals: 2
  roles: ["safety", "platform"]

prompt_mutation_prod:
  requires_human: true
  required_approvals: 1
  roles: ["ops"]

lab_mode:
  requires_human: false
```

---

## 7. Research Memory Graph

### 7.1 `memory/models.py`

Dataclasses for nodes/edges:

```python
from dataclasses import dataclass
from typing import Dict, Any, Literal, List

@dataclass
class ModelVersionNode:
    id: str
    version: str
    metadata: Dict[str, Any]

@dataclass
class ExperimentNode:
    id: str
    hypothesis_id: str
    config: Dict[str, Any]

@dataclass
class FailureModeNode:
    id: str
    primary_class: str
    secondary_class: str
    severity: str
    trigger_signature: List[str]

@dataclass
class InterventionNode:
    id: str
    type: str
    params: Dict[str, Any]

@dataclass
class Edge:
    src: str
    dst: str
    relation: str  # OBSERVED_IN, CAUSED_BY, MUTATED_BY, etc.
```

### 7.2 `memory/graph.py`

A backend-agnostic interface:

```python
class MemoryGraphBackend(ABC):
    @abstractmethod
    def add_node(self, node): ...
    @abstractmethod
    def add_edge(self, edge: Edge): ...
    @abstractmethod
    def get_neighbors(self, node_id: str, relation: str): ...


class MemoryGraph:
    def __init__(self, backend: MemoryGraphBackend):
        self.backend = backend

    def record_experiment_failure_intervention(...):
        # orchestrates node+edge creation
        ...
```

Backends in `memory/storage/`:

* `sqlite_backend.py` (default)
* `neo4j_backend.py` (optional, for graph nerds)
* `in_memory_backend.py` (tests)

---

## 8. Evals & Taxonomy

### 8.1 `evals/schema.py`

Defines basic schemas:

```python
class EvalDefinition(BaseModel):
    id: str
    name: str
    description: str
    metrics: List[str]
    generator_config: Dict[str, Any]
```

### 8.2 `evals/long_context.py`, `evals/tool_use.py`, etc.

Each file exports:

* `build_eval_definition()`
* `run_eval()` (can be used standalone in tests)
* `classify_failures()` for that eval type

---

## 9. Integrations

### 9.1 `integrations/models/*.py`

Each model client implements a common interface:

```python
class BaseModelClient(ABC):
    @abstractmethod
    async def generate(self, prompt: str, **kwargs) -> str: ...
```

Examples:

* `OpenAIModelClient(BaseModelClient)`
* `AnthropicModelClient`
* `LocalLLMClient` (via vLLM / llama.cpp proxy)

### 9.2 Pipelines

`integrations/pipelines/generic_llm_pipeline.py` defines an abstraction for “the deployed system” FDRA is probing:

* Input:

  * `user_input`, `context`, `tools`, etc.
* Output:

  * model output
  * tool traces
  * latency
  * tokens

FDRA doesn’t care whether underneath it’s LangChain, a bespoke microservice, or a SaaS product — it just calls this interface.

---

## 10. Reporting

### 10.1 `reporting/lab_reports.py`

Given:

* Memory graph slice
* Recent experiments
* Failure modes

Produces:

* Markdown / JSON summaries for labs.

### 10.2 `reporting/partner_reports.py`

Given:

* Same data
* Partner policies

Produces:

* “Safe envelope” docs
* “Known limitations” cards
* Suggested deployment configs

Templates in `templates/` are Jinja.

---

## 11. CLI and Examples

### 11.1 `cli/fdra_cli.py`

Entrypoint:

```bash
fdra init   # create config skeleton
fdra run    # start agents, event bus, control plane
fdra status # show running experiments & failures
fdra report # generate reports
```

CLI uses `fdra.config.settings` to load mode (`LAB_AUTONOMOUS`, etc.).

### 11.2 `examples/`

* `examples/legal_summarization_shadow/`

  * `config.yml`
  * `pipeline_stub.py`
* `examples/tool_use_agent/`
* `examples/rag_qa/`

Each shows:

* How to plug FDRA into a target system
* How to run full autonomous research in lab/shadow mode

---

## 12. Tests & CI

* `tests/agents/` – unit tests for each agent.
* `tests/memory/` – graph behaviors, lineage, rollback chains.
* `tests/integrations/` – fake model/pipeline clients.
* `tests/e2e/` – one full loop from hypothesis → experiment → failure → intervention → simulation → approval.

CI (`.github/workflows/ci.yml`):

* Lint (ruff/black)
* Types (mypy/pyright)
* Tests (pytest)
* Security scan (bandit / pip-audit)

---

## 13. Contributor Extension Points

Very explicit, so OSS folks know where to plug in:

1. **New Eval Types** → `fdra/evals/`

   * Add a new `*.py`
   * Register in `evals/registry.py`

2. **New Failure Detectors / Taxonomy Extensions**

   * Add classifiers to `failure_discovery.py`
   * Extend `FailureModeNode` / taxonomy enums

3. **New Model Integrations**

   * Implement `BaseModelClient` under `integrations/models/`
   * Add config mapping

4. **New Pipelines / Framework Adapters**

   * `integrations/pipelines/*.py`
   * Implement the “target system” interface

5. **New Risk Rules**

   * Add to `risk/rules.py`
   * Map from policies.yml

6. **New Memory Backends**

   * Implement `MemoryGraphBackend` in `memory/storage/`

---


