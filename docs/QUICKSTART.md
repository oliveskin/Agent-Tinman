# Quickstart Guide

Get Tinman running and discover your first failure in under 5 minutes.

---

## Prerequisites

- Python 3.10 or higher
- SQLite (default, no setup) or PostgreSQL for production
- An LLM API key (see options below)

### Model Provider Options

| Provider | Cost | Setup |
|----------|------|-------|
| **Ollama** | Free (local) | `ollama pull llama3.1` |
| **Groq** | Free tier (14,400/day) | Get key at groq.com |
| **OpenRouter** | Many free models | Get key at openrouter.ai |
| **Together** | $25 free credits | Get key at together.xyz |
| **OpenAI** | Paid | Get key at openai.com |
| **Anthropic** | Paid | Get key at anthropic.com |

---

## Installation

### Step 1: Install Tinman

```bash
# Basic installation
pip install AgentTinman

# With OpenAI support
pip install AgentTinman[openai]

# With Anthropic support
pip install AgentTinman[anthropic]

# With all providers
pip install AgentTinman[all]

# Development installation (from source)
git clone https://github.com/oliveskin/agent_tinman.git
cd agent_tinman
pip install -e ".[dev]"
```

### Step 2: Set Up Database

Tinman defaults to SQLite (`sqlite:///tinman.db`) for quick starts.
If you want PostgreSQL, set `database.url` in `.tinman/config.yaml` and create the role/database first.

**Option A: PostgreSQL (Recommended for production)**

```bash
# Create database (PostgreSQL)
createdb tinman

# Tinman will create tables automatically on first run
```

**Option B: SQLite (Quick testing)**

```bash
# No setup needed - Tinman will create the file
# Just use: sqlite:///tinman.db as your database URL
```

### Step 3: Set Environment Variables

```bash
# Pick ONE of these based on your provider:

# For Ollama (local, free) - no key needed!
# Just make sure Ollama is running: ollama serve

# For Groq (fast, free tier)
export GROQ_API_KEY="gsk_..."

# For OpenRouter (many free models)
export OPENROUTER_API_KEY="sk-or-..."

# For Together ($25 free credits)
export TOGETHER_API_KEY="..."

# For OpenAI (paid)
export OPENAI_API_KEY="sk-..."

# For Anthropic (paid)
export ANTHROPIC_API_KEY="sk-ant-..."
```

---

## Initialize Your Project

### Step 4: Create Configuration

```bash
tinman init
```

This creates `.tinman/config.yaml`:

```yaml
mode: lab

database:
  url: sqlite:///tinman.db  # Default (no setup required)
  # For PostgreSQL: url: postgresql://localhost:5432/tinman

models:
  default: openai
  providers:
    openai:
      api_key: ${OPENAI_API_KEY}
      model: gpt-4-turbo-preview
      temperature: 0.7

research:
  max_hypotheses_per_run: 5
  max_experiments_per_hypothesis: 2
  default_runs_per_experiment: 3

experiments:
  max_parallel: 3
  default_timeout_seconds: 120
  cost_limit_usd: 5.0
```

Edit the configuration to match your setup.

---

## Run Your First Research Cycle

### Option 1: Command Line

```bash
# Run a basic research cycle
tinman research

# With a specific focus area
tinman research --focus "reasoning errors"

# With custom parameters
tinman research --focus "tool use" --hypotheses 3 --experiments 2
```

### Option 2: Interactive TUI

```bash
tinman tui
```

This launches the retro terminal interface:

```
████████╗██╗███╗   ██╗███╗   ███╗ █████╗ ███╗   ██╗
╚══██╔══╝██║████╗  ██║████╗ ████║██╔══██╗████╗  ██║
   ██║   ██║██╔██╗ ██║██╔████╔██║███████║██╔██╗ ██║
   ██║   ██║██║╚██╗██║██║╚██╔╝██║██╔══██║██║╚██╗██║
   ██║   ██║██║ ╚████║██║ ╚═╝ ██║██║  ██║██║ ╚████║
   ╚═╝   ╚═╝╚═╝  ╚═══╝╚═╝     ╚═╝╚═╝  ╚═╝╚═╝  ╚═══╝

[F1] Research  [F2] Hypotheses  [F3] Failures  [F4] Intervene  [F5] Discuss

═══ RESEARCH CONTROL ═══

[▶ Start Research] [⏸ Pause] [⏹ Stop]

Focus Area: [tool use failures_______________]

─── Activity Log ───
Ready. Press [F1] or click 'Start Research' to begin.

Hypotheses: 0 │ Experiments: 0 │ Failures: 0
```

