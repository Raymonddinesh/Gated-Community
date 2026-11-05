"""Society and Physical Spatial Hierarchy Models (Society -> Block -> Floor -> Unit)."""

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from apps.api.src.database.base import ArchiveMixin, Base, TenantScopedMixin, TimestampMixin

if TYPE_CHECKING:
    from apps.api.src.database.models.authorization import RoleAssignment
    from apps.api.src.database.models.membership import (
        ResidentDelegate,
        ResidentFamilyMember,
        ResidentProfile,
        UnitOccupancy,
        UnitOwnership,
        UserSocietyMembership,
    )


class Society(Base, TimestampMixin, ArchiveMixin):
    """
    Primary Tenant Boundary.
    Represents an independent housing cooperative or apartment society.
    """

    __tablename__ = "societies"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    legal_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    display_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    registration_number: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        index=True,
    )
    address_line1: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    address_line2: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    city: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )
    state: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )
    country: Mapped[str] = mapped_column(
        String(10),
        default="IN",
        nullable=False,
    )
    postal_code: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )
    timezone: Mapped[str] = mapped_column(
        String(50),
        default="Asia/Kolkata",
        nullable=False,
    )
    default_language: Mapped[str] = mapped_column(
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
    onboarding_status: Mapped[str] = mapped_column(
        String(32),
        default="COMPLETED",
        nullable=False,
    )

    # Relationships
    blocks: Mapped[list["Block"]] = relationship(
        "Block",
        back_populates="society",
        cascade="all, delete-orphan",
    )
    memberships: Mapped[list["UserSocietyMembership"]] = relationship(
        "UserSocietyMembership",
        back_populates="society",
        cascade="all, delete-orphan",
    )
    role_assignments: Mapped[list["RoleAssignment"]] = relationship(
        "RoleAssignment",
        back_populates="society",
    )
    resident_profiles: Mapped[list["ResidentProfile"]] = relationship(
        "ResidentProfile",
        back_populates="society",
    )


class Block(Base, TimestampMixin, ArchiveMixin, TenantScopedMixin):
    """
    Physical Building or Wing within a Society.
    """

    __tablename__ = "blocks"
    __table_args__ = (UniqueConstraint("society_id", "code", name="uq_blocks_society_code"),)

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    code: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )
    display_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )
    sequence_order: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(32),
        default="ACTIVE",
        nullable=False,
    )

    # Relationships
    society: Mapped["Society"] = relationship("Society", back_populates="blocks")
    floors: Mapped[list["Floor"]] = relationship(
        "Floor",
        back_populates="block",
        cascade="all, delete-orphan",
    )
    units: Mapped[list["Unit"]] = relationship(
        "Unit",
        back_populates="block",
    )


class Floor(Base, TimestampMixin, ArchiveMixin, TenantScopedMixin):
    """
    Vertical Level within a Block.
    """

    __tablename__ = "floors"
    __table_args__ = (
        UniqueConstraint("society_id", "block_id", "floor_number", name="uq_floors_block_number"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    block_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("blocks.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    floor_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    display_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )
    sequence_order: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(32),
        default="ACTIVE",
        nullable=False,
    )

    # Relationships
    block: Mapped["Block"] = relationship("Block", back_populates="floors")
    units: Mapped[list["Unit"]] = relationship(
        "Unit",
        back_populates="floor",
        cascade="all, delete-orphan",
    )


class Unit(Base, TimestampMixin, ArchiveMixin, TenantScopedMixin):
    """
    Individual Residential Apartment, Flat, or Commercial Space.
    """

    __tablename__ = "units"
    __table_args__ = (
        UniqueConstraint("society_id", "block_id", "unit_number", name="uq_units_society_block_number"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    block_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("blocks.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    floor_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("floors.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    unit_number: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )
    unit_type: Mapped[str] = mapped_column(
        String(50),
        default="2BHK",
        nullable=False,
    )
    carpet_area_sqft: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )
    occupancy_status: Mapped[str] = mapped_column(
        String(32),
        default="VACANT",
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(32),
        default="ACTIVE",
        nullable=False,
    )

    # Relationships
    block: Mapped["Block"] = relationship("Block", back_populates="units")
    floor: Mapped["Floor"] = relationship("Floor", back_populates="units")
    occupancies: Mapped[list["UnitOccupancy"]] = relationship(
        "UnitOccupancy",
        back_populates="unit",
    )
    ownerships: Mapped[list["UnitOwnership"]] = relationship(
        "UnitOwnership",
        back_populates="unit",
    )
    family_members: Mapped[list["ResidentFamilyMember"]] = relationship(
        "ResidentFamilyMember",
        back_populates="unit",
    )
    delegates: Mapped[list["ResidentDelegate"]] = relationship(
        "ResidentDelegate",
        back_populates="unit",
    )
