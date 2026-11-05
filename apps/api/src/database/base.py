"""SQLAlchemy 2.x Declarative Base and Common Model Metadata."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import ForeignKey, MetaData
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Standard naming conventions for constraints and indexes (critical for Alembic)
POSTGRES_NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy entities."""

    metadata = MetaData(naming_convention=POSTGRES_NAMING_CONVENTION)


class TimestampMixin:
    """Mixin for standardized creation and update timestamps (UTC)."""

    created_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(UTC).replace(tzinfo=None),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(UTC).replace(tzinfo=None),
        onupdate=lambda: datetime.now(UTC).replace(tzinfo=None),
        nullable=False,
    )


class ArchiveMixin:
    """Mixin for soft-archival without hard-deleting historical data."""

    archived_at: Mapped[datetime | None] = mapped_column(
        default=None,
        nullable=True,
    )

    @property
    def is_archived(self) -> bool:
        return self.archived_at is not None


class TenantScopedMixin:
    """Mixin for tenant-owned entities strictly bound to a Society."""

    society_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("societies.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