**Controls:**
- `F1-F5` - Navigate tabs
- `F10` or `Ctrl+C` - Exit
- `Y/N` - Approve/Reject in approval dialogs

### Option 3: Python API

```python
import asyncio
from tinman import create_tinman
from tinman.config.modes import Mode

async def main():
    # Create Tinman instance
    tinman = await create_tinman(
        mode=Mode.LAB,
        db_url="postgresql://localhost/tinman"
    )

    # Run a research cycle
    results = await tinman.research_cycle(
        focus="reasoning errors in multi-step tasks",
        max_hypotheses=5,
        max_experiments=3
    )

    # Print summary
    print(f"\n{'='*50}")
    print("RESEARCH CYCLE COMPLETE")
    print(f"{'='*50}")
    print(f"Hypotheses generated: {len(results.hypotheses)}")
    print(f"Experiments run: {len(results.experiments)}")
    print(f"Failures discovered: {len(results.failures)}")
    print(f"Interventions proposed: {len(results.interventions)}")

    # Show discovered failures
    if results.failures:
        print(f"\n{'─'*50}")
        print("DISCOVERED FAILURES:")
        for f in results.failures:
            print(f"\n  [{f.severity.value}] {f.failure_class.value}")
            print(f"  Description: {f.description}")
            print(f"  Root cause: {f.root_cause}")

    # Generate report
    report = await tinman.generate_report(format="markdown")
    print(f"\n{'─'*50}")
    print("FULL REPORT:")
    print(report)

    await tinman.close()

if __name__ == "__main__":
    asyncio.run(main())
```

---

## Understanding the Output

### Hypotheses

```
Hypothesis: HYP-001
Target: reasoning
Expected Failure: goal_drift
Confidence: 0.7
Rationale: System may lose track of original objectives in long conversations
```

Hypotheses are educated guesses about what might fail. Higher confidence means more evidence supports the hypothesis.

### Experiments

```
Experiment: EXP-001
Testing: HYP-001
Stress Type: CONTEXT_INJECTION
Parameters: {"distractor_count": 3, "injection_point": "mid"}
Runs: 5
```

Experiments are designed to confirm or refute hypotheses. Multiple runs ensure statistical significance.

### Failures

```
Failure: FAIL-001
Class: REASONING
Subtype: GOAL_DRIFT
Severity: S2 (Business Risk)
Reproducibility: 4/5 runs
Description: Model abandoned original task after distractor injection
Root Cause: Attention mechanism prioritizes recent context over instructions
```

Failures are classified using the taxonomy. Severity indicates impact.

### Interventions

```
Intervention: INT-001
Target: FAIL-001
Type: PROMPT_MUTATION
Description: Add periodic instruction reinforcement
Estimated Effectiveness: 75%
Risk Tier: REVIEW
Rollback Plan: Remove injection logic
```

Interventions are proposed fixes. They require approval before deployment.

---

## Common Commands

### Research

```bash
# Basic research
tinman research

# Focused research
tinman research --focus "tool use"
tinman research --focus "long context handling"
tinman research --focus "feedback loops"

# Control parameters
tinman research --hypotheses 10 --experiments 5 --runs 10

# Different mode
tinman --mode shadow research
```

### Reporting

```bash
# Generate markdown report
tinman report --format markdown

# Generate JSON report
tinman report --format json

# Exclude synthetic demo failures
tinman report --format markdown --exclude-demo-failures

# Save to file
tinman report --format markdown > report.md

# Reset the local SQLite demo database
tinman demo-reset-db
```

### Status

```bash
# Show current status
tinman status

# Show failure summary
tinman failures

# Show intervention status
tinman interventions
```

### Interactive

```bash
# Launch TUI
tinman tui

# Chat with Tinman
tinman discuss "What's the most critical failure?"
tinman discuss "How should I prioritize fixes?"
```

### Service Mode

