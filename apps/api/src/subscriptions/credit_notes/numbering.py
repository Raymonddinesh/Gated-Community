"""Phase 21E.4C — Financial-Year Sequential Credit Note Numbering Service.

Allocates sequential, deterministic statutory credit note numbers:
- Follows statutory Indian Financial Year boundaries (April 1 to March 31).
- Timezone-aware evaluation using Asia/Kolkata (IST).
- Pessimistic row locking on PlatformCreditNoteSequence via SELECT ... FOR UPDATE.
- Zero gap reuse: Numbers are permanently allocated during DRAFT -> ISSUED.
- Format: `SS-CN-{FY}-{SEQ:05d}` (e.g. `SS-CN-2627-00001`).
- Explicit Disclaimer: Sequential counter ensures unique sequential progression under
  database locking; legal gaplessness requires professional Chartered Accountant validation.
"""

from datetime import UTC, date, datetime, timedelta, timezone, tzinfo
from typing import Final

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.database.models.platform_billing import (
    PlatformCreditNote,
    PlatformCreditNoteSequence,
)
from apps.api.src.subscriptions.credit_notes.exceptions import CreditNoteSequenceExhaustedException


def _get_ist_timezone() -> tzinfo:
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo("Asia/Kolkata")
    except Exception:
        return timezone(timedelta(hours=5, minutes=30), name="Asia/Kolkata")


IST_TIMEZONE: Final[tzinfo] = _get_ist_timezone()

DEFAULT_CREDIT_NOTE_PREFIX: Final[str] = "SS-CN"  # SocietySphere Credit Note


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
            target_dt = dt.replace(tzinfo=UTC).astimezone(IST_TIMEZONE)
        else:
            target_dt = dt.astimezone(IST_TIMEZONE)
    else:
        target_dt = datetime(dt.year, dt.month, dt.day, 12, 0, 0, tzinfo=IST_TIMEZONE)

    year = target_dt.year
    month = target_dt.month

    if month >= 4:
        start_yr = year
        end_yr = year + 1
    else:
        start_yr = year - 1
        end_yr = year

    return f"{str(start_yr)[2:]}{str(end_yr)[2:]}"


class CreditNoteNumberingService:
    """Service managing sequential financial-year credit note numbering with pessimistic row locking."""

    def __init__(self, prefix: str = DEFAULT_CREDIT_NOTE_PREFIX) -> None:
        self.prefix = prefix.strip().upper()

    async def allocate_credit_note_number(
        self,
        session: AsyncSession,
        transaction_date: datetime | date | None = None,
    ) -> tuple[str, str]:
        """Atomically allocate the next sequential credit note number for the applicable financial year.

        Guarantees:
            - Executes within the caller's active database transaction.
            - Locks the sequence row with SELECT ... FOR UPDATE, serializing concurrent issuance.
            - Increments the sequence atomically.
            - Returns a tuple of (allocated_credit_note_number, fiscal_year).

        Format:
            `{PREFIX}-{FISCAL_YEAR}-{SEQUENCE:05d}` (e.g. `SS-CN-2627-00001`)
        """
        fy = get_financial_year(transaction_date)
        now_utc = datetime.now(UTC).replace(tzinfo=None)

        # 1. Pessimistically lock sequence row for the financial year
        try:
            bind = session.get_bind()
            dialect_name = getattr(bind, "dialect", None)
            dialect_name_str = dialect_name.name if dialect_name else ""
        except Exception:
            dialect_name_str = ""

        if dialect_name_str == "postgresql":
            from sqlalchemy.dialects.postgresql import insert as pg_insert

            init_stmt = (
                pg_insert(PlatformCreditNoteSequence)
                .values(fiscal_year=fy, current_sequence=0, updated_at=now_utc)
                .on_conflict_do_nothing(index_elements=["fiscal_year"])
            )
            await session.execute(init_stmt)
            await session.flush()

        stmt = (
            select(PlatformCreditNoteSequence)
            .where(PlatformCreditNoteSequence.fiscal_year == fy)
            .with_for_update()
        )
        res = await session.execute(stmt)
        seq_row = res.scalar_one_or_none()

        if seq_row is None:
            # First credit note in this financial year (e.g. SQLite test environment)
            allocated_seq = 1
            seq_row = PlatformCreditNoteSequence(
                fiscal_year=fy,
                current_sequence=allocated_seq,
                updated_at=now_utc,
            )
            session.add(seq_row)
        else:
            if seq_row.current_sequence < 0:
                raise CreditNoteSequenceExhaustedException(
                    fiscal_year=fy,
                    reason=f"Corrupt sequence counter: {seq_row.current_sequence}",
                )

            # Check if there are any existing credit notes higher than current_sequence
            existing_stmt = select(PlatformCreditNote.credit_note_number).where(
                PlatformCreditNote.credit_note_number.like(f"{self.prefix}-{fy}-%")
            )
            existing_res = await session.execute(existing_stmt)
            existing_nums = existing_res.scalars().all()
            if existing_nums:
                max_found = 0
                for num_str in existing_nums:
                    if not num_str:
                        continue
                    try:
                        parts = num_str.split("-")
                        if len(parts) >= 4 and parts[-1].isdigit():
                            max_found = max(max_found, int(parts[-1]))
                    except Exception:
                        pass
                if seq_row.current_sequence < max_found:
                    seq_row.current_sequence = max_found

            seq_row.current_sequence += 1
            seq_row.updated_at = now_utc
            allocated_seq = seq_row.current_sequence

        if allocated_seq > 99999:
            raise CreditNoteSequenceExhaustedException(
                fiscal_year=fy,
                reason=f"Sequence counter reached maximum limit of 99999 for FY {fy}.",
            )

        # Flush to register row changes and acquire locks in Postgres without premature commit
        await session.flush()

        credit_note_number = f"{self.prefix}-{fy}-{allocated_seq:05d}"
        return credit_note_number, fy

    async def peek_current_sequence(
        self,
        session: AsyncSession,
        fiscal_year: str,
    ) -> int:
        """Inspect the current sequence counter for a fiscal year without advancing it."""
        stmt = select(PlatformCreditNoteSequence.current_sequence).where(
            PlatformCreditNoteSequence.fiscal_year == fiscal_year
        )
        val = await session.scalar(stmt)
        return val or 0
