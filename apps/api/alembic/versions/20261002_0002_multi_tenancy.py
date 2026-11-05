"""Multi-Tenancy, Spatial Hierarchy, and Identity Foundation

Revision ID: 0002_multi_tenancy
Revises: 0001_baseline
Create Date: 2026-10-02 12:45:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0002_multi_tenancy"
down_revision: str | None = "0001_baseline"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Users Table (Global Identity)
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("phone", sa.String(32), nullable=True),
        sa.Column("password_hash", sa.String(255), nullable=True),
        sa.Column("first_name", sa.String(100), nullable=False),
        sa.Column("last_name", sa.String(100), nullable=False),
        sa.Column("display_name", sa.String(200), nullable=False),
        sa.Column("preferred_language", sa.String(10), server_default="en", nullable=False),
        sa.Column("status", sa.String(32), server_default="ACTIVE", nullable=False),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("email IS NOT NULL OR phone IS NOT NULL", name="ck_users_email_or_phone_required"),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_index("ix_users_phone", "users", ["phone"], unique=True)
    op.create_index("ix_users_status", "users", ["status"])

    # 2. Societies Table (Tenant Root)
    op.create_table(
        "societies",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("legal_name", sa.String(255), nullable=False),
        sa.Column("display_name", sa.String(255), nullable=False),
        sa.Column("registration_number", sa.String(100), nullable=True),
        sa.Column("address_line1", sa.String(255), nullable=False),
        sa.Column("address_line2", sa.String(255), nullable=True),
        sa.Column("city", sa.String(100), nullable=False),
        sa.Column("state", sa.String(100), nullable=False),
        sa.Column("country", sa.String(10), server_default="IN", nullable=False),
        sa.Column("postal_code", sa.String(20), nullable=False),
        sa.Column("timezone", sa.String(50), server_default="Asia/Kolkata", nullable=False),
        sa.Column("default_language", sa.String(10), server_default="en", nullable=False),
        sa.Column("status", sa.String(32), server_default="ACTIVE", nullable=False),
        sa.Column("onboarding_status", sa.String(32), server_default="COMPLETED", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_societies_registration_number", "societies", ["registration_number"])
    op.create_index("ix_societies_status", "societies", ["status"])

    # 3. Blocks Table
    op.create_table(
        "blocks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "society_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("societies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("code", sa.String(50), nullable=False),
        sa.Column("display_name", sa.String(100), nullable=False),
        sa.Column("sequence_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column("status", sa.String(32), server_default="ACTIVE", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("society_id", "code", name="uq_blocks_society_code"),
    )
    op.create_index("ix_blocks_society_id", "blocks", ["society_id"])

    # 4. Floors Table
    op.create_table(
        "floors",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "society_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("societies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "block_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("blocks.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("floor_number", sa.Integer(), nullable=False),
        sa.Column("display_name", sa.String(100), nullable=False),
        sa.Column("sequence_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column("status", sa.String(32), server_default="ACTIVE", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("society_id", "block_id", "floor_number", name="uq_floors_block_number"),
    )
    op.create_index("ix_floors_society_id", "floors", ["society_id"])
    op.create_index("ix_floors_block_id", "floors", ["block_id"])

    # 5. Units Table
    op.create_table(
        "units",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "society_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("societies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "block_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("blocks.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "floor_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("floors.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("unit_number", sa.String(50), nullable=False),
        sa.Column("unit_type", sa.String(50), server_default="2BHK", nullable=False),
        sa.Column("carpet_area_sqft", sa.Float(), nullable=True),
        sa.Column("occupancy_status", sa.String(32), server_default="VACANT", nullable=False),
        sa.Column("status", sa.String(32), server_default="ACTIVE", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("society_id", "block_id", "unit_number", name="uq_units_society_block_number"),
    )
    op.create_index("ix_units_society_id", "units", ["society_id"])
    op.create_index("ix_units_block_id", "units", ["block_id"])
    op.create_index("ix_units_floor_id", "units", ["floor_id"])

    # 6. User Society Memberships Table
    op.create_table(
        "user_society_memberships",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "society_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("societies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("membership_status", sa.String(32), server_default="ACTIVE", nullable=False),
        sa.Column("joined_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deactivated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "society_id", name="uq_membership_user_society"),
    )
    op.create_index("ix_user_society_memberships_user_id", "user_society_memberships", ["user_id"])
    op.create_index("ix_user_society_memberships_society_id", "user_society_memberships", ["society_id"])

    # 7. Unit Occupancies Table
    op.create_table(
        "unit_occupancies",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "society_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("societies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "unit_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("units.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("relationship_type", sa.String(32), nullable=False),
        sa.Column("is_primary_contact", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("valid_from", sa.Date(), nullable=True),
        sa.Column("valid_to", sa.Date(), nullable=True),
        sa.Column("status", sa.String(32), server_default="ACTIVE", nullable=False),
        sa.Column("notes", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_unit_occupancies_society_id", "unit_occupancies", ["society_id"])
    op.create_index("ix_unit_occupancies_unit_id", "unit_occupancies", ["unit_id"])
    op.create_index("ix_unit_occupancies_user_id", "unit_occupancies", ["user_id"])
    op.create_index("ix_unit_occupancies_relationship_type", "unit_occupancies", ["relationship_type"])

    # 8. Resident Profiles Table
    op.create_table(
        "resident_profiles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "society_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("societies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("emergency_contact_name", sa.String(150), nullable=True),
        sa.Column("emergency_contact_phone", sa.String(32), nullable=True),
        sa.Column("preferred_contact_method", sa.String(32), server_default="APP", nullable=False),
        sa.Column("accessibility_preferences", sa.JSON(), nullable=False),
        sa.Column("communication_preferences", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("user_id", "society_id", name="uq_resident_profile_user_society"),
    )
    op.create_index("ix_resident_profiles_user_id", "resident_profiles", ["user_id"])
    op.create_index("ix_resident_profiles_society_id", "resident_profiles", ["society_id"])

    # 9. Roles Table
    op.create_table(
        "roles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("code", sa.String(50), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("scope_type", sa.String(20), server_default="SOCIETY", nullable=False),
        sa.Column("description", sa.String(255), nullable=True),
        sa.Column("is_system_role", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("code", "scope_type", name="uq_roles_code_scope"),
    )
    op.create_index("ix_roles_code", "roles", ["code"])

    # 10. Permissions Table
    op.create_table(
        "permissions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("code", sa.String(100), nullable=False, unique=True),
        sa.Column("name", sa.String(150), nullable=False),
        sa.Column("module", sa.String(50), nullable=False),
        sa.Column("description", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_permissions_code", "permissions", ["code"])
    op.create_index("ix_permissions_module", "permissions", ["module"])

    # 11. Role Permissions Junction Table
    op.create_table(
        "role_permissions",
        sa.Column(
            "role_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("roles.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "permission_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("permissions.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )

    # 12. Role Assignments Table
    op.create_table(
        "role_assignments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "role_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("roles.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "society_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("societies.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("scope_type", sa.String(20), server_default="SOCIETY", nullable=False),
        sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(32), server_default="ACTIVE", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "(scope_type = 'PLATFORM' AND society_id IS NULL) OR (scope_type = 'SOCIETY' AND society_id IS NOT NULL)",
            name="ck_role_assignments_scope_validity",
        ),
    )
    op.create_index("ix_role_assignments_user_id", "role_assignments", ["user_id"])
    op.create_index("ix_role_assignments_role_id", "role_assignments", ["role_id"])
    op.create_index("ix_role_assignments_society_id", "role_assignments", ["society_id"])
    op.create_index(
        "ix_role_assignments_user_society_role",
        "role_assignments",
        ["user_id", "role_id", "society_id"],
        unique=True,
    )

    # 13. Audit Logs Table (Append-Only)
    op.create_table(
        "audit_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "society_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("societies.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "actor_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("action", sa.String(50), nullable=False),
        sa.Column("entity_type", sa.String(50), nullable=False),
        sa.Column("entity_id", sa.String(100), nullable=False),
        sa.Column("request_id", sa.String(100), nullable=True),
        sa.Column("correlation_id", sa.String(100), nullable=True),
        sa.Column("before_state", sa.JSON(), nullable=True),
        sa.Column("after_state", sa.JSON(), nullable=True),
        sa.Column("diff", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_audit_logs_society_created", "audit_logs", ["society_id", "created_at"])
    op.create_index("ix_audit_logs_entity", "audit_logs", ["entity_type", "entity_id"])
    op.create_index("ix_audit_logs_actor", "audit_logs", ["actor_user_id"])

    # 14. PostgreSQL Row-Level Security (RLS) Policies (Applied on PostgreSQL connections)
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        # Strict tenant-owned tables
        rls_tables = [
            "blocks",
            "floors",
            "units",
            "user_society_memberships",
            "unit_occupancies",
            "resident_profiles",
        ]
        for table in rls_tables:
            op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;")
            op.execute(
                f"""
                CREATE POLICY tenant_isolation_{table} ON {table}
                USING (
                    society_id = NULLIF(current_setting('app.current_society_id', true), '')::uuid
                );
                """
            )

        # Role assignments RLS: Platform roles (scope_type='PLATFORM') are platform visible;
        # Society roles are strictly partitioned by society_id
        op.execute("ALTER TABLE role_assignments ENABLE ROW LEVEL SECURITY;")
        op.execute(
            """
            CREATE POLICY tenant_isolation_role_assignments ON role_assignments
            USING (
                scope_type = 'PLATFORM'
                OR society_id = NULLIF(current_setting('app.current_society_id', true), '')::uuid
            );
            """
        )

        # Audit logs RLS: Platform audit logs (society_id IS NULL) are platform visible;
        # Society audit logs are strictly partitioned by society_id
        op.execute("ALTER TABLE audit_logs ENABLE ROW LEVEL SECURITY;")
        op.execute(
            """
            CREATE POLICY tenant_isolation_audit_logs ON audit_logs
            USING (
                society_id IS NULL
                OR society_id = NULLIF(current_setting('app.current_society_id', true), '')::uuid
            );
            """
        )


def downgrade() -> None:
    # Drop tables in reverse foreign key order
    op.drop_table("audit_logs")
    op.drop_table("role_assignments")
    op.drop_table("role_permissions")
    op.drop_table("permissions")
    op.drop_table("roles")
    op.drop_table("resident_profiles")
    op.drop_table("unit_occupancies")
    op.drop_table("user_society_memberships")
    op.drop_table("units")
    op.drop_table("floors")
    op.drop_table("blocks")
    op.drop_table("societies")
    op.drop_table("users")
