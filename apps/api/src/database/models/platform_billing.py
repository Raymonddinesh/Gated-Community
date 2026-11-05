"""Phase 21E.1 — Commercial SaaS Platform Billing and Financial Core Models.

Domain B: B2B Commercial billing between SocietySphere Ltd and tenant societies.
Completely isolated from Domain A (resident maintenance billing).
"""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from apps.api.src.database.base import Base, TenantScopedMixin, TimestampMixin

if TYPE_CHECKING:
    from apps.api.src.database.models.identity import User
    from apps.api.src.database.models.society import Society
    from apps.api.src.database.models.subscription import (
        PlatformSubscriptionPlan,
        SocietySubscription,
    )


class PlatformInvoiceSequence(Base):
    """
    Global financial-year sequential counter for legal tax invoices.
    Pessimistic row-locking via SELECT ... FOR UPDATE serializes counter progression.
    Not tenant-scoped.
    """

    __tablename__ = "platform_invoice_sequences"
    __table_args__ = (
        CheckConstraint(
            "current_sequence >= 0",
            name="ck_platform_invoice_sequences_non_negative",
        ),
    )

    fiscal_year: Mapped[str] = mapped_column(
        String(10),
        primary_key=True,
    )  # e.g., '2627' for FY 2026-2027
    current_sequence: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
    )


class PlatformCreditNoteSequence(Base):
    """
    Global financial-year sequential counter for statutory credit notes.
    Pessimistic row-locking via SELECT ... FOR UPDATE serializes counter progression.
    Not tenant-scoped.
    """

    __tablename__ = "platform_credit_note_sequences"
    __table_args__ = (
        CheckConstraint(
            "current_sequence >= 0",
            name="ck_platform_credit_note_sequences_non_negative",
        ),
    )

    fiscal_year: Mapped[str] = mapped_column(
        String(10),
        primary_key=True,
    )  # e.g., '2627' for FY 2026-2027
    current_sequence: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
    )


class PlatformPaymentGatewayConfig(Base, TimestampMixin):
    """
    Global platform-wide payment gateway merchant credentials.
    Stores encrypted API keys and webhook secrets for SocietySphere Ltd.
    Not tenant-scoped.
    """

    __tablename__ = "platform_payment_gateway_configs"
    __table_args__ = (
        UniqueConstraint("gateway_provider", name="uq_platform_gateway_configs_provider"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    gateway_provider: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        unique=True,
        index=True,
    )  # 'RAZORPAY', 'STRIPE', 'CASHFREE'
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
    )
    is_test_mode: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
    )
    key_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )  # Merchant ID / Public API Key
    encrypted_secret: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )  # Encrypted Secret Key (Fernet / AES-256)
    webhook_secret_primary: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )  # Encrypted webhook signing secret
    webhook_secret_secondary: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )  # Encrypted secondary secret for zero-downtime rotation


class PlatformWebhookEvent(Base, TimestampMixin):
    """
    Durable global webhook ingestion log and idempotency registry.
    Receives and persists gateway events before worker processing.
    Not tenant-scoped.
    """

    __tablename__ = "platform_webhook_events"
    __table_args__ = (
        UniqueConstraint(
            "gateway_provider", "event_id", name="uq_platform_webhook_provider_event"
        ),
        CheckConstraint(
            "processing_status IN ('PENDING', 'PROCESSING', 'PROCESSED', "
            "'PROCESSED_REFUND_INITIATED', 'FAILED', 'SKIPPED')",
            name="ck_platform_webhook_events_status",
        ),
        Index("ix_platform_webhook_events_status", "processing_status"),
        Index("ix_platform_webhook_events_received", "received_at"),
        Index("ix_platform_webhook_events_society", "society_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    gateway_provider: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )  # 'RAZORPAY', 'STRIPE'
    event_id: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )  # Provider event ID
    event_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )  # 'payment.captured', 'invoice.paid', etc.
    lock_key: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )  # Deterministic signed 64-bit integer for advisory locking
    society_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("societies.id", ondelete="SET NULL"),
        nullable=True,
    )
    payment_reference: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
    )
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
    )
    processing_status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="PENDING",
    )
    processing_attempts: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    last_error: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    processed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    society: Mapped["Society | None"] = relationship("Society")


