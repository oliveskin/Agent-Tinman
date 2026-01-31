#!/usr/bin/env python
"""fal.ai REST demo wired into Tinman PipelineAdapter."""

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


def call_fal(endpoint: str, prompt: str, api_key: str) -> dict[str, Any]:
    headers = {
        "Authorization": f"Key {api_key}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    payload = {"prompt": prompt}
    resp = requests.post(endpoint, headers=headers, json=payload, timeout=60)
    resp.raise_for_status()
    data = resp.json()
    return data if isinstance(data, dict) else {"output": data}


def _extract_output(data: dict[str, Any]) -> str:
    output = data.get("output", data)
    if isinstance(output, list):
        return "\n".join(str(x) for x in output)
    return str(output)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--endpoint",
        default="https://fal.run/fal-ai/fast-sdxl",
        help="fal.ai model endpoint URL",
    )
    parser.add_argument("--prompt", default="Generate a short summary of AI safety risks.")
    args = parser.parse_args()

    api_key = _require_env("FAL_API_KEY")

    adapter = PipelineAdapter(mode=OperatingMode.SHADOW)
    adapter.register_hook(FailureDetectionHook())

    ctx = adapter.create_context(
        messages=[{"role": "user", "content": args.prompt}],
        model=f"fal:{args.endpoint}",
    )

    asyncio.run(adapter.pre_request(ctx))

    response_json = call_fal(args.endpoint, args.prompt, api_key)
    response_text = _extract_output(response_json)

    ctx.response = {"content": response_text}
    asyncio.run(adapter.post_request(ctx))

    print("=== fal.ai Response ===")
    print(response_text)

    if "detected_failures" in ctx.metadata:
        print("\nDetected potential issues:")
        print(ctx.metadata["detected_failures"])


if __name__ == "__main__":
    main()
