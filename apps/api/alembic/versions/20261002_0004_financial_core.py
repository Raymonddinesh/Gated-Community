"""Accounting & Financial Core Foundation Migration.

Revision ID: 0004_financial_core
Revises: 0003_auth_sessions
Create Date: 2026-10-02 14:15:00.000000

Establishes:
1. financial_periods
2. accounts (Chart of Accounts)
3. journal_entries (Double-Entry Header)
4. journal_entry_lines (Double-Entry Lines)
5. expenses (Operational Expenses)
6. financial_reports (Versioned Financial Reports)
7. society_accounting_configs (Provider Authority & Config)
8. PostgreSQL Row-Level Security (RLS) policies for all tenant-scoped financial tables.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004_financial_core"
down_revision: str | None = "0003_auth_sessions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Financial Periods Table
    op.create_table(
        "financial_periods",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "society_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("societies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("fiscal_year", sa.String(20), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(20), server_default="OPEN", nullable=False),
        sa.Column("currency", sa.String(3), server_default="INR", nullable=False),
        sa.Column(
            "created_by",
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
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("end_date >= start_date", name="ck_financial_periods_date_range"),
        sa.UniqueConstraint("society_id", "name", name="uq_financial_period_society_name"),
    )
    op.create_index("ix_financial_periods_society_id", "financial_periods", ["society_id"])
    op.create_index("ix_financial_periods_society_status", "financial_periods", ["society_id", "status"])

    # 2. Chart of Accounts Table
    op.create_table(
        "accounts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "society_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("societies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("account_code", sa.String(50), nullable=False),
        sa.Column("account_name", sa.String(150), nullable=False),
        sa.Column("account_type", sa.String(20), nullable=False),
        sa.Column("sub_type", sa.String(50), nullable=True),
        sa.Column(
            "parent_account_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("accounts.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("normal_balance", sa.String(10), nullable=False),
        sa.Column("currency", sa.String(3), server_default="INR", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("is_system_account", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("society_id", "account_code", name="uq_accounts_society_code"),
    )
    op.create_index("ix_accounts_society_id", "accounts", ["society_id"])
    op.create_index("ix_accounts_society_type", "accounts", ["society_id", "account_type"])
    op.create_index("ix_accounts_society_active", "accounts", ["society_id", "is_active"])

    # 3. Journal Entries Table
    op.create_table(
        "journal_entries",
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
        sa.Column("journal_number", sa.String(50), nullable=False),
        sa.Column("entry_date", sa.Date(), nullable=False),
        sa.Column("description", sa.String(500), nullable=False),
        sa.Column("status", sa.String(20), server_default="DRAFT", nullable=False),
        sa.Column("source_type", sa.String(50), server_default="MANUAL", nullable=False),
        sa.Column("source_record_id", sa.String(100), nullable=True),
        sa.Column("reference_number", sa.String(100), nullable=True),
        sa.Column("currency", sa.String(3), server_default="INR", nullable=False),
        sa.Column("total_debit", sa.Numeric(18, 4), server_default="0.0000", nullable=False),
        sa.Column("total_credit", sa.Numeric(18, 4), server_default="0.0000", nullable=False),
        sa.Column("idempotency_key", sa.String(100), nullable=True),
        sa.Column(
            "reversed_entry_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("journal_entries.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("reversal_reason", sa.String(500), nullable=True),
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "posted_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("posted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("society_id", "journal_number", name="uq_journal_society_number"),
    )
    op.create_index("ix_journal_entries_society_id", "journal_entries", ["society_id"])
    op.create_index("ix_journal_entries_financial_period_id", "journal_entries", ["financial_period_id"])
    op.create_index("ix_journal_entries_society_date", "journal_entries", ["society_id", "entry_date"])
    op.create_index("ix_journal_entries_society_status", "journal_entries", ["society_id", "status"])
    op.create_index(
        "ix_journal_entries_idempotency",
        "journal_entries",
        ["society_id", "idempotency_key"],
        unique=True,
        postgresql_where=sa.text("idempotency_key IS NOT NULL"),
    )

    # 4. Journal Entry Lines Table
    op.create_table(
        "journal_entry_lines",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "journal_entry_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("journal_entries.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "society_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("societies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "account_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("accounts.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("line_number", sa.Integer(), nullable=False),
        sa.Column("description", sa.String(255), nullable=True),
        sa.Column("debit_amount", sa.Numeric(18, 4), server_default="0.0000", nullable=False),
        sa.Column("credit_amount", sa.Numeric(18, 4), server_default="0.0000", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "(debit_amount > 0 AND credit_amount = 0) OR (credit_amount > 0 AND debit_amount = 0)",
            name="ck_journal_entry_lines_debit_or_credit",
        ),
        sa.CheckConstraint("debit_amount >= 0 AND credit_amount >= 0", name="ck_journal_lines_non_negative"),
        sa.UniqueConstraint("journal_entry_id", "line_number", name="uq_journal_lines_entry_line_number"),
    )
    op.create_index("ix_journal_entry_lines_journal_entry_id", "journal_entry_lines", ["journal_entry_id"])
    op.create_index("ix_journal_entry_lines_society_id", "journal_entry_lines", ["society_id"])
    op.create_index("ix_journal_entry_lines_account_id", "journal_entry_lines", ["account_id"])

    # 5. Expenses Table
    op.create_table(
        "expenses",
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
        sa.Column("expense_number", sa.String(50), nullable=False),
        sa.Column("expense_date", sa.Date(), nullable=False),
        sa.Column(
            "category_account_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("accounts.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "paid_from_account_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("accounts.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("description", sa.String(500), nullable=False),
        sa.Column("amount", sa.Numeric(18, 4), nullable=False),
        sa.Column("currency", sa.String(3), server_default="INR", nullable=False),
        sa.Column("status", sa.String(20), server_default="DRAFT", nullable=False),
        sa.Column("reference_number", sa.String(100), nullable=True),
        sa.Column("vendor_name", sa.String(200), nullable=True),
        sa.Column(
            "journal_entry_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("journal_entries.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "approved_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("amount > 0", name="ck_expenses_amount_positive"),
        sa.UniqueConstraint("society_id", "expense_number", name="uq_expenses_society_number"),
    )
    op.create_index("ix_expenses_society_id", "expenses", ["society_id"])
    op.create_index("ix_expenses_financial_period_id", "expenses", ["financial_period_id"])
    op.create_index("ix_expenses_society_status", "expenses", ["society_id", "status"])

    # 6. Financial Reports Table
    op.create_table(
        "financial_reports",
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
        sa.Column("report_type", sa.String(50), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("status", sa.String(20), server_default="GENERATED", nullable=False),
        sa.Column("report_data", sa.JSON(), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "generated_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
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
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "society_id", "report_type", "financial_period_id", "version", name="uq_reports_version"
        ),
    )
    op.create_index("ix_financial_reports_society_id", "financial_reports", ["society_id"])
    op.create_index("ix_financial_reports_society_type", "financial_reports", ["society_id", "report_type"])

    # 7. Society Accounting Configs Table
    op.create_table(
        "society_accounting_configs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "society_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("societies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("accounting_mode", sa.String(30), server_default="NATIVE", nullable=False),
        sa.Column("authoritative_source", sa.String(30), server_default="INTERNAL", nullable=False),
        sa.Column("default_currency", sa.String(3), server_default="INR", nullable=False),
        sa.Column("allow_backdated_postings", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("tally_company_name", sa.String(200), nullable=True),
        sa.Column("tally_guid", sa.String(100), nullable=True),
        sa.Column("sync_metadata", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("society_id", name="uq_accounting_config_society"),
    )
    op.create_index("ix_society_accounting_configs_society_id", "society_accounting_configs", ["society_id"])

    # 8. PostgreSQL Row-Level Security (RLS) Policies
    bind = op.get_bind()
    if bind and getattr(bind, "dialect", None) and bind.dialect.name == "postgresql":
        finance_rls_tables = [
            "financial_periods",
            "accounts",
            "journal_entries",
            "journal_entry_lines",
            "expenses",
            "financial_reports",
            "society_accounting_configs",
        ]
        for table in finance_rls_tables:
            op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;")
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
    op.drop_table("society_accounting_configs")
    op.drop_table("financial_reports")
    op.drop_table("expenses")
    op.drop_table("journal_entry_lines")
    op.drop_table("journal_entries")
    op.drop_table("accounts")
    op.drop_table("financial_periods")
