"""SQLAlchemy ORM models for Tinman FDRA."""

import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID

JSONType = JSON().with_variant(JSONB, "postgresql")
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


def generate_uuid():
    return str(uuid.uuid4())


class NodeModel(Base):
    """Research Memory Graph nodes."""

    __tablename__ = "nodes"

    id = Column(UUID(as_uuid=False), primary_key=True, default=generate_uuid)
    node_type = Column(String(50), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    valid_from = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    valid_to = Column(DateTime(timezone=True), nullable=True)
    data = Column(JSONType, nullable=False, default=dict)

    __table_args__ = (
        CheckConstraint(
            "node_type IN ('model_version', 'hypothesis', 'experiment', 'run', "
            "'failure_mode', 'intervention', 'simulation', 'deployment', 'rollback')",
            name="valid_node_type",
        ),
        CheckConstraint("valid_to IS NULL OR valid_from <= valid_to", name="valid_temporal_range"),
        Index("idx_nodes_type", "node_type"),
        Index("idx_nodes_created_at", "created_at"),
        Index("idx_nodes_valid_range", "valid_from", "valid_to"),
    )


class EdgeModel(Base):
    """Research Memory Graph edges (causal relationships)."""

    __tablename__ = "edges"

    id = Column(UUID(as_uuid=False), primary_key=True, default=generate_uuid)
    src_id = Column(UUID(as_uuid=False), ForeignKey("nodes.id"), nullable=False)
    dst_id = Column(UUID(as_uuid=False), ForeignKey("nodes.id"), nullable=False)
    relation = Column(String(50), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    valid_from = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    valid_to = Column(DateTime(timezone=True), nullable=True)
    edge_metadata = Column(JSONType, nullable=True)

    src_node = relationship("NodeModel", foreign_keys=[src_id])
    dst_node = relationship("NodeModel", foreign_keys=[dst_id])

    __table_args__ = (
        CheckConstraint(
            "relation IN ('tested_in', 'executed_as', 'observed_in', 'caused_by', "
            "'addressed_by', 'simulated_by', 'deployed_as', 'rolled_back_by', "
            "'regressed_as', 'evolved_into')",
            name="valid_relation",
        ),
        CheckConstraint(
            "valid_to IS NULL OR valid_from <= valid_to", name="valid_edge_temporal_range"
        ),
        Index("idx_edges_src", "src_id"),
        Index("idx_edges_dst", "dst_id"),
        Index("idx_edges_relation", "relation"),
        Index("idx_edges_src_relation", "src_id", "relation"),
        Index("idx_edges_valid_range", "valid_from", "valid_to"),
    )


class ExperimentModel(Base):
    """Experiment definitions."""

    __tablename__ = "experiments"

    id = Column(UUID(as_uuid=False), primary_key=True, default=generate_uuid)
    hypothesis_id = Column(UUID(as_uuid=False), ForeignKey("nodes.id"), nullable=True)
    mode = Column(String(20), nullable=False)
    stress_type = Column(String(50), nullable=False)
    config = Column(JSONType, nullable=False, default=dict)
    constraints = Column(JSONType, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    status = Column(String(20), nullable=False, default="pending")

    runs = relationship(
        "ExperimentRunModel", back_populates="experiment", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("idx_experiments_mode", "mode"),
        Index("idx_experiments_status", "status"),
    )


class ExperimentRunModel(Base):
    """Experiment execution runs."""

    __tablename__ = "experiment_runs"

    id = Column(UUID(as_uuid=False), primary_key=True, default=generate_uuid)
    experiment_id = Column(UUID(as_uuid=False), ForeignKey("experiments.id"), nullable=False)
    started_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    status = Column(String(20), nullable=False, default="running")
    inputs = Column(JSONType, nullable=False, default=list)
    outputs = Column(JSONType, nullable=True)
    traces = Column(JSONType, nullable=True)
    metrics = Column(JSONType, nullable=True)
    determinism_seed = Column(BigInteger, nullable=True)

    experiment = relationship("ExperimentModel", back_populates="runs")
    failures = relationship("FailureModel", back_populates="run", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_runs_experiment", "experiment_id"),
        Index("idx_runs_status", "status"),
    )


class FailureModel(Base):
    """Discovered failure modes."""

    __tablename__ = "failures"

    id = Column(UUID(as_uuid=False), primary_key=True, default=generate_uuid)
    run_id = Column(UUID(as_uuid=False), ForeignKey("experiment_runs.id"), nullable=True)
    primary_class = Column(String(50), nullable=False)
    secondary_class = Column(String(50), nullable=True)
    severity = Column(String(5), nullable=False)
    trigger_signature = Column(JSONType, nullable=False, default=list)
    impact_surface = Column(JSONType, nullable=True)
    reproducibility_score = Column(Float, nullable=True)
    confidence = Column(Float, nullable=True)
    first_seen_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    model_version = Column(String(100), nullable=True)
    is_resolved = Column(Boolean, default=False)
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    resolved_by = Column(UUID(as_uuid=False), ForeignKey("nodes.id"), nullable=True)
    parent_failure_id = Column(UUID(as_uuid=False), ForeignKey("failures.id"), nullable=True)

    run = relationship("ExperimentRunModel", back_populates="failures")
    causal_links = relationship(
        "CausalLinkModel", back_populates="failure", cascade="all, delete-orphan"
    )
    interventions = relationship(
        "InterventionModel", back_populates="failure", cascade="all, delete-orphan"
    )
    parent_failure = relationship("FailureModel", remote_side=[id])

    __table_args__ = (
        Index("idx_failures_class", "primary_class"),
        Index("idx_failures_severity", "severity"),
        Index("idx_failures_model", "model_version"),
        Index("idx_failures_resolved", "is_resolved"),
    )


class CausalLinkModel(Base):
    """Causal links for root cause analysis."""

    __tablename__ = "causal_links"

    id = Column(UUID(as_uuid=False), primary_key=True, default=generate_uuid)
    failure_id = Column(UUID(as_uuid=False), ForeignKey("failures.id"), nullable=False)
    cause_type = Column(String(50), nullable=False)
    cause_description = Column(Text, nullable=False)
    depth = Column(Integer, nullable=False, default=1)
    confidence = Column(Float, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    created_by = Column(String(50), nullable=False)
    parent_cause_id = Column(UUID(as_uuid=False), ForeignKey("causal_links.id"), nullable=True)

    failure = relationship("FailureModel", back_populates="causal_links")
    parent_cause = relationship("CausalLinkModel", remote_side=[id])

    __table_args__ = (Index("idx_causal_failure", "failure_id"),)


class InterventionModel(Base):
    """Proposed interventions."""

    __tablename__ = "interventions"

    id = Column(UUID(as_uuid=False), primary_key=True, default=generate_uuid)
    failure_id = Column(UUID(as_uuid=False), ForeignKey("failures.id"), nullable=True)
    intervention_type = Column(String(50), nullable=False)
    payload = Column(JSONType, nullable=False, default=dict)
    expected_gains = Column(JSONType, nullable=True)
    expected_regressions = Column(JSONType, nullable=True)
    cost_impact_estimate = Column(Float, nullable=True)
    latency_impact_ms = Column(Integer, nullable=True)
    risk_tier = Column(String(10), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    status = Column(String(20), nullable=False, default="proposed")

    failure = relationship("FailureModel", back_populates="interventions")
    simulations = relationship(
        "SimulationModel", back_populates="intervention", cascade="all, delete-orphan"
    )
    approvals = relationship(
        "ApprovalModel", back_populates="intervention", cascade="all, delete-orphan"
    )
    deployments = relationship(
        "DeploymentModel", back_populates="intervention", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("idx_interventions_failure", "failure_id"),
        Index("idx_interventions_status", "status"),
        Index("idx_interventions_risk", "risk_tier"),
    )


class SimulationModel(Base):
    """Counterfactual simulation results."""

    __tablename__ = "simulations"

    id = Column(UUID(as_uuid=False), primary_key=True, default=generate_uuid)
    intervention_id = Column(UUID(as_uuid=False), ForeignKey("interventions.id"), nullable=False)
    replay_dataset_id = Column(String(100), nullable=True)
    baseline_metrics = Column(JSONType, nullable=False, default=dict)
    modified_metrics = Column(JSONType, nullable=False, default=dict)
    pass_rate = Column(Float, nullable=True)
    new_failures_count = Column(Integer, nullable=True)
    risk_shift = Column(Float, nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    intervention = relationship("InterventionModel", back_populates="simulations")

    __table_args__ = (Index("idx_simulations_intervention", "intervention_id"),)


class ApprovalModel(Base):
    """Human approval queue."""

    __tablename__ = "approvals"

    id = Column(UUID(as_uuid=False), primary_key=True, default=generate_uuid)
    intervention_id = Column(UUID(as_uuid=False), ForeignKey("interventions.id"), nullable=False)
    risk_summary = Column(Text, nullable=False)
    impact_summary = Column(Text, nullable=True)
    rollback_plan = Column(Text, nullable=True)
    status = Column(String(20), nullable=False, default="pending")
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    decided_at = Column(DateTime(timezone=True), nullable=True)
    decided_by = Column(String(100), nullable=True)
    decision_reason = Column(Text, nullable=True)

    intervention = relationship("InterventionModel", back_populates="approvals")

    __table_args__ = (
        Index("idx_approvals_status", "status"),
        Index("idx_approvals_intervention", "intervention_id"),
    )


class DeploymentModel(Base):
    """Deployed interventions."""

    __tablename__ = "deployments"

    id = Column(UUID(as_uuid=False), primary_key=True, default=generate_uuid)
    intervention_id = Column(UUID(as_uuid=False), ForeignKey("interventions.id"), nullable=False)
    approval_id = Column(UUID(as_uuid=False), ForeignKey("approvals.id"), nullable=True)
    deployed_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    mode = Column(String(20), nullable=False)
    rollback_state = Column(JSONType, nullable=True)
    status = Column(String(20), nullable=False, default="active")
    rolled_back_at = Column(DateTime(timezone=True), nullable=True)
    rollback_reason = Column(Text, nullable=True)

    intervention = relationship("InterventionModel", back_populates="deployments")
    approval = relationship("ApprovalModel")

    __table_args__ = (
        Index("idx_deployments_status", "status"),
        Index("idx_deployments_intervention", "intervention_id"),
    )


class ModelVersionModel(Base):
    """Tracked model versions."""

    __tablename__ = "model_versions"

    id = Column(UUID(as_uuid=False), primary_key=True, default=generate_uuid)
    version = Column(String(100), nullable=False, unique=True)
    provider = Column(String(50), nullable=False)
    model_metadata = Column(JSONType, nullable=True)
    registered_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    __table_args__ = (Index("idx_model_versions_version", "version"),)
