"""Phase 11 — Maintenance & Work Order Management Foundation.

Revision ID: 0011_maintenance_work_orders
Revises: 0010_complaints_helpdesk
Create Date: 2026-10-04
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0011_maintenance_work_orders"
down_revision: str | None = "0010_complaints_helpdesk"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Maintenance Categories Table
    op.create_table(
        "maintenance_categories",
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
        sa.UniqueConstraint("society_id", "code", name="uq_maintenance_category_society_code"),
    )
    op.create_index("ix_maintenance_category_society_name", "maintenance_categories", ["society_id", "name"])

    # 2. Maintenance Subcategories Table
    op.create_table(
        "maintenance_subcategories",
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
            sa.ForeignKey("maintenance_categories.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("code", sa.String(50), nullable=False),
        sa.Column("description", sa.String(500), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("display_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("society_id", "category_id", "code", name="uq_maintenance_subcategory_code"),
    )
    op.create_index("ix_maintenance_subcategory_cat", "maintenance_subcategories", ["category_id"])

    # 3. Maintenance Priority Policies Table
    op.create_table(
        "maintenance_priority_policies",
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
            sa.ForeignKey("maintenance_categories.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("priority", sa.String(20), nullable=False),
        sa.Column("target_resolution_hours", sa.Integer(), server_default="72", nullable=False),
        sa.Column("escalation_threshold_hours", sa.Integer(), server_default="48", nullable=False),
        sa.Column("requires_approval", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "priority IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')",
            name="ck_maintenance_priority_policy_priority",
        ),
        sa.UniqueConstraint(
            "society_id", "category_id", "priority", name="uq_maintenance_priority_society_cat_prio"
        ),
    )

    # 4. Maintenance Work Orders Table
    op.create_table(
        "maintenance_work_orders",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "society_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("societies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("work_order_number", sa.String(32), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column(
            "category_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("maintenance_categories.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "subcategory_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("maintenance_subcategories.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("source", sa.String(32), server_default="ADMIN", nullable=False),
        sa.Column(
            "complaint_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("complaints.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "unit_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("units.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "block_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("blocks.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("priority", sa.String(20), server_default="MEDIUM", nullable=False),
        sa.Column("status", sa.String(32), server_default="OPEN", nullable=False),
        sa.Column(
            "requested_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "requested_for_unit_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("units.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("current_assignment_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("estimated_start_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("scheduled_start_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("scheduled_end_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("actual_start_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("actual_end_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.Column(
            "created_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "society_id", "work_order_number", name="uq_maintenance_work_orders_society_number"
        ),
        sa.CheckConstraint(
            "priority IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')",
            name="ck_maintenance_work_orders_priority",
        ),
        sa.CheckConstraint(
            "source IN ('COMPLAINT', 'SERVICE_REQUEST', 'ADMIN', 'INSPECTION', 'EMERGENCY', 'PREVENTIVE')",
            name="ck_maintenance_work_orders_source",
        ),
        sa.CheckConstraint(
            "status IN ('DRAFT', 'OPEN', 'ASSIGNED', 'SCHEDULED', 'IN_PROGRESS', 'ON_HOLD', 'WAITING_FOR_PARTS', 'WAITING_FOR_RESIDENT', 'COMPLETED', 'VERIFIED', 'CLOSED', 'REOPENED', 'CANCELLED')",
            name="ck_maintenance_work_orders_status",
        ),
    )
    op.create_index("ix_maintenance_wo_society_status", "maintenance_work_orders", ["society_id", "status"])
    op.create_index(
        "ix_maintenance_wo_society_priority", "maintenance_work_orders", ["society_id", "priority"]
    )
    op.create_index("ix_maintenance_wo_due_at", "maintenance_work_orders", ["society_id", "due_at"])
    op.create_index("ix_maintenance_wo_complaint", "maintenance_work_orders", ["society_id", "complaint_id"])

    # 5. Work Order Assignments Table
    op.create_table(
        "work_order_assignments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "society_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("societies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "work_order_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("maintenance_work_orders.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("assignment_type", sa.String(32), server_default="INTERNAL_USER", nullable=False),
        sa.Column(
            "target_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("target_team_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "assigned_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("unassigned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reason", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "assignment_type IN ('INTERNAL_USER', 'TEAM', 'STAFF', 'VENDOR')",
            name="ck_work_order_assignment_type",
        ),
    )
    op.create_index("ix_wo_assignment_wo_status", "work_order_assignments", ["society_id", "work_order_id"])

    # 6. Work Order Comments Table
    op.create_table(
        "work_order_comments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "society_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("societies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "work_order_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("maintenance_work_orders.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("comment_text", sa.Text(), nullable=False),
        sa.Column("comment_type", sa.String(20), server_default="PUBLIC", nullable=False),
        sa.Column("is_internal", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "comment_type IN ('PUBLIC', 'INTERNAL')",
            name="ck_work_order_comment_type",
        ),
    )
    op.create_index("ix_wo_comment_wo", "work_order_comments", ["society_id", "work_order_id"])

    # 7. Work Order Attachments Table
    op.create_table(
        "work_order_attachments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "society_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("societies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "work_order_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("maintenance_work_orders.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "uploaded_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("file_name", sa.String(255), nullable=False),
        sa.Column("file_type", sa.String(20), server_default="PHOTO", nullable=False),
        sa.Column("file_size", sa.Integer(), nullable=False),
        sa.Column("storage_key", sa.String(500), nullable=False),
        sa.Column("mime_type", sa.String(100), nullable=False),
        sa.Column("is_archived", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "file_type IN ('PHOTO', 'VIDEO', 'AUDIO', 'DOCUMENT', 'OTHER')",
            name="ck_work_order_attachment_file_type",
        ),
    )
    op.create_index("ix_wo_attachment_wo", "work_order_attachments", ["society_id", "work_order_id"])

    # 8. Work Order Status Histories Table
    op.create_table(
        "work_order_status_histories",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "society_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("societies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "work_order_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("maintenance_work_orders.id", ondelete="CASCADE"),
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
    op.create_index("ix_wo_status_history_wo", "work_order_status_histories", ["society_id", "work_order_id"])

    # 9. Work Order Escalations Table
    op.create_table(
        "work_order_escalations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "society_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("societies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "work_order_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("maintenance_work_orders.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("escalation_level", sa.Integer(), server_default="1", nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("status", sa.String(32), server_default="PENDING", nullable=False),
        sa.Column("triggered_at", sa.DateTime(timezone=True), nullable=False),
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
        sa.Column("target_team_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_wo_escalation_wo", "work_order_escalations", ["society_id", "work_order_id"])

    # 10. Work Order Resolutions Table
    op.create_table(
        "work_order_resolutions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "society_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("societies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "work_order_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("maintenance_work_orders.id", ondelete="CASCADE"),
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
        sa.Column("resolution_evidence", sa.String(500), nullable=True),
        sa.Column("verification_required", sa.Boolean(), server_default="true", nullable=False),
        sa.Column(
            "verified_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("verification_comment", sa.Text(), nullable=True),
        sa.Column("status", sa.String(32), server_default="PENDING_VERIFICATION", nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_wo_resolution_wo", "work_order_resolutions", ["society_id", "work_order_id"])

    # 11. Work Order Material Usages Table
    op.create_table(
        "work_order_material_usages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "society_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("societies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "work_order_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("maintenance_work_orders.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("material_name", sa.String(150), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("quantity", sa.Numeric(12, 2), server_default="1.00", nullable=False),
        sa.Column("unit", sa.String(50), server_default="units", nullable=False),
        sa.Column("estimated_unit_cost", sa.Numeric(12, 2), nullable=True),
        sa.Column("actual_unit_cost", sa.Numeric(12, 2), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_wo_material_wo", "work_order_material_usages", ["society_id", "work_order_id"])

    # 12. Work Order Activities Table
    op.create_table(
        "work_order_activities",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "society_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("societies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "work_order_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("maintenance_work_orders.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column(
            "actor_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("metadata_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_wo_activity_wo", "work_order_activities", ["society_id", "work_order_id"])

    # Enable & Force PostgreSQL Row Level Security for all 12 tables
    bind = op.get_bind()
    if bind and getattr(bind, "dialect", None) and bind.dialect.name == "postgresql":
        phase11_tables = [
            "maintenance_categories",
            "maintenance_subcategories",
            "maintenance_priority_policies",
            "maintenance_work_orders",
            "work_order_assignments",
            "work_order_comments",
            "work_order_attachments",
            "work_order_status_histories",
            "work_order_escalations",
            "work_order_resolutions",
            "work_order_material_usages",
            "work_order_activities",
        ]
        for table in phase11_tables:
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
    op.drop_table("work_order_activities")
    op.drop_table("work_order_material_usages")
    op.drop_table("work_order_resolutions")
    op.drop_table("work_order_escalations")
    op.drop_table("work_order_status_histories")
    op.drop_table("work_order_attachments")
    op.drop_table("work_order_comments")
    op.drop_table("work_order_assignments")
    op.drop_table("maintenance_work_orders")
    op.drop_table("maintenance_priority_policies")
    op.drop_table("maintenance_subcategories")
    op.drop_table("maintenance_categories")