class PlatformInvoice(Base, TimestampMixin, TenantScopedMixin):
    """
    Official B2B SaaS Tax Invoice issued by SocietySphere Ltd to a tenant Society.
    Enforces FORCE ROW LEVEL SECURITY.
    """

    __tablename__ = "platform_invoices"
    __table_args__ = (
        UniqueConstraint("invoice_number", name="uq_platform_invoices_number"),
        CheckConstraint(
            "status IN ('DRAFT', 'ISSUED', 'PAID', 'PARTIALLY_PAID', 'OVERDUE', 'VOID', 'UNCOLLECTIBLE')",
            name="ck_platform_invoices_status",
        ),
        CheckConstraint(
            "billing_cycle IN ('MONTHLY', 'ANNUAL')",
            name="ck_platform_invoices_billing_cycle",
        ),
        CheckConstraint(
            "grand_total >= 0",
            name="ck_platform_invoices_grand_total_non_negative",
        ),
        CheckConstraint(
            "amount_due >= 0",
            name="ck_platform_invoices_amount_due_non_negative",
        ),
        Index("ix_platform_invoices_society_status", "society_id", "status"),
        Index("ix_platform_invoices_subscription", "subscription_id"),
        Index("ix_platform_invoices_due_date", "due_date"),
        Index("ix_platform_invoices_number", "invoice_number"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    subscription_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("society_subscriptions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    invoice_number: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )  # NULL while DRAFT; allocated at finalization e.g. 'SS-2627-00001'
    fiscal_year: Mapped[str | None] = mapped_column(
        String(10),
        nullable=True,
    )  # e.g., '2627'
    billing_cycle: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        default="MONTHLY",
    )  # 'MONTHLY', 'ANNUAL'
    period_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    period_end: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    subtotal: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
        default=Decimal("0.00"),
    )
    discount_total: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
        default=Decimal("0.00"),
    )
    prorated_credit: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
        default=Decimal("0.00"),
    )
    taxable_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
        default=Decimal("0.00"),
    )
    cgst_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
        default=Decimal("0.00"),
    )
    sgst_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
        default=Decimal("0.00"),
    )
    igst_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
        default=Decimal("0.00"),
    )
    tax_total: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
        default=Decimal("0.00"),
    )
    grand_total: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
        default=Decimal("0.00"),
    )
    credits_applied: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
        default=Decimal("0.00"),
    )
    amount_paid: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
        default=Decimal("0.00"),
    )
    amount_due: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
        default=Decimal("0.00"),
    )
    currency_code: Mapped[str] = mapped_column(
        String(3),
        nullable=False,
        default="INR",
    )
    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="DRAFT",
    )
    due_date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
    )
    issued_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    paid_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    voided_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    void_reason: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    sac_code: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="998313",
    )
    place_of_supply: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )
    customer_gstin: Mapped[str | None] = mapped_column(
        String(15),
        nullable=True,
    )
    idempotency_key: Mapped[str | None] = mapped_column(
        String(150),
        nullable=True,
    )

    society: Mapped["Society"] = relationship("Society")
    subscription: Mapped["SocietySubscription"] = relationship("SocietySubscription")
    items: Mapped[list["PlatformInvoiceItem"]] = relationship(
        "PlatformInvoiceItem",
        back_populates="invoice",
        cascade="all, delete-orphan",
        order_by="PlatformInvoiceItem.item_index",
    )
    payments: Mapped[list["PlatformPayment"]] = relationship(
        "PlatformPayment",
        back_populates="invoice",
    )
    credit_notes: Mapped[list["PlatformCreditNote"]] = relationship(
        "PlatformCreditNote",
        back_populates="invoice",
    )


