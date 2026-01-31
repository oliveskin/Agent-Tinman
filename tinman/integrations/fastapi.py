"""FastAPI integration helpers (optional dependency)."""

from __future__ import annotations

import asyncio
from typing import Any

from ..config.modes import OperatingMode
from .pipeline_adapter import FailureDetectionHook, PipelineAdapter, PipelineContext


def _run_async(coro: Any) -> None:
    """Run an async coroutine from a sync context safely."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        asyncio.run(coro)
        return

    loop.create_task(coro)


def record_llm_interaction(
    adapter: PipelineAdapter,
    messages: list[dict[str, str]],
    model: str,
    response_text: str,
    error: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> PipelineContext:
    """
    Record a single LLM interaction via the PipelineAdapter.

    This is a lightweight helper for FastAPI handlers where you already
    have request/response objects and want Tinman to observe them.
    """
    ctx = adapter.create_context(messages=messages, model=model)
    if metadata:
        ctx.metadata.update(metadata)
    if error:
        ctx.error = error
        _run_async(adapter.on_error(ctx))
        return ctx
    ctx.response = {"content": response_text}
    _run_async(adapter.post_request(ctx))
    return ctx


def create_fastapi_adapter(
    mode: OperatingMode = OperatingMode.SHADOW,
) -> PipelineAdapter:
    """Create a PipelineAdapter with default hooks for FastAPI usage."""
    adapter = PipelineAdapter(mode=mode)
    adapter.register_hook(FailureDetectionHook())
    return adapter
