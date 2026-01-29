# Demos

Tinman ships with demo scripts under `examples/`.

## GitHub Demo

```bash
python examples/github_demo.py --repo moltbot/moltbot
```

## Hugging Face Demo

```bash
python examples/huggingface_demo.py --model gpt2
```

## Replicate Demo

```bash
python examples/replicate_demo.py --version <MODEL_VERSION_ID>
```

## fal.ai Demo

```bash
python examples/fal_demo.py --endpoint https://fal.run/fal-ai/fast-sdxl
```

## Demo Runner

```bash
python examples/demo_env_check.py all
python examples/demo_runner.py github -- --repo moltbot/moltbot
```

## Required Keys

```env
GITHUB_TOKEN=
HUGGINGFACE_API_KEY=
REPLICATE_API_TOKEN=
FAL_API_KEY=
```