class PlatformInvoiceItem(Base, TenantScopedMixin):
    """
    Detailed breakdown line item within a PlatformInvoice.
    Denormalizes society_id for direct FORCE RLS enforcement without joins.
    """

    __tablename__ = "platform_invoice_items"
    __table_args__ = (
        UniqueConstraint("invoice_id", "item_index", name="uq_platform_invoice_items_index"),
        CheckConstraint(
            "item_type IN ('BASE_PLAN', 'PRORATION_CREDIT', 'PRORATION_CHARGE', "
            "'DISCOUNT', 'OVERAGE', 'ADJUSTMENT')",
            name="ck_platform_invoice_items_type",
        ),
        Index("ix_platform_invoice_items_invoice", "invoice_id"),
        Index("ix_platform_invoice_items_society", "society_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    invoice_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("platform_invoices.id", ondelete="CASCADE"),
        nullable=False,
    )
    item_index: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    item_type: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
    )  # 'BASE_PLAN', 'PRORATION_CREDIT', etc.
    description: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    sac_code: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="998313",
    )
    quantity: Mapped[Decimal] = mapped_column(
        Numeric(12, 4),
        nullable=False,
        default=Decimal("1.0000"),
    )
    unit_price: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
    )
    discount_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
        default=Decimal("0.00"),
    )
    taxable_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
    )
    tax_rate: Mapped[Decimal] = mapped_column(
        Numeric(5, 2),
        nullable=False,
        default=Decimal("18.00"),
    )
    tax_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
    )
    total_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
    )
    period_start: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    period_end: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
    )

    invoice: Mapped["PlatformInvoice"] = relationship("PlatformInvoice", back_populates="items")
    society: Mapped["Society"] = relationship("Society")


class PlatformPaymentAttempt(Base, TimestampMixin, TenantScopedMixin):
    """
    Transient payment attempt / checkout session initiated with gateway.
    Enforces FORCE ROW LEVEL SECURITY.
    """

    __tablename__ = "platform_payment_attempts"
    __table_args__ = (
        UniqueConstraint(
            "gateway_order_id", name="uq_platform_payment_attempts_order_id"
        ),
        CheckConstraint(
            "amount > 0",
            name="ck_platform_payment_attempts_amount_positive",
        ),
        CheckConstraint(
            "status IN ('CREATED', 'PROCESSING', 'SUCCEEDED', 'FAILED', 'EXPIRED')",
            name="ck_platform_payment_attempts_status",
        ),
        Index("ix_platform_payment_attempts_society_status", "society_id", "status"),
        Index("ix_platform_payment_attempts_invoice", "invoice_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    invoice_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("platform_invoices.id", ondelete="RESTRICT"),
        nullable=False,
    )
    gateway_provider: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )  # 'RAZORPAY', 'STRIPE', 'CASHFREE'
    gateway_order_id: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        unique=True,
    )  # e.g., 'order_XYZ123'
    amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
    )
    currency_code: Mapped[str] = mapped_column(
        String(3),
        nullable=False,
        default="INR",
    )
    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="CREATED",
    )
    idempotency_key: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        unique=True,
    )
    checkout_url: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    error_code: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )
    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    society: Mapped["Society"] = relationship("Society")
    invoice: Mapped["PlatformInvoice"] = relationship("PlatformInvoice")


