"""Phase 21E.2 — Proration Engine.

Provides high-precision, Decimal-based proration calculations for subscription changes:
- Calculation principle:
    Unused fraction = remaining elapsed seconds / total billing-period seconds.
    Prorated unused credit = eligible subscription amount × unused fraction.
- Strict Decimal arithmetic; zero binary float inaccuracies.
- Intermediate fraction computed to 8 decimal places (0.00000001).
- Final monetary quantization to 2 decimal places (0.01) using ROUND_HALF_UP.
- Graceful boundary handling: zero remaining duration, expired periods, start-of-cycle upgrades.
- Leap year and variable month length accuracy through second-level UTC timestamps.
"""

from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal

from apps.api.src.subscriptions.exceptions import ProrationCalculationException
from apps.api.src.subscriptions.schemas import ProrationResult

FRACTION_PRECISION = Decimal("0.00000001")
CURRENCY_PRECISION = Decimal("0.01")


def _utc_now() -> datetime:
    return datetime.now(UTC)


class ProrationEngine:
    """Reusable high-precision proration engine for SaaS subscription lifecycle changes."""

    @classmethod
    def calculate_proration(
        cls,
        eligible_amount: Decimal | datetime | None = None,
        period_start: datetime | None = None,
        period_end: datetime | None = None,
        effective_at: datetime | Decimal | None = None,
        *,
        rate: Decimal | None = None,
        as_of_time: datetime | None = None,
    ) -> ProrationResult:
        """Calculate the prorated monetary value of a subscription for a partial duration.

        Supports standard (amount, start, end, effective) and alternate
        (start, end, as_of, rate) argument conventions.
        """
        # Resolve argument ordering
        if isinstance(eligible_amount, datetime):
            # Positional: (start, end, effective, amount)
            actual_start: datetime = eligible_amount
            actual_end: datetime = period_start  # type: ignore
            actual_effective: datetime = as_of_time or (period_end if isinstance(period_end, datetime) else _utc_now())
            if isinstance(effective_at, Decimal):
                actual_amount: Decimal = effective_at
            elif rate is not None:
                actual_amount = rate
            else:
                actual_amount = Decimal("0.00")
        else:
            actual_start = period_start  # type: ignore
            actual_end = period_end  # type: ignore
            actual_effective = as_of_time or (effective_at if isinstance(effective_at, datetime) else _utc_now())
            actual_amount = eligible_amount if isinstance(eligible_amount, Decimal) else (rate or Decimal("0.00"))

        if actual_start is None or actual_end is None:
            raise ProrationCalculationException("period_start and period_end are required.")

        if actual_start.tzinfo is None:
            actual_start = actual_start.replace(tzinfo=UTC)
        if actual_end.tzinfo is None:
            actual_end = actual_end.replace(tzinfo=UTC)
        if actual_effective.tzinfo is None:
            actual_effective = actual_effective.replace(tzinfo=UTC)

        total_sec = Decimal(str((actual_end - actual_start).total_seconds()))
        if total_sec <= Decimal("0"):
            raise ProrationCalculationException(
                "Invalid period duration: period_end must be strictly greater than period_start."
            )

        # If effective_at is at or past period_end, zero remaining duration
        if actual_effective >= actual_end:
            return ProrationResult(
                total_seconds=total_sec,
                remaining_seconds=Decimal("0"),
                unused_fraction=Decimal("0.00000000"),
                eligible_amount=actual_amount,
                prorated_amount=Decimal("0.00"),
                is_zero_duration=True,
            )

        # If effective_at is at or before period_start, 100% of period is remaining
        if actual_effective <= actual_start:
            prorated_val = actual_amount.quantize(CURRENCY_PRECISION, rounding=ROUND_HALF_UP)
            return ProrationResult(
                total_seconds=total_sec,
                remaining_seconds=total_sec,
                unused_fraction=Decimal("1.00000000"),
                eligible_amount=actual_amount,
                prorated_amount=prorated_val,
                is_zero_duration=False,
            )

        # Mid-period calculation
        remaining_sec = Decimal(str((actual_end - actual_effective).total_seconds()))
        raw_fraction = remaining_sec / total_sec
        fraction_8dec = raw_fraction.quantize(FRACTION_PRECISION, rounding=ROUND_HALF_UP)

        # Prorated currency calculation
        raw_prorated = actual_amount * raw_fraction
        prorated_cur = raw_prorated.quantize(CURRENCY_PRECISION, rounding=ROUND_HALF_UP)

        return ProrationResult(
            total_seconds=total_sec,
            remaining_seconds=remaining_sec,
            unused_fraction=fraction_8dec,
            eligible_amount=actual_amount,
            prorated_amount=prorated_cur,
            is_zero_duration=False,
        )

