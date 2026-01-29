<p align="center">
  <img src="assets/tinman.png" alt="Tinman" width="400">
</p>

<h1 align="center">Tinman</h1>

<p align="center">
  <strong>A Forward-Deployed Research Agent for Continuous AI Reliability Discovery</strong>
</p>

<p align="center">
  <a href="#installation">Installation</a> •
  <a href="#quick-start">Quick Start</a> •
  <a href="https://oliveskin.github.io/Agent-Tinman/">Documentation</a> •
  <a href="#contributing">Contributing</a>
</p>

---

Tinman is not a testing tool. It's an autonomous research agent that continuously explores your AI system's behavior to discover failure modes you haven't imagined yet.

While traditional approaches wait for failures to happen, Tinman proactively generates hypotheses about what *could* fail, designs experiments to test them, and proposes interventions—all with human oversight at critical decision points.

---

## Why Tinman?

**The problem:** Every team deploying LLMs faces the same question: *"What don't we know about how this system can fail?"*

Most tools help you monitor what you've already anticipated. Tinman helps you discover what you haven't.

**What makes it different:**

| Traditional Approach | Tinman |
|---------------------|--------|
| Reactive—triggered after incidents | Proactive—always exploring |
| Tests known failure patterns | Generates novel hypotheses |
| Output: pass/fail results | Output: understanding |
| Goal: verify correctness | Goal: expand knowledge |
| Stops when tests pass | Never stops—research is ongoing |

---

## Core Capabilities

### Hypothesis-Driven Research
Tinman generates testable hypotheses about potential failure modes based on your system's architecture, observed behavior, and a comprehensive failure taxonomy.

### Controlled Experimentation
Each hypothesis is tested through carefully designed experiments with configurable parameters, cost controls, and reproducibility tracking.

### Failure Classification
Discovered failures are classified using a structured taxonomy covering reasoning errors, context handling, tool use, feedback loops, and deployment issues—each with severity ratings (S0-S4).

### Intervention Design
For each failure, Tinman proposes concrete interventions: prompt mutations, guardrails, tool policy changes, or architectural recommendations.

### Simulation & Validation
Before deployment, interventions are validated through counterfactual replay—replaying historical traces with the proposed fix applied.

### Human-in-the-Loop Oversight
Risk-tiered approval gates ensure humans remain in control of consequential decisions while allowing safe actions to proceed autonomously.

---

## Installation

```bash
pip install AgentTinman
```

With specific model provider support:

```bash
pip install AgentTinman[openai]     # OpenAI
pip install AgentTinman[anthropic]  # Anthropic
pip install AgentTinman[all]        # All providers
```

### Development Setup

```bash
# Clone and install in development mode
git clone https://github.com/oliveskin/agent_tinman.git
cd agent_tinman
pip install -e ".[dev]"

# Run tests
pytest

# Run tests with coverage
pytest --cov=tinman

# Type checking
mypy tinman

# Linting
ruff check tinman
```

### Requirements
- Python 3.10+
- PostgreSQL (for persistent memory graph) or SQLite for testing
- An LLM provider (see supported models below)

### Supported Model Providers

| Provider | Cost | Best For |
|----------|------|----------|
| **Ollama** | Free (local) | Privacy, offline, unlimited |
| **Groq** | Free tier | Speed, high volume |
| **OpenRouter** | Many free models | Variety, DeepSeek, Qwen |
| **Together** | $25 free credits | Quality open models |
| **OpenAI** | Paid | GPT-4 |
| **Anthropic** | Paid | Claude |

---

## Quick Start

### 1. Initialize

```bash
tinman init
```

This creates `.tinman/config.yaml` with sensible defaults (SQLite by default).

If you are using PostgreSQL, initialize the database:

```bash
tinman db init
```

### 2. Configure Your Model

Edit `.tinman/config.yaml`:

```yaml
mode: lab

models:
  default: openai
  providers:
    openai:
      api_key: ${OPENAI_API_KEY}
      model: gpt-4-turbo-preview
```

### Environment Variables (where to put keys)

Tinman expects provider keys as **environment variables**. The config stores **references** to those variables:

```yaml
api_key: ${OPENAI_API_KEY}
```

Set them in your shell (examples):

```bash
export OPENAI_API_KEY="..."
export ANTHROPIC_API_KEY="..."
export GEMINI_API_KEY="..."
```

**Recommended:** copy the template `.env.example` to `.env` in your project root and fill in the keys:

```bash
cp .env.example .env
```

