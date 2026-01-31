"""Pipeline adapter for integrating Tinman into existing systems."""

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from ..config.modes import OperatingMode
from ..utils import generate_id, get_logger, utc_now

logger = get_logger("pipeline_adapter")


class HookPoint(str, Enum):
    """Points where Tinman can hook into a pipeline."""

    PRE_REQUEST = "pre_request"  # Before model call
    POST_REQUEST = "post_request"  # After model call
    PRE_TOOL = "pre_tool"  # Before tool execution
    POST_TOOL = "post_tool"  # After tool execution
    ON_ERROR = "on_error"  # On any error
    ON_COMPLETION = "on_completion"  # On task completion


@dataclass
class PipelineContext:
    """Context passed through pipeline hooks."""

    id: str = field(default_factory=generate_id)
    mode: OperatingMode = OperatingMode.LAB

    # Request data
    messages: list[dict] = field(default_factory=list)
    model: str = ""
    tools: list[dict] = field(default_factory=list)

    # Response data (populated after request)
    response: dict | None = None
    error: str | None = None

    # Metadata
    metadata: dict[str, Any] = field(default_factory=dict)
    started_at: Any = field(default_factory=utc_now)


@dataclass
class HookResult:
    """Result from a pipeline hook."""

    allow: bool = True  # Whether to proceed
    modified_context: PipelineContext | None = None  # Modified context
    message: str = ""  # Optional message


class PipelineHook(ABC):
    """
    Abstract base class for pipeline hooks.

    Hooks can inspect and optionally modify pipeline execution.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Hook name for identification."""
        pass

    @property
    @abstractmethod
    def hook_points(self) -> list[HookPoint]:
        """Which hook points this hook handles."""
        pass

    @abstractmethod
    async def execute(self, hook_point: HookPoint, context: PipelineContext) -> HookResult:
        """Execute the hook at the given point."""
        pass


class PipelineAdapter:
    """
    Adapter for integrating Tinman into existing LLM pipelines.

    Provides hooks at key points to enable:
    - Request/response monitoring
    - Failure detection
    - Intervention injection
    - Shadow mode operation

    Usage:
        adapter = PipelineAdapter(mode=OperatingMode.SHADOW)
        adapter.register_hook(FailureDetectionHook())

        # In your pipeline
        ctx = adapter.create_context(messages=messages)
        ctx = await adapter.pre_request(ctx)

        response = await your_model_call(...)

        ctx.response = response
        ctx = await adapter.post_request(ctx)
    """

    def __init__(self, mode: OperatingMode = OperatingMode.LAB):
        self.mode = mode
        self._hooks: dict[HookPoint, list[PipelineHook]] = {point: [] for point in HookPoint}
        self._callbacks: dict[str, list[Callable]] = {}

    def register_hook(self, hook: PipelineHook) -> None:
        """Register a hook for execution."""
        for point in hook.hook_points:
            self._hooks[point].append(hook)
            logger.debug(f"Registered hook '{hook.name}' at {point.value}")

    def unregister_hook(self, hook_name: str) -> None:
        """Unregister a hook by name."""
        for point in HookPoint:
            self._hooks[point] = [h for h in self._hooks[point] if h.name != hook_name]

    def on(self, event: str, callback: Callable) -> None:
        """Register an event callback."""
        if event not in self._callbacks:
            self._callbacks[event] = []
        self._callbacks[event].append(callback)

    def create_context(self, **kwargs) -> PipelineContext:
        """Create a new pipeline context."""
        return PipelineContext(mode=self.mode, **kwargs)

    async def pre_request(self, context: PipelineContext) -> PipelineContext:
        """Execute pre-request hooks."""
        return await self._execute_hooks(HookPoint.PRE_REQUEST, context)

    async def post_request(self, context: PipelineContext) -> PipelineContext:
        """Execute post-request hooks."""
        return await self._execute_hooks(HookPoint.POST_REQUEST, context)

    async def pre_tool(self, context: PipelineContext) -> PipelineContext:
        """Execute pre-tool hooks."""
        return await self._execute_hooks(HookPoint.PRE_TOOL, context)

    async def post_tool(self, context: PipelineContext) -> PipelineContext:
        """Execute post-tool hooks."""
        return await self._execute_hooks(HookPoint.POST_TOOL, context)

    async def on_error(self, context: PipelineContext) -> PipelineContext:
        """Execute error hooks."""
        return await self._execute_hooks(HookPoint.ON_ERROR, context)

    async def on_completion(self, context: PipelineContext) -> PipelineContext:
        """Execute completion hooks."""
        return await self._execute_hooks(HookPoint.ON_COMPLETION, context)

    async def _execute_hooks(
        self, hook_point: HookPoint, context: PipelineContext
    ) -> PipelineContext:
        """Execute all hooks for a given point."""
        current_context = context

        for hook in self._hooks[hook_point]:
            try:
                result = await hook.execute(hook_point, current_context)

                if not result.allow:
                    logger.warning(f"Hook '{hook.name}' blocked execution: {result.message}")
                    self._emit(
                        "hook.blocked",
                        {
                            "hook": hook.name,
                            "point": hook_point.value,
                            "message": result.message,
                        },
                    )
                    # In SHADOW mode, log but continue
                    if self.mode != OperatingMode.SHADOW:
                        raise PipelineBlocked(hook.name, result.message)

                if result.modified_context:
                    current_context = result.modified_context

            except PipelineBlocked:
                raise
            except Exception as e:
                logger.error(f"Hook '{hook.name}' error: {e}")
                self._emit(
                    "hook.error",
                    {
                        "hook": hook.name,
                        "point": hook_point.value,
                        "error": str(e),
                    },
                )

        return current_context

    def _emit(self, event: str, data: dict) -> None:
        """Emit an event to callbacks."""
        for callback in self._callbacks.get(event, []):
            try:
                callback(data)
            except Exception as e:
                logger.error(f"Callback error for '{event}': {e}")


