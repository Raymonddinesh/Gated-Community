"""Phase 15 — Facility Booking & Common Area Reservation Foundation.

Revision ID: 0015_facility_booking_management
Revises: 0014_facility_asset_management
Create Date: 2026-10-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0015_facility_booking_management"
down_revision: str | None = "0014_facility_asset_management"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Facility Booking Configs Table
    op.create_table(
        "facility_booking_configs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "society_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("societies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "facility_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("facilities.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("is_bookable", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("requires_approval", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("max_capacity", sa.Integer(), nullable=True),
        sa.Column("min_duration_minutes", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("max_duration_minutes", sa.Integer(), nullable=False, server_default="480"),
        sa.Column("advance_booking_days", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("min_cancellation_notice_hours", sa.Integer(), nullable=False, server_default="24"),
        sa.Column("buffer_before_minutes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("buffer_after_minutes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("allow_recurring", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("allow_delegate_booking", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("admin_override_enabled", sa.Boolean(), nullable=False, server_default="true"),
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
        sa.UniqueConstraint("society_id", "facility_id", name="uq_facility_booking_config_facility"),
    )
    op.create_index(
        "ix_facility_booking_config_society",
        "facility_booking_configs",
        ["society_id", "facility_id"],
    )

    # 2. Facility Availability Windows Table
    op.create_table(
        "facility_availability_windows",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "society_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("societies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "facility_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("facilities.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("day_of_week", sa.Integer(), nullable=False),
        sa.Column("start_time", sa.String(10), nullable=False),
        sa.Column("end_time", sa.String(10), nullable=False),
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
        "ix_facility_avail_society_facility",
        "facility_availability_windows",
        ["society_id", "facility_id", "day_of_week"],
    )

    # 3. Facility Blackout Periods Table
    op.create_table(
        "facility_blackout_periods",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "society_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("societies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "facility_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("facilities.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reason", sa.String(500), nullable=True),
        sa.Column("status", sa.String(50), nullable=False, server_default="ACTIVE"),
        sa.Column(
            "created_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
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
    op.create_index(
        "ix_facility_blackout_society_facility",
        "facility_blackout_periods",
        ["society_id", "facility_id"],
    )
    op.create_index(
        "ix_facility_blackout_time_range",
        "facility_blackout_periods",
        ["society_id", "facility_id", "start_at", "end_at"],
    )

    # 4. Facility Bookings Table
    op.create_table(
        "facility_bookings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "society_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("societies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "facility_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("facilities.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "facility_area_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("facility_areas.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("booking_code", sa.String(50), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.String(500), nullable=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "delegate_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(50), nullable=False, server_default="PENDING_APPROVAL"),
        sa.Column("participant_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("idempotency_key", sa.String(100), nullable=True),
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
        sa.UniqueConstraint("society_id", "booking_code", name="uq_facility_booking_code"),
    )
    op.create_index(
        "ix_facility_booking_society_facility",
        "facility_bookings",
        ["society_id", "facility_id"],
    )
    op.create_index(
        "ix_facility_booking_society_user",
        "facility_bookings",
        ["society_id", "user_id"],
    )
    op.create_index(
        "ix_facility_booking_society_status",
        "facility_bookings",
        ["society_id", "status"],
    )
    op.create_index(
        "ix_facility_booking_time_range",
        "facility_bookings",
        ["society_id", "facility_id", "start_at", "end_at"],
    )
    op.create_index(
        "ix_facility_booking_idempotency",
        "facility_bookings",
        ["society_id", "idempotency_key"],
    )

    # 5. Facility Booking Participants Table
    op.create_table(
        "facility_booking_participants",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "society_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("societies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "booking_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("facility_bookings.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("contact_phone", sa.String(50), nullable=True),
        sa.Column("role_or_type", sa.String(50), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_facility_booking_part_society_booking",
        "facility_booking_participants",
        ["society_id", "booking_id"],
    )

    # 6. Facility Booking Approvals Table
    op.create_table(
        "facility_booking_approvals",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "society_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("societies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "booking_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("facility_bookings.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "approver_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("decision", sa.String(50), nullable=False),
        sa.Column("reason", sa.String(500), nullable=True),
        sa.Column(
            "decided_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_facility_booking_appr_society_booking",
        "facility_booking_approvals",
        ["society_id", "booking_id"],
    )

    # 7. Facility Booking Cancellations Table
    op.create_table(
        "facility_booking_cancellations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "society_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("societies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "booking_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("facility_bookings.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "cancelled_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("cancellation_reason", sa.String(500), nullable=True),
        sa.Column("is_within_notice_period", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column(
            "cancelled_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_facility_booking_canc_society_booking",
        "facility_booking_cancellations",
        ["society_id", "booking_id"],
    )

    # 8. Facility Booking Status Histories Table
    op.create_table(
        "facility_booking_status_histories",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "society_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("societies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "booking_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("facility_bookings.id", ondelete="CASCADE"),
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
        "ix_facility_booking_stat_society_booking",
        "facility_booking_status_histories",
        ["society_id", "booking_id"],
    )

    # Enable RLS & Force RLS on all 8 tables
    booking_tables = [
        "facility_booking_configs",
        "facility_availability_windows",
        "facility_blackout_periods",
        "facility_bookings",
        "facility_booking_participants",
        "facility_booking_approvals",
        "facility_booking_cancellations",
        "facility_booking_status_histories",
    ]

    for table in booking_tables:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY;")
        op.execute(
            f"CREATE POLICY {table}_tenant_isolation ON {table} "
            f"USING (society_id = NULLIF(current_setting('app.current_society_id', true), '')::uuid);"
        )


def downgrade() -> None:
    booking_tables = [
        "facility_booking_status_histories",
        "facility_booking_cancellations",
        "facility_booking_approvals",
        "facility_booking_participants",
        "facility_bookings",
        "facility_blackout_periods",
        "facility_availability_windows",
        "facility_booking_configs",
    ]

    for table in booking_tables:
        op.execute(f"DROP POLICY IF EXISTS {table}_tenant_isolation ON {table};")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY;")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;")

    for table in booking_tables:
        op.drop_table(table)
