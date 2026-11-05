"""Membership, Unit Occupancy, Resident Profile, Ownership, Family and Delegate Models."""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Optional

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.orm import relationship as sa_relationship

from apps.api.src.database.base import ArchiveMixin, Base, TenantScopedMixin, TimestampMixin

if TYPE_CHECKING:
    from apps.api.src.database.models.identity import User
    from apps.api.src.database.models.society import Society, Unit


class UserSocietyMembership(Base, TimestampMixin):
    """
    Core association between a User and a Society.
    User != Membership: A single global User may hold memberships across multiple societies.
    """

    __tablename__ = "user_society_memberships"
    __table_args__ = (UniqueConstraint("user_id", "society_id", name="uq_membership_user_society"),)

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    society_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("societies.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    membership_status: Mapped[str] = mapped_column(
        String(32),
        default="ACTIVE",
        nullable=False,
        index=True,
    )
    joined_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    activated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    deactivated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Relationships
    user: Mapped["User"] = sa_relationship("User", back_populates="memberships")
    society: Mapped["Society"] = sa_relationship("Society", back_populates="memberships")


class UnitOccupancy(Base, TimestampMixin, TenantScopedMixin):
    """
    Relationship between a Person and a specific Unit.
    Represents Owner, Tenant, Family Member, or Authorized Delegate.
    Historical occupancies are preserved; records are never overwritten.
    """

    __tablename__ = "unit_occupancies"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    unit_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("units.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    relationship_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        index=True,
    )
    is_primary_contact: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )
    valid_from: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
    )
    valid_to: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
    )
    status: Mapped[str] = mapped_column(
        String(32),
        default="ACTIVE",
        nullable=False,
        index=True,
    )
    notes: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    # Relationships
    unit: Mapped["Unit"] = sa_relationship("Unit", back_populates="occupancies")
    user: Mapped["User"] = sa_relationship("User", back_populates="occupancies")


class ResidentProfile(Base, TimestampMixin, ArchiveMixin, TenantScopedMixin):
    """
    Society-specific preferences and contact metadata for a resident.
    Separates localized preferences (e.g., Easy Mode, vernacular language) from global identity.
    """

    __tablename__ = "resident_profiles"
    __table_args__ = (UniqueConstraint("user_id", "society_id", name="uq_resident_profile_user_society"),)

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    emergency_contact_name: Mapped[str | None] = mapped_column(
        String(150),
        nullable=True,
    )
    emergency_contact_phone: Mapped[str | None] = mapped_column(
        String(32),
        nullable=True,
    )
    alternate_phone: Mapped[str | None] = mapped_column(
        String(32),
        nullable=True,
    )
    preferred_contact_method: Mapped[str] = mapped_column(
        String(32),
        default="APP",
        nullable=False,
    )
    preferred_language: Mapped[str] = mapped_column(
        String(10),
        default="en",
        nullable=False,
    )
    accessibility_preferences: Mapped[dict[str, Any]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"),
        default=dict,
        nullable=False,
    )
    communication_preferences: Mapped[dict[str, Any]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"),
        default=dict,
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(32),
        default="ACTIVE",
        nullable=False,
        index=True,
    )
    notes: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    # Relationships
    user: Mapped["User"] = sa_relationship("User", back_populates="resident_profiles")
    society: Mapped["Society"] = sa_relationship("Society", back_populates="resident_profiles")


class UnitOwnership(Base, TimestampMixin, TenantScopedMixin):
    """
    Legal or beneficial ownership record for a specific Unit within a Society.
    Supports single owner and joint co-owners with percentage validation.
    Historical ownership transitions are preserved; records are never deleted.
    """

    __tablename__ = "unit_ownerships"
    __table_args__ = (
        CheckConstraint(
            "ownership_percentage > 0 AND ownership_percentage <= 100",
            name="ck_unit_ownership_percentage",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    unit_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("units.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    ownership_percentage: Mapped[Decimal] = mapped_column(
        Numeric(5, 2),
        default=Decimal("100.00"),
        nullable=False,
    )
    start_date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
    )
    end_date: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
    )
    is_primary: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(32),
        default="ACTIVE",
        nullable=False,
        index=True,
    )
    notes: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    # Relationships
    unit: Mapped["Unit"] = sa_relationship("Unit", back_populates="ownerships")
    user: Mapped["User"] = sa_relationship("User", back_populates="ownerships")


class ResidentFamilyMember(Base, TimestampMixin, TenantScopedMixin):
    """
    Family relationship attached to a primary resident and unit.
    Supports Spouse, Child, Parent, Sibling, Other with restricted access scopes.
    """

    __tablename__ = "resident_family_members"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    unit_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("units.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    primary_resident_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    name: Mapped[str] = mapped_column(
        String(150),
        nullable=False,
    )
    relationship: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )
    phone: Mapped[str | None] = mapped_column(
        String(32),
        nullable=True,
    )
    email: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    access_scope: Mapped[dict[str, Any]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"),
        default=dict,
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(32),
        default="ACTIVE",
        nullable=False,
        index=True,
    )

    # Relationships
    unit: Mapped["Unit"] = sa_relationship("Unit", back_populates="family_members")
    primary_resident: Mapped["User"] = sa_relationship("User", foreign_keys=[primary_resident_user_id])
    user: Mapped[Optional["User"]] = sa_relationship("User", foreign_keys=[user_id])


class ResidentDelegate(Base, TimestampMixin, TenantScopedMixin):
    """
    Authorized delegate acting on behalf of an owner or tenant for designated unit scopes.
    Permissions are explicit, time-bound, revocable, and auditable.
    """

    __tablename__ = "resident_delegates"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    unit_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("units.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    delegator_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    delegate_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    permissions: Mapped[list[str]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"),
        default=list,
        nullable=False,
    )
    valid_from: Mapped[date] = mapped_column(
        Date,
        nullable=False,
    )
    valid_to: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
    )
    status: Mapped[str] = mapped_column(
        String(32),
        default="ACTIVE",
        nullable=False,
        index=True,
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    revoked_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=True,
    )
    revocation_reason: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    notes: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    # Relationships
    unit: Mapped["Unit"] = sa_relationship("Unit", back_populates="delegates")
    delegator: Mapped["User"] = sa_relationship("User", foreign_keys=[delegator_user_id])
    delegate: Mapped["User"] = sa_relationship("User", foreign_keys=[delegate_user_id])
