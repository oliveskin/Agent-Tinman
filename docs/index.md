---
hide:
  - navigation
  - toc
---

<div class="hero" markdown>

# Agent Tinman

**Forward-Deployed Research Agent for Continuous AI Reliability Discovery**

<div class="badges">
  <a href="https://pypi.org/project/AgentTinman/"><img src="https://img.shields.io/pypi/v/AgentTinman?color=d97706&label=pypi" alt="PyPI"></a>
  <a href="https://pypi.org/project/AgentTinman/"><img src="https://img.shields.io/pypi/pyversions/AgentTinman?color=d97706" alt="Python"></a>
  <a href="https://github.com/oliveskin/Agent-Tinman/blob/main/LICENSE"><img src="https://img.shields.io/badge/license-Apache%202.0-7c3aed" alt="License"></a>
</div>

[Get Started](QUICKSTART.md){ .md-button .md-button--primary }
[View on GitHub](https://github.com/oliveskin/Agent-Tinman){ .md-button }

</div>

---

> **Tinman is not a testing tool.** It's an autonomous research agent that continuously explores your AI system's behavior to discover failure modes you haven't imagined yet.

---

## The Problem

Every team deploying LLMs faces the same question:

> *"What don't we know about how this system can fail?"*

Most tools help you monitor what you've already anticipated. **Tinman helps you discover what you haven't.**

<div class="comparison" markdown>

<div markdown>

### Traditional Approach

- :material-close: Reactive—triggered after incidents
- :material-close: Tests known failure patterns
- :material-close: Output: pass/fail results
- :material-close: Stops when tests pass

</div>

<div markdown>

### Tinman

- :material-check: Proactive—always exploring
- :material-check: Generates novel hypotheses
- :material-check: Output: understanding
- :material-check: Never stops—research is ongoing

</div>

</div>

---

## Core Capabilities

<div class="grid" markdown>

<div class="card" markdown>
### :material-lightbulb: Hypothesis-Driven Research
Generates testable hypotheses about potential failure modes based on system architecture and observed behavior.
</div>

<div class="card" markdown>
### :material-flask: Controlled Experimentation
Tests each hypothesis with configurable parameters, cost controls, and reproducibility tracking.
</div>

<div class="card" markdown>
### :material-tag: Failure Classification
Classifies failures using a structured taxonomy with severity ratings (S0-S4).
</div>

<div class="card" markdown>
### :material-wrench: Intervention Design
Proposes concrete fixes: prompt mutations, guardrails, tool policies, architectural changes.
</div>

<div class="card" markdown>
### :material-replay: Simulation & Validation
Validates interventions through counterfactual replay before deployment.
</div>

<div class="card" markdown>
### :material-shield-account: Human-in-the-Loop
Risk-tiered approval gates ensure humans control consequential decisions.
</div>

</div>

---

## Quick Start

=== "Install"

    ```bash
    pip install AgentTinman
    ```

=== "Initialize"

    ```bash
    tinman init
    ```

=== "Run TUI"

    ```bash
    tinman tui
    ```

=== "Research Cycle"

    ```bash
    tinman research --focus "tool use failures"
    tinman report --format markdown
    ```

---

## Operating Modes

| Mode | Purpose | Approval Gates | Destructive Tests |
|:-----|:--------|:---------------|:------------------|
| **LAB** | Unrestricted research | Auto-approve most | Allowed |
| **SHADOW** | Observe production traffic | Review S3+ severity | Read-only |
| **PRODUCTION** | Active protection | Human approval required | Blocked |

!!! info "Progressive Rollout"
    LAB → SHADOW → PRODUCTION. Cannot skip modes.

---

## Failure Taxonomy

Tinman classifies failures into five primary classes:

| Class | Description |
|:------|:------------|
| **REASONING** | Logical errors, goal drift, hallucination |
| **LONG_CONTEXT** | Context window issues, attention dilution |
| **TOOL_USE** | Tool call failures, parameter errors, exfiltration |
| **FEEDBACK_LOOP** | Output amplification, error cascades |
| **DEPLOYMENT** | Infrastructure, latency, resource issues |

**Severity:** S0 (Benign) → S1 (UX) → S2 (Business) → S3 (Serious) → S4 (Critical)

---

## The Research Cycle

<div class="cycle-diagram" markdown>
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
</div>

1. **Generate hypotheses** about potential failures
2. **Design experiments** to test each hypothesis
3. **Execute experiments** with approval gates
4. **Discover and classify** failures found
5. **Design interventions** to address failures
6. **Simulate fixes** via counterfactual replay
7. **Learn** from results for future cycles

---

## Integrations

### Model Providers

| Provider | Cost | Best For |
|:---------|:-----|:---------|
| **Ollama** | Free (local) | Privacy, offline |
| **Groq** | Free tier | Speed, high volume |
| **OpenRouter** | Many free | DeepSeek, Qwen, Llama |
| **Together** | $25 free | Quality open models |
| **OpenAI** | Paid | GPT-4 |
| **Anthropic** | Paid | Claude |

### Real-Time Gateway Monitoring

Connect to AI gateway WebSockets for instant event analysis:

```python
from tinman.integrations.gateway_plugin import GatewayMonitor, ConsoleAlerter

monitor = GatewayMonitor(your_adapter)
monitor.add_alerter(ConsoleAlerter())
await monitor.start()
```

**Platform adapters:**

- [**OpenClaw**](https://github.com/oliveskin/tinman-openclaw-eval) — Security eval harness + gateway adapter

---

## Philosophy

Tinman embodies a **research methodology**, not just a tool:

1. **Systematic curiosity** — Ask "what could go wrong?" not "does this work?"
2. **Hypothesis-driven** — Every test has a reason. No random fuzzing.
3. **Human oversight** — Autonomy where safe, judgment where it matters.
4. **Temporal knowledge** — Track "what did we know, when?"
5. **Continuous learning** — Each cycle compounds knowledge.

---

<div style="text-align: center; margin-top: 3rem;" markdown>

**Tinman is a public good.**

Not monetized, not proprietary—just a crystallized methodology for systematic AI reliability research.

[GitHub](https://github.com/oliveskin/Agent-Tinman){ .md-button }
[PyPI](https://pypi.org/project/AgentTinman/){ .md-button }

</div>
