"""Tinman FDRA Recipes - Common usage patterns and examples.

This module contains ready-to-use recipes for common Tinman operations.
Copy and adapt these patterns for your use case.
"""

import asyncio
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

# ============================================================================
# RECIPE 1: Basic Research Cycle
# ============================================================================

async def run_basic_research():
    """Run a basic research cycle with default settings."""
    from tinman import create_tinman
    from tinman.config.modes import OperatingMode

    tinman = await create_tinman(mode=OperatingMode.LAB)

    try:
        results = await tinman.research_cycle(
            focus="tool_use",
            max_hypotheses=5,
            max_experiments=3,
            runs_per_experiment=10,
        )

        print(f"Discovered {len(results.get('failures', []))} failures")
        return results

    finally:
        await tinman.close()


# ============================================================================
# RECIPE 2: Continuous Research with Cost Limits
# ============================================================================

async def continuous_research_with_budget(
    budget_usd: float = 10.0,
    max_cycles: int = 10,
):
    """Run continuous research until budget exhausted or max cycles reached."""
    from tinman import create_tinman
    from tinman.config.modes import OperatingMode
    from tinman.core.cost_tracker import CostTracker, BudgetExceededError

    tinman = await create_tinman(mode=OperatingMode.LAB)
    tracker = CostTracker(budget_usd=budget_usd)

    all_failures = []
    cycle_count = 0

    try:
        while cycle_count < max_cycles:
            try:
                tracker.enforce_budget(estimated_cost=1.0)
            except BudgetExceededError:
                print(f"Budget exhausted after {cycle_count} cycles")
                break

            results = await tinman.research_cycle(
                max_hypotheses=2,
                max_experiments=1,
            )

            # Record estimated cost
            tracker.record_cost(
                amount_usd=0.50,  # Estimate
                source="research_cycle",
                model="claude-3",
            )

            all_failures.extend(results.get("failures", []))
            cycle_count += 1

            print(f"Cycle {cycle_count}: Found {len(results.get('failures', []))} failures")
            print(f"  Budget remaining: ${tracker.remaining_budget:.2f}")

        return all_failures

    finally:
        await tinman.close()


# ============================================================================
# RECIPE 3: Targeted Failure Discovery
# ============================================================================

async def discover_failures_by_class(
    failure_class: str,
    min_severity: str = "S2",
):
    """Focus research on discovering specific failure classes."""
    from tinman import create_tinman
    from tinman.config.modes import OperatingMode
    from tinman.taxonomy import FailureClass

    tinman = await create_tinman(mode=OperatingMode.LAB)

    try:
        # Ask Tinman to focus on specific class
        prompt = f"""
        Focus your research specifically on {failure_class} failures.
        Generate hypotheses that target this failure class.
        Only propose experiments likely to trigger {failure_class} failures.
        """

        response = await tinman.discuss(prompt)
        print(f"Research focus set: {response[:200]}...")

        # Run focused research
        results = await tinman.research_cycle(
            focus=failure_class.lower(),
            max_hypotheses=5,
            max_experiments=3,
        )

        # Filter results to target class
        target_failures = [
            f for f in results.get("failures", [])
            if f.get("primary_class") == failure_class
        ]

        return target_failures

    finally:
        await tinman.close()


# ============================================================================
# RECIPE 4: Generate Reports for Stakeholders
# ============================================================================

async def generate_weekly_report(output_dir: str = "./reports"):
    """Generate comprehensive weekly report."""
    from tinman import create_tinman
    from tinman.config.modes import OperatingMode
    from tinman.reporting import (
        ExecutiveSummaryReport,
        TechnicalAnalysisReport,
        export_all_formats,
        ReportFormat,
    )

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    tinman = await create_tinman(mode=OperatingMode.LAB)

    try:
        now = datetime.utcnow()
        week_ago = now - timedelta(days=7)

        # Executive summary
        exec_gen = ExecutiveSummaryReport(graph=tinman.graph)
        exec_report = await exec_gen.generate(
            period_start=week_ago,
            period_end=now,
        )

        # Technical report
        tech_gen = TechnicalAnalysisReport(graph=tinman.graph)
        tech_report = await tech_gen.generate(
            period_start=week_ago,
            period_end=now,
        )

        # Export
        date_str = now.strftime("%Y%m%d")

        export_all_formats(
            exec_report,
            output_dir=output_path,
            base_name=f"executive_weekly_{date_str}",
        )

        export_all_formats(
            tech_report,
            output_dir=output_path,
            base_name=f"technical_weekly_{date_str}",
        )

        print(f"Reports saved to {output_path}")
        return output_path

    finally:
        await tinman.close()


# ============================================================================
# RECIPE 5: Ingest and Analyze External Traces
# ============================================================================

async def analyze_otlp_traces(otlp_data: dict):
    """Ingest OTLP traces and analyze for failures."""
    from tinman import create_tinman
    from tinman.config.modes import OperatingMode
    from tinman.ingest import OTLPAdapter

    # Parse traces
    adapter = OTLPAdapter()
    traces = list(adapter.parse(otlp_data))

    tinman = await create_tinman(mode=OperatingMode.LAB)

    try:
        # Extract errors for analysis
        error_summaries = []
        for trace in traces:
            for span in trace.error_spans:
                error_summaries.append({
                    "service": span.service_name,
                    "operation": span.name,
                    "error_type": span.get_exceptions()[0].get("type", "unknown")
                    if span.has_exception() else "unknown",
                    "duration_ms": span.duration_ms,
                })

        if error_summaries:
            # Ask Tinman to analyze
            prompt = f"""
            Analyze these {len(error_summaries)} errors from production traces:

            {error_summaries[:10]}  # First 10 for context

            What patterns do you see? What hypotheses should we investigate?
            """

            analysis = await tinman.discuss(prompt)
            print(f"Analysis: {analysis}")

        return error_summaries

    finally:
        await tinman.close()


