# Tinman FDRA

Forward-Deployed Research Agent for continuous AI reliability discovery.

**Tinman is not a testing tool.** It is an autonomous research agent that explores your AI system and discovers failure modes you haven’t imagined yet.

---

## Quick Start

```bash
pip install AgentTinman
python -m tinman.cli.main init
python -m tinman.cli.main tui
```

---

## What Tinman Does

- Generates hypotheses about potential failures
- Designs and runs experiments
- Classifies failures using a structured taxonomy
- Proposes interventions and simulates fixes
- Keeps a memory graph for longitudinal learning

---

## Demo-First Flow

1. Set keys in `.env` (created by `tinman init`)
2. Run a GitHub demo
3. Generate a demo report

```bash
python -m tinman.demo.github_demo --repo moltbot/moltbot
python -m tinman.cli.main report --format demo

Exclude synthetic demo failures:

```bash
tinman report --format markdown --exclude-demo-failures
```
```

---

## Screenshots

Add TUI screenshots here once available.

---

## Next Steps

- [Getting Started](getting-started.md)
- [Demos](demos.md)
- [TUI](tui.md)
- [Integration Guide](INTEGRATION.md)
