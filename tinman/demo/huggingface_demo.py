"""Hugging Face Inference API demo wired into Tinman PipelineAdapter."""

import argparse
import asyncio
import os
from typing import Any

import requests

from tinman.integrations.pipeline_adapter import PipelineAdapter, FailureDetectionHook
from tinman.config.modes import OperatingMode


def _require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def call_hf_inference(model: str, prompt: str, api_key: str) -> str:
    url = f"https://api-inference.huggingface.co/models/{model}"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json",
    }
    payload = {"inputs": prompt}
    resp = requests.post(url, headers=headers, json=payload, timeout=60)
    resp.raise_for_status()
    data: Any = resp.json()

    # HF typically returns a list of dicts with generated_text
    if isinstance(data, list) and data:
        first = data[0]
        if isinstance(first, dict) and "generated_text" in first:
            return str(first.get("generated_text", ""))

    if isinstance(data, dict):
        return str(data.get("generated_text", data))

    return str(data)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="gpt2")
    parser.add_argument("--prompt", default="Summarize the benefits of failure testing.")
    args = parser.parse_args()

    api_key = _require_env("HUGGINGFACE_API_KEY")

    adapter = PipelineAdapter(mode=OperatingMode.SHADOW)
    adapter.register_hook(FailureDetectionHook())

    ctx = adapter.create_context(
        messages=[{"role": "user", "content": args.prompt}],
        model=args.model,
    )

    asyncio.run(adapter.pre_request(ctx))

    response_text = call_hf_inference(args.model, args.prompt, api_key)

    ctx.response = {"content": response_text}
    asyncio.run(adapter.post_request(ctx))

    print("=== Hugging Face Response ===")
    print(response_text)

    if "detected_failures" in ctx.metadata:
        print("\nDetected potential issues:")
        print(ctx.metadata["detected_failures"])


if __name__ == "__main__":
    main()