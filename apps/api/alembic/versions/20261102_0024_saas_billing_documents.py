"""Phase 21E.4D — SaaS Billing Document Storage & Email Delivery Schema.

Revision ID: 0024_saas_billing_documents
Revises: 0023_saas_credit_notes
Create Date: 2026-11-02 14:45:00.000000

Adds tenant-isolated document storage registry and reliable email delivery tracking:
1. platform_billing_documents:
   - Stores metadata, private storage keys, SHA-256 integrity checksums for generated PDFs.
   - Scoped to society_id with PostgreSQL 16 FORCE ROW LEVEL SECURITY.
   - Enforces unique document number and composite (society_id, document_type, document_id).
2. platform_document_deliveries:
   - Tracks idempotent email delivery states (QUEUED, PROCESSING, SENT, FAILED, RETRYING).
   - Scoped to society_id with PostgreSQL 16 FORCE ROW LEVEL SECURITY.
3. platform_document_delivery_attempts:
   - Transactional attempt history recording every provider dispatch attempt, latency, and status.
   - Scoped to society_id with PostgreSQL 16 FORCE ROW LEVEL SECURITY.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0024_saas_billing_documents"
down_revision: str | None = "0023_saas_credit_notes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # =========================================================================
    # 1. Create Tenant Table: platform_billing_documents
    # =========================================================================
    op.create_table(
        "platform_billing_documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "society_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("societies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("document_type", sa.String(30), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_number", sa.String(50), nullable=False),
        sa.Column("storage_key", sa.String(500), nullable=False),
        sa.Column("sha256_checksum", sa.String(64), nullable=False),
        sa.Column("file_size_bytes", sa.Integer(), nullable=False),
        sa.Column(
            "content_type",
            sa.String(50),
            nullable=False,
            server_default="application/pdf",
        ),
        sa.Column(
            "generated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.UniqueConstraint(
            "society_id",
            "document_type",
            "document_id",
            name="uq_platform_billing_docs_tenant_entity",
        ),
        sa.UniqueConstraint(
            "document_type",
            "document_number",
            name="uq_platform_billing_docs_number",
        ),
        sa.CheckConstraint(
            "document_type IN ('INVOICE', 'CREDIT_NOTE')",
            name="ck_platform_billing_docs_type",
        ),
        sa.CheckConstraint(
            "file_size_bytes > 0",
            name="ck_platform_billing_docs_file_size_positive",
        ),
    )
    op.create_index(
        "ix_platform_billing_docs_society_type",
        "platform_billing_documents",
        ["society_id", "document_type"],
    )
    op.create_index(
        "ix_platform_billing_docs_doc_id",
        "platform_billing_documents",
        ["document_id"],
    )
    op.create_index(
        "ix_platform_billing_docs_checksum",
        "platform_billing_documents",
        ["sha256_checksum"],
    )

    op.execute("ALTER TABLE platform_billing_documents ENABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE platform_billing_documents FORCE ROW LEVEL SECURITY;")
    op.execute(
        "CREATE POLICY platform_billing_documents_tenant_isolation ON platform_billing_documents "
        "USING (society_id = NULLIF(current_setting('app.current_society_id', true), '')::uuid);"
    )

    # =========================================================================
    # 2. Create Tenant Table: platform_document_deliveries
    # =========================================================================
    op.create_table(
        "platform_document_deliveries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "society_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("societies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "document_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("platform_billing_documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("channel", sa.String(20), nullable=False, server_default="EMAIL"),
        sa.Column("recipient_email", sa.String(255), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="QUEUED"),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("provider_message_id", sa.String(255), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.UniqueConstraint(
            "idempotency_key",
            name="uq_platform_document_deliveries_idempotency",
        ),
        sa.CheckConstraint(
            "channel IN ('EMAIL', 'WEBHOOK')",
            name="ck_platform_document_deliveries_channel",
        ),
        sa.CheckConstraint(
            "status IN ('QUEUED', 'PROCESSING', 'SENT', 'FAILED', 'RETRYING')",
            name="ck_platform_document_deliveries_status",
        ),
        sa.CheckConstraint(
            "attempt_count >= 0",
            name="ck_platform_document_deliveries_attempt_non_negative",
        ),
    )
    op.create_index(
        "ix_platform_document_deliveries_society_status",
        "platform_document_deliveries",
        ["society_id", "status"],
    )
    op.create_index(
        "ix_platform_document_deliveries_doc_id",
        "platform_document_deliveries",
        ["document_id"],
    )

    op.execute("ALTER TABLE platform_document_deliveries ENABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE platform_document_deliveries FORCE ROW LEVEL SECURITY;")
    op.execute(
        "CREATE POLICY platform_document_deliveries_tenant_isolation ON platform_document_deliveries "
        "USING (society_id = NULLIF(current_setting('app.current_society_id', true), '')::uuid);"
    )

    # =========================================================================
    # 3. Create Tenant Table: platform_document_delivery_attempts
    # =========================================================================
    op.create_table(
        "platform_document_delivery_attempts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "society_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("societies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "delivery_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("platform_document_deliveries.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("provider_name", sa.String(50), nullable=False),
        sa.Column("provider_response_code", sa.String(50), nullable=True),
        sa.Column("provider_request_id", sa.String(255), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint(
            "delivery_id",
            "attempt_number",
            name="uq_platform_delivery_attempts_num",
        ),
        sa.CheckConstraint(
            "attempt_number > 0",
            name="ck_platform_delivery_attempts_num_positive",
        ),
        sa.CheckConstraint(
            "status IN ('SUCCESS', 'FAILURE')",
            name="ck_platform_delivery_attempts_status",
        ),
    )
    op.create_index(
        "ix_platform_delivery_attempts_society",
        "platform_document_delivery_attempts",
        ["society_id"],
    )
    op.create_index(
        "ix_platform_delivery_attempts_delivery_id",
        "platform_document_delivery_attempts",
        ["delivery_id"],
    )

    op.execute("ALTER TABLE platform_document_delivery_attempts ENABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE platform_document_delivery_attempts FORCE ROW LEVEL SECURITY;")
    op.execute(
        "CREATE POLICY platform_document_delivery_attempts_tenant_isolation ON platform_document_delivery_attempts "
        "USING (society_id = NULLIF(current_setting('app.current_society_id', true), '')::uuid);"
    )


def downgrade() -> None:
    # 1. Drop platform_document_delivery_attempts
    op.execute(
        "DROP POLICY IF EXISTS platform_document_delivery_attempts_tenant_isolation ON platform_document_delivery_attempts;"
    )
    op.execute("ALTER TABLE platform_document_delivery_attempts NO FORCE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE platform_document_delivery_attempts DISABLE ROW LEVEL SECURITY;")
    op.drop_table("platform_document_delivery_attempts")

    # 2. Drop platform_document_deliveries
    op.execute(
        "DROP POLICY IF EXISTS platform_document_deliveries_tenant_isolation ON platform_document_deliveries;"
    )
    op.execute("ALTER TABLE platform_document_deliveries NO FORCE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE platform_document_deliveries DISABLE ROW LEVEL SECURITY;")
    op.drop_table("platform_document_deliveries")

    # 3. Drop platform_billing_documents
    op.execute(
        "DROP POLICY IF EXISTS platform_billing_documents_tenant_isolation ON platform_billing_documents;"
    )
    op.execute("ALTER TABLE platform_billing_documents NO FORCE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE platform_billing_documents DISABLE ROW LEVEL SECURITY;")
    op.drop_table("platform_billing_documents")
