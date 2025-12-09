"""Pytest configuration and fixtures."""

import asyncio
import pytest
from datetime import datetime
from typing import Generator
from unittest.mock import AsyncMock, MagicMock

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from tinman.config.modes import OperatingMode, Mode
from tinman.agents.base import AgentContext
from tinman.memory.models import Node, NodeType
from tinman.db.models import Base
from tinman.core.risk_evaluator import RiskEvaluator, Action, ActionType, Severity
from tinman.core.risk_policy import RiskPolicy, PolicyDrivenRiskEvaluator
from tinman.core.approval_handler import ApprovalHandler, ApprovalMode
from tinman.core.tools import ToolRegistry, ToolRiskLevel
from tinman.core.event_bus import EventBus
from tinman.integrations.model_client import ModelClient, ModelResponse


# Test database URL (SQLite in-memory)
TEST_DB_URL = "sqlite:///:memory:"


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="function")
def db_engine():
    """Create a test database engine."""
    engine = create_engine(TEST_DB_URL, echo=False)
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture(scope="function")
def db_session(db_engine) -> Generator[Session, None, None]:
    """Create a test database session."""
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=db_engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture
def event_bus() -> EventBus:
    """Create an event bus for tests."""
    return EventBus()


@pytest.fixture
def risk_evaluator() -> RiskEvaluator:
    """Create a risk evaluator for tests."""
    return RiskEvaluator(
        detailed_mode=False,
        auto_approve_safe=True,
        block_on_destructive=True,
    )


@pytest.fixture
def default_risk_policy() -> RiskPolicy:
    """Create a default risk policy."""
    return RiskPolicy.default()


@pytest.fixture
def policy_evaluator(default_risk_policy) -> PolicyDrivenRiskEvaluator:
    """Create a policy-driven risk evaluator."""
    return PolicyDrivenRiskEvaluator(policy=default_risk_policy)


@pytest.fixture
def approval_handler(event_bus, risk_evaluator) -> ApprovalHandler:
    """Create an approval handler for tests."""
    return ApprovalHandler(
        mode=Mode.LAB,
        approval_mode=ApprovalMode.AUTO_APPROVE,
        risk_evaluator=risk_evaluator,
        event_bus=event_bus,
        auto_approve_in_lab=True,
    )


@pytest.fixture
def strict_approval_handler(event_bus, risk_evaluator) -> ApprovalHandler:
    """Create a strict approval handler (production-like) for tests."""
    return ApprovalHandler(
        mode=Mode.PRODUCTION,
        approval_mode=ApprovalMode.AUTO_REJECT,
        risk_evaluator=risk_evaluator,
        event_bus=event_bus,
        auto_approve_in_lab=False,
    )


@pytest.fixture
def tool_registry() -> ToolRegistry:
    """Create a tool registry for tests."""
    return ToolRegistry()


@pytest.fixture
def mock_model_client() -> ModelClient:
    """Create a mock model client for tests."""
    client = MagicMock(spec=ModelClient)
    client.complete = AsyncMock(return_value=ModelResponse(
        content="Test response",
        model="test-model",
        input_tokens=10,
        output_tokens=20,
    ))
    return client


# Sample actions for testing
@pytest.fixture
def safe_action() -> Action:
    """A safe action (S0 severity)."""
    return Action(
        action_type=ActionType.CONFIG_CHANGE,
        target_surface="lab",
        payload={"key": "value"},
        predicted_severity=Severity.S0,
        estimated_cost=0.0,
        is_reversible=True,
    )


@pytest.fixture
def medium_action() -> Action:
    """A medium-risk action (S2 severity)."""
    return Action(
        action_type=ActionType.PROMPT_MUTATION,
        target_surface="shadow",
        payload={"prompt": "modified"},
        predicted_severity=Severity.S2,
        estimated_cost=1.0,
        is_reversible=True,
    )


@pytest.fixture
def high_risk_action() -> Action:
    """A high-risk action (S3 severity)."""
    return Action(
        action_type=ActionType.TOOL_POLICY_CHANGE,
        target_surface="production",
        payload={"tool": "dangerous"},
        predicted_severity=Severity.S3,
        estimated_cost=10.0,
        is_reversible=False,
    )


@pytest.fixture
def destructive_action() -> Action:
    """A destructive action (should always be blocked)."""
    return Action(
        action_type=ActionType.DESTRUCTIVE_TOOL_CALL,
        target_surface="production",
        payload={"delete": "everything"},
        predicted_severity=Severity.S4,
        estimated_cost=0.0,
        is_reversible=False,
    )


# Agent context fixtures
@pytest.fixture
def lab_context():
    """Create a LAB mode agent context."""
    return AgentContext(mode=OperatingMode.LAB)


@pytest.fixture
def shadow_context():
    """Create a SHADOW mode agent context."""
    return AgentContext(mode=OperatingMode.SHADOW)


@pytest.fixture
def production_context():
    """Create a PRODUCTION mode agent context."""
    return AgentContext(mode=OperatingMode.PRODUCTION)


@pytest.fixture
def sample_hypothesis_node():
    """Create a sample hypothesis node."""
    return Node(
        node_type=NodeType.HYPOTHESIS,
        data={
            "target_surface": "tool_use",
            "expected_failure": "Tool parameter injection",
            "confidence": 0.7,
            "priority": "high",
        },
    )


@pytest.fixture
def sample_failure_node():
    """Create a sample failure node."""
    return Node(
        node_type=NodeType.FAILURE_MODE,
        data={
            "primary_class": "tool_use",
            "secondary_class": "injection",
            "severity": "S3",
            "trigger_signature": ["tool:injection", "error:path_traversal"],
            "reproducibility": 0.8,
            "is_resolved": False,
        },
    )


# Sample async tools for testing
async def safe_tool(**kwargs) -> str:
    """A safe tool that always succeeds."""
    return f"Success: {kwargs}"


async def failing_tool(**kwargs) -> str:
    """A tool that always fails."""
    raise RuntimeError("Tool failure")


async def slow_tool(**kwargs) -> str:
    """A tool that takes time."""
    await asyncio.sleep(10)
    return "Completed"


@pytest.fixture
def sample_tools():
    """Dictionary of sample tools for testing."""
    return {
        "safe": safe_tool,
        "failing": failing_tool,
        "slow": slow_tool,
    }
