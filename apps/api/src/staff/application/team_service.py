"""Staff Team Application Service."""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.database.models.identity import User
from apps.api.src.database.models.staff import StaffTeam, StaffTeamMembership
from apps.api.src.staff.domain.exceptions import (
    StaffNotFoundError,
    StaffTeamNotFoundError,
)
from apps.api.src.staff.infrastructure.repositories import (
    StaffProfileRepository,
    StaffTeamRepository,
)
from apps.api.src.staff.schemas import StaffTeamCreateRequest


class StaffTeamService:
    """Application Service managing operational Staff Teams."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = StaffTeamRepository(session)
        self.staff_repo = StaffProfileRepository(session)

    async def create_staff_team(self, req: StaffTeamCreateRequest, society_id: uuid.UUID) -> StaffTeam:
        """Create a new staff team."""
        team = StaffTeam(
            society_id=society_id,
            name=req.name,
            code=req.code.upper(),
            description=req.description,
        )
        return await self.repo.create_team(team)

    async def list_staff_teams(self, society_id: uuid.UUID) -> list[StaffTeam]:
        """List active staff teams."""
        return await self.repo.list_teams(society_id)

    async def add_staff_to_team(
        self,
        staff_id: uuid.UUID,
        team_id: uuid.UUID,
        society_id: uuid.UUID,
        is_primary: bool,
        assigned_by_user: User,
    ) -> StaffTeamMembership:
        """Add staff to a team."""
        staff = await self.staff_repo.get_by_id(staff_id, society_id)
        if not staff:
            raise StaffNotFoundError(str(staff_id))

        team = await self.repo.get_team_by_id(team_id, society_id)
        if not team:
            raise StaffTeamNotFoundError(str(team_id))

        membership = StaffTeamMembership(
            society_id=society_id,
            staff_id=staff.id,
            team_id=team.id,
            is_primary=is_primary,
            assigned_by_user_id=assigned_by_user.id,
        )
        return await self.repo.add_membership(membership)
