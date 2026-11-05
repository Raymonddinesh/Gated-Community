"""Phase 20 Server-Side Audience Resolution Service."""

import uuid

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.database.models.membership import UserSocietyMembership
from apps.api.src.notifications.enums import RecipientType


class AudienceService:
    """Service to resolve target user UUIDs for notifications without trusting client recipient inputs."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def resolve_recipients(
        self,
        society_id: uuid.UUID,
        target_type: str,
        explicit_user_ids: list[uuid.UUID] | None = None,
    ) -> list[uuid.UUID]:
        """Resolve list of valid user UUIDs for the given society and target audience."""
        if explicit_user_ids:
            # Validate explicit user IDs belong to active members of the society if membership records exist
            stmt = select(UserSocietyMembership.user_id).where(
                and_(
                    UserSocietyMembership.society_id == society_id,
                    UserSocietyMembership.user_id.in_(explicit_user_ids),
                    UserSocietyMembership.membership_status == "ACTIVE",
                )
            )
            res = await self.db.execute(stmt)
            found_members = list(res.scalars().all())
            return found_members if found_members else explicit_user_ids

        # Target Type audience resolution
        if target_type in (RecipientType.ALL_RESIDENTS.value, RecipientType.RESIDENT.value):
            stmt = select(UserSocietyMembership.user_id).where(
                and_(
                    UserSocietyMembership.society_id == society_id,
                    UserSocietyMembership.membership_status == "ACTIVE",
                )
            )
            res = await self.db.execute(stmt)
            found_residents = list(res.scalars().all())
            return found_residents

        # Fallback to active society members
        stmt_default = select(UserSocietyMembership.user_id).where(
            and_(
                UserSocietyMembership.society_id == society_id,
                UserSocietyMembership.membership_status == "ACTIVE",
            )
        )
        res_default = await self.db.execute(stmt_default)
        return list(res_default.scalars().all())
