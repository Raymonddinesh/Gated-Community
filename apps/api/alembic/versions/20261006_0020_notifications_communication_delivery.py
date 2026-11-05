"""Phase 20 — Notifications & Communication Delivery Foundation.

Revision ID: 0020_notifications_communication_delivery
Revises: 0019_emergency_incident_management
Create Date: 2026-10-06
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0020_notifications_communication_delivery"
down_revision: str | None = "0019_emergency_incident_management"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Notifications Table
    op.create_table(
        "notifications",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "society_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("societies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("category", sa.String(50), nullable=False),
        sa.Column("priority", sa.String(20), nullable=False, server_default="NORMAL"),
        sa.Column("source_domain", sa.String(50), nullable=False),
        sa.Column("source_event_id", sa.String(100), nullable=True),
        sa.Column("idempotency_key", sa.String(128), nullable=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("payload", sa.Text(), nullable=True),
        sa.Column(
            "sender_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("status", sa.String(30), nullable=False, server_default="CREATED"),
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
        sa.UniqueConstraint("society_id", "idempotency_key", name="uq_notifications_society_idempotency"),
    )
    op.create_index("ix_notifications_society_category", "notifications", ["society_id", "category"])
    op.create_index("ix_notifications_society_status", "notifications", ["society_id", "status"])

    # 2. Notification Recipients Table
    op.create_table(
        "notification_recipients",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "society_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("societies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "notification_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("notifications.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("recipient_type", sa.String(30), nullable=False, server_default="RESIDENT"),
        sa.Column("is_read", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.UniqueConstraint("notification_id", "user_id", name="uq_notification_recipients_notif_user"),
    )
    op.create_index("ix_notification_recipients_user_read", "notification_recipients", ["society_id", "user_id", "is_read"])
    op.create_index("ix_notification_recipients_notification", "notification_recipients", ["society_id", "notification_id"])

    # 3. Notification Templates Table
    op.create_table(
        "notification_templates",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "society_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("societies.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("code", sa.String(100), nullable=False),
        sa.Column("name", sa.String(150), nullable=False),
        sa.Column("category", sa.String(50), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("allowlisted_variables", sa.Text(), nullable=True),
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
        sa.UniqueConstraint("society_id", "code", name="uq_notification_templates_society_code"),
    )
    op.create_index("ix_notification_templates_code", "notification_templates", ["code"])

    # 4. Notification Template Versions Table
    op.create_table(
        "notification_template_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "society_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("societies.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "template_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("notification_templates.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("channel", sa.String(20), nullable=False),
        sa.Column("locale", sa.String(10), nullable=False, server_default="en"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("subject_template", sa.String(255), nullable=True),
        sa.Column("body_template", sa.Text(), nullable=False),
        sa.Column("is_published", sa.Boolean(), nullable=False, server_default="true"),
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
        sa.UniqueConstraint("template_id", "channel", "locale", "version", name="uq_notif_template_version_key"),
    )
    op.create_index("ix_notification_template_versions_lookup", "notification_template_versions", ["template_id", "channel", "locale", "is_published"])

    # 5. Notification Preferences Table
    op.create_table(
        "notification_preferences",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "society_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("societies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("category", sa.String(50), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("quiet_hours_enabled", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("quiet_hours_start", sa.String(10), nullable=True),
        sa.Column("quiet_hours_end", sa.String(10), nullable=True),
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
        sa.UniqueConstraint("society_id", "user_id", "category", name="uq_notification_preference_user_cat"),
    )

    # 6. Notification Channel Preferences Table
    op.create_table(
        "notification_channel_preferences",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "society_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("societies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("category", sa.String(50), nullable=False),
        sa.Column("channel", sa.String(20), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default="true"),
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
        sa.UniqueConstraint("society_id", "user_id", "category", "channel", name="uq_notif_channel_pref_key"),
    )

    # 7. Notification Deliveries Table
    op.create_table(
        "notification_deliveries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "society_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("societies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "notification_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("notifications.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "recipient_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("notification_recipients.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("channel", sa.String(20), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="QUEUED"),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
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
        sa.UniqueConstraint("recipient_id", "channel", name="uq_notification_delivery_recipient_channel"),
    )
    op.create_index("ix_notification_deliveries_status", "notification_deliveries", ["society_id", "status"])
    op.create_index("ix_notification_deliveries_recipient", "notification_deliveries", ["society_id", "recipient_id"])

    # 8. Notification Delivery Attempts Table
    op.create_table(
        "notification_delivery_attempts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "society_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("societies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "delivery_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("notification_deliveries.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("provider_name", sa.String(50), nullable=False),
        sa.Column("provider_request_id", sa.String(100), nullable=True),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("response_code", sa.String(50), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_notif_delivery_attempts_delivery", "notification_delivery_attempts", ["society_id", "delivery_id"])

    # 9. Notification Batches Table
    op.create_table(
        "notification_batches",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "society_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("societies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "notification_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("notifications.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("batch_index", sa.Integer(), nullable=False),
        sa.Column("total_batches", sa.Integer(), nullable=False),
        sa.Column("recipient_count", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="QUEUED"),
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
        sa.UniqueConstraint("notification_id", "batch_index", name="uq_notif_batch_index"),
    )

    # 10. User Device Tokens Table
    op.create_table(
        "user_device_tokens",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "society_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("societies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("device_token", sa.String(255), nullable=False),
        sa.Column("platform", sa.String(20), nullable=False, server_default="ANDROID"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.UniqueConstraint("society_id", "user_id", "device_token", name="uq_user_device_token"),
    )
    op.create_index("ix_user_device_tokens_user", "user_device_tokens", ["society_id", "user_id"])

    # Enable & Force RLS on all 10 tables
    strict_tables = [
        "notifications",
        "notification_recipients",
        "notification_preferences",
        "notification_channel_preferences",
        "notification_deliveries",
        "notification_delivery_attempts",
        "notification_batches",
        "user_device_tokens",
    ]

    for table in strict_tables:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY;")
        op.execute(
            f"CREATE POLICY {table}_tenant_isolation ON {table} "
            f"USING (society_id = NULLIF(current_setting('app.current_society_id', true), '')::uuid);"
        )

    # Global/Society shared tables (templates, template versions)
    shared_tables = ["notification_templates", "notification_template_versions"]
    for table in shared_tables:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY;")
        op.execute(
            f"CREATE POLICY {table}_tenant_isolation ON {table} "
            f"USING (society_id IS NULL OR society_id = NULLIF(current_setting('app.current_society_id', true), '')::uuid);"
        )


def downgrade() -> None:
    all_tables = [
        "user_device_tokens",
        "notification_batches",
        "notification_delivery_attempts",
        "notification_deliveries",
        "notification_channel_preferences",
        "notification_preferences",
        "notification_template_versions",
        "notification_templates",
        "notification_recipients",
        "notifications",
    ]

    for table in all_tables:
        op.execute(f"DROP POLICY IF EXISTS {table}_tenant_isolation ON {table};")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY;")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;")

    for table in all_tables:
        op.drop_table(table)
