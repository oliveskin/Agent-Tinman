"""PostgreSQL repository for the Research Memory Graph."""

from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session, selectinload

from ..db.models import EdgeModel, NodeModel
from ..utils import get_logger, utc_now
from .models import Edge, EdgeRelation, Node, NodeType

logger = get_logger("graph_repository")


class GraphRepository:
    """
    PostgreSQL persistence layer for the Research Memory Graph.

    Handles storage and retrieval of nodes and edges with
    temporal versioning support.

    Note: This repository does NOT auto-commit transactions.
    Callers must explicitly call commit() to persist changes,
    or rollback() to discard them. This allows batching multiple
    operations into a single atomic transaction.
    """

    def __init__(self, session: Session):
        self.session = session

    def add_node(self, node: Node) -> str:
        """Persist a node and return its ID."""
        db_node = NodeModel(
            id=node.id,
            node_type=node.node_type.value,
            created_at=node.created_at,
            valid_from=node.valid_from,
            valid_to=node.valid_to,
            data=node.data,
        )
        self.session.add(db_node)
        self.session.flush()
        logger.debug(f"Added node: {node.id} ({node.node_type.value})")
        return node.id

    def get_node(self, node_id: str) -> Node | None:
        """Retrieve a node by ID."""
        db_node = self.session.query(NodeModel).filter(NodeModel.id == node_id).first()

        if not db_node:
            return None

        return self._db_to_node(db_node)

    def update_node_data(self, node_id: str, updates: dict[str, Any]) -> bool:
        """Update a node's data payload."""
        db_node = self.session.query(NodeModel).filter(NodeModel.id == node_id).first()

        if not db_node:
            return False

        existing = db_node.data or {}
        existing.update(updates)
        db_node.data = existing
        self.session.flush()
        return True

    def add_edge(self, edge: Edge) -> str:
        """Persist an edge and return its ID."""
        db_edge = EdgeModel(
            id=edge.id,
            src_id=edge.src_id,
            dst_id=edge.dst_id,
            relation=edge.relation.value,
            created_at=edge.created_at,
            metadata=edge.metadata,
        )
        self.session.add(db_edge)
        self.session.flush()
        logger.debug(f"Added edge: {edge.src_id} -[{edge.relation.value}]-> {edge.dst_id}")
        return edge.id

    def get_edge(self, edge_id: str) -> Edge | None:
        """Retrieve an edge by ID."""
        db_edge = self.session.query(EdgeModel).filter(EdgeModel.id == edge_id).first()

        if not db_edge:
            return None

        return self._db_to_edge(db_edge)

    def get_nodes_by_type(
        self,
        node_type: NodeType,
        valid_only: bool = True,
        limit: int = 100,
        with_edges: bool = False,
    ) -> list[Node]:
        """Get all nodes of a specific type with optional eager loading of edges."""
        query = self.session.query(NodeModel).filter(NodeModel.node_type == node_type.value)

        if with_edges:
            query = query.options(
                selectinload(NodeModel.outgoing_edges), selectinload(NodeModel.incoming_edges)
            )

        if valid_only:
            now = utc_now()
            query = query.filter(
                NodeModel.valid_from <= now,
                (NodeModel.valid_to.is_(None)) | (NodeModel.valid_to >= now),
            )

        query = query.order_by(NodeModel.created_at.desc()).limit(limit)

        return [self._db_to_node(n) for n in query.all()]

    def get_outgoing_edges(
        self, node_id: str, relation: EdgeRelation | None = None
    ) -> list[Edge]:
        """Get edges originating from a node."""
        query = self.session.query(EdgeModel).filter(EdgeModel.src_id == node_id)

        if relation:
            query = query.filter(EdgeModel.relation == relation.value)

        return [self._db_to_edge(e) for e in query.all()]

    def get_incoming_edges(
        self, node_id: str, relation: EdgeRelation | None = None
    ) -> list[Edge]:
        """Get edges pointing to a node."""
        query = self.session.query(EdgeModel).filter(EdgeModel.dst_id == node_id)

        if relation:
            query = query.filter(EdgeModel.relation == relation.value)

        return [self._db_to_edge(e) for e in query.all()]

    def get_neighbors(
        self,
        node_id: str,
        relation: EdgeRelation | None = None,
        direction: str = "outgoing",
        valid_only: bool = True,
        limit: int = 100,
    ) -> list[Node]:
        """Get neighboring nodes with eager loading."""
        if direction == "outgoing":
            query = (
                self.session.query(NodeModel)
                .join(EdgeModel, EdgeModel.dst_id == NodeModel.id)
                .filter(EdgeModel.src_id == node_id)
            )
        else:
            query = (
                self.session.query(NodeModel)
                .join(EdgeModel, EdgeModel.src_id == NodeModel.id)
                .filter(EdgeModel.dst_id == node_id)
            )

        if relation:
            query = query.filter(EdgeModel.relation == relation.value)

        if valid_only:
            now = utc_now()
            query = query.filter(
                NodeModel.valid_from <= now,
                (NodeModel.valid_to.is_(None)) | (NodeModel.valid_to >= now),
            )

        db_nodes = query.limit(limit).all()
        return [self._db_to_node(n) for n in db_nodes]

    def invalidate_node(self, node_id: str, at: datetime | None = None) -> bool:
        """Mark a node as no longer valid."""
        db_node = self.session.query(NodeModel).filter(NodeModel.id == node_id).first()

        if not db_node:
            return False

        db_node.valid_to = at or utc_now()
        self.session.flush()
        return True

    def query_at_time(
        self, node_type: NodeType | None = None, at: datetime | None = None, limit: int = 100
    ) -> list[Node]:
        """
        Query nodes valid at a specific point in time.

        Supports temporal versioning - "what did we know at time T?"
        """
        timestamp = at or utc_now()

        query = self.session.query(NodeModel).filter(
            NodeModel.valid_from <= timestamp,
            (NodeModel.valid_to.is_(None)) | (NodeModel.valid_to >= timestamp),
        )

        if node_type:
            query = query.filter(NodeModel.node_type == node_type.value)

        query = query.order_by(NodeModel.created_at.desc()).limit(limit)

        return [self._db_to_node(n) for n in query.all()]

    def get_lineage(
        self,
        node_id: str,
        max_depth: int = 10,
        max_branches: int = 5,
    ) -> list[tuple[Node, Edge, int]]:
        """
        Get the causal lineage of a node as a tree structure.

        Traverses CAUSED_BY edges to find all causal chains.
        Returns list of (node, edge, depth) tuples in depth-first order.
        The depth indicator shows how far each cause is from the original node.

        Args:
            node_id: The starting node ID
            max_depth: Maximum depth to traverse
            max_branches: Maximum number of cause branches per node

        Returns:
            List of (node, edge, depth) tuples representing the cause tree
        """
        result: list[tuple[Node, Edge, int]] = []
        visited: set[str] = {node_id}

        def traverse(current_id: str, depth: int) -> None:
            if depth >= max_depth:
                return

            # Get incoming CAUSED_BY edges for current node
            edges = self.get_incoming_edges(current_id, EdgeRelation.CAUSED_BY)

            for edge in edges[:max_branches]:  # Limit branches per node
                if edge.src_id in visited:
                    continue
                visited.add(edge.src_id)

                cause_node = self.get_node(edge.src_id)
                if cause_node:
                    result.append((cause_node, edge, depth + 1))
                    traverse(edge.src_id, depth + 1)

        traverse(node_id, 0)
        return result

    def get_failure_evolution(self, failure_class: str, limit: int = 50) -> list[Node]:
        """
        Track how a failure class evolved over time.

        Returns failure nodes in chronological order, following
        EVOLVED_INTO edges where present.
        """
        # Get all failure nodes of this class
        failures = (
            self.session.query(NodeModel)
            .filter(
                NodeModel.node_type == NodeType.FAILURE_MODE.value,
                NodeModel.data["primary_class"].astext == failure_class,
            )
            .order_by(NodeModel.created_at.asc())
            .limit(limit)
            .all()
        )

        return [self._db_to_node(f) for f in failures]

    def search_nodes(
        self, data_filter: dict[str, Any], node_type: NodeType | None = None, limit: int = 100
    ) -> list[Node]:
        """
        Search nodes by data field values.

        Uses PostgreSQL JSONB operators for efficient querying.
        """
        query = self.session.query(NodeModel)

        if node_type:
            query = query.filter(NodeModel.node_type == node_type.value)

        # Apply JSONB filters
        for key, value in data_filter.items():
            if isinstance(value, str):
                query = query.filter(NodeModel.data[key].astext == value)
            else:
                query = query.filter(NodeModel.data[key] == value)

        query = query.order_by(NodeModel.created_at.desc()).limit(limit)

        return [self._db_to_node(n) for n in query.all()]

    def _db_to_node(self, db_node: NodeModel) -> Node:
        """Convert database model to domain model."""
        return Node(
            id=str(db_node.id),
            node_type=NodeType(db_node.node_type),
            created_at=db_node.created_at,
            valid_from=db_node.valid_from,
            valid_to=db_node.valid_to,
            data=db_node.data or {},
        )

    def _db_to_edge(self, db_edge: EdgeModel) -> Edge:
        """Convert database model to domain model."""
        return Edge(
            id=str(db_edge.id),
            src_id=str(db_edge.src_id),
            dst_id=str(db_edge.dst_id),
            relation=EdgeRelation(db_edge.relation),
            created_at=db_edge.created_at,
            metadata=db_edge.metadata or {},
        )

    def commit(self) -> None:
        """Commit the current transaction."""
        self.session.commit()

    def rollback(self) -> None:
        """Rollback the current transaction."""
        self.session.rollback()
