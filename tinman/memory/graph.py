"""Research Memory Graph - core API for behavioral lineage tracking."""

from datetime import datetime
from typing import Any, Optional
from sqlalchemy.orm import Session

from ..utils import get_logger
from .models import Node, Edge, NodeType, EdgeRelation
from .repository import GraphRepository

logger = get_logger("memory_graph")


class MemoryGraph:
    """
    Research Memory Graph with temporal versioning.

    The central knowledge store for FDRA, tracking:
    - Model behavior evolution
    - Failure emergence and evolution
    - Intervention effects and side effects
    - Causal relationships

    Supports temporal queries ("what did we know at time T?")
    and lineage tracking ("what caused this failure?").
    """

    def __init__(self, session: Session):
        self.repo = GraphRepository(session)

    # --- Node Operations ---

    def add_node(self, node: Node) -> str:
        """Add a node to the graph."""
        return self.repo.add_node(node)

    def get_node(self, node_id: str) -> Optional[Node]:
        """Get a node by ID."""
        return self.repo.get_node(node_id)

    def update_node_data(self, node_id: str, updates: dict[str, Any]) -> bool:
        """Update a node's data payload."""
        return self.repo.update_node_data(node_id, updates)

    def invalidate_node(self, node_id: str) -> bool:
        """Mark a node as no longer valid (soft delete with temporal semantics)."""
        return self.repo.invalidate_node(node_id)

    # --- Edge Operations ---

    def add_edge(self, edge: Edge) -> str:
        """Add an edge to the graph."""
        return self.repo.add_edge(edge)

    def link(self,
             src_id: str,
             dst_id: str,
             relation: EdgeRelation,
             metadata: Optional[dict[str, Any]] = None) -> Edge:
        """Create and add an edge between two nodes."""
        edge = Edge(
            src_id=src_id,
            dst_id=dst_id,
            relation=relation,
            metadata=metadata or {},
        )
        self.add_edge(edge)
        return edge

    def get_edge(self, edge_id: str) -> Optional[Edge]:
        """Get an edge by ID."""
        return self.repo.get_edge(edge_id)

    # --- Query Operations ---

    def get_hypotheses(self, valid_only: bool = True, limit: int = 100) -> list[Node]:
        """Get hypothesis nodes."""
        return self.repo.get_nodes_by_type(NodeType.HYPOTHESIS, valid_only, limit)

    def get_experiments(self, valid_only: bool = True, limit: int = 100) -> list[Node]:
        """Get experiment nodes."""
        return self.repo.get_nodes_by_type(NodeType.EXPERIMENT, valid_only, limit)

    def get_failures(self, valid_only: bool = True, limit: int = 100) -> list[Node]:
        """Get failure mode nodes."""
        return self.repo.get_nodes_by_type(NodeType.FAILURE_MODE, valid_only, limit)

    def get_interventions(self, valid_only: bool = True, limit: int = 100) -> list[Node]:
        """Get intervention nodes."""
        return self.repo.get_nodes_by_type(NodeType.INTERVENTION, valid_only, limit)

    def get_neighbors(self,
                      node_id: str,
                      relation: Optional[EdgeRelation] = None,
                      direction: str = "outgoing") -> list[Node]:
        """Get neighboring nodes."""
        return self.repo.get_neighbors(node_id, relation, direction)

    # --- Temporal Queries ---

    def snapshot_at(self,
                    timestamp: datetime,
                    node_type: Optional[NodeType] = None) -> list[Node]:
        """
        Get graph state at a specific point in time.

        Useful for forensic analysis: "What failures did we know about
        when we deployed intervention X?"
        """
        return self.repo.query_at_time(node_type, timestamp)

    # --- Lineage Queries ---

    def get_lineage(self, node_id: str, max_depth: int = 10) -> list[tuple[Node, Edge]]:
        """
        Get the causal lineage of a node.

        Returns the chain of causes from effect to root cause.
        """
        return self.repo.get_lineage(node_id, max_depth)

    def get_failure_evolution(self, failure_class: str) -> list[Node]:
        """
        Track how a failure class evolved over time.

        Useful for understanding failure family mutations
        across model versions.
        """
        return self.repo.get_failure_evolution(failure_class)

    # --- Search Operations ---

    def search(self,
               data_filter: dict[str, Any],
               node_type: Optional[NodeType] = None,
               limit: int = 100) -> list[Node]:
        """
        Search nodes by data field values.

        Examples:
            graph.search({"severity": "S3"}, NodeType.FAILURE_MODE)
            graph.search({"risk_tier": "block"}, NodeType.INTERVENTION)
        """
        return self.repo.search_nodes(data_filter, node_type, limit)

    def find_failures_by_severity(self, min_severity: str) -> list[Node]:
        """Find failures at or above a severity level."""
        severity_order = ["S0", "S1", "S2", "S3", "S4"]
        min_idx = severity_order.index(min_severity)

        results = []
        for severity in severity_order[min_idx:]:
            results.extend(
                self.search({"severity": severity}, NodeType.FAILURE_MODE)
            )
        return results

    def find_unresolved_failures(self) -> list[Node]:
        """Find failures that haven't been resolved."""
        return self.search({"is_resolved": False}, NodeType.FAILURE_MODE)

    def find_interventions_by_risk(self, risk_tier: str) -> list[Node]:
        """Find interventions by risk tier."""
        return self.search({"risk_tier": risk_tier}, NodeType.INTERVENTION)

    # --- Recording Convenience Methods ---

    def record_hypothesis(self,
                          target_surface: str,
                          expected_failure: str,
                          confidence: float,
                          priority: str = "medium",
                          hypothesis_id: Optional[str] = None,
                          **extra_data: Any) -> Node:
        """Record a new hypothesis."""
        from .models import create_hypothesis_node
        node = create_hypothesis_node(
            target_surface=target_surface,
            expected_failure=expected_failure,
            confidence=confidence,
            priority=priority,
            hypothesis_id=hypothesis_id,
            **extra_data,
        )
        self.add_node(node)
        logger.info(f"Recorded hypothesis: {node.id}")
        return node

    def record_experiment(self,
                          hypothesis_id: str,
                          stress_type: str,
                          mode: str,
                          constraints: dict[str, Any],
                          experiment_id: Optional[str] = None,
                          **extra_data: Any) -> Node:
        """Record a new experiment, linked to its hypothesis."""
        from .models import create_experiment_node
        node = create_experiment_node(
            hypothesis_id=hypothesis_id,
            stress_type=stress_type,
            mode=mode,
            constraints=constraints,
            experiment_id=experiment_id,
            **extra_data,
        )
        self.add_node(node)

        # Link to hypothesis
        self.link(hypothesis_id, node.id, EdgeRelation.TESTED_IN)

        logger.info(f"Recorded experiment: {node.id}")
        return node

    def record_failure(self,
                       run_id: str,
                       primary_class: str,
                       secondary_class: str,
                       severity: str,
                       trigger_signature: list[str],
                       reproducibility: float = 0.0,
                       parent_failure_id: Optional[str] = None,
                       **extra_data: Any) -> Node:
        """Record a discovered failure, linked to its experiment run."""
        from .models import create_failure_node
        node = create_failure_node(
            primary_class=primary_class,
            secondary_class=secondary_class,
            severity=severity,
            trigger_signature=trigger_signature,
            reproducibility=reproducibility,
            is_resolved=False,
            **extra_data,
        )
        self.add_node(node)

        # Link to run
        self.link(node.id, run_id, EdgeRelation.OBSERVED_IN)

        # Link to parent failure (evolution)
        if parent_failure_id:
            self.link(parent_failure_id, node.id, EdgeRelation.EVOLVED_INTO)

        logger.info(f"Recorded failure: {node.id} ({severity})")
        return node

    def record_intervention(self,
                            failure_id: str,
                            intervention_type: str,
                            payload: dict[str, Any],
                            expected_gains: dict[str, float],
                            expected_regressions: dict[str, float],
                            risk_tier: str) -> Node:
        """Record a proposed intervention, linked to the failure it addresses."""
        from .models import create_intervention_node
        node = create_intervention_node(
            intervention_type=intervention_type,
            payload=payload,
            expected_gains=expected_gains,
            expected_regressions=expected_regressions,
            risk_tier=risk_tier,
        )
        self.add_node(node)

        # Link to failure
        self.link(failure_id, node.id, EdgeRelation.ADDRESSED_BY)

        logger.info(f"Recorded intervention: {node.id} ({risk_tier})")
        return node

    def record_deployment(self,
                          intervention_id: str,
                          mode: str,
                          rollback_state: Optional[dict[str, Any]] = None) -> Node:
        """Record a deployment of an intervention."""
        node = Node(
            node_type=NodeType.DEPLOYMENT,
            data={
                "intervention_id": intervention_id,
                "mode": mode,
                "rollback_state": rollback_state or {},
                "status": "active",
            },
        )
        self.add_node(node)

        # Link to intervention
        self.link(intervention_id, node.id, EdgeRelation.DEPLOYED_AS)

        logger.info(f"Recorded deployment: {node.id}")
        return node

    def record_rollback(self,
                        deployment_id: str,
                        reason: str,
                        regression_failure_id: Optional[str] = None) -> Node:
        """Record a rollback of a deployment."""
        node = Node(
            node_type=NodeType.ROLLBACK,
            data={
                "deployment_id": deployment_id,
                "reason": reason,
            },
        )
        self.add_node(node)

        # Link to deployment
        self.link(deployment_id, node.id, EdgeRelation.ROLLED_BACK_BY)

        # If there's an associated regression failure, link it
        if regression_failure_id:
            self.link(deployment_id, regression_failure_id, EdgeRelation.REGRESSED_AS)

        logger.info(f"Recorded rollback: {node.id}")
        return node

    # --- Statistics ---

    def get_stats(self) -> dict[str, int]:
        """Get graph statistics."""
        stats = {}
        for node_type in NodeType:
            nodes = self.repo.get_nodes_by_type(node_type, valid_only=False, limit=10000)
            stats[node_type.value] = len(nodes)
        return stats
