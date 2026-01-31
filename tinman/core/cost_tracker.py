"""Cost tracking and enforcement for Tinman FDRA.

This module provides end-to-end cost tracking across all LLM operations,
with configurable budgets and automatic enforcement.

Usage:
    tracker = CostTracker(budget_usd=10.0)

    # Track a cost
    tracker.record_cost(0.05, source="experiment_001", model="gpt-4")

    # Check if budget allows operation
    if tracker.can_afford(estimated_cost=0.10):
        # Proceed with operation
        pass

    # Get remaining budget
    remaining = tracker.remaining_budget

    # Enforce budget (raises exception if exceeded)
    tracker.enforce_budget()
"""

import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any

from ..utils import get_logger, utc_now

logger = get_logger("cost_tracker")


class BudgetPeriod(str, Enum):
    """Budget time periods."""

    HOURLY = "hourly"
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    SESSION = "session"  # Per Tinman session
    UNLIMITED = "unlimited"


@dataclass
class CostRecord:
    """Record of a single cost event."""

    amount_usd: float
    timestamp: datetime
    source: str  # Which component incurred the cost
    model: str  # Which model was used
    operation: str  # What operation (research, experiment, etc.)
    input_tokens: int = 0
    output_tokens: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class BudgetConfig:
    """Configuration for cost budget."""

    limit_usd: float = 10.0
    period: BudgetPeriod = BudgetPeriod.DAILY
    warn_threshold: float = 0.8  # Warn when 80% consumed
    hard_limit: bool = True  # Block operations when exceeded
    rollover: bool = False  # Allow unused budget to roll over

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BudgetConfig":
        """Create from dictionary."""
        return cls(
            limit_usd=data.get("limit_usd", 10.0),
            period=BudgetPeriod(data.get("period", "daily")),
            warn_threshold=data.get("warn_threshold", 0.8),
            hard_limit=data.get("hard_limit", True),
            rollover=data.get("rollover", False),
        )


class BudgetExceededError(Exception):
    """Raised when budget is exceeded and hard_limit is True."""

    def __init__(self, current: float, limit: float, message: str = ""):
        self.current = current
        self.limit = limit
        super().__init__(message or f"Budget exceeded: ${current:.4f} / ${limit:.2f}")