For demo scripts (GitHub / Hugging Face / Replicate / fal), set:

```bash
export GITHUB_TOKEN="..."
export HUGGINGFACE_API_KEY="..."
export REPLICATE_API_TOKEN="..."
export FAL_API_KEY="..."
```

You can add more providers to `.tinman/config.yaml` by adding a new entry under `models.providers`
and pointing it to an env var. Example for Groq:

```yaml
models:
  providers:
    groq:
      api_key: ${GROQ_API_KEY}
      model: llama3-70b-8192
```

### 3. Run a Research Cycle

```bash
tinman research --focus "tool use failures"
```

Or use the interactive TUI:

```bash
python -m tinman.cli.main tui
```

Windows convenience launchers (optional):

```powershell
.\tinman.bat tui
.\tinman.ps1 tui
```

### 3a. Run Demos (optional)

```bash
# Validate env vars, then run a demo
python -m tinman.demo.env_check all
python -m tinman.demo.runner github -- --repo moltbot/moltbot
```

Force a demo failure (useful for reports in sparse repos):

```bash
python -m tinman.demo.github_demo --repo moltbot/moltbot --inject-failure
```

The TUI also includes a **Demos** tab where you can select a provider, edit args,
and run the demo directly.

### 4. Review Findings

```bash
tinman report --format markdown
```

For a concise demo report:

```bash
tinman report --format demo
```

Exclude synthetic demo failures from reports:

```bash
tinman report --format markdown --exclude-demo-failures
```

Reset the local SQLite demo database:

```bash
tinman demo-reset-db
```

---

## Operating Modes

Tinman operates in three modes, each with different safety boundaries:

| Mode | Purpose | Approval Gates | Destructive Tests |
|------|---------|----------------|-------------------|
| **LAB** | Unrestricted research | Auto-approve most | Allowed |
| **SHADOW** | Observe production traffic | Review S3+ severity | Read-only |
| **PRODUCTION** | Active protection | Human approval required | Blocked |

**Transition rules:**
- LAB → SHADOW → PRODUCTION (progressive rollout)
- PRODUCTION → SHADOW (regression fallback)
- Cannot skip modes (LAB → PRODUCTION blocked)

See [docs/MODES.md](docs/MODES.md) for detailed behavior matrix.

---

## The Research Cycle

```
┌─────────────────────────────────────────────────────────────────┐
│                     RESEARCH CYCLE                               │
│                                                                  │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐      │
│  │  Hypothesis  │───▶│  Experiment  │───▶│  Experiment  │      │
│  │   Engine     │    │  Architect   │    │  Executor    │      │
│  └──────────────┘    └──────────────┘    └──────┬───────┘      │
│         │                                        │               │
│         │            ┌──────────────┐           │               │
│         │            │   Failure    │◀──────────┘               │
│         │            │  Discovery   │                           │
│         │            └──────┬───────┘                           │
│         │                   │                                    │
│         │            ┌──────▼───────┐    ┌──────────────┐      │
│         │            │ Intervention │───▶│  Simulation  │      │
│         │            │   Engine     │    │   Engine     │      │
│         │            └──────────────┘    └──────┬───────┘      │
│         │                                        │               │
│         └────────────── Learning ◀───────────────┘               │
│                     (Memory Graph)                               │
└─────────────────────────────────────────────────────────────────┘
```

Each cycle:
1. **Generate hypotheses** about potential failures
2. **Design experiments** to test each hypothesis
3. **Execute experiments** with approval gates
4. **Discover and classify** failures found
5. **Design interventions** to address failures
6. **Simulate fixes** via counterfactual replay
7. **Learn** from results for future cycles

---

## Failure Taxonomy

Tinman classifies failures into five primary classes:

| Class | Description | Example |
|-------|-------------|---------|
| **REASONING** | Logical errors, goal drift, hallucination | Model contradicts itself mid-response |
| **LONG_CONTEXT** | Context window issues, attention dilution | Forgets instructions from early in conversation |
| **TOOL_USE** | Tool call failures, parameter errors | Calls API with invalid arguments |
| **FEEDBACK_LOOP** | Output amplification, error cascades | Retry loop amplifies initial mistake |
| **DEPLOYMENT** | Infrastructure, latency, resource issues | Timeout under load causes partial response |

Each failure is assigned a severity:

