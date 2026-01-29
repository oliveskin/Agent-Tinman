"""LangChain integration helpers (optional dependency)."""

from __future__ import annotations

import asyncio
from typing import Any, Optional

from ..config.modes import OperatingMode
from .pipeline_adapter import PipelineAdapter, FailureDetectionHook, PipelineContext


def _run_async(coro: Any) -> None:
    """Run an async coroutine from a sync callback safely."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        asyncio.run(coro)
        return

    loop.create_task(coro)


def _response_text(response: Any) -> str:
    """Best-effort extraction of text from LangChain LLMResult."""
    generations = getattr(response, "generations", None) or []
    if generations and generations[0]:
        text = getattr(generations[0][0], "text", "")
        return text or ""
    return ""


def _load_base_callback_handler():
    """Import BaseCallbackHandler lazily to avoid hard dependency."""
    try:
        from langchain.callbacks.base import BaseCallbackHandler
    except Exception as exc:  # pragma: no cover - depends on optional package
        raise ImportError(
            "LangChain integration requires langchain. "
            "Install with: pip install langchain"
        ) from exc
    return BaseCallbackHandler


class TinmanLangChainCallbackHandler:  # intentionally not typed to avoid hard dependency
    """LangChain callback handler that emits Tinman pipeline events."""

    def __new__(cls, *args, **kwargs):  # pragma: no cover - constructor wrapper
        base = _load_base_callback_handler()
        if base not in cls.__mro__:
            cls.__bases__ = (base,)
        return super().__new__(cls)

    def __init__(self,
                 mode: OperatingMode = OperatingMode.SHADOW,
                 adapter: Optional[PipelineAdapter] = None):
        self.adapter = adapter or PipelineAdapter(mode=mode)
        self.adapter.register_hook(FailureDetectionHook())
        self._context: Optional[PipelineContext] = None

    def on_llm_start(self, serialized, prompts, **kwargs):  # type: ignore[override]
        messages = [{"role": "user", "content": p} for p in (prompts or [])]
        model = ""
        if isinstance(serialized, dict):
            model = serialized.get("name", "") or serialized.get("id", "")
        self._context = self.adapter.create_context(messages=messages, model=model)
        _run_async(self.adapter.pre_request(self._context))

    def on_llm_end(self, response, **kwargs):  # type: ignore[override]
        if not self._context:
            return
        self._context.response = {"content": _response_text(response)}
        _run_async(self.adapter.post_request(self._context))

    def on_llm_error(self, error, **kwargs):  # type: ignore[override]
        if not self._context:
            return
        self._context.error = str(error)
        _run_async(self.adapter.on_error(self._context))
