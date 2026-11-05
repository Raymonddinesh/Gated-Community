"""Phase 21E.2 — Grace Period Service.

Manages grace-period calculations for past-due subscriptions:
- Default grace period: 7 days.
- Deterministic evaluation of grace period expiry against UTC timestamps.
- Evaluation of remaining grace window duration.
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

DEFAULT_GRACE_PERIOD_DAYS = 7


@dataclass(frozen=True)
class GracePeriodEvaluation:
    """Detailed evaluation result for past_due grace period."""

    is_expired: bool
    seconds_remaining: int
    seconds_overdue: int


class GracePeriodService:
    """Domain service managing subscription grace-period evaluations."""

    def __init__(self, default_grace_days: int = DEFAULT_GRACE_PERIOD_DAYS) -> None:
        self.default_grace_days = default_grace_days

    def evaluate_grace_period(
        self,
        due_date: datetime,
        as_of_time: datetime | None = None,
        grace_days: int | None = None,
    ) -> GracePeriodEvaluation:
        """Evaluate grace period status relative to invoice due date or past_due start."""
        effective_days = grace_days if grace_days is not None else self.default_grace_days
        if due_date.tzinfo is None:
            due_date = due_date.replace(tzinfo=UTC)

        current_time = as_of_time or datetime.now(UTC)
        if current_time.tzinfo is None:
            current_time = current_time.replace(tzinfo=UTC)

        expiry = self.calculate_grace_expiry(due_date, effective_days)

        if current_time >= expiry:
            overdue_sec = int((current_time - expiry).total_seconds())
            return GracePeriodEvaluation(
                is_expired=True,
                seconds_remaining=0,
                seconds_overdue=overdue_sec,
            )
        else:
            remaining_sec = int((expiry - current_time).total_seconds())
            return GracePeriodEvaluation(
                is_expired=False,
                seconds_remaining=remaining_sec,
                seconds_overdue=0,
            )

    @classmethod
    def calculate_grace_expiry(
        cls,
        past_due_since: datetime,
        grace_period_days: int = DEFAULT_GRACE_PERIOD_DAYS,
    ) -> datetime:
        """Calculate the UTC timestamp when the grace period expires."""
        if past_due_since.tzinfo is None:
            past_due_since = past_due_since.replace(tzinfo=UTC)
        return past_due_since + timedelta(days=grace_period_days)

    @classmethod
    def is_grace_period_expired(
        cls,
        past_due_since: datetime | None,
        grace_period_days: int = DEFAULT_GRACE_PERIOD_DAYS,
        as_of: datetime | None = None,
    ) -> bool:
        """Evaluate whether a subscription's grace period has expired."""
        if past_due_since is None:
            return False

        if past_due_since.tzinfo is None:
            past_due_since = past_due_since.replace(tzinfo=UTC)

        current_time = as_of or datetime.now(UTC)
        if current_time.tzinfo is None:
            current_time = current_time.replace(tzinfo=UTC)

        expiry = cls.calculate_grace_expiry(past_due_since, grace_period_days)
        return current_time >= expiry

    @classmethod
    def get_remaining_grace_duration(
        cls,
        past_due_since: datetime | None,
        grace_period_days: int = DEFAULT_GRACE_PERIOD_DAYS,
        as_of: datetime | None = None,
    ) -> timedelta:
        """Return remaining time in grace period. Returns 0 duration if already expired."""
        if past_due_since is None:
            return timedelta(0)

        if past_due_since.tzinfo is None:
            past_due_since = past_due_since.replace(tzinfo=UTC)

        current_time = as_of or datetime.now(UTC)
        if current_time.tzinfo is None:
            current_time = current_time.replace(tzinfo=UTC)

        expiry = cls.calculate_grace_expiry(past_due_since, grace_period_days)
        remaining = expiry - current_time
        return max(timedelta(0), remaining)

