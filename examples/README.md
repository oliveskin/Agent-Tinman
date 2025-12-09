# Tinman Examples

Working code examples demonstrating Tinman capabilities.

## Examples

| Example | Description |
|---------|-------------|
| `basic_research.py` | Simple research cycle |
| `custom_hooks.py` | Pipeline adapter with custom hooks |
| `event_monitoring.py` | Event-driven monitoring |
| `conversation.py` | Interactive dialogue with Tinman |
| `fastapi_integration.py` | FastAPI service integration |

## Running Examples

1. **Set up environment:**

```bash
# Install Tinman
pip install tinman[all]

# Set API key
export OPENAI_API_KEY="sk-..."
# or
export ANTHROPIC_API_KEY="sk-ant-..."

# Set up database (for persistence examples)
createdb tinman
export DATABASE_URL="postgresql://localhost/tinman"
```

2. **Run an example:**

```bash
python examples/basic_research.py
```

## Prerequisites

- Python 3.11+
- PostgreSQL (optional, for persistence)
- An LLM API key (OpenAI or Anthropic)
