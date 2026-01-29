# Integration Guide

This document covers how to integrate Tinman into existing AI systems, pipelines, and workflows.

---

## Table of Contents

1. [Overview](#overview)
2. [Integration Patterns](#integration-patterns)
3. [Pipeline Adapter](#pipeline-adapter)
4. [Model Clients](#model-clients)
5. [Embedding Tinman](#embedding-tinman)
6. [Event System](#event-system)
7. [Database Integration](#database-integration)
8. [CI/CD Integration](#cicd-integration)
9. [Framework Integration](#framework-integration)
10. [Production Deployment](#production-deployment)
11. [Examples](#examples)

---

## Overview

Tinman is designed to integrate seamlessly into existing AI infrastructure. There are multiple integration approaches depending on your use case:

| Integration Pattern | Description | Best For |
|---------------------|-------------|----------|
| **Library Import** | Import Tinman directly in Python code | Custom applications, notebooks |
| **Pipeline Adapter** | Hook into existing LLM pipelines | Production systems, middleware |
| **CLI/TUI** | Use command-line interface | Ad-hoc research, exploration |
| **Event-Driven** | Subscribe to Tinman events | Monitoring, alerting |

### Integration Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Your Application                             │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐│
│  │ Web Service │  │  Worker     │  │  Notebook   │  │  CLI Tool   ││
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘│
│         │                │                │                │        │
│         └────────────────┴────────────────┴────────────────┘        │
│                                  │                                  │
│                        ┌─────────▼─────────┐                        │
│                        │ Tinman Integration │                        │
│                        │                   │                        │
│                        │ ┌───────────────┐ │                        │
│                        │ │PipelineAdapter│ │                        │
│                        │ │ ModelClient   │ │                        │
│                        │ │ EventBus      │ │                        │
│                        │ └───────────────┘ │                        │
│                        └─────────┬─────────┘                        │
│                                  │                                  │
└──────────────────────────────────┼──────────────────────────────────┘
                                   │
                          ┌────────▼────────┐
                          │    Tinman       │
                          │  Research Core  │
                          └─────────────────┘
```

---

## Integration Patterns

### Pattern 1: Direct Library Import

The simplest integration - import and use Tinman as a Python library.

```python
import asyncio
from tinman import create_tinman, OperatingMode
from tinman.integrations import OpenAIClient

async def main():
    # Create model client
    client = OpenAIClient(api_key="sk-...")

    # Create Tinman instance
    tinman = await create_tinman(
        mode=OperatingMode.LAB,
        model_client=client,
        db_url="postgresql://localhost/tinman",
    )

    # Run research
    results = await tinman.research_cycle(
        focus="reasoning failures in code generation",
        max_hypotheses=5,
    )

    # Generate report
    report = await tinman.generate_report()
    print(report)

    await tinman.close()

asyncio.run(main())
```

### Pattern 2: Pipeline Middleware

Intercept requests/responses in your existing LLM pipeline.

```python
from tinman.integrations import PipelineAdapter, FailureDetectionHook
from tinman.config.modes import OperatingMode

# Create adapter
adapter = PipelineAdapter(mode=OperatingMode.SHADOW)
adapter.register_hook(FailureDetectionHook())

# In your existing pipeline
async def my_llm_call(messages: list, model: str):
    # Pre-request hook
    ctx = adapter.create_context(messages=messages, model=model)
    ctx = await adapter.pre_request(ctx)

    # Your existing LLM call
    response = await your_model_client.complete(messages, model)

    # Post-request hook
    ctx.response = response
    ctx = await adapter.post_request(ctx)

    # Check for detected issues
    if "detected_failures" in ctx.metadata:
        log_potential_failures(ctx.metadata["detected_failures"])

    return response
```

### Pattern 3: Event-Driven Integration

Subscribe to Tinman events for monitoring and alerting.

```python
from tinman import create_tinman
from tinman.core.event_bus import EventBus

# Create event bus
event_bus = EventBus()

# Subscribe to events
@event_bus.on("failure.discovered")
async def on_failure(event_data):
    await send_alert(
        channel="ai-reliability",
        message=f"New failure: {event_data['failure_class']}"
    )

@event_bus.on("intervention.proposed")
async def on_intervention(event_data):
    await create_ticket(
        title=f"Intervention proposed: {event_data['name']}",
        body=event_data['description']
    )

# Tinman will emit events as it works
tinman = await create_tinman(mode=OperatingMode.LAB)
tinman.event_bus = event_bus
```

---

## Pipeline Adapter

The `PipelineAdapter` provides hooks at key points in LLM pipeline execution.

### Hook Points

```python
from tinman.integrations.pipeline_adapter import HookPoint

class HookPoint(str, Enum):
    PRE_REQUEST = "pre_request"      # Before model call
    POST_REQUEST = "post_request"    # After model call
    PRE_TOOL = "pre_tool"           # Before tool execution
    POST_TOOL = "post_tool"         # After tool execution
    ON_ERROR = "on_error"           # On any error
    ON_COMPLETION = "on_completion"  # On task completion
```

### Creating Custom Hooks

```python
from tinman.integrations.pipeline_adapter import (
    PipelineHook, HookPoint, HookResult, PipelineContext
)

class CustomValidationHook(PipelineHook):
    """Custom hook for validating model responses."""

    @property
    def name(self) -> str:
        return "custom_validation"

    @property
    def hook_points(self) -> list[HookPoint]:
        return [HookPoint.POST_REQUEST]

    async def execute(self,
                      hook_point: HookPoint,
                      context: PipelineContext) -> HookResult:
        # Validate response
        if context.response:
            content = str(context.response.get("content", ""))

            # Check for concerning patterns
            if "I cannot" in content and "error" in content.lower():
                # Log but don't block (in SHADOW mode)
                context.metadata["validation_warning"] = "Potential refusal pattern"
                return HookResult(
                    allow=True,
                    modified_context=context,
                    message="Logged potential issue"
                )

        return HookResult(allow=True)
```

### Built-in Hooks

**LoggingHook** - Simple logging for debugging:

```python
from tinman.integrations.pipeline_adapter import LoggingHook

adapter = PipelineAdapter()
adapter.register_hook(LoggingHook())
# Logs all hook points
```

**TokenLimitHook** - Enforce token limits:

```python
from tinman.integrations.pipeline_adapter import TokenLimitHook

adapter = PipelineAdapter()
adapter.register_hook(TokenLimitHook(max_tokens=50000))
# Blocks requests exceeding token limit
```

**FailureDetectionHook** - Detect failure patterns:

```python
from tinman.integrations.pipeline_adapter import FailureDetectionHook

adapter = PipelineAdapter()
adapter.register_hook(FailureDetectionHook(
    failure_patterns=["error", "failed", "cannot", "unable"]
))
# Detects potential failures in responses
```

### Pipeline Context

```python
from tinman.integrations.pipeline_adapter import PipelineContext

@dataclass
class PipelineContext:
    id: str                           # Unique request ID
    mode: OperatingMode               # Current operating mode

    # Request data
    messages: list[dict]              # Input messages
    model: str                        # Target model
    tools: list[dict]                 # Available tools

    # Response data (after request)
    response: Optional[dict]          # Model response
    error: Optional[str]              # Error if any

    # Metadata (for passing data between hooks)
    metadata: dict[str, Any]          # Custom metadata
    started_at: datetime              # Request start time
```

### Hook Blocking Behavior

Hooks can block pipeline execution based on mode:

```python
# In LAB/PRODUCTION mode: raises PipelineBlocked exception
# In SHADOW mode: logs warning but continues

async def execute(self, hook_point, context) -> HookResult:
    if should_block(context):
        return HookResult(
            allow=False,
            message="Request blocked: exceeds safety threshold"
        )
    return HookResult(allow=True)
```

---

## Model Clients

Tinman provides a unified interface for different LLM providers.

### Abstract ModelClient

```python
from tinman.integrations.model_client import ModelClient, ModelResponse

class ModelClient(ABC):
    """Abstract base class for model clients."""

    @property
    @abstractmethod
    def provider(self) -> str:
        """Provider name (e.g., 'openai', 'anthropic')."""
        pass

    @abstractmethod
    async def complete(self,
                       messages: list[dict[str, str]],
                       model: Optional[str] = None,
                       temperature: float = 0.7,
                       max_tokens: int = 4096,
                       tools: Optional[list[dict]] = None,
                       **kwargs) -> ModelResponse:
        """Send a completion request."""
        pass

    @abstractmethod
    async def stream(self,
                     messages: list[dict[str, str]],
                     model: Optional[str] = None,
                     **kwargs):
        """Stream a completion response."""
        pass
```

### ModelResponse

```python
@dataclass
class ModelResponse:
    id: str                              # Response ID
    content: str                         # Generated content
    model: str                           # Model used

    # Token usage
    prompt_tokens: int                   # Input tokens
    completion_tokens: int               # Output tokens
    total_tokens: int                    # Total tokens

    # Tool calls
    tool_calls: list[dict[str, Any]]     # Tool call requests

    # Metadata
    finish_reason: str                   # Stop reason
    latency_ms: int                      # Response latency
    raw: Optional[dict[str, Any]]        # Raw response
```

### OpenAI Client

```python
from tinman.integrations import OpenAIClient

client = OpenAIClient(
    api_key="sk-...",                    # Or use OPENAI_API_KEY env var
    base_url="https://api.openai.com/v1",  # Optional custom endpoint
    organization="org-...",               # Optional organization
)

# Use with Tinman
tinman = await create_tinman(
    model_client=client,
    mode=OperatingMode.LAB,
)
```

Supported models:
- GPT-4 Turbo (`gpt-4-turbo-preview`)
- GPT-4 (`gpt-4`)
- GPT-3.5 Turbo (`gpt-3.5-turbo`)
- Any OpenAI-compatible endpoint

### Anthropic Client

```python
from tinman.integrations import AnthropicClient

client = AnthropicClient(
    api_key="sk-ant-...",                # Or use ANTHROPIC_API_KEY env var
    base_url="https://api.anthropic.com",  # Optional custom endpoint
)

# Use with Tinman
tinman = await create_tinman(
    model_client=client,
    mode=OperatingMode.LAB,
)
```

Supported models:
- Claude 3.5 Sonnet (`claude-3-5-sonnet-20241022`)
- Claude 3 Opus (`claude-3-opus-20240229`)
- Claude 3 Sonnet (`claude-3-sonnet-20240229`)
- Claude 3 Haiku (`claude-3-haiku-20240307`)

---

### Open Model Providers

Tinman supports several providers for open/free models, making it accessible for experimentation without API costs.

#### Provider Comparison

| Provider | Free Tier | Speed | Models | Best For |
|----------|-----------|-------|--------|----------|
| **OpenRouter** | Many free models | Good | DeepSeek, Qwen, Llama, Mistral | Variety, free tiers |
| **Groq** | 14,400 req/day | Ultra-fast | Llama 3.x, Mixtral, Gemma | Speed, high volume |
| **Ollama** | Unlimited (local) | Varies | Any Ollama model | Privacy, offline |
| **Together** | $25 credits | Good | DeepSeek, Qwen, Llama | Quality, credits |

---

### OpenRouter Client

Access to 100+ models including DeepSeek, Qwen, Llama, and Mistral with many free tiers.

```python
from tinman.integrations import OpenRouterClient

client = OpenRouterClient(
    api_key="sk-or-...",  # Or set OPENROUTER_API_KEY env var
)

# Use DeepSeek (free tier available)
tinman = await create_tinman(model_client=client)

# Specify model explicitly
response = await client.complete(
    messages=[{"role": "user", "content": "Hello"}],
    model="deepseek-chat",  # Shorthand
    # or: model="deepseek/deepseek-chat"  # Full ID
)
```

**Available model shorthands:**

| Shorthand | Full Model ID | Notes |
|-----------|---------------|-------|
| `deepseek-chat` | `deepseek/deepseek-chat` | Free tier |
| `deepseek-coder` | `deepseek/deepseek-coder` | Free tier |
| `deepseek-r1` | `deepseek/deepseek-r1` | Reasoning model |
| `qwen-2.5-72b` | `qwen/qwen-2.5-72b-instruct` | Strong general |
| `qwen-2.5-coder-32b` | `qwen/qwen-2.5-coder-32b-instruct` | Code |
| `llama-3.1-405b` | `meta-llama/llama-3.1-405b-instruct` | Largest |
| `llama-3.1-70b` | `meta-llama/llama-3.1-70b-instruct` | Balanced |
| `mixtral-8x22b` | `mistralai/mixtral-8x22b-instruct` | MoE |
| `phi-3-mini` | `microsoft/phi-3-mini-128k-instruct:free` | Free |

Get API key: https://openrouter.ai/keys

---

### Groq Client

Ultra-fast inference with a generous free tier (14,400 requests/day for smaller models).

```python
from tinman.integrations import GroqClient

client = GroqClient(
    api_key="gsk_...",  # Or set GROQ_API_KEY env var
)

# Use Llama 3.1 70B (very fast!)
tinman = await create_tinman(model_client=client)

# Specify model
response = await client.complete(
    messages=[{"role": "user", "content": "Hello"}],
    model="llama-3.1-70b",
)
```

**Available models:**

| Shorthand | Full Model ID | Context |
|-----------|---------------|---------|
| `llama-3.3-70b` | `llama-3.3-70b-versatile` | 128K |
| `llama-3.1-70b` | `llama-3.1-70b-versatile` | 128K |
| `llama-3.1-8b` | `llama-3.1-8b-instant` | 128K |
| `mixtral-8x7b` | `mixtral-8x7b-32768` | 32K |
| `gemma-2-9b` | `gemma2-9b-it` | 8K |

Get API key: https://console.groq.com/keys

---

### Ollama Client

Run models locally - completely free, no API keys needed, works offline.

```bash
# Install Ollama first: https://ollama.ai
ollama pull llama3.1
ollama pull qwen2.5
ollama pull deepseek-r1
```

```python
from tinman.integrations import OllamaClient

# No API key needed!
client = OllamaClient(
    base_url="http://localhost:11434/v1",  # Default
)

# Use local Llama
tinman = await create_tinman(model_client=client)

# Use Qwen
response = await client.complete(
    messages=[{"role": "user", "content": "Hello"}],
    model="qwen2.5",
)

# List locally available models
models = await client.list_local_models()
print(models)  # ['llama3.1', 'qwen2.5', ...]
```

**Popular Ollama models:**

| Model | Command | Size |
|-------|---------|------|
| Llama 3.1 | `ollama pull llama3.1` | 8B default |
| Qwen 2.5 | `ollama pull qwen2.5` | 7B default |
| DeepSeek R1 | `ollama pull deepseek-r1` | Various |
| DeepSeek Coder | `ollama pull deepseek-coder-v2` | 16B |
| Mistral | `ollama pull mistral` | 7B |
| Mixtral | `ollama pull mixtral` | 8x7B |
| CodeLlama | `ollama pull codellama` | 7B default |

---

### Together Client

Fast inference for open models with $25 free credits for new accounts.

```python
from tinman.integrations import TogetherClient

client = TogetherClient(
    api_key="...",  # Or set TOGETHER_API_KEY env var
)

# Use DeepSeek V3
tinman = await create_tinman(model_client=client)

response = await client.complete(
    messages=[{"role": "user", "content": "Hello"}],
    model="deepseek-v3",
)
```

**Available models:**

| Shorthand | Full Model ID |
|-----------|---------------|
| `deepseek-v3` | `deepseek-ai/DeepSeek-V3` |
| `deepseek-r1` | `deepseek-ai/DeepSeek-R1` |
| `llama-3.1-405b` | `meta-llama/Meta-Llama-3.1-405B-Instruct-Turbo` |
| `llama-3.1-70b` | `meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo` |
| `qwen-2.5-72b` | `Qwen/Qwen2.5-72B-Instruct-Turbo` |
| `mixtral-8x22b` | `mistralai/Mixtral-8x22B-Instruct-v0.1` |

Get API key: https://api.together.xyz

---

### Custom Model Client

Implement `ModelClient` for any LLM provider:

```python
from tinman.integrations.model_client import ModelClient, ModelResponse

class CustomClient(ModelClient):
    """Client for custom LLM endpoint."""

    def __init__(self, endpoint: str, api_key: str):
        super().__init__(api_key=api_key)
        self.endpoint = endpoint

    @property
    def provider(self) -> str:
        return "custom"

    async def complete(self,
                       messages: list[dict[str, str]],
                       model: Optional[str] = None,
                       temperature: float = 0.7,
                       max_tokens: int = 4096,
                       tools: Optional[list[dict]] = None,
                       **kwargs) -> ModelResponse:
        # Your implementation
        async with aiohttp.ClientSession() as session:
            response = await session.post(
                self.endpoint,
                json={
                    "messages": messages,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                },
                headers={"Authorization": f"Bearer {self.api_key}"}
            )
            data = await response.json()

        return ModelResponse(
            content=data["content"],
            model=data.get("model", "custom"),
            prompt_tokens=data.get("usage", {}).get("prompt_tokens", 0),
            completion_tokens=data.get("usage", {}).get("completion_tokens", 0),
            total_tokens=data.get("usage", {}).get("total_tokens", 0),
            tool_calls=data.get("tool_calls", []),
            finish_reason=data.get("finish_reason", ""),
            latency_ms=0,  # Calculate from timing
            raw=data,
        )

    async def stream(self, messages, **kwargs):
        # Your streaming implementation
        pass
```

---

## Embedding Tinman

### Full Tinman Instance

For complete research capabilities:

```python
from tinman import Tinman, create_tinman, OperatingMode
from tinman.integrations import OpenAIClient
from tinman.core.approval_handler import ApprovalMode

# Method 1: Factory function (recommended)
tinman = await create_tinman(
    mode=OperatingMode.LAB,
    model_client=OpenAIClient(),
    db_url="postgresql://localhost/tinman",
)

# Method 2: Manual initialization
tinman = Tinman(
    model_client=OpenAIClient(),
    mode=OperatingMode.LAB,
    approval_mode=ApprovalMode.AUTO_APPROVE,  # For automated systems
    auto_approve_in_lab=True,
)
await tinman.initialize(db_url="postgresql://localhost/tinman")
```

### Tinman Components

Use individual components for specific needs:

```python
from tinman.agents import (
    HypothesisEngine,
    ExperimentArchitect,
    ExperimentExecutor,
    FailureDiscoveryAgent,
)
from tinman.memory import MemoryGraph
from tinman.reasoning import LLMBackbone

# Just hypothesis generation
hypothesis_engine = HypothesisEngine(
    graph=your_graph,
    llm_backbone=your_llm,
)
hypotheses = await hypothesis_engine.run(context)

# Just failure classification
failure_discovery = FailureDiscoveryAgent(
    graph=your_graph,
    llm_backbone=your_llm,
)
failures = await failure_discovery.run(context, results=experiment_results)
```

### With Custom Approval Flow

```python
from tinman import Tinman
from tinman.core.approval_handler import ApprovalMode

# Create with interactive approvals
tinman = Tinman(
    model_client=client,
    approval_mode=ApprovalMode.INTERACTIVE,
    auto_approve_in_lab=False,  # Require all approvals
)

# Register custom UI callback
async def my_approval_ui(context):
    """Custom approval UI."""
    # Show in your UI
    approved = await show_approval_dialog(
        title=context.action_name,
        description=context.description,
        risk_tier=context.risk_tier,
    )
    return approved

tinman.register_approval_ui(my_approval_ui)
```

---

## Event System

Tinman uses an event bus for cross-component communication.

### Event Bus API

```python
from tinman.core.event_bus import EventBus

event_bus = EventBus()

# Subscribe to events
@event_bus.on("hypothesis.generated")
async def handle_hypothesis(data):
    print(f"New hypothesis: {data['target_surface']}")

# Or subscribe programmatically
def my_handler(data):
    log_event("hypothesis.generated", data)

event_bus.subscribe("hypothesis.generated", my_handler)

# Unsubscribe
event_bus.unsubscribe("hypothesis.generated", my_handler)
```

### Event Types

| Event | Data | Description |
|-------|------|-------------|
| `hypothesis.generated` | `{id, target_surface, failure_class}` | New hypothesis created |
| `experiment.designed` | `{id, hypothesis_id, stress_type}` | Experiment designed |
| `experiment.started` | `{id, total_runs}` | Experiment execution started |
| `experiment.completed` | `{id, failures_triggered}` | Experiment finished |
| `failure.discovered` | `{id, failure_class, severity}` | Failure identified |
| `intervention.proposed` | `{id, type, risk_tier}` | Intervention suggested |
| `intervention.deployed` | `{id, status}` | Intervention deployed |
| `simulation.completed` | `{id, outcome}` | Simulation finished |
| `approval.requested` | `{id, action, risk_tier}` | Approval needed |
| `approval.decided` | `{id, approved, reason}` | Approval decision made |
| `hook.blocked` | `{hook, point, message}` | Pipeline hook blocked |
| `hook.error` | `{hook, point, error}` | Pipeline hook error |

### Integration Example

```python
from tinman import create_tinman
from tinman.core.event_bus import EventBus

# Create shared event bus
event_bus = EventBus()

# Subscribe handlers
@event_bus.on("failure.discovered")
async def alert_on_failure(data):
    if data.get("severity") in ["S3", "S4"]:
        await pagerduty.create_incident(
            title=f"Critical AI Failure: {data['failure_class']}",
            severity="high",
            details=data,
        )

@event_bus.on("experiment.completed")
async def log_experiment(data):
    await metrics.record("tinman.experiments", 1, tags={
        "failures": data["failures_triggered"],
    })

# Use with Tinman
tinman = await create_tinman(mode=OperatingMode.LAB)
tinman.event_bus = event_bus
```

---

## Database Integration

Tinman uses PostgreSQL for persistent storage and SQLite for testing.

### PostgreSQL Setup

```bash
# Create database
createdb tinman

# Run migrations (handled automatically)
tinman init
```

```python
from tinman import create_tinman

tinman = await create_tinman(
    db_url="postgresql://user:pass@localhost:5432/tinman",
)
```

### Connection URL Format

```
postgresql://[user[:password]@][host][:port]/database[?options]
```

Examples:
```python
# Local development
db_url = "postgresql://localhost/tinman"

# With credentials
db_url = "postgresql://tinman_user:secret@localhost:5432/tinman"

# Remote server with SSL
db_url = "postgresql://user:pass@prod-db.example.com:5432/tinman?sslmode=require"

# SQLite for testing
db_url = "sqlite:///tinman.db"
db_url = "sqlite:///:memory:"  # In-memory
```

### Using DatabaseConnection Directly

```python
from tinman.db.connection import DatabaseConnection

# Create connection
db = DatabaseConnection("postgresql://localhost/tinman")
db.create_tables()

# Use session context manager
with db.session() as session:
    # Query operations
    results = session.execute(query).fetchall()

    # The session commits on exit
```

### Schema Migrations

Tinman handles schema migrations automatically. For manual control:

```python
from tinman.db.connection import DatabaseConnection

db = DatabaseConnection(db_url)

# Create all tables
db.create_tables()

# The memory graph schema includes:
# - nodes table (with temporal validity)
# - edges table (with relationships)
# - indexes for common queries
```

---

## CI/CD Integration

### GitHub Actions Example

```yaml
# .github/workflows/tinman-research.yml
name: AI Reliability Research

on:
  schedule:
    - cron: '0 0 * * *'  # Daily at midnight
  workflow_dispatch:
    inputs:
      focus:
        description: 'Research focus area'
        required: false
        default: 'general'

jobs:
  research:
    runs-on: ubuntu-latest

    services:
      postgres:
        image: postgres:15
        env:
          POSTGRES_DB: tinman
          POSTGRES_USER: postgres
          POSTGRES_PASSWORD: postgres
        ports:
          - 5432:5432
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5

    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          pip install tinman
          pip install pytest pytest-asyncio

      - name: Run research cycle
        env:
          OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
          DATABASE_URL: postgresql://postgres:postgres@localhost:5432/tinman
          TINMAN_MODE: lab
        run: |
          python -c "
          import asyncio
          from tinman import create_tinman, OperatingMode
          from tinman.integrations import OpenAIClient

          async def main():
              client = OpenAIClient()
              tinman = await create_tinman(
                  mode=OperatingMode.LAB,
                  model_client=client,
                  db_url='$DATABASE_URL',
              )

              results = await tinman.research_cycle(
                  focus='${{ github.event.inputs.focus || 'general' }}',
                  max_hypotheses=5,
              )

              # Generate report
              report = await tinman.generate_report()

              with open('research-report.md', 'w') as f:
                  f.write(report)

              await tinman.close()

              # Fail if critical issues found
              critical = [f for f in results['failures'] if f.get('severity') in ['S3', 'S4']]
              if critical:
                  print(f'Found {len(critical)} critical issues!')
                  exit(1)

          asyncio.run(main())
          "

      - name: Upload report
        uses: actions/upload-artifact@v4
        with:
          name: research-report
          path: research-report.md

      - name: Create issue on critical findings
        if: failure()
        uses: actions/github-script@v7
        with:
          script: |
            const fs = require('fs');
            const report = fs.readFileSync('research-report.md', 'utf8');

            await github.rest.issues.create({
              owner: context.repo.owner,
              repo: context.repo.repo,
              title: 'Critical AI Reliability Issues Found',
              body: report,
              labels: ['ai-reliability', 'critical']
            });
```

### Pre-commit Hook

```yaml
# .pre-commit-config.yaml
repos:
  - repo: local
    hooks:
      - id: tinman-check
        name: Tinman AI Safety Check
        entry: python -c "
          import asyncio
          from tinman import create_tinman
          from tinman.integrations import OpenAIClient

          async def check():
              tinman = await create_tinman(
                  model_client=OpenAIClient(),
                  skip_db=True,
              )
              # Quick sanity check
              results = await tinman.research_cycle(
                  max_hypotheses=2,
                  max_experiments=1,
              )
              critical = [f for f in results.get('failures', []) if f.get('severity') == 'S4']
              return len(critical) == 0

          if not asyncio.run(check()):
              exit(1)
          "
        language: python
        pass_filenames: false
        stages: [push]
```

---

## Framework Integration

### FastAPI Integration

```python
from fastapi import FastAPI, BackgroundTasks
from contextlib import asynccontextmanager
from tinman import create_tinman, OperatingMode
from tinman.integrations import OpenAIClient

# Global Tinman instance
tinman = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global tinman
    tinman = await create_tinman(
        mode=OperatingMode.SHADOW,
        model_client=OpenAIClient(),
        db_url="postgresql://localhost/tinman",
    )
    yield
    await tinman.close()

app = FastAPI(lifespan=lifespan)

@app.post("/api/llm/complete")
async def complete(request: CompletionRequest, background_tasks: BackgroundTasks):
    # Your normal completion logic
    response = await your_llm_call(request)

    # Background analysis with Tinman
    background_tasks.add_task(analyze_with_tinman, request, response)

    return response

async def analyze_with_tinman(request, response):
    """Run Tinman analysis in background."""
    from tinman.integrations import record_llm_interaction
    record_llm_interaction(
        adapter=tinman.pipeline_adapter,
        messages=request.messages,
        model=request.model,
        response_text=response.content,
    )

@app.get("/api/tinman/status")
async def tinman_status():
    return tinman.get_state()

@app.get("/api/tinman/report")
async def tinman_report():
    return await tinman.generate_report(format="json")

@app.post("/api/tinman/research")
async def start_research(focus: str = None):
    results = await tinman.research_cycle(focus=focus)
    return {"status": "complete", "findings": len(results["failures"])}
```

### LangChain Integration

```python
from tinman.integrations import TinmanLangChainCallbackHandler

# Usage
from langchain.llms import OpenAI

llm = OpenAI(callbacks=[TinmanLangChainCallbackHandler()])
response = llm.invoke("Your prompt here")
```

### CrewAI Integration

```python
from tinman.integrations import TinmanCrewHook

crew_hook = TinmanCrewHook()

# Wire into CrewAI task callbacks / events:
# crew_hook.on_task_start(task)
# crew_hook.on_task_end(task, output)
# crew_hook.on_task_error(task, error)
```

### Django Integration

```python
# settings.py
TINMAN_CONFIG = {
    "mode": "shadow",
    "db_url": "postgresql://localhost/tinman",
}

# services/tinman_service.py
import asyncio
from django.conf import settings
from tinman import create_tinman, OperatingMode
from tinman.integrations import OpenAIClient

class TinmanService:
    _instance = None
    _tinman = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    async def get_tinman(self):
        if self._tinman is None:
            config = settings.TINMAN_CONFIG
            self._tinman = await create_tinman(
                mode=OperatingMode(config["mode"]),
                model_client=OpenAIClient(),
                db_url=config["db_url"],
            )
        return self._tinman

    def run_research_sync(self, focus=None):
        """Synchronous wrapper for Django views."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            tinman = loop.run_until_complete(self.get_tinman())
            return loop.run_until_complete(
                tinman.research_cycle(focus=focus)
            )
        finally:
            loop.close()

# views.py
from django.http import JsonResponse
from .services.tinman_service import TinmanService

def tinman_status(request):
    service = TinmanService()
    loop = asyncio.new_event_loop()
    tinman = loop.run_until_complete(service.get_tinman())
    state = tinman.get_state()
    loop.close()
    return JsonResponse(state)
```

---

## Production Deployment

### Deployment Checklist

- [ ] **Database**: PostgreSQL with proper credentials and SSL
- [ ] **Secrets**: API keys in secure secret store (not environment variables)
- [ ] **Mode**: Start with SHADOW mode, graduate to PRODUCTION
- [ ] **Approval**: Configure HITL approval with proper timeouts
- [ ] **Monitoring**: Set up event handlers for alerting
- [ ] **Resources**: Adequate compute for LLM calls
- [ ] **Backups**: Regular database backups
- [ ] **Audit**: Enable audit logging

### Docker Deployment

```dockerfile
# Dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY . .

# Run Tinman
CMD ["python", "-m", "tinman.cli.main", "tui"]
```

```yaml
# docker-compose.yml
version: '3.8'

services:
  tinman:
    build: .
    environment:
      - OPENAI_API_KEY=${OPENAI_API_KEY}
      - DATABASE_URL=postgresql://postgres:postgres@db:5432/tinman
      - TINMAN_MODE=shadow
    depends_on:
      - db
    volumes:
      - ./reports:/app/reports

  db:
    image: postgres:15-alpine
    environment:
      - POSTGRES_DB=tinman
      - POSTGRES_USER=postgres
      - POSTGRES_PASSWORD=postgres
    volumes:
      - postgres_data:/var/lib/postgresql/data
    ports:
      - "5432:5432"

volumes:
  postgres_data:
```

### Kubernetes Deployment

```yaml
# k8s/deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: tinman
  labels:
    app: tinman
spec:
  replicas: 1
  selector:
    matchLabels:
      app: tinman
  template:
    metadata:
      labels:
        app: tinman
    spec:
      containers:
      - name: tinman
        image: your-registry/tinman:latest
        env:
        - name: OPENAI_API_KEY
          valueFrom:
            secretKeyRef:
              name: tinman-secrets
              key: openai-api-key
        - name: DATABASE_URL
          valueFrom:
            secretKeyRef:
              name: tinman-secrets
              key: database-url
        - name: TINMAN_MODE
          value: "shadow"
        resources:
          requests:
            memory: "512Mi"
            cpu: "500m"
          limits:
            memory: "2Gi"
            cpu: "2000m"
        volumeMounts:
        - name: reports
          mountPath: /app/reports
      volumes:
      - name: reports
        persistentVolumeClaim:
          claimName: tinman-reports-pvc
```

---

## Examples

### Complete Integration Example

```python
"""
Complete example: FastAPI service with Tinman integration.
"""
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import Optional

from tinman import create_tinman, OperatingMode
from tinman.integrations import OpenAIClient, PipelineAdapter, FailureDetectionHook
from tinman.core.event_bus import EventBus

# Models
class CompletionRequest(BaseModel):
    messages: list[dict]
    model: str = "gpt-4"
    temperature: float = 0.7

class ResearchRequest(BaseModel):
    focus: Optional[str] = None
    max_hypotheses: int = 5

# Global state
tinman = None
event_bus = EventBus()
adapter = None

# Event handlers
@event_bus.on("failure.discovered")
async def on_failure(data):
    print(f"ALERT: New failure discovered - {data['failure_class']}")
    # In production: send to monitoring system

@asynccontextmanager
async def lifespan(app: FastAPI):
    global tinman, adapter

    # Initialize Tinman
    client = OpenAIClient()
    tinman = await create_tinman(
        mode=OperatingMode.SHADOW,
        model_client=client,
        db_url="postgresql://localhost/tinman",
    )
    tinman.event_bus = event_bus

    # Initialize pipeline adapter
    adapter = PipelineAdapter(mode=OperatingMode.SHADOW)
    adapter.register_hook(FailureDetectionHook())

    yield

    await tinman.close()

app = FastAPI(
    title="AI Service with Tinman",
    lifespan=lifespan,
)

@app.post("/v1/completions")
async def create_completion(
    request: CompletionRequest,
    background_tasks: BackgroundTasks,
):
    """LLM completion endpoint with Tinman monitoring."""
    # Create pipeline context
    ctx = adapter.create_context(
        messages=request.messages,
        model=request.model,
    )

    # Pre-request hook
    ctx = await adapter.pre_request(ctx)

    # Your actual LLM call
    try:
        response = await tinman.model_client.complete(
            messages=request.messages,
            model=request.model,
            temperature=request.temperature,
        )
    except Exception as e:
        ctx.error = str(e)
        await adapter.on_error(ctx)
        raise HTTPException(status_code=500, detail=str(e))

    # Post-request hook
    ctx.response = {"content": response.content}
    ctx = await adapter.post_request(ctx)

    # Log any detected issues
    if "detected_failures" in ctx.metadata:
        background_tasks.add_task(
            log_potential_issues,
            ctx.metadata["detected_failures"],
            ctx.id,
        )

    return {
        "id": response.id,
        "content": response.content,
        "model": response.model,
        "usage": {
            "prompt_tokens": response.prompt_tokens,
            "completion_tokens": response.completion_tokens,
            "total_tokens": response.total_tokens,
        }
    }

async def log_potential_issues(issues: list, request_id: str):
    """Background task to log potential issues."""
    for issue in issues:
        print(f"[{request_id}] Potential issue detected: {issue}")

@app.post("/v1/research")
async def start_research(request: ResearchRequest):
    """Trigger a research cycle."""
    results = await tinman.research_cycle(
        focus=request.focus,
        max_hypotheses=request.max_hypotheses,
    )

    return {
        "hypotheses": len(results["hypotheses"]),
        "experiments": len(results["experiments"]),
        "failures": len(results["failures"]),
        "interventions": len(results["interventions"]),
    }

@app.get("/v1/tinman/status")
async def get_status():
    """Get Tinman status."""
    return tinman.get_state()

@app.get("/v1/tinman/report")
async def get_report(format: str = "markdown"):
    """Get research report."""
    report = await tinman.generate_report(format=format)
    return {"report": report}

@app.get("/v1/tinman/approvals/pending")
async def get_pending_approvals():
    """Get pending approval requests."""
    return tinman.get_pending_approvals()

@app.get("/health")
async def health():
    """Health check endpoint."""
    return await tinman.health_check()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

---

## Summary

Integration approaches by use case:

| Use Case | Pattern | Key Components |
|----------|---------|----------------|
| Custom app | Library import | `create_tinman()`, agents |
| Existing pipeline | Pipeline adapter | `PipelineAdapter`, hooks |
| Monitoring | Event-driven | `EventBus`, event handlers |
| CI/CD | CLI/automation | CLI commands, exit codes |
| Web service | Framework integration | FastAPI/Django patterns |

Key integration points:

| Component | Purpose |
|-----------|---------|
| `PipelineAdapter` | Hook into existing LLM calls |
| `ModelClient` | Unified interface for LLM providers |
| `EventBus` | Subscribe to Tinman events |
| `ApprovalHandler` | Custom approval UI integration |
| `MemoryGraph` | Query research findings |

---

## Next Steps

- [CONFIGURATION.md](CONFIGURATION.md) - Complete configuration reference
- [MODES.md](MODES.md) - Operating mode details
- [HITL.md](HITL.md) - Human-in-the-loop approval flow
- [AGENTS.md](AGENTS.md) - Individual agent documentation
