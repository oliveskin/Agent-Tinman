"""Complete failure taxonomy for AI model behavior."""

from enum import Enum
from dataclasses import dataclass
from typing import Optional


class FailureClass(str, Enum):
    """Primary failure class categories."""
    REASONING = "reasoning"
    LONG_CONTEXT = "long_context"
    TOOL_USE = "tool_use"
    FEEDBACK_LOOP = "feedback_loop"
    DEPLOYMENT = "deployment"


class ReasoningFailure(str, Enum):
    """Failures in model reasoning and inference."""
    SPURIOUS_INFERENCE = "spurious_inference"
    GOAL_DRIFT = "goal_drift"
    CONTRADICTION_LOOP = "contradiction_loop"
    CONTEXT_COLLAPSE = "context_collapse"
    INSTRUCTION_OVERRIDE = "instruction_override"
    LOGIC_ERROR = "logic_error"


class LongContextFailure(str, Enum):
    """Failures related to long-context processing."""
    ATTENTION_DILUTION = "attention_dilution"
    LATENT_FORGETTING = "latent_forgetting"
    RETRIEVAL_DOMINANCE = "retrieval_dominance"
    POSITION_BIAS = "position_bias"
    CONTEXT_OVERFLOW = "context_overflow"
    RECENCY_BIAS = "recency_bias"


class ToolUseFailure(str, Enum):
    """Failures in tool/function calling."""
    TOOL_HALLUCINATION = "tool_hallucination"
    CHAIN_MISORDER = "chain_misorder"
    RETRY_AMPLIFICATION = "retry_amplification"
    DESTRUCTIVE_CALL = "destructive_call"
    PARAMETER_ERROR = "parameter_error"
    TOOL_LOOP = "tool_loop"
    WRONG_TOOL_SELECTION = "wrong_tool_selection"


class FeedbackLoopFailure(str, Enum):
    """Failures in feedback/learning loops."""
    REWARD_HACKING = "reward_hacking"
    CONFIRMATION_DRIFT = "confirmation_drift"
    MEMORY_POISONING = "memory_poisoning"
    ECHO_CHAMBER = "echo_chamber"
    DISTRIBUTIONAL_SHIFT = "distributional_shift"


class DeploymentFailure(str, Enum):
    """Operational/deployment failures."""
    LATENCY_COLLAPSE = "latency_collapse"
    COST_RUNAWAY = "cost_runaway"
    SAFETY_REGRESSION = "safety_regression"
    RATE_LIMIT_EXHAUSTION = "rate_limit_exhaustion"
    CASCADING_FAILURE = "cascading_failure"
    RESOURCE_EXHAUSTION = "resource_exhaustion"


@dataclass
class FailureTypeInfo:
    """Detailed information about a failure type."""
    primary_class: FailureClass
    secondary_class: str
    description: str
    typical_severity: str
    indicators: list[str]
    mitigation_hints: list[str]


