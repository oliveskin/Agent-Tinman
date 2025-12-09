"""Tests for memory graph."""

import pytest
from datetime import datetime, timedelta

from tinman.memory.models import (
    Node,
    Edge,
    NodeType,
    EdgeRelation,
    create_hypothesis_node,
    create_failure_node,
)
from tinman.utils import utc_now


def test_node_creation():
    """Test basic node creation."""
    node = Node(node_type=NodeType.HYPOTHESIS)

    assert node.id
    assert node.node_type == NodeType.HYPOTHESIS
    assert node.created_at
    assert node.valid_from
    assert node.valid_to is None
    assert node.is_valid


def test_node_invalidation():
    """Test node invalidation."""
    node = Node(node_type=NodeType.HYPOTHESIS)
    assert node.is_valid

    node.invalidate()

    assert node.valid_to is not None
    assert not node.is_valid


def test_node_temporal_validity():
    """Test temporal validity checks."""
    now = utc_now()
    past = now - timedelta(hours=1)
    future = now + timedelta(hours=1)

    # Node valid from past, no end
    node1 = Node(node_type=NodeType.HYPOTHESIS, valid_from=past)
    assert node1.is_valid

    # Node valid from past to future
    node2 = Node(node_type=NodeType.HYPOTHESIS, valid_from=past, valid_to=future)
    assert node2.is_valid

    # Node valid from future
    node3 = Node(node_type=NodeType.HYPOTHESIS, valid_from=future)
    assert not node3.is_valid


def test_edge_creation():
    """Test edge creation."""
    node1 = Node(node_type=NodeType.HYPOTHESIS)
    node2 = Node(node_type=NodeType.EXPERIMENT)

    edge = Edge(
        src_id=node1.id,
        dst_id=node2.id,
        relation=EdgeRelation.TESTED_IN,
    )

    assert edge.id
    assert edge.src_id == node1.id
    assert edge.dst_id == node2.id
    assert edge.relation == EdgeRelation.TESTED_IN


def test_hypothesis_node_factory():
    """Test hypothesis node factory."""
    node = create_hypothesis_node(
        target_surface="tool_use",
        expected_failure="Injection attack",
        confidence=0.8,
        priority="high",
    )

    assert node.node_type == NodeType.HYPOTHESIS
    assert node.data["target_surface"] == "tool_use"
    assert node.data["expected_failure"] == "Injection attack"
    assert node.data["confidence"] == 0.8
    assert node.data["priority"] == "high"


def test_failure_node_factory():
    """Test failure node factory."""
    node = create_failure_node(
        primary_class="tool_use",
        secondary_class="injection",
        severity="S3",
        trigger_signature=["tool:injection"],
        reproducibility=0.9,
    )

    assert node.node_type == NodeType.FAILURE_MODE
    assert node.data["primary_class"] == "tool_use"
    assert node.data["severity"] == "S3"
    assert node.data["reproducibility"] == 0.9


def test_node_serialization():
    """Test node to_dict and from_dict."""
    node = create_hypothesis_node(
        target_surface="context",
        expected_failure="Overflow",
        confidence=0.5,
    )

    data = node.to_dict()

    assert data["node_type"] == "hypothesis"
    assert data["data"]["target_surface"] == "context"

    # Round-trip
    restored = Node.from_dict(data)
    assert restored.id == node.id
    assert restored.node_type == node.node_type
    assert restored.data == node.data
