# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Tinman** (repo: `oliveskin/agent_tinman`) is an autonomous, embedded research operator that:
- Lives inside AI deployments to continuously probe model behavior
- Actively searches for failure modes and designs interventions
- Feeds insights back to both AI labs and product teams

This is NOT an eval harness or benchmark runner. It's an "always-on, field-embedded Research Engineer implemented as an agentic system."

## Repository

- **GitHub**: https://github.com/oliveskin/agent_tinman
- **License**: Apache 2.0

## Quick Start

```bash
# Install
pip install tinman

# Initialize in project
tinman init

# Generate failure hypotheses
tinman hypothesize

# Run experiments
tinman experiment --runs 10

# Generate report
tinman report --format markdown
```

## Package Structure

```
tinman/
├── __init__.py          # Main exports
├── agents/              # Research agents
│   ├── base.py          # BaseAgent, AgentContext, AgentResult
│   ├── hypothesis_engine.py
│   ├── experiment_architect.py
│   ├── experiment_executor.py
│   ├── failure_discovery.py
│   ├── intervention_engine.py
│   └── simulation_engine.py
├── cli/                 # Command-line interface
│   └── main.py          # Click-based CLI
├── config/              # Configuration
│   ├── modes.py         # LAB/SHADOW/PRODUCTION modes
│   └── settings.py      # Settings management
├── core/                # Core systems
│   ├── approval_gate.py # Human approval queue
│   ├── control_plane.py # Central control
│   ├── event_bus.py     # Pub/sub messaging
│   └── risk_evaluator.py # Risk assessment
├── db/                  # Database layer
│   ├── connection.py    # Session management
│   └── models.py        # SQLAlchemy ORM
├── integrations/        # External integrations
│   ├── anthropic_client.py
│   ├── model_client.py  # Abstract client
│   ├── openai_client.py
│   └── pipeline_adapter.py
├── memory/              # Research Memory Graph
│   ├── graph.py         # MemoryGraph API
│   ├── models.py        # Node, Edge dataclasses
│   └── repository.py    # PostgreSQL persistence
├── reporting/           # Report generation
│   ├── lab_reporter.py  # Research reports
│   └── ops_reporter.py  # Operational reports
├── taxonomy/            # Failure classification
│   ├── causal_linker.py # Root cause analysis
│   ├── classifiers.py   # FailureClassifier
│   └── failure_types.py # Taxonomy definitions
└── utils/               # Utilities
    ├── id_gen.py        # UUID generation
    ├── logging_setup.py # Structured logging
    └── time_utils.py    # Datetime helpers
```

## Operating Modes

Three modes with different capabilities:

| Mode | Purpose | Interventions |
|------|---------|---------------|
| LAB | Full research | Auto-deploy |
| SHADOW | Observation | None |
| PRODUCTION | Active protection | Approval required |

```python
from tinman import OperatingMode, AgentContext

context = AgentContext(mode=OperatingMode.LAB)
```

## Key Concepts

### Failure Taxonomy

Five primary classes with severity S0-S4:

| Class | Description |
|-------|-------------|
| REASONING | Spurious inference, goal drift |
| LONG_CONTEXT | Attention dilution, latent forgetting |
| TOOL_USE | Parameter injection, hallucinated calls |
| FEEDBACK_LOOP | Output amplification, memory poisoning |
| DEPLOYMENT | Latency collapse, resource exhaustion |

### Research Memory Graph

Temporal knowledge graph with:
- Nodes: hypotheses, experiments, failures, interventions
- Edges: causal relationships (CAUSED_BY, EVOLVED_INTO, etc.)
- Time-travel queries: `graph.snapshot_at(timestamp)`

### Risk Tiers

| Tier | Action | Approval |
|------|--------|----------|
| SAFE | Auto-deploy | No |
| REVIEW | Queue for review | Yes |
| BLOCK | Manual only | Required |

## Agent Pipeline

```
HypothesisEngine → ExperimentArchitect → ExperimentExecutor
                                              ↓
                                      FailureDiscovery
                                              ↓
                                   InterventionEngine
                                              ↓
                                    SimulationEngine
                                              ↓
                                      [Deployment]
```

## Python API

```python
import asyncio
from tinman import (
    HypothesisEngine,
    ExperimentArchitect,
    ExperimentExecutor,
    AgentContext,
    OperatingMode,
)

async def research():
    context = AgentContext(mode=OperatingMode.LAB)

    # Generate hypotheses
    engine = HypothesisEngine()
    hypotheses = await engine.run(context)

    # Design experiments
    architect = ExperimentArchitect()
    experiments = await architect.run(context, hypotheses=hypotheses.data["hypotheses"])

    return experiments

asyncio.run(research())
```

## Pipeline Integration

```python
from tinman import PipelineAdapter, OperatingMode

adapter = PipelineAdapter(mode=OperatingMode.SHADOW)

# In your pipeline
ctx = adapter.create_context(messages=messages)
ctx = await adapter.pre_request(ctx)

response = await your_model_call(...)

ctx.response = response
ctx = await adapter.post_request(ctx)
```

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Type check
mypy tinman

# Lint
ruff check .
```

## Design Principles

- **Simple over complex**: No multi-tenancy, HSM, or enterprise features
- **Temporal by default**: All graph nodes have valid_from/valid_to
- **Event-driven**: Agents communicate via event bus, not direct calls
- **Risk-aware**: Every action goes through risk evaluation
- **Observable**: Structured logging, Prometheus metrics support
