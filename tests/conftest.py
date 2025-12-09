"""Pytest configuration and fixtures."""

import pytest
from datetime import datetime

from tinman.config.modes import OperatingMode
from tinman.agents.base import AgentContext
from tinman.memory.models import Node, NodeType


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
