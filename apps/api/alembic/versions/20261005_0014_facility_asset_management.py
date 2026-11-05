"""Phase 14 — Facility & Asset Management Foundation.

Revision ID: 0014_facility_asset_management
Revises: 0013_vendor_management
Create Date: 2026-10-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0014_facility_asset_management"
down_revision: str | None = "0013_vendor_management"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Facilities Table
    op.create_table(
        "facilities",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "society_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("societies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("facility_code", sa.String(50), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("facility_type", sa.String(50), nullable=False),
        sa.Column("description", sa.String(500), nullable=True),
        sa.Column("status", sa.String(50), nullable=False, server_default="ACTIVE"),
        sa.Column("capacity", sa.Integer(), nullable=True),
        sa.Column("location_summary", sa.String(255), nullable=True),
        sa.Column("is_bookable_separately", sa.Boolean(), nullable=False, server_default="false"),
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
        sa.UniqueConstraint("society_id", "facility_code", name="uq_facility_society_code"),
    )
    op.create_index(
        "ix_facility_society_code",
        "facilities",
        ["society_id", "facility_code"],
    )
    op.create_index(
        "ix_facility_society_type",
        "facilities",
        ["society_id", "facility_type"],
    )

    # 2. Facility Areas Table
    op.create_table(
        "facility_areas",
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
        sa.Column("area_code", sa.String(50), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("description", sa.String(500), nullable=True),
        sa.Column("floor_level", sa.String(50), nullable=True),
        sa.Column("max_occupancy", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(50), nullable=False, server_default="ACTIVE"),
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
        sa.UniqueConstraint("facility_id", "area_code", name="uq_facility_area_facility_code"),
    )
    op.create_index(
        "ix_facility_area_society_facility",
        "facility_areas",
        ["society_id", "facility_id"],
    )

    # 3. Asset Categories Table
    op.create_table(
        "asset_categories",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "society_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("societies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("category_code", sa.String(50), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("description", sa.String(500), nullable=True),
        sa.Column(
            "parent_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("asset_categories.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("is_critical", sa.Boolean(), nullable=False, server_default="false"),
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
        sa.UniqueConstraint("society_id", "category_code", name="uq_asset_category_society_code"),
    )
    op.create_index(
        "ix_asset_category_society_code",
        "asset_categories",
        ["society_id", "category_code"],
    )

    # 4. Assets Table
    op.create_table(
        "assets",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "society_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("societies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("asset_code", sa.String(50), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column(
            "category_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("asset_categories.id", ondelete="RESTRICT"),
            nullable=False,
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
        sa.Column("serial_number", sa.String(100), nullable=True),
        sa.Column("model_number", sa.String(100), nullable=True),
        sa.Column("manufacturer", sa.String(100), nullable=True),
        sa.Column(
            "vendor_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("vendor_profiles.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("purchase_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("warranty_expiry_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(50), nullable=False, server_default="IN_SERVICE"),
        sa.Column("criticality", sa.String(50), nullable=False, server_default="MEDIUM"),
        sa.Column("estimated_lifespan_months", sa.Integer(), nullable=True),
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
        sa.UniqueConstraint("society_id", "asset_code", name="uq_asset_society_code"),
    )
    op.create_index(
        "ix_asset_society_code",
        "assets",
        ["society_id", "asset_code"],
    )
    op.create_index(
        "ix_asset_society_status",
        "assets",
        ["society_id", "status"],
    )
    op.create_index(
        "ix_asset_society_category",
        "assets",
        ["society_id", "category_id"],
    )

    # 5. Asset Locations Table
    op.create_table(
        "asset_locations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "society_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("societies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "asset_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("assets.id", ondelete="CASCADE"),
            nullable=False,
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
        sa.Column("location_details", sa.String(500), nullable=True),
        sa.Column(
            "moved_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "moved_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("reason", sa.String(500), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_asset_location_society_asset",
        "asset_locations",
        ["society_id", "asset_id"],
    )

    # 6. Asset Status History Table
    op.create_table(
        "asset_status_history",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "society_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("societies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "asset_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("assets.id", ondelete="CASCADE"),
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
        "ix_asset_status_history_society_asset",
        "asset_status_history",
        ["society_id", "asset_id"],
    )

    # 7. Asset Assignment History Table
    op.create_table(
        "asset_assignment_history",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "society_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("societies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "asset_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("assets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("assigned_to_type", sa.String(50), nullable=False),
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
        sa.Column(
            "assigned_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("unassigned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "assigned_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("notes", sa.String(500), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_asset_assignment_history_society_asset",
        "asset_assignment_history",
        ["society_id", "asset_id"],
    )

    # 8. Asset Documents Table
    op.create_table(
        "asset_documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "society_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("societies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "asset_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("assets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("document_type", sa.String(50), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("file_path", sa.String(500), nullable=False),
        sa.Column("file_size_bytes", sa.Integer(), nullable=True),
        sa.Column("mime_type", sa.String(100), nullable=True),
        sa.Column(
            "uploaded_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "uploaded_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_asset_documents_society_asset",
        "asset_documents",
        ["society_id", "asset_id"],
    )

    # 9. Asset Maintenance Links Table
    op.create_table(
        "asset_maintenance_links",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "society_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("societies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "asset_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("assets.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "facility_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("facilities.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "work_order_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("maintenance_work_orders.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "complaint_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("complaints.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("link_type", sa.String(50), nullable=False, server_default="CORRECTIVE"),
        sa.Column(
            "linked_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "linked_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("notes", sa.String(500), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_asset_maint_link_society_asset",
        "asset_maintenance_links",
        ["society_id", "asset_id"],
    )
    op.create_index(
        "ix_asset_maint_link_society_facility",
        "asset_maintenance_links",
        ["society_id", "facility_id"],
    )
    op.create_index(
        "ix_asset_maint_link_society_wo",
        "asset_maintenance_links",
        ["society_id", "work_order_id"],
    )

    # 10. Facility Documents Table
    op.create_table(
        "facility_documents",
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
        sa.Column("document_type", sa.String(50), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("file_path", sa.String(500), nullable=False),
        sa.Column("file_size_bytes", sa.Integer(), nullable=True),
        sa.Column("mime_type", sa.String(100), nullable=True),
        sa.Column(
            "uploaded_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "uploaded_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_facility_documents_society_facility",
        "facility_documents",
        ["society_id", "facility_id"],
    )

    # Enable RLS & Force RLS on all 10 tables
    facility_asset_tables = [
        "facilities",
        "facility_areas",
        "asset_categories",
        "assets",
        "asset_locations",
        "asset_status_history",
        "asset_assignment_history",
        "asset_documents",
        "asset_maintenance_links",
        "facility_documents",
    ]

    for table in facility_asset_tables:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY;")
        op.execute(
            f"CREATE POLICY {table}_tenant_isolation ON {table} "
            f"USING (society_id = NULLIF(current_setting('app.current_society_id', true), '')::uuid);"
        )


def downgrade() -> None:
    facility_asset_tables = [
        "facility_documents",
        "asset_maintenance_links",
        "asset_documents",
        "asset_assignment_history",
        "asset_status_history",
        "asset_locations",
        "assets",
        "asset_categories",
        "facility_areas",
        "facilities",
    ]

    for table in facility_asset_tables:
        op.execute(f"DROP POLICY IF EXISTS {table}_tenant_isolation ON {table};")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY;")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;")

    for table in facility_asset_tables:
        op.drop_table(table)
