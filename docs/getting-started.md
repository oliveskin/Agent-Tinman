# Getting Started

## Install

```bash
pip install AgentTinman
```

## Initialize

```bash
python -m tinman.cli.main init
```

This creates:
- `.tinman/config.yaml`
- `.env` (template for provider keys)

If you are using PostgreSQL, initialize the database:

```bash
tinman db init
```

## Configure Providers

Edit `.env` and add your keys. Example:

```env
GEMINI_API_KEY=...
GITHUB_TOKEN=...
```

Update `.tinman/config.yaml` to pick a default model provider:

```yaml
models:
  default: google
  providers:
    google:
      api_key: ${GEMINI_API_KEY}
      model: gemini-2.5-flash
```

## Run a Research Cycle

```bash
tinman research --focus "tool use failures"
```

## Generate a Demo Report

```bash
tinman report --format demo
```

Exclude synthetic demo failures:

```bash
tinman report --format markdown --exclude-demo-failures
```

Reset the local SQLite demo database:

```bash
tinman demo-reset-db
```

## Launch the TUI

```bash
python -m tinman.cli.main tui
```
