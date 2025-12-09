"""Operating modes for Tinman FDRA."""

from enum import Enum


class Mode(str, Enum):
    """
    Three operating modes for the research agent.

    LAB: Full autonomy, destructive testing allowed, no production impact
    SHADOW: Mirror production traffic, full autonomy, no customer impact
    PRODUCTION: Live deployment with risk gating and human approval
    """
    LAB = "lab"
    SHADOW = "shadow"
    PRODUCTION = "production"

    @classmethod
    def can_transition(cls, from_mode: "Mode", to_mode: "Mode") -> bool:
        """Check if mode transition is allowed."""
        allowed = {
            cls.LAB: {cls.SHADOW},
            cls.SHADOW: {cls.PRODUCTION, cls.LAB},
            cls.PRODUCTION: {cls.SHADOW},  # Regression fallback
        }
        return to_mode in allowed.get(from_mode, set())

    @property
    def allows_destructive_testing(self) -> bool:
        return self == Mode.LAB

    @property
    def requires_approval_gate(self) -> bool:
        return self == Mode.PRODUCTION

    @property
    def is_autonomous(self) -> bool:
        return self in (Mode.LAB, Mode.SHADOW)


# Alias for backwards compatibility
OperatingMode = Mode
