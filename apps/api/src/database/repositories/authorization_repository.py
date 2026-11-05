"""Repository for RBAC Roles, Permissions, and Assignments."""

import uuid
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.database.models.authorization import Permission, Role, RoleAssignment


class AuthorizationRepository:
    """Data access layer for roles, permissions, and assignments."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_user_roles(self, user_id: UUID, society_id: UUID | None = None) -> list[Role]:
        """
        Fetch active roles assigned to a user.
        Includes platform-scoped roles (society_id IS NULL) and matching society-scoped roles.
        """
        condition = (
            or_(
                RoleAssignment.society_id == society_id,
                RoleAssignment.society_id.is_(None),
            )
            if society_id
            else RoleAssignment.society_id.is_(None)
        )

        result = await self.session.execute(
            select(Role)
            .join(RoleAssignment, Role.id == RoleAssignment.role_id)
            .where(
                RoleAssignment.user_id == user_id,
                RoleAssignment.status == "ACTIVE",
                condition,
            )
        )
        return list(result.scalars().all())

    async def get_user_permission_codes(self, user_id: UUID, society_id: UUID | None = None) -> list[str]:
        """
        Resolve all distinct permission tokens for a user within a given society context.
        """
        roles = await self.get_user_roles(user_id, society_id)
        if not roles:
            return []

        role_ids = [role.id for role in roles]
        result = await self.session.execute(
            select(Permission.code).join(Role.permissions).where(Role.id.in_(role_ids)).distinct()
        )
        return list(result.scalars().all())

    async def get_role_by_code(self, code: str, scope_type: str = "SOCIETY") -> Role | None:
        """Fetch a role definition by code and scope."""
        result = await self.session.execute(
            select(Role).where(Role.code == code, Role.scope_type == scope_type)
        )
        return result.scalar_one_or_none()

    async def assign_role(
        self,
        user_id: UUID,
        role_id: UUID,
        society_id: UUID | None,
        scope_type: str = "SOCIETY",
    ) -> RoleAssignment:
        """Assign a role to a user within specified scope."""
        # Check if already assigned
        result = await self.session.execute(
            select(RoleAssignment).where(
                RoleAssignment.user_id == user_id,
                RoleAssignment.role_id == role_id,
                RoleAssignment.society_id == society_id,
            )
        )
        existing = result.scalar_one_or_none()
        if existing:
            if existing.status != "ACTIVE":
                existing.status = "ACTIVE"
                existing.revoked_at = None
                await self.session.flush()
            return existing

        assignment = RoleAssignment(
            id=uuid.uuid4(),
            user_id=user_id,
            role_id=role_id,
            society_id=society_id,
            scope_type=scope_type,
            status="ACTIVE",
            assigned_at=datetime.now(UTC),
        )
        self.session.add(assignment)
        await self.session.flush()
        return assignment

    async def revoke_role(
        self,
        user_id: UUID,
        role_id: UUID,
        society_id: UUID | None,
    ) -> None:
        """Revoke a role assignment."""
        await self.session.execute(
            update(RoleAssignment)
            .where(
                RoleAssignment.user_id == user_id,
                RoleAssignment.role_id == role_id,
                RoleAssignment.society_id == society_id,
                RoleAssignment.status == "ACTIVE",
            )
            .values(
                status="REVOKED",
                revoked_at=datetime.now(UTC),
            )
        )
