"""Simulation Engine - counterfactual replay for intervention testing using LLM reasoning."""

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Optional

from ..config.modes import OperatingMode
from ..integrations.model_client import ModelClient
from ..memory.graph import MemoryGraph
from ..memory.models import Node, NodeType
from ..reasoning.llm_backbone import LLMBackbone, ReasoningContext, ReasoningMode
from ..utils import generate_id, get_logger, utc_now
from .base import AgentContext, AgentResult, BaseAgent
from .intervention_engine import Intervention, InterventionType

if TYPE_CHECKING:
    from ..core.approval_handler import ApprovalHandler

logger = get_logger("simulation_engine")


class SimulationOutcome(str, Enum):
    """Possible simulation outcomes."""

    IMPROVED = "improved"  # Intervention helps
    NO_CHANGE = "no_change"  # No effect
    DEGRADED = "degraded"  # Made things worse
    SIDE_EFFECT = "side_effect"  # Unintended consequence
    INCONCLUSIVE = "inconclusive"


@dataclass
class SimulationRun:
    """A single simulation run."""

    id: str = field(default_factory=generate_id)
    run_number: int = 0

    # Baseline (without intervention)
    baseline_failure_rate: float = 0.0
    baseline_latency_ms: float = 0.0

    # With intervention
    intervention_failure_rate: float = 0.0
    intervention_latency_ms: float = 0.0

    # Comparison
    failure_rate_delta: float = 0.0  # Negative is better
    latency_delta: float = 0.0  # Negative is better

    # Side effects observed
    side_effects: list[str] = field(default_factory=list)


@dataclass
class SimulationResult:
    """Result of simulating an intervention."""

    id: str = field(default_factory=generate_id)
    intervention_id: str = ""
    failure_id: str = ""

    # Aggregate results
    outcome: SimulationOutcome = SimulationOutcome.INCONCLUSIVE
    confidence: float = 0.0

    # Metrics
    avg_failure_rate_improvement: float = 0.0
    avg_latency_impact: float = 0.0

    # Side effects
    side_effects_observed: list[str] = field(default_factory=list)
    regressions_observed: list[str] = field(default_factory=list)

    # Individual runs
    runs: list[SimulationRun] = field(default_factory=list)

    # Recommendation
    deploy_recommended: bool = False
    recommendation_reason: str = ""


