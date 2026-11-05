"""Staff Profile Application Service."""

import uuid
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.database.models.identity import User
from apps.api.src.database.models.staff import (
    StaffContact,
    StaffProfile,
    StaffStatusHistory,
)
from apps.api.src.staff.domain.enums import StaffStatus
from apps.api.src.staff.domain.exceptions import (
    StaffNotFoundError,
    StaffRoleNotFoundError,
)
from apps.api.src.staff.domain.state_machine import StaffStatusStateMachine
from apps.api.src.staff.infrastructure.repositories import (
    StaffProfileRepository,
    StaffRoleRepository,
)
from apps.api.src.staff.schemas import (
    StaffProfileCreateRequest,
    StaffProfileUpdateRequest,
    StaffStatusUpdateRequest,
)


class StaffProfileService:
    """Application Service managing Staff Profile creation, updates, and state machine transitions."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = StaffProfileRepository(session)
        self.role_repo = StaffRoleRepository(session)

    async def create_staff_profile(
        self,
        req: StaffProfileCreateRequest,
        society_id: uuid.UUID,
        created_by_user: User,
    ) -> StaffProfile:
        """Create a new operational staff profile."""
        # 1. Validate primary role if provided
        if req.primary_role_id:
            role = await self.role_repo.get_role_by_id(req.primary_role_id, society_id)
            if not role:
                raise StaffRoleNotFoundError(str(req.primary_role_id))

        # 2. Generate sequential staff code STF-YYYY-XXXXXX
        year = datetime.utcnow().year
        staff_code = await self.repo.generate_next_staff_code(society_id, year)

        display_name = f"{req.first_name} {req.last_name}"

        # 3. Instantiate ORM models
        staff = StaffProfile(
            society_id=society_id,
            user_id=req.user_id,
            staff_code=staff_code,
            first_name=req.first_name,
            middle_name=req.middle_name,
            last_name=req.last_name,
            display_name=display_name,
            preferred_name=req.preferred_name,
            profile_photo_url=req.profile_photo_url,
            date_of_joining=req.date_of_joining or datetime.utcnow().date(),
            engagement_type=req.engagement_type.value,
            status=StaffStatus.ONBOARDING.value,
            primary_role_id=req.primary_role_id,
            notes=req.notes,
            created_by_user_id=created_by_user.id,
        )

        contact = StaffContact(
            phone=req.contact.phone,
            alternate_phone=req.contact.alternate_phone,
            email=req.contact.email,
            emergency_contact_name=req.contact.emergency_contact_name,
            emergency_contact_relationship=req.contact.emergency_contact_relationship,
            emergency_contact_phone=req.contact.emergency_contact_phone,
        )

        # 4. Save via repository
        created_staff = await self.repo.create_staff(staff, contact)

        # 5. Log initial status history
        hist = StaffStatusHistory(
            society_id=society_id,
            staff_id=created_staff.id,
            from_status=None,
            to_status=StaffStatus.ONBOARDING.value,
            changed_by_user_id=created_by_user.id,
            reason="Initial staff profile creation",
        )
        await self.repo.add_status_history(hist)

        return created_staff

    async def get_staff_profile(self, staff_id: uuid.UUID, society_id: uuid.UUID) -> StaffProfile:
        """Fetch staff profile by ID and verify society context."""
        staff = await self.repo.get_by_id(staff_id, society_id)
        if not staff:
            raise StaffNotFoundError(str(staff_id))
        return staff

    async def update_staff_profile(
        self,
        staff_id: uuid.UUID,
        society_id: uuid.UUID,
        req: StaffProfileUpdateRequest,
        updated_by_user: User,
    ) -> StaffProfile:
        """Update staff profile details."""
        staff = await self.get_staff_profile(staff_id, society_id)

        if req.first_name is not None:
            staff.first_name = req.first_name
        if req.middle_name is not None:
            staff.middle_name = req.middle_name
        if req.last_name is not None:
            staff.last_name = req.last_name
        if req.first_name or req.last_name:
            staff.display_name = f"{staff.first_name} {staff.last_name}"

        if req.preferred_name is not None:
            staff.preferred_name = req.preferred_name
        if req.profile_photo_url is not None:
            staff.profile_photo_url = req.profile_photo_url
        if req.engagement_type is not None:
            staff.engagement_type = req.engagement_type.value
        if req.primary_role_id is not None:
            role = await self.role_repo.get_role_by_id(req.primary_role_id, society_id)
            if not role:
                raise StaffRoleNotFoundError(str(req.primary_role_id))
            staff.primary_role_id = req.primary_role_id
        if req.notes is not None:
            staff.notes = req.notes

        staff.updated_at = datetime.utcnow()
        await self.session.flush()
        return staff

    async def transition_staff_status(
        self,
        staff_id: uuid.UUID,
        society_id: uuid.UUID,
        req: StaffStatusUpdateRequest,
        changed_by_user: User,
    ) -> StaffProfile:
        """Execute validated state machine transition for staff status."""
        staff = await self.get_staff_profile(staff_id, society_id)
        current_status = staff.status
        target_status = req.status.value

        # Validate transition using state machine
        StaffStatusStateMachine.validate_transition(current_status, target_status)

        staff.status = target_status
        staff.updated_at = datetime.utcnow()

        # Log status transition history
        history = StaffStatusHistory(
            society_id=society_id,
            staff_id=staff.id,
            from_status=current_status,
            to_status=target_status,
            changed_by_user_id=changed_by_user.id,
            reason=req.reason,
        )
        await self.repo.add_status_history(history)
        await self.session.flush()
        return staff

    async def list_staff(
        self,
        society_id: uuid.UUID,
        status: str | None = None,
        engagement_type: str | None = None,
        role_id: uuid.UUID | None = None,
        team_id: uuid.UUID | None = None,
        search: str | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> list[StaffProfile]:
        """List staff profiles for society."""
        return await self.repo.list_staff(
            society_id=society_id,
            status=status,
            engagement_type=engagement_type,
            role_id=role_id,
            team_id=team_id,
            search=search,
            offset=offset,
            limit=limit,
        )
