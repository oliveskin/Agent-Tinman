"""FastAPI application for Tinman service mode.

This provides an HTTP API for running Tinman as a service,
enabling integration with CI/CD pipelines, monitoring systems,
and other infrastructure components.

Usage:
    # Run directly
    uvicorn tinman.service.app:app --host 0.0.0.0 --port 8000

    # Or via CLI
    tinman serve --host 0.0.0.0 --port 8000
"""

import os
import time
from contextlib import asynccontextmanager

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .. import __version__
from ..config.modes import Mode, OperatingMode
from ..config.settings import load_config
from ..tinman import Tinman, create_tinman
from ..utils import get_logger, utc_now
from .models import (
    ApprovalDecisionRequest,
    ApprovalDecisionResponse,
    ApprovalRequest,
    DiscussRequest,
    DiscussResponse,
    FailureResponse,
    HealthResponse,
    HypothesisResponse,
    ModeEnum,
    ModeTransitionRequest,
    ModeTransitionResponse,
    PendingApprovalsResponse,
    ReportResponse,
    ResearchCycleRequest,
    ResearchCycleResponse,
    StatusResponse,
)

logger = get_logger("service")

# Global Tinman instance
_tinman: Tinman | None = None
_start_time: float = 0


async def get_tinman() -> Tinman:
    """Dependency to get the Tinman instance."""
    if _tinman is None:
        raise HTTPException(status_code=503, detail="Tinman not initialized")
    return _tinman


def get_tinman_service() -> Tinman | None:
    """Get the global Tinman service instance."""
    return _tinman


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    global _tinman, _start_time

    logger.info("Starting Tinman service...")
    _start_time = time.time()

    # Load configuration
    settings = load_config()

    # Get mode from environment or config
    mode_str = os.environ.get("TINMAN_MODE", settings.mode.value)
    try:
        mode = OperatingMode(mode_str)
    except ValueError:
        mode = OperatingMode.LAB
        logger.warning(f"Invalid mode '{mode_str}', defaulting to LAB")

    # Get database URL from environment or config
    db_url = os.environ.get("TINMAN_DATABASE_URL", os.environ.get("DATABASE_URL"))
    if not db_url:
        db_url = settings.database_url

    # Initialize Tinman
    try:
        _tinman = await create_tinman(
            mode=mode,
            db_url=db_url,
            skip_db=db_url is None,
        )
        logger.info(f"Tinman service started in {mode.value} mode")
    except Exception as e:
        logger.error(f"Failed to initialize Tinman: {e}")
        _tinman = None

    yield

    # Cleanup
    if _tinman:
        await _tinman.close()
        logger.info("Tinman service stopped")


