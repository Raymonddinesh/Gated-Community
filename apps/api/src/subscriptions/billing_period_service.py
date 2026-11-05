"""Phase 21E.2 — Billing Period Service.

Provides deterministic, timezone-aware billing calendar calculations:
- Storage standard: Timestamps stored in UTC.
- Business calendar: Asia/Kolkata (IST, UTC+05:30) for billing day/month boundaries.
- Precise month-end handling with anchor day preservation across variable-length months.
- Leap year exactness (Feb 29 in leap years vs Feb 28 in common years).
- Trial periods, renewal boundaries, next billing dates, and grace-period expiry.
"""

import calendar
from datetime import UTC, datetime, timedelta, timezone, tzinfo

from apps.api.src.subscriptions.exceptions import InvalidBillingPeriodException

IST: tzinfo
try:
    from zoneinfo import ZoneInfo
    IST = ZoneInfo("Asia/Kolkata")
except Exception:
    IST = timezone(timedelta(hours=5, minutes=30), name="Asia/Kolkata")


class BillingPeriodService:
    """Deterministic domain calculation service for subscription billing cycles."""

    @staticmethod
    def to_ist(utc_dt: datetime) -> datetime:
        """Convert a UTC datetime to Asia/Kolkata timezone."""
        if utc_dt.tzinfo is None:
            utc_dt = utc_dt.replace(tzinfo=UTC)
        return utc_dt.astimezone(IST)

    @staticmethod
    def to_utc(ist_dt: datetime) -> datetime:
        """Convert an Asia/Kolkata datetime to UTC datetime."""
        if ist_dt.tzinfo is None:
            ist_dt = ist_dt.replace(tzinfo=IST)
        return ist_dt.astimezone(UTC)

    @staticmethod
    def clamp_day_to_month(year: int, month: int, target_day: int) -> int:
        """Clamp target day to the maximum days available in the specified year/month."""
        _, max_days = calendar.monthrange(year, month)
        return min(target_day, max_days)

    @classmethod
    def calculate_trial_period(
        cls,
        trial_days: int = 14,
        starts_at_utc: datetime | None = None,
        *,
        start_time: datetime | None = None,
    ) -> tuple[datetime, datetime]:
        """Calculate start and end timestamps for a trial period.

        Returns (start_utc, trial_ends_at_utc).
        """
        if trial_days < 0:
            raise InvalidBillingPeriodException("Trial days cannot be negative.")
        base_start = start_time or starts_at_utc or datetime.now(UTC)
        if base_start.tzinfo is None:
            base_start = base_start.replace(tzinfo=UTC)

        trial_end = base_start + timedelta(days=trial_days)
        return base_start, trial_end

    @classmethod
    def calculate_initial_period(
        cls,
        starts_at_utc: datetime,
        billing_cycle: str = "MONTHLY",
    ) -> tuple[datetime, datetime]:
        """Calculate the initial subscription billing period based on start time and cycle.

        Calendar Boundary Rule:
        Evaluated in Asia/Kolkata (IST). Period start aligns with starts_at.
        Period end aligns with renewal date at 00:00:00 IST of next cycle.
        """
        if billing_cycle not in ("MONTHLY", "ANNUAL"):
            raise InvalidBillingPeriodException(
                f"Unsupported billing cycle '{billing_cycle}'. Must be 'MONTHLY' or 'ANNUAL'."
            )

        if starts_at_utc.tzinfo is None:
            starts_at_utc = starts_at_utc.replace(tzinfo=UTC)

        ist_start = cls.to_ist(starts_at_utc)
        anchor_day = ist_start.day

        if billing_cycle == "MONTHLY":
            # Advance 1 calendar month
            year = ist_start.year + (1 if ist_start.month == 12 else 0)
            month = 1 if ist_start.month == 12 else ist_start.month + 1
            clamped_day = cls.clamp_day_to_month(year, month, anchor_day)
            ist_end = datetime(year, month, clamped_day, ist_start.hour, ist_start.minute, ist_start.second, ist_start.microsecond, tzinfo=IST)
        else:  # ANNUAL
            # Advance 1 calendar year (handles Feb 29 leap year clamping to Feb 28)
            year = ist_start.year + 1
            month = ist_start.month
            clamped_day = cls.clamp_day_to_month(year, month, anchor_day)
            ist_end = datetime(year, month, clamped_day, ist_start.hour, ist_start.minute, ist_start.second, ist_start.microsecond, tzinfo=IST)

        return starts_at_utc, cls.to_utc(ist_end)

    @classmethod
    def calculate_next_billing_period(
        cls,
        current_period_end_utc: datetime,
        billing_cycle: str = "MONTHLY",
        original_anchor_day: int | None = None,
    ) -> tuple[datetime, datetime]:
        """Calculate the next renewal billing period starting from current_period_end.

        Preserves original_anchor_day (e.g. 31st) across variable-length months.
        """
        if billing_cycle not in ("MONTHLY", "ANNUAL"):
            raise InvalidBillingPeriodException(
                f"Unsupported billing cycle '{billing_cycle}'. Must be 'MONTHLY' or 'ANNUAL'."
            )

        if current_period_end_utc.tzinfo is None:
            current_period_end_utc = current_period_end_utc.replace(tzinfo=UTC)

        ist_start = cls.to_ist(current_period_end_utc)
        anchor_day = original_anchor_day if original_anchor_day is not None else ist_start.day

        if billing_cycle == "MONTHLY":
            year = ist_start.year + (1 if ist_start.month == 12 else 0)
            month = 1 if ist_start.month == 12 else ist_start.month + 1
            clamped_day = cls.clamp_day_to_month(year, month, anchor_day)
            ist_end = datetime(year, month, clamped_day, ist_start.hour, ist_start.minute, ist_start.second, ist_start.microsecond, tzinfo=IST)
        else:  # ANNUAL
            year = ist_start.year + 1
            month = ist_start.month
            clamped_day = cls.clamp_day_to_month(year, month, anchor_day)
            ist_end = datetime(year, month, clamped_day, ist_start.hour, ist_start.minute, ist_start.second, ist_start.microsecond, tzinfo=IST)

        return current_period_end_utc, cls.to_utc(ist_end)

    @classmethod
    def calculate_next_period(
        cls,
        cycle_start: datetime | None = None,
        billing_cycle: str = "MONTHLY",
        anchor_day: int | None = None,
        *,
        current_period_end_utc: datetime | None = None,
        original_anchor_day: int | None = None,
    ) -> tuple[datetime, datetime]:
        """Convenience alias for calculate_next_billing_period supporting varied keyword signatures."""
        base_start = cycle_start or current_period_end_utc
        if base_start is None:
            raise InvalidBillingPeriodException("cycle_start is required.")
        effective_anchor = anchor_day if anchor_day is not None else original_anchor_day
        return cls.calculate_next_billing_period(
            current_period_end_utc=base_start,
            billing_cycle=billing_cycle,
            original_anchor_day=effective_anchor,
        )

    @classmethod
    def calculate_grace_period_expiry(
        cls,
        past_due_since_utc: datetime,
        grace_period_days: int = 7,
    ) -> datetime:
        """Calculate the exact moment a past_due grace period expires."""
        if grace_period_days < 0:
            raise InvalidBillingPeriodException("Grace period days cannot be negative.")
        if past_due_since_utc.tzinfo is None:
            past_due_since_utc = past_due_since_utc.replace(tzinfo=UTC)

        return past_due_since_utc + timedelta(days=grace_period_days)

    @classmethod
    def calculate_grace_period_end(
        cls,
        due_date: datetime | None = None,
        grace_days: int = 7,
        *,
        past_due_since_utc: datetime | None = None,
    ) -> datetime:
        """Convenience alias for calculate_grace_period_expiry."""
        ref_dt = due_date or past_due_since_utc
        if ref_dt is None:
            raise InvalidBillingPeriodException("Reference date is required.")
        return cls.calculate_grace_period_expiry(ref_dt, grace_days)

