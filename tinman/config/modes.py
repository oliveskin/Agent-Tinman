"""Operating modes for Tinman FDRA."""

from dataclasses import dataclass
from enum import Enum


@dataclass
class ModeCapabilities:
    """Capabilities and restrictions for each operating mode."""

    can_generate_hypotheses: bool = True
    can_run_experiments: bool = True
    can_analyze_failures: bool = True
    can_design_interventions: bool = True
    can_execute_interventions: bool = True
    can_deploy_to_production: bool = False
    requires_approval_for_interventions: bool = False
    requires_approval_for_experiments: bool = False
    allows_destructive_testing: bool = False
    max_risk_tier: str = "BLOCK"


# Valid mode transitions
VALID_TRANSITIONS = {
    "lab": {"shadow"},
    "shadow": {"production", "lab"},
    "production": {"shadow"},
}


def get_capabilities(mode: "Mode") -> ModeCapabilities:
    """Get capabilities for a specific mode."""
    if mode == Mode.LAB:
        return ModeCapabilities(
            can_generate_hypotheses=True,
            can_run_experiments=True,
            can_analyze_failures=True,
            can_design_interventions=True,
            can_execute_interventions=True,
            can_deploy_to_production=False,
            requires_approval_for_interventions=False,
            requires_approval_for_experiments=False,
            allows_destructive_testing=True,
            max_risk_tier="BLOCK",
        )
    elif mode == Mode.SHADOW:
        return ModeCapabilities(
            can_generate_hypotheses=True,
            can_run_experiments=True,
            can_analyze_failures=True,
            can_design_interventions=True,
            can_execute_interventions=False,
            can_deploy_to_production=False,
            requires_approval_for_interventions=True,
            requires_approval_for_experiments=False,
            allows_destructive_testing=False,
            max_risk_tier="REVIEW",
        )
    else:  # PRODUCTION
        return ModeCapabilities(
            can_generate_hypotheses=True,
            can_run_experiments=True,
            can_analyze_failures=True,
            can_design_interventions=True,
            can_execute_interventions=True,
            can_deploy_to_production=True,
            requires_approval_for_interventions=True,
            requires_approval_for_experiments=True,
            allows_destructive_testing=False,
            max_risk_tier="SAFE",
        )


def can_transition(from_mode: "Mode", to_mode: "Mode") -> bool:
    """Check if a mode transition is valid."""
    return to_mode.value in VALID_TRANSITIONS.get(from_mode.value, set())


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