class PlatformPayment(Base, TimestampMixin, TenantScopedMixin):
    """
    Captured gateway payment transaction for SaaS subscription fees.
    Enforces FORCE ROW LEVEL SECURITY.
    """

    __tablename__ = "platform_payments"
    __table_args__ = (
        UniqueConstraint(
            "gateway_provider",
            "gateway_payment_id",
            name="uq_platform_payments_provider_payment_id",
        ),
        CheckConstraint(
            "amount > 0",
            name="ck_platform_payments_amount_positive",
        ),
        CheckConstraint(
            "refunded_amount >= 0 AND refunded_amount <= amount",
            name="ck_platform_payments_refunded_amount_valid",
        ),
        CheckConstraint(
            "status IN ('CAPTURED', 'REFUNDED', 'PARTIALLY_REFUNDED', 'FAILED', 'DISPUTED')",
            name="ck_platform_payments_status",
        ),
        Index("ix_platform_payments_society_status", "society_id", "status"),
        Index("ix_platform_payments_invoice", "invoice_id"),
        Index("ix_platform_payments_captured", "captured_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    invoice_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("platform_invoices.id", ondelete="RESTRICT"),
        nullable=True,
    )
    payment_attempt_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("platform_payment_attempts.id", ondelete="SET NULL"),
        nullable=True,
    )
    gateway_provider: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )
    gateway_payment_id: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )  # e.g., 'pay_ABC123'
    payment_method: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="CARD",
    )  # 'CARD', 'UPI', 'NETBANKING', 'MANDATE', 'OFFLINE'
    amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
    )
    refunded_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
        default=Decimal("0.00"),
    )
    currency_code: Mapped[str] = mapped_column(
        String(3),
        nullable=False,
        default="INR",
    )
    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="CAPTURED",
    )
    reconciliation_status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="RECONCILED",
    )  # 'RECONCILED', 'UNALLOCATED', 'ORPHAN_ON_CANCELLED_SUBSCRIPTION', 'DISCREPANCY'
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    card_network: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )
    card_last4: Mapped[str | None] = mapped_column(
        String(4),
        nullable=True,
    )
    upi_vpa: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )
    gateway_fee: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
        default=Decimal("0.00"),
    )
    gateway_tax: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
        default=Decimal("0.00"),
    )
    is_settled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )
    settled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    society: Mapped["Society"] = relationship("Society")
    invoice: Mapped["PlatformInvoice | None"] = relationship(
        "PlatformInvoice", back_populates="payments"
    )
    payment_attempt: Mapped["PlatformPaymentAttempt | None"] = relationship(
        "PlatformPaymentAttempt"
    )
    refunds: Mapped[list["PlatformRefund"]] = relationship(
        "PlatformRefund", back_populates="payment"
    )


class PlatformRefund(Base, TimestampMixin, TenantScopedMixin):
    """
    Outflow refund reversing a captured gateway payment.
    Enforces FORCE ROW LEVEL SECURITY.
    """

    __tablename__ = "platform_refunds"
    __table_args__ = (
        UniqueConstraint("gateway_refund_id", name="uq_platform_refunds_gateway_refund_id"),
        CheckConstraint(
            "amount > 0",
            name="ck_platform_refunds_amount_positive",
        ),
        CheckConstraint(
            "status IN ('INITIATED', 'COMPLETED', 'FAILED', 'PENDING_RETRY')",
            name="ck_platform_refunds_status",
        ),
        Index("ix_platform_refunds_society_status", "society_id", "status"),
        Index("ix_platform_refunds_payment", "payment_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    payment_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("platform_payments.id", ondelete="RESTRICT"),
        nullable=False,
    )
    gateway_provider: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )
    gateway_refund_id: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        unique=True,
    )  # e.g., 'rfnd_XYZ123'
    amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
    )
    currency_code: Mapped[str] = mapped_column(
        String(3),
        nullable=False,
        default="INR",
    )
    reason: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )  # 'ORPHAN_PAYMENT_ON_CANCELLED_SUBSCRIPTION', 'CUSTOMER_REQUEST', etc.
    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="INITIATED",
    )
    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    initiated_by: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        default="SYSTEM",
    )  # 'SYSTEM' or user UUID string
    processed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    society: Mapped["Society"] = relationship("Society")
    payment: Mapped["PlatformPayment"] = relationship(
        "PlatformPayment", back_populates="refunds"
    )


