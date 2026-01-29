"""LLM Backbone - the reasoning core that powers Tinman's intelligence."""

from dataclasses import dataclass, field
from typing import Any, Optional
from enum import Enum

from ..integrations.model_client import ModelClient, ModelResponse
from ..utils import generate_id, utc_now, get_logger

logger = get_logger("llm_backbone")


class ReasoningMode(str, Enum):
    """Types of reasoning tasks."""
    HYPOTHESIS_GENERATION = "hypothesis_generation"
    FAILURE_ANALYSIS = "failure_analysis"
    ROOT_CAUSE_ANALYSIS = "root_cause_analysis"
    INTERVENTION_DESIGN = "intervention_design"
    INSIGHT_SYNTHESIS = "insight_synthesis"
    EXPERIMENT_DESIGN = "experiment_design"
    DIALOGUE = "dialogue"


@dataclass
class ReasoningContext:
    """Context for a reasoning task."""
    id: str = field(default_factory=generate_id)
    mode: ReasoningMode = ReasoningMode.HYPOTHESIS_GENERATION

    # Input data
    observations: list[dict[str, Any]] = field(default_factory=list)
    prior_knowledge: list[str] = field(default_factory=list)
    constraints: dict[str, Any] = field(default_factory=dict)

    # Task-specific data
    task_description: str = ""
    focus_areas: list[str] = field(default_factory=list)

    # Conversation history for multi-turn reasoning
    history: list[dict[str, str]] = field(default_factory=list)


@dataclass
class ReasoningResult:
    """Result from a reasoning task."""
    id: str = field(default_factory=generate_id)
    mode: ReasoningMode = ReasoningMode.HYPOTHESIS_GENERATION

    # Output
    content: str = ""
    structured_output: dict[str, Any] = field(default_factory=dict)

    # Metadata
    confidence: float = 0.0
    reasoning_trace: str = ""
    tokens_used: int = 0

    # For learning
    should_remember: bool = False
    key_insights: list[str] = field(default_factory=list)


