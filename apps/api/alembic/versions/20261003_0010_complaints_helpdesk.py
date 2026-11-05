"""Phase 10 — Complaints & Helpdesk Management Foundation.

Revision ID: 0010_complaints_helpdesk
Revises: 0009_visitor_management
Create Date: 2026-10-03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0010_complaints_helpdesk"
down_revision: str | None = "0009_visitor_management"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Complaint Categories Table
    op.create_table(
        "complaint_categories",
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
        sa.Column("icon", sa.String(100), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("display_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("society_id", "code", name="uq_complaint_category_society_code"),
    )
    op.create_index("ix_complaint_category_society_name", "complaint_categories", ["society_id", "name"])

    # 2. Complaint Subcategories Table
    op.create_table(
        "complaint_subcategories",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "society_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("societies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "category_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("complaint_categories.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("code", sa.String(50), nullable=False),
        sa.Column("description", sa.String(500), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("display_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("society_id", "category_id", "code", name="uq_complaint_subcategory_code"),
    )
    op.create_index("ix_complaint_subcategory_cat", "complaint_subcategories", ["category_id"])

    # 3. Complaint SLA Policies Table
    op.create_table(
        "complaint_sla_policies",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "society_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("societies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "category_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("complaint_categories.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("priority", sa.String(20), nullable=False),
        sa.Column("acknowledgement_target_hours", sa.Integer(), server_default="24", nullable=False),
        sa.Column("resolution_target_hours", sa.Integer(), server_default="72", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "priority IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')",
            name="ck_complaint_sla_priority",
        ),
        sa.UniqueConstraint(
            "society_id", "category_id", "priority", name="uq_complaint_sla_society_cat_prio"
        ),
    )

    # 4. Complaints Table
    op.create_table(
        "complaints",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "society_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("societies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("complaint_number", sa.String(32), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column(
            "category_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("complaint_categories.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "subcategory_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("complaint_subcategories.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "raised_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "raised_for_unit_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("units.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("priority", sa.String(20), server_default="MEDIUM", nullable=False),
        sa.Column("source", sa.String(20), server_default="WEB", nullable=False),
        sa.Column("status", sa.String(32), server_default="OPEN", nullable=False),
        sa.Column(
            "sla_policy_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("complaint_sla_policies.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ack_due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reopened_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolution_summary", sa.Text(), nullable=True),
        sa.Column(
            "vehicle_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("vehicles.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "visitor_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("visitors.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("work_order_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("society_id", "complaint_number", name="uq_complaints_society_number"),
        sa.CheckConstraint(
            "priority IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')",
            name="ck_complaints_priority",
        ),
        sa.CheckConstraint(
            "source IN ('WEB', 'MOBILE', 'ADMIN', 'SECURITY', 'VOICE', 'PHOTO', 'OTHER')",
            name="ck_complaints_source",
        ),
        sa.CheckConstraint(
            "status IN ('OPEN', 'ACKNOWLEDGED', 'ASSIGNED', 'IN_PROGRESS', 'WAITING_FOR_RESIDENT', 'RESOLVED', 'REOPENED', 'CLOSED', 'CANCELLED')",
            name="ck_complaints_status",
        ),
    )
    op.create_index("ix_complaints_society_status", "complaints", ["society_id", "status"])
    op.create_index("ix_complaints_society_raised_by", "complaints", ["society_id", "raised_by_user_id"])
    op.create_index("ix_complaints_society_created", "complaints", ["society_id", "created_at"])

    # 5. Complaint Assignments Table
    op.create_table(
        "complaint_assignments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "society_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("societies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "complaint_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("complaints.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "assigned_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("target_type", sa.String(30), server_default="INTERNAL_USER", nullable=False),
        sa.Column(
            "assigned_to_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("assigned_to_role", sa.String(50), nullable=True),
        sa.Column("assigned_to_team", sa.String(100), nullable=True),
        sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("notes", sa.String(500), nullable=True),
        sa.Column("is_current", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "target_type IN ('INTERNAL_USER', 'TEAM', 'FUTURE_STAFF', 'FUTURE_VENDOR')",
            name="ck_complaint_assignment_target_type",
        ),
    )
    op.create_index(
        "ix_complaint_assignment_active",
        "complaint_assignments",
        ["society_id", "complaint_id", "is_current"],
    )

    # 6. Complaint Comments Table
    op.create_table(
        "complaint_comments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "society_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("societies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "complaint_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("complaints.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "author_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("comment_type", sa.String(20), server_default="PUBLIC", nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "comment_type IN ('PUBLIC', 'INTERNAL')",
            name="ck_complaint_comment_type",
        ),
    )
    op.create_index(
        "ix_complaint_comment_complaint", "complaint_comments", ["society_id", "complaint_id", "created_at"]
    )

    # 7. Complaint Attachments Table
    op.create_table(
        "complaint_attachments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "society_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("societies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "complaint_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("complaints.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "uploaded_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("attachment_type", sa.String(20), server_default="PHOTO", nullable=False),
        sa.Column("file_key", sa.String(500), nullable=False),
        sa.Column("original_filename", sa.String(255), nullable=False),
        sa.Column("content_type", sa.String(100), server_default="image/jpeg", nullable=False),
        sa.Column("file_size_bytes", sa.Integer(), nullable=True),
        sa.Column("checksum", sa.String(64), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "attachment_type IN ('PHOTO', 'VIDEO', 'AUDIO', 'DOCUMENT', 'OTHER')",
            name="ck_complaint_attachment_type",
        ),
    )
    op.create_index(
        "ix_complaint_attachment_complaint", "complaint_attachments", ["society_id", "complaint_id"]
    )

    # 8. Complaint Status History Table
    op.create_table(
        "complaint_status_history",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "society_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("societies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "complaint_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("complaints.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "actor_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("from_status", sa.String(32), nullable=True),
        sa.Column("to_status", sa.String(32), nullable=False),
        sa.Column("reason", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_complaint_status_history_complaint",
        "complaint_status_history",
        ["society_id", "complaint_id", "created_at"],
    )

    # 9. Complaint Escalations Table
    op.create_table(
        "complaint_escalations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "society_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("societies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "complaint_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("complaints.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("escalation_level", sa.Integer(), server_default="1", nullable=False),
        sa.Column("escalation_reason", sa.String(500), nullable=False),
        sa.Column(
            "triggered_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "target_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("target_role", sa.String(50), nullable=True),
        sa.Column("status", sa.String(20), server_default="ACTIVE", nullable=False),
        sa.Column("triggered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_complaint_escalation_complaint", "complaint_escalations", ["society_id", "complaint_id", "status"]
    )

    # 10. Complaint Resolutions Table
    op.create_table(
        "complaint_resolutions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "society_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("societies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "complaint_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("complaints.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "resolved_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("resolution_summary", sa.Text(), nullable=False),
        sa.Column("resolution_code", sa.String(50), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    # Enable & Force PostgreSQL Row Level Security for all 10 tables
    bind = op.get_bind()
    if bind and getattr(bind, "dialect", None) and bind.dialect.name == "postgresql":
        phase10_tables = [
            "complaint_categories",
            "complaint_subcategories",
            "complaint_sla_policies",
            "complaints",
            "complaint_assignments",
            "complaint_comments",
            "complaint_attachments",
            "complaint_status_history",
            "complaint_escalations",
            "complaint_resolutions",
        ]
        for table in phase10_tables:
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
    op.drop_table("complaint_resolutions")
    op.drop_table("complaint_escalations")
    op.drop_table("complaint_status_history")
    op.drop_table("complaint_attachments")
    op.drop_table("complaint_comments")
    op.drop_table("complaint_assignments")
    op.drop_table("complaints")
    op.drop_table("complaint_sla_policies")
    op.drop_table("complaint_subcategories")
    op.drop_table("complaint_categories")