class PlatformCreditNote(Base, TimestampMixin, TenantScopedMixin):
    """
    Statutory GST Credit Note issued against a finalized PlatformInvoice.
    Supports DRAFT, ISSUED, and VOID lifecycle.
    Enforces FORCE ROW LEVEL SECURITY.
    """

    __tablename__ = "platform_credit_notes"
    __table_args__ = (
        UniqueConstraint("credit_note_number", name="uq_platform_credit_notes_number"),
        CheckConstraint(
            "grand_total > 0",
            name="ck_platform_credit_notes_grand_total_positive",
        ),
        CheckConstraint(
            "status IN ('DRAFT', 'ISSUED', 'VOID')",
            name="ck_platform_credit_notes_status",
        ),
        Index("ix_platform_credit_notes_society", "society_id"),
        Index("ix_platform_credit_notes_invoice", "invoice_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    invoice_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("platform_invoices.id", ondelete="RESTRICT"),
        nullable=False,
    )
    credit_note_number: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        unique=True,
    )  # e.g., 'SS-CN-2627-00001', NULL for DRAFT
    fiscal_year: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
    )
    taxable_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
    )
    cgst_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
        default=Decimal("0.00"),
    )
    sgst_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
        default=Decimal("0.00"),
    )
    igst_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
        default=Decimal("0.00"),
    )
    tax_total: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
        default=Decimal("0.00"),
    )
    grand_total: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
    )
    currency_code: Mapped[str] = mapped_column(
        String(3),
        nullable=False,
        default="INR",
    )
    reason: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )  # 'SERVICE_DEFICIENCY', 'DOWNGRADE_PRORATION', 'INVOICE_CANCELLATION'
    notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="DRAFT",
    )
    issued_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    society: Mapped["Society"] = relationship("Society")
    invoice: Mapped["PlatformInvoice"] = relationship(
        "PlatformInvoice", back_populates="credit_notes"
    )
    items: Mapped[list["PlatformCreditNoteItem"]] = relationship(
        "PlatformCreditNoteItem",
        back_populates="credit_note",
        cascade="all, delete-orphan",
        order_by="PlatformCreditNoteItem.item_index",
    )
    creator: Mapped["User | None"] = relationship("User")


class PlatformCreditNoteItem(Base, TenantScopedMixin):
    """
    Detailed breakdown line item within a PlatformCreditNote.
    Denormalizes society_id for direct FORCE RLS enforcement without joins.
    """

    __tablename__ = "platform_credit_note_items"
    __table_args__ = (
        UniqueConstraint("credit_note_id", "item_index", name="uq_platform_credit_note_items_index"),
        CheckConstraint(
            "taxable_amount > 0",
            name="ck_platform_credit_note_items_taxable_positive",
        ),
        CheckConstraint(
            "total_amount > 0",
            name="ck_platform_credit_note_items_total_positive",
        ),
        Index("ix_platform_credit_note_items_credit_note", "credit_note_id"),
        Index("ix_platform_credit_note_items_society", "society_id"),
        Index("ix_platform_credit_note_items_invoice_item", "invoice_item_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    credit_note_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("platform_credit_notes.id", ondelete="CASCADE"),
        nullable=False,
    )
    society_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("societies.id", ondelete="RESTRICT"),
        nullable=False,
    )
    invoice_item_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("platform_invoice_items.id", ondelete="RESTRICT"),
        nullable=True,
    )
    item_index: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    description: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    sac_code: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="998313",
    )
    quantity: Mapped[Decimal] = mapped_column(
        Numeric(12, 4),
        nullable=False,
        default=Decimal("1.0000"),
    )
    unit_price: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
    )
    taxable_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
    )
    tax_rate: Mapped[Decimal] = mapped_column(
        Numeric(5, 2),
        nullable=False,
        default=Decimal("18.00"),
    )
    tax_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
    )
    total_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
    )

    credit_note: Mapped["PlatformCreditNote"] = relationship(
        "PlatformCreditNote", back_populates="items"
    )
    invoice_item: Mapped["PlatformInvoiceItem | None"] = relationship(
        "PlatformInvoiceItem"
    )
    society: Mapped["Society"] = relationship("Society")


