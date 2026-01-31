<p align="center">
  <img src="assets/tinman.png" alt="Tinman" width="300">
</p>

<h1 align="center">Agent Tinman</h1>

<p align="center">
  <strong>Forward-Deployed Research Agent for Continuous AI Reliability Discovery</strong>
</p>

<p align="center">
  <a href="https://pypi.org/project/AgentTinman/"><img src="https://img.shields.io/pypi/v/AgentTinman?color=d97706&label=pypi" alt="PyPI"></a>
  <a href="https://pypi.org/project/AgentTinman/"><img src="https://img.shields.io/pypi/pyversions/AgentTinman?color=d97706" alt="Python"></a>
  <a href="https://github.com/oliveskin/Agent-Tinman/blob/main/LICENSE"><img src="https://img.shields.io/badge/license-Apache%202.0-4c1" alt="License"></a>
  <a href="https://oliveskin.github.io/Agent-Tinman/"><img src="https://img.shields.io/badge/docs-oliveskin.github.io-4c1" alt="Docs"></a>
</p>

<p align="center">
  <a href="#quick-start">Quick Start</a>&nbsp;&nbsp;•&nbsp;&nbsp;
  <a href="#the-research-cycle">How It Works</a>&nbsp;&nbsp;•&nbsp;&nbsp;
  <a href="#python-api">API</a>&nbsp;&nbsp;•&nbsp;&nbsp;
  <a href="https://oliveskin.github.io/Agent-Tinman/">Documentation</a>
</p>

<br>

---

<br>

> **Tinman is not a testing tool.** It's an autonomous research agent that continuously explores your AI system's behavior to discover failure modes you haven't imagined yet.

While traditional approaches wait for failures to happen, Tinman proactively generates hypotheses about what *could* fail, designs experiments to test them, and proposes interventions—all with human oversight at critical decision points.

<br>

## Why Tinman?

**The problem:** Every team deploying LLMs faces the same question: *"What don't we know about how this system can fail?"*

Most tools help you monitor what you've already anticipated. Tinman helps you discover what you haven't.

<table>
<tr>
<td width="50%" valign="top">

### Traditional Approach

```diff
- Reactive—triggered after incidents
- Tests known failure patterns
- Output: pass/fail results
- Goal: verify correctness
- Stops when tests pass
```

</td>
<td width="50%" valign="top">

### Tinman

```diff
+ Proactive—always exploring
+ Generates novel hypotheses
+ Output: understanding
+ Goal: expand knowledge
+ Never stops—research is ongoing
```

</td>
</tr>
</table>

<br>

## Core Capabilities

| Capability | Description |
|:-----------|:------------|
| **Hypothesis-Driven Research** | Generates testable hypotheses about potential failure modes based on system architecture and observed behavior |
| **Controlled Experimentation** | Tests each hypothesis with configurable parameters, cost controls, and reproducibility tracking |
| **Failure Classification** | Classifies failures using a structured taxonomy with severity ratings (S0-S4) |
| **Intervention Design** | Proposes concrete fixes: prompt mutations, guardrails, tool policy changes, architectural recommendations |
| **Simulation & Validation** | Validates interventions through counterfactual replay before deployment |
| **Human-in-the-Loop** | Risk-tiered approval gates ensure humans control consequential decisions |

<br>

## Quick Start

### Installation

```bash
pip install AgentTinman
```

With specific model provider support:

```bash
pip install AgentTinman[openai]     # OpenAI
pip install AgentTinman[anthropic]  # Anthropic
pip install AgentTinman[all]        # All providers
```

### Initialize & Run

```bash
# Initialize configuration
tinman init

# Launch the interactive TUI
tinman tui

# Or run a research cycle directly
tinman research --focus "tool use failures"

# Generate a report
tinman report --format markdown
```

### Configure Your Model

Edit `.tinman/config.yaml`:

```yaml
mode: lab

models:
  default: openai
  providers:
    openai:
      api_key: ${OPENAI_API_KEY}
      model: gpt-4-turbo-preview
    groq:
      api_key: ${GROQ_API_KEY}
      model: llama3-70b-8192
```

Set API keys as environment variables:

```bash
export OPENAI_API_KEY="..."
export ANTHROPIC_API_KEY="..."
export GROQ_API_KEY="..."
```

### Supported Providers

| Provider | Cost | Best For |
|:---------|:-----|:---------|
| **Ollama** | Free (local) | Privacy, offline, unlimited experimentation |
| **Groq** | Free tier | Speed, high volume |
| **OpenRouter** | Many free models | Variety—DeepSeek, Qwen, Llama, Mistral |
| **Together** | $25 free credits | Quality open models |
| **OpenAI** | Paid | GPT-4 |
| **Anthropic** | Paid | Claude |

<br>

## The Research Cycle