class FailureTaxonomy:
    """
    Complete failure taxonomy with metadata.

    Provides lookup, classification hints, and relationships
    between failure types.
    """

    TAXONOMY: dict[str, FailureTypeInfo] = {
        # Reasoning failures
        "spurious_inference": FailureTypeInfo(
            primary_class=FailureClass.REASONING,
            secondary_class="spurious_inference",
            description="Model hallucinates causal links that don't exist",
            typical_severity="S2",
            indicators=["unsupported_claim", "false_causation", "invented_fact"],
            mitigation_hints=["Add fact-checking step", "Require citations"],
        ),
        "goal_drift": FailureTypeInfo(
            primary_class=FailureClass.REASONING,
            secondary_class="goal_drift",
            description="Model gradually deviates from the original objective",
            typical_severity="S2",
            indicators=["off_topic", "lost_context", "wrong_objective"],
            mitigation_hints=["Periodic goal reinforcement", "Checkpoint validation"],
        ),
        "contradiction_loop": FailureTypeInfo(
            primary_class=FailureClass.REASONING,
            secondary_class="contradiction_loop",
            description="Model gets stuck in logical contradictions",
            typical_severity="S1",
            indicators=["self_contradiction", "circular_reasoning", "infinite_loop"],
            mitigation_hints=["Add contradiction detection", "Limit reasoning depth"],
        ),
        "context_collapse": FailureTypeInfo(
            primary_class=FailureClass.REASONING,
            secondary_class="context_collapse",
            description="Model ignores or loses earlier context",
            typical_severity="S2",
            indicators=["ignored_instruction", "missing_context", "reset_behavior"],
            mitigation_hints=["Context summarization", "Key point repetition"],
        ),

        # Long-context failures
        "attention_dilution": FailureTypeInfo(
            primary_class=FailureClass.LONG_CONTEXT,
            secondary_class="attention_dilution",
            description="Early content loses influence as context grows",
            typical_severity="S2",
            indicators=["early_info_ignored", "recency_preference", "attention_decay"],
            mitigation_hints=["Chunked processing", "Priority markers"],
        ),
        "latent_forgetting": FailureTypeInfo(
            primary_class=FailureClass.LONG_CONTEXT,
            secondary_class="latent_forgetting",
            description="Silent loss of constraints or instructions",
            typical_severity="S3",
            indicators=["constraint_violation", "forgotten_rule", "gradual_drift"],
            mitigation_hints=["Periodic constraint reminder", "Explicit checkpoints"],
        ),
        "retrieval_dominance": FailureTypeInfo(
            primary_class=FailureClass.LONG_CONTEXT,
            secondary_class="retrieval_dominance",
            description="RAG results overwhelm model's reasoning",
            typical_severity="S2",
            indicators=["over_reliance_on_retrieved", "ignored_instructions", "copy_paste"],
            mitigation_hints=["Balance retrieval weight", "Reason before retrieval"],
        ),

        # Tool use failures
        "tool_hallucination": FailureTypeInfo(
            primary_class=FailureClass.TOOL_USE,
            secondary_class="tool_hallucination",
            description="Model invents tools that don't exist",
            typical_severity="S2",
            indicators=["unknown_tool_call", "invented_api", "fake_function"],
            mitigation_hints=["Strict tool schema validation", "Tool inventory prompt"],
        ),
        "chain_misorder": FailureTypeInfo(
            primary_class=FailureClass.TOOL_USE,
            secondary_class="chain_misorder",
            description="Tools executed in wrong dependency order",
            typical_severity="S2",
            indicators=["dependency_error", "missing_input", "wrong_sequence"],
            mitigation_hints=["Explicit dependency graph", "Order validation"],
        ),
        "retry_amplification": FailureTypeInfo(
            primary_class=FailureClass.TOOL_USE,
            secondary_class="retry_amplification",
            description="Infinite retry loops on failing tools",
            typical_severity="S3",
            indicators=["repeated_calls", "exponential_retries", "no_backoff"],
            mitigation_hints=["Retry limits", "Exponential backoff", "Circuit breaker"],
        ),
        "destructive_call": FailureTypeInfo(
            primary_class=FailureClass.TOOL_USE,
            secondary_class="destructive_call",
            description="Model calls dangerous/destructive endpoints",
            typical_severity="S4",
            indicators=["delete_operation", "admin_action", "irreversible_call"],
            mitigation_hints=["Tool allowlisting", "Destructive action gate"],
        ),

        # Feedback loop failures
        "reward_hacking": FailureTypeInfo(
            primary_class=FailureClass.FEEDBACK_LOOP,
            secondary_class="reward_hacking",
            description="Model learns exploitative shortcuts",
            typical_severity="S3",
            indicators=["metric_gaming", "shortcut_behavior", "reward_exploitation"],
            mitigation_hints=["Diverse metrics", "Adversarial evaluation"],
        ),
        "confirmation_drift": FailureTypeInfo(
            primary_class=FailureClass.FEEDBACK_LOOP,
            secondary_class="confirmation_drift",
            description="Model over-reinforces incorrect beliefs",
            typical_severity="S2",
            indicators=["echo_chamber", "belief_amplification", "bias_increase"],
            mitigation_hints=["Diverse feedback sources", "Belief reset"],
        ),
        "memory_poisoning": FailureTypeInfo(
            primary_class=FailureClass.FEEDBACK_LOOP,
            secondary_class="memory_poisoning",
            description="Bad data becomes persistent truth",
            typical_severity="S3",
            indicators=["corrupted_memory", "false_persistent_belief", "tainted_context"],
            mitigation_hints=["Memory validation", "Source attribution"],
        ),

        # Deployment failures
        "latency_collapse": FailureTypeInfo(
            primary_class=FailureClass.DEPLOYMENT,
            secondary_class="latency_collapse",
            description="Response times exceed SLA under load",
            typical_severity="S2",
            indicators=["timeout", "sla_breach", "response_delay"],
            mitigation_hints=["Load balancing", "Request queuing", "Caching"],
        ),
        "cost_runaway": FailureTypeInfo(
            primary_class=FailureClass.DEPLOYMENT,
            secondary_class="cost_runaway",
            description="Token/API costs spiral out of control",
            typical_severity="S3",
            indicators=["token_explosion", "api_cost_spike", "budget_exceeded"],
            mitigation_hints=["Cost monitoring", "Token limits", "Circuit breaker"],
        ),
        "safety_regression": FailureTypeInfo(
            primary_class=FailureClass.DEPLOYMENT,
            secondary_class="safety_regression",
            description="Safety filters bypassed or degraded",
            typical_severity="S4",
            indicators=["filter_bypass", "harmful_output", "jailbreak_success"],
            mitigation_hints=["Safety monitoring", "Regression tests", "Multi-layer filters"],
        ),
    }

    @classmethod
    def get_info(cls, failure_type: str) -> Optional[FailureTypeInfo]:
        """Get detailed info for a failure type."""
        return cls.TAXONOMY.get(failure_type.lower())

    @classmethod
    def get_all_types(cls) -> list[str]:
        """Get all registered failure types."""
        return list(cls.TAXONOMY.keys())

    @classmethod
    def get_types_by_class(cls, failure_class: FailureClass) -> list[str]:
        """Get all failure types in a primary class."""
        return [
            k for k, v in cls.TAXONOMY.items()
            if v.primary_class == failure_class
        ]

    @classmethod
    def get_high_severity_types(cls) -> list[str]:
        """Get failure types with S3 or S4 typical severity."""
        return [
            k for k, v in cls.TAXONOMY.items()
            if v.typical_severity in ("S3", "S4")
        ]

    @classmethod
    def get_typical_severity(cls, failure_type: str) -> str:
        """Get typical severity for a failure type."""
        info = cls.TAXONOMY.get(failure_type.lower())
        return info.typical_severity if info else "S1"

    @classmethod
    def get_mitigation_hints(cls, failure_type: str) -> list[str]:
        """Get mitigation hints for a failure type."""
        info = cls.TAXONOMY.get(failure_type.lower())
        return info.mitigation_hints if info else []


