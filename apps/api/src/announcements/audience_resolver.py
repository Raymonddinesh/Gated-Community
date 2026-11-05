"""Phase 16 Announcement Audience Resolver Service."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.announcements.enums import AudienceType, RoleFilter
from apps.api.src.announcements.exceptions import CrossTenantAudienceError, InvalidAudienceError
from apps.api.src.database.models.announcements import Announcement, AnnouncementAudience
from apps.api.src.database.models.membership import UnitOccupancy, UnitOwnership, UserSocietyMembership
from apps.api.src.database.models.society import Block, Floor, Unit


class AnnouncementAudienceResolver:
    """Domain resolver for audience targeting and eligibility checks."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def validate_audience_target_tenant(
        self,
        society_id: UUID,
        audience_type: AudienceType,
        target_block_id: UUID | None = None,
        target_floor_id: UUID | None = None,
        target_unit_id: UUID | None = None,
        target_user_id: UUID | None = None,
    ) -> None:
        """Verify all referenced hierarchy objects belong strictly to society_id."""
        if audience_type == AudienceType.BLOCK:
            if not target_block_id:
                raise InvalidAudienceError("target_block_id is required for BLOCK audience targeting")
            block_stmt = select(Block).where(Block.id == target_block_id, Block.society_id == society_id)
            if not (await self.db.execute(block_stmt)).scalar_one_or_none():
                raise CrossTenantAudienceError("Target block does not exist or belongs to another society")

        elif audience_type == AudienceType.FLOOR:
            if not target_floor_id:
                raise InvalidAudienceError("target_floor_id is required for FLOOR audience targeting")
            floor_stmt = (
                select(Floor).join(Block).where(Floor.id == target_floor_id, Block.society_id == society_id)
            )
            if not (await self.db.execute(floor_stmt)).scalar_one_or_none():
                raise CrossTenantAudienceError("Target floor does not exist or belongs to another society")

        elif audience_type == AudienceType.UNIT:
            if not target_unit_id:
                raise InvalidAudienceError("target_unit_id is required for UNIT audience targeting")
            unit_stmt = select(Unit).where(Unit.id == target_unit_id, Unit.society_id == society_id)
            if not (await self.db.execute(unit_stmt)).scalar_one_or_none():
                raise CrossTenantAudienceError("Target unit does not exist or belongs to another society")

        elif audience_type == AudienceType.RESIDENT:
            if not target_user_id:
                raise InvalidAudienceError("target_user_id is required for RESIDENT audience targeting")
            user_stmt = select(UserSocietyMembership).where(
                UserSocietyMembership.user_id == target_user_id,
                UserSocietyMembership.society_id == society_id,
            )
            if not (await self.db.execute(user_stmt)).scalar_one_or_none():
                raise CrossTenantAudienceError("Target resident does not belong to this society")

    async def is_user_eligible(
        self,
        society_id: UUID,
        announcement: Announcement,
        user_id: UUID,
        audiences: list[AnnouncementAudience],
    ) -> bool:
        """Check if user_id is eligible to view the announcement according to audience rules."""
        if not audiences:
            # Default: society-wide if no explicit audience rules defined
            return True

        for aud in audiences:
            aud_type = AudienceType(aud.audience_type)
            role_flt = RoleFilter(aud.role_filter) if aud.role_filter else RoleFilter.ALL

            if aud_type == AudienceType.SOCIETY:
                return True

            elif aud_type == AudienceType.RESIDENT:
                if aud.target_user_id == user_id:
                    return True

            elif aud_type == AudienceType.BLOCK:
                units_stmt = select(Unit.id).where(
                    Unit.society_id == society_id, Unit.block_id == aud.target_block_id
                )
                unit_ids = list((await self.db.execute(units_stmt)).scalars().all())
                if await self._user_has_unit_association(society_id, user_id, unit_ids, role_flt):
                    return True

            elif aud_type == AudienceType.FLOOR:
                units_stmt = select(Unit.id).where(
                    Unit.society_id == society_id, Unit.floor_id == aud.target_floor_id
                )
                unit_ids = list((await self.db.execute(units_stmt)).scalars().all())
                if await self._user_has_unit_association(society_id, user_id, unit_ids, role_flt):
                    return True

            elif aud_type == AudienceType.UNIT:
                if aud.target_unit_id and await self._user_has_unit_association(
                    society_id, user_id, [aud.target_unit_id], role_flt
                ):
                    return True

        return False

    async def _user_has_unit_association(
        self, society_id: UUID, user_id: UUID, unit_ids: list[UUID], role_filter: RoleFilter
    ) -> bool:
        if not unit_ids:
            return False

        if role_filter in (RoleFilter.ALL, RoleFilter.OWNER_ONLY):
            own_stmt = select(UnitOwnership).where(
                UnitOwnership.society_id == society_id,
                UnitOwnership.user_id == user_id,
                UnitOwnership.unit_id.in_(unit_ids),
                UnitOwnership.status == "ACTIVE",
            )
            if (await self.db.execute(own_stmt)).scalar_one_or_none():
                return True

        if role_filter in (RoleFilter.ALL, RoleFilter.TENANT_ONLY):
            occ_stmt = select(UnitOccupancy).where(
                UnitOccupancy.society_id == society_id,
                UnitOccupancy.user_id == user_id,
                UnitOccupancy.unit_id.in_(unit_ids),
                UnitOccupancy.status == "ACTIVE",
            )
            if (await self.db.execute(occ_stmt)).scalar_one_or_none():
                return True

        return False