def create_app() -> FastAPI:
    """Create the FastAPI application."""
    app = FastAPI(
        title="Tinman FDRA",
        description="Forward-Deployed Research Agent API for AI reliability discovery",
        version=__version__,
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Configure appropriately for production
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register routes
    register_routes(app)

    return app


def register_routes(app: FastAPI):
    """Register all API routes."""

    # Health and status endpoints

    @app.get("/health", response_model=HealthResponse, tags=["Health"])
    async def health_check():
        """Check service health."""
        global _tinman, _start_time

        checks = {
            "tinman_initialized": _tinman is not None,
            "database_connected": False,
            "llm_available": False,
        }

        if _tinman:
            checks["database_connected"] = _tinman.db is not None
            checks["llm_available"] = _tinman.llm is not None

        all_healthy = all(checks.values())

        return HealthResponse(
            status="healthy" if all_healthy else ("degraded" if _tinman else "unhealthy"),
            version=__version__,
            mode=ModeEnum(_tinman.state.mode.value) if _tinman else ModeEnum.LAB,
            database_connected=checks["database_connected"],
            llm_available=checks["llm_available"],
            uptime_seconds=time.time() - _start_time,
            checks=checks,
        )

    @app.get("/status", response_model=StatusResponse, tags=["Health"])
    async def get_status(tinman: Tinman = Depends(get_tinman)):
        """Get current Tinman status."""
        state = tinman.get_state()
        approval_stats = tinman.get_approval_stats()
        pending = tinman.get_pending_approvals()

        return StatusResponse(
            mode=ModeEnum(state["mode"]),
            session_id=state["session_id"],
            started_at=state["started_at"],
            hypotheses_generated=state["hypotheses_generated"],
            experiments_run=state["experiments_run"],
            failures_discovered=state["failures_discovered"],
            interventions_proposed=state["interventions_proposed"],
            current_focus=state["current_focus"],
            has_llm=state["has_llm"],
            has_graph=state["has_graph"],
            pending_approvals=len(pending),
            approval_stats=approval_stats,
        )

    @app.get("/ready", tags=["Health"])
    async def readiness_check():
        """Kubernetes readiness probe."""
        if _tinman is None:
            raise HTTPException(status_code=503, detail="Not ready")
        return {"status": "ready"}

    @app.get("/live", tags=["Health"])
    async def liveness_check():
        """Kubernetes liveness probe."""
        return {"status": "alive"}

    # Research endpoints

    @app.post("/research/cycle", response_model=ResearchCycleResponse, tags=["Research"])
    async def run_research_cycle(
        request: ResearchCycleRequest,
        background_tasks: BackgroundTasks,
        tinman: Tinman = Depends(get_tinman),
    ):
        """Run a research cycle."""
        try:
            result = await tinman.research_cycle(
                focus=request.focus,
                max_hypotheses=request.max_hypotheses,
                max_experiments=request.max_experiments,
                runs_per_experiment=request.runs_per_experiment,
            )

            return ResearchCycleResponse(
                success=True,
                hypotheses_count=len(result.get("hypotheses", [])),
                experiments_count=len(result.get("experiments", [])),
                failures_count=len(result.get("failures", [])),
                interventions_count=len(result.get("interventions", [])),
                hypotheses=[
                    HypothesisResponse(
                        id=h["id"],
                        target_surface=h["target_surface"],
                        expected_failure=h["expected_failure"],
                        failure_class=h["failure_class"],
                        confidence=h["confidence"],
                        priority=h["priority"],
                        rationale=h.get("rationale"),
                    )
                    for h in result.get("hypotheses", [])
                ],
                failures=[
                    FailureResponse(
                        id=f["id"],
                        primary_class=f["primary_class"],
                        secondary_class=f.get("secondary_class"),
                        severity=f["severity"],
                        description=f["description"],
                        reproducibility=f["reproducibility"],
                    )
                    for f in result.get("failures", [])
                ],
            )
        except Exception as e:
            logger.error(f"Research cycle failed: {e}")
            return ResearchCycleResponse(
                success=False,
                hypotheses_count=0,
                experiments_count=0,
                failures_count=0,
                interventions_count=0,
                error=str(e),
            )

    # Approval endpoints

    @app.get("/approvals/pending", response_model=PendingApprovalsResponse, tags=["Approvals"])
    async def get_pending_approvals(tinman: Tinman = Depends(get_tinman)):
        """Get all pending approval requests."""
        pending = tinman.get_pending_approvals()

        return PendingApprovalsResponse(
            count=len(pending),
            approvals=[
                ApprovalRequest(
                    id=ctx.id,
                    action_type=ctx.action_type.value,
                    action_description=ctx.action_description,
                    risk_tier=ctx.risk_tier.value,
                    severity=ctx.severity.value,
                    estimated_cost_usd=ctx.estimated_cost_usd,
                    affected_systems=ctx.affected_systems,
                    is_reversible=ctx.is_reversible,
                    rollback_plan=ctx.rollback_plan,
                    requester_agent=ctx.requester_agent,
                    created_at=ctx.created_at,
                    timeout_seconds=ctx.timeout_seconds,
                )
                for ctx in pending
            ],
        )

    @app.post(
        "/approvals/{approval_id}/decide",
        response_model=ApprovalDecisionResponse,
        tags=["Approvals"],
    )
    async def decide_approval(
        approval_id: str,
        request: ApprovalDecisionRequest,
        tinman: Tinman = Depends(get_tinman),
    ):
        """Decide on a pending approval."""
        # Find the pending approval
        pending = tinman.get_pending_approvals()
        approval = next((a for a in pending if a.id == approval_id), None)

        if not approval:
            raise HTTPException(status_code=404, detail=f"Approval {approval_id} not found")

        # For now, we just log the decision
        # In a real implementation, this would signal to the waiting coroutine
        logger.info(f"Approval {approval_id} decided: {request.decision} by {request.decided_by}")

        return ApprovalDecisionResponse(
            success=True,
            approval_id=approval_id,
            decision=request.decision.value,
            message=f"Decision recorded: {request.decision.value}",
        )

    # Discussion endpoint

    @app.post("/discuss", response_model=DiscussResponse, tags=["Discussion"])
    async def discuss(
        request: DiscussRequest,
        tinman: Tinman = Depends(get_tinman),
    ):
        """Have a conversation with Tinman."""
        response = await tinman.discuss(request.message)

        return DiscussResponse(
            response=response,
            conversation_length=len(tinman._conversation_history),
        )

    @app.post("/discuss/reset", tags=["Discussion"])
    async def reset_conversation(tinman: Tinman = Depends(get_tinman)):
        """Reset conversation history."""
        tinman.reset_conversation()
        return {"message": "Conversation reset"}

    # Report endpoints

    @app.get("/report", response_model=ReportResponse, tags=["Reports"])
    async def generate_report(
        format: str = Query("markdown", enum=["markdown", "json"]),
        tinman: Tinman = Depends(get_tinman),
    ):
        """Generate a research report."""
        content = await tinman.generate_report(format=format)

        return ReportResponse(
            format=format,
            content=content,
            generated_at=utc_now(),
        )

    # Mode management

    @app.post("/mode/transition", response_model=ModeTransitionResponse, tags=["Mode"])
    async def transition_mode(
        request: ModeTransitionRequest,
        tinman: Tinman = Depends(get_tinman),
    ):
        """Transition to a different operating mode."""
        current_mode = tinman.state.mode
        target_mode = OperatingMode(request.target_mode.value)

        # Validate transition
        valid_transitions = {
            OperatingMode.LAB: [OperatingMode.SHADOW],
            OperatingMode.SHADOW: [OperatingMode.PRODUCTION, OperatingMode.LAB],
            OperatingMode.PRODUCTION: [OperatingMode.SHADOW],
        }

        if target_mode not in valid_transitions.get(current_mode, []):
            return ModeTransitionResponse(
                success=False,
                from_mode=ModeEnum(current_mode.value),
                to_mode=ModeEnum(target_mode.value),
                message="Invalid mode transition",
                blocked_reason=f"Cannot transition from {current_mode.value} to {target_mode.value}. "
                f"Valid transitions: {[m.value for m in valid_transitions.get(current_mode, [])]}",
            )

        # Update mode
        tinman.state.mode = target_mode
        tinman.settings.mode = target_mode
        tinman.approval_handler.mode = Mode(target_mode.value)

        logger.info(f"Mode transitioned: {current_mode.value} -> {target_mode.value}")

        return ModeTransitionResponse(
            success=True,
            from_mode=ModeEnum(current_mode.value),
            to_mode=ModeEnum(target_mode.value),
            message=f"Successfully transitioned to {target_mode.value} mode",
        )

    @app.get("/mode", tags=["Mode"])
    async def get_current_mode(tinman: Tinman = Depends(get_tinman)):
        """Get current operating mode."""
        return {"mode": tinman.state.mode.value}

    # Error handler
    @app.exception_handler(Exception)
    async def generic_exception_handler(request, exc):
        logger.error(f"Unhandled exception: {exc}")
        return JSONResponse(
            status_code=500,
            content={"error": "Internal server error", "detail": str(exc)},
        )


# Create the app instance
app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
