"""Phase 16 — Announcements, Communications & Resident Notification Foundation.

Revision ID: 0016_announcements_communications
Revises: 0015_facility_booking_management
Create Date: 2026-10-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0016_announcements_communications"
down_revision: str | None = "0015_facility_booking_management"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Announcements Table
    op.create_table(
        "announcements",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "society_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("societies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("announcement_number", sa.String(50), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("summary", sa.String(500), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("priority", sa.String(20), nullable=False, server_default="NORMAL"),
        sa.Column("status", sa.String(30), nullable=False, server_default="DRAFT"),
        sa.Column(
            "author_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "publisher_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("requires_acknowledgement", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("is_pinned", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version_number", sa.Integer(), nullable=False, server_default="1"),
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
        sa.UniqueConstraint("society_id", "announcement_number", name="uq_announcement_number_society"),
    )
    op.create_index(
        "ix_announcements_society_status",
        "announcements",
        ["society_id", "status"],
    )
    op.create_index(
        "ix_announcements_society_priority",
        "announcements",
        ["society_id", "priority"],
    )
    op.create_index(
        "ix_announcements_published_expires",
        "announcements",
        ["published_at", "expires_at"],
    )

    # 2. Announcement Audiences Table
    op.create_table(
        "announcement_audiences",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "society_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("societies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "announcement_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("announcements.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("audience_type", sa.String(30), nullable=False),
        sa.Column(
            "target_block_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("blocks.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "target_floor_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("floors.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "target_unit_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("units.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "target_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("role_filter", sa.String(30), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_announcement_audiences_society_announcement",
        "announcement_audiences",
        ["society_id", "announcement_id"],
    )

    # 3. Announcement Attachments Table
    op.create_table(
        "announcement_attachments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "society_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("societies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "announcement_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("announcements.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("file_name", sa.String(255), nullable=False),
        sa.Column("file_size", sa.Integer(), nullable=False),
        sa.Column("mime_type", sa.String(100), nullable=False),
        sa.Column("storage_object_key", sa.String(500), nullable=False),
        sa.Column(
            "uploaded_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "uploaded_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_announcement_attachments_society_announcement",
        "announcement_attachments",
        ["society_id", "announcement_id"],
    )

    # 4. Announcement Acknowledgements Table
    op.create_table(
        "announcement_acknowledgements",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "society_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("societies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "announcement_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("announcements.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("version_number", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "acknowledged_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint(
            "society_id", "announcement_id", "user_id", "version_number", name="uq_announcement_ack_version"
        ),
    )
    op.create_index(
        "ix_announcement_acks_society_user",
        "announcement_acknowledgements",
        ["society_id", "user_id"],
    )

    # 5. Announcement Read Receipts Table
    op.create_table(
        "announcement_read_receipts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "society_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("societies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "announcement_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("announcements.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "read_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("society_id", "announcement_id", "user_id", name="uq_announcement_read_user"),
    )
    op.create_index(
        "ix_announcement_reads_society_user",
        "announcement_read_receipts",
        ["society_id", "user_id"],
    )

    # 6. Announcement Schedules Table
    op.create_table(
        "announcement_schedules",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "society_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("societies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "announcement_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("announcements.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("publish_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(30), nullable=False, server_default="PENDING"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_announcement_schedules_society_publish",
        "announcement_schedules",
        ["society_id", "publish_at", "status"],
    )

    # 7. Announcement Status Histories Table
    op.create_table(
        "announcement_status_histories",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "society_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("societies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "announcement_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("announcements.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("old_status", sa.String(50), nullable=False),
        sa.Column("new_status", sa.String(50), nullable=False),
        sa.Column(
            "changed_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("reason", sa.String(500), nullable=True),
        sa.Column(
            "changed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_announcement_status_hist_society_announcement",
        "announcement_status_histories",
        ["society_id", "announcement_id"],
    )

    # 8. Announcement Versions Table
    op.create_table(
        "announcement_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "society_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("societies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "announcement_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("announcements.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("summary", sa.String(500), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("priority", sa.String(20), nullable=False),
        sa.Column(
            "edited_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("edit_reason", sa.String(500), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint(
            "society_id", "announcement_id", "version_number", name="uq_announcement_version_number"
        ),
    )
    op.create_index(
        "ix_announcement_versions_society_announcement",
        "announcement_versions",
        ["society_id", "announcement_id"],
    )

    # Enable & Force RLS on all 8 tables
    tables = [
        "announcements",
        "announcement_audiences",
        "announcement_attachments",
        "announcement_acknowledgements",
        "announcement_read_receipts",
        "announcement_schedules",
        "announcement_status_histories",
        "announcement_versions",
    ]

    for table in tables:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY;")
        op.execute(
            f"CREATE POLICY {table}_tenant_isolation ON {table} "
            f"USING (society_id = NULLIF(current_setting('app.current_society_id', true), '')::uuid);"
        )


def downgrade() -> None:
    tables = [
        "announcement_versions",
        "announcement_status_histories",
        "announcement_schedules",
        "announcement_read_receipts",
        "announcement_acknowledgements",
        "announcement_attachments",
        "announcement_audiences",
        "announcements",
    ]

    for table in tables:
        op.execute(f"DROP POLICY IF EXISTS {table}_tenant_isolation ON {table};")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY;")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;")

    for table in tables:
        op.drop_table(table)
