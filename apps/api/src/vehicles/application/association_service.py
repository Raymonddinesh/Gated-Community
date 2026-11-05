"""Application service for Vehicle-Resident-Unit associations."""

import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.core.exceptions import NotFoundException
from apps.api.src.database.models.membership import UserSocietyMembership
from apps.api.src.database.models.society import Unit
from apps.api.src.database.models.vehicle import VehicleResidentAssociation
from apps.api.src.residents.domain.concurrency import get_unit_lock
from apps.api.src.vehicles.domain.concurrency import get_vehicle_lock
from apps.api.src.vehicles.domain.exceptions import (
    DuplicateVehicleAssociationError,
    VehicleAssociationNotFoundError,
    VehicleNotFoundError,
)
from apps.api.src.vehicles.infrastructure.repositories import (
    VehicleAssociationRepository,
    VehicleRepository,
)
from apps.api.src.vehicles.schemas import VehicleAssociationCreateRequest


class VehicleAssociationService:
    """Service managing links between vehicles, residents, and units."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.vehicle_repo = VehicleRepository(session)
        self.assoc_repo = VehicleAssociationRepository(session)

    async def add_association(
        self,
        society_id: uuid.UUID,
        vehicle_id: uuid.UUID,
        requesting_user_id: uuid.UUID,
        data: VehicleAssociationCreateRequest,
    ) -> VehicleResidentAssociation:
        """Link a vehicle to a resident and unit."""
        async with get_unit_lock(data.unit_id), get_vehicle_lock(vehicle_id):
            veh = await self.vehicle_repo.get_by_id(vehicle_id, society_id)
            if not veh:
                raise VehicleNotFoundError(vehicle_id)

            # 1. Same-society relational check for Unit
            unit_res = await self.session.execute(
                select(Unit).where(Unit.id == data.unit_id, Unit.society_id == society_id)
            )
            if not unit_res.scalar_one_or_none():
                raise NotFoundException(f"Unit with ID '{data.unit_id}' not found in this society")

            # 2. Same-society relational check for User membership
            mem_res = await self.session.execute(
                select(UserSocietyMembership).where(
                    UserSocietyMembership.user_id == data.user_id,
                    UserSocietyMembership.society_id == society_id,
                    UserSocietyMembership.membership_status == "ACTIVE",
                )
            )
            if not mem_res.scalar_one_or_none():
                raise NotFoundException(
                    f"User with ID '{data.user_id}' does not have an active membership in this society"
                )

            existing = await self.assoc_repo.find_existing_active(
                society_id=society_id,
                vehicle_id=vehicle_id,
                user_id=data.user_id,
                unit_id=data.unit_id,
            )
            if existing:
                raise DuplicateVehicleAssociationError(
                    vehicle_id=vehicle_id,
                    user_id=data.user_id,
                    unit_id=data.unit_id,
                )

            # If marking primary, demote existing primary for this (unit_id, user_id)
            if data.is_primary:
                existing_primary = await self.assoc_repo.get_active_primary(
                    society_id=society_id,
                    unit_id=data.unit_id,
                    user_id=data.user_id,
                )
                if existing_primary:
                    existing_primary.is_primary = False
                    await self.assoc_repo.save(existing_primary)

            assoc = VehicleResidentAssociation(
                id=uuid.uuid4(),
                society_id=society_id,
                vehicle_id=vehicle_id,
                user_id=data.user_id,
                unit_id=data.unit_id,
                association_type=data.association_type.value,
                is_primary=data.is_primary,
                valid_from=data.valid_from or date.today(),
                valid_to=data.valid_to,
                status="ACTIVE",
                notes=data.notes,
            )
            await self.assoc_repo.save(assoc)
            return assoc

    async def end_association(
        self,
        society_id: uuid.UUID,
        association_id: uuid.UUID,
        user_id: uuid.UUID,
        notes: str | None = None,
    ) -> VehicleResidentAssociation:
        """End an active association."""
        assoc = await self.assoc_repo.get_by_id(association_id, society_id)
        if not assoc:
            raise VehicleAssociationNotFoundError(association_id)

        assoc.status = "ENDED"
        assoc.valid_to = date.today()
        if notes:
            assoc.notes = f"{assoc.notes or ''}\nEnded: {notes}".strip()

        await self.assoc_repo.save(assoc)
        return assoc

    async def set_primary(
        self,
        society_id: uuid.UUID,
        association_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> VehicleResidentAssociation:
        """Designate an association as the primary vehicle for the user & unit."""
        assoc = await self.assoc_repo.get_by_id(association_id, society_id)
        if not assoc:
            raise VehicleAssociationNotFoundError(association_id)

        async with get_unit_lock(assoc.unit_id):
            # Demote existing primary
            existing_primary = await self.assoc_repo.get_active_primary(
                society_id=society_id,
                unit_id=assoc.unit_id,
                user_id=assoc.user_id,
            )
            if existing_primary and existing_primary.id != assoc.id:
                existing_primary.is_primary = False
                await self.assoc_repo.save(existing_primary)

            assoc.is_primary = True
            await self.assoc_repo.save(assoc)
            return assoc