```
┌─────────────────────────────────────────────────────────────────────┐
│                         RESEARCH CYCLE                              │
│                                                                     │
│   ┌────────────┐    ┌────────────┐    ┌────────────┐               │
│   │ Hypothesis │───▶│ Experiment │───▶│  Failure   │               │
│   │   Engine   │    │  Executor  │    │ Discovery  │               │
│   └────────────┘    └────────────┘    └─────┬──────┘               │
│         ▲                                   │                       │
│         │           ┌────────────┐    ┌─────▼──────┐               │
│         │           │ Simulation │◀───│Intervention│               │
│         │           │   Engine   │    │   Engine   │               │
│         │           └─────┬──────┘    └────────────┘               │
│         │                 │                                         │
│         └─────── Learning ◀┘                                        │
│                (Memory Graph)                                       │
└─────────────────────────────────────────────────────────────────────┘
```

**Each cycle:**

1. **Generate hypotheses** about potential failures
2. **Design experiments** to test each hypothesis
3. **Execute experiments** with approval gates
4. **Discover and classify** failures found
5. **Design interventions** to address failures
6. **Simulate fixes** via counterfactual replay
7. **Learn** from results for future cycles

<br>

## Operating Modes

Tinman operates in three modes with different safety boundaries:

| Mode | Purpose | Approval Gates | Destructive Tests |
|:-----|:--------|:---------------|:------------------|
| **LAB** | Unrestricted research | Auto-approve most | Allowed |
| **SHADOW** | Observe production traffic | Review S3+ severity | Read-only |
| **PRODUCTION** | Active protection | Human approval required | Blocked |

**Transition rules:**
- LAB → SHADOW → PRODUCTION (progressive rollout)
- PRODUCTION → SHADOW (regression fallback)
- Cannot skip modes (LAB → PRODUCTION blocked)

<br>

## Failure Taxonomy

Tinman classifies failures into five primary classes:

| Class | Description | Example |
|:------|:------------|:--------|
| **REASONING** | Logical errors, goal drift, hallucination | Model contradicts itself mid-response |
| **LONG_CONTEXT** | Context window issues, attention dilution | Forgets instructions from early in conversation |
| **TOOL_USE** | Tool call failures, parameter errors, exfil | Calls API with invalid arguments |
| **FEEDBACK_LOOP** | Output amplification, error cascades | Retry loop amplifies initial mistake |
| **DEPLOYMENT** | Infrastructure, latency, resource issues | Timeout under load causes partial response |

**Severity levels:**

| Level | Impact | Action |
|:------|:-------|:-------|
| **S0** | Benign | Monitor |
| **S1** | UX degradation | Review |
| **S2** | Business risk | Investigate |
| **S3** | Serious risk | Mitigate |
| **S4** | Critical | Immediate action |

<br>

## Human-in-the-Loop Approval

Risk-tiered approval balances autonomy with safety:

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
   ▼
Auto-Approved
```

**Risk Tiers:**
- **SAFE**: Low-risk actions proceed automatically
- **REVIEW**: Medium-risk actions require human approval
- **BLOCK**: High-risk actions are always rejected

<br>

## Python API

### Basic Usage

```python
import asyncio
from tinman import create_tinman
from tinman.config.modes import Mode

async def main():
    tinman = await create_tinman(
        mode=Mode.LAB,
        db_url="sqlite:///tinman.db"
    )

    results = await tinman.research_cycle(
        focus="reasoning failures in multi-step tasks",
        max_hypotheses=5,
        max_experiments=3
    )

    print(f"Hypotheses tested: {len(results.hypotheses)}")
    print(f"Failures discovered: {len(results.failures)}")
    print(f"Interventions proposed: {len(results.interventions)}")

    report = await tinman.generate_report(format="markdown")
    print(report)

    await tinman.close()

asyncio.run(main())
```

### Pipeline Integration

```python
from tinman.integrations import PipelineAdapter
from tinman.config.modes import Mode

adapter = PipelineAdapter(mode=Mode.SHADOW)

async def monitored_llm_call(messages):
    ctx = adapter.create_context(messages=messages)
    ctx = await adapter.pre_request(ctx)

    response = await your_existing_llm_call(messages)

    ctx.response = response
    ctx = await adapter.post_request(ctx)
    return response
```

### Real-Time Gateway Monitoring

Connect to AI gateway WebSockets for instant event analysis:

```python
from tinman.integrations.gateway_plugin import GatewayMonitor, ConsoleAlerter, FileAlerter

monitor = GatewayMonitor(your_adapter)
monitor.add_alerter(ConsoleAlerter())
monitor.add_alerter(FileAlerter("~/tinman-findings.md"))
await monitor.start()
```

**Platform adapters:**
- [**OpenClaw**](https://github.com/oliveskin/tinman-openclaw-eval) — Security eval harness + gateway adapter

<br>

## Configuration Reference

```yaml
# .tinman/config.yaml

