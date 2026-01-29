# Demos

Tinman ships with demo scripts under `examples/`.

## GitHub Demo

```bash
python -m tinman.demo.github_demo --repo moltbot/moltbot
```

## Hugging Face Demo

```bash
python -m tinman.demo.huggingface_demo --model gpt2
```

## Replicate Demo

```bash
python -m tinman.demo.replicate_demo --version <MODEL_VERSION_ID>
```

## fal.ai Demo

```bash
python -m tinman.demo.fal_demo --endpoint https://fal.run/fal-ai/fast-sdxl
```

## Demo Runner

```bash
python -m tinman.demo.env_check all
python -m tinman.demo.runner github -- --repo moltbot/moltbot
```

## Required Keys

```env
GITHUB_TOKEN=
HUGGINGFACE_API_KEY=
REPLICATE_API_TOKEN=
FAL_API_KEY=
```