class LLMBackbone:
    """
    The reasoning core that powers all of Tinman's intelligence.

    This is what transforms Tinman from a template-driven automation
    tool into an actual AI Forward Deployed Researcher capable of:

    - Generating novel hypotheses by reasoning about observations
    - Analyzing failures with genuine understanding
    - Synthesizing insights in natural language
    - Engaging in collaborative dialogue
    - Learning from its discoveries
    """

    # System prompt that defines Tinman's identity and capabilities
    SYSTEM_PROMPT = """You are Tinman, an AI Forward Deployed Researcher specializing in discovering and addressing failure modes in AI systems.

Your role is to:
1. EXPLORE how models behave in complex real-world scenarios
2. SURFACE subtle failure modes that others miss
3. DESIGN interventions that improve model reliability
4. SYNTHESIZE insights that inform model development

You think like a researcher:
- You form hypotheses based on observations
- You design experiments to test those hypotheses
- You analyze results with intellectual honesty
- You communicate findings clearly and actionably

You are embedded with AI teams to help them understand their models better. Your insights directly shape how advanced AI systems work.

Be rigorous. Be curious. Be direct."""

    def __init__(self,
                 model_client: ModelClient,
                 temperature: float = 0.7,
                 max_tokens: int = 4096):
        self.client = model_client
        self.temperature = temperature
        self.max_tokens = max_tokens
        self._reasoning_history: list[ReasoningResult] = []

    async def reason(self, context: ReasoningContext) -> ReasoningResult:
        """
        Perform a reasoning task.

        This is the core method that all Tinman intelligence flows through.
        """
        # Build the prompt based on reasoning mode
        prompt = self._build_prompt(context)

        # Add conversation history if present
        messages = [{"role": "system", "content": self.SYSTEM_PROMPT}]
        messages.extend(context.history)
        messages.append({"role": "user", "content": prompt})

        # Call the LLM
        response = await self.client.complete(
            messages=messages,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )

        # Parse and structure the response
        result = self._parse_response(response, context.mode)

        # Store for learning
        self._reasoning_history.append(result)

        logger.info(f"Reasoning complete: {context.mode.value}, confidence={result.confidence:.2f}")

        return result

    async def dialogue(self,
                       user_message: str,
                       context: Optional[ReasoningContext] = None) -> ReasoningResult:
        """
        Engage in collaborative dialogue.

        This enables Tinman to:
        - Answer questions about its findings
        - Explain its reasoning
        - Discuss strategic directions
        - Collaborate with human researchers
        """
        if context is None:
            context = ReasoningContext(mode=ReasoningMode.DIALOGUE)

        context.task_description = user_message
        context.mode = ReasoningMode.DIALOGUE

        return await self.reason(context)

    def _build_prompt(self, context: ReasoningContext) -> str:
        """Build prompt based on reasoning mode."""

        if context.mode == ReasoningMode.HYPOTHESIS_GENERATION:
            return self._build_hypothesis_prompt(context)

        elif context.mode == ReasoningMode.FAILURE_ANALYSIS:
            return self._build_failure_analysis_prompt(context)

        elif context.mode == ReasoningMode.ROOT_CAUSE_ANALYSIS:
            return self._build_root_cause_prompt(context)

        elif context.mode == ReasoningMode.INTERVENTION_DESIGN:
            return self._build_intervention_prompt(context)

        elif context.mode == ReasoningMode.INSIGHT_SYNTHESIS:
            return self._build_insight_prompt(context)

        elif context.mode == ReasoningMode.EXPERIMENT_DESIGN:
            return self._build_experiment_prompt(context)

        elif context.mode == ReasoningMode.DIALOGUE:
            return self._build_dialogue_prompt(context)

        else:
            return context.task_description

    def _build_hypothesis_prompt(self, context: ReasoningContext) -> str:
        """Build prompt for hypothesis generation."""
        observations_text = "\n".join(
            f"- {obs.get('description', obs)}"
            for obs in context.observations
        )

        prior_text = "\n".join(f"- {p}" for p in context.prior_knowledge) if context.prior_knowledge else "None available"

        focus_text = ", ".join(context.focus_areas) if context.focus_areas else "general model behavior"

        return f"""Generate hypotheses about potential failure modes based on these observations.

## Observations
{observations_text}

## Prior Knowledge
{prior_text}

## Focus Areas
{focus_text}

## Task
Reason about what failure modes might exist based on these observations. Think like a researcher:

1. What patterns do you notice in the observations?
2. What underlying issues might cause these patterns?
3. What hasn't been tested yet that could reveal failures?
4. What edge cases or adversarial scenarios should we explore?

For each hypothesis, provide:
- Target surface (what we're testing)
- Expected failure (what we expect to go wrong)
- Confidence (0-1, how confident are you)
- Rationale (why you believe this)
- Suggested experiment (how to test it)

Format your response as JSON:
```json
{{
  "reasoning": "Your chain of thought...",
  "hypotheses": [
    {{
      "target_surface": "...",
      "expected_failure": "...",
      "confidence": 0.X,
      "rationale": "...",
      "suggested_experiment": "..."
    }}
  ]
}}
```"""

    def _build_failure_analysis_prompt(self, context: ReasoningContext) -> str:
        """Build prompt for failure analysis."""
        observations_text = "\n".join(
            f"- {obs}" for obs in context.observations
        )

        return f"""Analyze these failure observations and provide a deep understanding of what went wrong.

## Failure Observations
{observations_text}

## Task
Perform a thorough failure analysis:

1. **What happened?** - Describe the failure in precise terms
2. **Why did it happen?** - Identify contributing factors
3. **What type of failure is this?** - Classify using the taxonomy:
   - REASONING: Logical errors, inconsistencies, goal drift
   - LONG_CONTEXT: Attention issues, information loss
   - TOOL_USE: Incorrect tool calls, parameter errors
   - FEEDBACK_LOOP: Amplification, self-reinforcing errors
   - DEPLOYMENT: Infrastructure, resource issues

4. **How severe is this?** - Rate S0 (negligible) to S4 (critical)
5. **Is this novel?** - Have we seen this failure pattern before?
6. **What's the reproducibility?** - Likely to recur?

Format your response as JSON:
```json
{{
  "analysis": "Your detailed analysis...",
  "classification": {{
    "primary_class": "...",
    "secondary_class": "...",
    "severity": "S0-S4",
    "is_novel": true/false,
    "reproducibility_estimate": 0.X
  }},
  "contributing_factors": ["..."],
  "key_insight": "The most important thing we learned..."
}}
```"""

    def _build_root_cause_prompt(self, context: ReasoningContext) -> str:
        """Build prompt for root cause analysis."""
        observations_text = "\n".join(
            f"- {obs}" for obs in context.observations
        )

        return f"""Perform root cause analysis on this failure.

## Failure Details
{observations_text}

## Task
Trace backwards from the observed failure to identify root causes.

Use the "5 Whys" approach:
1. Why did this failure occur? → [immediate cause]
2. Why did that happen? → [contributing factor]
3. Why? → [deeper cause]
4. Why? → [systemic issue]
5. Why? → [root cause]

Consider these cause categories:
- MODEL_BEHAVIOR: Inherent model limitations
- POLICY: Rule or constraint issues
- INFRASTRUCTURE: System/resource problems
- DATA: Training or context data issues
- CONFIGURATION: Parameter/setting problems
- EXTERNAL: Third-party dependencies

Format your response as JSON:
```json
{{
  "causal_chain": [
    {{"depth": 1, "cause": "...", "type": "...", "confidence": 0.X}},
    ...
  ],
  "root_cause": {{
    "description": "...",
    "type": "...",
    "confidence": 0.X,
    "evidence": ["..."]
  }},
  "actionable_insight": "What we should do about this..."
}}
```"""

    def _build_intervention_prompt(self, context: ReasoningContext) -> str:
        """Build prompt for intervention design."""
        observations_text = "\n".join(
            f"- {obs}" for obs in context.observations
        )

        constraints_text = "\n".join(
            f"- {k}: {v}" for k, v in context.constraints.items()
        ) if context.constraints else "No specific constraints"

        return f"""Design interventions to address this failure.

## Failure Details
{observations_text}

## Constraints
{constraints_text}

## Task
Propose interventions that could fix or mitigate this failure.

Consider these intervention types:
- PROMPT_PATCH: Modify system prompt
- GUARDRAIL: Add input/output filtering
- PARAMETER_TUNE: Adjust model parameters
- TOOL_RESTRICTION: Limit tool access
- CONTEXT_LIMIT: Manage context window
- RETRY_POLICY: Change retry behavior
- CIRCUIT_BREAKER: Add failure detection
- HUMAN_REVIEW: Route to human oversight

For each intervention:
1. What exactly would we change?
2. Why should this help?
3. What could go wrong? (potential regressions)
4. How risky is this to deploy?

Format your response as JSON:
```json
{{
  "analysis": "Your reasoning about what interventions would work...",
  "interventions": [
    {{
      "type": "...",
      "name": "...",
      "description": "...",
      "payload": {{}},
      "expected_improvement": 0.X,
      "potential_regressions": ["..."],
      "risk_tier": "safe|review|block",
      "rationale": "..."
    }}
  ],
  "recommended_intervention": "Which one to try first and why..."
}}
```"""

    def _build_insight_prompt(self, context: ReasoningContext) -> str:
        """Build prompt for insight synthesis."""
        observations_text = "\n".join(
            f"- {obs}" for obs in context.observations
        )

        prior_text = "\n".join(
            f"- {p}" for p in context.prior_knowledge
        ) if context.prior_knowledge else "None"

        return f"""Synthesize insights from these research findings.

## Recent Findings
{observations_text}

## Prior Knowledge
{prior_text}

## Task
You are preparing to communicate findings to an AI lab team. Synthesize the key insights:

1. **What did we learn?** - The most important discoveries
2. **What patterns emerged?** - Recurring themes or connections
3. **What surprised us?** - Unexpected findings
4. **What should change?** - Actionable recommendations
5. **What should we explore next?** - Open questions

Write in clear, direct prose that a technical team can act on.
Be specific. Avoid vague statements. Quantify where possible.

Format your response as:
```json
{{
  "executive_summary": "2-3 sentence overview...",
  "key_insights": [
    {{"insight": "...", "evidence": "...", "implication": "..."}}
  ],
  "patterns": ["..."],
  "surprises": ["..."],
  "recommendations": [
    {{"action": "...", "priority": "high|medium|low", "rationale": "..."}}
  ],
  "open_questions": ["..."],
  "narrative": "Full prose write-up for the team..."
}}
```"""

    def _build_experiment_prompt(self, context: ReasoningContext) -> str:
        """Build prompt for experiment design."""
        observations_text = "\n".join(
            f"- {obs}" for obs in context.observations
        )

        return f"""Design an experiment to test this hypothesis.

## Hypothesis
{context.task_description}

## Background
{observations_text}

## Task
Design a rigorous experiment to test this hypothesis:

1. **Objective**: What exactly are we trying to learn?
2. **Method**: How will we test this?
3. **Inputs**: What prompts/scenarios will we use?
4. **Expected outcomes**: What would confirm/refute the hypothesis?
5. **Controls**: How do we avoid confounding factors?
6. **Metrics**: What do we measure?

Be specific about the actual prompts or inputs to use.

Format your response as JSON:
```json
{{
  "objective": "...",
  "method": {{
    "stress_type": "...",
    "mode": "single|iterative|adversarial",
    "description": "..."
  }},
  "test_cases": [
    {{
      "name": "...",
      "input": "The actual prompt or input...",
      "expected_behavior": "...",
      "failure_indicator": "..."
    }}
  ],
  "controls": ["..."],
  "metrics": ["..."],
  "success_criteria": "How we know the hypothesis is confirmed...",
  "estimated_runs": N
}}
```"""

    def _build_dialogue_prompt(self, context: ReasoningContext) -> str:
        """Build prompt for dialogue."""
        recent_findings = "\n".join(
            f"- {obs}" for obs in context.observations[-5:]
        ) if context.observations else "No recent findings to reference"

        return f"""Respond to this message from a collaborator.

## Recent Research Context
{recent_findings}

## Message
{context.task_description}

## Task
Respond as Tinman, an AI Forward Deployed Researcher. Be:
- Direct and specific
- Grounded in your research findings
- Willing to say "I don't know" when uncertain
- Collaborative - this is a discussion, not a lecture

If asked about your findings, reference specific observations.
If asked for recommendations, be concrete and actionable.
If asked to explain your reasoning, walk through your logic step by step."""

    def _parse_response(self,
                        response: ModelResponse,
                        mode: ReasoningMode) -> ReasoningResult:
        """Parse LLM response into structured result."""
        import json
        import re

        content = response.content
        result = ReasoningResult(
            mode=mode,
            content=content,
            tokens_used=response.total_tokens,
        )

        # Try to extract JSON from response
        json_match = re.search(r'```json\s*(.*?)\s*```', content, re.DOTALL)
        if json_match:
            try:
                result.structured_output = json.loads(json_match.group(1))
            except json.JSONDecodeError:
                logger.debug("Failed to parse JSON from response")
                result.structured_output = {"raw": content}
        else:
            # Try parsing entire content as JSON
            try:
                result.structured_output = json.loads(content)
            except json.JSONDecodeError:
                result.structured_output = {"raw": content}

        # Extract confidence if present
        if "confidence" in result.structured_output:
            result.confidence = float(result.structured_output.get("confidence", 0.5))
        elif "hypotheses" in result.structured_output:
            confidences = [h.get("confidence", 0.5) for h in result.structured_output["hypotheses"]]
            result.confidence = sum(confidences) / len(confidences) if confidences else 0.5
        else:
            result.confidence = 0.7  # Default

        # Extract reasoning trace
        result.reasoning_trace = result.structured_output.get(
            "reasoning",
            result.structured_output.get("analysis", "")
        )

        # Determine if this should be remembered
        result.should_remember = mode in [
            ReasoningMode.FAILURE_ANALYSIS,
            ReasoningMode.INSIGHT_SYNTHESIS,
        ]

        # Extract key insights
        if "key_insights" in result.structured_output:
            result.key_insights = [
                i.get("insight", str(i))
                for i in result.structured_output["key_insights"]
            ]
        elif "key_insight" in result.structured_output:
            result.key_insights = [result.structured_output["key_insight"]]

        return result

    def get_reasoning_history(self, limit: int = 10) -> list[ReasoningResult]:
        """Get recent reasoning history for context."""
        return self._reasoning_history[-limit:]