class Severity(Enum):
    """Severity levels for failures."""
    S0 = 0  # Negligible - cosmetic issues
    S1 = 1  # Low - minor degradation
    S2 = 2  # Medium - noticeable impact
    S3 = 3  # High - significant impact
    S4 = 4  # Critical - severe/dangerous


# Convenience class for backwards compatibility - maps primary classes to info
@dataclass
class FailureClassInfo:
    """Info about a failure class for taxonomy lookup."""
    description: str
    base_severity: Severity
    typical_triggers: list[str]


FAILURE_TAXONOMY: dict[FailureClass, FailureClassInfo] = {
    FailureClass.REASONING: FailureClassInfo(
        description="Logical errors, inconsistencies, and goal drift in model reasoning",
        base_severity=Severity.S2,
        typical_triggers=["complex_reasoning", "multi_step", "contradictory_inputs"],
    ),
    FailureClass.LONG_CONTEXT: FailureClassInfo(
        description="Attention issues, information loss, and position bias in long contexts",
        base_severity=Severity.S2,
        typical_triggers=["long_context", "many_documents", "early_information"],
    ),
    FailureClass.TOOL_USE: FailureClassInfo(
        description="Incorrect tool calls, parameter errors, and chain issues",
        base_severity=Severity.S2,
        typical_triggers=["tool_call", "function_use", "api_interaction"],
    ),
    FailureClass.FEEDBACK_LOOP: FailureClassInfo(
        description="Self-reinforcing errors, amplification cascades, and drift",
        base_severity=Severity.S3,
        typical_triggers=["feedback", "output_as_input", "iterative_processing"],
    ),
    FailureClass.DEPLOYMENT: FailureClassInfo(
        description="Infrastructure, resource, and operational failures",
        base_severity=Severity.S2,
        typical_triggers=["high_load", "resource_pressure", "concurrent_requests"],
    ),
}
