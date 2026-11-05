"""Global User Identity Model (Platform-Level)."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, Index, String
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from apps.api.src.database.base import ArchiveMixin, Base, TimestampMixin

if TYPE_CHECKING:
    from apps.api.src.database.models.authorization import RoleAssignment
    from apps.api.src.database.models.membership import (
        ResidentProfile,
        UnitOccupancy,
        UnitOwnership,
        UserSocietyMembership,
    )


class User(Base, TimestampMixin, ArchiveMixin):
    """
    Global Platform User Identity.
    Single identity across all societies; does NOT contain society-scoped data.
    """

    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(
            "email IS NOT NULL OR phone IS NOT NULL",
            name="ck_users_email_or_phone_required",
        ),
        Index("ix_users_email_lower", "email", unique=True, postgresql_where="email IS NOT NULL"),
        Index("ix_users_phone", "phone", unique=True, postgresql_where="phone IS NOT NULL"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    email: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    phone: Mapped[str | None] = mapped_column(
        String(32),
        nullable=True,
    )
    password_hash: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    first_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )
    last_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )
    display_name: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
    )
    preferred_language: Mapped[str] = mapped_column(
        String(10),
        default="en",
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(32),
        default="ACTIVE",
        nullable=False,
        index=True,
    )
    last_login_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Relationships
    memberships: Mapped[list["UserSocietyMembership"]] = relationship(
        "UserSocietyMembership",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    occupancies: Mapped[list["UnitOccupancy"]] = relationship(
        "UnitOccupancy",
        back_populates="user",
    )
    resident_profiles: Mapped[list["ResidentProfile"]] = relationship(
        "ResidentProfile",
        back_populates="user",
    )
    ownerships: Mapped[list["UnitOwnership"]] = relationship(
        "UnitOwnership",
        back_populates="user",
    )
    role_assignments: Mapped[list["RoleAssignment"]] = relationship(
        "RoleAssignment",
        back_populates="user",
    )
