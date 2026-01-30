"""Failure classification logic."""

from dataclasses import dataclass, field
from typing import Any, Optional
import re

from ..utils import get_logger
from .failure_types import FailureTaxonomy, FailureClass

logger = get_logger("classifiers")


@dataclass
class ClassificationResult:
    """Result of failure classification."""
    primary_class: FailureClass
    secondary_class: str
    confidence: float
    reasoning: str
    indicators_matched: list[str] = field(default_factory=list)
    suggested_severity: str = "S1"


class FailureClassifier:
    """
    Classifies failures based on traces and outputs.

    Uses heuristic rules and pattern matching.
    Can be extended with ML-based classification.
    """

    # Pattern matchers for different failure types
    PATTERNS = {
        # Reasoning failures
        "spurious_inference": [
            r"(?i)therefore.*must",
            r"(?i)clearly.*because",
            r"(?i)obviously.*so",
            r"(?i)this proves",
        ],
        "goal_drift": [
            r"(?i)instead.*i will",
            r"(?i)let me.*different",
            r"(?i)actually.*rather",
        ],
        "contradiction_loop": [
            r"(?i)but.*however.*but",
            r"(?i)yes.*no.*yes",
            r"(?i)correct.*incorrect.*correct",
        ],

        # Tool use failures
        "tool_hallucination": [
            r"(?i)calling.*\b(?!allowed_tool)\w+_tool\b",
            r"(?i)use.*\b(?!allowed_api)\w+_api\b",
        ],
        "retry_amplification": [
            r"(?i)trying again",
            r"(?i)retrying",
            r"(?i)attempt \d+",
        ],

        # Long context failures
        "attention_dilution": [
            r"(?i)as mentioned earlier",  # often wrong
            r"(?i)you said.*(?!correctly)",
        ],

        # Deployment failures
        "cost_runaway": [
            r"(?i)token limit",
            r"(?i)context length exceeded",
        ],
    }

    # Keywords that indicate specific failure classes
    KEYWORDS = {
        FailureClass.REASONING: [
            "incorrect", "wrong", "error", "mistake", "false",
            "hallucinate", "invent", "fabricate", "assume",
        ],
        FailureClass.LONG_CONTEXT: [
            "forgot", "ignore", "miss", "overlook", "skip",
            "earlier", "previous", "context", "remember",
        ],
        FailureClass.TOOL_USE: [
            "tool", "function", "api", "call", "invoke",
            "retry", "timeout", "failed", "error",
        ],
        FailureClass.FEEDBACK_LOOP: [
            "repeat", "loop", "same", "again", "stuck",
            "reinforce", "amplify", "bias",
        ],
        FailureClass.DEPLOYMENT: [
            "slow", "timeout", "cost", "expensive", "limit",
            "rate", "quota", "latency",
        ],
    }

    def __init__(self, allowed_tools: Optional[list[str]] = None):
        self.allowed_tools = allowed_tools or []

    def classify(self,
                 output: Optional[str] = None,
                 trace: Optional[dict[str, Any]] = None,
                 context: Optional[str] = None,
                 description: Optional[str] = None) -> ClassificationResult:
        """
        Classify a potential failure based on output and traces.

        Args:
            output: Model output text
            trace: Execution trace (tool calls, etc.)
            context: Original input/context

        Returns:
            ClassificationResult with class, confidence, reasoning
        """
        indicators = []
        scores: dict[str, float] = {}

        # Check patterns
        for failure_type, patterns in self.PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, text):
                    indicators.append(f"pattern:{failure_type}")
                    scores[failure_type] = scores.get(failure_type, 0) + 0.3

        # Check keywords by class
        text = output or description or ""
        output_lower = text.lower()
        class_scores: dict[FailureClass, float] = {}

        for failure_class, keywords in self.KEYWORDS.items():
            keyword_count = sum(1 for kw in keywords if kw in output_lower)
            if keyword_count > 0:
                class_scores[failure_class] = keyword_count * 0.1
                indicators.append(f"keywords:{failure_class.value}:{keyword_count}")

        # Check trace for tool use failures
        if trace:
            tool_failures = self._analyze_tool_trace(trace)
            if tool_failures:
                class_scores[FailureClass.TOOL_USE] = class_scores.get(
                    FailureClass.TOOL_USE, 0) + 0.5
                indicators.extend(tool_failures)

        # Check for context issues
        if isinstance(context, str) and context and self._check_context_issues(text, context):
            class_scores[FailureClass.LONG_CONTEXT] = class_scores.get(
                FailureClass.LONG_CONTEXT, 0) + 0.4
            indicators.append("context_mismatch")

        # Determine primary class
        if not class_scores:
            return ClassificationResult(
                primary_class=FailureClass.REASONING,
                secondary_class="unknown",
                confidence=0.1,
                reasoning="No clear failure indicators found",
                indicators_matched=indicators,
                suggested_severity="S0",
            )

        primary_class = max(class_scores, key=class_scores.get)
        confidence = min(class_scores[primary_class], 1.0)

        # Determine secondary class
        secondary_class = self._determine_secondary_class(
            primary_class, indicators, scores
        )

        # Get suggested severity
        severity = FailureTaxonomy.get_typical_severity(secondary_class)

        return ClassificationResult(
            primary_class=primary_class,
            secondary_class=secondary_class,
            confidence=confidence,
            reasoning=self._build_reasoning(primary_class, indicators),
            indicators_matched=indicators,
            suggested_severity=severity,
        )

    def _analyze_tool_trace(self, trace: dict[str, Any]) -> list[str]:
        """Analyze tool trace for failure indicators."""
        indicators = []

        tool_calls = trace.get("tool_calls", [])

        # Check for unknown tools
        for call in tool_calls:
            tool_name = call.get("name", "")
            if self.allowed_tools and tool_name not in self.allowed_tools:
                indicators.append(f"unknown_tool:{tool_name}")

        # Check for excessive retries
        retry_count = trace.get("retry_count", 0)
        if retry_count > 3:
            indicators.append(f"excessive_retries:{retry_count}")

        # Check for errors
        errors = trace.get("errors", [])
        if errors:
            indicators.append(f"tool_errors:{len(errors)}")

        return indicators

    def _check_context_issues(self, output: str, context: str) -> bool:
        """Check if output properly references context."""
        # Simple heuristic: if context mentions specific terms,
        # check if output addresses them
        context_lower = context.lower()
        output_lower = output.lower()

        # Check for explicit instructions being ignored
        instruction_markers = ["must", "always", "never", "required"]
        for marker in instruction_markers:
            if marker in context_lower and marker not in output_lower:
                return True

        return False

    def _determine_secondary_class(self,
                                    primary_class: FailureClass,
                                    indicators: list[str],
                                    scores: dict[str, float]) -> str:
        """Determine the secondary (specific) failure class."""
        # Get all types in primary class
        types_in_class = FailureTaxonomy.get_types_by_class(primary_class)

        # Check which specific types have indicators
        for failure_type in types_in_class:
            if any(failure_type in ind for ind in indicators):
                return failure_type
            if failure_type in scores and scores[failure_type] > 0:
                return failure_type

        # Default to first type in class
        return types_in_class[0] if types_in_class else "unknown"

    def _build_reasoning(self, primary_class: FailureClass,
                         indicators: list[str]) -> str:
        """Build human-readable reasoning for classification."""
        parts = [f"Classified as {primary_class.value} failure."]

        if indicators:
            parts.append(f"Matched indicators: {', '.join(indicators[:5])}")
            if len(indicators) > 5:
                parts.append(f"(+{len(indicators) - 5} more)")

        return " ".join(parts)


class EnsembleClassifier:
    """
    Ensemble of multiple classifiers for improved accuracy.

    Combines heuristic classifier with optional ML classifier.
    """

    def __init__(self):
        self.heuristic = FailureClassifier()
        self.ml_classifier = None  # Placeholder for ML model

    def classify(self,
                 output: str,
                 trace: Optional[dict[str, Any]] = None,
                 context: Optional[str] = None) -> ClassificationResult:
        """Classify using ensemble of methods."""
        # Start with heuristic
        result = self.heuristic.classify(output, trace, context)

        # If ML classifier available and confidence is low, try ML
        if self.ml_classifier and result.confidence < 0.5:
            ml_result = self._ml_classify(output, trace, context)
            if ml_result and ml_result.confidence > result.confidence:
                return ml_result

        return result

    def _ml_classify(self,
                     output: str,
                     trace: Optional[dict[str, Any]],
                     context: Optional[str]) -> Optional[ClassificationResult]:
        """ML-based classification (placeholder)."""
        # This would integrate with a trained model
        # For now, returns None to fall back to heuristic
        return None