mode: lab  # lab, shadow, or production

database:
  url: sqlite:///tinman.db
  pool_size: 10

models:
  default: openai
  providers:
    openai:
      api_key: ${OPENAI_API_KEY}
      model: gpt-4-turbo-preview
      temperature: 0.7

research:
  max_hypotheses_per_run: 10
  max_experiments_per_hypothesis: 3
  default_runs_per_experiment: 5

experiments:
  max_parallel: 5
  default_timeout_seconds: 300
  cost_limit_usd: 10.0

risk:
  auto_approve_safe: true
  block_on_destructive: true

approval:
  mode: interactive  # interactive, async, auto_approve, auto_reject
  timeout_seconds: 300
```

<br>

## Architecture

```
tinman/
├── agents/                 # Autonomous research agents
│   ├── hypothesis_engine.py
│   ├── experiment_architect.py
│   ├── experiment_executor.py
│   ├── failure_discovery.py
│   ├── intervention_engine.py
│   └── simulation_engine.py
├── config/                 # Configuration and modes
│   ├── modes.py            # LAB/SHADOW/PRODUCTION
│   └── settings.py
├── core/                   # Infrastructure
│   ├── approval_gate.py
│   ├── control_plane.py
│   ├── risk_policy.py
│   ├── cost_tracker.py
│   └── tools.py
├── db/                     # Persistence
│   ├── connection.py
│   ├── models.py
│   └── audit.py
├── integrations/           # External connections
│   ├── model_client.py
│   ├── pipeline_adapter.py
│   ├── gateway_plugin/     # Real-time monitoring
│   └── *_client.py         # Provider clients
├── memory/                 # Knowledge graph
│   ├── graph.py
│   ├── models.py
│   └── repository.py
├── taxonomy/               # Failure classification
│   ├── failure_types.py
│   └── classifiers.py
├── reporting/              # Report generation
└── tui/                    # Terminal UI
```

<br>

## Documentation

| Document | Description |
|:---------|:------------|
| [QUICKSTART.md](docs/QUICKSTART.md) | Get running in 5 minutes |
| [CONCEPTS.md](docs/CONCEPTS.md) | Core mental model and abstractions |
| [ARCHITECTURE.md](docs/ARCHITECTURE.md) | System design and data flow |
| [TAXONOMY.md](docs/TAXONOMY.md) | Complete failure classification guide |
| [MODES.md](docs/MODES.md) | Operating mode behavior matrix |
| [HITL.md](docs/HITL.md) | Human-in-the-loop approval system |
| [INTEGRATION.md](docs/INTEGRATION.md) | Pipeline integration patterns |
| [CONFIGURATION.md](docs/CONFIGURATION.md) | All configuration options |

**Live docs:** [oliveskin.github.io/Agent-Tinman](https://oliveskin.github.io/Agent-Tinman/)

<br>

## Use Cases

**Research Lab** — Run in LAB mode against development deployments to discover failures before production.

**Shadow Monitoring** — Deploy in SHADOW mode alongside production to observe real traffic and surface emergent failure modes.

**Production Protection** — Run in PRODUCTION mode with human approval gates to actively protect against discovered patterns.

**Compliance & Audit** — Use the memory graph to demonstrate due diligence: what was discovered, what was applied, what the outcomes were.

**Real-Time Gateway Monitoring** — Connect to AI gateway WebSockets for instant event analysis as failures happen.

<br>

## Philosophy

Tinman embodies a **research methodology**, not just a tool:

1. **Systematic curiosity** — Continuously ask "what could go wrong?" rather than "does this work?"
2. **Hypothesis-driven** — Every test has a reason. No random fuzzing.
3. **Human oversight** — Autonomy where safe, human judgment where it matters.
4. **Temporal knowledge** — Not just "what failed" but "what did we know, when?"
5. **Continuous learning** — Each cycle informs the next. Knowledge compounds.

<br>

## Contributing

We welcome contributions. See [CONTRIBUTING.md](CONTRIBUTING.md) for:
- Development setup
- Code style (ruff, mypy)
- Testing requirements
- PR process

<br>

## License

Apache 2.0 — See [LICENSE](LICENSE)

<br>

---

<p align="center">
  <strong>Tinman is a public good.</strong><br>
  Not monetized, not proprietary—just a crystallized methodology for systematic AI reliability research.
</p>

<p align="center">
  <a href="https://github.com/oliveskin/Agent-Tinman">GitHub</a>&nbsp;&nbsp;•&nbsp;&nbsp;
  <a href="https://pypi.org/project/AgentTinman/">PyPI</a>&nbsp;&nbsp;•&nbsp;&nbsp;
  <a href="https://oliveskin.github.io/Agent-Tinman/">Docs</a>
</p>