class CostTracker:
    """Tracks and enforces cost limits across Tinman operations.

    Thread-safe implementation that supports multiple budget periods
    and configurable enforcement behavior.
    """

    def __init__(
        self,
        budget_config: BudgetConfig | None = None,
        budget_usd: float | None = None,
        period: BudgetPeriod = BudgetPeriod.DAILY,
        on_warning: Callable[[float, float], None] | None = None,
        on_exceeded: Callable[[float, float], None] | None = None,
    ):
        """Initialize cost tracker.

        Args:
            budget_config: Full budget configuration
            budget_usd: Simple budget limit (creates default config if provided)
            period: Budget period (if using simple limit)
            on_warning: Callback when warning threshold reached
            on_exceeded: Callback when budget exceeded
        """
        if budget_config:
            self.config = budget_config
        elif budget_usd is not None:
            self.config = BudgetConfig(limit_usd=budget_usd, period=period)
        else:
            self.config = BudgetConfig()

        self.on_warning = on_warning
        self.on_exceeded = on_exceeded

        # Cost records
        self._records: list[CostRecord] = []
        self._lock = threading.Lock()

        # Period tracking
        self._period_start = utc_now()
        self._total_ever_usd = 0.0

        # Warning state
        self._warning_issued = False

        logger.info(
            f"CostTracker initialized: budget=${self.config.limit_usd:.2f}, "
            f"period={self.config.period.value}"
        )

    def record_cost(
        self,
        amount_usd: float,
        source: str,
        model: str = "unknown",
        operation: str = "unknown",
        input_tokens: int = 0,
        output_tokens: int = 0,
        metadata: dict[str, Any] | None = None,
    ) -> CostRecord:
        """Record a cost event.

        Args:
            amount_usd: Cost in USD
            source: Component that incurred the cost
            model: Model used
            operation: Operation type
            input_tokens: Input token count
            output_tokens: Output token count
            metadata: Additional metadata

        Returns:
            The recorded CostRecord
        """
        record = CostRecord(
            amount_usd=amount_usd,
            timestamp=utc_now(),
            source=source,
            model=model,
            operation=operation,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            metadata=metadata or {},
        )

        with self._lock:
            self._records.append(record)
            self._total_ever_usd += amount_usd

        # Check thresholds
        self._check_thresholds()

        logger.debug(
            f"Cost recorded: ${amount_usd:.4f} from {source} (model={model}, op={operation})"
        )

        return record

    def _check_thresholds(self) -> None:
        """Check budget thresholds and trigger callbacks."""
        current = self.current_period_cost
        limit = self.config.limit_usd

        # Check warning threshold
        if not self._warning_issued and current >= limit * self.config.warn_threshold:
            self._warning_issued = True
            logger.warning(
                f"Budget warning: ${current:.4f} / ${limit:.2f} "
                f"({current / limit * 100:.1f}% consumed)"
            )
            if self.on_warning:
                self.on_warning(current, limit)

        # Check hard limit
        if current >= limit:
            logger.warning(f"Budget exceeded: ${current:.4f} / ${limit:.2f}")
            if self.on_exceeded:
                self.on_exceeded(current, limit)

    @property
    def current_period_cost(self) -> float:
        """Get total cost for current period."""
        if self.config.period == BudgetPeriod.UNLIMITED:
            return self._total_ever_usd

        period_start = self._get_period_start()

        with self._lock:
            return sum(r.amount_usd for r in self._records if r.timestamp >= period_start)

    @property
    def remaining_budget(self) -> float:
        """Get remaining budget for current period."""
        if self.config.period == BudgetPeriod.UNLIMITED:
            return float("inf")

        return max(0, self.config.limit_usd - self.current_period_cost)

    @property
    def total_cost_ever(self) -> float:
        """Get total cost ever recorded."""
        return self._total_ever_usd

    def _get_period_start(self) -> datetime:
        """Get the start of the current budget period."""
        now = utc_now()

        if self.config.period == BudgetPeriod.SESSION:
            return self._period_start

        if self.config.period == BudgetPeriod.HOURLY:
            return now.replace(minute=0, second=0, microsecond=0)

        if self.config.period == BudgetPeriod.DAILY:
            return now.replace(hour=0, minute=0, second=0, microsecond=0)

        if self.config.period == BudgetPeriod.WEEKLY:
            days_since_monday = now.weekday()
            return (now - timedelta(days=days_since_monday)).replace(
                hour=0, minute=0, second=0, microsecond=0
            )

        if self.config.period == BudgetPeriod.MONTHLY:
            return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        return self._period_start

    def can_afford(self, estimated_cost: float) -> bool:
        """Check if an operation can be afforded.

        Args:
            estimated_cost: Estimated cost of the operation

        Returns:
            True if operation can be afforded
        """
        if self.config.period == BudgetPeriod.UNLIMITED:
            return True

        if not self.config.hard_limit:
            return True  # Soft limit - always allow but warn

        return self.remaining_budget >= estimated_cost

    def enforce_budget(self, estimated_cost: float = 0.0) -> None:
        """Enforce budget limit.

        Args:
            estimated_cost: Optional estimated cost to check

        Raises:
            BudgetExceededError: If budget is exceeded and hard_limit is True
        """
        if self.config.period == BudgetPeriod.UNLIMITED:
            return

        if not self.config.hard_limit:
            return

        current = self.current_period_cost
        limit = self.config.limit_usd

        if current >= limit:
            raise BudgetExceededError(current, limit)

        if estimated_cost > 0 and current + estimated_cost > limit:
            raise BudgetExceededError(
                current + estimated_cost,
                limit,
                f"Estimated cost ${estimated_cost:.4f} would exceed budget "
                f"(current: ${current:.4f}, limit: ${limit:.2f})",
            )

    def get_summary(self) -> dict[str, Any]:
        """Get cost summary."""
        with self._lock:
            records = list(self._records)

        # Calculate by source
        by_source: dict[str, float] = {}
        by_model: dict[str, float] = {}
        by_operation: dict[str, float] = {}

        for r in records:
            by_source[r.source] = by_source.get(r.source, 0) + r.amount_usd
            by_model[r.model] = by_model.get(r.model, 0) + r.amount_usd
            by_operation[r.operation] = by_operation.get(r.operation, 0) + r.amount_usd

        return {
            "current_period_cost_usd": self.current_period_cost,
            "remaining_budget_usd": self.remaining_budget,
            "total_cost_ever_usd": self._total_ever_usd,
            "budget_limit_usd": self.config.limit_usd,
            "budget_period": self.config.period.value,
            "utilization_percent": (
                self.current_period_cost / self.config.limit_usd * 100
                if self.config.limit_usd > 0
                else 0
            ),
            "record_count": len(records),
            "by_source": by_source,
            "by_model": by_model,
            "by_operation": by_operation,
        }

    def get_records(
        self,
        since: datetime | None = None,
        source: str | None = None,
        model: str | None = None,
        limit: int = 100,
    ) -> list[CostRecord]:
        """Get cost records with filters.

        Args:
            since: Only records after this time
            source: Filter by source
            model: Filter by model
            limit: Maximum records to return

        Returns:
            List of matching CostRecord objects
        """
        with self._lock:
            records = list(self._records)

        if since:
            records = [r for r in records if r.timestamp >= since]

        if source:
            records = [r for r in records if r.source == source]

        if model:
            records = [r for r in records if r.model == model]

        # Return most recent first
        return sorted(records, key=lambda r: r.timestamp, reverse=True)[:limit]

    def reset_period(self) -> None:
        """Reset the current budget period.

        This clears the warning state and optionally clears records
        (depending on rollover config).
        """
        self._warning_issued = False
        self._period_start = utc_now()

        if not self.config.rollover:
            # Clear records for new period
            with self._lock:
                period_start = self._get_period_start()
                self._records = [r for r in self._records if r.timestamp >= period_start]

        logger.info("Budget period reset")


# Default tracker instance
_default_tracker: CostTracker | None = None


def get_cost_tracker() -> CostTracker:
    """Get the default cost tracker."""
    global _default_tracker
    if _default_tracker is None:
        _default_tracker = CostTracker()
    return _default_tracker


def set_cost_tracker(tracker: CostTracker) -> None:
    """Set the default cost tracker."""
    global _default_tracker
    _default_tracker = tracker


def record_cost(
    amount_usd: float,
    source: str,
    model: str = "unknown",
    operation: str = "unknown",
    **kwargs,
) -> CostRecord:
    """Convenience function to record cost to default tracker."""
    return get_cost_tracker().record_cost(
        amount_usd=amount_usd,
        source=source,
        model=model,
        operation=operation,
        **kwargs,
    )
