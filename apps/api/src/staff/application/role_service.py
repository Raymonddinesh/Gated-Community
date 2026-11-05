"""Staff Role Application Service."""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.database.models.identity import User
from apps.api.src.database.models.staff import StaffRole, StaffRoleAssignment
from apps.api.src.staff.domain.exceptions import (
    StaffNotFoundError,
    StaffRoleNotFoundError,
)
from apps.api.src.staff.infrastructure.repositories import (
    StaffProfileRepository,
    StaffRoleRepository,
)
from apps.api.src.staff.schemas import StaffRoleCreateRequest


class StaffRoleService:
    """Application Service managing operational Staff Roles."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = StaffRoleRepository(session)
        self.staff_repo = StaffProfileRepository(session)

    async def create_staff_role(self, req: StaffRoleCreateRequest, society_id: uuid.UUID) -> StaffRole:
        """Create a new operational staff role."""
        role = StaffRole(
            society_id=society_id,
            name=req.name,
            code=req.code.upper(),
            description=req.description,
            display_order=req.display_order,
        )
        return await self.repo.create_role(role)

    async def list_staff_roles(self, society_id: uuid.UUID) -> list[StaffRole]:
        """List operational staff roles."""
        return await self.repo.list_roles(society_id)

    async def assign_role_to_staff(
        self,
        staff_id: uuid.UUID,
        role_id: uuid.UUID,
        society_id: uuid.UUID,
        is_primary: bool,
        assigned_by_user: User,
        reason: str | None = None,
    ) -> StaffRoleAssignment:
        """Assign an operational role to staff member."""
        staff = await self.staff_repo.get_by_id(staff_id, society_id)
        if not staff:
            raise StaffNotFoundError(str(staff_id))

        role = await self.repo.get_role_by_id(role_id, society_id)
        if not role:
            raise StaffRoleNotFoundError(str(role_id))

        assignment = StaffRoleAssignment(
            society_id=society_id,
            staff_id=staff.id,
            role_id=role.id,
            is_primary=is_primary,
            assigned_by_user_id=assigned_by_user.id,
            reason=reason,
        )

        if is_primary:
            staff.primary_role_id = role.id

        return await self.repo.assign_role(assignment)
