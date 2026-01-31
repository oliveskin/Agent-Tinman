# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Tinman (AgentTinman)** is a Forward-Deployed Research Agent for continuous AI reliability discovery. It's an autonomous research agent that proactively generates hypotheses about AI system failures, designs experiments to test them, discovers failure modes, and proposes interventions—all with human oversight at critical decision points.

- **Package:** `AgentTinman` on PyPI
- **Repository:** https://github.com/oliveskin/Agent-Tinman
- **License:** Apache 2.0
- **Python:** 3.10+ (tested on 3.10, 3.11, 3.12)

## Build & Development Commands

```bash
# Install with dev dependencies
pip install -e ".[dev,all]"

# Run tests
pytest                          # All tests
pytest tests/test_agents.py     # Specific file
pytest -k "test_name"           # Specific test by name

# Lint and format
ruff format .                   # Format code
ruff check .                    # Lint
ruff check --fix .              # Auto-fix lint issues

# Type checking
mypy tinman

# All quality checks
ruff format . && ruff check . && mypy tinman && pytest

# Database migrations (PostgreSQL)
alembic upgrade head
tinman db init

# CLI commands
tinman init                     # Create .tinman/config.yaml
tinman research --focus "..."   # Run research cycle
tinman report --format markdown # Generate report
tinman tui                      # Terminal UI
python -m tinman.cli.main tui   # Alternative TUI launch
```

## Architecture

### Core Research Loop

```
HypothesisEngine → ExperimentArchitect → ExperimentExecutor
                                              ↓
                                       FailureDiscovery
                                              ↓
                   SimulationEngine ← InterventionEngine
                                              ↓
                                    MemoryGraph (learning)
```

### Key Components

| Directory | Purpose |
|-----------|---------|
| `tinman/agents/` | Autonomous research agents (base.py, hypothesis_engine.py, etc.) |
| `tinman/core/` | Infrastructure: approval_gate.py, risk_evaluator.py, event_bus.py, control_plane.py |
| `tinman/memory/` | Knowledge graph with temporal validity (graph.py, models.py) |
| `tinman/reasoning/` | LLM interaction: llm_backbone.py, adaptive_memory.py |
| `tinman/taxonomy/` | Failure classification: failure_types.py (5 classes, 25+ subtypes, S0-S4 severity) |
| `tinman/integrations/` | Model clients: openai, anthropic, google, groq, ollama, together, openrouter |
| `tinman/db/` | SQLAlchemy ORM with PostgreSQL/SQLite support |
| `tinman/tui/` | Textual-based terminal UI (app.py, styles.tcss) |
| `tinman/cli/` | Click-based CLI (main.py) |
| `tinman/tinman.py` | Main Tinman orchestrator |

### Operating Modes

| Mode | Approval | Destructive Tests |
|------|----------|-------------------|
| **LAB** | Auto-approve most | Allowed |
| **SHADOW** | Review S3+ severity | Read-only |
| **PRODUCTION** | Human approval required | Blocked |

Transition: LAB → SHADOW → PRODUCTION (cannot skip modes)

## Code Conventions

- **Line length:** 100 characters
- **Type hints:** Required on all functions (strict mypy mode)
- **Async:** Heavy use of async/await for I/O operations
- **Classes:** PascalCase
- **Functions/methods:** snake_case
- **Constants:** UPPER_SNAKE_CASE
- **Private:** _leading_underscore

### Agent Pattern

All agents inherit from `BaseAgent` with:
- `agent_type` property (unique identifier)
- `execute(context, **kwargs) → AgentResult` (main logic)
- `AgentContext` passed through with mode, session_id, metadata
- `AgentState` lifecycle: IDLE → RUNNING → PAUSED/COMPLETED/FAILED

### Key Architectural Patterns

- **Mode-aware behavior:** Always check `context.mode` before destructive actions
- **Event-driven communication:** Use `EventBus` for cross-component communication
- **Temporal memory:** Graph nodes have `valid_from`/`valid_to` for point-in-time queries
- **Approval flow:** Route through `ApprovalHandler`, never bypass HITL in PRODUCTION

## Testing

- pytest with `asyncio_mode = "auto"`
- Fixtures in `tests/conftest.py` for lab/shadow/production contexts
- Mode-aware tests verify behavior differs by operating mode
- Test files: test_agents.py, test_approval_flow.py, test_memory.py, test_taxonomy.py, etc.

## Configuration

Config file: `.tinman/config.yaml`

API keys via environment variables (referenced as `${VAR_NAME}` in config):
- `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`
- `GROQ_API_KEY`, `TOGETHER_API_KEY`, `OPENROUTER_API_KEY`
- Demo APIs: `GITHUB_TOKEN`, `HUGGINGFACE_API_KEY`, `REPLICATE_API_TOKEN`, `FAL_API_KEY`

## Failure Taxonomy

| Class | Description |
|-------|-------------|
| REASONING | Logic errors, goal drift, hallucination |
| LONG_CONTEXT | Context window issues, attention dilution |
| TOOL_USE | Tool call failures, parameter errors |
| FEEDBACK_LOOP | Output amplification, error cascades |
| DEPLOYMENT | Infrastructure, latency, resource issues |

Severity: S0 (benign) → S4 (critical/harmful action)

## Documentation

Key docs in `docs/`:
- ARCHITECTURE.md - System design
- CONCEPTS.md - Mental model
- TAXONOMY.md - Failure classification
- HITL.md - Approval system
- MODES.md - Operating mode behavior
- MEMORY.md - Knowledge graph
- INTEGRATION.md - Pipeline integration patterns
