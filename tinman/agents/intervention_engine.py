"""Intervention Engine - proposes fixes for discovered failures using LLM reasoning."""

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any, Optional

from ..config.modes import OperatingMode
from ..core.risk_evaluator import RiskEvaluator, RiskTier
from ..memory.graph import MemoryGraph
from ..reasoning.llm_backbone import LLMBackbone, ReasoningContext, ReasoningMode
from ..taxonomy.failure_types import FailureClass, Severity
from ..utils import generate_id, get_logger
from .base import AgentContext, AgentResult, BaseAgent
from .failure_discovery import DiscoveredFailure

if TYPE_CHECKING:
    from ..core.approval_handler import ApprovalHandler

logger = get_logger("intervention_engine")


class InterventionType(str, Enum):
    """Types of interventions."""

    PROMPT_PATCH = "prompt_patch"  # Modify system prompt
    GUARDRAIL = "guardrail"  # Add input/output filter
    PARAMETER_TUNE = "parameter_tune"  # Adjust model parameters
    TOOL_RESTRICTION = "tool_restriction"  # Restrict tool access
    CONTEXT_LIMIT = "context_limit"  # Limit context window
    RETRY_POLICY = "retry_policy"  # Change retry behavior
    CIRCUIT_BREAKER = "circuit_breaker"  # Add failure circuit breaker
    HUMAN_REVIEW = "human_review"  # Route to human review


@dataclass
class Intervention:
    """A proposed intervention to address a failure."""

    id: str = field(default_factory=generate_id)
    failure_id: str = ""

    # Intervention details
    intervention_type: InterventionType = InterventionType.PROMPT_PATCH
    name: str = ""
    description: str = ""

    # The actual fix
    payload: dict[str, Any] = field(default_factory=dict)

    # Expected impact
    expected_gains: dict[str, float] = field(default_factory=dict)
    expected_regressions: dict[str, float] = field(default_factory=dict)

    # Risk assessment
    risk_tier: RiskTier = RiskTier.REVIEW
    risk_factors: list[str] = field(default_factory=list)

    # Metadata
    rationale: str = ""
    requires_approval: bool = True
    reversible: bool = True


