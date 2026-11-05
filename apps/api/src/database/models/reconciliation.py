"""Bank and Cash Account Reconciliation Models."""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from apps.api.src.database.base import Base, TenantScopedMixin, TimestampMixin

if TYPE_CHECKING:
    from apps.api.src.database.models.billing import Payment
    from apps.api.src.database.models.finance import Account
    from apps.api.src.database.models.society import Society


class ReconciliationSession(Base, TimestampMixin, TenantScopedMixin):
    """
    Bank or Cash Account Reconciliation Session.
    Groups statement lines and tracks reconciliation progress for an accounting period.
    """

    __tablename__ = "reconciliation_sessions"
    __table_args__ = (
        UniqueConstraint("society_id", "session_number", name="uq_reconciliation_session_number"),
        CheckConstraint("statement_end_date >= statement_start_date", name="ck_recon_date_range"),
        Index("ix_recon_sessions_society_account", "society_id", "account_id"),
        Index("ix_recon_sessions_society_status", "society_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    session_number: Mapped[str] = mapped_column(String(50), nullable=False)
    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("accounts.id", ondelete="RESTRICT"),
        nullable=False,
    )
    statement_reference: Mapped[str] = mapped_column(String(100), nullable=False)
    statement_start_date: Mapped[date] = mapped_column(Date, nullable=False)
    statement_end_date: Mapped[date] = mapped_column(Date, nullable=False)

    opening_balance: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), default=Decimal("0.0000"), nullable=False
    )
    closing_balance: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), default=Decimal("0.0000"), nullable=False
    )
    reconciled_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), default=Decimal("0.0000"), nullable=False
    )
    unreconciled_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), default=Decimal("0.0000"), nullable=False
    )

    status: Mapped[str] = mapped_column(
        String(20), default="OPEN", nullable=False
    )  # 'OPEN', 'IN_PROGRESS', 'RECONCILED', 'CLOSED', 'CANCELLED'
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)

    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Relationships
    society: Mapped["Society"] = relationship("Society")
    account: Mapped["Account"] = relationship("Account")
    items: Mapped[list["ReconciliationItem"]] = relationship(
        "ReconciliationItem",
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="ReconciliationItem.transaction_date",
        lazy="selectin",
    )


class ReconciliationItem(Base, TimestampMixin, TenantScopedMixin):
    """
    Individual transaction/statement line item within a Reconciliation Session.
    Matches against a recorded Payment or flags a reconciliation mismatch/unmatched entry.
    """

    __tablename__ = "reconciliation_items"
    __table_args__ = (
        Index("ix_recon_items_session", "session_id"),
        Index("ix_recon_items_payment", "payment_id"),
        Index("ix_recon_items_status", "society_id", "match_status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("reconciliation_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    payment_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("payments.id", ondelete="SET NULL"),
        nullable=True,
    )
    transaction_date: Mapped[date] = mapped_column(Date, nullable=False)
    reference_number: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    statement_amount: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    recorded_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    discrepancy_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), default=Decimal("0.0000"), nullable=False
    )

    match_status: Mapped[str] = mapped_column(
        String(20), default="UNMATCHED", nullable=False
    )  # 'UNMATCHED', 'MATCHED', 'MISMATCH', 'EXCLUDED'
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)

    matched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    matched_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Relationships
    session: Mapped["ReconciliationSession"] = relationship("ReconciliationSession", back_populates="items")
    payment: Mapped["Payment | None"] = relationship("Payment")