| Severity | Impact | Example |
|----------|--------|---------|
| **S0** | Benign | Minor formatting issue |
| **S1** | UX degradation | Slightly verbose response |
| **S2** | Business risk | Incorrect but plausible answer |
| **S3** | Serious risk | Leaks sensitive information |
| **S4** | Critical | Executes harmful action |

See [docs/TAXONOMY.md](docs/TAXONOMY.md) for the complete classification guide.

---

## Human-in-the-Loop Approval

Tinman uses risk-tiered approval to balance autonomy with safety:

```
Action Request
      │
      ▼
┌─────────────┐
│    Risk     │
│  Evaluator  │
└──────┬──────┘
       │
   ┌───┴───┐
   │       │
   ▼       ▼
 SAFE    REVIEW ───▶ Human Decision ───▶ Approved/Rejected
   │       │
   │       ▼
   │     BLOCK ───▶ Rejected (always)
   │
   ▼
Auto-Approved
```

**Risk Tiers:**
- **SAFE**: Low-risk actions proceed automatically
- **REVIEW**: Medium-risk actions require human approval
- **BLOCK**: High-risk actions are always rejected

Approval UI options:
- Interactive TUI (default)
- CLI prompts (fallback)
- Custom callbacks (for integration)

See [docs/HITL.md](docs/HITL.md) for approval flow details.

---

## Python API

### Basic Usage

```python
import asyncio
from tinman import create_tinman
from tinman.config.modes import Mode

async def main():
    # Create and initialize Tinman
    tinman = await create_tinman(
        mode=Mode.LAB,
        db_url="postgresql://localhost/tinman"
    )

    # Run a research cycle
    results = await tinman.research_cycle(
        focus="reasoning failures in multi-step tasks",
        max_hypotheses=5,
        max_experiments=3
    )

    # Access findings
    print(f"Hypotheses tested: {len(results.hypotheses)}")
    print(f"Failures discovered: {len(results.failures)}")
    print(f"Interventions proposed: {len(results.interventions)}")

    # Generate report
    report = await tinman.generate_report(format="markdown")
    print(report)

    # Interactive discussion
    answer = await tinman.discuss("What's the most critical failure found?")
    print(answer)

    await tinman.close()

asyncio.run(main())
```

### Pipeline Integration

```python
from tinman.integrations import PipelineAdapter
from tinman.config.modes import Mode

# Create adapter for your existing pipeline
adapter = PipelineAdapter(mode=Mode.SHADOW)

# Wrap your LLM calls
async def monitored_llm_call(messages):
    ctx = adapter.create_context(messages=messages)
    ctx = await adapter.pre_request(ctx)

    response = await your_existing_llm_call(messages)

    ctx.response = response
    ctx = await adapter.post_request(ctx)

    # Tinman now tracks this interaction
    return response
```

See [docs/INTEGRATION.md](docs/INTEGRATION.md) for advanced integration patterns.

---

## Configuration Reference

```yaml
# .tinman/config.yaml

# Operating mode: lab, shadow, or production
mode: lab

# Database configuration
database:
  url: sqlite:///tinman.db  # Default (no setup required)
  pool_size: 10

# Model providers
models:
  default: openai
  providers:
    openai:
      api_key: ${OPENAI_API_KEY}
      model: gpt-4-turbo-preview
      temperature: 0.7
    anthropic:
      api_key: ${ANTHROPIC_API_KEY}
      model: claude-3-opus-20240229
    # Set your default provider above and choose a model here.

# Research parameters
research:
  max_hypotheses_per_run: 10
  max_experiments_per_hypothesis: 3
  default_runs_per_experiment: 5

# Experiment controls
experiments:
  max_parallel: 5
  default_timeout_seconds: 300
  cost_limit_usd: 10.0

# Risk evaluation
risk:
  detailed_mode: false
  auto_approve_safe: true
  block_on_destructive: true

# Approval settings
approval:
  mode: interactive  # interactive, async, auto_approve, auto_reject
  auto_approve_in_lab: true
  timeout_seconds: 300
```

See [docs/CONFIGURATION.md](docs/CONFIGURATION.md) for all options.

---

## Architecture

