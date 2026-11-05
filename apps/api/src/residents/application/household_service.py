"""Application service for Household, Family Members, Scoped Delegates, and My Home Aggregation."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.database.models.membership import ResidentDelegate, ResidentFamilyMember
from apps.api.src.database.models.society import Unit
from apps.api.src.database.repositories.audit_repository import AuditRepository
from apps.api.src.database.repositories.user_repository import UserRepository
from apps.api.src.residents.application.occupancy_service import OccupancyService
from apps.api.src.residents.application.ownership_service import OwnershipService
from apps.api.src.residents.application.resident_service import ResidentService
from apps.api.src.residents.domain.exceptions import (
    FamilyMemberNotFoundError,
    InvalidDateRangeError,
    ResidentNotFoundError,
    UnauthorizedDelegateError,
    UnitNotFoundError,
)
from apps.api.src.residents.domain.models import ALLOWED_DELEGATE_PERMISSIONS
from apps.api.src.residents.infrastructure.repositories import (
    DelegateRepository,
    FamilyRepository,
    OccupancyRepository,
    OwnershipRepository,
    ResidentRepository,
)
from apps.api.src.residents.schemas import (
    DelegateCreate,
    DelegateResponse,
    DelegateRevokeRequest,
    FamilyMemberCreate,
    FamilyMemberResponse,
    FamilyMemberUpdate,
    MyHomeResponse,
    MyHomeUnitSummary,
)


class HouseholdService:
    """Service managing family members, scoped delegates, and aggregated self-service view."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.family_repo = FamilyRepository(session)
        self.delegate_repo = DelegateRepository(session)
        self.occupancy_repo = OccupancyRepository(session)
        self.ownership_repo = OwnershipRepository(session)
        self.resident_repo = ResidentRepository(session)
        self.user_repo = UserRepository(session)
        self.audit_repo = AuditRepository(session)
        self.resident_service = ResidentService(session)
        self.occupancy_service = OccupancyService(session)
        self.ownership_service = OwnershipService(session)

    def _to_family_response(self, member: ResidentFamilyMember) -> FamilyMemberResponse:
        return FamilyMemberResponse(
            id=member.id,
            society_id=member.society_id,
            unit_id=member.unit_id,
            primary_resident_user_id=member.primary_resident_user_id,
            user_id=member.user_id,
            name=member.name,
            relationship=member.relationship,
            phone=member.phone,
            email=member.email,
            access_scope=member.access_scope or {},
            status=member.status,
            created_at=member.created_at,
            updated_at=member.updated_at,
        )

    def _to_delegate_response(self, dlg: ResidentDelegate) -> DelegateResponse:
        del_user = dlg.delegate
        dlgr_user = dlg.delegator
        return DelegateResponse(
            id=dlg.id,
            society_id=dlg.society_id,
            unit_id=dlg.unit_id,
            delegator_user_id=dlg.delegator_user_id,
            delegator_name=dlgr_user.display_name if dlgr_user else "Unknown",
            delegate_user_id=dlg.delegate_user_id,
            delegate_name=del_user.display_name if del_user else "Unknown",
            delegate_phone=del_user.phone if del_user else None,
            delegate_email=del_user.email if del_user else None,
            permissions=dlg.permissions,
            valid_from=dlg.valid_from,
            valid_to=dlg.valid_to,
            status=dlg.status,
            revoked_at=dlg.revoked_at,
            revoked_by=dlg.revoked_by,
            revocation_reason=dlg.revocation_reason,
            notes=dlg.notes,
            created_at=dlg.created_at,
            updated_at=dlg.updated_at,
        )

    async def _get_unit(self, unit_id: UUID, society_id: UUID) -> Unit:
        stmt = select(Unit).where(Unit.id == unit_id, Unit.society_id == society_id)
        result = await self.session.execute(stmt)
        unit = result.scalar_one_or_none()
        if not unit:
            raise UnitNotFoundError(f"Unit {unit_id} not found in society.")
        return unit

    # -----------------------------------------------------------------------
    # Family Members
    # -----------------------------------------------------------------------
    async def add_family_member(
        self,
        society_id: UUID,
        unit_id: UUID,
        primary_resident_user_id: UUID,
        data: FamilyMemberCreate,
        actor_user_id: UUID,
    ) -> FamilyMemberResponse:
        """Add a family member associated with a primary resident and unit."""
        await self._get_unit(unit_id, society_id)

        # Verify primary resident has active relation to unit
        occs = await self.occupancy_repo.get_occupancies_for_user(
            primary_resident_user_id, society_id, active_only=True
        )
        owns = await self.ownership_repo.get_ownerships_for_user(
            primary_resident_user_id, society_id, active_only=True
        )
        has_unit = any(o.unit_id == unit_id for o in occs) or any(w.unit_id == unit_id for w in owns)
        if not has_unit:
            raise UnauthorizedDelegateError(
                "Primary resident has no active occupancy or ownership in this unit."
            )

        member = await self.family_repo.create_family_member(
            society_id=society_id,
            unit_id=unit_id,
            primary_resident_user_id=primary_resident_user_id,
            name=data.name,
            relationship=data.relationship.upper(),
            phone=data.phone,
            email=str(data.email) if data.email else None,
            user_id=data.user_id,
            access_scope=data.access_scope,
            status="ACTIVE",
        )

        await self.audit_repo.log_event(
            action="family.added",
            entity_type="resident_family_member",
            entity_id=str(member.id),
            society_id=society_id,
            actor_user_id=actor_user_id,
            after_state={
                "unit_id": str(unit_id),
                "primary_resident_user_id": str(primary_resident_user_id),
                "name": member.name,
                "relationship": member.relationship,
            },
        )

        return self._to_family_response(member)

    async def update_family_member(
        self,
        society_id: UUID,
        member_id: UUID,
        data: FamilyMemberUpdate,
        actor_user_id: UUID,
    ) -> FamilyMemberResponse:
        """Update family member details."""
        member = await self.family_repo.get_family_member(member_id, society_id)
        if not member:
            raise FamilyMemberNotFoundError()

        if data.name is not None:
            member.name = data.name
        if data.relationship is not None:
            member.relationship = data.relationship.upper()
        if data.phone is not None:
            member.phone = data.phone
        if data.email is not None:
            member.email = str(data.email)
        if data.access_scope is not None:
            member.access_scope = data.access_scope
        if data.status is not None:
            member.status = data.status

        await self.session.flush()

        await self.audit_repo.log_event(
            action="family.updated",
            entity_type="resident_family_member",
            entity_id=str(member.id),
            society_id=society_id,
            actor_user_id=actor_user_id,
            after_state={"name": member.name, "relationship": member.relationship, "status": member.status},
        )

        return self._to_family_response(member)

    async def remove_family_member(
        self, society_id: UUID, member_id: UUID, actor_user_id: UUID
    ) -> FamilyMemberResponse:
        """Soft-delete / deactivate family member relationship."""
        member = await self.family_repo.get_family_member(member_id, society_id)
        if not member:
            raise FamilyMemberNotFoundError()

        member.status = "INACTIVE"
        await self.session.flush()

        await self.audit_repo.log_event(
            action="family.removed",
            entity_type="resident_family_member",
            entity_id=str(member.id),
            society_id=society_id,
            actor_user_id=actor_user_id,
            after_state={"status": "INACTIVE"},
        )

        return self._to_family_response(member)

    async def list_family_members(
        self,
        society_id: UUID,
        unit_id: UUID,
        primary_resident_user_id: UUID | None = None,
        active_only: bool = True,
    ) -> list[FamilyMemberResponse]:
        """List family members for a unit."""
        members = await self.family_repo.list_family_members(
            unit_id=unit_id,
            society_id=society_id,
            primary_resident_user_id=primary_resident_user_id,
            active_only=active_only,
        )
        return [self._to_family_response(m) for m in members]

    # -----------------------------------------------------------------------
    # Scoped Delegates
    # -----------------------------------------------------------------------
    async def create_delegate(
        self,
        society_id: UUID,
        unit_id: UUID,
        delegator_user_id: UUID,
        data: DelegateCreate,
        actor_user_id: UUID,
    ) -> DelegateResponse:
        """Grant explicit, permission-scoped delegation for a unit."""
        await self._get_unit(unit_id, society_id)

        if delegator_user_id == data.delegate_user_id:
            raise UnauthorizedDelegateError("A resident cannot delegate authority to themselves.")

        # Ensure delegator has active occupancy or ownership in this unit
        occs = await self.occupancy_repo.get_occupancies_for_user(
            delegator_user_id, society_id, active_only=True
        )
        owns = await self.ownership_repo.get_ownerships_for_user(
            delegator_user_id, society_id, active_only=True
        )
        has_unit = any(o.unit_id == unit_id for o in occs) or any(w.unit_id == unit_id for w in owns)
        if not has_unit:
            raise UnauthorizedDelegateError("Delegator is not an active occupant or owner of this unit.")

        # Ensure delegate exists
        delegate_user = await self.user_repo.get_by_id(data.delegate_user_id)
        if not delegate_user:
            raise ResidentNotFoundError("Delegate user not found.")

        # Validate explicit permissions
        invalid_perms = [p for p in data.permissions if p not in ALLOWED_DELEGATE_PERMISSIONS]
        if invalid_perms:
            raise UnauthorizedDelegateError(
                f"Unauthorized delegate permissions: {', '.join(invalid_perms)}. "
                f"Allowed permissions are: {', '.join(sorted(ALLOWED_DELEGATE_PERMISSIONS))}."
            )

        if data.valid_to and data.valid_to < data.valid_from:
            raise InvalidDateRangeError("Delegation end date cannot precede start date.")

        delegate = await self.delegate_repo.create_delegate(
            society_id=society_id,
            unit_id=unit_id,
            delegator_user_id=delegator_user_id,
            delegate_user_id=data.delegate_user_id,
            permissions=data.permissions,
            valid_from=data.valid_from,
            valid_to=data.valid_to,
            notes=data.notes,
        )

        await self.audit_repo.log_event(
            action="delegate.granted",
            entity_type="resident_delegate",
            entity_id=str(delegate.id),
            society_id=society_id,
            actor_user_id=actor_user_id,
            after_state={
                "unit_id": str(unit_id),
                "delegator_id": str(delegator_user_id),
                "delegate_id": str(data.delegate_user_id),
                "permissions": data.permissions,
            },
        )

        return self._to_delegate_response(delegate)

    async def revoke_delegate(
        self,
        society_id: UUID,
        delegate_id: UUID,
        data: DelegateRevokeRequest,
        actor_user_id: UUID,
    ) -> DelegateResponse:
        """Revoke a previously granted delegation."""
        delegate = await self.delegate_repo.revoke_delegate(
            delegate_id=delegate_id,
            society_id=society_id,
            revoked_by=actor_user_id,
            reason=data.reason,
        )

        await self.audit_repo.log_event(
            action="delegate.revoked",
            entity_type="resident_delegate",
            entity_id=str(delegate.id),
            society_id=society_id,
            actor_user_id=actor_user_id,
            after_state={"status": "REVOKED", "reason": data.reason},
        )

        return self._to_delegate_response(delegate)

    async def list_delegates(
        self,
        society_id: UUID,
        unit_id: UUID | None = None,
        delegator_user_id: UUID | None = None,
        delegate_user_id: UUID | None = None,
        active_only: bool = True,
    ) -> list[DelegateResponse]:
        """List delegates with optional filters."""
        delegates = await self.delegate_repo.list_delegates(
            unit_id=unit_id,
            society_id=society_id,
            delegator_user_id=delegator_user_id,
            delegate_user_id=delegate_user_id,
            active_only=active_only,
        )
        return [self._to_delegate_response(d) for d in delegates]

    async def is_delegate_authorized(
        self,
        society_id: UUID,
        delegate_user_id: UUID,
        unit_id: UUID,
        permission_code: str,
    ) -> bool:
        """
        Verify if a delegate user is actively authorized for a specific permission on a unit.
        Enforces tenant scoping, active status, unrevoked state, date window validity,
        and canonical module support.
        """
        return await self.delegate_repo.is_delegate_authorized(
            society_id=society_id,
            delegate_user_id=delegate_user_id,
            unit_id=unit_id,
            permission_code=permission_code,
        )

    # -----------------------------------------------------------------------
    # My Home / Aggregated Self-Service
    # -----------------------------------------------------------------------
    async def get_my_home(self, user_id: UUID, society_id: UUID) -> MyHomeResponse:
        """Aggregated self-service profile and household representation for 'My Home'."""
        resident_resp = await self.resident_service.get_my_profile(user_id, society_id)

        # Find user's active unit association (via active occupancy or ownership)
        user_occs = await self.occupancy_repo.get_occupancies_for_user(user_id, society_id, active_only=True)
        user_owns = await self.ownership_repo.get_ownerships_for_user(user_id, society_id, active_only=True)

        primary_unit_id: UUID | None = None
        my_occ_resp = None
        if user_occs:
            primary_unit_id = user_occs[0].unit_id
            my_occ_resp = self.occupancy_service._to_response(user_occs[0])
        elif user_owns:
            primary_unit_id = user_owns[0].unit_id

        unit_summary = None
        co_occupants: list = []
        owners: list = []
        family_members: list = []
        delegates: list = []

        if primary_unit_id:
            unit = await self._get_unit(primary_unit_id, society_id)
            block_code = unit.block.code if unit.block else "N/A"
            floor_num = unit.floor.floor_number if unit.floor else 0
            unit_summary = MyHomeUnitSummary(
                unit_id=unit.id,
                unit_number=unit.unit_number,
                block_name=block_code,
                floor_number=floor_num,
                unit_type=unit.unit_type,
                carpet_area_sqft=unit.carpet_area_sqft,
                occupancy_status=unit.occupancy_status,
            )

            co_occupants = await self.occupancy_service.list_occupants(society_id, primary_unit_id)
            owners = await self.ownership_service.list_owners(society_id, primary_unit_id)
            family_members = await self.list_family_members(society_id, primary_unit_id)
            delegates = await self.list_delegates(society_id=society_id, unit_id=primary_unit_id)

        easy_mode = resident_resp.accessibility_preferences.get("easy_mode", False)

        return MyHomeResponse(
            resident=resident_resp,
            unit=unit_summary,
            my_occupancy=my_occ_resp,
            co_occupants=co_occupants,
            owners=owners,
            family_members=family_members,
            delegates=delegates,
            easy_mode=easy_mode,
        )