class PlatformBillingAdjustment(Base, TenantScopedMixin):
    """
    Credits, waivers, and proration adjustments applied to a society.
    Enforces FORCE ROW LEVEL SECURITY.
    """

    __tablename__ = "platform_billing_adjustments"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_platform_billing_adjustments_key"),
        CheckConstraint(
            "amount != 0",
            name="ck_platform_billing_adjustments_amount_nonzero",
        ),
        CheckConstraint(
            "adjustment_type IN ('PRORATION_CREDIT', 'GOODWILL_WAIVER', "
            "'ADVANCE_BALANCE', 'MINIMUM_CHARGE_ROUNDOFF')",
            name="ck_platform_billing_adjustments_type",
        ),
        Index("ix_platform_billing_adjustments_society", "society_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    invoice_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("platform_invoices.id", ondelete="SET NULL"),
        nullable=True,
    )
    credit_note_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("platform_credit_notes.id", ondelete="SET NULL"),
        nullable=True,
    )
    adjustment_type: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
    )  # 'PRORATION_CREDIT', 'GOODWILL_WAIVER', etc.
    amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
    )
    currency_code: Mapped[str] = mapped_column(
        String(3),
        nullable=False,
        default="INR",
    )
    idempotency_key: Mapped[str | None] = mapped_column(
        String(150),
        nullable=True,
        unique=True,
    )
    reason: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    applied_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
    )

    society: Mapped["Society"] = relationship("Society")
    invoice: Mapped["PlatformInvoice | None"] = relationship("PlatformInvoice")
    credit_note: Mapped["PlatformCreditNote | None"] = relationship("PlatformCreditNote")
    creator: Mapped["User | None"] = relationship("User")


class PlatformSubscriptionHistory(Base, TenantScopedMixin):
    """
    Immutable snapshot history of plan tier changes, cycle alterations, and state machine transitions.
    Enforces FORCE ROW LEVEL SECURITY.
    """

    __tablename__ = "platform_subscription_history"
    __table_args__ = (
        Index(
            "ix_platform_subscription_history_soc_sub",
            "society_id",
            "subscription_id",
        ),
        Index("ix_platform_subscription_history_effective", "effective_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    subscription_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("society_subscriptions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    previous_plan_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("platform_subscription_plans.id", ondelete="RESTRICT"),
        nullable=True,
    )
    new_plan_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("platform_subscription_plans.id", ondelete="RESTRICT"),
        nullable=False,
    )
    previous_status: Mapped[str | None] = mapped_column(
        String(30),
        nullable=True,
    )
    new_status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
    )
    previous_cycle: Mapped[str | None] = mapped_column(
        String(10),
        nullable=True,
    )
    new_cycle: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
    )
    transition_reason: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    changed_by: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    effective_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
    )

    society: Mapped["Society"] = relationship("Society")
    subscription: Mapped["SocietySubscription"] = relationship("SocietySubscription")
    previous_plan: Mapped["PlatformSubscriptionPlan | None"] = relationship(
        "PlatformSubscriptionPlan", foreign_keys=[previous_plan_id]
    )
    new_plan: Mapped["PlatformSubscriptionPlan"] = relationship(
        "PlatformSubscriptionPlan", foreign_keys=[new_plan_id]
    )
    changer: Mapped["User | None"] = relationship("User")


class PlatformSubscriptionAuditLog(Base, TenantScopedMixin):
    """
    Financial and subscription audit log with sensitive data redacted (PCI-DSS compliant).
    Enforces FORCE ROW LEVEL SECURITY.
    """

    __tablename__ = "platform_subscription_audit_logs"
    __table_args__ = (
        Index(
            "ix_platform_subscription_audit_soc_entity",
            "society_id",
            "entity_type",
            "entity_id",
        ),
        Index("ix_platform_subscription_audit_created", "created_at"),
        Index("ix_platform_subscription_audit_correlation", "correlation_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    entity_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )  # 'INVOICE', 'PAYMENT', 'REFUND', 'SUBSCRIPTION', 'CREDIT_NOTE', etc.
    entity_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=False,
    )
    action: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )  # 'CREATE', 'UPDATE', 'FINALIZE', 'CAPTURE', 'REFUND', 'VOID'
    actor_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )  # 'USER', 'SYSTEM', 'WEBHOOK'
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    correlation_id: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )
    before_state: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True,
    )
    after_state: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True,
    )
    ip_address: Mapped[str | None] = mapped_column(
        String(45),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
    )

    society: Mapped["Society"] = relationship("Society")
    actor: Mapped["User | None"] = relationship("User")