class SimulationEngine(BaseAgent):
    """
    Simulates interventions before deployment via counterfactual replay.

    Key capability: Takes historical failure traces and replays them
    with the proposed intervention applied, comparing outcomes.

    When LLM and model client are available:
    - Actually replays prompts through model with intervention applied
    - Uses LLM to analyze whether intervention improved behavior
    - Builds statistical confidence in intervention effectiveness

    When only LLM available:
    - Uses reasoning to estimate intervention effects
    - Provides lower-confidence but still useful predictions

    This allows us to estimate intervention effectiveness before
    any production deployment.
    """

    def __init__(
        self,
        graph: MemoryGraph | None = None,
        model_client: ModelClient | None = None,
        llm_backbone: LLMBackbone | None = None,
        approval_handler: Optional["ApprovalHandler"] = None,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.graph = graph
        self.model_client = model_client
        self.llm = llm_backbone
        self.approval_handler = approval_handler

    @property
    def agent_type(self) -> str:
        return "simulation_engine"

    async def execute(self, context: AgentContext, **kwargs) -> AgentResult:
        """Simulate interventions."""
        interventions = kwargs.get("interventions", [])
        num_runs = kwargs.get("num_runs", 5)
        skip_approval = kwargs.get("skip_approval", False)

        if not interventions:
            return AgentResult(
                agent_id=self.id,
                agent_type=self.agent_type,
                success=False,
                error="No interventions provided",
            )

        results = []
        skipped = []

        for intervention in interventions:
            # Request approval for simulation if handler configured
            if self.approval_handler and not skip_approval:
                # Estimate cost based on num_runs
                estimated_cost = num_runs * 0.01  # $0.01 per run estimate

                approved = await self.approval_handler.approve_simulation(
                    failure_id=intervention.failure_id,
                    intervention_id=intervention.id,
                    trace_count=num_runs,
                    estimated_cost_usd=estimated_cost,
                    requester_agent=self.agent_type,
                )

                if not approved:
                    logger.info(f"Simulation for intervention {intervention.id} rejected")
                    skipped.append(intervention.id)
                    continue

            result = await self._simulate_intervention(context, intervention, num_runs)
            results.append(result)

        # Record to memory graph
        if self.graph:
            for result in results:
                self._record_simulation(result)

        # Summary statistics
        improved_count = sum(1 for r in results if r.outcome == SimulationOutcome.IMPROVED)
        deploy_recommended = sum(1 for r in results if r.deploy_recommended)

        return AgentResult(
            agent_id=self.id,
            agent_type=self.agent_type,
            success=True,
            data={
                "simulations_run": len(results),
                "skipped_count": len(skipped),
                "skipped_interventions": skipped,
                "improved": improved_count,
                "deploy_recommended": deploy_recommended,
                "results": [self._result_to_dict(r) for r in results],
            },
        )

    async def _simulate_intervention(
        self, context: AgentContext, intervention: Intervention, num_runs: int
    ) -> SimulationResult:
        """Run simulation for a single intervention."""
        result = SimulationResult(
            intervention_id=intervention.id,
            failure_id=intervention.failure_id,
        )

        # Get historical traces for this failure
        traces = self._get_failure_traces(intervention.failure_id)

        for i in range(num_runs):
            run = await self._run_counterfactual(intervention, traces, i + 1)
            result.runs.append(run)

        # Aggregate results
        self._aggregate_results(result)

        # Determine outcome and recommendation
        result.outcome = self._determine_outcome(result)
        result.deploy_recommended, result.recommendation_reason = self._make_recommendation(
            result, intervention, context
        )

        return result

    def _get_failure_traces(self, failure_id: str) -> list[dict]:
        """Get historical traces for a failure from memory graph or cache."""
        traces = []

        # Try to get traces from memory graph
        if self.graph:
            failure_node = self.graph.get_node(failure_id)
            if failure_node:
                # Get experiment runs linked to this failure
                run_nodes = self.graph.get_neighbors(
                    failure_id, relation=None, direction="outgoing"
                )
                for run in run_nodes:
                    if run.data.get("trace"):
                        traces.append(
                            {
                                "id": run.id,
                                "prompt": run.data.get("prompt", ""),
                                "system_prompt": run.data.get("system_prompt"),
                                "response": run.data.get("response", ""),
                                "failure_triggered": True,
                                "failure_description": failure_node.data.get("description", ""),
                                "tokens_used": run.data.get("tokens_used", 0),
                                "latency_ms": run.data.get("latency_ms", 0),
                                "tool_calls": run.data.get("tool_calls", 0),
                                "stress_type": run.data.get("stress_type", ""),
                                **run.data.get("trace", {}),
                            }
                        )

        # If no traces found, generate minimal synthetic traces
        # (allows simulation to proceed with LLM estimation)
        if not traces:
            failure_data = {}
            if self.graph:
                failure_node = self.graph.get_node(failure_id)
                if failure_node:
                    failure_data = failure_node.data

            traces = [
                {
                    "id": generate_id(),
                    "failure_triggered": True,
                    "failure_description": failure_data.get("description", "unknown failure"),
                    "tokens_used": 15000,
                    "latency_ms": 2500,
                    "tool_calls": 3,
                    "stress_type": failure_data.get("trigger_signature", ["unknown"])[0]
                    if failure_data.get("trigger_signature")
                    else "unknown",
                }
                for _ in range(3)
            ]

        return traces

    async def _run_counterfactual(
        self, intervention: Intervention, traces: list[dict], run_number: int
    ) -> SimulationRun:
        """Run a counterfactual simulation - with real model replay when available."""
        run = SimulationRun(run_number=run_number)

        # Use a trace (cycling through if needed)
        trace = traces[run_number % len(traces)]

        # Baseline metrics (from original trace)
        run.baseline_failure_rate = 1.0 if trace.get("failure_triggered") else 0.0
        run.baseline_latency_ms = trace.get("latency_ms", 2000)

        # If we have model client, do real counterfactual replay
        if self.model_client and trace.get("prompt"):
            intervention_result = await self._replay_with_intervention(intervention, trace)
        elif self.llm:
            # Use LLM reasoning to estimate intervention effect
            intervention_result = await self._estimate_intervention_effect(intervention, trace)
        else:
            # Fall back to heuristic simulation
            intervention_result = self._apply_intervention_to_trace(intervention, trace)

        run.intervention_failure_rate = intervention_result["failure_rate"]
        run.intervention_latency_ms = intervention_result["latency_ms"]

        # Calculate deltas
        run.failure_rate_delta = run.intervention_failure_rate - run.baseline_failure_rate
        run.latency_delta = run.intervention_latency_ms - run.baseline_latency_ms

        # Check for side effects
        run.side_effects = intervention_result.get("side_effects", [])

        return run

    async def _replay_with_intervention(self, intervention: Intervention, trace: dict) -> dict:
        """Actually replay the prompt with intervention applied."""
        start_time = utc_now()

        # Apply intervention to the prompt/system
        modified_prompt, modified_system = self._apply_intervention_to_prompt(
            intervention, trace.get("prompt", ""), trace.get("system_prompt")
        )

        messages = []
        if modified_system:
            messages.append({"role": "system", "content": modified_system})
        messages.append({"role": "user", "content": modified_prompt})

        try:
            response = await self.model_client.complete(
                messages=messages,
                temperature=0.7,
                max_tokens=2048,
            )

            latency_ms = int((utc_now() - start_time).total_seconds() * 1000)

            # Use LLM to analyze if intervention helped
            if self.llm:
                analysis = await self._analyze_replay_result(intervention, trace, response.content)
                failure_rate = analysis.get("failure_rate", 0.5)
                side_effects = analysis.get("side_effects", [])
            else:
                # Heuristic analysis
                failure_rate = 0.5  # Uncertain without analysis
                side_effects = []

            return {
                "failure_rate": failure_rate,
                "latency_ms": latency_ms,
                "side_effects": side_effects,
                "response": response.content,
            }

        except Exception as e:
            logger.error(f"Replay failed: {e}")
            return {
                "failure_rate": 1.0,
                "latency_ms": 0,
                "side_effects": [f"replay_error: {str(e)}"],
            }

    def _apply_intervention_to_prompt(
        self, intervention: Intervention, prompt: str, system_prompt: str | None
    ) -> tuple[str, str | None]:
        """Apply intervention to prompt/system."""
        modified_prompt = prompt
        modified_system = system_prompt or ""

        if intervention.intervention_type == InterventionType.PROMPT_PATCH:
            payload = intervention.payload
            if payload.get("position") == "system_prefix":
                addition = payload.get("prompt_addition", "")
                modified_system = f"{addition}\n\n{modified_system}"
            elif payload.get("position") == "user_prefix":
                addition = payload.get("prompt_addition", "")
                modified_prompt = f"{addition}\n\n{modified_prompt}"

        elif intervention.intervention_type == InterventionType.CONTEXT_LIMIT:
            max_tokens = intervention.payload.get("max_tokens", 100000)
            # Simple truncation (real impl would be smarter)
            if len(modified_prompt) > max_tokens * 4:  # ~4 chars per token
                modified_prompt = modified_prompt[: max_tokens * 4]

        return modified_prompt, modified_system if modified_system else None

    async def _analyze_replay_result(
        self, intervention: Intervention, original_trace: dict, new_response: str
    ) -> dict:
        """Use LLM to analyze whether intervention helped."""
        context = ReasoningContext(
            mode=ReasoningMode.FAILURE_ANALYSIS,
            observations=[
                f"Original failure: {original_trace.get('failure_description', 'unknown')}",
                f"Intervention applied: {intervention.name} ({intervention.intervention_type.value})",
                f"Original response (truncated): {original_trace.get('response', '')[:500]}",
                f"New response (truncated): {new_response[:500]}",
            ],
            task_description="""Analyze whether this intervention improved behavior.

Compare the original failing response to the new response with intervention.
Did the intervention:
1. Prevent the original failure?
2. Introduce any new issues?
3. Change behavior in unexpected ways?

Respond with JSON:
{
  "failure_rate": 0.0-1.0 (0 = no failure, 1 = complete failure),
  "improvement": true/false,
  "side_effects": ["list of any unexpected changes"],
  "analysis": "brief explanation"
}""",
        )

        result = await self.llm.reason(context)
        output = result.structured_output

        return {
            "failure_rate": output.get("failure_rate", 0.5),
            "side_effects": output.get("side_effects", []),
            "improvement": output.get("improvement", False),
        }

    async def _estimate_intervention_effect(self, intervention: Intervention, trace: dict) -> dict:
        """Use LLM reasoning to estimate intervention effect without replay."""
        context = ReasoningContext(
            mode=ReasoningMode.INTERVENTION_DESIGN,
            observations=[
                f"Failure description: {trace.get('failure_description', 'unknown')}",
                f"Stress type: {trace.get('stress_type', 'unknown')}",
                f"Intervention: {intervention.name}",
                f"Intervention type: {intervention.intervention_type.value}",
                f"Intervention payload: {intervention.payload}",
            ],
            task_description="""Estimate the likely effect of this intervention on this failure.

Without running the actual test, predict:
1. How likely is this intervention to prevent the failure? (0-1)
2. What latency impact would it have?
3. What side effects might occur?

Respond with JSON:
{
  "estimated_failure_rate": 0.0-1.0,
  "latency_multiplier": 1.0-2.0,
  "potential_side_effects": [],
  "confidence": 0.0-1.0,
  "reasoning": "brief explanation"
}""",
        )

        result = await self.llm.reason(context)
        output = result.structured_output

        original_latency = trace.get("latency_ms", 2000)
        multiplier = output.get("latency_multiplier", 1.1)

        return {
            "failure_rate": output.get("estimated_failure_rate", 0.5),
            "latency_ms": original_latency * multiplier,
            "side_effects": output.get("potential_side_effects", []),
        }

    def _apply_intervention_to_trace(self, intervention: Intervention, trace: dict) -> dict:
        """Simulate applying intervention to a trace."""
        import random

        # Effectiveness varies by intervention type
        effectiveness = {
            InterventionType.PROMPT_PATCH: 0.4,
            InterventionType.GUARDRAIL: 0.6,
            InterventionType.PARAMETER_TUNE: 0.3,
            InterventionType.TOOL_RESTRICTION: 0.7,
            InterventionType.CONTEXT_LIMIT: 0.5,
            InterventionType.RETRY_POLICY: 0.3,
            InterventionType.CIRCUIT_BREAKER: 0.8,
            InterventionType.HUMAN_REVIEW: 0.95,
        }.get(intervention.intervention_type, 0.3)

        # Base failure rate reduction
        original_failure = 1.0 if trace.get("failure_triggered") else 0.0

        # Add noise
        noise = random.gauss(0, 0.1)
        new_failure_rate = max(0, original_failure * (1 - effectiveness) + noise)

        # Latency impact
        latency_multipliers = {
            InterventionType.PROMPT_PATCH: 1.1,
            InterventionType.GUARDRAIL: 1.2,
            InterventionType.PARAMETER_TUNE: 1.0,
            InterventionType.TOOL_RESTRICTION: 0.9,
            InterventionType.CONTEXT_LIMIT: 0.8,
            InterventionType.RETRY_POLICY: 1.3,
            InterventionType.CIRCUIT_BREAKER: 1.05,
            InterventionType.HUMAN_REVIEW: 10.0,  # Significant delay
        }

        multiplier = latency_multipliers.get(intervention.intervention_type, 1.0)
        new_latency = trace.get("latency_ms", 2000) * multiplier

        # Random side effects (10% chance)
        side_effects = []
        if random.random() < 0.1:
            possible_effects = [
                "increased_token_usage",
                "reduced_tool_accuracy",
                "changed_output_format",
                "memory_usage_increase",
            ]
            side_effects.append(random.choice(possible_effects))

        return {
            "failure_rate": new_failure_rate,
            "latency_ms": new_latency,
            "side_effects": side_effects,
        }

    def _aggregate_results(self, result: SimulationResult) -> None:
        """Aggregate results from all runs."""
        if not result.runs:
            return

        # Average improvements
        failure_improvements = [-run.failure_rate_delta for run in result.runs]
        latency_impacts = [run.latency_delta for run in result.runs]

        result.avg_failure_rate_improvement = sum(failure_improvements) / len(failure_improvements)
        result.avg_latency_impact = sum(latency_impacts) / len(latency_impacts)

        # Aggregate side effects
        all_effects = set()
        for run in result.runs:
            all_effects.update(run.side_effects)
        result.side_effects_observed = list(all_effects)

        # Calculate confidence based on consistency
        if failure_improvements:
            mean = result.avg_failure_rate_improvement
            variance = sum((x - mean) ** 2 for x in failure_improvements) / len(
                failure_improvements
            )
            # Higher variance = lower confidence
            result.confidence = max(0.3, 1.0 - min(variance, 0.7))

        # Check for regressions
        if result.avg_latency_impact > 1000:  # >1s increase
            result.regressions_observed.append("significant_latency_increase")
        if result.avg_failure_rate_improvement < 0:
            result.regressions_observed.append("failure_rate_increased")

    def _determine_outcome(self, result: SimulationResult) -> SimulationOutcome:
        """Determine simulation outcome."""
        if result.regressions_observed:
            if "failure_rate_increased" in result.regressions_observed:
                return SimulationOutcome.DEGRADED
            return SimulationOutcome.SIDE_EFFECT

        if result.avg_failure_rate_improvement > 0.2:
            return SimulationOutcome.IMPROVED

        if result.avg_failure_rate_improvement > 0:
            return SimulationOutcome.NO_CHANGE

        if result.confidence < 0.5:
            return SimulationOutcome.INCONCLUSIVE

        return SimulationOutcome.NO_CHANGE

    def _make_recommendation(
        self, result: SimulationResult, intervention: Intervention, context: AgentContext
    ) -> tuple[bool, str]:
        """Make deployment recommendation."""
        # Strict criteria for production
        if context.mode == OperatingMode.PRODUCTION:
            if result.outcome != SimulationOutcome.IMPROVED:
                return False, "Only deploy improved interventions in production"
            if result.confidence < 0.7:
                return False, "Insufficient confidence for production deployment"
            if result.regressions_observed:
                return False, f"Regressions observed: {result.regressions_observed}"
            if result.avg_latency_impact > 500:
                return False, "Latency impact too high for production"
            return True, "Simulation shows clear improvement with acceptable impact"

        # More lenient for lab/shadow
        if result.outcome == SimulationOutcome.IMPROVED:
            return True, "Simulation shows improvement"
        if result.outcome == SimulationOutcome.NO_CHANGE and result.confidence > 0.5:
            return False, "No significant improvement observed"
        if result.outcome == SimulationOutcome.INCONCLUSIVE:
            return False, "Results inconclusive, more testing needed"

        return False, f"Outcome: {result.outcome.value}"

    def _record_simulation(self, result: SimulationResult) -> None:
        """Record simulation to memory graph."""
        if not self.graph:
            return

        node = Node(
            node_type=NodeType.SIMULATION,
            data={
                "intervention_id": result.intervention_id,
                "failure_id": result.failure_id,
                "outcome": result.outcome.value,
                "confidence": result.confidence,
                "avg_improvement": result.avg_failure_rate_improvement,
                "avg_latency_impact": result.avg_latency_impact,
                "deploy_recommended": result.deploy_recommended,
                "run_count": len(result.runs),
            },
        )
        self.graph.add_node(node)

    def _result_to_dict(self, result: SimulationResult) -> dict:
        """Convert result to dictionary."""
        return {
            "id": result.id,
            "intervention_id": result.intervention_id,
            "outcome": result.outcome.value,
            "confidence": result.confidence,
            "avg_failure_rate_improvement": result.avg_failure_rate_improvement,
            "avg_latency_impact": result.avg_latency_impact,
            "side_effects": result.side_effects_observed,
            "regressions": result.regressions_observed,
            "deploy_recommended": result.deploy_recommended,
            "recommendation_reason": result.recommendation_reason,
            "run_count": len(result.runs),
        }