class PipelineBlocked(Exception):
    """Raised when a hook blocks pipeline execution."""

    def __init__(self, hook_name: str, message: str):
        self.hook_name = hook_name
        self.message = message
        super().__init__(f"Pipeline blocked by '{hook_name}': {message}")


# Built-in hooks


class LoggingHook(PipelineHook):
    """Simple logging hook for debugging."""

    @property
    def name(self) -> str:
        return "logging"

    @property
    def hook_points(self) -> list[HookPoint]:
        return list(HookPoint)

    async def execute(self, hook_point: HookPoint, context: PipelineContext) -> HookResult:
        logger.info(f"[{hook_point.value}] Context ID: {context.id}")
        return HookResult(allow=True)


class TokenLimitHook(PipelineHook):
    """Hook to enforce token limits."""

    def __init__(self, max_tokens: int = 100000):
        self.max_tokens = max_tokens

    @property
    def name(self) -> str:
        return "token_limit"

    @property
    def hook_points(self) -> list[HookPoint]:
        return [HookPoint.PRE_REQUEST]

    async def execute(self, hook_point: HookPoint, context: PipelineContext) -> HookResult:
        # Estimate token count (rough estimate)
        total_chars = sum(len(m.get("content", "")) for m in context.messages)
        estimated_tokens = total_chars // 4  # Rough estimate

        if estimated_tokens > self.max_tokens:
            return HookResult(
                allow=False,
                message=f"Estimated tokens ({estimated_tokens}) exceeds limit ({self.max_tokens})",
            )

        return HookResult(allow=True)


class FailureDetectionHook(PipelineHook):
    """Hook to detect failures in responses."""

    def __init__(self, failure_patterns: list[str] | None = None):
        self.failure_patterns = failure_patterns or [
            "error",
            "failed",
            "exception",
            "cannot",
            "unable",
        ]

    @property
    def name(self) -> str:
        return "failure_detection"

    @property
    def hook_points(self) -> list[HookPoint]:
        return [HookPoint.POST_REQUEST, HookPoint.POST_TOOL]

    async def execute(self, hook_point: HookPoint, context: PipelineContext) -> HookResult:
        if not context.response:
            return HookResult(allow=True)

        # Check response content for failure patterns
        content = str(context.response.get("content", "")).lower()

        detected = []
        for pattern in self.failure_patterns:
            if pattern in content:
                detected.append(pattern)

        if detected:
            context.metadata["detected_failures"] = detected
            logger.warning(f"Potential failures detected: {detected}")

        return HookResult(allow=True, modified_context=context)