# ============================================================================
# RECIPE 6: Mode Transition with Validation
# ============================================================================

async def safe_mode_transition(
    from_mode: str,
    to_mode: str,
    validation_fn: Optional[callable] = None,
):
    """Safely transition between modes with validation."""
    from tinman import create_tinman
    from tinman.config.modes import OperatingMode

    mode_map = {
        "lab": OperatingMode.LAB,
        "shadow": OperatingMode.SHADOW,
        "production": OperatingMode.PRODUCTION,
    }

    tinman = await create_tinman(mode=mode_map[from_mode])

    try:
        current = tinman.state.mode.value
        target = mode_map[to_mode]

        # Validate transition
        valid_transitions = {
            "lab": ["shadow"],
            "shadow": ["lab", "production"],
            "production": ["shadow"],
        }

        if to_mode not in valid_transitions.get(current, []):
            raise ValueError(f"Invalid transition: {current} -> {to_mode}")

        # Run custom validation if provided
        if validation_fn:
            is_valid = await validation_fn(tinman)
            if not is_valid:
                raise ValueError("Custom validation failed")

        # Perform transition
        tinman.state.mode = target
        print(f"Transitioned: {current} -> {to_mode}")

        return True

    finally:
        await tinman.close()


# ============================================================================
# RECIPE 7: Custom Approval Handler
# ============================================================================

async def setup_custom_approvals():
    """Configure custom approval handling."""
    from tinman import create_tinman
    from tinman.config.modes import OperatingMode
    from tinman.core.approval_handler import ApprovalHandler, ApprovalContext

    tinman = await create_tinman(mode=OperatingMode.LAB)

    # Custom approval callback
    async def my_approval_handler(context: ApprovalContext) -> tuple[bool, str]:
        """Custom approval logic."""
        # Auto-approve safe actions
        if context.risk_tier.value == "safe":
            return True, "Auto-approved safe action"

        # Auto-reject destructive actions in lab
        if context.severity.value in ("S3", "S4"):
            return False, "High severity actions blocked in lab"

        # Require human approval for review tier
        print(f"Approval needed: {context.action_description}")
        user_input = input("Approve? (y/n): ")
        return user_input.lower() == "y", "Human decision"

    # Note: In production, integrate with your approval system
    # tinman.approval_handler.set_callback(my_approval_handler)

    return tinman


# ============================================================================
# RECIPE 8: Prometheus Metrics Integration
# ============================================================================

async def setup_metrics_server():
    """Start Tinman with Prometheus metrics server."""
    from tinman import create_tinman
    from tinman.config.modes import OperatingMode
    from tinman.core.metrics import start_metrics_server, get_metrics

    # Start metrics server on port 9090
    start_metrics_server(port=9090)
    print("Metrics available at http://localhost:9090/metrics")

    tinman = await create_tinman(mode=OperatingMode.LAB)

    # Metrics are automatically recorded during operations
    await tinman.research_cycle(max_hypotheses=2)

    # Check current metrics
    metrics = get_metrics()
    print(f"Research cycles run: {metrics.research_cycles_total._value}")

    return tinman


# ============================================================================
# RECIPE 9: Database-Backed Session
# ============================================================================

async def create_persistent_session(db_url: str):
    """Create a session with database persistence."""
    from tinman import create_tinman
    from tinman.config.modes import OperatingMode

    tinman = await create_tinman(
        mode=OperatingMode.LAB,
        db_url=db_url,  # e.g., "postgresql://user:pass@localhost/tinman"
    )

    try:
        # All operations are automatically persisted
        await tinman.research_cycle(max_hypotheses=3)

        # Query historical data
        if tinman.db:
            # Get recent failures
            from tinman.db.models import Failure
            failures = tinman.db.query(Failure).order_by(
                Failure.created_at.desc()
            ).limit(10).all()
            print(f"Recent failures: {len(failures)}")

        return tinman

    except Exception as e:
        await tinman.close()
        raise


# ============================================================================
# RECIPE 10: FastAPI Service Integration
# ============================================================================

def create_fastapi_integration():
    """Example FastAPI integration with Tinman."""
    from fastapi import FastAPI, HTTPException
    from tinman.service import create_app, get_tinman_service

    # Tinman's built-in FastAPI app
    app = create_app()

    # Add custom endpoints
    @app.get("/custom/summary")
    async def custom_summary():
        tinman = get_tinman_service()
        if not tinman:
            raise HTTPException(503, "Tinman not initialized")

        state = tinman.get_state()
        return {
            "failures": state["failures_discovered"],
            "experiments": state["experiments_run"],
            "mode": state["mode"],
        }

    return app


# ============================================================================
# CLI Entry Points
# ============================================================================

if __name__ == "__main__":
    import sys

    recipes = {
        "basic": run_basic_research,
        "budget": lambda: continuous_research_with_budget(5.0, 5),
        "report": generate_weekly_report,
        "metrics": setup_metrics_server,
    }

    if len(sys.argv) < 2 or sys.argv[1] not in recipes:
        print("Usage: python recipes.py <recipe>")
        print(f"Available recipes: {', '.join(recipes.keys())}")
        sys.exit(1)

    recipe = sys.argv[1]
    print(f"Running recipe: {recipe}")
    asyncio.run(recipes[recipe]())