class PlatformBillingDocument(Base, TenantScopedMixin):
    """
    Permanent metadata registry and checksum audit record for generated billing PDFs.
    Enforces FORCE ROW LEVEL SECURITY.
    """

    __tablename__ = "platform_billing_documents"
    __table_args__ = (
        UniqueConstraint(
            "society_id",
            "document_type",
            "document_id",
            name="uq_platform_billing_docs_tenant_entity",
        ),
        UniqueConstraint(
            "document_type",
            "document_number",
            name="uq_platform_billing_docs_number",
        ),
        CheckConstraint(
            "document_type IN ('INVOICE', 'CREDIT_NOTE')",
            name="ck_platform_billing_docs_type",
        ),
        CheckConstraint(
            "file_size_bytes > 0",
            name="ck_platform_billing_docs_file_size_positive",
        ),
        Index("ix_platform_billing_docs_society_type", "society_id", "document_type"),
        Index("ix_platform_billing_docs_doc_id", "document_id"),
        Index("ix_platform_billing_docs_checksum", "sha256_checksum"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    document_type: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
    )  # 'INVOICE', 'CREDIT_NOTE'
    document_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=False,
        index=True,
    )
    document_number: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )  # e.g., 'SS-2627-00001', 'SS-CN-2627-00001'
    storage_key: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )
    sha256_checksum: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )
    file_size_bytes: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    content_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="application/pdf",
    )
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
    )
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True,
    )

    society: Mapped["Society"] = relationship("Society")
    deliveries: Mapped[list["PlatformDocumentDelivery"]] = relationship(
        "PlatformDocumentDelivery",
        back_populates="document",
        cascade="all, delete-orphan",
    )


class PlatformDocumentDelivery(Base, TimestampMixin, TenantScopedMixin):
    """
    Idempotent document delivery execution log (Email / Webhook).
    Enforces FORCE ROW LEVEL SECURITY.
    """

    __tablename__ = "platform_document_deliveries"
    __table_args__ = (
        UniqueConstraint(
            "idempotency_key",
            name="uq_platform_document_deliveries_idempotency",
        ),
        CheckConstraint(
            "channel IN ('EMAIL', 'WEBHOOK')",
            name="ck_platform_document_deliveries_channel",
        ),
        CheckConstraint(
            "status IN ('QUEUED', 'PROCESSING', 'SENT', 'FAILED', 'RETRYING')",
            name="ck_platform_document_deliveries_status",
        ),
        CheckConstraint(
            "attempt_count >= 0",
            name="ck_platform_document_deliveries_attempt_non_negative",
        ),
        Index("ix_platform_document_deliveries_society_status", "society_id", "status"),
        Index("ix_platform_document_deliveries_doc_id", "document_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("platform_billing_documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    channel: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="EMAIL",
    )
    recipient_email: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="QUEUED",
    )  # 'QUEUED', 'PROCESSING', 'SENT', 'FAILED', 'RETRYING'
    attempt_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    max_attempts: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=3,
    )
    next_retry_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    idempotency_key: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        unique=True,
    )
    provider_message_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    society: Mapped["Society"] = relationship("Society")
    document: Mapped["PlatformBillingDocument"] = relationship(
        "PlatformBillingDocument",
        back_populates="deliveries",
    )
    attempts: Mapped[list["PlatformDocumentDeliveryAttempt"]] = relationship(
        "PlatformDocumentDeliveryAttempt",
        back_populates="delivery",
        cascade="all, delete-orphan",
        order_by="PlatformDocumentDeliveryAttempt.attempt_number",
    )


class PlatformDocumentDeliveryAttempt(Base, TenantScopedMixin):
    """
    Transactional attempt record for each delivery attempt.
    Enforces FORCE ROW LEVEL SECURITY.
    """

    __tablename__ = "platform_document_delivery_attempts"
    __table_args__ = (
        UniqueConstraint(
            "delivery_id",
            "attempt_number",
            name="uq_platform_delivery_attempts_num",
        ),
        CheckConstraint(
            "attempt_number > 0",
            name="ck_platform_delivery_attempts_num_positive",
        ),
        CheckConstraint(
            "status IN ('SUCCESS', 'FAILURE')",
            name="ck_platform_delivery_attempts_status",
        ),
        Index("ix_platform_delivery_attempts_society", "society_id"),
        Index("ix_platform_delivery_attempts_delivery_id", "delivery_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    delivery_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("platform_document_deliveries.id", ondelete="CASCADE"),
        nullable=False,
    )
    attempt_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
    )  # 'SUCCESS', 'FAILURE'
    provider_name: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )
    provider_response_code: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )
    provider_request_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    latency_ms: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
    )

    society: Mapped["Society"] = relationship("Society")
    delivery: Mapped["PlatformDocumentDelivery"] = relationship(
        "PlatformDocumentDelivery",
        back_populates="attempts",
    )


