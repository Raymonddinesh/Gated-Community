"""Phase 21E.6 — SaaS Billing Automation & Dunning Execution Schema.

Revision ID: 0025_saas_billing_automation
Revises: 0024_saas_billing_documents
Create Date: 2026-11-02 22:25:00.000000

Adds platform-wide job execution tracking and tenant-isolated dunning audit ledger:
1. platform_billing_job_runs:
   - Global platform operational ledger tracking batch execution runs.
   - Status, duration, itemized processed/succeeded/failed counters, error summaries.
   - Platform-internal table (not tenant-scoped).
2. platform_dunning_attempts:
   - Tenant-scoped dunning execution and retry audit ledger.
   - Scoped to society_id with PostgreSQL 16 FORCE ROW LEVEL SECURITY.
   - Idempotency key, scheduled/executed timestamps, retry counts, gateway references.
3. Subscription & Billing Period Idempotency Invariants:
   - Partial unique index on platform_invoices (subscription_id, period_start, period_end) WHERE status != 'VOID' AND period_start < period_end.
   - Optional idempotency_key column on platform_invoices with unique partial index.
   - Composite scheduler index on society_subscriptions (status, auto_renew, next_billing_at).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0025_saas_billing_automation"
down_revision: str | None = "0024_saas_billing_documents"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # =========================================================================
    # 1. Create Global Table: platform_billing_job_runs
    # =========================================================================
    op.create_table(
        "platform_billing_job_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("job_type", sa.String(50), nullable=False),
        sa.Column("execution_id", sa.String(100), nullable=False),
        sa.Column(
            "status",
            sa.String(30),
            nullable=False,
            server_default="RUNNING",
        ),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "processed_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "succeeded_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "failed_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "skipped_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column("error_summary", sa.Text(), nullable=True),
        sa.Column("diagnostics", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
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
        sa.UniqueConstraint("execution_id", name="uq_platform_billing_job_runs_exec_id"),
        sa.CheckConstraint(
            "status IN ('RUNNING', 'COMPLETED', 'FAILED', 'PARTIAL')",
            name="ck_platform_billing_job_runs_status",
        ),
        sa.CheckConstraint(
            "processed_count >= 0",
            name="ck_platform_billing_job_runs_processed_non_negative",
        ),
        sa.CheckConstraint(
            "succeeded_count >= 0",
            name="ck_platform_billing_job_runs_succeeded_non_negative",
        ),
        sa.CheckConstraint(
            "failed_count >= 0",
            name="ck_platform_billing_job_runs_failed_non_negative",
        ),
        sa.CheckConstraint(
            "skipped_count >= 0",
            name="ck_platform_billing_job_runs_skipped_non_negative",
        ),
    )
    op.create_index(
        "ix_platform_billing_job_runs_type_status",
        "platform_billing_job_runs",
        ["job_type", "status"],
    )
    op.create_index(
        "ix_platform_billing_job_runs_started_at",
        "platform_billing_job_runs",
        ["started_at"],
    )

    # =========================================================================
    # 2. Create Tenant Table: platform_dunning_attempts
    # =========================================================================
    op.create_table(
        "platform_dunning_attempts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "society_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("societies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "subscription_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("society_subscriptions.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "invoice_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("platform_invoices.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("attempt_type", sa.String(50), nullable=False),
        sa.Column(
            "status",
            sa.String(30),
            nullable=False,
            server_default="PENDING",
        ),
        sa.Column("idempotency_key", sa.String(150), nullable=False),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "retry_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column("grace_days_remaining", sa.Integer(), nullable=True),
        sa.Column("provider_reference", sa.String(100), nullable=True),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("idempotency_key", name="uq_platform_dunning_attempts_idempotency"),
        sa.CheckConstraint(
            "status IN ('PENDING', 'PROCESSING', 'SUCCEEDED', 'FAILED', 'SKIPPED')",
            name="ck_platform_dunning_attempts_status",
        ),
        sa.CheckConstraint(
            "retry_count >= 0",
            name="ck_platform_dunning_attempts_retry_non_negative",
        ),
    )
    op.create_index(
        "ix_platform_dunning_attempts_society_sub",
        "platform_dunning_attempts",
        ["society_id", "subscription_id"],
    )
    op.create_index(
        "ix_platform_dunning_attempts_society_status",
        "platform_dunning_attempts",
        ["society_id", "status"],
    )
    op.create_index(
        "ix_platform_dunning_attempts_invoice",
        "platform_dunning_attempts",
        ["invoice_id"],
    )
    op.create_index(
        "ix_platform_dunning_attempts_scheduled",
        "platform_dunning_attempts",
        ["scheduled_at"],
    )

    op.execute("ALTER TABLE platform_dunning_attempts ENABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE platform_dunning_attempts FORCE ROW LEVEL SECURITY;")
    op.execute(
        "CREATE POLICY platform_dunning_attempts_tenant_isolation ON platform_dunning_attempts "
        "USING (society_id = NULLIF(current_setting('app.current_society_id', true), '')::uuid);"
    )

    # =========================================================================
    # 3. Add Idempotency Invariants & Scheduler Indexes to Existing Tables
    # =========================================================================
    # 3a. Add idempotency_key to platform_invoices
    op.add_column(
        "platform_invoices",
        sa.Column("idempotency_key", sa.String(150), nullable=True),
    )
    op.create_index(
        "ix_platform_invoices_idempotency_key",
        "platform_invoices",
        ["idempotency_key"],
        unique=True,
        postgresql_where=sa.text("idempotency_key IS NOT NULL"),
    )

    # 3b. Partial unique index ensuring zero duplicate non-VOID invoices per billing period
    op.create_index(
        "uq_platform_invoices_sub_period",
        "platform_invoices",
        ["subscription_id", "period_start", "period_end"],
        unique=True,
        postgresql_where=sa.text("status != 'VOID' AND period_start < period_end"),
    )

    # 3c. Composite index on society_subscriptions for lock-efficient batch selection
    op.create_index(
        "ix_society_subscriptions_sched_roll",
        "society_subscriptions",
        ["status", "auto_renew", "next_billing_at"],
    )


def downgrade() -> None:
    # 3. Drop Invariants & Scheduler Indexes
    op.drop_index(
        "ix_society_subscriptions_sched_roll",
        table_name="society_subscriptions",
    )
    op.drop_index(
        "uq_platform_invoices_sub_period",
        table_name="platform_invoices",
        postgresql_where=sa.text("status != 'VOID' AND period_start < period_end"),
    )
    op.drop_index(
        "ix_platform_invoices_idempotency_key",
        table_name="platform_invoices",
        postgresql_where=sa.text("idempotency_key IS NOT NULL"),
    )
    op.drop_column("platform_invoices", "idempotency_key")

    # 2. Drop Tenant Table: platform_dunning_attempts
    op.execute("DROP POLICY IF EXISTS platform_dunning_attempts_tenant_isolation ON platform_dunning_attempts;")
    op.drop_table("platform_dunning_attempts")

    # 1. Drop Global Table: platform_billing_job_runs
    op.drop_table("platform_billing_job_runs")
