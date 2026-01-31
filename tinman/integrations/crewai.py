"""CrewAI integration helpers (optional dependency)."""

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


class TinmanCrewHook:
    """
    Minimal CrewAI hook that emits Tinman pipeline events.

    Wire these methods into CrewAI's task callbacks or event hooks.
    """

    def __init__(
        self, mode: OperatingMode = OperatingMode.SHADOW, adapter: Optional[PipelineAdapter] = None
    ):
        self.adapter = adapter or PipelineAdapter(mode=mode)
        self.adapter.register_hook(FailureDetectionHook())
        self._context: Optional[PipelineContext] = None

    def on_task_start(self, task: Any) -> None:
        description = getattr(task, "description", "") or str(task)
        messages = [{"role": "user", "content": description}]
        model = getattr(task, "model", "") or "crewai"
        self._context = self.adapter.create_context(messages=messages, model=model)
        _run_async(self.adapter.pre_request(self._context))

    def on_task_end(self, task: Any, output: Any) -> None:
        if not self._context:
            return
        content = getattr(output, "raw_output", "") or getattr(output, "output", "")
        self._context.response = {"content": str(content)}
        _run_async(self.adapter.post_request(self._context))

    def on_task_error(self, task: Any, error: Exception) -> None:
        if not self._context:
            return
        self._context.error = str(error)
        _run_async(self.adapter.on_error(self._context))
