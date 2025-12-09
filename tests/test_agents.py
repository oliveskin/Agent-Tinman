"""Tests for Tinman agents."""

import pytest
from tinman.agents.hypothesis_engine import HypothesisEngine
from tinman.agents.experiment_architect import ExperimentArchitect
from tinman.agents.base import AgentState


@pytest.mark.asyncio
async def test_hypothesis_engine_generates_hypotheses(lab_context):
    """Test that hypothesis engine generates hypotheses."""
    engine = HypothesisEngine()

    assert engine.state == AgentState.IDLE

    result = await engine.run(lab_context)

    assert result.success
    assert "hypotheses" in result.data
    assert len(result.data["hypotheses"]) > 0
    assert engine.state == AgentState.COMPLETED


@pytest.mark.asyncio
async def test_hypothesis_engine_includes_attack_surfaces(lab_context):
    """Test that hypotheses cover standard attack surfaces."""
    engine = HypothesisEngine()
    result = await engine.run(lab_context)

    hypotheses = result.data["hypotheses"]
    surfaces = {h["target_surface"] for h in hypotheses}

    # Should include standard attack surfaces
    expected_surfaces = {"tool_use", "context_window", "reasoning_chain"}
    assert surfaces & expected_surfaces, "Missing expected attack surfaces"


@pytest.mark.asyncio
async def test_experiment_architect_requires_hypotheses(lab_context):
    """Test that experiment architect fails without hypotheses."""
    architect = ExperimentArchitect()

    result = await architect.run(lab_context, hypotheses=[])

    assert not result.success
    assert "No hypotheses" in result.error


@pytest.mark.asyncio
async def test_experiment_architect_designs_experiments(lab_context):
    """Test that experiment architect designs experiments from hypotheses."""
    # First generate hypotheses
    engine = HypothesisEngine()
    h_result = await engine.run(lab_context)

    # Convert to Hypothesis objects
    from tinman.agents.hypothesis_engine import Hypothesis
    from tinman.taxonomy.failure_types import FailureClass

    hypotheses = [
        Hypothesis(
            id=h["id"],
            target_surface=h["target_surface"],
            expected_failure=h["expected_failure"],
            failure_class=FailureClass(h["failure_class"]),
            confidence=h["confidence"],
            priority=h["priority"],
        )
        for h in h_result.data["hypotheses"][:3]
    ]

    # Design experiments
    architect = ExperimentArchitect()
    result = await architect.run(lab_context, hypotheses=hypotheses)

    assert result.success
    assert "experiments" in result.data
    assert len(result.data["experiments"]) > 0


@pytest.mark.asyncio
async def test_agent_lifecycle(lab_context):
    """Test agent state transitions."""
    engine = HypothesisEngine()

    assert engine.state == AgentState.IDLE

    # Run should transition through states
    result = await engine.run(lab_context)

    assert engine.state == AgentState.COMPLETED
    assert result.duration_ms >= 0
