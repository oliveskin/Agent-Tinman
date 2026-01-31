"""Prompt library for Tinman's reasoning tasks."""

from dataclasses import dataclass


@dataclass
class PromptTemplate:
    """A reusable prompt template."""

    name: str
    template: str
    description: str


class PromptLibrary:
    """
    Library of prompts for different reasoning tasks.

    These prompts encode Tinman's research methodology and
    can be customized for specific domains or models.
    """

    # Hypothesis generation prompts
    HYPOTHESIS_FROM_BEHAVIOR = PromptTemplate(
        name="hypothesis_from_behavior",
        template="""Observe this model behavior and generate hypotheses about potential failure modes:

{behavior_description}

What failure modes might exist? Consider:
- Edge cases that weren't tested
- Adversarial inputs that could break this
- Subtle biases or inconsistencies
- Scalability concerns

Generate 3-5 testable hypotheses.""",
        description="Generate hypotheses from observed model behavior",
    )

    HYPOTHESIS_FROM_FAILURE = PromptTemplate(
        name="hypothesis_from_failure",
        template="""We observed this failure:

{failure_description}

Generate hypotheses about:
1. Related failure modes (what else might fail similarly?)
2. Root causes (what underlying issue caused this?)
3. Evolution (how might this failure mutate over time?)

Be specific and testable.""",
        description="Generate hypotheses from observed failures",
    )

    HYPOTHESIS_ADVERSARIAL = PromptTemplate(
        name="hypothesis_adversarial",
        template="""Think like an adversary trying to break this system:

{system_description}

What attacks or edge cases could cause failures? Consider:
- Prompt injection vectors
- Context manipulation
- Tool/API abuse
- State corruption
- Resource exhaustion

Generate adversarial hypotheses to test.""",
        description="Generate adversarial test hypotheses",
    )

    # Analysis prompts
    FAILURE_DEEP_DIVE = PromptTemplate(
        name="failure_deep_dive",
        template="""Analyze this failure in depth:

{failure_trace}

Questions to answer:
1. What is the exact failure mode?
2. What was the model trying to do?
3. Where did it go wrong?
4. Is this a capability limitation or a bug?
5. How reproducible is this likely to be?

Provide a detailed technical analysis.""",
        description="Deep dive analysis of a specific failure",
    )

    PATTERN_RECOGNITION = PromptTemplate(
        name="pattern_recognition",
        template="""Look at these failures and identify patterns:

{failures_list}

What patterns do you notice?
- Common triggers
- Shared characteristics
- Temporal patterns
- Correlation with inputs

Synthesize into actionable patterns.""",
        description="Identify patterns across multiple failures",
    )

    # Intervention prompts
    INTERVENTION_BRAINSTORM = PromptTemplate(
        name="intervention_brainstorm",
        template="""We need to fix this failure:

{failure_description}

Root cause analysis:
{root_cause}

Brainstorm interventions. Be creative but practical:
- What prompt changes could help?
- What guardrails would catch this?
- What parameter adjustments might work?
- What architectural changes would prevent this?

For each idea, note the tradeoffs.""",
        description="Brainstorm intervention ideas",
    )

    INTERVENTION_EVALUATE = PromptTemplate(
        name="intervention_evaluate",
        template="""Evaluate this proposed intervention:

Intervention: {intervention_description}
For failure: {failure_description}

Assess:
1. Likelihood of fixing the issue (0-100%)
2. Potential side effects
3. Implementation complexity
4. Reversibility
5. Risk level

Provide a clear recommendation.""",
        description="Evaluate a proposed intervention",
    )

    # Synthesis prompts
    WEEKLY_SYNTHESIS = PromptTemplate(
        name="weekly_synthesis",
        template="""Synthesize this week's research findings:

Failures discovered: {failure_count}
Experiments run: {experiment_count}
Interventions proposed: {intervention_count}

Key findings:
{findings_list}

Write a weekly research summary for the team. Include:
- Most important discoveries
- Patterns observed
- Recommendations
- Next week's priorities""",
        description="Weekly research synthesis",
    )

    STRATEGIC_INSIGHT = PromptTemplate(
        name="strategic_insight",
        template="""Based on our research so far:

{research_summary}

What strategic insights can we draw?
- What does this tell us about the model's limitations?
- What changes to training/architecture might help?
- What deployment safeguards are needed?
- What research directions should we prioritize?

Think big picture.""",
        description="Generate strategic insights from research",
    )

    # Collaboration prompts
    EXPLAIN_FINDING = PromptTemplate(
        name="explain_finding",
        template="""Explain this finding to a colleague:

{finding}

They asked: {question}

Provide a clear, technical explanation. Use examples where helpful.
If you're uncertain about something, say so.""",
        description="Explain a finding in response to a question",
    )

    DEBATE_HYPOTHESIS = PromptTemplate(
        name="debate_hypothesis",
        template="""A colleague proposed this hypothesis:

{hypothesis}

Your job is to steelman AND critique it:

Steelman (best case for this hypothesis):
- Why might this be true?
- What evidence supports it?

Critique (potential issues):
- What might be wrong with this?
- What's missing?
- What would disprove it?

Be intellectually honest in both directions.""",
        description="Debate the merits of a hypothesis",
    )

    @classmethod
    def get(cls, name: str) -> PromptTemplate | None:
        """Get a prompt template by name."""
        for attr_name in dir(cls):
            attr = getattr(cls, attr_name)
            if isinstance(attr, PromptTemplate) and attr.name == name:
                return attr
        return None

    @classmethod
    def list_all(cls) -> list[PromptTemplate]:
        """List all available prompt templates."""
        templates = []
        for attr_name in dir(cls):
            attr = getattr(cls, attr_name)
            if isinstance(attr, PromptTemplate):
                templates.append(attr)
        return templates

    @classmethod
    def format(cls, name: str, **kwargs) -> str:
        """Get and format a prompt template."""
        template = cls.get(name)
        if template is None:
            raise ValueError(f"Unknown prompt template: {name}")
        return template.template.format(**kwargs)
