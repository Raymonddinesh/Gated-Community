"""Tenant-Aware Append-Only Audit Log Foundation."""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from apps.api.src.database.base import Base


class AuditLog(Base):
    """
    Append-Only Audit Trail for All Critical State Changes.
    Captures actor, action, tenant context, and state diffs.
    Never modified or physically deleted.
    """

    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_logs_society_created", "society_id", "created_at"),
        Index("ix_audit_logs_entity", "entity_type", "entity_id"),
        Index("ix_audit_logs_actor", "actor_user_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    society_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("societies.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    action: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
    )
    entity_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
    )
    entity_id: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )
    request_id: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )
    correlation_id: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        index=True,
    )
    before_state: Mapped[dict[str, Any] | None] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"),
        nullable=True,
    )
    after_state: Mapped[dict[str, Any] | None] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"),
        nullable=True,
    )
    diff: Mapped[dict[str, Any] | None] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
        index=True,
    )
