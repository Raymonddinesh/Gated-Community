"""Application Service for Vehicle Management."""

import uuid
from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.core.exceptions import NotFoundException
from apps.api.src.database.models.membership import UserSocietyMembership
from apps.api.src.database.models.society import Unit
from apps.api.src.database.models.vehicle import (
    Vehicle,
    VehicleParkingAssociation,
    VehicleResidentAssociation,
    VehicleVerification,
)
from apps.api.src.residents.domain.concurrency import get_unit_lock
from apps.api.src.vehicles.domain.concurrency import get_registration_lock, get_vehicle_lock
from apps.api.src.vehicles.domain.exceptions import (
    DuplicateVehicleRegistrationError,
    InvalidVehicleStatusTransitionError,
    InvalidVerificationStatusError,
    VehicleNotFoundError,
)
from apps.api.src.vehicles.domain.normalization import normalize_registration_number
from apps.api.src.vehicles.infrastructure.repositories import (
    VehicleAssociationRepository,
    VehicleParkingRepository,
    VehicleRepository,
    VehicleVerificationRepository,
)
from apps.api.src.vehicles.schemas import (
    VehicleCreateRequest,
    VehicleStatusEnum,
    VehicleUpdateRequest,
    VehicleVerifyRequest,
)


class VehicleService:
    """Service handling vehicle registration, lifecycle, search, and verifications."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.vehicle_repo = VehicleRepository(session)
        self.assoc_repo = VehicleAssociationRepository(session)
        self.verif_repo = VehicleVerificationRepository(session)
        self.parking_repo = VehicleParkingRepository(session)

    async def register_vehicle(
        self,
        society_id: uuid.UUID,
        user_id: uuid.UUID,
        data: VehicleCreateRequest,
    ) -> Vehicle:
        """
        Register a new vehicle into the society.
        Ensures plate normalization, prevents active duplicates, and establishes optional initial links.
        """
        normalized_reg = normalize_registration_number(data.registration_number)

        async with get_registration_lock(society_id, normalized_reg):
            # Check duplicate active registration in this society
            existing = await self.vehicle_repo.get_active_by_normalized_reg(society_id, normalized_reg)
            if existing:
                raise DuplicateVehicleRegistrationError(
                    registration_number=data.registration_number,
                    normalized_registration_number=normalized_reg,
                )

            # Fuel / EV auto-adjust
            fuel_type = data.fuel_type.value
            is_ev = data.is_ev
            if is_ev and fuel_type not in ("ELECTRIC", "HYBRID"):
                fuel_type = "ELECTRIC"
            elif fuel_type == "ELECTRIC":
                is_ev = True

            vehicle = Vehicle(
                id=uuid.uuid4(),
                society_id=society_id,
                registration_number=data.registration_number.strip().upper(),
                normalized_registration_number=normalized_reg,
                vehicle_type=data.vehicle_type.value,
                make=data.make.strip() if data.make else None,
                model=data.model.strip() if data.model else None,
                variant=data.variant.strip() if data.variant else None,
                color=data.color.strip() if data.color else None,
                fuel_type=fuel_type,
                is_ev=is_ev,
                battery_capacity_kwh=data.battery_capacity_kwh,
                charging_required=data.charging_required,
                status="ACTIVE",
                verification_status="PENDING",
                notes=data.notes,
                created_by=user_id,
                updated_by=user_id,
            )
            await self.vehicle_repo.save(vehicle)

            # Optional initial association
            target_user_id = data.user_id or user_id
            if data.unit_id:
                # Same-society validation for Unit
                unit_res = await self.session.execute(
                    select(Unit).where(Unit.id == data.unit_id, Unit.society_id == society_id)
                )
                if not unit_res.scalar_one_or_none():
                    raise NotFoundException(f"Unit with ID '{data.unit_id}' not found in this society")

                # Same-society validation for User membership
                mem_res = await self.session.execute(
                    select(UserSocietyMembership).where(
                        UserSocietyMembership.user_id == target_user_id,
                        UserSocietyMembership.society_id == society_id,
                        UserSocietyMembership.membership_status == "ACTIVE",
                    )
                )
                if not mem_res.scalar_one_or_none():
                    raise NotFoundException(
                        f"User with ID '{target_user_id}' does not have an active membership in this society"
                    )

                # If primary, acquire unit lock and check existing primary
                if data.is_primary:
                    async with get_unit_lock(data.unit_id):
                        existing_primary = await self.assoc_repo.get_active_primary(
                            society_id=society_id,
                            unit_id=data.unit_id,
                            user_id=target_user_id,
                        )
                        if existing_primary:
                            existing_primary.is_primary = False
                            await self.assoc_repo.save(existing_primary)

                        assoc = VehicleResidentAssociation(
                            id=uuid.uuid4(),
                            society_id=society_id,
                            vehicle_id=vehicle.id,
                            user_id=target_user_id,
                            unit_id=data.unit_id,
                            association_type=data.association_type.value,
                            is_primary=True,
                            valid_from=date.today(),
                            status="ACTIVE",
                            notes="Initial registration association",
                        )
                        await self.assoc_repo.save(assoc)
                else:
                    assoc = VehicleResidentAssociation(
                        id=uuid.uuid4(),
                        society_id=society_id,
                        vehicle_id=vehicle.id,
                        user_id=target_user_id,
                        unit_id=data.unit_id,
                        association_type=data.association_type.value,
                        is_primary=False,
                        valid_from=date.today(),
                        status="ACTIVE",
                        notes="Initial registration association",
                    )
                    await self.assoc_repo.save(assoc)

            # Optional initial parking association
            if data.parking_slot_number:
                parking = VehicleParkingAssociation(
                    id=uuid.uuid4(),
                    society_id=society_id,
                    vehicle_id=vehicle.id,
                    parking_slot_number=data.parking_slot_number.strip().upper(),
                    valid_from=date.today(),
                    status="ACTIVE",
                    notes="Initial parking slot assignment",
                )
                await self.parking_repo.save(parking)

            await self.session.flush()
            # Fetch loaded vehicle
            loaded = await self.vehicle_repo.get_by_id(vehicle.id, society_id)
            return loaded or vehicle

    async def get_vehicle(self, society_id: uuid.UUID, vehicle_id: uuid.UUID) -> Vehicle:
        """Fetch single vehicle with relationships."""
        veh = await self.vehicle_repo.get_by_id(vehicle_id, society_id)
        if not veh:
            raise VehicleNotFoundError(vehicle_id)
        return veh

    async def update_vehicle(
        self,
        society_id: uuid.UUID,
        vehicle_id: uuid.UUID,
        user_id: uuid.UUID,
        data: VehicleUpdateRequest,
    ) -> Vehicle:
        """Update vehicle details."""
        async with get_vehicle_lock(vehicle_id):
            veh = await self.get_vehicle(society_id, vehicle_id)

            if data.make is not None:
                veh.make = data.make.strip() if data.make else None
            if data.model is not None:
                veh.model = data.model.strip() if data.model else None
            if data.variant is not None:
                veh.variant = data.variant.strip() if data.variant else None
            if data.color is not None:
                veh.color = data.color.strip() if data.color else None
            if data.fuel_type is not None:
                veh.fuel_type = data.fuel_type.value
            if data.is_ev is not None:
                veh.is_ev = data.is_ev
            if data.battery_capacity_kwh is not None:
                veh.battery_capacity_kwh = data.battery_capacity_kwh
            if data.charging_required is not None:
                veh.charging_required = data.charging_required
            if data.notes is not None:
                veh.notes = data.notes

            veh.updated_by = user_id
            await self.vehicle_repo.save(veh)
            return veh

    async def update_status(
        self,
        society_id: uuid.UUID,
        vehicle_id: uuid.UUID,
        user_id: uuid.UUID,
        target_status: VehicleStatusEnum,
        notes: str | None = None,
    ) -> Vehicle:
        """Transition vehicle lifecycle status."""
        async with get_vehicle_lock(vehicle_id):
            veh = await self.get_vehicle(society_id, vehicle_id)
            current_status = veh.status

            if current_status == target_status.value:
                return veh

            # Check valid transitions
            if current_status in ("SCRAPPED", "SOLD") and target_status.value == "ACTIVE":
                raise InvalidVehicleStatusTransitionError(current_status, target_status.value)

            veh.status = target_status.value
            veh.updated_by = user_id
            if notes:
                veh.notes = f"{veh.notes or ''}\nStatus changed: {notes}".strip()

            # If vehicle is no longer active, end all active associations and parking
            if target_status.value != "ACTIVE":
                active_assocs = await self.assoc_repo.get_active_for_vehicle(society_id, vehicle_id)
                for a in active_assocs:
                    a.status = "ENDED"
                    a.valid_to = date.today()
                    await self.assoc_repo.save(a)

                active_parkings = await self.parking_repo.get_active_for_vehicle(society_id, vehicle_id)
                for p in active_parkings:
                    p.status = "ENDED"
                    p.valid_to = date.today()
                    await self.parking_repo.save(p)

            await self.vehicle_repo.save(veh)
            return veh

    async def verify_vehicle(
        self,
        society_id: uuid.UUID,
        vehicle_id: uuid.UUID,
        verifier_user_id: uuid.UUID,
        data: VehicleVerifyRequest,
    ) -> Vehicle:
        """Audit-logged verification of a vehicle."""
        async with get_vehicle_lock(vehicle_id):
            veh = await self.get_vehicle(society_id, vehicle_id)

            status_str = data.verification_status.value
            if status_str not in ("VERIFIED", "REJECTED", "EXPIRED"):
                raise InvalidVerificationStatusError(f"Invalid verification target status: '{status_str}'")

            verif = VehicleVerification(
                id=uuid.uuid4(),
                society_id=society_id,
                vehicle_id=vehicle_id,
                verifier_user_id=verifier_user_id,
                verification_status=status_str,
                verification_date=date.today(),
                reason=data.reason,
                supporting_document_ref=data.supporting_document_ref,
                notes=data.notes,
                created_at=datetime.now(UTC),
            )
            await self.verif_repo.save(verif)

            veh.verification_status = status_str
            veh.updated_by = verifier_user_id
            await self.vehicle_repo.save(veh)

            loaded = await self.vehicle_repo.get_by_id(vehicle_id, society_id)
            return loaded or veh

    async def search(
        self,
        society_id: uuid.UUID,
        query: str | None = None,
        vehicle_type: str | None = None,
        fuel_type: str | None = None,
        is_ev: bool | None = None,
        status: str | None = None,
        verification_status: str | None = None,
        unit_id: uuid.UUID | None = None,
        page: int = 1,
        size: int = 50,
    ) -> tuple[list[Vehicle], int]:
        """Search society vehicles."""
        return await self.vehicle_repo.search(
            society_id=society_id,
            query=query,
            vehicle_type=vehicle_type,
            fuel_type=fuel_type,
            is_ev=is_ev,
            status=status,
            verification_status=verification_status,
            unit_id=unit_id,
            page=page,
            size=size,
        )

    async def get_my_vehicles(
        self,
        society_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> list[Vehicle]:
        """Get all vehicles linked to the requesting resident."""
        return await self.vehicle_repo.get_vehicles_for_resident(society_id, user_id)
