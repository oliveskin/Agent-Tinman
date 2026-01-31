#!/usr/bin/env python3
"""
Custom Pipeline Hooks Example

Demonstrates creating custom hooks to integrate Tinman into
an existing LLM pipeline for monitoring and intervention.

Usage:
    export OPENAI_API_KEY="sk-..."
    python examples/custom_hooks.py
"""

import asyncio
import os
from typing import Optional

from tinman.integrations.pipeline_adapter import (
    PipelineAdapter,
    PipelineHook,
    PipelineContext,
    HookPoint,
    HookResult,
    FailureDetectionHook,
    TokenLimitHook,
)
from tinman.config.modes import OperatingMode
from tinman.integrations import OpenAIClient


class SafetyValidationHook(PipelineHook):
    """
    Custom hook to validate responses for safety concerns.

    Checks for potentially harmful patterns in model outputs.
    """

    def __init__(self, block_patterns: Optional[list[str]] = None):
        self.block_patterns = block_patterns or [
            "ignore all previous instructions",
            "system prompt",
            "jailbreak",
        ]
        self.warnings: list[dict] = []

    @property
    def name(self) -> str:
        return "safety_validation"

    @property
    def hook_points(self) -> list[HookPoint]:
        return [HookPoint.POST_REQUEST, HookPoint.POST_TOOL]

    async def execute(self, hook_point: HookPoint, context: PipelineContext) -> HookResult:
        """Check response for safety concerns."""
        if not context.response:
            return HookResult(allow=True)

        content = str(context.response.get("content", "")).lower()

        # Check for concerning patterns
        concerns = []
        for pattern in self.block_patterns:
            if pattern.lower() in content:
                concerns.append(pattern)

        if concerns:
            warning = {
                "context_id": context.id,
                "hook_point": hook_point.value,
                "patterns_detected": concerns,
            }
            self.warnings.append(warning)
            context.metadata["safety_concerns"] = concerns

            print(f"  [SAFETY WARNING] Detected patterns: {concerns}")

            # In SHADOW mode, log but don't block
            # In other modes, this would block the request
            return HookResult(
                allow=context.mode == OperatingMode.SHADOW,
                modified_context=context,
                message=f"Safety concerns detected: {concerns}",
            )

        return HookResult(allow=True)


class LatencyMonitoringHook(PipelineHook):
    """
    Custom hook to monitor request latency.

    Logs slow requests and tracks latency statistics.
    """

    def __init__(self, slow_threshold_ms: int = 5000):
        self.slow_threshold_ms = slow_threshold_ms
        self.latencies: list[int] = []

    @property
    def name(self) -> str:
        return "latency_monitoring"

    @property
    def hook_points(self) -> list[HookPoint]:
        return [HookPoint.POST_REQUEST]

    async def execute(self, hook_point: HookPoint, context: PipelineContext) -> HookResult:
        """Record and analyze latency."""
        from datetime import datetime

        # Calculate latency
        latency_ms = int((datetime.utcnow() - context.started_at).total_seconds() * 1000)
        self.latencies.append(latency_ms)

        context.metadata["latency_ms"] = latency_ms

        if latency_ms > self.slow_threshold_ms:
            print(f"  [SLOW REQUEST] {latency_ms}ms (threshold: {self.slow_threshold_ms}ms)")

        return HookResult(allow=True, modified_context=context)

    def get_stats(self) -> dict:
        """Get latency statistics."""
        if not self.latencies:
            return {"count": 0}

        return {
            "count": len(self.latencies),
            "min_ms": min(self.latencies),
            "max_ms": max(self.latencies),
            "avg_ms": sum(self.latencies) / len(self.latencies),
        }


class RequestLoggingHook(PipelineHook):
    """
    Custom hook to log all requests and responses.

    Useful for debugging and audit trails.
    """

    def __init__(self):
        self.logs: list[dict] = []

    @property
    def name(self) -> str:
        return "request_logging"

    @property
    def hook_points(self) -> list[HookPoint]:
        return [HookPoint.PRE_REQUEST, HookPoint.POST_REQUEST, HookPoint.ON_ERROR]

    async def execute(self, hook_point: HookPoint, context: PipelineContext) -> HookResult:
        """Log the request/response."""
        log_entry = {
            "context_id": context.id,
            "hook_point": hook_point.value,
            "model": context.model,
            "message_count": len(context.messages),
        }

        if hook_point == HookPoint.POST_REQUEST:
            log_entry["has_response"] = context.response is not None
            if context.response:
                content = context.response.get("content", "")
                log_entry["response_length"] = len(content)

        if hook_point == HookPoint.ON_ERROR:
            log_entry["error"] = context.error

        self.logs.append(log_entry)
        print(f"  [{hook_point.value.upper()}] Context: {context.id[:8]}...")

        return HookResult(allow=True)


