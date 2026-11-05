"""Phase 21A — Commercial SaaS Platform Administration & Subscription Models.

Revision ID: 0021_saas_platform_subscriptions
Revises: 0020_notifications_communication_delivery
Create Date: 2026-10-10
"""

import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0021_saas_platform_subscriptions"
down_revision: str | None = "0020_notifications_communication_delivery"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. platform_subscription_plans (Global Catalog)
    op.create_table(
        "platform_subscription_plans",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("plan_code", sa.String(50), nullable=False, unique=True),
        sa.Column("display_name", sa.String(100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("monthly_price", sa.Numeric(12, 2), nullable=False, server_default="0.00"),
        sa.Column("annual_price", sa.Numeric(12, 2), nullable=False, server_default="0.00"),
        sa.Column("currency_code", sa.String(3), nullable=False, server_default="INR"),
        sa.Column("trial_days", sa.Integer(), nullable=False, server_default="14"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
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
    op.create_index("ix_platform_subscription_plans_code", "platform_subscription_plans", ["plan_code"])

    # 2. subscription_plan_entitlements (Global Catalog Entitlements)
    op.create_table(
        "subscription_plan_entitlements",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "plan_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("platform_subscription_plans.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("entitlement_key", sa.String(100), nullable=False),
        sa.Column("entitlement_type", sa.String(20), nullable=False, server_default="BOOLEAN"),
        sa.Column("entitlement_value", sa.String(255), nullable=False),
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
        sa.UniqueConstraint("plan_id", "entitlement_key", name="uq_plan_entitlement_key"),
        sa.CheckConstraint(
            "entitlement_type IN ('BOOLEAN', 'NUMERIC', 'UNLIMITED')",
            name="ck_entitlement_type_valid",
        ),
    )
    op.create_index("ix_subscription_plan_entitlements_plan", "subscription_plan_entitlements", ["plan_id"])

    # 3. society_subscriptions (Tenant Subscription Lifecycle)
    op.create_table(
        "society_subscriptions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "society_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("societies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "plan_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("platform_subscription_plans.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("status", sa.String(30), nullable=False, server_default="TRIAL"),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("trial_ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("current_period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("current_period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("past_due_since", sa.DateTime(timezone=True), nullable=True),
        sa.Column("suspended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancellation_reason", sa.Text(), nullable=True),
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
        sa.UniqueConstraint("society_id", name="uq_society_subscriptions_society_id"),
    )
    op.create_index("ix_society_subscriptions_status", "society_subscriptions", ["society_id", "status"])

    # 4. society_feature_overrides (Tenant Specific Feature Overrides)
    op.create_table(
        "society_feature_overrides",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "society_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("societies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("feature_key", sa.String(100), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("override_reason", sa.Text(), nullable=False),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("effective_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_by",
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
        sa.UniqueConstraint("society_id", "feature_key", name="uq_society_feature_override_key"),
    )
    op.create_index(
        "ix_society_feature_overrides_lookup",
        "society_feature_overrides",
        ["society_id", "feature_key"],
    )

    # 5. society_quota_overrides (Tenant Specific Quota Overrides)
    op.create_table(
        "society_quota_overrides",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "society_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("societies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("quota_key", sa.String(100), nullable=False),
        sa.Column("max_limit", sa.Integer(), nullable=False),
        sa.Column("override_reason", sa.Text(), nullable=False),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("effective_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_by",
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
        sa.UniqueConstraint("society_id", "quota_key", name="uq_society_quota_override_key"),
        sa.CheckConstraint("max_limit >= 0", name="ck_society_quota_override_non_negative"),
    )

    # 6. society_usage_metrics (Atomic Persistent Counters)
    op.create_table(
        "society_usage_metrics",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "society_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("societies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("metric_key", sa.String(100), nullable=False),
        sa.Column("current_value", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_calculated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
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
        sa.UniqueConstraint("society_id", "metric_key", name="uq_society_usage_metric_key"),
        sa.CheckConstraint("current_value >= 0", name="ck_society_usage_metric_non_negative"),
    )

    # 7. society_provisioning_logs (Audit Trail for Provisioning)
    op.create_table(
        "society_provisioning_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "society_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("societies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("provisioning_request_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("step_key", sa.String(50), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="STARTED"),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("correlation_id", sa.String(100), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
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
    op.create_index("ix_society_provisioning_logs_request", "society_provisioning_logs", ["provisioning_request_id"])
    op.create_index(
        "ix_society_provisioning_logs_society",
        "society_provisioning_logs",
        ["society_id", "created_at"],
    )

    # Enable & Force RLS on tenant-owned tables
    tenant_tables = [
        "society_subscriptions",
        "society_feature_overrides",
        "society_quota_overrides",
        "society_usage_metrics",
        "society_provisioning_logs",
    ]

    for table in tenant_tables:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY;")
        op.execute(
            f"CREATE POLICY {table}_tenant_isolation ON {table} "
            f"USING (society_id = NULLIF(current_setting('app.current_society_id', true), '')::uuid);"
        )

    # Seed Reference Data (Deterministic Plan Tiers)
    plans_table = sa.sql.table(
        "platform_subscription_plans",
        sa.sql.column("id", postgresql.UUID(as_uuid=True)),
        sa.sql.column("plan_code", sa.String),
        sa.sql.column("display_name", sa.String),
        sa.sql.column("description", sa.Text),
        sa.sql.column("monthly_price", sa.Numeric),
        sa.sql.column("annual_price", sa.Numeric),
        sa.sql.column("currency_code", sa.String),
        sa.sql.column("trial_days", sa.Integer),
        sa.sql.column("is_active", sa.Boolean),
    )

    free_plan_id = uuid.UUID("11111111-1111-4111-8111-111111111111")
    standard_plan_id = uuid.UUID("22222222-2222-4222-8222-222222222222")
    enterprise_plan_id = uuid.UUID("33333333-3333-4333-8333-333333333333")

    op.bulk_insert(
        plans_table,
        [
            {
                "id": free_plan_id,
                "plan_code": "FREE",
                "display_name": "Free Tier",
                "description": "Basic management for small housing societies up to 50 units.",
                "monthly_price": 0.00,
                "annual_price": 0.00,
                "currency_code": "INR",
                "trial_days": 14,
                "is_active": True,
            },
            {
                "id": standard_plan_id,
                "plan_code": "STANDARD",
                "display_name": "Standard Tier",
                "description": "Standard management for mid-size societies up to 500 units.",
                "monthly_price": 1999.00,
                "annual_price": 19990.00,
                "currency_code": "INR",
                "trial_days": 14,
                "is_active": True,
            },
            {
                "id": enterprise_plan_id,
                "plan_code": "ENTERPRISE",
                "display_name": "Enterprise Tier",
                "description": "Unlimited management for large multi-block apartment complexes.",
                "monthly_price": 4999.00,
                "annual_price": 49990.00,
                "currency_code": "INR",
                "trial_days": 14,
                "is_active": True,
            },
        ],
    )

    # Seed Default Entitlements for FREE Plan
    entitlements_table = sa.sql.table(
        "subscription_plan_entitlements",
        sa.sql.column("id", postgresql.UUID(as_uuid=True)),
        sa.sql.column("plan_id", postgresql.UUID(as_uuid=True)),
        sa.sql.column("entitlement_key", sa.String),
        sa.sql.column("entitlement_type", sa.String),
        sa.sql.column("entitlement_value", sa.String),
    )

    op.bulk_insert(
        entitlements_table,
        [
            {
                "id": uuid.UUID("11111111-1111-4111-8111-111111111112"),
                "plan_id": free_plan_id,
                "entitlement_key": "quota.units.max",
                "entitlement_type": "NUMERIC",
                "entitlement_value": "50",
            },
            {
                "id": uuid.UUID("11111111-1111-4111-8111-111111111113"),
                "plan_id": free_plan_id,
                "entitlement_key": "feature.governance",
                "entitlement_type": "BOOLEAN",
                "entitlement_value": "false",
            },
            {
                "id": uuid.UUID("11111111-1111-4111-8111-111111111114"),
                "plan_id": free_plan_id,
                "entitlement_key": "feature.facility_booking",
                "entitlement_type": "BOOLEAN",
                "entitlement_value": "true",
            },
            {
                "id": uuid.UUID("11111111-1111-4111-8111-111111111115"),
                "plan_id": free_plan_id,
                "entitlement_key": "feature.maintenance_billing",
                "entitlement_type": "BOOLEAN",
                "entitlement_value": "true",
            },
        ],
    )


def downgrade() -> None:
    tenant_tables = [
        "society_provisioning_logs",
        "society_usage_metrics",
        "society_quota_overrides",
        "society_feature_overrides",
        "society_subscriptions",
    ]

    for table in tenant_tables:
        op.execute(f"DROP POLICY IF EXISTS {table}_tenant_isolation ON {table};")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY;")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;")

    all_tables = [
        "society_provisioning_logs",
        "society_usage_metrics",
        "society_quota_overrides",
        "society_feature_overrides",
        "society_subscriptions",
        "subscription_plan_entitlements",
        "platform_subscription_plans",
    ]

    for table in all_tables:
        op.drop_table(table)
