"""Maintenance Billing & Resident Financial Obligations Migration.

Revision ID: 0005_maintenance_billing
Revises: 0004_financial_core
Create Date: 2026-10-02 17:00:00.000000

Establishes:
1. society_billing_configs
2. billing_rules
3. billing_periods
4. invoices
5. invoice_lines
6. billing_adjustments
7. credit_debit_notes
8. payments
9. payment_allocations
10. receipts
11. PostgreSQL Row-Level Security (RLS) policies for all tenant-scoped billing tables.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005_maintenance_billing"
down_revision: str | None = "0004_financial_core"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Society Billing Configs Table
    op.create_table(
        "society_billing_configs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "society_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("societies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("currency", sa.String(3), server_default="INR", nullable=False),
        sa.Column("billing_frequency", sa.String(20), server_default="MONTHLY", nullable=False),
        sa.Column("billing_day", sa.Integer(), server_default="1", nullable=False),
        sa.Column("default_due_days", sa.Integer(), server_default="15", nullable=False),
        sa.Column("late_fee_enabled", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("late_fee_type", sa.String(30), server_default="PERCENTAGE", nullable=False),
        sa.Column("late_fee_rate", sa.Numeric(18, 4), server_default="0.0000", nullable=False),
        sa.Column("grace_period_days", sa.Integer(), server_default="0", nullable=False),
        sa.Column("max_late_fee", sa.Numeric(18, 4), nullable=True),
        sa.Column("interest_enabled", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("auto_generate_enabled", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("approval_required", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("default_responsibility", sa.String(30), server_default="OWNER", nullable=False),
        sa.Column(
            "receivable_account_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("accounts.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "income_account_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("accounts.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "bank_account_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("accounts.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "late_fee_income_account_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("accounts.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "updated_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("society_id", name="uq_billing_config_society"),
    )
    op.create_index("ix_society_billing_configs_society_id", "society_billing_configs", ["society_id"])

    # 2. Maintenance Charge Rules Table
    op.create_table(
        "billing_rules",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "society_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("societies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("code", sa.String(50), nullable=False),
        sa.Column("calculation_type", sa.String(30), nullable=False),
        sa.Column("rate_or_amount", sa.Numeric(18, 4), server_default="0.0000", nullable=False),
        sa.Column("unit_type_rates", postgresql.JSONB(), nullable=True),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("effective_to", sa.Date(), nullable=True),
        sa.Column(
            "income_account_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("accounts.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("description", sa.String(255), nullable=True),
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("society_id", "code", name="uq_billing_rules_society_code"),
    )
    op.create_index("ix_billing_rules_society_id", "billing_rules", ["society_id"])
    op.create_index("ix_billing_rules_society_active", "billing_rules", ["society_id", "is_active"])

    # 3. Billing Periods Table
    op.create_table(
        "billing_periods",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "society_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("societies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "financial_period_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("financial_periods.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("period_code", sa.String(50), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("billing_date", sa.Date(), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(20), server_default="DRAFT", nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "approved_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "published_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "closed_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("society_id", "period_code", name="uq_billing_periods_society_code"),
        sa.CheckConstraint("end_date >= start_date", name="ck_billing_periods_date_range"),
    )
    op.create_index("ix_billing_periods_society_id", "billing_periods", ["society_id"])
    op.create_index("ix_billing_periods_society_status", "billing_periods", ["society_id", "status"])
    op.create_index("ix_billing_periods_financial_period_id", "billing_periods", ["financial_period_id"])

    # 4. Invoices Table
    op.create_table(
        "invoices",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "society_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("societies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "billing_period_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("billing_periods.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "unit_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("units.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "responsible_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("invoice_number", sa.String(50), nullable=False),
        sa.Column("invoice_date", sa.Date(), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("subtotal", sa.Numeric(18, 4), server_default="0.0000", nullable=False),
        sa.Column("adjustment_total", sa.Numeric(18, 4), server_default="0.0000", nullable=False),
        sa.Column("late_fee_total", sa.Numeric(18, 4), server_default="0.0000", nullable=False),
        sa.Column("tax_total", sa.Numeric(18, 4), server_default="0.0000", nullable=False),
        sa.Column("grand_total", sa.Numeric(18, 4), server_default="0.0000", nullable=False),
        sa.Column("paid_amount", sa.Numeric(18, 4), server_default="0.0000", nullable=False),
        sa.Column("outstanding_amount", sa.Numeric(18, 4), server_default="0.0000", nullable=False),
        sa.Column("status", sa.String(20), server_default="DRAFT", nullable=False),
        sa.Column("currency", sa.String(3), server_default="INR", nullable=False),
        sa.Column(
            "journal_entry_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("journal_entries.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("accounting_status", sa.String(20), server_default="NOT_POSTED", nullable=False),
        sa.Column("accounting_error", sa.String(500), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "approved_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "published_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("society_id", "billing_period_id", "unit_id", name="uq_invoices_period_unit"),
        sa.UniqueConstraint("society_id", "invoice_number", name="uq_invoices_society_number"),
    )
    op.create_index("ix_invoices_society_id", "invoices", ["society_id"])
    op.create_index("ix_invoices_society_status", "invoices", ["society_id", "status"])
    op.create_index("ix_invoices_society_unit", "invoices", ["society_id", "unit_id"])
    op.create_index("ix_invoices_society_user", "invoices", ["society_id", "responsible_user_id"])
    op.create_index("ix_invoices_due_date", "invoices", ["society_id", "due_date"])

    # 5. Invoice Lines Table
    op.create_table(
        "invoice_lines",
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
            sa.ForeignKey("invoices.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "charge_rule_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("billing_rules.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("charge_rule_snapshot", postgresql.JSONB(), nullable=True),
        sa.Column("line_number", sa.Integer(), nullable=False),
        sa.Column("description", sa.String(255), nullable=False),
        sa.Column("quantity", sa.Numeric(18, 4), server_default="1.0000", nullable=False),
        sa.Column("unit_rate", sa.Numeric(18, 4), nullable=False),
        sa.Column("amount", sa.Numeric(18, 4), nullable=False),
        sa.Column(
            "accounting_account_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("accounts.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.UniqueConstraint("invoice_id", "line_number", name="uq_invoice_lines_number"),
    )
    op.create_index("ix_invoice_lines_society_id", "invoice_lines", ["society_id"])
    op.create_index("ix_invoice_lines_invoice_id", "invoice_lines", ["invoice_id"])

    # 6. Billing Adjustments Table
    op.create_table(
        "billing_adjustments",
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
            sa.ForeignKey("invoices.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("adjustment_type", sa.String(30), nullable=False),
        sa.Column("amount", sa.Numeric(18, 4), nullable=False),
        sa.Column("reason", sa.String(500), nullable=False),
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_billing_adjustments_society_id", "billing_adjustments", ["society_id"])
    op.create_index("ix_billing_adjustments_invoice", "billing_adjustments", ["invoice_id"])

    # 7. Credit & Debit Notes Table
    op.create_table(
        "credit_debit_notes",
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
            sa.ForeignKey("invoices.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("note_type", sa.String(20), nullable=False),
        sa.Column("note_number", sa.String(50), nullable=False),
        sa.Column("amount", sa.Numeric(18, 4), nullable=False),
        sa.Column("reason", sa.String(500), nullable=False),
        sa.Column(
            "journal_entry_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("journal_entries.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("status", sa.String(20), server_default="APPLIED", nullable=False),
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("society_id", "note_number", name="uq_notes_society_number"),
    )
    op.create_index("ix_credit_debit_notes_society_id", "credit_debit_notes", ["society_id"])
    op.create_index("ix_credit_debit_notes_invoice", "credit_debit_notes", ["invoice_id"])

    # 8. Payments Table
    op.create_table(
        "payments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "society_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("societies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "payer_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "unit_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("units.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("amount", sa.Numeric(18, 4), nullable=False),
        sa.Column("currency", sa.String(3), server_default="INR", nullable=False),
        sa.Column("payment_date", sa.Date(), nullable=False),
        sa.Column("payment_method", sa.String(30), server_default="BANK_TRANSFER", nullable=False),
        sa.Column("reference_number", sa.String(100), nullable=False),
        sa.Column("notes", sa.String(500), nullable=True),
        sa.Column("status", sa.String(20), server_default="RECORDED", nullable=False),
        sa.Column("allocated_amount", sa.Numeric(18, 4), server_default="0.0000", nullable=False),
        sa.Column("unallocated_amount", sa.Numeric(18, 4), server_default="0.0000", nullable=False),
        sa.Column(
            "journal_entry_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("journal_entries.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_payments_society_id", "payments", ["society_id"])
    op.create_index("ix_payments_society_payer", "payments", ["society_id", "payer_user_id"])
    op.create_index("ix_payments_society_date", "payments", ["society_id", "payment_date"])
    op.create_index("ix_payments_society_status", "payments", ["society_id", "status"])

    # 9. Payment Allocations Table
    op.create_table(
        "payment_allocations",
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
            sa.ForeignKey("payments.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "invoice_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("invoices.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("amount", sa.Numeric(18, 4), nullable=False),
        sa.Column("allocated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "allocated_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_payment_allocations_society_id", "payment_allocations", ["society_id"])
    op.create_index("ix_payment_allocations_payment", "payment_allocations", ["payment_id"])
    op.create_index("ix_payment_allocations_invoice", "payment_allocations", ["invoice_id"])

    # 10. Receipts Table
    op.create_table(
        "receipts",
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
            sa.ForeignKey("payments.id", ondelete="RESTRICT"),
            nullable=False,
            unique=True,
        ),
        sa.Column("receipt_number", sa.String(50), nullable=False),
        sa.Column("receipt_date", sa.Date(), nullable=False),
        sa.Column("amount", sa.Numeric(18, 4), nullable=False),
        sa.Column(
            "payer_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "unit_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("units.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("society_id", "receipt_number", name="uq_receipts_society_number"),
    )
    op.create_index("ix_receipts_society_id", "receipts", ["society_id"])
    op.create_index("ix_receipts_society_payer", "receipts", ["society_id", "payer_user_id"])
    op.create_index("ix_receipts_society_payment", "receipts", ["society_id", "payment_id"])

    # 11. PostgreSQL Row-Level Security (RLS) Policies
    bind = op.get_bind()
    if bind and getattr(bind, "dialect", None) and bind.dialect.name == "postgresql":
        billing_rls_tables = [
            "society_billing_configs",
            "billing_rules",
            "billing_periods",
            "invoices",
            "invoice_lines",
            "billing_adjustments",
            "credit_debit_notes",
            "payments",
            "payment_allocations",
            "receipts",
        ]
        for table in billing_rls_tables:
            op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;")
            op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY;")
            op.execute(
                f"""
                CREATE POLICY tenant_isolation_{table} ON {table}
                USING (
                    society_id = NULLIF(current_setting('app.current_society_id', true), '')::uuid
                );
                """
            )


def downgrade() -> None:
    # Drop tables in reverse foreign key order
    op.drop_table("receipts")
    op.drop_table("payment_allocations")
    op.drop_table("payments")
    op.drop_table("credit_debit_notes")
    op.drop_table("billing_adjustments")
    op.drop_table("invoice_lines")
    op.drop_table("invoices")
    op.drop_table("billing_periods")
    op.drop_table("billing_rules")
    op.drop_table("society_billing_configs")
