"""Phase 12 — Staff & Workforce Management Foundation.

Revision ID: 0012_staff_workforce
Revises: 0011_maintenance_work_orders
Create Date: 2026-10-04
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0012_staff_workforce"
down_revision: str | None = "0011_maintenance_work_orders"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Staff Roles Table
    op.create_table(
        "staff_roles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "society_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("societies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("code", sa.String(50), nullable=False),
        sa.Column("description", sa.String(500), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("display_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("society_id", "code", name="uq_staff_role_society_code"),
    )
    op.create_index("ix_staff_role_society_code", "staff_roles", ["society_id", "code"])

    # 2. Staff Teams Table
    op.create_table(
        "staff_teams",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "society_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("societies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("code", sa.String(50), nullable=False),
        sa.Column("description", sa.String(500), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("society_id", "code", name="uq_staff_team_society_code"),
    )
    op.create_index("ix_staff_team_society_code", "staff_teams", ["society_id", "code"])

    # 3. Staff Profiles Table
    op.create_table(
        "staff_profiles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "society_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("societies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("staff_code", sa.String(32), nullable=False),
        sa.Column("first_name", sa.String(100), nullable=False),
        sa.Column("middle_name", sa.String(100), nullable=True),
        sa.Column("last_name", sa.String(100), nullable=False),
        sa.Column("display_name", sa.String(200), nullable=False),
        sa.Column("preferred_name", sa.String(100), nullable=True),
        sa.Column("profile_photo_url", sa.String(500), nullable=True),
        sa.Column("date_of_joining", sa.Date(), nullable=False),
        sa.Column("engagement_type", sa.String(32), server_default="FULL_TIME", nullable=False),
        sa.Column("status", sa.String(32), server_default="ONBOARDING", nullable=False),
        sa.Column(
            "primary_role_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("staff_roles.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("society_id", "staff_code", name="uq_staff_profile_society_code"),
        sa.CheckConstraint(
            "engagement_type IN ('FULL_TIME', 'PART_TIME', 'CONTRACT', 'TEMPORARY', 'VOLUNTEER', 'OTHER')",
            name="ck_staff_profile_engagement_type",
        ),
        sa.CheckConstraint(
            "status IN ('ONBOARDING', 'ACTIVE', 'INACTIVE', 'SUSPENDED', 'OFFBOARDED')",
            name="ck_staff_profile_status",
        ),
    )
    op.create_index("ix_staff_profile_society_status", "staff_profiles", ["society_id", "status"])
    op.create_index("ix_staff_profile_society_user", "staff_profiles", ["society_id", "user_id"])

    # 4. Staff Role Assignments Table
    op.create_table(
        "staff_role_assignments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "society_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("societies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "staff_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("staff_profiles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "role_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("staff_roles.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("is_primary", sa.Boolean(), server_default="false", nullable=False),
        sa.Column(
            "assigned_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reason", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_staff_role_assign_staff", "staff_role_assignments", ["society_id", "staff_id"])

    # 5. Staff Team Memberships Table
    op.create_table(
        "staff_team_memberships",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "society_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("societies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "staff_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("staff_profiles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "team_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("staff_teams.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("is_primary", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("joined_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "assigned_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_staff_team_mem_staff", "staff_team_memberships", ["society_id", "staff_id"])
    op.create_index("ix_staff_team_mem_team", "staff_team_memberships", ["society_id", "team_id"])

    # 6. Staff Contacts Table
    op.create_table(
        "staff_contacts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "society_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("societies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "staff_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("staff_profiles.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("phone", sa.String(32), nullable=False),
        sa.Column("alternate_phone", sa.String(32), nullable=True),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("emergency_contact_name", sa.String(150), nullable=True),
        sa.Column("emergency_contact_relationship", sa.String(50), nullable=True),
        sa.Column("emergency_contact_phone", sa.String(32), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_staff_contact_staff", "staff_contacts", ["society_id", "staff_id"])

    # 7. Staff Documents Table
    op.create_table(
        "staff_documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "society_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("societies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "staff_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("staff_profiles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("document_type", sa.String(50), server_default="IDENTITY", nullable=False),
        sa.Column("storage_key", sa.String(500), nullable=False),
        sa.Column("original_filename", sa.String(255), nullable=False),
        sa.Column("content_type", sa.String(100), nullable=False),
        sa.Column("file_size", sa.Integer(), nullable=False),
        sa.Column("checksum", sa.String(64), nullable=True),
        sa.Column(
            "uploaded_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "document_type IN ('IDENTITY', 'EMPLOYMENT', 'CERTIFICATION', 'TRAINING', 'OTHER')",
            name="ck_staff_document_type",
        ),
    )
    op.create_index("ix_staff_doc_staff", "staff_documents", ["society_id", "staff_id"])

    # 8. Staff Status Histories Table
    op.create_table(
        "staff_status_histories",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "society_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("societies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "staff_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("staff_profiles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("from_status", sa.String(32), nullable=True),
        sa.Column("to_status", sa.String(32), nullable=False),
        sa.Column(
            "changed_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_staff_status_hist_staff", "staff_status_histories", ["society_id", "staff_id"])

    # 9. Staff Assignment Histories Table
    op.create_table(
        "staff_assignment_histories",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "society_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("societies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "staff_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("staff_profiles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "work_order_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("maintenance_work_orders.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "actor_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_staff_assign_hist_staff", "staff_assignment_histories", ["society_id", "staff_id"])
    op.create_index("ix_staff_assign_hist_wo", "staff_assignment_histories", ["society_id", "work_order_id"])

    # Enable & Force PostgreSQL Row Level Security for all 9 tables
    bind = op.get_bind()
    if bind and getattr(bind, "dialect", None) and bind.dialect.name == "postgresql":
        phase12_tables = [
            "staff_roles",
            "staff_teams",
            "staff_profiles",
            "staff_role_assignments",
            "staff_team_memberships",
            "staff_contacts",
            "staff_documents",
            "staff_status_histories",
            "staff_assignment_histories",
        ]
        for table in phase12_tables:
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
    op.drop_table("staff_assignment_histories")
    op.drop_table("staff_status_histories")
    op.drop_table("staff_documents")
    op.drop_table("staff_contacts")
    op.drop_table("staff_team_memberships")
    op.drop_table("staff_role_assignments")
    op.drop_table("staff_profiles")
    op.drop_table("staff_teams")
    op.drop_table("staff_roles")