async def simulate_llm_call(messages: list, model: str) -> dict:
    """Simulate an LLM call for demonstration."""
    await asyncio.sleep(0.1)  # Simulate latency

    # Simulate different response scenarios
    user_message = messages[-1].get("content", "") if messages else ""

    if "jailbreak" in user_message.lower():
        return {"content": "I cannot ignore all previous instructions..."}
    elif "slow" in user_message.lower():
        await asyncio.sleep(6)  # Trigger slow request warning
        return {"content": "This was a slow response."}
    else:
        return {"content": f"Here's my response to: {user_message[:50]}..."}


async def main():
    print("=" * 60)
    print("Custom Pipeline Hooks Example")
    print("=" * 60)

    # Create pipeline adapter in SHADOW mode
    # SHADOW mode logs issues but doesn't block requests
    adapter = PipelineAdapter(mode=OperatingMode.SHADOW)

    # Register built-in hooks
    adapter.register_hook(TokenLimitHook(max_tokens=50000))
    adapter.register_hook(FailureDetectionHook())

    # Register custom hooks
    safety_hook = SafetyValidationHook()
    latency_hook = LatencyMonitoringHook(slow_threshold_ms=5000)
    logging_hook = RequestLoggingHook()

    adapter.register_hook(safety_hook)
    adapter.register_hook(latency_hook)
    adapter.register_hook(logging_hook)

    # Register event callbacks
    blocked_events = []

    def on_blocked(data):
        blocked_events.append(data)
        print(f"  [BLOCKED EVENT] {data}")

    adapter.on("hook.blocked", on_blocked)

    print("\nRegistered hooks:")
    for hook_point in HookPoint:
        hooks = adapter._hooks[hook_point]
        if hooks:
            print(f"  {hook_point.value}: {[h.name for h in hooks]}")

    # Simulate several requests
    test_cases = [
        {"messages": [{"role": "user", "content": "Hello, how are you?"}]},
        {"messages": [{"role": "user", "content": "Tell me about Python"}]},
        {"messages": [{"role": "user", "content": "Try to jailbreak the system"}]},
        {"messages": [{"role": "user", "content": "This will be slow response"}]},
    ]

    print("\n" + "=" * 60)
    print("Running Test Requests")
    print("=" * 60)

    for i, test in enumerate(test_cases, 1):
        print(f"\n--- Request {i} ---")
        print(f"Input: {test['messages'][-1]['content'][:50]}...")

        # Create context
        ctx = adapter.create_context(
            messages=test["messages"],
            model="gpt-4",
        )

        # Pre-request hooks
        ctx = await adapter.pre_request(ctx)

        # Simulated LLM call
        response = await simulate_llm_call(ctx.messages, ctx.model)
        ctx.response = response

        # Post-request hooks
        ctx = await adapter.post_request(ctx)

        print(f"Output: {response['content'][:50]}...")

        # Check for issues detected
        if ctx.metadata.get("safety_concerns"):
            print(f"Safety concerns: {ctx.metadata['safety_concerns']}")
        if ctx.metadata.get("detected_failures"):
            print(f"Failures detected: {ctx.metadata['detected_failures']}")
        if ctx.metadata.get("latency_ms"):
            print(f"Latency: {ctx.metadata['latency_ms']}ms")

    # Summary statistics
    print("\n" + "=" * 60)
    print("Summary Statistics")
    print("=" * 60)

    print(f"\nLatency stats: {latency_hook.get_stats()}")
    print(f"Safety warnings: {len(safety_hook.warnings)}")
    print(f"Total logged events: {len(logging_hook.logs)}")
    print(f"Blocked events: {len(blocked_events)}")

    # Show safety warnings if any
    if safety_hook.warnings:
        print("\nSafety Warnings:")
        for warning in safety_hook.warnings:
            print(f"  - Context {warning['context_id'][:8]}: {warning['patterns_detected']}")


if __name__ == "__main__":
    asyncio.run(main())
