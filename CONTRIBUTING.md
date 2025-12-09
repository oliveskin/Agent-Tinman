# Contributing to Tinman

Thank you for your interest in contributing to Tinman.

## Development Setup

1. Clone the repository:

```sh
git clone https://github.com/oliveskin/agent_tinman.git
cd agent_tinman
```

2. Create a virtual environment:

```sh
python -m venv .venv
source .venv/bin/activate  # or `.venv\Scripts\activate` on Windows
```

3. Install development dependencies:

```sh
pip install -e ".[dev]"
```

4. Set up PostgreSQL (required for memory graph):

```sh
createdb tinman
```

## Running Tests

```sh
pytest
```

With coverage:

```sh
pytest --cov=tinman
```

## Code Style

We use ruff for linting and formatting:

```sh
ruff check .
ruff format .
```

Type checking with mypy:

```sh
mypy tinman
```

## Pull Request Process

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes
4. Run tests and linting
5. Commit with descriptive message
6. Push and open a PR

## Architecture Guidelines

- Keep agents focused and single-purpose
- Use the event bus for cross-component communication
- Record all significant events to the memory graph
- Maintain temporal versioning for all graph nodes
- Respect operating mode restrictions

## Adding New Agents

1. Extend `BaseAgent` in `tinman/agents/base.py`
2. Implement `agent_type` property and `execute` method
3. Use `AgentContext` for mode-aware behavior
4. Return `AgentResult` with structured data
5. Add tests in `tests/agents/`

Example:

```python
class MyAgent(BaseAgent):
    @property
    def agent_type(self) -> str:
        return "my_agent"

    async def execute(self, context: AgentContext, **kwargs) -> AgentResult:
        # Your logic here
        return AgentResult(
            agent_id=self.id,
            agent_type=self.agent_type,
            success=True,
            data={"result": "data"},
        )
```

## Questions?

Open an issue or start a discussion.
