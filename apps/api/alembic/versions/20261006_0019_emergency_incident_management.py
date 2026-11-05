"""Phase 19 — Emergency & Incident Management Foundation.

Revision ID: 0019_emergency_incident_management
Revises: 0018_committee_meetings_resolutions_governance
Create Date: 2026-10-06
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0019_emergency_incident_management"
down_revision: str | None = "0018_committee_meetings_resolutions_governance"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Incident Categories Table
    op.create_table(
        "incident_categories",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "society_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("societies.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("code", sa.String(50), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("default_severity", sa.String(20), nullable=False, server_default="MEDIUM"),
        sa.Column("default_sla_minutes", sa.Integer(), nullable=True, server_default="60"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
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
        "ix_incident_categories_society_code",
        "incident_categories",
        ["society_id", "code"],
    )

    # 2. Incidents Table
    op.create_table(
        "incidents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "society_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("societies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("incident_number", sa.String(50), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column(
            "category_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("incident_categories.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("severity", sa.String(20), nullable=False, server_default="MEDIUM"),
        sa.Column("status", sa.String(30), nullable=False, server_default="REPORTED"),
        sa.Column(
            "reported_by_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("reporter_type", sa.String(30), nullable=False, server_default="RESIDENT"),
        sa.Column("reporter_contact", sa.String(100), nullable=True),
        sa.Column(
            "block_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("blocks.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "floor_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("floors.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "unit_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("units.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "facility_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("facilities.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "facility_area_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("facility_areas.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("location_details", sa.Text(), nullable=True),
        sa.Column("latitude", sa.Float(), nullable=True),
        sa.Column("longitude", sa.Float(), nullable=True),
        sa.Column("voice_note_url", sa.String(500), nullable=True),
        sa.Column("voice_note_duration_seconds", sa.Integer(), nullable=True),
        sa.Column("is_hazard_contained", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("hazard_contained_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("requires_governance_review", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("requires_work_order", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("override_applied", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("override_reason", sa.Text(), nullable=True),
        sa.Column(
            "overridden_by_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("overridden_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.UniqueConstraint("society_id", "incident_number", name="uq_incidents_society_number"),
    )
    op.create_index("ix_incidents_society_status", "incidents", ["society_id", "status"])
    op.create_index("ix_incidents_society_severity", "incidents", ["society_id", "severity"])
    op.create_index("ix_incidents_society_created", "incidents", ["society_id", "created_at"])

    # 3. Incident Assignments Table
    op.create_table(
        "incident_assignments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "society_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("societies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "incident_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("incidents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("responder_type", sa.String(30), nullable=False),
        sa.Column(
            "assigned_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "assigned_staff_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("staff_profiles.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "assigned_vendor_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("vendor_profiles.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("assigned_role", sa.String(50), nullable=True),
        sa.Column("assignment_notes", sa.Text(), nullable=True),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column(
            "assigned_by_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "assigned_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("unassigned_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_incident_assignments_society_incident", "incident_assignments", ["society_id", "incident_id"]
    )

    # 4. Incident Timelines Table
    op.create_table(
        "incident_timelines",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "society_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("societies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "incident_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("incidents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "actor_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("actor_role", sa.String(50), nullable=False),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column("summary", sa.String(255), nullable=False),
        sa.Column("details", sa.Text(), nullable=True),
        sa.Column("is_internal_only", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_incident_timelines_society_incident", "incident_timelines", ["society_id", "incident_id"]
    )

    # 5. Incident Actions Table
    op.create_table(
        "incident_actions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "society_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("societies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "incident_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("incidents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(30), nullable=False, server_default="PENDING"),
        sa.Column("priority", sa.String(20), nullable=False, server_default="MEDIUM"),
        sa.Column(
            "assigned_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "completed_by_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_by_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
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
    )
    op.create_index("ix_incident_actions_society_incident", "incident_actions", ["society_id", "incident_id"])

    # 6. Incident Escalations Table
    op.create_table(
        "incident_escalations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "society_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("societies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "incident_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("incidents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("escalation_level", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "triggered_by_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("target_role", sa.String(50), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("sla_minutes_at_escalation", sa.Integer(), nullable=True),
        sa.Column(
            "escalated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_incident_escalations_society_incident", "incident_escalations", ["society_id", "incident_id"]
    )

    # 7. Incident Attachments Table
    op.create_table(
        "incident_attachments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "society_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("societies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "incident_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("incidents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("file_name", sa.String(255), nullable=False),
        sa.Column("file_type", sa.String(50), nullable=False, server_default="DOCUMENT"),
        sa.Column("file_size_bytes", sa.Integer(), nullable=False),
        sa.Column("storage_path", sa.String(500), nullable=False),
        sa.Column("mime_type", sa.String(100), nullable=False),
        sa.Column("duration_seconds", sa.Integer(), nullable=True),
        sa.Column(
            "uploaded_by_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_incident_attachments_society_incident", "incident_attachments", ["society_id", "incident_id"]
    )

    # 8. Emergency Contacts Table
    op.create_table(
        "emergency_contacts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "society_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("societies.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("contact_type", sa.String(30), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("phone_number", sa.String(30), nullable=False),
        sa.Column("alt_phone_number", sa.String(30), nullable=True),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("address", sa.Text(), nullable=True),
        sa.Column("is_platform_default", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("notes", sa.Text(), nullable=True),
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
        "ix_emergency_contacts_society_type", "emergency_contacts", ["society_id", "contact_type"]
    )

    # 9. Incident Status Histories Table
    op.create_table(
        "incident_status_histories",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "society_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("societies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "incident_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("incidents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("from_status", sa.String(30), nullable=True),
        sa.Column("to_status", sa.String(30), nullable=False),
        sa.Column(
            "changed_by_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_incident_status_histories_society_incident",
        "incident_status_histories",
        ["society_id", "incident_id"],
    )

    # 10. Incident Acknowledgements Table
    op.create_table(
        "incident_acknowledgements",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "society_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("societies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "incident_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("incidents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "acknowledged_by_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("responder_role", sa.String(50), nullable=False),
        sa.Column(
            "acknowledged_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("notes", sa.Text(), nullable=True),
    )
    op.create_index(
        "ix_incident_acknowledgements_society_incident",
        "incident_acknowledgements",
        ["society_id", "incident_id"],
    )

    # Enable & Force RLS on all 10 tables
    strict_tables = [
        "incidents",
        "incident_assignments",
        "incident_timelines",
        "incident_actions",
        "incident_escalations",
        "incident_attachments",
        "incident_status_histories",
        "incident_acknowledgements",
    ]

    for table in strict_tables:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY;")
        op.execute(
            f"CREATE POLICY {table}_tenant_isolation ON {table} "
            f"USING (society_id = NULLIF(current_setting('app.current_society_id', true), '')::uuid);"
        )

    # Global/Society shared tables (categories, emergency contacts)
    shared_tables = ["incident_categories", "emergency_contacts"]
    for table in shared_tables:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY;")
        op.execute(
            f"CREATE POLICY {table}_tenant_isolation ON {table} "
            f"USING (society_id IS NULL OR society_id = NULLIF(current_setting('app.current_society_id', true), '')::uuid);"
        )


def downgrade() -> None:
    all_tables = [
        "incident_acknowledgements",
        "incident_status_histories",
        "emergency_contacts",
        "incident_attachments",
        "incident_escalations",
        "incident_actions",
        "incident_timelines",
        "incident_assignments",
        "incidents",
        "incident_categories",
    ]

    for table in all_tables:
        op.execute(f"DROP POLICY IF EXISTS {table}_tenant_isolation ON {table};")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY;")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;")

    for table in all_tables:
        op.drop_table(table)
