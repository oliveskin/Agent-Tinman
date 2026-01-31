"""Initial schema with all tables

Revision ID: 0001
Revises:
Create Date: 2024-12-09

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Memory Graph - Nodes
    op.create_table(
        "nodes",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("node_type", sa.String(50), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "valid_from", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("valid_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("data", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.CheckConstraint(
            "node_type IN ('model_version', 'hypothesis', 'experiment', 'run', "
            "'failure_mode', 'intervention', 'simulation', 'deployment', 'rollback')",
            name="valid_node_type",
        ),
    )
    op.create_index("idx_nodes_type", "nodes", ["node_type"])
    op.create_index("idx_nodes_created_at", "nodes", ["created_at"])
    op.create_index("idx_nodes_valid_range", "nodes", ["valid_from", "valid_to"])

    # Memory Graph - Edges
    op.create_table(
        "edges",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "src_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("nodes.id"), nullable=False
        ),
        sa.Column(
            "dst_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("nodes.id"), nullable=False
        ),
        sa.Column("relation", sa.String(50), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("edge_metadata", postgresql.JSONB, nullable=True),
        sa.CheckConstraint(
            "relation IN ('tested_in', 'executed_as', 'observed_in', 'caused_by', "
            "'addressed_by', 'simulated_by', 'deployed_as', 'rolled_back_by', "
            "'regressed_as', 'evolved_into')",
            name="valid_relation",
        ),
    )
    op.create_index("idx_edges_src", "edges", ["src_id"])
    op.create_index("idx_edges_dst", "edges", ["dst_id"])
    op.create_index("idx_edges_relation", "edges", ["relation"])
    op.create_index("idx_edges_src_relation", "edges", ["src_id", "relation"])

    # Experiments
    op.create_table(
        "experiments",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "hypothesis_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("nodes.id"),
            nullable=True,
        ),
        sa.Column("mode", sa.String(20), nullable=False),
        sa.Column("stress_type", sa.String(50), nullable=False),
        sa.Column("config", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("constraints", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
    )
    op.create_index("idx_experiments_mode", "experiments", ["mode"])
    op.create_index("idx_experiments_status", "experiments", ["status"])

    # Experiment Runs
    op.create_table(
        "experiment_runs",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "experiment_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("experiments.id"),
            nullable=False,
        ),
        sa.Column(
            "started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="running"),
        sa.Column("inputs", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("outputs", postgresql.JSONB, nullable=True),
        sa.Column("traces", postgresql.JSONB, nullable=True),
        sa.Column("metrics", postgresql.JSONB, nullable=True),
        sa.Column("determinism_seed", sa.BigInteger, nullable=True),
    )
    op.create_index("idx_runs_experiment", "experiment_runs", ["experiment_id"])
    op.create_index("idx_runs_status", "experiment_runs", ["status"])

    # Failures
    op.create_table(
        "failures",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "run_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("experiment_runs.id"),
            nullable=True,
        ),
        sa.Column("primary_class", sa.String(50), nullable=False),
        sa.Column("secondary_class", sa.String(50), nullable=True),
        sa.Column("severity", sa.String(5), nullable=False),
        sa.Column("trigger_signature", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("impact_surface", postgresql.JSONB, nullable=True),
        sa.Column("reproducibility_score", sa.Float, nullable=True),
        sa.Column("confidence", sa.Float, nullable=True),
        sa.Column(
            "first_seen_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("model_version", sa.String(100), nullable=True),
        sa.Column("is_resolved", sa.Boolean, server_default="false"),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "resolved_by", postgresql.UUID(as_uuid=False), sa.ForeignKey("nodes.id"), nullable=True
        ),
        sa.Column(
            "parent_failure_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("failures.id"),
            nullable=True,
        ),
    )
    op.create_index("idx_failures_class", "failures", ["primary_class"])
    op.create_index("idx_failures_severity", "failures", ["severity"])
    op.create_index("idx_failures_model", "failures", ["model_version"])
    op.create_index("idx_failures_resolved", "failures", ["is_resolved"])

    # Causal Links
    op.create_table(
        "causal_links",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "failure_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("failures.id"),
            nullable=False,
        ),
        sa.Column("cause_type", sa.String(50), nullable=False),
        sa.Column("cause_description", sa.Text, nullable=False),
        sa.Column("depth", sa.Integer, nullable=False, server_default="1"),
        sa.Column("confidence", sa.Float, nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("created_by", sa.String(50), nullable=False),
        sa.Column(
            "parent_cause_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("causal_links.id"),
            nullable=True,
        ),
    )
    op.create_index("idx_causal_failure", "causal_links", ["failure_id"])

    # Interventions
    op.create_table(
        "interventions",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "failure_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("failures.id"),
            nullable=True,
        ),
        sa.Column("intervention_type", sa.String(50), nullable=False),
        sa.Column("payload", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("expected_gains", postgresql.JSONB, nullable=True),
        sa.Column("expected_regressions", postgresql.JSONB, nullable=True),
        sa.Column("cost_impact_estimate", sa.Float, nullable=True),
        sa.Column("latency_impact_ms", sa.Integer, nullable=True),
        sa.Column("risk_tier", sa.String(10), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("status", sa.String(20), nullable=False, server_default="proposed"),
    )
    op.create_index("idx_interventions_failure", "interventions", ["failure_id"])
    op.create_index("idx_interventions_status", "interventions", ["status"])
    op.create_index("idx_interventions_risk", "interventions", ["risk_tier"])

    # Simulations
    op.create_table(
        "simulations",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "intervention_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("interventions.id"),
            nullable=False,
        ),
        sa.Column("replay_dataset_id", sa.String(100), nullable=True),
        sa.Column("baseline_metrics", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("modified_metrics", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("pass_rate", sa.Float, nullable=True),
        sa.Column("new_failures_count", sa.Integer, nullable=True),
        sa.Column("risk_shift", sa.Float, nullable=True),
        sa.Column(
            "completed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("idx_simulations_intervention", "simulations", ["intervention_id"])

    # Approvals (original)
    op.create_table(
        "approvals",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "intervention_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("interventions.id"),
            nullable=False,
        ),
        sa.Column("risk_summary", sa.Text, nullable=False),
        sa.Column("impact_summary", sa.Text, nullable=True),
        sa.Column("rollback_plan", sa.Text, nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decided_by", sa.String(100), nullable=True),
        sa.Column("decision_reason", sa.Text, nullable=True),
    )
    op.create_index("idx_approvals_status", "approvals", ["status"])
    op.create_index("idx_approvals_intervention", "approvals", ["intervention_id"])

    # Deployments
    op.create_table(
        "deployments",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "intervention_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("interventions.id"),
            nullable=False,
        ),
        sa.Column(
            "approval_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("approvals.id"),
            nullable=True,
        ),
        sa.Column(
            "deployed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("mode", sa.String(20), nullable=False),
        sa.Column("rollback_state", postgresql.JSONB, nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("rolled_back_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rollback_reason", sa.Text, nullable=True),
    )
    op.create_index("idx_deployments_status", "deployments", ["status"])
    op.create_index("idx_deployments_intervention", "deployments", ["intervention_id"])

    # Model Versions
    op.create_table(
        "model_versions",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("version", sa.String(100), nullable=False, unique=True),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column("model_metadata", postgresql.JSONB, nullable=True),
        sa.Column(
            "registered_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("idx_model_versions_version", "model_versions", ["version"])

    # Audit Log (new)
    op.create_table(
        "audit_log",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "timestamp", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column("actor_type", sa.String(50), nullable=False),
        sa.Column("actor_id", sa.String(100), nullable=True),
        sa.Column("session_id", sa.String(100), nullable=True),
        sa.Column("mode", sa.String(20), nullable=True),
        sa.Column("target_type", sa.String(50), nullable=True),
        sa.Column("target_id", sa.String(100), nullable=True),
        sa.Column("severity", sa.String(5), nullable=True),
        sa.Column("risk_tier", sa.String(10), nullable=True),
        sa.Column("action_type", sa.String(50), nullable=True),
        sa.Column("event_data", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("success", sa.Boolean, nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("duration_ms", sa.Integer, nullable=True),
        sa.Column("estimated_cost_usd", sa.Float, nullable=True),
        sa.Column("actual_cost_usd", sa.Float, nullable=True),
    )
    op.create_index("idx_audit_event_type", "audit_log", ["event_type"])
    op.create_index("idx_audit_timestamp", "audit_log", ["timestamp"])
    op.create_index("idx_audit_session", "audit_log", ["session_id"])
    op.create_index("idx_audit_actor", "audit_log", ["actor_type", "actor_id"])
    op.create_index("idx_audit_target", "audit_log", ["target_type", "target_id"])
    op.create_index("idx_audit_mode_time", "audit_log", ["mode", "timestamp"])

    # Approval Decisions (new)
    op.create_table(
        "approval_decisions",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("audit_log_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column(
            "timestamp", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("request_id", sa.String(100), nullable=False),
        sa.Column("action_type", sa.String(50), nullable=False),
        sa.Column("action_description", sa.Text, nullable=False),
        sa.Column("risk_tier", sa.String(10), nullable=False),
        sa.Column("severity", sa.String(5), nullable=False),
        sa.Column("risk_reasoning", sa.Text, nullable=True),
        sa.Column("decision", sa.String(20), nullable=False),
        sa.Column("decided_by", sa.String(100), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decision_reason", sa.Text, nullable=True),
        sa.Column("mode", sa.String(20), nullable=False),
        sa.Column("session_id", sa.String(100), nullable=True),
        sa.Column("requester_agent", sa.String(100), nullable=True),
        sa.Column("estimated_cost_usd", sa.Float, nullable=True),
        sa.Column("affected_systems", postgresql.JSONB, nullable=True),
        sa.Column("rollback_plan", sa.Text, nullable=True),
    )
    op.create_index("idx_approval_decision", "approval_decisions", ["decision"])
    op.create_index("idx_approval_timestamp", "approval_decisions", ["timestamp"])
    op.create_index("idx_approval_request", "approval_decisions", ["request_id"])
    op.create_index("idx_approval_mode_time", "approval_decisions", ["mode", "timestamp"])

    # Mode Transitions (new)
    op.create_table(
        "mode_transitions",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("audit_log_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column(
            "timestamp", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("from_mode", sa.String(20), nullable=False),
        sa.Column("to_mode", sa.String(20), nullable=False),
        sa.Column("success", sa.Boolean, nullable=False),
        sa.Column("blocked_reason", sa.Text, nullable=True),
        sa.Column("initiated_by", sa.String(100), nullable=True),
        sa.Column("session_id", sa.String(100), nullable=True),
        sa.Column("reason", sa.Text, nullable=True),
        sa.Column("metadata", postgresql.JSONB, nullable=True),
    )
    op.create_index("idx_mode_transition_timestamp", "mode_transitions", ["timestamp"])
    op.create_index("idx_mode_transition_modes", "mode_transitions", ["from_mode", "to_mode"])

    # Tool Executions (new)
    op.create_table(
        "tool_executions",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("audit_log_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("execution_id", sa.String(100), nullable=False),
        sa.Column(
            "timestamp", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("tool_name", sa.String(100), nullable=False),
        sa.Column("action_type", sa.String(50), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("mode", sa.String(20), nullable=False),
        sa.Column("session_id", sa.String(100), nullable=True),
        sa.Column("requester_agent", sa.String(100), nullable=True),
        sa.Column("input_params", postgresql.JSONB, nullable=True),
        sa.Column("output_summary", sa.Text, nullable=True),
        sa.Column("risk_tier", sa.String(10), nullable=True),
        sa.Column("severity", sa.String(5), nullable=True),
        sa.Column("approval_required", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("approval_granted", sa.Boolean, nullable=True),
        sa.Column("approval_decision_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("success", sa.Boolean, nullable=False),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("blocked", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("block_reason", sa.Text, nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Integer, nullable=True),
        sa.Column("estimated_cost_usd", sa.Float, nullable=True),
        sa.Column("actual_cost_usd", sa.Float, nullable=True),
    )
    op.create_index("idx_tool_exec_timestamp", "tool_executions", ["timestamp"])
    op.create_index("idx_tool_exec_name", "tool_executions", ["tool_name"])
    op.create_index("idx_tool_exec_mode", "tool_executions", ["mode"])
    op.create_index("idx_tool_exec_success", "tool_executions", ["success"])
    op.create_index("idx_tool_exec_id", "tool_executions", ["execution_id"])


def downgrade() -> None:
    # Drop in reverse order of creation
    op.drop_table("tool_executions")
    op.drop_table("mode_transitions")
    op.drop_table("approval_decisions")
    op.drop_table("audit_log")
    op.drop_table("model_versions")
    op.drop_table("deployments")
    op.drop_table("approvals")
    op.drop_table("simulations")
    op.drop_table("interventions")
    op.drop_table("causal_links")
    op.drop_table("failures")
    op.drop_table("experiment_runs")
    op.drop_table("experiments")
    op.drop_table("edges")
    op.drop_table("nodes")