class PlatformBillingJobRun(Base, TimestampMixin):
    """
    Global platform operational ledger tracking automated billing scheduler runs.
    Not tenant-scoped.
    """

    __tablename__ = "platform_billing_job_runs"
    __table_args__ = (
        UniqueConstraint("execution_id", name="uq_platform_billing_job_runs_exec_id"),
        CheckConstraint(
            "status IN ('RUNNING', 'COMPLETED', 'FAILED', 'PARTIAL')",
            name="ck_platform_billing_job_runs_status",
        ),
        CheckConstraint(
            "processed_count >= 0",
            name="ck_platform_billing_job_runs_processed_non_negative",
        ),
        CheckConstraint(
            "succeeded_count >= 0",
            name="ck_platform_billing_job_runs_succeeded_non_negative",
        ),
        CheckConstraint(
            "failed_count >= 0",
            name="ck_platform_billing_job_runs_failed_non_negative",
        ),
        CheckConstraint(
            "skipped_count >= 0",
            name="ck_platform_billing_job_runs_skipped_non_negative",
        ),
        Index("ix_platform_billing_job_runs_type_status", "job_type", "status"),
        Index("ix_platform_billing_job_runs_started_at", "started_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    job_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )  # e.g., 'PERIOD_ROLL', 'RENEWAL_INVOICING', 'DUNNING_EVAL'
    execution_id: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        unique=True,
    )
    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="RUNNING",
    )  # 'RUNNING', 'COMPLETED', 'FAILED', 'PARTIAL'
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    processed_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    succeeded_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    failed_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    skipped_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    error_summary: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    diagnostics: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True,
    )


class PlatformDunningAttempt(Base, TenantScopedMixin):
    """
    Tenant-scoped dunning execution and retry audit ledger.
    Enforces FORCE ROW LEVEL SECURITY.
    """

    __tablename__ = "platform_dunning_attempts"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_platform_dunning_attempts_idempotency"),
        CheckConstraint(
            "status IN ('PENDING', 'PROCESSING', 'SUCCEEDED', 'FAILED', 'SKIPPED')",
            name="ck_platform_dunning_attempts_status",
        ),
        CheckConstraint(
            "retry_count >= 0",
            name="ck_platform_dunning_attempts_retry_non_negative",
        ),
        Index("ix_platform_dunning_attempts_society_sub", "society_id", "subscription_id"),
        Index("ix_platform_dunning_attempts_society_status", "society_id", "status"),
        Index("ix_platform_dunning_attempts_invoice", "invoice_id"),
        Index("ix_platform_dunning_attempts_scheduled", "scheduled_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    subscription_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("society_subscriptions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    invoice_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("platform_invoices.id", ondelete="SET NULL"),
        nullable=True,
    )
    attempt_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )  # 'PAYMENT_RETRY', 'REMINDER_NOTICE', 'SUSPENSION_WARNING', 'SUSPENSION_EXECUTION'
    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="PENDING",
    )  # 'PENDING', 'PROCESSING', 'SUCCEEDED', 'FAILED', 'SKIPPED'
    idempotency_key: Mapped[str] = mapped_column(
        String(150),
        nullable=False,
        unique=True,
    )
    scheduled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    executed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    retry_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    grace_days_remaining: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    provider_reference: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )
    failure_reason: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
    )

    society: Mapped["Society"] = relationship("Society")
    subscription: Mapped["SocietySubscription"] = relationship("SocietySubscription")
    invoice: Mapped["PlatformInvoice | None"] = relationship("PlatformInvoice")


