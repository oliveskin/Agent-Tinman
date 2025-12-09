# Contributing to Tinman

Thank you for your interest in contributing to Tinman! This guide covers everything you need to know to contribute effectively.

---

## Table of Contents

1. [Code of Conduct](#code-of-conduct)
2. [Getting Started](#getting-started)
3. [Development Setup](#development-setup)
4. [Project Structure](#project-structure)
5. [Code Style](#code-style)
6. [Testing](#testing)
7. [Pull Request Process](#pull-request-process)
8. [Architecture Guidelines](#architecture-guidelines)
9. [Adding Features](#adding-features)
10. [Documentation](#documentation)
11. [Release Process](#release-process)

---

## Code of Conduct

This project is a public good, free and open source. We expect all contributors to:

- Be respectful and inclusive
- Focus on constructive feedback
- Prioritize safety and reliability
- Help maintain code quality

---

## Getting Started

### Prerequisites

- Python 3.11+
- PostgreSQL 14+ (for production) or SQLite (for testing)
- Git
- An LLM API key (OpenAI or Anthropic)

### Quick Start for Contributors

```bash
# Fork and clone
git clone https://github.com/YOUR_USERNAME/agent_tinman.git
cd agent_tinman

# Set up development environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install with all dependencies
pip install -e ".[dev,all]"

# Set up database
createdb tinman

# Run tests to verify setup
pytest

# Set API keys (for integration testing)
export OPENAI_API_KEY="sk-..."
# or
export ANTHROPIC_API_KEY="sk-ant-..."
```

---

## Development Setup

### 1. Clone and Install

```bash
git clone https://github.com/oliveskin/agent_tinman.git
cd agent_tinman

python -m venv .venv
source .venv/bin/activate

# Install in editable mode with dev dependencies
pip install -e ".[dev,all]"
```

### 2. Database Setup

**PostgreSQL (Recommended for Development):**

```bash
# Create database
createdb tinman

# Connection URL
export DATABASE_URL="postgresql://localhost/tinman"
```

**SQLite (Quick Testing):**

```bash
export DATABASE_URL="sqlite:///tinman.db"
```

### 3. Environment Variables

Create a `.env` file (not committed to git):

```bash
# .env
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
DATABASE_URL=postgresql://localhost/tinman
TINMAN_MODE=lab
```

Load with:
```bash
source .env
# or use python-dotenv
```

### 4. IDE Setup

**VS Code:**
```json
// .vscode/settings.json
{
    "python.defaultInterpreterPath": ".venv/bin/python",
    "python.linting.enabled": true,
    "python.linting.ruffEnabled": true,
    "python.formatting.provider": "none",
    "[python]": {
        "editor.formatOnSave": true,
        "editor.defaultFormatter": "charliermarsh.ruff"
    }
}
```

**PyCharm:**
- Set interpreter to `.venv/bin/python`
- Enable Ruff plugin for linting
- Configure pytest as test runner

---

## Project Structure

```
tinman/
├── __init__.py          # Public API exports
├── tinman.py            # Main Tinman class
│
├── agents/              # Autonomous agents
│   ├── base.py          # BaseAgent abstract class
│   ├── hypothesis_engine.py
│   ├── experiment_architect.py
│   ├── experiment_executor.py
│   ├── failure_discovery.py
│   ├── intervention_engine.py
│   └── simulation_engine.py
│
├── config/              # Configuration
│   ├── modes.py         # Operating modes (LAB/SHADOW/PRODUCTION)
│   └── settings.py      # Settings management
│
├── core/                # Core components
│   ├── approval_handler.py  # HITL approval flow
│   ├── event_bus.py     # Event system
│   └── risk_evaluator.py    # Risk assessment
│
├── memory/              # Knowledge graph
│   ├── graph.py         # MemoryGraph implementation
│   └── models.py        # Node/Edge types
│
├── reasoning/           # LLM backbone
│   ├── llm_backbone.py  # LLM interface
│   ├── adaptive_memory.py   # Learning patterns
│   └── insight_synthesizer.py
│
├── taxonomy/            # Failure classification
│   ├── failure_types.py # FailureClass, Severity
│   └── classifiers.py   # Classification logic
│
├── integrations/        # External integrations
│   ├── model_client.py  # Abstract client
│   ├── openai_client.py
│   ├── anthropic_client.py
│   └── pipeline_adapter.py
│
├── reporting/           # Report generation
│   ├── lab_reporter.py
│   └── ops_reporter.py
│
├── db/                  # Database layer
│   └── connection.py
│
├── cli/                 # CLI interface
│   ├── main.py          # Click commands
│   └── tui.py           # Terminal UI
│
└── utils/               # Utilities
    └── __init__.py

tests/
├── conftest.py          # Pytest fixtures
├── test_agents.py
├── test_approval_flow.py
├── test_config.py
├── test_memory.py
└── test_taxonomy.py

docs/
├── CONCEPTS.md
├── ARCHITECTURE.md
├── QUICKSTART.md
├── TAXONOMY.md
├── MODES.md
├── HITL.md
├── AGENTS.md
├── CONFIGURATION.md
├── MEMORY.md
└── INTEGRATION.md
```

---

## Code Style

### Linting with Ruff

We use Ruff for linting and formatting:

```bash
# Check for issues
ruff check .

# Auto-fix issues
ruff check --fix .

# Format code
ruff format .
```

### Ruff Configuration

From `pyproject.toml`:

```toml
[tool.ruff]
target-version = "py311"
line-length = 100

[tool.ruff.lint]
select = [
    "E",   # pycodestyle errors
    "W",   # pycodestyle warnings
    "F",   # pyflakes
    "I",   # isort
    "B",   # flake8-bugbear
    "C4",  # flake8-comprehensions
    "UP",  # pyupgrade
]
```

### Type Checking with Mypy

```bash
mypy tinman
```

Configuration:
```toml
[tool.mypy]
python_version = "3.11"
strict = true
warn_return_any = true
warn_unused_ignores = true
```

### Style Guidelines

**General:**
- Line length: 100 characters max
- Use type hints for all function signatures
- Use dataclasses for data structures
- Prefer composition over inheritance
- Keep functions focused and small

**Imports:**
```python
# Standard library
import asyncio
from dataclasses import dataclass
from typing import Optional

# Third-party
import structlog

# Local
from tinman.agents.base import BaseAgent
from tinman.config.modes import OperatingMode
```

**Naming:**
```python
# Classes: PascalCase
class HypothesisEngine:
    pass

# Functions/methods: snake_case
async def generate_hypotheses(self) -> list[Hypothesis]:
    pass

# Constants: UPPER_SNAKE_CASE
DEFAULT_MAX_HYPOTHESES = 10

# Private: leading underscore
def _internal_helper(self):
    pass
```

**Docstrings:**
```python
async def research_cycle(
    self,
    focus: Optional[str] = None,
    max_hypotheses: int = 5,
) -> dict[str, Any]:
    """
    Run a complete research cycle.

    This is the core loop:
    1. Generate hypotheses
    2. Design experiments
    3. Execute experiments
    4. Discover failures
    5. Propose interventions

    Args:
        focus: Optional focus area for research
        max_hypotheses: Maximum hypotheses to generate

    Returns:
        Dictionary with research results
    """
```

---

## Testing

### Running Tests

```bash
# All tests
pytest

# With coverage
pytest --cov=tinman

# Specific test file
pytest tests/test_agents.py

# Specific test
pytest tests/test_agents.py::test_hypothesis_generation

# Verbose output
pytest -v

# Stop on first failure
pytest -x
```

### Test Configuration

From `pyproject.toml`:

```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
addopts = "-v --tb=short"
```

### Writing Tests

**Use Fixtures:**

```python
# tests/conftest.py
import pytest
from tinman.config.modes import OperatingMode
from tinman.agents.base import AgentContext

@pytest.fixture
def lab_context():
    """Create a LAB mode agent context."""
    return AgentContext(mode=OperatingMode.LAB)

@pytest.fixture
def shadow_context():
    """Create a SHADOW mode agent context."""
    return AgentContext(mode=OperatingMode.SHADOW)

@pytest.fixture
def production_context():
    """Create a PRODUCTION mode agent context."""
    return AgentContext(mode=OperatingMode.PRODUCTION)
```

**Async Tests:**

```python
import pytest

@pytest.mark.asyncio
async def test_hypothesis_generation(lab_context):
    """Test that hypothesis engine generates valid hypotheses."""
    engine = HypothesisEngine(graph=None, llm_backbone=mock_llm)
    result = await engine.run(lab_context)

    assert result.success
    assert "hypotheses" in result.data
    assert len(result.data["hypotheses"]) > 0
```

**Mode-Aware Tests:**

```python
@pytest.mark.asyncio
async def test_destructive_blocked_in_shadow(shadow_context):
    """Verify destructive experiments blocked in SHADOW mode."""
    executor = ExperimentExecutor(graph=None, mode=shadow_context.mode)

    with pytest.raises(ModeRestrictionError):
        await executor.run_destructive_test(shadow_context)
```

**Approval Flow Tests:**

```python
@pytest.mark.asyncio
async def test_approval_required_in_production(production_context):
    """Test that production mode requires approval."""
    handler = ApprovalHandler(
        mode=Mode.PRODUCTION,
        approval_mode=ApprovalMode.INTERACTIVE,
    )

    # Mock the approval callback
    handler.register_ui(lambda ctx: asyncio.create_task(async_approve()))

    result = await handler.request_approval(
        action_type=ActionType.INTERVENTION_DEPLOY,
        context=production_context,
    )

    assert result.required_approval is True
```

### Test Categories

| Category | Location | Description |
|----------|----------|-------------|
| Unit | `tests/test_*.py` | Individual component tests |
| Integration | `tests/integration/` | Cross-component tests |
| Approval | `tests/test_approval_flow.py` | HITL flow tests |
| Memory | `tests/test_memory.py` | Graph operations |

---

## Pull Request Process

### 1. Create a Branch

```bash
# Update main
git checkout main
git pull origin main

# Create feature branch
git checkout -b feature/amazing-feature
# or
git checkout -b fix/bug-description
```

### 2. Make Changes

- Keep commits focused and atomic
- Write descriptive commit messages
- Follow code style guidelines
- Add tests for new functionality

### 3. Run Quality Checks

```bash
# Format code
ruff format .

# Lint
ruff check .

# Type check
mypy tinman

# Run tests
pytest

# All at once
ruff format . && ruff check . && mypy tinman && pytest
```

### 4. Push and Create PR

```bash
git push -u origin feature/amazing-feature
```

Then open a PR on GitHub with:

- **Title:** Clear, descriptive title
- **Description:** What changes, why, any context
- **Tests:** Description of how it was tested
- **Breaking changes:** Note any API changes

### 5. PR Review Checklist

- [ ] Code follows style guidelines
- [ ] Tests pass
- [ ] Type checking passes
- [ ] Documentation updated (if needed)
- [ ] No breaking changes (or documented)
- [ ] Respects operating mode restrictions
- [ ] HITL approval flow maintained

---

## Architecture Guidelines

### Core Principles

1. **Mode-Aware Behavior**
   - Always check operating mode before destructive actions
   - Respect approval requirements per mode
   - Use `AgentContext.mode` to determine behavior

2. **Event-Driven Communication**
   - Use `EventBus` for cross-component communication
   - Emit events for significant actions
   - Don't create tight coupling between components

3. **Temporal Memory**
   - All graph nodes have validity periods
   - Use `valid_from` and `valid_until` for versioning
   - Query with `snapshot_at()` for point-in-time views

4. **Approval Flow**
   - Route approval requests through `ApprovalHandler`
   - Respect risk tier classifications
   - Never bypass HITL in PRODUCTION mode

### Anti-Patterns to Avoid

| Anti-Pattern | Why Bad | Better Approach |
|--------------|---------|-----------------|
| Direct mode checks | Scattered logic | Use `mode.allows_destructive_testing` |
| Tight agent coupling | Hard to test | Use event bus |
| Skipping approval | Safety risk | Route through handler |
| Hardcoded thresholds | Not configurable | Use settings |
| Mutable shared state | Race conditions | Use dataclasses |

---

## Adding Features

### Adding a New Agent

1. **Create the agent file:**

```python
# tinman/agents/my_agent.py
from dataclasses import dataclass
from typing import Any

from .base import BaseAgent, AgentContext, AgentResult
from ..utils import get_logger

logger = get_logger("my_agent")

@dataclass
class MyOutput:
    """Output from MyAgent."""
    results: list[dict]

class MyAgent(BaseAgent):
    """
    Description of what this agent does.

    Purpose:
    - Point 1
    - Point 2
    """

    @property
    def agent_type(self) -> str:
        return "my_agent"

    async def execute(
        self,
        context: AgentContext,
        **kwargs,
    ) -> AgentResult:
        """Execute the agent logic."""
        logger.info(f"Running in {context.mode.value} mode")

        # Your logic here
        results = await self._do_work(context, **kwargs)

        return AgentResult(
            agent_id=self.id,
            agent_type=self.agent_type,
            success=True,
            data={"results": results},
        )

    async def _do_work(self, context: AgentContext, **kwargs) -> list:
        """Internal implementation."""
        # Mode-aware behavior
        if context.mode == OperatingMode.PRODUCTION:
            # More conservative in production
            pass

        return []
```

2. **Add exports:**

```python
# tinman/agents/__init__.py
from .my_agent import MyAgent, MyOutput
```

3. **Add tests:**

```python
# tests/test_my_agent.py
import pytest
from tinman.agents.my_agent import MyAgent

@pytest.mark.asyncio
async def test_my_agent_basic(lab_context):
    agent = MyAgent()
    result = await agent.run(lab_context)

    assert result.success
    assert "results" in result.data
```

### Adding a New Failure Class

1. **Update taxonomy:**

```python
# tinman/taxonomy/failure_types.py
class FailureClass(str, Enum):
    # ... existing
    MY_NEW_CLASS = "my_new_class"
```

2. **Add subtypes:**

```python
FailureTaxonomy.register_failure_type(
    failure_class=FailureClass.MY_NEW_CLASS,
    subtype="specific_failure",
    description="What this failure means",
    indicators=["pattern1", "pattern2"],
    mitigation_hints=["hint1", "hint2"],
)
```

3. **Update documentation:**
   - Add to `docs/TAXONOMY.md`

### Adding Configuration Options

1. **Update settings:**

```python
# tinman/config/settings.py
@dataclass
class Settings:
    # ... existing
    my_new_option: str = "default_value"
```

2. **Update config loading:**

```python
def load_settings(path: Path) -> Settings:
    # Handle new option
```

3. **Document in `docs/CONFIGURATION.md`**

---

## Documentation

### Documentation Structure

| File | Purpose |
|------|---------|
| `README.md` | Project overview, quickstart |
| `docs/CONCEPTS.md` | Core concepts, mental model |
| `docs/ARCHITECTURE.md` | System architecture |
| `docs/QUICKSTART.md` | Getting started guide |
| `docs/TAXONOMY.md` | Failure classification |
| `docs/MODES.md` | Operating modes |
| `docs/HITL.md` | Human-in-the-loop |
| `docs/AGENTS.md` | Agent reference |
| `docs/CONFIGURATION.md` | Settings reference |
| `docs/MEMORY.md` | Memory graph |
| `docs/INTEGRATION.md` | Integration guide |

### Writing Documentation

- Use clear, concise language
- Include code examples
- Add diagrams where helpful
- Keep examples working and tested
- Cross-reference related docs

### Docstring Standards

```python
def my_function(param1: str, param2: int = 10) -> dict[str, Any]:
    """
    Brief one-line description.

    Longer description if needed. Can span multiple lines
    and include details about the function's purpose.

    Args:
        param1: Description of param1
        param2: Description of param2

    Returns:
        Description of return value

    Raises:
        ValueError: When param1 is empty
        RuntimeError: When something fails

    Example:
        >>> result = my_function("test", 5)
        >>> print(result["key"])
        value
    """
```

---

## Release Process

### Version Numbering

We follow [Semantic Versioning](https://semver.org/):

- **MAJOR.MINOR.PATCH** (e.g., `0.1.0`)
- **MAJOR**: Breaking API changes
- **MINOR**: New features, backward compatible
- **PATCH**: Bug fixes, backward compatible

### Creating a Release

1. **Update version:**

```python
# tinman/__init__.py
__version__ = "0.2.0"
```

```toml
# pyproject.toml
version = "0.2.0"
```

2. **Update CHANGELOG:**

```markdown
## [0.2.0] - 2024-XX-XX

### Added
- New feature X
- New agent Y

### Changed
- Improved Z

### Fixed
- Bug in W
```

3. **Create release PR:**

```bash
git checkout -b release/0.2.0
# Make version changes
git commit -m "Release 0.2.0"
git push -u origin release/0.2.0
```

4. **After merge, tag release:**

```bash
git checkout main
git pull
git tag v0.2.0
git push origin v0.2.0
```

---

## Questions?

- **Bug reports:** [Open an issue](https://github.com/oliveskin/agent_tinman/issues)
- **Feature requests:** [Open a discussion](https://github.com/oliveskin/agent_tinman/discussions)
- **Security issues:** Email maintainers directly

Thank you for contributing to Tinman!