```
tinman/
├── agents/              # Autonomous research agents
│   ├── base.py          # BaseAgent abstract class
│   ├── hypothesis_engine.py
│   ├── experiment_architect.py
│   ├── experiment_executor.py
│   ├── failure_discovery.py
│   ├── intervention_engine.py
│   └── simulation_engine.py
├── config/              # Configuration and operating modes
│   ├── modes.py         # LAB/SHADOW/PRODUCTION
│   └── settings.py      # Settings dataclasses
├── core/                # Infrastructure
│   ├── approval_gate.py
│   ├── approval_handler.py
│   ├── control_plane.py
│   ├── event_bus.py
│   ├── risk_evaluator.py
│   ├── tools.py          # Guarded tool execution
│   ├── risk_policy.py    # Policy-driven risk matrix
│   ├── cost_tracker.py   # Budget enforcement
│   └── metrics.py        # Prometheus metrics
├── db/                  # Persistence
│   ├── connection.py
│   ├── models.py
│   └── audit.py          # Durable audit trail
├── ingest/              # Trace ingestion
│   ├── otlp.py           # OpenTelemetry adapter
│   ├── datadog.py        # Datadog APM adapter
│   └── xray.py           # AWS X-Ray adapter
├── service/             # HTTP API
│   ├── app.py            # FastAPI application
│   └── models.py         # Request/response models
├── integrations/        # External integrations
│   ├── model_client.py
│   ├── openai_client.py
│   ├── anthropic_client.py
│   └── pipeline_adapter.py
├── memory/              # Knowledge graph
│   ├── graph.py
│   ├── models.py
│   └── repository.py
├── reasoning/           # LLM reasoning
│   ├── llm_backbone.py
│   ├── adaptive_memory.py
│   ├── insight_synthesizer.py
│   └── prompts.py
├── reporting/           # Partner-facing reports
│   ├── executive.py      # Executive summary reports
│   ├── technical.py      # Technical analysis reports
│   ├── compliance.py     # Compliance/audit reports
│   └── export.py         # Multi-format export
├── taxonomy/            # Failure classification
│   ├── failure_types.py
│   ├── classifiers.py
│   └── causal_linker.py
├── tui/                 # Terminal UI
│   ├── app.py
│   └── styles.tcss
└── tinman.py            # Main orchestrator
```

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for component details and data flow.

---

## Documentation

| Document | Description |
|----------|-------------|
| [QUICKSTART.md](docs/QUICKSTART.md) | Get running in 5 minutes |
| [CONCEPTS.md](docs/CONCEPTS.md) | Core mental model and abstractions |
| [ARCHITECTURE.md](docs/ARCHITECTURE.md) | System design and component interaction |
| [TAXONOMY.md](docs/TAXONOMY.md) | Complete failure classification guide |
| [MODES.md](docs/MODES.md) | Operating mode behavior matrix |
| [HITL.md](docs/HITL.md) | Human-in-the-loop approval system |
| [AGENTS.md](docs/AGENTS.md) | Individual agent documentation |
| [MEMORY.md](docs/MEMORY.md) | Memory graph and temporal queries |
| [CONFIGURATION.md](docs/CONFIGURATION.md) | All configuration options |
| [INTEGRATION.md](docs/INTEGRATION.md) | Pipeline integration patterns |
| [PRODUCTION.md](docs/PRODUCTION.md) | Production deployment guide |
| [CONTRIBUTING.md](CONTRIBUTING.md) | Contribution guidelines |

Live docs: https://oliveskin.github.io/Agent-Tinman/

---

## Use Cases

### Research Lab
Run Tinman in LAB mode against development deployments to discover failures before they reach production.

### Shadow Monitoring
Deploy in SHADOW mode alongside production to observe real traffic patterns and surface emergent failure modes.

### Production Protection
Run in PRODUCTION mode with human approval gates to actively protect against discovered failure patterns.

### Compliance & Audit
Use the memory graph to demonstrate due diligence: what failures were discovered, what interventions were applied, and what the outcomes were.

---

## Philosophy

Tinman embodies a **research methodology**, not just a tool:

1. **Systematic curiosity** - Continuously ask "what could go wrong?" rather than "does this work?"

2. **Hypothesis-driven** - Every test has a reason. No random fuzzing.

3. **Human oversight** - Autonomy where safe, human judgment where it matters.

4. **Temporal knowledge** - Not just "what failed" but "what did we know, when?"

5. **Continuous learning** - Each cycle informs the next. Knowledge compounds.

---

## Contributing

We welcome contributions. See [CONTRIBUTING.md](CONTRIBUTING.md) for:
- Development setup
- Code style (ruff, mypy)
- Testing requirements
- PR process

---

## License

Apache 2.0 - See [LICENSE](LICENSE)

---

## Acknowledgments

Tinman is a public good, built for the community. Not monetized, not proprietary—just a crystallized methodology for systematic AI reliability research.
