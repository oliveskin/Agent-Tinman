# Tinman

Forward-Deployed Research Agent for AI system failure discovery.

Tinman systematically discovers, classifies, and addresses failure modes in AI systems through automated hypothesis generation, experimentation, and intervention.

## Installation

```sh
pip install tinman
```

With model provider support:

```sh
pip install tinman[openai]    # OpenAI support
pip install tinman[anthropic] # Anthropic support
pip install tinman[all]       # All providers
```

## Quick Start

Initialize Tinman in your project:

```sh
tinman init
```

Generate failure hypotheses:

```sh
tinman hypothesize
```

Run experiments:

```sh
tinman experiment --runs 10
```

Generate a report:

```sh
tinman report --format markdown
```

## Operating Modes

Tinman has three operating modes:

- **LAB** - Full research mode with unrestricted experimentation
- **SHADOW** - Observes production traffic without intervention
- **PRODUCTION** - Active protection with human approval gates

Set mode via CLI or config:

```sh
tinman --mode shadow experiment
```

## Configuration

Create `.tinman/config.yaml`:

```yaml
mode: lab

database:
  url: postgresql://localhost/tinman

model:
  provider: openai
  model: gpt-4-turbo-preview
  temperature: 0.7

research:
  max_hypotheses_per_run: 10
  max_experiments_per_hypothesis: 3
  default_runs_per_experiment: 5
```

## Architecture

```
tinman/
├── agents/          # Autonomous research agents
│   ├── hypothesis_engine    # Generates failure hypotheses
│   ├── experiment_architect # Designs experiments
│   ├── experiment_executor  # Runs experiments
│   ├── failure_discovery    # Discovers and classifies failures
│   ├── intervention_engine  # Proposes fixes
│   └── simulation_engine    # Counterfactual replay
├── config/          # Configuration and operating modes
├── core/            # Control plane and event bus
├── db/              # Database models
├── integrations/    # Model clients (OpenAI, Anthropic)
├── memory/          # Research Memory Graph
├── reporting/       # Lab and ops reporters
└── taxonomy/        # Failure classification system
```

## Key Concepts

### Research Memory Graph

Tinman maintains a temporal knowledge graph tracking:

- Hypotheses and experiments
- Discovered failures with lineage
- Interventions and their effects
- Causal relationships

Query the graph at any point in time:

```python
from tinman.memory import MemoryGraph

graph = MemoryGraph(session)
failures_at_deployment = graph.snapshot_at(deployment_time)
```

### Failure Taxonomy

Five primary failure classes:

| Class | Description |
|-------|-------------|
| REASONING | Logical errors, goal drift |
| LONG_CONTEXT | Context window issues |
| TOOL_USE | Tool call failures |
| FEEDBACK_LOOP | Output amplification |
| DEPLOYMENT | Infrastructure failures |

Each with severity S0-S4 (S4 = critical).

### Risk Tiers

Interventions are risk-classified:

- **SAFE** - Auto-deployable
- **REVIEW** - Requires human approval
- **BLOCK** - Manual review only

## Python API

```python
import asyncio
from tinman.agents import HypothesisEngine, ExperimentArchitect
from tinman.agents.base import AgentContext
from tinman.config.modes import OperatingMode

async def research():
    context = AgentContext(mode=OperatingMode.LAB)

    # Generate hypotheses
    engine = HypothesisEngine()
    result = await engine.run(context)

    # Design experiments
    architect = ExperimentArchitect()
    experiments = await architect.run(
        context,
        hypotheses=result.data["hypotheses"]
    )

    return experiments

asyncio.run(research())
```

## Pipeline Integration

Hook Tinman into existing LLM pipelines:

```python
from tinman.integrations import PipelineAdapter
from tinman.config.modes import OperatingMode

adapter = PipelineAdapter(mode=OperatingMode.SHADOW)

# In your pipeline
ctx = adapter.create_context(messages=messages)
ctx = await adapter.pre_request(ctx)

response = await your_model_call(...)

ctx.response = response
ctx = await adapter.post_request(ctx)
```

## Contributing

Contributions welcome. See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## License

Apache 2.0
