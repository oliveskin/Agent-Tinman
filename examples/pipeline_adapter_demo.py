"""Test 2: PipelineAdapter wrapping a tiny tool+LLM agent in SHADOW mode."""

import argparse
import asyncio
from typing import Any
from pathlib import Path

import requests

from tinman.config import load_config
from tinman.config.modes import OperatingMode
from tinman.cli.main import get_db_session, get_model_client
from tinman.integrations.pipeline_adapter import PipelineAdapter, FailureDetectionHook
from tinman.tinman import create_tinman
from tinman.taxonomy.classifiers import FailureClassifier
from tinman.memory.models import Node, NodeType


def fetch_url(url: str) -> dict[str, Any]:
    """Minimal tool: fetch URL with forced error injection."""
    try:
        resp = requests.get(url, timeout=10)
        return {"ok": True, "status": resp.status_code, "text": resp.text[:1000]}
    except Exception as exc:
        return {"ok": False, "error": str(exc), "text": ""}


async def run(config_path: str | None, url: str, inject_failure: bool) -> None:
    settings = load_config() if not config_path else load_config(Path(config_path))
    settings.mode = OperatingMode.SHADOW

    model_client = get_model_client(settings)
    provider_settings = settings.models.providers.get(settings.models.default)
    if provider_settings and not provider_settings.api_key:
        model_client = None

    db = get_db_session(settings)
    db_url = settings.database_url if db else None
    skip_db = db is None

    tinman = await create_tinman(
        model_client=model_client,
        db_url=db_url,
        mode=settings.mode,
        skip_db=skip_db,
    )

    adapter = PipelineAdapter(mode=OperatingMode.SHADOW)
    adapter.register_hook(FailureDetectionHook())

    ctx = adapter.create_context(
        messages=[{"role": "user", "content": "Summarize the fetched content."}],
        model=settings.models.default,
        tools=[{"name": "fetch_url"}],
    )

    await adapter.pre_request(ctx)

    tool_result = fetch_url(url if not inject_failure else "http://invalid.invalid")
    trace = {
        "tool_calls": [{"name": "fetch_url", "status": "error" if not tool_result["ok"] else "ok"}],
        "errors": [tool_result["error"]] if not tool_result["ok"] else [],
        "retry_count": 4 if not tool_result["ok"] else 0,
    }

    if tool_result["ok"]:
        prompt = f"Summarize:\n{tool_result['text'][:4000]}"
    else:
        prompt = "Summarize: error"

    if model_client:
        response = await model_client.complete(
            messages=[{"role": "user", "content": prompt}],
            model=model_client.default_model,
        )
        response_text = response.content
    else:
        response_text = "error: no model client configured"

    ctx.response = {"content": response_text}
    ctx.metadata["trace"] = trace
    await adapter.post_request(ctx)

    classifier = FailureClassifier()
    classification = classifier.classify(
        output=ctx.response["content"],
        trace=trace,
        context=prompt,
    )

    if tinman.graph:
        run_node = Node(
            node_type=NodeType.RUN,
            data={
                "tool_calls": trace["tool_calls"],
                "errors": trace["errors"],
                "notes": "PipelineAdapter demo run",
            },
        )
        tinman.graph.add_node(run_node)
        tinman.graph.record_failure(
            run_id=run_node.id,
            primary_class=classification.primary_class.value,
            secondary_class=classification.secondary_class,
            severity=classification.suggested_severity,
            trigger_signature=classification.indicators_matched,
            reproducibility=1.0 if inject_failure else 0.0,
            description="Injected failure from pipeline adapter demo."
            if inject_failure
            else "No injected failure.",
            is_novel=True,
        )

    print("\n=== Pipeline Adapter Demo ===")
    print(f"Tool error injected: {inject_failure}")
    print(f"Detected failures: {ctx.metadata.get('detected_failures', [])}")
    print(f"Classification: {classification.primary_class.value}/{classification.secondary_class}")
    print(f"Indicators: {classification.indicators_matched}")

    await tinman.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=None)
    parser.add_argument("--url", default="https://example.com")
    parser.add_argument("--inject-failure", action="store_true")
    args = parser.parse_args()
    asyncio.run(run(args.config, args.url, args.inject_failure))


if __name__ == "__main__":
    main()
