"""Pydantic models for the Tinman service API."""

from datetime import datetime
from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, Field


class ModeEnum(str, Enum):
    """Operating mode enumeration."""
    LAB = "lab"
    SHADOW = "shadow"
    PRODUCTION = "production"


class SeverityEnum(str, Enum):
    """Severity level enumeration."""
    S0 = "S0"
    S1 = "S1"
    S2 = "S2"
    S3 = "S3"
    S4 = "S4"


class RiskTierEnum(str, Enum):
    """Risk tier enumeration."""
    SAFE = "safe"
    REVIEW = "review"
    BLOCK = "block"


class DecisionEnum(str, Enum):
    """Approval decision enumeration."""
    APPROVED = "approved"
    REJECTED = "rejected"


# Request models

class ResearchCycleRequest(BaseModel):
    """Request to run a research cycle."""
    focus: Optional[str] = Field(None, description="Focus area for research")
    max_hypotheses: int = Field(5, ge=1, le=50, description="Maximum hypotheses to generate")
    max_experiments: int = Field(3, ge=1, le=20, description="Maximum experiments per hypothesis")
    runs_per_experiment: int = Field(5, ge=1, le=100, description="Runs per experiment")


class ApprovalDecisionRequest(BaseModel):
    """Request to decide on an approval."""
    decision: DecisionEnum = Field(..., description="Approval decision")
    reason: Optional[str] = Field(None, description="Reason for decision")
    decided_by: str = Field(..., description="Who made the decision")


class DiscussRequest(BaseModel):
    """Request to have a conversation with Tinman."""
    message: str = Field(..., min_length=1, description="Message to discuss")


class ModeTransitionRequest(BaseModel):
    """Request to transition operating mode."""
    target_mode: ModeEnum = Field(..., description="Target mode to transition to")
    reason: Optional[str] = Field(None, description="Reason for transition")


# Response models

class HypothesisResponse(BaseModel):
    """Hypothesis in response."""
    id: str
    target_surface: str
    expected_failure: str
    failure_class: str
    confidence: float
    priority: str
    rationale: Optional[str] = None


class ExperimentResponse(BaseModel):
    """Experiment in response."""
    id: str
    hypothesis_id: str
    name: str
    stress_type: str
    mode: str
    status: str


class FailureResponse(BaseModel):
    """Discovered failure in response."""
    id: str
    primary_class: str
    secondary_class: Optional[str] = None
    severity: str
    description: str
    reproducibility: float
    is_resolved: bool = False


class InterventionResponse(BaseModel):
    """Intervention in response."""
    id: str
    failure_id: str
    type: str
    name: str
    description: str
    risk_tier: str
    estimated_effectiveness: Optional[float] = None


class ResearchCycleResponse(BaseModel):
    """Response from a research cycle."""
    success: bool
    hypotheses_count: int
    experiments_count: int
    failures_count: int
    interventions_count: int
    hypotheses: list[HypothesisResponse] = []
    experiments: list[ExperimentResponse] = []
    failures: list[FailureResponse] = []
    interventions: list[InterventionResponse] = []
    error: Optional[str] = None


class ApprovalRequest(BaseModel):
    """Pending approval request."""
    id: str
    action_type: str
    action_description: str
    risk_tier: RiskTierEnum
    severity: SeverityEnum
    estimated_cost_usd: Optional[float] = None
    affected_systems: list[str] = []
    is_reversible: bool = True
    rollback_plan: Optional[str] = None
    requester_agent: Optional[str] = None
    created_at: datetime
    timeout_seconds: int


class PendingApprovalsResponse(BaseModel):
    """Response with pending approvals."""
    count: int
    approvals: list[ApprovalRequest]


class ApprovalDecisionResponse(BaseModel):
    """Response after approval decision."""
    success: bool
    approval_id: str
    decision: str
    message: str


class StatusResponse(BaseModel):
    """Status response."""
    mode: ModeEnum
    session_id: str
    started_at: datetime
    hypotheses_generated: int
    experiments_run: int
    failures_discovered: int
    interventions_proposed: int
    current_focus: Optional[str] = None
    has_llm: bool
    has_graph: bool
    pending_approvals: int
    approval_stats: dict[str, Any]


class HealthResponse(BaseModel):
    """Health check response."""
    status: str  # healthy, degraded, unhealthy
    version: str
    mode: ModeEnum
    database_connected: bool
    llm_available: bool
    uptime_seconds: float
    checks: dict[str, bool]


class DiscussResponse(BaseModel):
    """Response from discussion."""
    response: str
    conversation_length: int


class ReportResponse(BaseModel):
    """Response with report."""
    format: str
    content: str
    generated_at: datetime


class ErrorResponse(BaseModel):
    """Error response."""
    error: str
    detail: Optional[str] = None
    code: Optional[str] = None


class ModeTransitionResponse(BaseModel):
    """Response from mode transition."""
    success: bool
    from_mode: ModeEnum
    to_mode: ModeEnum
    message: str
    blocked_reason: Optional[str] = None