```bash
# Start HTTP service
tinman serve --host 0.0.0.0 --port 8000

# Or with specific mode
TINMAN_MODE=shadow tinman serve

# Health check
curl http://localhost:8000/health

# Run research cycle via API
curl -X POST http://localhost:8000/research/cycle \
  -H "Content-Type: application/json" \
  -d '{"focus": "tool_use", "max_hypotheses": 5}'

# Get status
curl http://localhost:8000/status

# Get pending approvals
curl http://localhost:8000/approvals/pending
```

---

## What's Next?

### Learn the Concepts

Read [CONCEPTS.md](CONCEPTS.md) to understand:
- What a forward-deployed research agent does
- The hypothesis-driven methodology
- How knowledge compounds over time

### Understand Operating Modes

Read [MODES.md](MODES.md) to learn about:
- LAB mode for unrestricted research
- SHADOW mode for production observation
- PRODUCTION mode for active protection

### Explore the Taxonomy

Read [TAXONOMY.md](TAXONOMY.md) to understand:
- Failure classes (REASONING, LONG_CONTEXT, etc.)
- Severity levels (S0-S4)
- How to interpret and act on findings

### Configure for Production

Read [CONFIGURATION.md](CONFIGURATION.md) for:
- All configuration options
- Environment variable setup
- Cost and safety controls

### Integrate with Your Pipeline

Read [INTEGRATION.md](INTEGRATION.md) for:
- Embedding Tinman in existing systems
- Using the PipelineAdapter
- Custom approval workflows

### Deploy to Production

Read [PRODUCTION.md](PRODUCTION.md) for:
- Docker/Kubernetes deployment
- Database migrations with Alembic
- Prometheus metrics setup
- Cost controls and budget enforcement
- Operational runbook

---

## Development & Testing

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage report
pytest --cov=tinman

# Run specific test file
pytest tests/test_risk_evaluation.py

# Run specific test
pytest tests/test_risk_evaluation.py::TestRiskEvaluator::test_destructive_always_blocked

# Verbose output
pytest -v

# Stop on first failure
pytest -x
```

### Test Categories

| Test File | Coverage |
|-----------|----------|
| `test_risk_evaluation.py` | Risk evaluator, severity, policy-driven evaluation |
| `test_guarded_tools.py` | Tool registry, guarded_call, blocking, approval flow |
| `test_audit.py` | AuditLogger, approval decisions, mode transitions |
| `test_approval_flow.py` | Full HITL flow including timeouts |
| `test_ingest.py` | OTLP, Datadog, X-Ray, JSON trace adapters |
| `test_agents.py` | Hypothesis engine, experiment executor |
| `test_memory.py` | Memory graph operations |

### Code Quality

```bash
# Type checking
mypy tinman

# Linting
ruff check tinman

# Format code
ruff format tinman
```

### Database Migrations (Development)

```bash
# Create new migration after model changes
alembic revision --autogenerate -m "description"

# Apply migrations
alembic upgrade head

# Rollback one version
alembic downgrade -1

# Check current version
alembic current
```

---

## Troubleshooting

### Database Connection Error

```
Error: Could not connect to database
```

**Fix:** Check your database URL and ensure the database exists. If you want to skip
PostgreSQL for now, set `database.url` to `sqlite:///tinman.db`:
```bash
# PostgreSQL
createdb tinman

# Or use SQLite
# Set url: sqlite:///tinman.db in config
```

### API Key Error

```
Error: Invalid API key
```

**Fix:** Ensure environment variable is set:
```bash
echo $OPENAI_API_KEY  # Should show your key
export OPENAI_API_KEY="sk-..."
```

### Permission Error (Windows)

```
Error: Permission denied
```

**Fix:** Run terminal as administrator or check file permissions.

### TUI Not Displaying Correctly

**Fix:** Ensure your terminal supports Unicode and has sufficient size:
```bash
# Check terminal size
tput cols  # Should be 80+
tput lines # Should be 24+
```

### Cost Limit Reached

```
Warning: Cost limit reached ($5.00)
```

**Fix:** Increase limit in config or wait for next cycle:
```yaml
experiments:
  cost_limit_usd: 10.0
```

---

## Getting Help

- **Documentation:** See the `docs/` directory
- **Issues:** Report bugs at [GitHub Issues](https://github.com/oliveskin/agent_tinman/issues)
- **Discussions:** Ask questions in [GitHub Discussions](https://github.com/oliveskin/agent_tinman/discussions)
