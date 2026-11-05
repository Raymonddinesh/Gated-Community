"""Visitor & Security Management Foundation Migration.

Revision ID: 0009_visitor_management
Revises: 0008_vehicle_management
Create Date: 2026-10-03 16:00:00.000000

Establishes:
1. visitors table (visitor registration, type, identification, photo reference, status)
2. visitor_invitations table (resident pre-approved visitor invitations, time window, pass code)
3. visitor_approvals table (resident approval/rejection decision workflow)
4. visitor_documents table (visitor photo / ID document metadata storage references)
5. visitor_access_records table (gate entry/exit immutable logs, QR/OTP readiness)
6. PostgreSQL Row-Level Security (RLS) policies with explicit USING and WITH CHECK + FORCE ROW LEVEL SECURITY.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0009_visitor_management"
down_revision: str | None = "0008_vehicle_management"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Visitors Table
    op.create_table(
        "visitors",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "society_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("societies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("phone", sa.String(20), nullable=False),
        sa.Column("alternate_phone", sa.String(20), nullable=True),
        sa.Column("visitor_type", sa.String(32), server_default="GUEST", nullable=False),
        sa.Column("identification_type", sa.String(50), nullable=True),
        sa.Column("identification_number", sa.String(100), nullable=True),
        sa.Column("photo_file_key", sa.String(500), nullable=True),
        sa.Column("notes", sa.String(500), nullable=True),
        sa.Column("status", sa.String(32), server_default="ACTIVE", nullable=False),
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "updated_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "visitor_type IN ('GUEST', 'DELIVERY', 'SERVICE', 'CAB', 'OTHER')",
            name="ck_visitors_visitor_type",
        ),
        sa.CheckConstraint(
            "status IN ('ACTIVE', 'BLOCKED', 'ARCHIVED')",
            name="ck_visitors_status",
        ),
    )
    op.create_index("ix_visitors_society_phone", "visitors", ["society_id", "phone"])
    op.create_index("ix_visitors_society_type", "visitors", ["society_id", "visitor_type"])
    op.create_index("ix_visitors_society_status", "visitors", ["society_id", "status"])

    # 2. Visitor Invitations Table
    op.create_table(
        "visitor_invitations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "society_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("societies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "visitor_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("visitors.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "host_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "unit_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("units.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("expected_date", sa.Date(), nullable=False),
        sa.Column("expected_arrival_window_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expected_arrival_window_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expected_departure", sa.DateTime(timezone=True), nullable=True),
        sa.Column("purpose", sa.String(255), nullable=True),
        sa.Column("pass_code", sa.String(16), nullable=True),
        sa.Column("access_code_hash", sa.String(128), nullable=True),
        sa.Column("delivery_company", sa.String(100), nullable=True),
        sa.Column("service_type", sa.String(100), nullable=True),
        sa.Column("status", sa.String(32), server_default="PENDING", nullable=False),
        sa.Column("notes", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('PENDING', 'APPROVED', 'REJECTED', 'EXPIRED', 'CANCELLED', 'USED')",
            name="ck_visitor_invitations_status",
        ),
    )
    op.create_index("ix_visitor_invitations_society_unit", "visitor_invitations", ["society_id", "unit_id"])
    op.create_index(
        "ix_visitor_invitations_society_host", "visitor_invitations", ["society_id", "host_user_id"]
    )
    op.create_index(
        "ix_visitor_invitations_expected_date", "visitor_invitations", ["society_id", "expected_date"]
    )
    op.create_index("ix_visitor_invitations_pass_code", "visitor_invitations", ["society_id", "pass_code"])

    # 3. Visitor Approvals Table
    op.create_table(
        "visitor_approvals",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "society_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("societies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "visitor_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("visitors.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "invitation_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("visitor_invitations.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "unit_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("units.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "approving_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("approval_status", sa.String(32), nullable=False),
        sa.Column("decision_reason", sa.String(255), nullable=True),
        sa.Column("decision_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "approval_status IN ('PENDING', 'APPROVED', 'REJECTED', 'EXPIRED')",
            name="ck_visitor_approvals_status",
        ),
    )
    op.create_index("ix_visitor_approvals_society_visitor", "visitor_approvals", ["society_id", "visitor_id"])
    op.create_index("ix_visitor_approvals_society_unit", "visitor_approvals", ["society_id", "unit_id"])

    # 4. Visitor Documents Table
    op.create_table(
        "visitor_documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "society_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("societies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "visitor_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("visitors.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("document_type", sa.String(50), nullable=False),
        sa.Column("file_key", sa.String(500), nullable=False),
        sa.Column("file_name", sa.String(255), nullable=False),
        sa.Column("file_size_bytes", sa.Integer(), nullable=True),
        sa.Column("content_type", sa.String(100), server_default="image/jpeg", nullable=False),
        sa.Column(
            "uploaded_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "document_type IN ('PHOTO', 'ID_CARD', 'DRIVING_LICENSE', 'PASSPORT', 'OTHER')",
            name="ck_visitor_doc_type",
        ),
    )
    op.create_index("ix_visitor_doc_visitor_id", "visitor_documents", ["visitor_id"])

    # 5. Visitor Access Records Table (Gate entry/exit logs)
    op.create_table(
        "visitor_access_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "society_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("societies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "visitor_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("visitors.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "invitation_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("visitor_invitations.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "approval_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("visitor_approvals.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "unit_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("units.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "host_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "security_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "vehicle_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("vehicles.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("visitor_name_snapshot", sa.String(100), nullable=False),
        sa.Column("visitor_phone_snapshot", sa.String(20), nullable=False),
        sa.Column("visitor_type_snapshot", sa.String(32), nullable=False),
        sa.Column("gate_identifier", sa.String(50), nullable=False),
        sa.Column("access_type", sa.String(20), server_default="ENTRY", nullable=False),
        sa.Column("access_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("entry_method", sa.String(30), server_default="MANUAL", nullable=False),
        sa.Column("exit_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("exit_gate_identifier", sa.String(50), nullable=True),
        sa.Column(
            "exit_security_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("exit_method", sa.String(30), nullable=True),
        sa.Column("delivery_company", sa.String(100), nullable=True),
        sa.Column("service_type", sa.String(100), nullable=True),
        sa.Column("notes", sa.String(500), nullable=True),
        sa.Column("emergency_override_reason", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "access_type IN ('ENTRY', 'EXIT')",
            name="ck_visitor_access_type",
        ),
        sa.CheckConstraint(
            "entry_method IN ('MANUAL', 'QR', 'OTP', 'PRE_APPROVED')",
            name="ck_visitor_entry_method",
        ),
    )
    op.create_index("ix_visitor_access_society_time", "visitor_access_records", ["society_id", "access_time"])
    op.create_index("ix_visitor_access_visitor_id", "visitor_access_records", ["visitor_id"])
    op.create_index("ix_visitor_access_unit_id", "visitor_access_records", ["society_id", "unit_id"])

    # 6. PostgreSQL Row-Level Security with explicit USING and WITH CHECK
    bind = op.get_bind()
    if bind and getattr(bind, "dialect", None) and bind.dialect.name == "postgresql":
        phase9_tables = [
            "visitors",
            "visitor_invitations",
            "visitor_approvals",
            "visitor_documents",
            "visitor_access_records",
        ]
        for table in phase9_tables:
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
    # Drop all Phase 9 tables in reverse order of creation
    op.drop_table("visitor_access_records")
    op.drop_table("visitor_documents")
    op.drop_table("visitor_approvals")
    op.drop_table("visitor_invitations")
    op.drop_table("visitors")
