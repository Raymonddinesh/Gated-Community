"""Application service for Resident Profiles, Contact Privacy, and Deterministic Completeness."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.database.models.identity import User
from apps.api.src.database.models.membership import ResidentProfile
from apps.api.src.database.repositories.audit_repository import AuditRepository
from apps.api.src.database.repositories.membership_repository import MembershipRepository
from apps.api.src.database.repositories.user_repository import UserRepository
from apps.api.src.residents.domain.exceptions import ResidentNotFoundError
from apps.api.src.residents.domain.models import (
    calculate_profile_completeness,
    mask_email,
    mask_phone,
)
from apps.api.src.residents.infrastructure.repositories import ResidentRepository
from apps.api.src.residents.schemas import (
    EmergencyContactUpdate,
    ProfileCompleteness,
    ResidentCreateRequest,
    ResidentProfileUpdate,
    ResidentResponse,
)


class ResidentService:
    """Service orchestrating resident profile retrieval, updates, and privacy masking."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.resident_repo = ResidentRepository(session)
        self.user_repo = UserRepository(session)
        self.membership_repo = MembershipRepository(session)
        self.audit_repo = AuditRepository(session)

    def _build_response(
        self,
        user: User,
        profile: ResidentProfile,
        can_view_full_contact: bool = True,
        can_view_emergency: bool = True,
    ) -> ResidentResponse:
        """Construct ResidentResponse applying privacy masking based on permissions."""
        comp_dict = calculate_profile_completeness(
            display_name=user.display_name,
            phone=user.phone,
            email=user.email,
            alternate_phone=profile.alternate_phone,
            emergency_contact_name=profile.emergency_contact_name,
            emergency_contact_phone=profile.emergency_contact_phone,
            preferred_language=profile.preferred_language,
        )
        completeness = ProfileCompleteness(
            is_complete=bool(comp_dict["is_complete"]),
            score_percent=int(comp_dict["score_percent"]),  # type: ignore
            missing_required=list(comp_dict["missing_required"]),  # type: ignore
            missing_fields=list(comp_dict["missing_fields"]),  # type: ignore
        )

        phone = user.phone if can_view_full_contact else mask_phone(user.phone)
        email = user.email if can_view_full_contact else mask_email(user.email)
        alt_phone = profile.alternate_phone if can_view_full_contact else mask_phone(profile.alternate_phone)

        em_name = profile.emergency_contact_name if can_view_emergency else None
        em_phone = (
            profile.emergency_contact_phone
            if can_view_emergency
            else mask_phone(profile.emergency_contact_phone)
            if profile.emergency_contact_phone
            else None
        )

        return ResidentResponse(
            id=profile.id,
            user_id=user.id,
            society_id=profile.society_id,
            first_name=user.first_name,
            last_name=user.last_name,
            display_name=user.display_name,
            phone=phone,
            alternate_phone=alt_phone,
            email=email,
            emergency_contact_name=em_name,
            emergency_contact_phone=em_phone,
            preferred_contact_method=profile.preferred_contact_method,
            preferred_language=profile.preferred_language,
            accessibility_preferences=profile.accessibility_preferences or {},
            communication_preferences=profile.communication_preferences or {},
            status=profile.status,
            notes=profile.notes,
            completeness=completeness,
            created_at=profile.created_at,
            updated_at=profile.updated_at,
        )

    async def get_my_profile(self, user_id: UUID, society_id: UUID) -> ResidentResponse:
        """Self-service endpoint: residents always see their own unmasked details."""
        user = await self.user_repo.get_by_id(user_id)
        if not user:
            raise ResidentNotFoundError("User identity not found.")

        profile = await self.resident_repo.get_profile(user_id, society_id)
        if not profile:
            # Auto-initialize resident profile if user is a member
            profile = await self.resident_repo.create_profile(user_id=user_id, society_id=society_id)

        return self._build_response(user, profile, can_view_full_contact=True, can_view_emergency=True)

    async def update_my_profile(
        self, user_id: UUID, society_id: UUID, data: ResidentProfileUpdate
    ) -> ResidentResponse:
        """Self-service update of resident preferences and emergency contact."""
        profile = await self.resident_repo.get_profile(user_id, society_id)
        if not profile:
            profile = await self.resident_repo.create_profile(user_id=user_id, society_id=society_id)

        before_state = {
            "emergency_contact_name": profile.emergency_contact_name,
            "emergency_contact_phone": profile.emergency_contact_phone,
            "alternate_phone": profile.alternate_phone,
            "preferred_language": profile.preferred_language,
        }

        if data.emergency_contact_name is not None:
            profile.emergency_contact_name = data.emergency_contact_name
        if data.emergency_contact_phone is not None:
            profile.emergency_contact_phone = data.emergency_contact_phone
        if data.alternate_phone is not None:
            profile.alternate_phone = data.alternate_phone
        if data.preferred_contact_method is not None:
            profile.preferred_contact_method = data.preferred_contact_method
        if data.preferred_language is not None:
            profile.preferred_language = data.preferred_language
        if data.accessibility_preferences is not None:
            profile.accessibility_preferences = data.accessibility_preferences
        if data.communication_preferences is not None:
            profile.communication_preferences = data.communication_preferences
        if data.notes is not None:
            profile.notes = data.notes

        await self.session.flush()

        after_state = {
            "emergency_contact_name": profile.emergency_contact_name,
            "emergency_contact_phone": profile.emergency_contact_phone,
            "alternate_phone": profile.alternate_phone,
            "preferred_language": profile.preferred_language,
        }

        await self.audit_repo.log_event(
            action="resident.profile_updated",
            entity_type="resident_profile",
            entity_id=str(profile.id),
            society_id=society_id,
            actor_user_id=user_id,
            before_state=before_state,
            after_state=after_state,
        )

        user = await self.user_repo.get_by_id(user_id)
        return self._build_response(user, profile, can_view_full_contact=True, can_view_emergency=True)  # type: ignore

    async def update_my_emergency_contact(
        self, user_id: UUID, society_id: UUID, data: EmergencyContactUpdate
    ) -> ResidentResponse:
        """Self-service update for emergency contact."""
        return await self.update_my_profile(
            user_id,
            society_id,
            ResidentProfileUpdate(
                emergency_contact_name=data.emergency_contact_name,
                emergency_contact_phone=data.emergency_contact_phone,
            ),
        )

    async def get_resident(
        self,
        profile_id: UUID,
        society_id: UUID,
        requester_user_id: UUID,
        permissions: list[str],
        roles: list[str],
    ) -> ResidentResponse:
        """Administrative or resident lookup with granular privacy enforcement."""
        profile = await self.resident_repo.get_profile_by_id(profile_id, society_id)
        if not profile:
            raise ResidentNotFoundError("Resident profile not found in society.")

        user = profile.user or await self.user_repo.get_by_id(profile.user_id)
        if not user:
            raise ResidentNotFoundError("User identity not found.")

        # Determine visibility
        is_self = requester_user_id == user.id
        is_admin = any(r in ("SUPER_ADMIN", "SOCIETY_ADMIN", "SECRETARY", "TREASURER") for r in roles)
        can_view_contact = is_self or is_admin or ("resident.contact.view" in permissions)
        can_view_emergency = is_self or is_admin or ("resident.emergency.view" in permissions)

        return self._build_response(user, profile, can_view_contact, can_view_emergency)

    async def create_resident(
        self, society_id: UUID, data: ResidentCreateRequest, actor_user_id: UUID
    ) -> ResidentResponse:
        """Admin endpoint to create a resident association."""
        user = await self.user_repo.get_by_id(data.user_id)
        if not user:
            raise ResidentNotFoundError("Target user not found.")

        # Ensure user has active society membership
        await self.membership_repo.create_membership(user_id=data.user_id, society_id=society_id)

        # Check existing profile
        existing = await self.resident_repo.get_profile(data.user_id, society_id)
        if existing:
            return self._build_response(user, existing, can_view_full_contact=True, can_view_emergency=True)

        profile = await self.resident_repo.create_profile(
            user_id=data.user_id,
            society_id=society_id,
            alternate_phone=data.alternate_phone,
            emergency_contact_name=data.emergency_contact_name,
            emergency_contact_phone=data.emergency_contact_phone,
            preferred_language=data.preferred_language,
            preferred_contact_method=data.preferred_contact_method,
            notes=data.notes,
        )

        await self.audit_repo.log_event(
            action="resident.created",
            entity_type="resident_profile",
            entity_id=str(profile.id),
            society_id=society_id,
            actor_user_id=actor_user_id,
            after_state={"user_id": str(data.user_id), "status": profile.status},
        )

        return self._build_response(user, profile, can_view_full_contact=True, can_view_emergency=True)

    async def update_resident(
        self,
        profile_id: UUID,
        society_id: UUID,
        data: ResidentProfileUpdate,
        actor_user_id: UUID,
    ) -> ResidentResponse:
        """Admin update of resident profile."""
        profile = await self.resident_repo.get_profile_by_id(profile_id, society_id)
        if not profile:
            raise ResidentNotFoundError()

        before_state = {
            "emergency_contact_name": profile.emergency_contact_name,
            "emergency_contact_phone": profile.emergency_contact_phone,
            "alternate_phone": profile.alternate_phone,
            "preferred_language": profile.preferred_language,
            "status": profile.status,
        }

        if data.emergency_contact_name is not None:
            profile.emergency_contact_name = data.emergency_contact_name
        if data.emergency_contact_phone is not None:
            profile.emergency_contact_phone = data.emergency_contact_phone
        if data.alternate_phone is not None:
            profile.alternate_phone = data.alternate_phone
        if data.preferred_contact_method is not None:
            profile.preferred_contact_method = data.preferred_contact_method
        if data.preferred_language is not None:
            profile.preferred_language = data.preferred_language
        if data.accessibility_preferences is not None:
            profile.accessibility_preferences = data.accessibility_preferences
        if data.communication_preferences is not None:
            profile.communication_preferences = data.communication_preferences
        if data.notes is not None:
            profile.notes = data.notes

        await self.session.flush()

        after_state = {
            "emergency_contact_name": profile.emergency_contact_name,
            "emergency_contact_phone": profile.emergency_contact_phone,
            "alternate_phone": profile.alternate_phone,
            "preferred_language": profile.preferred_language,
            "status": profile.status,
        }

        await self.audit_repo.log_event(
            action="resident.updated",
            entity_type="resident_profile",
            entity_id=str(profile.id),
            society_id=society_id,
            actor_user_id=actor_user_id,
            before_state=before_state,
            after_state=after_state,
        )

        user = profile.user or await self.user_repo.get_by_id(profile.user_id)
        return self._build_response(user, profile, can_view_full_contact=True, can_view_emergency=True)  # type: ignore

    async def search_residents(
        self,
        society_id: UUID,
        query: str | None,
        unit_number: str | None,
        block_code: str | None,
        status: str | None,
        limit: int,
        offset: int,
        requester_user_id: UUID,
        permissions: list[str],
        roles: list[str],
    ) -> list[ResidentResponse]:
        """Tenant-scoped search with contact privacy."""
        is_admin = any(r in ("SUPER_ADMIN", "SOCIETY_ADMIN", "SECRETARY", "TREASURER") for r in roles)
        can_view_contact = is_admin or ("resident.contact.view" in permissions)
        can_view_emergency = is_admin or ("resident.emergency.view" in permissions)

        results = await self.resident_repo.search_residents(
            society_id=society_id,
            query_str=query,
            unit_number=unit_number,
            block_code=block_code,
            status=status,
            limit=limit,
            offset=offset,
        )

        responses: list[ResidentResponse] = []
        for user, profile in results:
            if not profile:
                profile = await self.resident_repo.create_profile(user_id=user.id, society_id=society_id)
            is_self = requester_user_id == user.id
            resp = self._build_response(
                user,
                profile,
                can_view_full_contact=is_self or can_view_contact,
                can_view_emergency=is_self or can_view_emergency,
            )
            responses.append(resp)
        return responses
