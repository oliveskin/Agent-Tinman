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
| `github_demo.py` | GitHub repo demo (issues + PRs) |
| `huggingface_demo.py` | Hugging Face Inference API demo |
| `replicate_demo.py` | Replicate API demo |
| `fal_demo.py` | fal.ai REST demo |
| `demo_runner.py` | One-command runner for provider demos |
| `demo_env_check.py` | Validate required env vars without running demos |

## Running Examples

1. **Set up environment:**

```bash
# Install Tinman
pip install AgentTinman[all]

# Set API key
export OPENAI_API_KEY="sk-..."
# or
export ANTHROPIC_API_KEY="sk-ant-..."
# or
export GEMINI_API_KEY="..."

# Set up database (for persistence examples)
createdb tinman
export DATABASE_URL="postgresql://localhost/tinman"
```

2. **Run an example:**

```bash
python examples/basic_research.py
```

## Provider Demo Keys

These demos call external APIs and require provider tokens:

```bash
export HUGGINGFACE_API_KEY="hf_..."
export REPLICATE_API_TOKEN="..."
export FAL_API_KEY="..."
export GITHUB_TOKEN="ghp_..."  # recommended to avoid rate limits
```

## Demo Runner

```bash
# Validate keys first
python -m tinman.demo.env_check all

# Run a demo
python -m tinman.demo.runner github -- --repo moltbot/moltbot
python -m tinman.demo.runner huggingface -- --model gpt2
python -m tinman.demo.runner replicate -- --version <MODEL_VERSION_ID>
python -m tinman.demo.runner fal -- --endpoint https://fal.run/fal-ai/fast-sdxl
```

## Prerequisites

- Python 3.11+
- PostgreSQL (optional, for persistence)
- An LLM API key (OpenAI or Anthropic)
