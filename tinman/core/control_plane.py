"""Control plane for managing FDRA global state and mode transitions."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Callable
import threading

from ..config import Mode, Settings
from ..utils import utc_now, get_logger
from .event_bus import EventBus, Topics
from .risk_evaluator import RiskEvaluator

logger = get_logger("control_plane")


@dataclass
class ControlPlaneState:
    """Current state of the control plane."""
    mode: Mode
    started_at: datetime
    last_mode_change: datetime
    total_experiments: int = 0
    total_failures: int = 0
    total_interventions: int = 0
    is_running: bool = False


class ControlPlane:
    """
    Central nervous system of Tinman FDRA.

    Manages:
    - Operating mode (LAB/SHADOW/PRODUCTION)
    - Mode transitions with validation
    - Global state tracking
    - Event bus coordination
    - Risk evaluation integration
    """

    def __init__(self, settings: Settings, event_bus: Optional[EventBus] = None):
        self.settings = settings
        self.event_bus = event_bus or EventBus()
        self.risk_evaluator = RiskEvaluator(
            detailed_mode=settings.risk.detailed_mode,
            auto_approve_safe=settings.risk.auto_approve_safe,
            block_on_destructive=settings.risk.block_on_destructive,
        )

        self._mode = settings.mode
        self._state = ControlPlaneState(
            mode=settings.mode,
            started_at=utc_now(),
            last_mode_change=utc_now(),
        )
        self._lock = threading.Lock()
        self._mode_change_hooks: list[Callable[[Mode, Mode], None]] = []

        logger.info(f"Control plane initialized in {self._mode.value} mode")

    @property
    def mode(self) -> Mode:
        """Current operating mode."""
        return self._mode

    @property
    def state(self) -> ControlPlaneState:
        """Current control plane state."""
        with self._lock:
            return self._state

    def start(self) -> None:
        """Start the control plane."""
        with self._lock:
            self._state.is_running = True
            self._state.started_at = utc_now()
        logger.info("Control plane started")

    def stop(self) -> None:
        """Stop the control plane."""
        with self._lock:
            self._state.is_running = False
        logger.info("Control plane stopped")

    def set_mode(self, new_mode: Mode, force: bool = False) -> bool:
        """
        Transition to a new operating mode.

        Args:
            new_mode: Target mode
            force: Bypass transition validation (use with caution)

        Returns:
            True if transition succeeded, False otherwise
        """
        with self._lock:
            current = self._mode

            if current == new_mode:
                logger.debug(f"Already in {new_mode.value} mode")
                return True

            # Validate transition
            if not force and not Mode.can_transition(current, new_mode):
                logger.warning(
                    f"Invalid mode transition: {current.value} -> {new_mode.value}"
                )
                return False

            # Execute transition
            old_mode = self._mode
            self._mode = new_mode
            self._state.mode = new_mode
            self._state.last_mode_change = utc_now()

            logger.info(f"Mode transition: {old_mode.value} -> {new_mode.value}")

        # Notify hooks (outside lock)
        for hook in self._mode_change_hooks:
            try:
                hook(old_mode, new_mode)
            except Exception as e:
                logger.error(f"Error in mode change hook: {e}")

        return True

    def register_mode_change_hook(self, hook: Callable[[Mode, Mode], None]) -> None:
        """Register a callback for mode changes."""
        self._mode_change_hooks.append(hook)

    def can_transition_to(self, target: Mode) -> bool:
        """Check if transition to target mode is allowed."""
        return Mode.can_transition(self._mode, target)

    def record_experiment(self) -> None:
        """Record that an experiment was run."""
        with self._lock:
            self._state.total_experiments += 1

    def record_failure(self) -> None:
        """Record that a failure was discovered."""
        with self._lock:
            self._state.total_failures += 1

    def record_intervention(self) -> None:
        """Record that an intervention was proposed."""
        with self._lock:
            self._state.total_interventions += 1

    def get_status(self) -> dict:
        """Get current status as dictionary."""
        with self._lock:
            return {
                "mode": self._mode.value,
                "is_running": self._state.is_running,
                "started_at": self._state.started_at.isoformat(),
                "last_mode_change": self._state.last_mode_change.isoformat(),
                "total_experiments": self._state.total_experiments,
                "total_failures": self._state.total_failures,
                "total_interventions": self._state.total_interventions,
                "allows_destructive": self._mode.allows_destructive_testing,
                "requires_approval": self._mode.requires_approval_gate,
                "is_autonomous": self._mode.is_autonomous,
            }

    def trigger_regression_fallback(self, reason: str) -> bool:
        """
        Trigger automatic fallback to SHADOW mode on regression detection.

        Only applies in PRODUCTION mode.
        """
        if self._mode != Mode.PRODUCTION:
            logger.debug("Regression fallback only applies in PRODUCTION mode")
            return False

        logger.warning(f"Regression detected, falling back to SHADOW: {reason}")

        # Publish regression event
        self.event_bus.publish(
            Topics.REGRESSION_DETECTED,
            {"reason": reason, "from_mode": self._mode.value},
        )

        return self.set_mode(Mode.SHADOW, force=True)
