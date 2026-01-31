#!/usr/bin/env python3
"""
FastAPI Integration Example

Demonstrates integrating Tinman into a FastAPI web service
for production AI reliability monitoring.

Usage:
    pip install fastapi uvicorn
    export OPENAI_API_KEY="sk-..."
    python examples/fastapi_integration.py

Then visit:
    http://localhost:8000/docs - API documentation
    http://localhost:8000/health - Health check
"""

import asyncio
import os
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional

# FastAPI imports
try:
    from fastapi import FastAPI, HTTPException, BackgroundTasks
    from fastapi.responses import JSONResponse
    from pydantic import BaseModel
except ImportError:
    print("This example requires FastAPI:")
    print("  pip install fastapi uvicorn")
    exit(1)

from tinman import create_tinman, OperatingMode
from tinman.integrations import OpenAIClient, PipelineAdapter, FailureDetectionHook
from tinman.core.event_bus import EventBus


# --- Pydantic Models ---


class CompletionRequest(BaseModel):
    """LLM completion request."""

    messages: list[dict]
    model: str = "gpt-4"
    temperature: float = 0.7
    max_tokens: int = 4096


class CompletionResponse(BaseModel):
    """LLM completion response."""

    id: str
    content: str
    model: str
    usage: dict


class ResearchRequest(BaseModel):
    """Research cycle request."""

    focus: Optional[str] = None
    max_hypotheses: int = 5
    max_experiments: int = 3


class ResearchResponse(BaseModel):
    """Research cycle response."""

    hypotheses: int
    experiments: int
    failures: int
    interventions: int


# --- Global State ---

tinman = None
event_bus = EventBus()
adapter = None
research_stats = {
    "cycles_run": 0,
    "total_failures": 0,
    "last_run": None,
}


# --- Event Handlers ---


@event_bus.on("failure.discovered")
async def on_failure(data):
    """Track discovered failures."""
    research_stats["total_failures"] += 1
    print(f"[EVENT] Failure discovered: {data.get('failure_class')}")


