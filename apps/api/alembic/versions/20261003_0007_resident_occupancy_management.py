"""Resident, Owner, Tenant & Occupancy Management Migration.

Revision ID: 0007_resident_occupancy
Revises: 0006_payments_reconciliation
Create Date: 2026-10-03 01:00:00.000000

Establishes:
1. Enhances resident_profiles table: alternate_phone, preferred_language, status, notes.
2. unit_ownerships table (single & co-owners with percentage validation and history preservation).
3. resident_family_members table (family relationships with configurable access scopes).
4. resident_delegates table (explicit, scoped, revocable delegation).
5. PostgreSQL Row-Level Security (RLS) policies with explicit USING and WITH CHECK + FORCE ROW LEVEL SECURITY.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007_resident_occupancy"
down_revision: str | None = "0006_payments_reconciliation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Enhance resident_profiles table
    op.add_column("resident_profiles", sa.Column("alternate_phone", sa.String(32), nullable=True))
    op.add_column(
        "resident_profiles",
        sa.Column("preferred_language", sa.String(10), server_default="en", nullable=False),
    )
    op.add_column(
        "resident_profiles",
        sa.Column("status", sa.String(32), server_default="ACTIVE", nullable=False),
    )
    op.add_column("resident_profiles", sa.Column("notes", sa.String(500), nullable=True))
    op.create_index("ix_resident_profiles_status", "resident_profiles", ["status"])

    # 2. Unit Ownerships Table (Single & Multi-Owner Joint Ownership)
    op.create_table(
        "unit_ownerships",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "society_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("societies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "unit_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("units.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "ownership_percentage",
            sa.Numeric(5, 2),
            server_default="100.00",
            nullable=False,
        ),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("is_primary", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("status", sa.String(32), server_default="ACTIVE", nullable=False),
        sa.Column("notes", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "ownership_percentage > 0 AND ownership_percentage <= 100",
            name="ck_unit_ownership_percentage",
        ),
    )
    op.create_index("ix_unit_ownerships_society_id", "unit_ownerships", ["society_id"])
    op.create_index("ix_unit_ownerships_unit_id", "unit_ownerships", ["unit_id"])
    op.create_index("ix_unit_ownerships_user_id", "unit_ownerships", ["user_id"])
    op.create_index("ix_unit_ownerships_status", "unit_ownerships", ["status"])

    # 3. Resident Family Members Table
    op.create_table(
        "resident_family_members",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "society_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("societies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "unit_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("units.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "primary_resident_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("name", sa.String(150), nullable=False),
        sa.Column("relationship", sa.String(50), nullable=False),
        sa.Column("phone", sa.String(32), nullable=True),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column(
            "access_scope",
            sa.JSON().with_variant(postgresql.JSONB, "postgresql"),
            nullable=False,
        ),
        sa.Column("status", sa.String(32), server_default="ACTIVE", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_family_members_society_id", "resident_family_members", ["society_id"])
    op.create_index("ix_family_members_unit_id", "resident_family_members", ["unit_id"])
    op.create_index(
        "ix_family_members_primary_user_id",
        "resident_family_members",
        ["primary_resident_user_id"],
    )
    op.create_index("ix_family_members_user_id", "resident_family_members", ["user_id"])
    op.create_index("ix_family_members_status", "resident_family_members", ["status"])

    # 4. Resident Delegates Table
    op.create_table(
        "resident_delegates",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "society_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("societies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "unit_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("units.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "delegator_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "delegate_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "permissions",
            sa.JSON().with_variant(postgresql.JSONB, "postgresql"),
            nullable=False,
        ),
        sa.Column("valid_from", sa.Date(), nullable=False),
        sa.Column("valid_to", sa.Date(), nullable=True),
        sa.Column("status", sa.String(32), server_default="ACTIVE", nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "revoked_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("revocation_reason", sa.String(255), nullable=True),
        sa.Column("notes", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_resident_delegates_society_id", "resident_delegates", ["society_id"])
    op.create_index("ix_resident_delegates_unit_id", "resident_delegates", ["unit_id"])
    op.create_index(
        "ix_resident_delegates_delegator_id",
        "resident_delegates",
        ["delegator_user_id"],
    )
    op.create_index(
        "ix_resident_delegates_delegate_id",
        "resident_delegates",
        ["delegate_user_id"],
    )
    op.create_index("ix_resident_delegates_status", "resident_delegates", ["status"])

    # 5. PostgreSQL Row-Level Security with explicit USING and WITH CHECK
    bind = op.get_bind()
    if bind and getattr(bind, "dialect", None) and bind.dialect.name == "postgresql":
        phase7_tables = [
            "resident_profiles",
            "unit_occupancies",
            "unit_ownerships",
            "resident_family_members",
            "resident_delegates",
        ]
        for table in phase7_tables:
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
    # Drop new Phase 7 tables
    op.drop_table("resident_delegates")
    op.drop_table("resident_family_members")
    op.drop_table("unit_ownerships")

    # Revert resident_profiles enhancements
    op.drop_index("ix_resident_profiles_status", table_name="resident_profiles")
    op.drop_column("resident_profiles", "notes")
    op.drop_column("resident_profiles", "status")
    op.drop_column("resident_profiles", "preferred_language")
    op.drop_column("resident_profiles", "alternate_phone")
