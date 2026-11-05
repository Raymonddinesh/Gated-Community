"""Phase 21E.4B — Financial-Year Sequential Invoice Numbering Service.

Allocates sequential, deterministic legal tax invoice numbers:
- Follows statutory Indian Financial Year boundaries (April 1 to March 31).
- Timezone-aware evaluation using Asia/Kolkata (IST).
- Pessimistic row locking on PlatformInvoiceSequence via SELECT ... FOR UPDATE.
- Zero gap reuse: Numbers are permanently allocated during DRAFT -> ISSUED.
- Rollback safety: Aborted finalization transactions automatically release sequence lock.
- Explicit Disclaimer: Sequential counter ensures unique sequential progression under
  database locking; legal gaplessness requires professional Chartered Accountant validation.
"""

from datetime import UTC, date, datetime, timedelta, timezone, tzinfo
from typing import Final

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.database.models.platform_billing import PlatformInvoiceSequence
from apps.api.src.subscriptions.invoicing.exceptions import InvoiceSequenceExhaustedException


def _get_ist_timezone() -> tzinfo:
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo("Asia/Kolkata")
    except Exception:
        return timezone(timedelta(hours=5, minutes=30), name="Asia/Kolkata")


IST_TIMEZONE: Final[tzinfo] = _get_ist_timezone()

DEFAULT_INVOICE_PREFIX: Final[str] = "SS"  # SocietySphere


def get_financial_year(dt: datetime | date | None = None) -> str:
    """Determine the Indian Financial Year (FY) code for a given datetime or date in Asia/Kolkata.

    Examples:
        - 2026-04-01 -> "2627" (FY 2026-27)
        - 2027-01-15 -> "2627" (FY 2026-27)
        - 2027-03-31 -> "2627" (FY 2026-27)
        - 2027-04-01 -> "2728" (FY 2027-28)
    """
    if dt is None:
        target_dt = datetime.now(IST_TIMEZONE)
    elif isinstance(dt, datetime):
        if dt.tzinfo is None:
            # Assume UTC if naive, then convert to IST
            target_dt = dt.replace(tzinfo=UTC).astimezone(IST_TIMEZONE)
        else:
            target_dt = dt.astimezone(IST_TIMEZONE)
    else:
        # Date instance
        target_dt = datetime(dt.year, dt.month, dt.day, 12, 0, 0, tzinfo=IST_TIMEZONE)

    year = target_dt.year
    month = target_dt.month

    if month >= 4:
        # April to December: Current year to Next year
        start_yr = year
        end_yr = year + 1
    else:
        # January to March: Previous year to Current year
        start_yr = year - 1
        end_yr = year

    # 4-digit code e.g. "2627"
    return f"{str(start_yr)[2:]}{str(end_yr)[2:]}"


class InvoiceNumberingService:
    """Service managing sequential financial-year invoice numbering with pessimistic row locking."""

    def __init__(self, prefix: str = DEFAULT_INVOICE_PREFIX) -> None:
        self.prefix = prefix.strip().upper()

    async def allocate_invoice_number(
        self,
        session: AsyncSession,
        transaction_date: datetime | date | None = None,
    ) -> tuple[str, str]:
        """Atomically allocate the next sequential invoice number for the applicable financial year.

        Guarantees:
            - Executes within the caller's active database transaction.
            - Locks the sequence row with SELECT ... FOR UPDATE, serializing concurrent issuance.
            - Increments the sequence atomically.
            - Returns a tuple of (allocated_invoice_number, fiscal_year).

        Format:
            `{PREFIX}-{FISCAL_YEAR}-{SEQUENCE:05d}` (e.g. `SS-2627-00001`)
        """
        fy = get_financial_year(transaction_date)
        now_utc = datetime.now(UTC).replace(tzinfo=None)

        # 1. Pessimistically lock sequence row for the financial year
        # On PostgreSQL, ensure the FY row exists so SELECT ... FOR UPDATE serializes immediately
        bind = session.bind
        if bind and getattr(bind, "dialect", None) and bind.dialect.name == "postgresql":
            from sqlalchemy.dialects.postgresql import insert as pg_insert

            init_stmt = (
                pg_insert(PlatformInvoiceSequence)
                .values(fiscal_year=fy, current_sequence=0, updated_at=now_utc)
                .on_conflict_do_nothing(index_elements=["fiscal_year"])
            )
            await session.execute(init_stmt)
            await session.flush()

        stmt = (
            select(PlatformInvoiceSequence)
            .where(PlatformInvoiceSequence.fiscal_year == fy)
            .with_for_update()
        )
        res = await session.execute(stmt)
        seq_row = res.scalar_one_or_none()

        if seq_row is None:
            # First invoice in this financial year (e.g. SQLite test environment)
            allocated_seq = 1
            seq_row = PlatformInvoiceSequence(
                fiscal_year=fy,
                current_sequence=allocated_seq,
                updated_at=now_utc,
            )
            session.add(seq_row)
        else:
            if seq_row.current_sequence < 0:
                raise InvoiceSequenceExhaustedException(
                    fiscal_year=fy,
                    reason=f"Corrupt sequence counter: {seq_row.current_sequence}",
                )
            seq_row.current_sequence += 1
            seq_row.updated_at = now_utc
            allocated_seq = seq_row.current_sequence

        # Flush to register row changes and acquire locks in Postgres without premature commit
        await session.flush()

        invoice_number = f"{self.prefix}-{fy}-{allocated_seq:05d}"
        return invoice_number, fy

    async def peek_current_sequence(
        self,
        session: AsyncSession,
        fiscal_year: str,
    ) -> int:
        """Inspect the current sequence counter for a fiscal year without advancing it."""
        stmt = select(PlatformInvoiceSequence.current_sequence).where(
            PlatformInvoiceSequence.fiscal_year == fiscal_year
        )
        val = await session.scalar(stmt)
        return val or 0
