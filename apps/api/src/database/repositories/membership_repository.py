"""Repository for User Society Membership and Unit Occupancy."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.database.models.membership import (
    ResidentProfile,
    UnitOccupancy,
    UserSocietyMembership,
)


class MembershipRepository:
    """Data access layer for Membership, Occupancy, and Resident Profiles."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def verify_user_society_membership(self, user_id: UUID, society_id: UUID) -> bool:
        """
        Verify whether an authenticated user has an ACTIVE membership in the requested society.
        Fundamental gatekeeper for tenant context resolution.
        """
        result = await self.session.execute(
            select(UserSocietyMembership.id).where(
                UserSocietyMembership.user_id == user_id,
                UserSocietyMembership.society_id == society_id,
                UserSocietyMembership.membership_status == "ACTIVE",
            )
        )
        return result.scalar_one_or_none() is not None

    async def get_membership(self, user_id: UUID, society_id: UUID) -> UserSocietyMembership | None:
        """Fetch full membership record."""
        result = await self.session.execute(
            select(UserSocietyMembership).where(
                UserSocietyMembership.user_id == user_id,
                UserSocietyMembership.society_id == society_id,
            )
        )
        return result.scalar_one_or_none()

    async def create_membership(
        self,
        user_id: UUID,
        society_id: UUID,
        status: str = "ACTIVE",
    ) -> UserSocietyMembership:
        """Create or reactivate a membership."""
        existing = await self.get_membership(user_id, society_id)
        if existing:
            if existing.membership_status != status:
                existing.membership_status = status
                await self.session.flush()
            return existing

        import uuid as _uuid

        membership = UserSocietyMembership(
            id=_uuid.uuid4(),
            user_id=user_id,
            society_id=society_id,
            membership_status=status,
        )
        self.session.add(membership)
        await self.session.flush()
        return membership

    async def list_user_societies(self, user_id: UUID) -> list[UUID]:
        """Retrieve all active society IDs a user belongs to."""
        result = await self.session.execute(
            select(UserSocietyMembership.society_id).where(
                UserSocietyMembership.user_id == user_id,
                UserSocietyMembership.membership_status == "ACTIVE",
            )
        )
        return list(result.scalars().all())

    async def get_unit_occupancies(self, unit_id: UUID, society_id: UUID) -> list[UnitOccupancy]:
        """Fetch current and historical occupancies for a specific unit."""
        result = await self.session.execute(
            select(UnitOccupancy).where(
                UnitOccupancy.unit_id == unit_id,
                UnitOccupancy.society_id == society_id,
            )
        )
        return list(result.scalars().all())

    async def get_resident_profile(self, user_id: UUID, society_id: UUID) -> ResidentProfile | None:
        """Fetch localized resident profile preferences."""
        result = await self.session.execute(
            select(ResidentProfile).where(
                ResidentProfile.user_id == user_id,
                ResidentProfile.society_id == society_id,
                ResidentProfile.archived_at.is_(None),
            )
        )
        return result.scalar_one_or_none()
