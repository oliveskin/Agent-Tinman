"""Causal linking for root cause analysis."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional

from ..utils import generate_id, utc_now, get_logger

logger = get_logger("causal_linker")


class CauseType(str, Enum):
    """Types of root causes."""
    MODEL_BEHAVIOR = "model_behavior"
    POLICY = "policy"
    INFRASTRUCTURE = "infrastructure"
    DATA = "data"
    CONFIGURATION = "configuration"
    EXTERNAL = "external"
    UNKNOWN = "unknown"


@dataclass
class CausalLink:
    """A link in the causal chain."""
    id: str = field(default_factory=generate_id)
    cause_type: CauseType = CauseType.UNKNOWN
    description: str = ""
    depth: int = 1  # 1 = immediate cause, higher = deeper
    confidence: float = 0.5
    evidence: list[str] = field(default_factory=list)
    parent_id: Optional[str] = None
    created_at: datetime = field(default_factory=utc_now)
    created_by: str = "auto"  # 'auto' or 'human:<user_id>'


@dataclass
class CausalGraph:
    """Complete causal graph for a failure."""
    failure_id: str
    root_causes: list[CausalLink] = field(default_factory=list)
    intermediate_causes: list[CausalLink] = field(default_factory=list)
    created_at: datetime = field(default_factory=utc_now)

    def get_chain(self) -> list[CausalLink]:
        """Get causal chain from failure to root cause."""
        # Sort by depth descending (root cause first)
        all_causes = self.root_causes + self.intermediate_causes
        return sorted(all_causes, key=lambda x: x.depth, reverse=True)

    def get_depth(self) -> int:
        """Get maximum depth of causal chain."""
        all_causes = self.root_causes + self.intermediate_causes
        return max((c.depth for c in all_causes), default=0)


class CausalLinker:
    """
    Builds causal graphs for failures.

    Supports both automated heuristic analysis and manual
    human-provided causation.
    """

    # Heuristic patterns for cause type detection
    CAUSE_PATTERNS = {
        CauseType.MODEL_BEHAVIOR: [
            "model", "generate", "predict", "output", "response",
            "hallucinate", "reasoning", "inference",
        ],
        CauseType.POLICY: [
            "policy", "rule", "constraint", "limit", "restrict",
            "allow", "deny", "permission",
        ],
        CauseType.INFRASTRUCTURE: [
            "timeout", "network", "connection", "server", "api",
            "rate limit", "quota", "resource",
        ],
        CauseType.DATA: [
            "data", "input", "training", "dataset", "context",
            "retrieval", "embedding", "vector",
        ],
        CauseType.CONFIGURATION: [
            "config", "setting", "parameter", "threshold",
            "temperature", "max_tokens",
        ],
        CauseType.EXTERNAL: [
            "external", "third-party", "upstream", "dependency",
            "service", "provider",
        ],
    }

    def __init__(self):
        self._graphs: dict[str, CausalGraph] = {}

    def analyze(self,
                failure_id: str,
                failure_description: str,
                trace: Optional[dict[str, Any]] = None,
                context: Optional[str] = None) -> CausalGraph:
        """
        Analyze a failure and build initial causal graph.

        This is the automated analysis - results should be
        reviewed and refined by humans for accuracy.
        """
        graph = CausalGraph(failure_id=failure_id)

        # Immediate cause from failure description
        immediate_cause = self._extract_immediate_cause(
            failure_description, trace
        )
        graph.intermediate_causes.append(immediate_cause)

        # Try to identify deeper causes
        if trace:
            deeper_causes = self._analyze_trace_for_causes(trace, immediate_cause.id)
            graph.intermediate_causes.extend(deeper_causes)

        # Attempt to identify root cause
        root_cause = self._hypothesize_root_cause(
            graph.intermediate_causes,
            failure_description,
        )
        if root_cause:
            graph.root_causes.append(root_cause)

        self._graphs[failure_id] = graph
        return graph

    def _extract_immediate_cause(self,
                                  description: str,
                                  trace: Optional[dict[str, Any]]) -> CausalLink:
        """Extract the immediate/proximate cause."""
        # Detect cause type from description
        cause_type = self._detect_cause_type(description)

        # Build evidence list
        evidence = [f"Failure description: {description[:200]}"]
        if trace:
            if "error" in trace:
                evidence.append(f"Error: {trace['error']}")
            if "tool_calls" in trace:
                evidence.append(f"Tool calls: {len(trace['tool_calls'])}")

        return CausalLink(
            cause_type=cause_type,
            description=f"Immediate cause: {description[:200]}",
            depth=1,
            confidence=0.6,
            evidence=evidence,
            created_by="auto",
        )

    def _analyze_trace_for_causes(self,
                                   trace: dict[str, Any],
                                   parent_id: str) -> list[CausalLink]:
        """Analyze execution trace for contributing causes."""
        causes = []
        depth = 2

        # Check for tool errors
        if "errors" in trace and trace["errors"]:
            for error in trace["errors"][:3]:  # Limit to 3
                causes.append(CausalLink(
                    cause_type=CauseType.INFRASTRUCTURE,
                    description=f"Tool error: {str(error)[:100]}",
                    depth=depth,
                    confidence=0.7,
                    evidence=[f"Error from trace: {error}"],
                    parent_id=parent_id,
                    created_by="auto",
                ))
                depth += 1

        # Check for retries (indicates transient issues)
        if trace.get("retry_count", 0) > 2:
            causes.append(CausalLink(
                cause_type=CauseType.INFRASTRUCTURE,
                description=f"Excessive retries: {trace['retry_count']}",
                depth=depth,
                confidence=0.6,
                evidence=["High retry count suggests instability"],
                parent_id=parent_id,
                created_by="auto",
            ))

        # Check for context issues
        if trace.get("context_length", 0) > 100000:
            causes.append(CausalLink(
                cause_type=CauseType.DATA,
                description="Very long context may cause attention issues",
                depth=depth,
                confidence=0.5,
                evidence=[f"Context length: {trace['context_length']}"],
                parent_id=parent_id,
                created_by="auto",
            ))

        return causes

    def _hypothesize_root_cause(self,
                                 intermediate_causes: list[CausalLink],
                                 description: str) -> Optional[CausalLink]:
        """Attempt to identify a root cause."""
        if not intermediate_causes:
            return None

        # Find the deepest cause
        deepest = max(intermediate_causes, key=lambda x: x.depth)
        max_depth = deepest.depth + 1

        # Aggregate cause types
        cause_types = [c.cause_type for c in intermediate_causes]

        # Determine likely root cause type
        if CauseType.INFRASTRUCTURE in cause_types:
            return CausalLink(
                cause_type=CauseType.INFRASTRUCTURE,
                description="Root cause appears to be infrastructure-related",
                depth=max_depth,
                confidence=0.4,
                evidence=["Multiple infrastructure-related intermediate causes"],
                parent_id=deepest.id,
                created_by="auto",
            )

        if CauseType.MODEL_BEHAVIOR in cause_types:
            return CausalLink(
                cause_type=CauseType.MODEL_BEHAVIOR,
                description="Root cause appears to be model behavior limitation",
                depth=max_depth,
                confidence=0.4,
                evidence=["Model behavior pattern in intermediate causes"],
                parent_id=deepest.id,
                created_by="auto",
            )

        return None

    def _detect_cause_type(self, text: str) -> CauseType:
        """Detect cause type from text using keywords."""
        text_lower = text.lower()
        scores = {}

        for cause_type, keywords in self.CAUSE_PATTERNS.items():
            score = sum(1 for kw in keywords if kw in text_lower)
            if score > 0:
                scores[cause_type] = score

        if scores:
            return max(scores, key=scores.get)
        return CauseType.UNKNOWN

    def add_manual_cause(self,
                         failure_id: str,
                         cause_type: CauseType,
                         description: str,
                         parent_id: Optional[str] = None,
                         is_root: bool = False,
                         user_id: str = "unknown") -> CausalLink:
        """
        Add a manually-identified cause.

        Human analysis is more reliable than automated detection.
        """
        graph = self._graphs.get(failure_id)
        if not graph:
            graph = CausalGraph(failure_id=failure_id)
            self._graphs[failure_id] = graph

        # Determine depth
        if parent_id:
            parent = self._find_cause(graph, parent_id)
            depth = (parent.depth + 1) if parent else 1
        else:
            existing = graph.intermediate_causes + graph.root_causes
            depth = max((c.depth for c in existing), default=0) + 1

        cause = CausalLink(
            cause_type=cause_type,
            description=description,
            depth=depth,
            confidence=0.9,  # Human-provided causes are high confidence
            evidence=["Human analysis"],
            parent_id=parent_id,
            created_by=f"human:{user_id}",
        )

        if is_root:
            graph.root_causes.append(cause)
        else:
            graph.intermediate_causes.append(cause)

        return cause

    def _find_cause(self, graph: CausalGraph, cause_id: str) -> Optional[CausalLink]:
        """Find a cause by ID in the graph."""
        for cause in graph.intermediate_causes + graph.root_causes:
            if cause.id == cause_id:
                return cause
        return None

    def get_graph(self, failure_id: str) -> Optional[CausalGraph]:
        """Get causal graph for a failure."""
        return self._graphs.get(failure_id)

    def export_graph(self, failure_id: str) -> Optional[dict[str, Any]]:
        """Export causal graph as dictionary."""
        graph = self._graphs.get(failure_id)
        if not graph:
            return None

        return {
            "failure_id": graph.failure_id,
            "created_at": graph.created_at.isoformat(),
            "max_depth": graph.get_depth(),
            "root_causes": [
                {
                    "id": c.id,
                    "type": c.cause_type.value,
                    "description": c.description,
                    "confidence": c.confidence,
                    "evidence": c.evidence,
                    "created_by": c.created_by,
                }
                for c in graph.root_causes
            ],
            "intermediate_causes": [
                {
                    "id": c.id,
                    "type": c.cause_type.value,
                    "description": c.description,
                    "depth": c.depth,
                    "confidence": c.confidence,
                    "parent_id": c.parent_id,
                    "created_by": c.created_by,
                }
                for c in graph.intermediate_causes
            ],
        }
