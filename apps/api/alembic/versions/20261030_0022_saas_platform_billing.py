"""Phase 21E.1 — Commercial SaaS Platform Billing Foundation.

Revision ID: 0022_saas_platform_billing
Revises: 0021_saas_platform_subscriptions
Create Date: 2026-10-30
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0022_saas_platform_billing"
down_revision: str | None = "0021_saas_platform_subscriptions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # =========================================================================
    # 1. Augment society_subscriptions with operational billing columns
    # =========================================================================
    op.add_column(
        "society_subscriptions",
        sa.Column("billing_cycle", sa.String(10), nullable=False, server_default="MONTHLY"),
    )
    op.create_check_constraint(
        "ck_society_subscriptions_billing_cycle",
        "society_subscriptions",
        "billing_cycle IN ('MONTHLY', 'ANNUAL')",
    )
    op.add_column(
        "society_subscriptions",
        sa.Column("auto_renew", sa.Boolean(), nullable=False, server_default="true"),
    )
    op.add_column(
        "society_subscriptions",
        sa.Column("gateway_customer_id", sa.String(100), nullable=True),
    )
    op.add_column(
        "society_subscriptions",
        sa.Column("gateway_subscription_id", sa.String(100), nullable=True),
    )
    op.add_column(
        "society_subscriptions",
        sa.Column("next_billing_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_society_subscriptions_gateway_customer",
        "society_subscriptions",
        ["gateway_customer_id"],
    )
    op.create_index(
        "ix_society_subscriptions_gateway_sub",
        "society_subscriptions",
        ["gateway_subscription_id"],
    )
    op.create_index(
        "ix_society_subscriptions_next_billing",
        "society_subscriptions",
        ["next_billing_at"],
    )

    # =========================================================================
    # 2. Global Table: platform_invoice_sequences
    # =========================================================================
    op.create_table(
        "platform_invoice_sequences",
        sa.Column("fiscal_year", sa.String(10), primary_key=True),
        sa.Column("current_sequence", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "current_sequence >= 0",
            name="ck_platform_invoice_sequences_non_negative",
        ),
    )

    # =========================================================================
    # 3. Global Table: platform_payment_gateway_configs
    # =========================================================================
    op.create_table(
        "platform_payment_gateway_configs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("gateway_provider", sa.String(50), nullable=False, unique=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("is_test_mode", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("key_id", sa.String(255), nullable=False),
        sa.Column("encrypted_secret", sa.Text(), nullable=False),
        sa.Column("webhook_secret_primary", sa.Text(), nullable=False),
        sa.Column("webhook_secret_secondary", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_platform_payment_gateway_configs_provider",
        "platform_payment_gateway_configs",
        ["gateway_provider"],
    )

    # =========================================================================
    # 4. Global Table: platform_webhook_events
    # =========================================================================
    op.create_table(
        "platform_webhook_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("gateway_provider", sa.String(50), nullable=False),
        sa.Column("event_id", sa.String(100), nullable=False),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("lock_key", sa.BigInteger(), nullable=False),
        sa.Column(
            "society_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("societies.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("payment_reference", sa.String(100), nullable=True),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("processing_status", sa.String(50), nullable=False, server_default="PENDING"),
        sa.Column("processing_attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint(
            "gateway_provider", "event_id", name="uq_platform_webhook_provider_event"
        ),
        sa.CheckConstraint(
            "processing_status IN ('PENDING', 'PROCESSING', 'PROCESSED', "
            "'PROCESSED_REFUND_INITIATED', 'FAILED', 'SKIPPED')",
            name="ck_platform_webhook_events_status",
        ),
    )
    op.create_index("ix_platform_webhook_events_status", "platform_webhook_events", ["processing_status"])
    op.create_index("ix_platform_webhook_events_received", "platform_webhook_events", ["received_at"])
    op.create_index("ix_platform_webhook_events_society", "platform_webhook_events", ["society_id"])

    # =========================================================================
    # 5. Tenant Table: platform_invoices
    # =========================================================================
    op.create_table(
        "platform_invoices",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "society_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("societies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "subscription_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("society_subscriptions.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("invoice_number", sa.String(50), nullable=True, unique=True),
        sa.Column("fiscal_year", sa.String(10), nullable=True),
        sa.Column("billing_cycle", sa.String(10), nullable=False, server_default="MONTHLY"),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("subtotal", sa.Numeric(12, 2), nullable=False, server_default="0.00"),
        sa.Column("discount_total", sa.Numeric(12, 2), nullable=False, server_default="0.00"),
        sa.Column("prorated_credit", sa.Numeric(12, 2), nullable=False, server_default="0.00"),
        sa.Column("taxable_amount", sa.Numeric(12, 2), nullable=False, server_default="0.00"),
        sa.Column("cgst_amount", sa.Numeric(12, 2), nullable=False, server_default="0.00"),
        sa.Column("sgst_amount", sa.Numeric(12, 2), nullable=False, server_default="0.00"),
        sa.Column("igst_amount", sa.Numeric(12, 2), nullable=False, server_default="0.00"),
        sa.Column("tax_total", sa.Numeric(12, 2), nullable=False, server_default="0.00"),
        sa.Column("grand_total", sa.Numeric(12, 2), nullable=False, server_default="0.00"),
        sa.Column("credits_applied", sa.Numeric(12, 2), nullable=False, server_default="0.00"),
        sa.Column("amount_paid", sa.Numeric(12, 2), nullable=False, server_default="0.00"),
        sa.Column("amount_due", sa.Numeric(12, 2), nullable=False, server_default="0.00"),
        sa.Column("currency_code", sa.String(3), nullable=False, server_default="INR"),
        sa.Column("status", sa.String(30), nullable=False, server_default="DRAFT"),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("voided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("void_reason", sa.Text(), nullable=True),
        sa.Column("sac_code", sa.String(20), nullable=False, server_default="998313"),
        sa.Column("place_of_supply", sa.String(100), nullable=False),
        sa.Column("customer_gstin", sa.String(15), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "status IN ('DRAFT', 'ISSUED', 'PAID', 'PARTIALLY_PAID', 'OVERDUE', 'VOID', 'UNCOLLECTIBLE')",
            name="ck_platform_invoices_status",
        ),
        sa.CheckConstraint(
            "billing_cycle IN ('MONTHLY', 'ANNUAL')",
            name="ck_platform_invoices_billing_cycle",
        ),
        sa.CheckConstraint(
            "grand_total >= 0",
            name="ck_platform_invoices_grand_total_non_negative",
        ),
        sa.CheckConstraint(
            "amount_due >= 0",
            name="ck_platform_invoices_amount_due_non_negative",
        ),
    )
    op.create_index(
        "ix_platform_invoices_society_status",
        "platform_invoices",
        ["society_id", "status"],
    )
    op.create_index("ix_platform_invoices_subscription", "platform_invoices", ["subscription_id"])
    op.create_index("ix_platform_invoices_due_date", "platform_invoices", ["due_date"])
    op.create_index("ix_platform_invoices_number", "platform_invoices", ["invoice_number"])

    # =========================================================================
    # 6. Tenant Table: platform_invoice_items
    # =========================================================================
    op.create_table(
        "platform_invoice_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "invoice_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("platform_invoices.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "society_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("societies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("item_index", sa.Integer(), nullable=False),
        sa.Column("item_type", sa.String(30), nullable=False),
        sa.Column("description", sa.String(255), nullable=False),
        sa.Column("sac_code", sa.String(20), nullable=False, server_default="998313"),
        sa.Column("quantity", sa.Numeric(12, 4), nullable=False, server_default="1.0000"),
        sa.Column("unit_price", sa.Numeric(12, 2), nullable=False),
        sa.Column("discount_amount", sa.Numeric(12, 2), nullable=False, server_default="0.00"),
        sa.Column("taxable_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("tax_rate", sa.Numeric(5, 2), nullable=False, server_default="18.00"),
        sa.Column("tax_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("total_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint(
            "invoice_id", "item_index", name="uq_platform_invoice_items_index"
        ),
        sa.CheckConstraint(
            "item_type IN ('BASE_PLAN', 'PRORATION_CREDIT', 'PRORATION_CHARGE', "
            "'DISCOUNT', 'OVERAGE', 'ADJUSTMENT')",
            name="ck_platform_invoice_items_type",
        ),
    )
    op.create_index("ix_platform_invoice_items_invoice", "platform_invoice_items", ["invoice_id"])
    op.create_index("ix_platform_invoice_items_society", "platform_invoice_items", ["society_id"])

    # =========================================================================
    # 7. Tenant Table: platform_payment_attempts
    # =========================================================================
    op.create_table(
        "platform_payment_attempts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "society_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("societies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "invoice_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("platform_invoices.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("gateway_provider", sa.String(50), nullable=False),
        sa.Column("gateway_order_id", sa.String(100), nullable=False, unique=True),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency_code", sa.String(3), nullable=False, server_default="INR"),
        sa.Column("status", sa.String(30), nullable=False, server_default="CREATED"),
        sa.Column("idempotency_key", sa.String(100), nullable=True, unique=True),
        sa.Column("checkout_url", sa.Text(), nullable=True),
        sa.Column("error_code", sa.String(100), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "amount > 0",
            name="ck_platform_payment_attempts_amount_positive",
        ),
        sa.CheckConstraint(
            "status IN ('CREATED', 'PROCESSING', 'SUCCEEDED', 'FAILED', 'EXPIRED')",
            name="ck_platform_payment_attempts_status",
        ),
    )
    op.create_index(
        "ix_platform_payment_attempts_society_status",
        "platform_payment_attempts",
        ["society_id", "status"],
    )
    op.create_index("ix_platform_payment_attempts_invoice", "platform_payment_attempts", ["invoice_id"])

    # =========================================================================
    # 8. Tenant Table: platform_payments
    # =========================================================================
    op.create_table(
        "platform_payments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "society_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("societies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "invoice_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("platform_invoices.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "payment_attempt_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("platform_payment_attempts.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("gateway_provider", sa.String(50), nullable=False),
        sa.Column("gateway_payment_id", sa.String(100), nullable=False),
        sa.Column("payment_method", sa.String(50), nullable=False, server_default="CARD"),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("refunded_amount", sa.Numeric(12, 2), nullable=False, server_default="0.00"),
        sa.Column("currency_code", sa.String(3), nullable=False, server_default="INR"),
        sa.Column("status", sa.String(30), nullable=False, server_default="CAPTURED"),
        sa.Column(
            "reconciliation_status",
            sa.String(50),
            nullable=False,
            server_default="RECONCILED",
        ),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("card_network", sa.String(50), nullable=True),
        sa.Column("card_last4", sa.String(4), nullable=True),
        sa.Column("upi_vpa", sa.String(100), nullable=True),
        sa.Column("gateway_fee", sa.Numeric(12, 2), nullable=False, server_default="0.00"),
        sa.Column("gateway_tax", sa.Numeric(12, 2), nullable=False, server_default="0.00"),
        sa.Column("is_settled", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("settled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint(
            "gateway_provider",
            "gateway_payment_id",
            name="uq_platform_payments_provider_payment_id",
        ),
        sa.CheckConstraint(
            "amount > 0",
            name="ck_platform_payments_amount_positive",
        ),
        sa.CheckConstraint(
            "refunded_amount >= 0 AND refunded_amount <= amount",
            name="ck_platform_payments_refunded_amount_valid",
        ),
        sa.CheckConstraint(
            "status IN ('CAPTURED', 'REFUNDED', 'PARTIALLY_REFUNDED', 'FAILED', 'DISPUTED')",
            name="ck_platform_payments_status",
        ),
    )
    op.create_index(
        "ix_platform_payments_society_status",
        "platform_payments",
        ["society_id", "status"],
    )
    op.create_index("ix_platform_payments_invoice", "platform_payments", ["invoice_id"])
    op.create_index("ix_platform_payments_captured", "platform_payments", ["captured_at"])

    # =========================================================================
    # 9. Tenant Table: platform_refunds
    # =========================================================================
    op.create_table(
        "platform_refunds",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "society_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("societies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "payment_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("platform_payments.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("gateway_provider", sa.String(50), nullable=False),
        sa.Column("gateway_refund_id", sa.String(100), nullable=True, unique=True),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency_code", sa.String(3), nullable=False, server_default="INR"),
        sa.Column("reason", sa.String(100), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="INITIATED"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("initiated_by", sa.String(100), nullable=False, server_default="SYSTEM"),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "amount > 0",
            name="ck_platform_refunds_amount_positive",
        ),
        sa.CheckConstraint(
            "status IN ('INITIATED', 'COMPLETED', 'FAILED', 'PENDING_RETRY')",
            name="ck_platform_refunds_status",
        ),
    )
    op.create_index(
        "ix_platform_refunds_society_status",
        "platform_refunds",
        ["society_id", "status"],
    )
    op.create_index("ix_platform_refunds_payment", "platform_refunds", ["payment_id"])

    # =========================================================================
    # 10. Tenant Table: platform_credit_notes
    # =========================================================================
    op.create_table(
        "platform_credit_notes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "society_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("societies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "invoice_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("platform_invoices.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("credit_note_number", sa.String(50), nullable=False, unique=True),
        sa.Column("fiscal_year", sa.String(10), nullable=False),
        sa.Column("taxable_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("cgst_amount", sa.Numeric(12, 2), nullable=False, server_default="0.00"),
        sa.Column("sgst_amount", sa.Numeric(12, 2), nullable=False, server_default="0.00"),
        sa.Column("igst_amount", sa.Numeric(12, 2), nullable=False, server_default="0.00"),
        sa.Column("tax_total", sa.Numeric(12, 2), nullable=False, server_default="0.00"),
        sa.Column("grand_total", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency_code", sa.String(3), nullable=False, server_default="INR"),
        sa.Column("reason", sa.String(100), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("status", sa.String(30), nullable=False, server_default="ISSUED"),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "grand_total > 0",
            name="ck_platform_credit_notes_grand_total_positive",
        ),
        sa.CheckConstraint(
            "status IN ('ISSUED', 'VOID')",
            name="ck_platform_credit_notes_status",
        ),
    )
    op.create_index("ix_platform_credit_notes_society", "platform_credit_notes", ["society_id"])
    op.create_index("ix_platform_credit_notes_invoice", "platform_credit_notes", ["invoice_id"])

    # =========================================================================
    # 11. Tenant Table: platform_billing_adjustments
    # =========================================================================
    op.create_table(
        "platform_billing_adjustments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "society_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("societies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "invoice_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("platform_invoices.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "credit_note_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("platform_credit_notes.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("adjustment_type", sa.String(30), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency_code", sa.String(3), nullable=False, server_default="INR"),
        sa.Column("idempotency_key", sa.String(150), nullable=True, unique=True),
        sa.Column("reason", sa.String(255), nullable=False),
        sa.Column(
            "applied_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "amount != 0",
            name="ck_platform_billing_adjustments_amount_nonzero",
        ),
        sa.CheckConstraint(
            "adjustment_type IN ('PRORATION_CREDIT', 'GOODWILL_WAIVER', "
            "'ADVANCE_BALANCE', 'MINIMUM_CHARGE_ROUNDOFF')",
            name="ck_platform_billing_adjustments_type",
        ),
    )
    op.create_index(
        "ix_platform_billing_adjustments_society",
        "platform_billing_adjustments",
        ["society_id"],
    )

    # =========================================================================
    # 12. Tenant Table: platform_subscription_history
    # =========================================================================
    op.create_table(
        "platform_subscription_history",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "society_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("societies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "subscription_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("society_subscriptions.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "previous_plan_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("platform_subscription_plans.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "new_plan_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("platform_subscription_plans.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("previous_status", sa.String(30), nullable=True),
        sa.Column("new_status", sa.String(30), nullable=False),
        sa.Column("previous_cycle", sa.String(10), nullable=True),
        sa.Column("new_cycle", sa.String(10), nullable=False),
        sa.Column("transition_reason", sa.String(255), nullable=False),
        sa.Column(
            "changed_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("effective_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_platform_subscription_history_soc_sub",
        "platform_subscription_history",
        ["society_id", "subscription_id"],
    )
    op.create_index(
        "ix_platform_subscription_history_effective",
        "platform_subscription_history",
        ["effective_at"],
    )

    # =========================================================================
    # 13. Tenant Table: platform_subscription_audit_logs
    # =========================================================================
    op.create_table(
        "platform_subscription_audit_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "society_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("societies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("entity_type", sa.String(50), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("action", sa.String(50), nullable=False),
        sa.Column("actor_type", sa.String(20), nullable=False),
        sa.Column(
            "actor_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("correlation_id", sa.String(100), nullable=True),
        sa.Column("before_state", postgresql.JSONB(), nullable=True),
        sa.Column("after_state", postgresql.JSONB(), nullable=True),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_platform_subscription_audit_soc_entity",
        "platform_subscription_audit_logs",
        ["society_id", "entity_type", "entity_id"],
    )
    op.create_index(
        "ix_platform_subscription_audit_created",
        "platform_subscription_audit_logs",
        ["created_at"],
    )
    op.create_index(
        "ix_platform_subscription_audit_correlation",
        "platform_subscription_audit_logs",
        ["correlation_id"],
    )

    # =========================================================================
    # 14. Enable & Force Row-Level Security on all 9 Tenant-Scoped Billing Tables
    # =========================================================================
    tenant_tables = [
        "platform_invoices",
        "platform_invoice_items",
        "platform_payment_attempts",
        "platform_payments",
        "platform_refunds",
        "platform_credit_notes",
        "platform_billing_adjustments",
        "platform_subscription_history",
        "platform_subscription_audit_logs",
    ]

    for table in tenant_tables:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY;")
        op.execute(
            f"CREATE POLICY {table}_tenant_isolation ON {table} "
            f"USING (society_id = NULLIF(current_setting('app.current_society_id', true), '')::uuid);"
        )


def downgrade() -> None:
    # 1. Drop RLS policies on all 9 tenant-scoped tables
    tenant_tables = [
        "platform_subscription_audit_logs",
        "platform_subscription_history",
        "platform_billing_adjustments",
        "platform_credit_notes",
        "platform_refunds",
        "platform_payments",
        "platform_payment_attempts",
        "platform_invoice_items",
        "platform_invoices",
    ]

    for table in tenant_tables:
        op.execute(f"DROP POLICY IF EXISTS {table}_tenant_isolation ON {table};")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY;")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;")

    # 2. Drop all 12 tables in reverse dependency order
    all_new_tables = [
        "platform_subscription_audit_logs",
        "platform_subscription_history",
        "platform_billing_adjustments",
        "platform_credit_notes",
        "platform_refunds",
        "platform_payments",
        "platform_payment_attempts",
        "platform_invoice_items",
        "platform_invoices",
        "platform_webhook_events",
        "platform_payment_gateway_configs",
        "platform_invoice_sequences",
    ]

    for table in all_new_tables:
        op.drop_table(table)

    # 3. Remove columns added to society_subscriptions
    op.drop_index("ix_society_subscriptions_next_billing", table_name="society_subscriptions")
    op.drop_index("ix_society_subscriptions_gateway_sub", table_name="society_subscriptions")
    op.drop_index("ix_society_subscriptions_gateway_customer", table_name="society_subscriptions")
    op.drop_constraint("ck_society_subscriptions_billing_cycle", "society_subscriptions", type_="check")
    op.drop_column("society_subscriptions", "next_billing_at")
    op.drop_column("society_subscriptions", "gateway_subscription_id")
    op.drop_column("society_subscriptions", "gateway_customer_id")
    op.drop_column("society_subscriptions", "auto_renew")
    op.drop_column("society_subscriptions", "billing_cycle")
