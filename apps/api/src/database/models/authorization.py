"""Role-Based and Attribute-Based Authorization Models (RBAC Foundation)."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from apps.api.src.database.base import Base, TimestampMixin

if TYPE_CHECKING:
    from apps.api.src.database.models.identity import User
    from apps.api.src.database.models.society import Society


class Role(Base, TimestampMixin):
    """
    Authorization Role definition.
    Can be PLATFORM scoped (e.g. SUPER_ADMIN) or SOCIETY scoped (e.g. SECRETARY, RESIDENT).
    """

    __tablename__ = "roles"
    __table_args__ = (UniqueConstraint("code", "scope_type", name="uq_roles_code_scope"),)

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    code: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )
    scope_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="SOCIETY",
    )
    description: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    is_system_role: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    # Relationships
    permissions: Mapped[list["Permission"]] = relationship(
        "Permission",
        secondary="role_permissions",
        back_populates="roles",
    )
    assignments: Mapped[list["RoleAssignment"]] = relationship(
        "RoleAssignment",
        back_populates="role",
    )


class Permission(Base):
    """
    Granular action capability token (e.g., 'society.read', 'billing.manage').
    """

    __tablename__ = "permissions"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    code: Mapped[str] = mapped_column(
        String(100),
        unique=True,
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(
        String(150),
        nullable=False,
    )
    module: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
    )
    description: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        nullable=False,
    )

    # Relationships
    roles: Mapped[list["Role"]] = relationship(
        "Role",
        secondary="role_permissions",
        back_populates="permissions",
    )


class RolePermission(Base):
    """
    Many-to-many junction table associating Roles with Permissions.
    """

    __tablename__ = "role_permissions"

    role_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("roles.id", ondelete="CASCADE"),
        primary_key=True,
    )
    permission_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("permissions.id", ondelete="CASCADE"),
        primary_key=True,
    )


class RoleAssignment(Base, TimestampMixin):
    """
    Explicit assignment of a Role to a User with defined tenant scope.
    Platform roles have society_id = NULL.
    Society roles require a valid society_id.
    """

    __tablename__ = "role_assignments"
    __table_args__ = (
        CheckConstraint(
            "(scope_type = 'PLATFORM' AND society_id IS NULL) OR (scope_type = 'SOCIETY' AND society_id IS NOT NULL)",
            name="ck_role_assignments_scope_validity",
        ),
        Index("ix_role_assignments_user_society_role", "user_id", "role_id", "society_id", unique=True),
    )

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
    role_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("roles.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    society_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("societies.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    scope_type: Mapped[str] = mapped_column(
        String(20),
        default="SOCIETY",
        nullable=False,
    )
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        nullable=False,
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(
        String(32),
        default="ACTIVE",
        nullable=False,
        index=True,
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="role_assignments")
    role: Mapped["Role"] = relationship("Role", back_populates="assignments")
    society: Mapped[Optional["Society"]] = relationship("Society", back_populates="role_assignments")
