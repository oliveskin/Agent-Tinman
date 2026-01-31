"""Replicate API demo wired into Tinman PipelineAdapter."""

import argparse
import asyncio
import os
import time
from typing import Any

import requests

from tinman.integrations.pipeline_adapter import PipelineAdapter, FailureDetectionHook
from tinman.config.modes import OperatingMode


API_BASE = "https://api.replicate.com/v1"


def _require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def _headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Token {token}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }


def create_prediction(version: str, prompt: str, token: str) -> dict[str, Any]:
    url = f"{API_BASE}/predictions"
    payload = {"version": version, "input": {"prompt": prompt}}
    resp = requests.post(url, headers=_headers(token), json=payload, timeout=60)
    resp.raise_for_status()
    return resp.json()


def poll_prediction(prediction_id: str, token: str, timeout_s: int = 120) -> dict[str, Any]:
    url = f"{API_BASE}/predictions/{prediction_id}"
    start = time.time()
    while time.time() - start < timeout_s:
        resp = requests.get(url, headers=_headers(token), timeout=30)
        resp.raise_for_status()
        data = resp.json()
        status = data.get("status")
        if status in {"succeeded", "failed", "canceled"}:
            return data
        time.sleep(2)
    raise TimeoutError("Prediction did not complete within timeout")


def _extract_output(data: dict[str, Any]) -> str:
    output = data.get("output")
    if isinstance(output, list):
        return "\n".join(str(x) for x in output)
    return str(output)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", required=True, help="Replicate model version id")
    parser.add_argument("--prompt", default="Summarize common agent failure modes.")
    args = parser.parse_args()

    token = _require_env("REPLICATE_API_TOKEN")

    adapter = PipelineAdapter(mode=OperatingMode.SHADOW)
    adapter.register_hook(FailureDetectionHook())

    ctx = adapter.create_context(
        messages=[{"role": "user", "content": args.prompt}],
        model=f"replicate:{args.version}",
    )

    asyncio.run(adapter.pre_request(ctx))

    created = create_prediction(args.version, args.prompt, token)
    final = poll_prediction(created["id"], token)

    response_text = _extract_output(final)
    ctx.response = {"content": response_text}
    asyncio.run(adapter.post_request(ctx))

    print("=== Replicate Response ===")
    print(response_text)

    if "detected_failures" in ctx.metadata:
        print("\nDetected potential issues:")
        print(ctx.metadata["detected_failures"])


if __name__ == "__main__":
    main()