class InterventionEngine(BaseAgent):
    """
    Proposes interventions to address discovered failures using LLM-powered reasoning.

    When LLM backbone is available, this agent:
    - Generates creative, tailored interventions for specific failures
    - Reasons about trade-offs and unintended consequences
    - Designs actual prompt patches, guardrail rules, etc.
    - Learns from intervention effectiveness over time

    Responsibilities:
    - Generate intervention candidates (LLM-powered or template-based)
    - Assess risk of each intervention
    - Estimate expected gains and regressions
    - Prioritize interventions by net benefit
    """

    # Intervention templates by failure class (fallback when no LLM)
    INTERVENTION_TEMPLATES = {
        FailureClass.REASONING: [
            {
                "type": InterventionType.PROMPT_PATCH,
                "name": "reasoning_scaffold",
                "description": "Add structured reasoning scaffold to system prompt",
                "payload_template": {
                    "prompt_addition": "Think step by step. For each step, explain your reasoning before proceeding.",
                    "position": "system_prefix",
                },
            },
            {
                "type": InterventionType.PARAMETER_TUNE,
                "name": "temperature_reduction",
                "description": "Reduce temperature for more consistent reasoning",
                "payload_template": {
                    "parameter": "temperature",
                    "from_value": 0.7,
                    "to_value": 0.3,
                },
            },
        ],
        FailureClass.LONG_CONTEXT: [
            {
                "type": InterventionType.CONTEXT_LIMIT,
                "name": "context_truncation",
                "description": "Implement intelligent context truncation",
                "payload_template": {
                    "max_tokens": 100000,
                    "strategy": "recency_weighted",
                    "preserve_system": True,
                },
            },
            {
                "type": InterventionType.PROMPT_PATCH,
                "name": "summary_checkpoint",
                "description": "Add periodic summary checkpoints",
                "payload_template": {
                    "checkpoint_interval": 10000,
                    "summary_prompt": "Summarize key information so far before continuing.",
                },
            },
        ],
        FailureClass.TOOL_USE: [
            {
                "type": InterventionType.GUARDRAIL,
                "name": "tool_input_validation",
                "description": "Add input validation for tool calls",
                "payload_template": {
                    "validation_type": "schema",
                    "reject_on_fail": True,
                },
            },
            {
                "type": InterventionType.TOOL_RESTRICTION,
                "name": "tool_allowlist",
                "description": "Restrict to allowlisted tools",
                "payload_template": {
                    "mode": "allowlist",
                    "allowed_tools": [],  # To be filled
                },
            },
        ],
        FailureClass.FEEDBACK_LOOP: [
            {
                "type": InterventionType.CIRCUIT_BREAKER,
                "name": "loop_detector",
                "description": "Detect and break feedback loops",
                "payload_template": {
                    "similarity_threshold": 0.9,
                    "max_iterations": 5,
                    "break_action": "halt_with_warning",
                },
            },
            {
                "type": InterventionType.GUARDRAIL,
                "name": "output_filter",
                "description": "Filter outputs that could cause loops",
                "payload_template": {
                    "filter_type": "similarity_check",
                    "compare_to": "recent_inputs",
                },
            },
        ],
        FailureClass.DEPLOYMENT: [
            {
                "type": InterventionType.RETRY_POLICY,
                "name": "exponential_backoff",
                "description": "Implement exponential backoff for retries",
                "payload_template": {
                    "initial_delay_ms": 100,
                    "max_delay_ms": 30000,
                    "multiplier": 2,
                    "max_retries": 5,
                },
            },
            {
                "type": InterventionType.HUMAN_REVIEW,
                "name": "manual_escalation",
                "description": "Escalate to human review",
                "payload_template": {
                    "trigger_conditions": ["high_severity", "novel_failure"],
                    "timeout_minutes": 30,
                },
            },
        ],
    }

    def __init__(
        self,
        graph: MemoryGraph | None = None,
        risk_evaluator: RiskEvaluator | None = None,
        llm_backbone: LLMBackbone | None = None,
        approval_handler: Optional["ApprovalHandler"] = None,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.graph = graph
        self.risk_evaluator = risk_evaluator or RiskEvaluator()
        self.llm = llm_backbone
        self.approval_handler = approval_handler

    @property
    def agent_type(self) -> str:
        return "intervention_engine"

    async def execute(self, context: AgentContext, **kwargs) -> AgentResult:
        """Generate interventions for failures."""
        failures = kwargs.get("failures", [])

        if not failures:
            return AgentResult(
                agent_id=self.id,
                agent_type=self.agent_type,
                success=False,
                error="No failures provided",
            )

        interventions = []
        for failure in failures:
            if self.llm:
                # Use LLM for creative intervention design
                failure_interventions = await self._generate_with_llm(failure, context)
            else:
                # Fallback to template-based generation
                failure_interventions = self._generate_interventions(failure, context)
            interventions.extend(failure_interventions)

        # Prioritize interventions
        interventions = self._prioritize(interventions)

        # Record to memory graph
        if self.graph:
            for intervention in interventions:
                self._record_intervention(intervention)

        return AgentResult(
            agent_id=self.id,
            agent_type=self.agent_type,
            success=True,
            data={
                "intervention_count": len(interventions),
                "by_risk_tier": self._count_by_risk_tier(interventions),
                "interventions": [self._intervention_to_dict(i) for i in interventions],
                "used_llm_design": self.llm is not None,
            },
        )

    async def _generate_with_llm(
        self, failure: DiscoveredFailure, context: AgentContext
    ) -> list[Intervention]:
        """Use LLM to generate creative interventions for a failure."""
        # Build context for intervention design
        observations = [
            f"Failure class: {failure.primary_class.value}",
            f"Severity: {failure.severity.name}",
            f"Description: {failure.description}",
            f"Trigger signature: {failure.trigger_signature}",
            f"Reproducibility: {failure.reproducibility:.0%}",
        ]

        if failure.llm_analysis:
            observations.append(f"Analysis: {failure.llm_analysis}")
        if failure.contributing_factors:
            observations.append(f"Contributing factors: {', '.join(failure.contributing_factors)}")
        if failure.key_insight:
            observations.append(f"Key insight: {failure.key_insight}")

        # Add constraints based on operating mode
        constraints = {
            "operating_mode": context.mode.value,
            "requires_reversible": context.mode != OperatingMode.LAB,
            "risk_tolerance": "high" if context.mode == OperatingMode.LAB else "low",
        }

        reasoning_context = ReasoningContext(
            mode=ReasoningMode.INTERVENTION_DESIGN,
            observations=observations,
            constraints=constraints,
            task_description=f"""Design interventions to fix this {failure.severity.name} {failure.primary_class.value} failure.

The failure occurs with {failure.reproducibility:.0%} reproducibility.
Trigger: {failure.trigger_signature}

Consider interventions that are:
1. Targeted at the root cause
2. Low risk of unintended side effects
3. Reversible if possible
4. Measurable in effectiveness

Generate 2-3 intervention options with concrete implementation details.""",
        )

        result = await self.llm.reason(reasoning_context)
        output = result.structured_output

        interventions = []
        llm_interventions = output.get("interventions", [])

        for i_data in llm_interventions:
            # Map intervention type
            type_str = i_data.get("type", "prompt_patch").lower().replace(" ", "_")
            try:
                intervention_type = InterventionType(type_str)
            except ValueError:
                intervention_type = InterventionType.PROMPT_PATCH

            # Map risk tier
            risk_str = i_data.get("risk_tier", "review").lower()
            try:
                risk_tier = RiskTier(risk_str)
            except ValueError:
                risk_tier = RiskTier.REVIEW

            intervention = Intervention(
                failure_id=failure.id,
                intervention_type=intervention_type,
                name=i_data.get("name", "llm_designed_intervention"),
                description=i_data.get("description", ""),
                payload=i_data.get("payload", {}),
                expected_gains={
                    "failure_reduction": i_data.get("expected_improvement", 0.5),
                    "safety_improvement": i_data.get("expected_improvement", 0.5) * 0.8,
                },
                expected_regressions={
                    "latency_increase": 0.1,
                    "capability_reduction": 0.1,
                },
                risk_tier=risk_tier,
                risk_factors=i_data.get("potential_regressions", []),
                rationale=i_data.get("rationale", ""),
                requires_approval=(risk_tier != RiskTier.SAFE),
                reversible=True,
            )

            # Adjust risk based on operating mode
            if context.mode == OperatingMode.PRODUCTION:
                intervention.risk_tier = max(intervention.risk_tier, RiskTier.REVIEW)
                intervention.requires_approval = True

            interventions.append(intervention)

        logger.info(f"LLM generated {len(interventions)} interventions for failure {failure.id}")

        # Also add severity-based interventions
        if failure.severity.value >= Severity.S3.value:
            interventions.append(self._create_circuit_breaker(failure))
        if failure.severity.value >= Severity.S4.value:
            interventions.append(self._create_human_escalation(failure))

        return interventions

    def _generate_interventions(
        self, failure: DiscoveredFailure, context: AgentContext
    ) -> list[Intervention]:
        """Generate interventions for a failure."""
        interventions = []

        # Get templates for this failure class
        templates = self.INTERVENTION_TEMPLATES.get(failure.primary_class, [])

        for template in templates:
            intervention = self._create_from_template(template, failure)

            # Assess risk
            risk_tier, risk_factors = self._assess_risk(intervention, failure, context)
            intervention.risk_tier = risk_tier
            intervention.risk_factors = risk_factors
            intervention.requires_approval = risk_tier != RiskTier.SAFE

            # Estimate impact
            intervention.expected_gains = self._estimate_gains(intervention, failure)
            intervention.expected_regressions = self._estimate_regressions(intervention)

            interventions.append(intervention)

        # Add severity-appropriate interventions
        if failure.severity.value >= Severity.S3.value:
            interventions.append(self._create_circuit_breaker(failure))

        if failure.severity.value >= Severity.S4.value:
            interventions.append(self._create_human_escalation(failure))

        return interventions

    def _create_from_template(self, template: dict, failure: DiscoveredFailure) -> Intervention:
        """Create intervention from template."""
        return Intervention(
            failure_id=failure.id,
            intervention_type=template["type"],
            name=template["name"],
            description=template["description"],
            payload=template["payload_template"].copy(),
            rationale=f"Addressing {failure.primary_class.value} failure: {failure.description[:100]}",
        )

    def _assess_risk(
        self, intervention: Intervention, failure: DiscoveredFailure, context: AgentContext
    ) -> tuple[RiskTier, list[str]]:
        """Assess risk of an intervention."""
        factors = []

        # Intervention type risk
        high_risk_types = {
            InterventionType.PARAMETER_TUNE,
            InterventionType.TOOL_RESTRICTION,
        }

        if intervention.intervention_type in high_risk_types:
            factors.append("high_impact_intervention_type")

        # Reversibility
        if not intervention.reversible:
            factors.append("irreversible_change")

        # Mode-based risk
        if context.mode == OperatingMode.PRODUCTION:
            factors.append("production_environment")

        # Failure severity
        if failure.severity.value >= Severity.S3.value:
            factors.append("high_severity_failure")

        # Determine tier
        if "irreversible_change" in factors or "production_environment" in factors:
            return RiskTier.BLOCK, factors
        if factors:
            return RiskTier.REVIEW, factors
        return RiskTier.SAFE, factors

    def _estimate_gains(
        self, intervention: Intervention, failure: DiscoveredFailure
    ) -> dict[str, float]:
        """Estimate expected gains from intervention."""
        gains = {
            "failure_reduction": 0.0,
            "safety_improvement": 0.0,
        }

        # Base estimates by intervention type
        type_gains = {
            InterventionType.PROMPT_PATCH: {"failure_reduction": 0.4, "safety_improvement": 0.2},
            InterventionType.GUARDRAIL: {"failure_reduction": 0.6, "safety_improvement": 0.5},
            InterventionType.PARAMETER_TUNE: {"failure_reduction": 0.3, "safety_improvement": 0.1},
            InterventionType.TOOL_RESTRICTION: {
                "failure_reduction": 0.7,
                "safety_improvement": 0.6,
            },
            InterventionType.CONTEXT_LIMIT: {"failure_reduction": 0.5, "safety_improvement": 0.3},
            InterventionType.RETRY_POLICY: {"failure_reduction": 0.3, "safety_improvement": 0.2},
            InterventionType.CIRCUIT_BREAKER: {"failure_reduction": 0.8, "safety_improvement": 0.7},
            InterventionType.HUMAN_REVIEW: {"failure_reduction": 0.9, "safety_improvement": 0.9},
        }

        gains.update(type_gains.get(intervention.intervention_type, {}))

        # Adjust based on failure reproducibility
        # Higher reproducibility = more confident in fix
        gains["failure_reduction"] *= 0.5 + failure.reproducibility * 0.5

        return gains

    def _estimate_regressions(self, intervention: Intervention) -> dict[str, float]:
        """Estimate potential regressions from intervention."""
        regressions = {
            "latency_increase": 0.0,
            "capability_reduction": 0.0,
        }

        # Estimates by type
        type_regressions = {
            InterventionType.PROMPT_PATCH: {"latency_increase": 0.1, "capability_reduction": 0.05},
            InterventionType.GUARDRAIL: {"latency_increase": 0.2, "capability_reduction": 0.1},
            InterventionType.PARAMETER_TUNE: {
                "latency_increase": 0.0,
                "capability_reduction": 0.15,
            },
            InterventionType.TOOL_RESTRICTION: {
                "latency_increase": 0.0,
                "capability_reduction": 0.3,
            },
            InterventionType.CONTEXT_LIMIT: {"latency_increase": 0.0, "capability_reduction": 0.2},
            InterventionType.RETRY_POLICY: {"latency_increase": 0.3, "capability_reduction": 0.0},
            InterventionType.CIRCUIT_BREAKER: {
                "latency_increase": 0.1,
                "capability_reduction": 0.2,
            },
            InterventionType.HUMAN_REVIEW: {"latency_increase": 0.9, "capability_reduction": 0.0},
        }

        regressions.update(type_regressions.get(intervention.intervention_type, {}))
        return regressions

    def _create_circuit_breaker(self, failure: DiscoveredFailure) -> Intervention:
        """Create circuit breaker intervention for severe failures."""
        return Intervention(
            failure_id=failure.id,
            intervention_type=InterventionType.CIRCUIT_BREAKER,
            name="emergency_circuit_breaker",
            description=f"Emergency circuit breaker for {failure.severity.name} failure",
            payload={
                "trigger": failure.trigger_signature[:3],
                "action": "halt",
                "notify": True,
            },
            expected_gains={"failure_reduction": 0.9, "safety_improvement": 0.8},
            expected_regressions={"capability_reduction": 0.3},
            risk_tier=RiskTier.REVIEW,
            risk_factors=["emergency_intervention"],
            rationale="High-severity failure requires immediate protection",
        )

    def _create_human_escalation(self, failure: DiscoveredFailure) -> Intervention:
        """Create human escalation intervention for critical failures."""
        return Intervention(
            failure_id=failure.id,
            intervention_type=InterventionType.HUMAN_REVIEW,
            name="critical_escalation",
            description=f"Human escalation for {failure.severity.name} failure",
            payload={
                "escalation_level": "immediate",
                "include_context": True,
                "block_until_resolved": True,
            },
            expected_gains={"failure_reduction": 0.95, "safety_improvement": 0.95},
            expected_regressions={"latency_increase": 0.95},
            risk_tier=RiskTier.SAFE,  # Human review is always safe
            risk_factors=[],
            rationale="Critical failure requires immediate human attention",
        )

    def _prioritize(self, interventions: list[Intervention]) -> list[Intervention]:
        """Prioritize interventions by expected net benefit."""

        def score(i: Intervention) -> float:
            gains = sum(i.expected_gains.values())
            regressions = sum(i.expected_regressions.values())
            risk_penalty = {
                RiskTier.SAFE: 0,
                RiskTier.REVIEW: 0.1,
                RiskTier.BLOCK: 0.3,
            }.get(i.risk_tier, 0)
            return gains - regressions - risk_penalty

        return sorted(interventions, key=score, reverse=True)

    def _count_by_risk_tier(self, interventions: list[Intervention]) -> dict[str, int]:
        """Count interventions by risk tier."""
        counts = {tier.value: 0 for tier in RiskTier}
        for i in interventions:
            counts[i.risk_tier.value] += 1
        return counts

    def _record_intervention(self, intervention: Intervention) -> None:
        """Record intervention to memory graph."""
        if not self.graph:
            return

        self.graph.record_intervention(
            failure_id=intervention.failure_id,
            intervention_type=intervention.intervention_type.value,
            payload=intervention.payload,
            expected_gains=intervention.expected_gains,
            expected_regressions=intervention.expected_regressions,
            risk_tier=intervention.risk_tier.value,
        )

    def _intervention_to_dict(self, intervention: Intervention) -> dict:
        """Convert intervention to dictionary."""
        return {
            "id": intervention.id,
            "failure_id": intervention.failure_id,
            "type": intervention.intervention_type.value,
            "name": intervention.name,
            "description": intervention.description,
            "risk_tier": intervention.risk_tier.value,
            "requires_approval": intervention.requires_approval,
            "expected_gains": intervention.expected_gains,
            "expected_regressions": intervention.expected_regressions,
        }

    async def deploy_intervention(
        self,
        context: AgentContext,
        intervention: Intervention,
        skip_approval: bool = False,
    ) -> dict[str, Any]:
        """
        Deploy an intervention with approval flow.

        This is the critical HITL point - deploying interventions
        can affect production systems and requires human approval.

        Args:
            context: Agent context with mode info
            intervention: The intervention to deploy
            skip_approval: Skip approval check (use with caution!)

        Returns:
            Dict with deployment status and details
        """
        result = {
            "intervention_id": intervention.id,
            "status": "pending",
            "approved": False,
            "deployed": False,
            "error": None,
        }

        # Check if approval is required
        requires_approval = intervention.requires_approval and not skip_approval

        if requires_approval and self.approval_handler:
            # Calculate estimated effect from expected gains
            expected_effect = sum(intervention.expected_gains.values()) / max(
                len(intervention.expected_gains), 1
            )

            # Build rollback plan
            rollback_plan = self._build_rollback_plan(intervention)

            # Request approval
            logger.info(f"Requesting approval for intervention: {intervention.name}")
            approved = await self.approval_handler.approve_intervention(
                intervention_type=intervention.intervention_type.value,
                target_failure=intervention.failure_id,
                description=f"{intervention.name}: {intervention.description}",
                is_reversible=intervention.reversible,
                rollback_plan=rollback_plan,
                estimated_effect=expected_effect,
                requester_agent=self.agent_type,
            )

            result["approved"] = approved

            if not approved:
                result["status"] = "rejected"
                logger.info(f"Intervention {intervention.id} rejected")
                return result
        else:
            result["approved"] = True

        # Deploy the intervention
        try:
            await self._apply_intervention(intervention)
            result["deployed"] = True
            result["status"] = "deployed"
            logger.info(f"Intervention {intervention.id} deployed successfully")

            # Record deployment in graph
            if self.graph:
                self.graph.record_intervention_deployment(
                    intervention_id=intervention.id,
                    status="deployed",
                )

        except Exception as e:
            result["status"] = "failed"
            result["error"] = str(e)
            logger.error(f"Intervention deployment failed: {e}")

        return result

    def _build_rollback_plan(self, intervention: Intervention) -> str:
        """Build a rollback plan description for an intervention."""
        if not intervention.reversible:
            return (
                "WARNING: This intervention is not reversible. Manual intervention may be required."
            )

        type_rollbacks = {
            InterventionType.PROMPT_PATCH: "Remove the prompt modification and restore original system prompt",
            InterventionType.GUARDRAIL: "Disable the guardrail filter and restore direct passthrough",
            InterventionType.PARAMETER_TUNE: "Revert parameter to original value",
            InterventionType.TOOL_RESTRICTION: "Remove tool restriction and restore full access",
            InterventionType.CONTEXT_LIMIT: "Remove context limit and restore default window",
            InterventionType.RETRY_POLICY: "Revert to original retry policy",
            InterventionType.CIRCUIT_BREAKER: "Disable circuit breaker and restore normal flow",
            InterventionType.HUMAN_REVIEW: "Remove human review requirement",
        }

        base_plan = type_rollbacks.get(
            intervention.intervention_type, "Revert changes and restore previous configuration"
        )

        return f"{base_plan}. Intervention ID: {intervention.id}"

    async def _apply_intervention(self, intervention: Intervention) -> dict[str, Any]:
        """
        Apply an intervention to the target system.

        This method handles each InterventionType with appropriate logging
        and returns a result dict describing what was applied.

        Args:
            intervention: The intervention to apply

        Returns:
            Dict with applied status, intervention type, payload, and message

        Raises:
            NotImplementedError: For unrecognized intervention types
        """
        # Audit trail logging - log the start of intervention application
        logger.info(
            "intervention_application_started",
            intervention_id=intervention.id,
            intervention_name=intervention.name,
            intervention_type=intervention.intervention_type.value,
            failure_id=intervention.failure_id,
        )

        intervention_type = intervention.intervention_type
        payload = intervention.payload

        if intervention_type == InterventionType.PROMPT_PATCH:
            message = f"Prompt patch would be applied: position={payload.get('position', 'unknown')}, addition_length={len(str(payload.get('prompt_addition', '')))}"
            logger.info(
                "applying_prompt_patch",
                intervention_id=intervention.id,
                position=payload.get("position"),
                prompt_addition_preview=str(payload.get("prompt_addition", ""))[:100],
                payload=payload,
            )

        elif intervention_type == InterventionType.GUARDRAIL:
            message = f"Guardrail would be added: type={payload.get('validation_type', payload.get('filter_type', 'unknown'))}"
            logger.info(
                "applying_guardrail",
                intervention_id=intervention.id,
                validation_type=payload.get("validation_type"),
                filter_type=payload.get("filter_type"),
                reject_on_fail=payload.get("reject_on_fail"),
                payload=payload,
            )

        elif intervention_type == InterventionType.PARAMETER_TUNE:
            param_name = payload.get("parameter", "unknown")
            from_val = payload.get("from_value")
            to_val = payload.get("to_value")
            message = f"Parameter '{param_name}' would be changed from {from_val} to {to_val}"
            logger.info(
                "applying_parameter_tune",
                intervention_id=intervention.id,
                parameter=param_name,
                from_value=from_val,
                to_value=to_val,
                payload=payload,
            )

        elif intervention_type == InterventionType.TOOL_RESTRICTION:
            mode = payload.get("mode", "unknown")
            allowed_tools = payload.get("allowed_tools", [])
            blocked_tools = payload.get("blocked_tools", [])
            message = f"Tool restriction would be applied: mode={mode}, allowed={len(allowed_tools)}, blocked={len(blocked_tools)}"
            logger.info(
                "applying_tool_restriction",
                intervention_id=intervention.id,
                restriction_mode=mode,
                allowed_tools=allowed_tools,
                blocked_tools=blocked_tools,
                payload=payload,
            )

        elif intervention_type == InterventionType.CONTEXT_LIMIT:
            max_tokens = payload.get("max_tokens")
            strategy = payload.get("strategy", "unknown")
            message = (
                f"Context limit would be changed: max_tokens={max_tokens}, strategy={strategy}"
            )
            logger.info(
                "applying_context_limit",
                intervention_id=intervention.id,
                max_tokens=max_tokens,
                strategy=strategy,
                preserve_system=payload.get("preserve_system"),
                payload=payload,
            )

        elif intervention_type == InterventionType.RETRY_POLICY:
            max_retries = payload.get("max_retries")
            initial_delay = payload.get("initial_delay_ms")
            max_delay = payload.get("max_delay_ms")
            message = f"Retry policy would be changed: max_retries={max_retries}, initial_delay={initial_delay}ms, max_delay={max_delay}ms"
            logger.info(
                "applying_retry_policy",
                intervention_id=intervention.id,
                max_retries=max_retries,
                initial_delay_ms=initial_delay,
                max_delay_ms=max_delay,
                multiplier=payload.get("multiplier"),
                payload=payload,
            )

        elif intervention_type == InterventionType.CIRCUIT_BREAKER:
            trigger = payload.get("trigger")
            action = payload.get("action", "unknown")
            message = f"Circuit breaker would be configured: action={action}, notify={payload.get('notify', False)}"
            logger.info(
                "applying_circuit_breaker",
                intervention_id=intervention.id,
                trigger=trigger,
                action=action,
                notify=payload.get("notify"),
                similarity_threshold=payload.get("similarity_threshold"),
                max_iterations=payload.get("max_iterations"),
                payload=payload,
            )

        elif intervention_type == InterventionType.HUMAN_REVIEW:
            escalation_level = payload.get("escalation_level", "standard")
            block_until_resolved = payload.get("block_until_resolved", False)
            message = f"Escalation to human review: level={escalation_level}, blocking={block_until_resolved}"
            logger.info(
                "applying_human_review_escalation",
                intervention_id=intervention.id,
                escalation_level=escalation_level,
                include_context=payload.get("include_context"),
                block_until_resolved=block_until_resolved,
                trigger_conditions=payload.get("trigger_conditions"),
                timeout_minutes=payload.get("timeout_minutes"),
                payload=payload,
            )

        else:
            # Unrecognized intervention type
            logger.error(
                "unrecognized_intervention_type",
                intervention_id=intervention.id,
                intervention_type=str(intervention_type),
            )
            raise NotImplementedError(
                f"Unrecognized intervention type: {intervention_type}. "
                f"Supported types are: {[t.value for t in InterventionType]}"
            )

        # Build result dict
        result = {
            "applied": True,
            "intervention_type": intervention_type.value,
            "payload": payload,
            "message": message,
        }

        # Audit trail logging - log successful application
        logger.info(
            "intervention_application_completed",
            intervention_id=intervention.id,
            intervention_name=intervention.name,
            intervention_type=intervention_type.value,
            message=message,
            success=True,
        )

        return result
