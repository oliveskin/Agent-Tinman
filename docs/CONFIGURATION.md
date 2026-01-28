# Configuration Reference

This document provides a complete reference for all Tinman configuration options.

---

## Table of Contents

1. [Overview](#overview)
2. [Configuration File](#configuration-file)
3. [Configuration Sections](#configuration-sections)
   - [mode](#mode)
   - [database](#database)
   - [models](#models)
   - [pipeline](#pipeline)
   - [risk](#risk)
   - [experiments](#experiments)
   - [research](#research)
   - [shadow](#shadow)
   - [approval](#approval)
   - [reporting](#reporting)
   - [logging](#logging)
   - [cost](#cost)
   - [metrics](#metrics)
   - [service](#service)
4. [Environment Variables](#environment-variables)
5. [Programmatic Configuration](#programmatic-configuration)
6. [Configuration Validation](#configuration-validation)
7. [Example Configurations](#example-configurations)

---

## Overview

Tinman configuration can be provided through:

1. **YAML Configuration File** - Primary configuration method
2. **Environment Variables** - For secrets and overrides
3. **Programmatic API** - Runtime configuration in code
4. **CLI Arguments** - Per-invocation overrides

Configuration is loaded in this order (later overrides earlier):
1. Default values
2. Configuration file (`.tinman/config.yaml` or `tinman.yaml`)
3. Environment variables
4. CLI arguments

---

## Configuration File

### File Location

Tinman looks for configuration in:
1. `.tinman/config.yaml` (preferred)
2. `tinman.yaml` (root directory)
3. Custom path via `--config` flag

### Creating Configuration

```bash
# Initialize with defaults
tinman init

# Creates .tinman/config.yaml
```

### File Structure

```yaml
# .tinman/config.yaml

mode: lab

database:
  url: sqlite:///tinman.db  # Default (no setup required)
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
  detailed_mode: false
  auto_approve_safe: true
  block_on_destructive: true

approval:
  mode: interactive
  timeout_seconds: 300

shadow:
  traffic_sample_rate: 0.1
  replay_buffer_days: 7

reporting:
  lab_output_dir: ./reports/lab
  ops_output_dir: ./reports/ops

logging:
  level: INFO
  format: json
```

---

## Configuration Sections

### mode

Operating mode for Tinman. See [MODES.md](MODES.md) for details.

```yaml
mode: lab  # or: shadow, production
```

| Value | Description |
|-------|-------------|
| `lab` | Full autonomy, destructive testing allowed |
| `shadow` | Observe production traffic, read-only |
| `production` | Active protection with human approval |

**CLI Override:**
```bash
tinman --mode shadow research
```

**Environment Variable:**
```bash
export TINMAN_MODE=production
```

---

### database

Database connection settings for the memory graph.

```yaml
database:
  url: sqlite:///tinman.db  # Default (no setup required)
  pool_size: 10
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `url` | string | `sqlite:///tinman.db` | Database connection URL |
| `pool_size` | int | `10` | Connection pool size |

**Supported Databases:**
- PostgreSQL (recommended for production)
- SQLite (for quick testing)

**PostgreSQL setup note:** If you use PostgreSQL, set `database.url` to your
Postgres DSN and ensure the role and database exist before running Tinman.

**SQLite Example:**
```yaml
database:
  url: sqlite:///tinman.db
  pool_size: 1  # SQLite supports single connection
```

**Environment Variable:**
```bash
export DATABASE_URL=postgresql://user:pass@host:5432/tinman
```

---

### models

LLM provider configuration.

```yaml
models:
  default: openai
  providers:
    openai:
      api_key: ${OPENAI_API_KEY}
      model: gpt-4-turbo-preview
      temperature: 0.7
      base_url: null  # Optional custom endpoint
    anthropic:
      api_key: ${ANTHROPIC_API_KEY}
      model: claude-3-opus-20240229
      temperature: 0.7
```

#### Top-Level Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `default` | string | `openai` | Default provider to use |

#### Provider Options

| Option | Type | Required | Description |
|--------|------|----------|-------------|
| `api_key` | string | Yes | API key (supports env var syntax) |
| `model` | string | Yes | Model identifier |
| `temperature` | float | No | Sampling temperature (0-1) |
| `base_url` | string | No | Custom API endpoint |

**Note:** The `model` value is used as the default for that provider unless a
specific model is passed at runtime. You can update the default provider/model
in `.tinman/config.yaml` (or via the TUI model picker if enabled).

**Environment Variable Syntax:**
```yaml
api_key: ${OPENAI_API_KEY}  # Reads from environment
```

**Supported Providers:**
- `openai` - OpenAI API
- `anthropic` - Anthropic Claude API
- `custom` - Custom OpenAI-compatible endpoint

---

### pipeline

Target pipeline/system configuration for probing.

```yaml
pipeline:
  adapter: generic
  endpoint: http://localhost:8000/v1/complete
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `adapter` | string | `generic` | Pipeline adapter type |
| `endpoint` | string | `http://localhost:8000/v1/complete` | Target endpoint |

**Adapter Types:**
- `generic` - Generic OpenAI-compatible API
- `langchain` - LangChain integration
- `custom` - Custom adapter (requires code)

---

### risk

Risk evaluation settings.

```yaml
risk:
  detailed_mode: false
  auto_approve_safe: true
  block_on_destructive: true
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `detailed_mode` | bool | `false` | Enable S0-S4 severity scoring |
| `auto_approve_safe` | bool | `true` | Auto-approve SAFE tier actions |
| `block_on_destructive` | bool | `true` | Block destructive actions |

**Detailed Mode:**
When enabled, provides granular severity assessment:
- S0: Negligible
- S1: Low
- S2: Medium
- S3: High
- S4: Critical

---

### experiments

Experiment execution settings.

```yaml
experiments:
  max_parallel: 5
  default_timeout_seconds: 300
  cost_limit_usd: 10.0
  allow_destructive: true  # Only in LAB mode
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `max_parallel` | int | `5` | Maximum concurrent experiments |
| `default_timeout_seconds` | int | `300` | Experiment timeout (5 minutes) |
| `cost_limit_usd` | float | `10.0` | Cost limit per research cycle |
| `allow_destructive` | bool | `false` | Allow destructive tests |

**Mode-Specific Recommendations:**

| Mode | max_parallel | cost_limit_usd | allow_destructive |
|------|--------------|----------------|-------------------|
| LAB | 10 | 50.0 | true |
| SHADOW | 5 | 20.0 | false |
| PRODUCTION | 2 | 5.0 | false |

---

### research

Research cycle parameters.

```yaml
research:
  max_hypotheses_per_run: 10
  max_experiments_per_hypothesis: 3
  default_runs_per_experiment: 5
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `max_hypotheses_per_run` | int | `10` | Maximum hypotheses per cycle |
| `max_experiments_per_hypothesis` | int | `3` | Experiments per hypothesis |
| `default_runs_per_experiment` | int | `5` | Runs per experiment |

**Tuning Guidance:**

| Scenario | Hypotheses | Experiments | Runs |
|----------|------------|-------------|------|
| Quick exploration | 3-5 | 1-2 | 3 |
| Standard research | 10 | 3 | 5 |
| Deep investigation | 20 | 5 | 10 |

---

### shadow

Shadow mode specific settings.

```yaml
shadow:
  traffic_sample_rate: 0.1
  replay_buffer_days: 7
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `traffic_sample_rate` | float | `0.1` | Fraction of traffic to mirror (0-1) |
| `replay_buffer_days` | int | `7` | Days to retain traces for replay |

**Traffic Sampling:**
```yaml
# Sample 10% of production traffic
traffic_sample_rate: 0.1

# Sample 50% for high-traffic systems
traffic_sample_rate: 0.5

# Sample all traffic (high cost)
traffic_sample_rate: 1.0
```

---

### approval

Human-in-the-loop approval settings.

```yaml
approval:
  mode: interactive
  timeout_seconds: 300
  auto_approve_in_lab: true
  require_comment: false
  notify_on_block: true
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `mode` | string | `interactive` | Approval mode |
| `timeout_seconds` | int | `300` | Approval timeout |
| `auto_approve_in_lab` | bool | `true` | Auto-approve in LAB mode |
| `require_comment` | bool | `false` | Require comment on decisions |
| `notify_on_block` | bool | `true` | Send notification on BLOCK |

**Approval Modes:**

| Mode | Description |
|------|-------------|
| `interactive` | Block and wait for human via TUI |
| `async` | Non-blocking, use callbacks |
| `auto_approve` | Auto-approve all (dangerous!) |
| `auto_reject` | Auto-reject all (safe but limiting) |

**Severity-Based Timeouts:**
```yaml
approval:
  mode: interactive
  timeouts:
    S0: 60      # 1 minute
    S1: 120     # 2 minutes
    S2: 300     # 5 minutes
    S3: 600     # 10 minutes
```

---

### reporting

Report generation settings.

```yaml
reporting:
  lab_output_dir: ./reports/lab
  ops_output_dir: ./reports/ops
  default_format: markdown
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `lab_output_dir` | string | `./reports/lab` | Lab report output directory |
| `ops_output_dir` | string | `./reports/ops` | Operations report directory |
| `default_format` | string | `markdown` | Default report format |

**Report Formats:**
- `markdown` - Markdown format
- `json` - JSON format
- `html` - HTML format (for web viewing)

---

### logging

Logging configuration.

```yaml
logging:
  level: INFO
  format: json
  file: ./logs/tinman.log
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `level` | string | `INFO` | Log level |
| `format` | string | `json` | Log format |
| `file` | string | null | Log file path (optional) |

**Log Levels:**
- `DEBUG` - Detailed debugging
- `INFO` - General information
- `WARNING` - Warnings
- `ERROR` - Errors only

**Log Formats:**
- `json` - Structured JSON logs
- `text` - Human-readable text

---

### cost

Budget and cost tracking settings.

```yaml
cost:
  budget_usd: 100.0
  period: daily
  warn_threshold: 0.8
  hard_limit: true
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `budget_usd` | float | `100.0` | Maximum spend per period |
| `period` | string | `daily` | Budget reset period |
| `warn_threshold` | float | `0.8` | Warning threshold (0-1) |
| `hard_limit` | bool | `true` | Block operations when exceeded |

**Budget Periods:**
- `hourly` - Reset every hour
- `daily` - Reset every day (default)
- `weekly` - Reset every week
- `monthly` - Reset every month

**Example with enforcement:**
```yaml
cost:
  budget_usd: 50.0
  period: daily
  warn_threshold: 0.75
  hard_limit: true
  notify_on_warning: true
```

---

### metrics

Prometheus metrics server settings.

```yaml
metrics:
  enabled: true
  port: 9090
  path: /metrics
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `enabled` | bool | `true` | Enable metrics server |
| `port` | int | `9090` | Metrics server port |
| `path` | string | `/metrics` | Metrics endpoint path |

**Available Metrics:**

| Metric | Type | Description |
|--------|------|-------------|
| `tinman_research_cycles_total` | Counter | Total research cycles |
| `tinman_failures_discovered_total` | Counter | Failures by severity/class |
| `tinman_approval_decisions_total` | Counter | Approvals by decision/tier |
| `tinman_cost_usd_total` | Counter | Costs by source/model |
| `tinman_llm_requests_total` | Counter | LLM requests by model/status |
| `tinman_llm_latency_seconds` | Histogram | LLM request latency |
| `tinman_pending_approvals` | Gauge | Current pending approvals |

---

### service

HTTP service settings (for `tinman serve`).

```yaml
service:
  host: 0.0.0.0
  port: 8000
  workers: 4
  cors_origins: ["*"]
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `host` | string | `0.0.0.0` | Bind host |
| `port` | int | `8000` | Bind port |
| `workers` | int | `1` | Number of workers |
| `cors_origins` | list | `["*"]` | CORS allowed origins |

**Available Endpoints:**

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check with component status |
| `/ready` | GET | Kubernetes readiness probe |
| `/live` | GET | Kubernetes liveness probe |
| `/status` | GET | Current Tinman state |
| `/research/cycle` | POST | Run a research cycle |
| `/approvals/pending` | GET | List pending approvals |
| `/approvals/{id}/decide` | POST | Decide on approval |
| `/discuss` | POST | Interactive discussion |
| `/mode` | GET | Current mode |
| `/mode/transition` | POST | Transition modes |
| `/metrics` | GET | Prometheus metrics |

---

### risk_policy

External risk policy configuration file.

```yaml
risk_policy:
  path: ./risk_policy.yaml
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `path` | string | null | Path to risk policy YAML |

**Risk Policy File Format:**

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

cost_thresholds:
  low_cost_max: 1.0
  high_cost_min: 10.0
```

---

## Environment Variables

Environment variables override configuration file values.

### Standard Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `OPENAI_API_KEY` | OpenAI API key | `sk-...` |
| `ANTHROPIC_API_KEY` | Anthropic API key | `sk-ant-...` |
| `DATABASE_URL` | Database connection URL | `postgresql://...` |
| `TINMAN_MODE` | Operating mode | `lab`, `shadow`, `production` |
| `TINMAN_LOG_LEVEL` | Log level | `DEBUG`, `INFO`, etc. |
| `TINMAN_DATABASE_URL` | Database connection URL | `postgresql://...` |
| `TINMAN_BUDGET_USD` | Budget limit | `100.0` |
| `TINMAN_METRICS_PORT` | Metrics server port | `9090` |
| `TINMAN_SERVICE_PORT` | HTTP service port | `8000` |

### Using Environment Variables in Config

```yaml
models:
  providers:
    openai:
      api_key: ${OPENAI_API_KEY}  # Substituted at load time

database:
  url: ${DATABASE_URL}
```

### Shell Setup

```bash
# .env file
export OPENAI_API_KEY="sk-..."
export ANTHROPIC_API_KEY="sk-ant-..."
export DATABASE_URL="postgresql://localhost:5432/tinman"
export TINMAN_MODE="lab"

# Load
source .env
```

---

## Programmatic Configuration

### Using Settings Directly

```python
from tinman.config.settings import Settings, DatabaseSettings, ModelsSettings

settings = Settings(
    mode=Mode.LAB,
    database=DatabaseSettings(
        url="postgresql://localhost:5432/tinman",
        pool_size=20,
    ),
    models=ModelsSettings(
        default="openai",
        providers={
            "openai": ModelProviderSettings(
                api_key=os.environ["OPENAI_API_KEY"],
                model="gpt-4-turbo-preview",
            ),
        },
    ),
)
```

### Loading from File

```python
from tinman.config.settings import load_config
from pathlib import Path

# Load from default location
settings = load_config()

# Load from custom path
settings = load_config(Path("./custom-config.yaml"))
```

### Creating Tinman with Settings

```python
from tinman import create_tinman
from tinman.config.modes import Mode

# From settings object
tinman = await create_tinman(
    mode=settings.mode,
    db_url=settings.database_url,
    settings=settings,
)

# With overrides
tinman = await create_tinman(
    mode=Mode.PRODUCTION,  # Override mode
    db_url="postgresql://prod-server/tinman",
)
```

---

## Configuration Validation

### Validation Rules

1. **Required Fields:**
   - `models.providers.<provider>.api_key` must be set
   - `database.url` must be valid URL format

2. **Value Ranges:**
   - `experiments.max_parallel`: 1-100
   - `shadow.traffic_sample_rate`: 0.0-1.0
   - `experiments.cost_limit_usd`: > 0

3. **Mode Constraints:**
   - `allow_destructive` only valid in LAB mode
   - PRODUCTION requires `approval.mode != auto_approve`

### Validation Example

```python
from tinman.config.settings import Settings

settings = Settings.from_dict(config_dict)

# Validation happens automatically
# Raises ValueError if invalid
```

---

## Example Configurations

### Minimal LAB Configuration

```yaml
mode: lab

database:
  url: sqlite:///tinman.db

models:
  default: openai
  providers:
    openai:
      api_key: ${OPENAI_API_KEY}
      model: gpt-4-turbo-preview
```

### Production Configuration

```yaml
mode: production

database:
  url: postgresql://prod-db:5432/tinman
  pool_size: 20

models:
  default: openai
  providers:
    openai:
      api_key: ${OPENAI_API_KEY}
      model: gpt-4-turbo-preview
      temperature: 0.3  # Lower for consistency

research:
  max_hypotheses_per_run: 5
  max_experiments_per_hypothesis: 2
  default_runs_per_experiment: 3

experiments:
  max_parallel: 2
  default_timeout_seconds: 60
  cost_limit_usd: 5.0

risk:
  detailed_mode: true
  auto_approve_safe: true
  block_on_destructive: true

approval:
  mode: interactive
  timeout_seconds: 600
  require_comment: true
  notify_on_block: true

logging:
  level: INFO
  format: json
  file: /var/log/tinman/tinman.log
```

### Shadow Mode Configuration

```yaml
mode: shadow

database:
  url: postgresql://shadow-db:5432/tinman
  pool_size: 10

models:
  default: openai
  providers:
    openai:
      api_key: ${OPENAI_API_KEY}
      model: gpt-4-turbo-preview

shadow:
  traffic_sample_rate: 0.1  # Sample 10% of traffic
  replay_buffer_days: 14    # 2 weeks of traces

experiments:
  max_parallel: 5
  cost_limit_usd: 20.0

approval:
  mode: interactive
  auto_approve_in_lab: false  # Not in LAB
```

### Multi-Provider Configuration

```yaml
mode: lab

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
      temperature: 0.7

    local:
      api_key: not-required
      model: llama-2-70b
      base_url: http://localhost:11434/v1
```

### CI/CD Testing Configuration

```yaml
mode: lab

database:
  url: sqlite:///:memory:  # In-memory for tests

models:
  default: mock
  providers:
    mock:
      api_key: test-key
      model: mock-model

experiments:
  max_parallel: 1
  default_timeout_seconds: 30
  cost_limit_usd: 1.0

approval:
  mode: auto_reject  # Reject all in CI
```

---

## Summary

Key configuration areas:

| Section | Purpose |
|---------|---------|
| `mode` | Operating mode (LAB/SHADOW/PRODUCTION) |
| `database` | Memory graph persistence |
| `models` | LLM provider settings |
| `experiments` | Research execution limits |
| `risk` | Risk evaluation behavior |
| `approval` | HITL approval settings |
| `shadow` | Traffic mirroring for SHADOW mode |
| `reporting` | Output generation |
| `logging` | Log configuration |
| `cost` | Budget and cost tracking |
| `metrics` | Prometheus metrics server |
| `service` | HTTP API service settings |
| `risk_policy` | External risk policy file |

Configuration precedence:
1. CLI arguments (highest)
2. Environment variables
3. Configuration file
4. Defaults (lowest)

---

## Next Steps

- [MODES.md](MODES.md) - Detailed mode behavior
- [HITL.md](HITL.md) - Approval configuration details
- [INTEGRATION.md](INTEGRATION.md) - Pipeline integration
- [PRODUCTION.md](PRODUCTION.md) - Production deployment guide
