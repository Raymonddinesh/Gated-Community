"""Phase 21E.4C — SaaS Credit Note Schema Enhancements.

Revision ID: 0023_saas_credit_notes
Revises: 0022_saas_platform_billing
Create Date: 2026-11-02
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0023_saas_credit_notes"
down_revision: str | None = "0022_saas_platform_billing"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # =========================================================================
    # 1. Update platform_credit_notes constraints & nullability for DRAFT support
    # =========================================================================
    op.alter_column(
        "platform_credit_notes",
        "credit_note_number",
        existing_type=sa.String(50),
        nullable=True,
    )
    op.alter_column(
        "platform_credit_notes",
        "issued_at",
        existing_type=sa.DateTime(timezone=True),
        nullable=True,
    )

    op.drop_constraint("ck_platform_credit_notes_status", "platform_credit_notes", type_="check")
    op.create_check_constraint(
        "ck_platform_credit_notes_status",
        "platform_credit_notes",
        "status IN ('DRAFT', 'ISSUED', 'VOID')",
    )

    # =========================================================================
    # 2. Create Global Table: platform_credit_note_sequences
    # =========================================================================
    op.create_table(
        "platform_credit_note_sequences",
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
            name="ck_platform_credit_note_sequences_non_negative",
        ),
    )

    # Backfill existing sequence state if platform_credit_notes contains numbered records
    op.execute(
        """
        INSERT INTO platform_credit_note_sequences (fiscal_year, current_sequence, updated_at)
        SELECT
            substring(credit_note_number from 'SS-CN-([0-9]{4})-') as fy,
            MAX(CAST(substring(credit_note_number from 'SS-CN-[0-9]{4}-([0-9]+)') AS integer)) as max_seq,
            now()
        FROM platform_credit_notes
        WHERE credit_note_number ~ '^SS-CN-[0-9]{4}-[0-9]+$'
        GROUP BY fy
        ON CONFLICT (fiscal_year) DO UPDATE
        SET current_sequence = GREATEST(platform_credit_note_sequences.current_sequence, EXCLUDED.current_sequence);
        """
    )

    # =========================================================================
    # 3. Create Tenant Table: platform_credit_note_items
    # =========================================================================
    op.create_table(
        "platform_credit_note_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "credit_note_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("platform_credit_notes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "society_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("societies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "invoice_item_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("platform_invoice_items.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("item_index", sa.Integer(), nullable=False),
        sa.Column("description", sa.String(255), nullable=False),
        sa.Column("sac_code", sa.String(20), nullable=False, server_default="998313"),
        sa.Column("quantity", sa.Numeric(12, 4), nullable=False, server_default="1.0000"),
        sa.Column("unit_price", sa.Numeric(12, 2), nullable=False),
        sa.Column("taxable_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("tax_rate", sa.Numeric(5, 2), nullable=False, server_default="18.00"),
        sa.Column("tax_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("total_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint(
            "credit_note_id", "item_index", name="uq_platform_credit_note_items_index"
        ),
        sa.CheckConstraint(
            "taxable_amount > 0",
            name="ck_platform_credit_note_items_taxable_positive",
        ),
        sa.CheckConstraint(
            "total_amount > 0",
            name="ck_platform_credit_note_items_total_positive",
        ),
    )
    op.create_index(
        "ix_platform_credit_note_items_credit_note",
        "platform_credit_note_items",
        ["credit_note_id"],
    )
    op.create_index(
        "ix_platform_credit_note_items_society",
        "platform_credit_note_items",
        ["society_id"],
    )
    op.create_index(
        "ix_platform_credit_note_items_invoice_item",
        "platform_credit_note_items",
        ["invoice_item_id"],
    )

    # =========================================================================
    # 4. Enable & Force Row-Level Security on platform_credit_note_items
    # =========================================================================
    op.execute("ALTER TABLE platform_credit_note_items ENABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE platform_credit_note_items FORCE ROW LEVEL SECURITY;")
    op.execute(
        "CREATE POLICY platform_credit_note_items_tenant_isolation ON platform_credit_note_items "
        "USING (society_id = NULLIF(current_setting('app.current_society_id', true), '')::uuid);"
    )


def downgrade() -> None:
    # 1. Drop RLS and table platform_credit_note_items
    op.execute(
        "DROP POLICY IF EXISTS platform_credit_note_items_tenant_isolation ON platform_credit_note_items;"
    )
    op.execute("ALTER TABLE platform_credit_note_items NO FORCE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE platform_credit_note_items DISABLE ROW LEVEL SECURITY;")
    op.drop_table("platform_credit_note_items")

    # 2. Drop table platform_credit_note_sequences
    op.drop_table("platform_credit_note_sequences")

    # 3. Clean up un-issued DRAFT records introduced in 0023 (schema 0022 requires NOT NULL credit_note_number and status in ISSUED/VOID)
    op.execute("DELETE FROM platform_credit_notes WHERE status = 'DRAFT';")

    # 4. Revert platform_credit_notes constraints & nullability
    op.drop_constraint("ck_platform_credit_notes_status", "platform_credit_notes", type_="check")
    op.create_check_constraint(
        "ck_platform_credit_notes_status",
        "platform_credit_notes",
        "status IN ('ISSUED', 'VOID')",
    )
    op.alter_column(
        "platform_credit_notes",
        "issued_at",
        existing_type=sa.DateTime(timezone=True),
        nullable=False,
    )
    op.alter_column(
        "platform_credit_notes",
        "credit_note_number",
        existing_type=sa.String(50),
        nullable=False,
    )
