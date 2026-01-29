"""Node and Edge models for the Research Memory Graph."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional

from ..utils import generate_id, utc_now


class NodeType(str, Enum):
    """Types of nodes in the memory graph."""
    MODEL_VERSION = "model_version"
    HYPOTHESIS = "hypothesis"
    EXPERIMENT = "experiment"
    RUN = "run"
    FAILURE_MODE = "failure_mode"
    INTERVENTION = "intervention"
    SIMULATION = "simulation"
    DEPLOYMENT = "deployment"
    ROLLBACK = "rollback"


class EdgeRelation(str, Enum):
    """Types of edges (relationships) in the memory graph."""
    TESTED_IN = "tested_in"          # Hypothesis -> Experiment
    EXECUTED_AS = "executed_as"      # Experiment -> Run
    OBSERVED_IN = "observed_in"      # Failure -> Run
    CAUSED_BY = "caused_by"          # Effect -> Cause
    ADDRESSED_BY = "addressed_by"    # Failure -> Intervention
    SIMULATED_BY = "simulated_by"    # Intervention -> Simulation
    DEPLOYED_AS = "deployed_as"      # Intervention -> Deployment
    ROLLED_BACK_BY = "rolled_back_by"  # Deployment -> Rollback
    REGRESSED_AS = "regressed_as"    # Deployment -> Failure
    EVOLVED_INTO = "evolved_into"    # Failure -> Failure (evolution)


@dataclass
class Node:
    """A node in the Research Memory Graph."""
    id: str = field(default_factory=generate_id)
    node_type: NodeType = NodeType.HYPOTHESIS
    created_at: datetime = field(default_factory=utc_now)
    valid_from: datetime = field(default_factory=utc_now)
    valid_to: Optional[datetime] = None
    data: dict[str, Any] = field(default_factory=dict)

    @property
    def is_valid(self) -> bool:
        """Check if node is currently valid (temporal versioning)."""
        now = utc_now()
        if self.valid_to is None:
            return now >= self.valid_from
        return self.valid_from <= now <= self.valid_to

    def invalidate(self, at: Optional[datetime] = None) -> None:
        """Mark node as no longer valid."""
        self.valid_to = at or utc_now()

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "id": self.id,
            "node_type": self.node_type.value,
            "created_at": self.created_at.isoformat(),
            "valid_from": self.valid_from.isoformat(),
            "valid_to": self.valid_to.isoformat() if self.valid_to else None,
            "data": self.data,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Node":
        """Create from dictionary."""
        from ..utils.time_utils import parse_timestamp
        return cls(
            id=d["id"],
            node_type=NodeType(d["node_type"]),
            created_at=parse_timestamp(d["created_at"]),
            valid_from=parse_timestamp(d["valid_from"]),
            valid_to=parse_timestamp(d["valid_to"]) if d.get("valid_to") else None,
            data=d.get("data", {}),
        )


@dataclass
class Edge:
    """An edge (relationship) in the Research Memory Graph."""
    id: str = field(default_factory=generate_id)
    src_id: str = ""
    dst_id: str = ""
    relation: EdgeRelation = EdgeRelation.CAUSED_BY
    created_at: datetime = field(default_factory=utc_now)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "id": self.id,
            "src_id": self.src_id,
            "dst_id": self.dst_id,
            "relation": self.relation.value,
            "created_at": self.created_at.isoformat(),
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Edge":
        """Create from dictionary."""
        from ..utils.time_utils import parse_timestamp
        return cls(
            id=d["id"],
            src_id=d["src_id"],
            dst_id=d["dst_id"],
            relation=EdgeRelation(d["relation"]),
            created_at=parse_timestamp(d["created_at"]),
            metadata=d.get("metadata", {}),
        )


# Convenience constructors for common node types

def create_hypothesis_node(
    target_surface: str,
    expected_failure: str,
    confidence: float,
    priority: str = "medium",
    hypothesis_id: Optional[str] = None,
    **extra_data
) -> Node:
    """Create a hypothesis node."""
    node_kwargs: dict[str, Any] = {
        "node_type": NodeType.HYPOTHESIS,
        "data": {
            "target_surface": target_surface,
            "expected_failure": expected_failure,
            "confidence": confidence,
            "priority": priority,
            **extra_data,
        },
    }
    if hypothesis_id:
        node_kwargs["id"] = hypothesis_id
    return Node(**node_kwargs)


def create_experiment_node(
    hypothesis_id: str,
    stress_type: str,
    mode: str,
    constraints: dict[str, Any],
    experiment_id: Optional[str] = None,
    **extra_data
) -> Node:
    """Create an experiment node."""
    node_kwargs: dict[str, Any] = {
        "node_type": NodeType.EXPERIMENT,
        "data": {
            "hypothesis_id": hypothesis_id,
            "stress_type": stress_type,
            "mode": mode,
            "constraints": constraints,
            **extra_data,
        },
    }
    if experiment_id:
        node_kwargs["id"] = experiment_id
    return Node(**node_kwargs)


def create_failure_node(
    primary_class: str,
    secondary_class: str,
    severity: str,
    trigger_signature: list[str],
    reproducibility: float = 0.0,
    **extra_data
) -> Node:
    """Create a failure mode node."""
    return Node(
        node_type=NodeType.FAILURE_MODE,
        data={
            "primary_class": primary_class,
            "secondary_class": secondary_class,
            "severity": severity,
            "trigger_signature": trigger_signature,
            "reproducibility": reproducibility,
            **extra_data,
        },
    )


def create_intervention_node(
    intervention_type: str,
    payload: dict[str, Any],
    expected_gains: dict[str, float],
    expected_regressions: dict[str, float],
    risk_tier: str,
    **extra_data
) -> Node:
    """Create an intervention node."""
    return Node(
        node_type=NodeType.INTERVENTION,
        data={
            "intervention_type": intervention_type,
            "payload": payload,
            "expected_gains": expected_gains,
            "expected_regressions": expected_regressions,
            "risk_tier": risk_tier,
            **extra_data,
        },
    )
