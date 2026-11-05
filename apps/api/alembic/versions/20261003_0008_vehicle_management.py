"""Vehicle Management & Vehicle Access Foundation Migration.

Revision ID: 0008_vehicle_management
Revises: 0007_resident_occupancy
Create Date: 2026-10-03 02:00:00.000000

Establishes:
1. vehicles table (registration, normalization, EV flags, verification lifecycle, status)
2. vehicle_resident_associations table (owner, tenant, resident, delegate mapping, primary vehicle)
3. vehicle_verifications table (verification lifecycle audit trail)
4. vehicle_documents table (RC, insurance, PUC, permit document storage references)
5. vehicle_parking_associations table (parking slot association boundary)
6. vehicle_access_records table (gate entry/exit immutable logs, RFID/ANPR readiness)
7. PostgreSQL Row-Level Security (RLS) policies with explicit USING and WITH CHECK + FORCE ROW LEVEL SECURITY.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008_vehicle_management"
down_revision: str | None = "0007_resident_occupancy"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Vehicles Table
    op.create_table(
        "vehicles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "society_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("societies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("registration_number", sa.String(32), nullable=False),
        sa.Column("normalized_registration_number", sa.String(32), nullable=False),
        sa.Column("vehicle_type", sa.String(32), nullable=False),
        sa.Column("make", sa.String(100), nullable=True),
        sa.Column("model", sa.String(100), nullable=True),
        sa.Column("variant", sa.String(100), nullable=True),
        sa.Column("color", sa.String(50), nullable=True),
        sa.Column("fuel_type", sa.String(32), server_default="PETROL", nullable=False),
        sa.Column("is_ev", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("battery_capacity_kwh", sa.Numeric(6, 2), nullable=True),
        sa.Column("charging_required", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("status", sa.String(32), server_default="ACTIVE", nullable=False),
        sa.Column("verification_status", sa.String(32), server_default="PENDING", nullable=False),
        sa.Column("notes", sa.String(500), nullable=True),
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
            "vehicle_type IN ('FOUR_WHEELER', 'THREE_WHEELER', 'TWO_WHEELER', 'BICYCLE')",
            name="ck_vehicles_vehicle_type",
        ),
        sa.CheckConstraint(
            "fuel_type IN ('PETROL', 'DIESEL', 'CNG', 'ELECTRIC', 'HYBRID', 'OTHER', 'NOT_APPLICABLE')",
            name="ck_vehicles_fuel_type",
        ),
        sa.CheckConstraint(
            "status IN ('ACTIVE', 'INACTIVE', 'SOLD', 'TRANSFERRED', 'SCRAPPED')",
            name="ck_vehicles_status",
        ),
        sa.CheckConstraint(
            "verification_status IN ('PENDING', 'VERIFIED', 'REJECTED', 'EXPIRED')",
            name="ck_vehicles_verification_status",
        ),
    )
    op.create_index("ix_vehicles_society_status", "vehicles", ["society_id", "status"])
    op.create_index(
        "ix_vehicles_society_normalized_reg",
        "vehicles",
        ["society_id", "normalized_registration_number"],
    )
    op.create_index(
        "ix_vehicles_verification_status",
        "vehicles",
        ["society_id", "verification_status"],
    )
    op.create_index(
        "uq_vehicles_society_active_normalized_reg",
        "vehicles",
        ["society_id", "normalized_registration_number"],
        unique=True,
        postgresql_where=sa.text("status = 'ACTIVE'"),
    )

    # 2. Vehicle Resident Associations Table
    op.create_table(
        "vehicle_resident_associations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "society_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("societies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "vehicle_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("vehicles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
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
        sa.Column("association_type", sa.String(32), server_default="RESIDENT", nullable=False),
        sa.Column("is_primary", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("valid_from", sa.Date(), nullable=False),
        sa.Column("valid_to", sa.Date(), nullable=True),
        sa.Column("status", sa.String(32), server_default="ACTIVE", nullable=False),
        sa.Column("notes", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "association_type IN ('OWNER', 'TENANT', 'RESIDENT', 'AUTHORIZED_DELEGATE')",
            name="ck_vehicle_assoc_type",
        ),
        sa.CheckConstraint(
            "status IN ('ACTIVE', 'ENDED', 'REVOKED')",
            name="ck_vehicle_assoc_status",
        ),
    )
    op.create_index(
        "ix_vehicle_assoc_vehicle_id",
        "vehicle_resident_associations",
        ["vehicle_id"],
    )
    op.create_index(
        "ix_vehicle_assoc_user_id",
        "vehicle_resident_associations",
        ["user_id"],
    )
    op.create_index(
        "ix_vehicle_assoc_unit_id",
        "vehicle_resident_associations",
        ["unit_id"],
    )
    op.create_index(
        "ix_vehicle_assoc_society_status",
        "vehicle_resident_associations",
        ["society_id", "status"],
    )
    op.create_index(
        "uq_vehicle_assoc_active_primary",
        "vehicle_resident_associations",
        ["society_id", "unit_id", "user_id"],
        unique=True,
        postgresql_where=sa.text("status = 'ACTIVE' AND is_primary = true"),
    )

    # 3. Vehicle Verifications Table
    op.create_table(
        "vehicle_verifications",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "society_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("societies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "vehicle_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("vehicles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "verifier_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("verification_status", sa.String(32), nullable=False),
        sa.Column("verification_date", sa.Date(), nullable=False),
        sa.Column("reason", sa.String(255), nullable=True),
        sa.Column("supporting_document_ref", sa.String(255), nullable=True),
        sa.Column("notes", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "verification_status IN ('VERIFIED', 'REJECTED', 'EXPIRED')",
            name="ck_vehicle_verif_status",
        ),
    )
    op.create_index(
        "ix_vehicle_verif_vehicle_id",
        "vehicle_verifications",
        ["vehicle_id"],
    )
    op.create_index(
        "ix_vehicle_verif_verifier",
        "vehicle_verifications",
        ["verifier_user_id"],
    )

    # 4. Vehicle Documents Table
    op.create_table(
        "vehicle_documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "society_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("societies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "vehicle_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("vehicles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("document_type", sa.String(50), nullable=False),
        sa.Column("document_number", sa.String(100), nullable=True),
        sa.Column("file_key", sa.String(500), nullable=False),
        sa.Column("file_name", sa.String(255), nullable=False),
        sa.Column("file_size_bytes", sa.Integer(), nullable=True),
        sa.Column("content_type", sa.String(100), server_default="application/pdf", nullable=False),
        sa.Column("valid_from", sa.Date(), nullable=True),
        sa.Column("valid_to", sa.Date(), nullable=True),
        sa.Column(
            "uploaded_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "document_type IN ('RC', 'INSURANCE', 'PUC', 'PERMIT', 'OTHER')",
            name="ck_vehicle_doc_type",
        ),
    )

    op.create_index(
        "ix_vehicle_doc_vehicle_id",
        "vehicle_documents",
        ["vehicle_id"],
    )

    # 5. Vehicle Parking Associations Table
    op.create_table(
        "vehicle_parking_associations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "society_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("societies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "vehicle_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("vehicles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("parking_slot_number", sa.String(50), nullable=False),
        sa.Column("valid_from", sa.Date(), nullable=False),
        sa.Column("valid_to", sa.Date(), nullable=True),
        sa.Column("status", sa.String(32), server_default="ACTIVE", nullable=False),
        sa.Column("notes", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('ACTIVE', 'ENDED')",
            name="ck_vehicle_parking_status",
        ),
    )
    op.create_index(
        "ix_vehicle_parking_vehicle_id",
        "vehicle_parking_associations",
        ["vehicle_id"],
    )
    op.create_index(
        "ix_vehicle_parking_society_slot",
        "vehicle_parking_associations",
        ["society_id", "parking_slot_number"],
    )

    # 6. Vehicle Access Records Table (Gate entry/exit logs)
    op.create_table(
        "vehicle_access_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "society_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("societies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "vehicle_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("vehicles.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("registration_number_snapshot", sa.String(32), nullable=False),
        sa.Column("normalized_registration_number_snapshot", sa.String(32), nullable=False),
        sa.Column("access_type", sa.String(20), nullable=False),
        sa.Column("gate_identifier", sa.String(50), nullable=False),
        sa.Column("access_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("detection_method", sa.String(30), server_default="MANUAL", nullable=False),
        sa.Column("captured_image_ref", sa.String(500), nullable=True),
        sa.Column(
            "operator_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("source_provider", sa.String(50), server_default="MANUAL", nullable=False),
        sa.Column("confidence_score", sa.Numeric(4, 3), nullable=True),
        sa.Column("notes", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "access_type IN ('ENTRY', 'EXIT')",
            name="ck_vehicle_access_type",
        ),
        sa.CheckConstraint(
            "detection_method IN ('MANUAL', 'RFID', 'ANPR')",
            name="ck_vehicle_detection_method",
        ),
    )
    op.create_index(
        "ix_vehicle_access_society_time",
        "vehicle_access_records",
        ["society_id", "access_time"],
    )
    op.create_index(
        "ix_vehicle_access_vehicle_id",
        "vehicle_access_records",
        ["vehicle_id"],
    )
    op.create_index(
        "ix_vehicle_access_normalized_reg",
        "vehicle_access_records",
        ["society_id", "normalized_registration_number_snapshot"],
    )

    # 7. PostgreSQL Row-Level Security with explicit USING and WITH CHECK
    bind = op.get_bind()
    if bind and getattr(bind, "dialect", None) and bind.dialect.name == "postgresql":
        phase8_tables = [
            "vehicles",
            "vehicle_resident_associations",
            "vehicle_verifications",
            "vehicle_documents",
            "vehicle_parking_associations",
            "vehicle_access_records",
        ]
        for table in phase8_tables:
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
    # Drop all Phase 8 tables in reverse order of creation
    op.drop_table("vehicle_access_records")
    op.drop_table("vehicle_parking_associations")
    op.drop_table("vehicle_documents")
    op.drop_table("vehicle_verifications")
    op.drop_table("vehicle_resident_associations")
    op.drop_table("vehicles")