# --- Lifespan Management ---


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage Tinman lifecycle."""
    global tinman, adapter

    print("Starting Tinman service...")

    # Initialize model client
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("Warning: OPENAI_API_KEY not set, some features disabled")
        client = None
    else:
        client = OpenAIClient(api_key=api_key)

    # Initialize Tinman
    tinman = await create_tinman(
        mode=OperatingMode.SHADOW,  # SHADOW mode for production monitoring
        model_client=client,
        skip_db=True,  # Set False and add db_url for persistence
    )
    tinman.event_bus = event_bus

    # Initialize pipeline adapter
    adapter = PipelineAdapter(mode=OperatingMode.SHADOW)
    adapter.register_hook(FailureDetectionHook())

    print("Tinman ready!")

    yield

    # Cleanup
    print("Shutting down Tinman...")
    await tinman.close()


# --- FastAPI App ---

app = FastAPI(
    title="AI Service with Tinman",
    description="Example FastAPI service with Tinman reliability monitoring",
    version="0.1.0",
    lifespan=lifespan,
)


# --- Endpoints ---


@app.get("/health")
async def health():
    """Health check endpoint."""
    if tinman is None:
        return JSONResponse(
            status_code=503, content={"status": "unhealthy", "error": "Tinman not initialized"}
        )

    return {
        "status": "healthy",
        "tinman": {
            "mode": tinman.state.mode.value,
            "hypotheses_generated": tinman.state.hypotheses_generated,
            "experiments_run": tinman.state.experiments_run,
            "failures_discovered": tinman.state.failures_discovered,
        },
        "stats": research_stats,
    }


@app.get("/tinman/status")
async def tinman_status():
    """Get Tinman status."""
    if tinman is None:
        raise HTTPException(status_code=503, detail="Tinman not initialized")

    return tinman.get_state()


@app.post("/v1/completions", response_model=CompletionResponse)
async def create_completion(
    request: CompletionRequest,
    background_tasks: BackgroundTasks,
):
    """
    LLM completion endpoint with Tinman monitoring.

    All requests are monitored for potential failures.
    """
    if tinman is None or tinman.model_client is None:
        raise HTTPException(status_code=503, detail="Model client not available")

    # Create pipeline context
    ctx = adapter.create_context(
        messages=request.messages,
        model=request.model,
    )

    # Pre-request hooks
    ctx = await adapter.pre_request(ctx)

    # Make the LLM call
    try:
        response = await tinman.model_client.complete(
            messages=request.messages,
            model=request.model,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
        )
    except Exception as e:
        ctx.error = str(e)
        await adapter.on_error(ctx)
        raise HTTPException(status_code=500, detail=str(e))

    # Post-request hooks
    ctx.response = {"content": response.content}
    ctx = await adapter.post_request(ctx)

    # Log detected issues in background
    if ctx.metadata.get("detected_failures"):
        background_tasks.add_task(
            log_potential_issues,
            ctx.metadata["detected_failures"],
            ctx.id,
        )

    return CompletionResponse(
        id=response.id,
        content=response.content,
        model=response.model,
        usage={
            "prompt_tokens": response.prompt_tokens,
            "completion_tokens": response.completion_tokens,
            "total_tokens": response.total_tokens,
        },
    )


async def log_potential_issues(issues: list, request_id: str):
    """Background task to log potential issues."""
    for issue in issues:
        print(f"[{request_id}] Potential issue: {issue}")


@app.post("/tinman/research", response_model=ResearchResponse)
async def run_research(request: ResearchRequest):
    """
    Run a Tinman research cycle.

    This discovers potential failure modes in the AI system.
    """
    if tinman is None:
        raise HTTPException(status_code=503, detail="Tinman not initialized")

    results = await tinman.research_cycle(
        focus=request.focus,
        max_hypotheses=request.max_hypotheses,
        max_experiments=request.max_experiments,
    )

    # Update stats
    research_stats["cycles_run"] += 1
    research_stats["last_run"] = datetime.utcnow().isoformat()

    return ResearchResponse(
        hypotheses=len(results["hypotheses"]),
        experiments=len(results["experiments"]),
        failures=len(results["failures"]),
        interventions=len(results["interventions"]),
    )


@app.get("/tinman/report")
async def get_report(format: str = "markdown"):
    """Generate a research report."""
    if tinman is None:
        raise HTTPException(status_code=503, detail="Tinman not initialized")

    report = await tinman.generate_report(format=format)
    return {"report": report}


@app.get("/tinman/suggestions")
async def get_suggestions():
    """Get research suggestions."""
    if tinman is None:
        raise HTTPException(status_code=503, detail="Tinman not initialized")

    suggestions = await tinman.suggest_next_steps()
    return {"suggestions": suggestions}


@app.post("/tinman/discuss")
async def discuss(message: str):
    """Have a conversation with Tinman."""
    if tinman is None:
        raise HTTPException(status_code=503, detail="Tinman not initialized")

    response = await tinman.discuss(message)
    return {"response": response}


@app.get("/tinman/approvals/pending")
async def get_pending_approvals():
    """Get pending approval requests."""
    if tinman is None:
        raise HTTPException(status_code=503, detail="Tinman not initialized")

    pending = tinman.get_pending_approvals()
    return {"pending": pending}


@app.get("/tinman/approvals/stats")
async def get_approval_stats():
    """Get approval statistics."""
    if tinman is None:
        raise HTTPException(status_code=503, detail="Tinman not initialized")

    stats = tinman.get_approval_stats()
    return stats


# --- Main ---

if __name__ == "__main__":
    import uvicorn

    print("""
╔══════════════════════════════════════════════════════════╗
║           FastAPI + Tinman Integration Demo              ║
║                                                          ║
║  This example shows how to integrate Tinman into a       ║
║  production FastAPI service for AI reliability.          ║
╚══════════════════════════════════════════════════════════╝

Starting server...
""")

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="info",
    )
