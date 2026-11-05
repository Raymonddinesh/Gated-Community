"""Application service managing Unit Occupancy, Move-In, Move-Out, and Overlap Validation."""

from datetime import date
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.database.models.membership import UnitOccupancy
from apps.api.src.database.models.society import Unit
from apps.api.src.database.repositories.audit_repository import AuditRepository
from apps.api.src.database.repositories.membership_repository import MembershipRepository
from apps.api.src.database.repositories.user_repository import UserRepository
from apps.api.src.residents.domain.concurrency import get_unit_lock
from apps.api.src.residents.domain.exceptions import (
    InvalidDateRangeError,
    OccupancyNotFoundError,
    OccupancyOverlapError,
    ResidentNotFoundError,
    UnitNotFoundError,
)
from apps.api.src.residents.infrastructure.repositories import OccupancyRepository
from apps.api.src.residents.schemas import (
    UnitOccupancyCreate,
    UnitOccupancyEndRequest,
    UnitOccupancyResponse,
    UnitOccupancyUpdate,
)


class OccupancyService:
    """Service orchestrating occupancy lifecycle, move-in, move-out, and overlap validation."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.occupancy_repo = OccupancyRepository(session)
        self.user_repo = UserRepository(session)
        self.membership_repo = MembershipRepository(session)
        self.audit_repo = AuditRepository(session)

    def _to_response(self, occ: UnitOccupancy) -> UnitOccupancyResponse:
        user = occ.user
        return UnitOccupancyResponse(
            id=occ.id,
            society_id=occ.society_id,
            unit_id=occ.unit_id,
            user_id=occ.user_id,
            user_name=user.display_name if user else "Unknown",
            user_phone=user.phone if user else None,
            user_email=user.email if user else None,
            relationship_type=occ.relationship_type,
            is_primary_contact=occ.is_primary_contact,
            valid_from=occ.valid_from,
            valid_to=occ.valid_to,
            status=occ.status,
            notes=occ.notes,
            created_at=occ.created_at,
            updated_at=occ.updated_at,
        )

    async def _get_unit(self, unit_id: UUID, society_id: UUID, for_update: bool = False) -> Unit:
        stmt = select(Unit).where(Unit.id == unit_id, Unit.society_id == society_id)
        if for_update:
            stmt = stmt.with_for_update()
        result = await self.session.execute(stmt)
        unit = result.scalar_one_or_none()
        if not unit:
            raise UnitNotFoundError(f"Unit {unit_id} not found in society.")
        return unit

    async def _ensure_membership(
        self, user_id: UUID, society_id: UUID, actor_user_id: UUID, source: str
    ) -> None:
        """Ensure active society membership, logging audit event if newly enrolled."""
        existing = await self.membership_repo.get_membership(user_id, society_id)
        if not existing:
            await self.membership_repo.create_membership(user_id=user_id, society_id=society_id)
            await self.audit_repo.log_event(
                action="membership.auto_enrolled",
                entity_type="user_society_membership",
                entity_id=str(user_id),
                society_id=society_id,
                actor_user_id=actor_user_id,
                after_state={"user_id": str(user_id), "source": source},
            )
        elif existing.membership_status != "ACTIVE":
            await self.membership_repo.create_membership(user_id=user_id, society_id=society_id)

    async def move_in(
        self,
        society_id: UUID,
        unit_id: UUID,
        data: UnitOccupancyCreate,
        actor_user_id: UUID,
    ) -> UnitOccupancyResponse:
        """Controlled move-in workflow with membership check and tenant overlap validation."""
        async with get_unit_lock(unit_id):
            unit = await self._get_unit(unit_id, society_id, for_update=True)

            user = await self.user_repo.get_by_id(data.user_id)
            if not user:
                raise ResidentNotFoundError("Occupant user not found.")

            # Ensure active society membership with audit tracking
            await self._ensure_membership(data.user_id, society_id, actor_user_id, "occupancy.move_in")

            if data.valid_to and data.valid_to < data.valid_from:
                raise InvalidDateRangeError("Move-in date cannot be after move-out date.")

            # Enforce no overlapping tenant leases
            if data.relationship_type.upper() == "TENANT":
                has_overlap = await self.occupancy_repo.check_tenant_overlap(
                    unit_id=unit_id,
                    society_id=society_id,
                    start_date=data.valid_from,
                    end_date=data.valid_to,
                )
                if has_overlap:
                    raise OccupancyOverlapError(
                        "Conflicting tenant occupancy exists for this unit in the specified time period."
                    )

            # If this occupant is designated primary contact, demote previous primary contacts
            if data.is_primary_contact:
                active_occs = await self.occupancy_repo.get_active_occupancies_for_unit(unit_id, society_id)
                for existing_occ in active_occs:
                    if existing_occ.is_primary_contact:
                        existing_occ.is_primary_contact = False

            occ = await self.occupancy_repo.create_occupancy(
                society_id=society_id,
                unit_id=unit_id,
                user_id=data.user_id,
                relationship_type=data.relationship_type.upper(),
                valid_from=data.valid_from,
                valid_to=data.valid_to,
                is_primary_contact=data.is_primary_contact,
                status="ACTIVE",
                notes=data.notes,
            )

            # Update physical unit occupancy status
            unit.occupancy_status = "OCCUPIED"
            await self.session.flush()

            await self.audit_repo.log_event(
                action="occupancy.move_in",
                entity_type="unit_occupancy",
                entity_id=str(occ.id),
                society_id=society_id,
                actor_user_id=actor_user_id,
                after_state={
                    "unit_id": str(unit_id),
                    "user_id": str(data.user_id),
                    "relationship_type": occ.relationship_type,
                    "valid_from": str(occ.valid_from),
                },
            )

            return self._to_response(occ)

    async def move_out(
        self,
        society_id: UUID,
        occupancy_id: UUID,
        data: UnitOccupancyEndRequest,
        actor_user_id: UUID,
    ) -> UnitOccupancyResponse:
        """Controlled move-out workflow preserving complete occupancy history."""
        occ = await self.occupancy_repo.get_occupancy(occupancy_id, society_id)
        if not occ:
            raise OccupancyNotFoundError("Occupancy record not found.")

        async with get_unit_lock(occ.unit_id):
            unit = await self._get_unit(occ.unit_id, society_id, for_update=True)

            before_state = {
                "status": occ.status,
                "valid_to": str(occ.valid_to) if occ.valid_to else None,
            }

            end_date = data.valid_to or date.today()
            if occ.valid_from and end_date < occ.valid_from:
                raise InvalidDateRangeError("End date cannot be prior to start date.")

            occ.valid_to = end_date
            occ.status = "ENDED"
            occ.is_primary_contact = False
            if data.reason:
                occ.notes = f"{occ.notes or ''} [End Reason: {data.reason}]".strip()

            await self.session.flush()

            # Check if any active occupancies remain for this unit
            remaining_active = await self.occupancy_repo.get_active_occupancies_for_unit(
                occ.unit_id, society_id
            )
            if not remaining_active:
                unit.occupancy_status = "VACANT"
                await self.session.flush()

            await self.audit_repo.log_event(
                action="occupancy.move_out",
                entity_type="unit_occupancy",
                entity_id=str(occ.id),
                society_id=society_id,
                actor_user_id=actor_user_id,
                before_state=before_state,
                after_state={"status": occ.status, "valid_to": str(occ.valid_to)},
            )

            return self._to_response(occ)

    async def update_occupancy(
        self,
        society_id: UUID,
        occupancy_id: UUID,
        data: UnitOccupancyUpdate,
        actor_user_id: UUID,
    ) -> UnitOccupancyResponse:
        """Update occupancy metadata."""
        occ = await self.occupancy_repo.get_occupancy(occupancy_id, society_id)
        if not occ:
            raise OccupancyNotFoundError()

        before_state = {
            "is_primary_contact": occ.is_primary_contact,
            "status": occ.status,
            "valid_to": str(occ.valid_to) if occ.valid_to else None,
        }

        if data.is_primary_contact is not None:
            if data.is_primary_contact:
                active_occs = await self.occupancy_repo.get_active_occupancies_for_unit(
                    occ.unit_id, society_id
                )
                for existing_occ in active_occs:
                    if existing_occ.id != occ.id and existing_occ.is_primary_contact:
                        existing_occ.is_primary_contact = False
            occ.is_primary_contact = data.is_primary_contact

        if data.valid_to is not None:
            if occ.valid_from and data.valid_to < occ.valid_from:
                raise InvalidDateRangeError("End date cannot be prior to start date.")
            occ.valid_to = data.valid_to

        if data.status is not None:
            occ.status = data.status

        if data.notes is not None:
            occ.notes = data.notes

        await self.session.flush()

        await self.audit_repo.log_event(
            action="occupancy.updated",
            entity_type="unit_occupancy",
            entity_id=str(occ.id),
            society_id=society_id,
            actor_user_id=actor_user_id,
            before_state=before_state,
            after_state={
                "is_primary_contact": occ.is_primary_contact,
                "status": occ.status,
                "valid_to": str(occ.valid_to) if occ.valid_to else None,
            },
        )

        return self._to_response(occ)

    async def list_occupants(self, society_id: UUID, unit_id: UUID) -> list[UnitOccupancyResponse]:
        """List current active occupants of a unit."""
        await self._get_unit(unit_id, society_id)
        occs = await self.occupancy_repo.get_active_occupancies_for_unit(unit_id, society_id)
        return [self._to_response(o) for o in occs]

    async def get_occupancy_history(self, society_id: UUID, unit_id: UUID) -> list[UnitOccupancyResponse]:
        """View full occupancy history for a unit."""
        await self._get_unit(unit_id, society_id)
        occs = await self.occupancy_repo.get_all_occupancies_for_unit(unit_id, society_id)
        return [self._to_response(o) for o in occs]
