"""Resident Payments, Receipts & Bank Reconciliation Migration.

Revision ID: 0006_payments_reconciliation
Revises: 0005_maintenance_billing
Create Date: 2026-10-03 00:00:00.000000

Establishes:
1. Enhances payments table: bank_account_id, idempotency_key, reversal tracking.
2. Enhances receipts table: status, cancelled_at, cancelled_by, cancellation_reason.
3. reconciliation_sessions table.
4. reconciliation_items table.
5. PostgreSQL Row-Level Security (RLS) policies for reconciliation tables.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006_payments_reconciliation"
down_revision: str | None = "0005_maintenance_billing"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Enhance payments table
    op.add_column(
        "payments",
        sa.Column(
            "bank_account_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("accounts.id", ondelete="RESTRICT"),
            nullable=True,
        ),
    )
    op.add_column("payments", sa.Column("idempotency_key", sa.String(100), nullable=True))
    op.add_column(
        "payments",
        sa.Column(
            "reversal_journal_entry_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("journal_entries.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column("payments", sa.Column("reversal_reason", sa.String(500), nullable=True))
    op.add_column("payments", sa.Column("reversed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "payments",
        sa.Column(
            "reversed_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_payments_bank_account", "payments", ["society_id", "bank_account_id"])
    op.create_index("ix_payments_idempotency", "payments", ["society_id", "idempotency_key"])

    # 2. Enhance receipts table
    op.add_column(
        "receipts",
        sa.Column("status", sa.String(20), server_default="ISSUED", nullable=False),
    )
    op.add_column("receipts", sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "receipts",
        sa.Column(
            "cancelled_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column("receipts", sa.Column("cancellation_reason", sa.String(500), nullable=True))
    op.create_index("ix_receipts_society_status", "receipts", ["society_id", "status"])

    # 2b. Enhance payment_allocations table
    op.add_column(
        "payment_allocations",
        sa.Column("status", sa.String(20), server_default="ACTIVE", nullable=False),
    )
    op.add_column("payment_allocations", sa.Column("reversed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "payment_allocations",
        sa.Column(
            "reversed_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column("payment_allocations", sa.Column("reversal_reason", sa.String(500), nullable=True))
    op.add_column("payment_allocations", sa.Column("reversal_reference", sa.String(100), nullable=True))
    op.create_index("ix_payment_allocations_society_status", "payment_allocations", ["society_id", "status"])

    # 3. Create reconciliation_sessions table
    op.create_table(
        "reconciliation_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "society_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("societies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("session_number", sa.String(50), nullable=False),
        sa.Column(
            "account_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("accounts.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("statement_reference", sa.String(100), nullable=False),
        sa.Column("statement_start_date", sa.Date(), nullable=False),
        sa.Column("statement_end_date", sa.Date(), nullable=False),
        sa.Column("opening_balance", sa.Numeric(18, 4), server_default="0.0000", nullable=False),
        sa.Column("closing_balance", sa.Numeric(18, 4), server_default="0.0000", nullable=False),
        sa.Column("reconciled_amount", sa.Numeric(18, 4), server_default="0.0000", nullable=False),
        sa.Column("unreconciled_amount", sa.Numeric(18, 4), server_default="0.0000", nullable=False),
        sa.Column("status", sa.String(20), server_default="OPEN", nullable=False),
        sa.Column("notes", sa.String(500), nullable=True),
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
        sa.UniqueConstraint("society_id", "session_number", name="uq_reconciliation_session_number"),
        sa.CheckConstraint("statement_end_date >= statement_start_date", name="ck_recon_date_range"),
    )
    op.create_index("ix_recon_sessions_society_id", "reconciliation_sessions", ["society_id"])
    op.create_index(
        "ix_recon_sessions_society_account", "reconciliation_sessions", ["society_id", "account_id"]
    )
    op.create_index("ix_recon_sessions_society_status", "reconciliation_sessions", ["society_id", "status"])

    # 4. Create reconciliation_items table
    op.create_table(
        "reconciliation_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "society_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("societies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("reconciliation_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "payment_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("payments.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("transaction_date", sa.Date(), nullable=False),
        sa.Column("reference_number", sa.String(100), nullable=False),
        sa.Column("description", sa.String(255), nullable=False),
        sa.Column("statement_amount", sa.Numeric(18, 4), nullable=False),
        sa.Column("recorded_amount", sa.Numeric(18, 4), nullable=True),
        sa.Column("discrepancy_amount", sa.Numeric(18, 4), server_default="0.0000", nullable=False),
        sa.Column("match_status", sa.String(20), server_default="UNMATCHED", nullable=False),
        sa.Column("notes", sa.String(500), nullable=True),
        sa.Column("matched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "matched_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_recon_items_society_id", "reconciliation_items", ["society_id"])
    op.create_index("ix_recon_items_session", "reconciliation_items", ["session_id"])
    op.create_index("ix_recon_items_payment", "reconciliation_items", ["payment_id"])
    op.create_index("ix_recon_items_status", "reconciliation_items", ["society_id", "match_status"])

    # 5. Row-Level Security with explicit USING and WITH CHECK for Phase 6 Tables
    bind = op.get_bind()
    if bind and getattr(bind, "dialect", None) and bind.dialect.name == "postgresql":
        phase6_tables = [
            "payments",
            "receipts",
            "payment_allocations",
            "reconciliation_sessions",
            "reconciliation_items",
        ]
        for table in phase6_tables:
            op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;")
            op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY;")
            op.execute(f"DROP POLICY IF EXISTS tenant_isolation_{table} ON {table};")
            op.execute(
                f"""
                CREATE POLICY tenant_isolation_{table} ON {table}
                FOR ALL
                USING (
                    society_id = NULLIF(current_setting('app.current_society_id', true), '')::uuid
                )
                WITH CHECK (
                    society_id = NULLIF(current_setting('app.current_society_id', true), '')::uuid
                );
                """
            )


def downgrade() -> None:
    # Drop reconciliation tables
    op.drop_table("reconciliation_items")
    op.drop_table("reconciliation_sessions")

    # Revert payment_allocations enhancements
    op.drop_index("ix_payment_allocations_society_status", table_name="payment_allocations")
    op.drop_column("payment_allocations", "reversal_reference")
    op.drop_column("payment_allocations", "reversal_reason")
    op.drop_column("payment_allocations", "reversed_by")
    op.drop_column("payment_allocations", "reversed_at")
    op.drop_column("payment_allocations", "status")

    # Revert receipts enhancements
    op.drop_index("ix_receipts_society_status", table_name="receipts")
    op.drop_column("receipts", "cancellation_reason")
    op.drop_column("receipts", "cancelled_by")
    op.drop_column("receipts", "cancelled_at")
    op.drop_column("receipts", "status")

    # Revert payments enhancements
    op.drop_index("ix_payments_idempotency", table_name="payments")
    op.drop_index("ix_payments_bank_account", table_name="payments")
    op.drop_column("payments", "reversed_by")
    op.drop_column("payments", "reversed_at")
    op.drop_column("payments", "reversal_reason")
    op.drop_column("payments", "reversal_journal_entry_id")
    op.drop_column("payments", "idempotency_key")
    op.drop_column("payments", "bank_account_id")
