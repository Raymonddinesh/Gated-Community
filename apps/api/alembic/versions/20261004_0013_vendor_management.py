"""Phase 13 — Vendor & Service Provider Management Foundation.

Revision ID: 0013_vendor_management
Revises: 0012_staff_workforce
Create Date: 2026-10-04
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0013_vendor_management"
down_revision: str | None = "0012_staff_workforce"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Vendor Categories Table
    op.create_table(
        "vendor_categories",
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
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"),
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
        sa.UniqueConstraint("society_id", "code", name="uq_vendor_category_society_code"),
    )
    op.create_index(
        "ix_vendor_category_society_code",
        "vendor_categories",
        ["society_id", "code"],
    )

    # 2. Vendor Profiles Table
    op.create_table(
        "vendor_profiles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "society_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("societies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("vendor_code", sa.String(32), nullable=False),
        sa.Column("legal_name", sa.String(200), nullable=False),
        sa.Column("display_name", sa.String(200), nullable=False),
        sa.Column("vendor_type", sa.String(32), nullable=False, server_default="COMPANY"),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "primary_category_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("vendor_categories.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("status", sa.String(32), nullable=False, server_default="ONBOARDING"),
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
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("society_id", "vendor_code", name="uq_vendor_profile_society_code"),
        sa.CheckConstraint(
            "vendor_type IN ('INDIVIDUAL', 'COMPANY', 'AGENCY', 'SERVICE_PROVIDER', 'CONTRACTOR', 'OTHER')",
            name="ck_vendor_profile_vendor_type",
        ),
        sa.CheckConstraint(
            "status IN ('ONBOARDING', 'ACTIVE', 'INACTIVE', 'SUSPENDED', 'BLACKLISTED', 'OFFBOARDED')",
            name="ck_vendor_profile_status",
        ),
    )
    op.create_index(
        "ix_vendor_profile_society_status",
        "vendor_profiles",
        ["society_id", "status"],
    )

    # 3. Vendor Society Associations Table
    op.create_table(
        "vendor_society_associations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "vendor_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("vendor_profiles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "society_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("societies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("status", sa.String(32), nullable=False, server_default="ACTIVE"),
        sa.Column(
            "onboarded_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("deactivated_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.UniqueConstraint("vendor_id", "society_id", name="uq_vendor_society_assoc"),
    )
    op.create_index(
        "ix_vendor_soc_assoc_society",
        "vendor_society_associations",
        ["society_id", "status"],
    )

    # 4. Vendor Contacts Table
    op.create_table(
        "vendor_contacts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "society_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("societies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "vendor_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("vendor_profiles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(150), nullable=False),
        sa.Column("designation", sa.String(100), nullable=True),
        sa.Column("phone", sa.String(32), nullable=False),
        sa.Column("alternate_phone", sa.String(32), nullable=True),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("preferred_contact_method", sa.String(32), nullable=False, server_default="PHONE"),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default="false"),
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
        "ix_vendor_contact_vendor",
        "vendor_contacts",
        ["society_id", "vendor_id"],
    )

    # 5. Vendor Addresses Table
    op.create_table(
        "vendor_addresses",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "society_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("societies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "vendor_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("vendor_profiles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("address_line1", sa.String(255), nullable=False),
        sa.Column("address_line2", sa.String(255), nullable=True),
        sa.Column("city", sa.String(100), nullable=False),
        sa.Column("state", sa.String(100), nullable=False),
        sa.Column("postal_code", sa.String(20), nullable=False),
        sa.Column("country", sa.String(2), nullable=False, server_default="IN"),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default="true"),
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
        "ix_vendor_address_vendor",
        "vendor_addresses",
        ["society_id", "vendor_id"],
    )

    # 6. Vendor Services Table
    op.create_table(
        "vendor_services",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "society_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("societies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "vendor_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("vendor_profiles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("service_name", sa.String(150), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "category_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("vendor_categories.id", ondelete="SET NULL"),
            nullable=True,
        ),
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
        "ix_vendor_service_vendor",
        "vendor_services",
        ["society_id", "vendor_id"],
    )

    # 7. Vendor Documents Table
    op.create_table(
        "vendor_documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "society_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("societies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "vendor_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("vendor_profiles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("document_type", sa.String(50), nullable=False, server_default="REGISTRATION"),
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
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "document_type IN ('REGISTRATION', 'CERTIFICATE', 'INSURANCE', 'LICENSE', 'QUALIFICATION', 'COMPLIANCE', 'OTHER')",
            name="ck_vendor_document_type",
        ),
    )
    op.create_index(
        "ix_vendor_doc_vendor",
        "vendor_documents",
        ["society_id", "vendor_id"],
    )

    # 8. Vendor Status Histories Table
    op.create_table(
        "vendor_status_histories",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "society_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("societies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "vendor_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("vendor_profiles.id", ondelete="CASCADE"),
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
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_vendor_status_hist_vendor",
        "vendor_status_histories",
        ["society_id", "vendor_id"],
    )

    # 9. Vendor Assignment Histories Table
    op.create_table(
        "vendor_assignment_histories",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "society_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("societies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "vendor_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("vendor_profiles.id", ondelete="CASCADE"),
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
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_vendor_assign_hist_vendor",
        "vendor_assignment_histories",
        ["society_id", "vendor_id"],
    )
    op.create_index(
        "ix_vendor_assign_hist_wo",
        "vendor_assignment_histories",
        ["society_id", "work_order_id"],
    )

    # Enable RLS & Force RLS on all 9 tables
    vendor_tables = [
        "vendor_categories",
        "vendor_profiles",
        "vendor_society_associations",
        "vendor_contacts",
        "vendor_addresses",
        "vendor_services",
        "vendor_documents",
        "vendor_status_histories",
        "vendor_assignment_histories",
    ]

    for table in vendor_tables:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY;")
        op.execute(
            f"CREATE POLICY {table}_tenant_isolation ON {table} "
            f"USING (society_id = NULLIF(current_setting('app.current_society_id', true), '')::uuid);"
        )


def downgrade() -> None:
    vendor_tables = [
        "vendor_assignment_histories",
        "vendor_status_histories",
        "vendor_documents",
        "vendor_services",
        "vendor_addresses",
        "vendor_contacts",
        "vendor_society_associations",
        "vendor_profiles",
        "vendor_categories",
    ]

    for table in vendor_tables:
        op.execute(f"DROP POLICY IF EXISTS {table}_tenant_isolation ON {table};")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY;")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;")

    for table in vendor_tables:
        op.drop_table(table)
