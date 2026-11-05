"""Data access repositories for Vehicles, Associations, Verifications, Documents, Parking, and Access Records."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from apps.api.src.database.models.vehicle import (
    Vehicle,
    VehicleAccessRecord,
    VehicleDocument,
    VehicleParkingAssociation,
    VehicleResidentAssociation,
    VehicleVerification,
)
from apps.api.src.vehicles.domain.exceptions import VehicleAccessRecordImmutableError


class VehicleRepository:
    """Repository for Vehicle queries and management."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, vehicle_id: uuid.UUID, society_id: uuid.UUID) -> Vehicle | None:
        """Fetch vehicle by ID within tenant boundary."""
        stmt = (
            select(Vehicle)
            .options(
                selectinload(Vehicle.associations).selectinload(VehicleResidentAssociation.unit),
                selectinload(Vehicle.associations).selectinload(VehicleResidentAssociation.user),
                selectinload(Vehicle.verifications),
                selectinload(Vehicle.documents),
                selectinload(Vehicle.parking_associations),
            )
            .where(
                Vehicle.id == vehicle_id,
                Vehicle.society_id == society_id,
            )
        )
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def get_active_by_normalized_reg(
        self,
        society_id: uuid.UUID,
        normalized_reg: str,
    ) -> Vehicle | None:
        """Fetch active vehicle by normalized registration number."""
        stmt = select(Vehicle).where(
            Vehicle.society_id == society_id,
            Vehicle.normalized_registration_number == normalized_reg,
            Vehicle.status == "ACTIVE",
        )
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

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
        """Search and filter vehicles with pagination."""
        base_stmt = select(Vehicle).where(Vehicle.society_id == society_id)

        if query:
            q_clean = query.strip()
            from apps.api.src.vehicles.domain.normalization import normalize_registration_number

            try:
                norm_q = normalize_registration_number(q_clean)
            except ValueError:
                norm_q = q_clean.upper()

            base_stmt = base_stmt.where(
                or_(
                    Vehicle.registration_number.ilike(f"%{q_clean}%"),
                    Vehicle.normalized_registration_number.ilike(f"%{norm_q}%"),
                    Vehicle.make.ilike(f"%{q_clean}%"),
                    Vehicle.model.ilike(f"%{q_clean}%"),
                )
            )

        if vehicle_type:
            base_stmt = base_stmt.where(Vehicle.vehicle_type == vehicle_type)
        if fuel_type:
            base_stmt = base_stmt.where(Vehicle.fuel_type == fuel_type)
        if is_ev is not None:
            base_stmt = base_stmt.where(Vehicle.is_ev == is_ev)
        if status:
            base_stmt = base_stmt.where(Vehicle.status == status)
        if verification_status:
            base_stmt = base_stmt.where(Vehicle.verification_status == verification_status)

        if unit_id:
            base_stmt = base_stmt.join(
                VehicleResidentAssociation,
                VehicleResidentAssociation.vehicle_id == Vehicle.id,
            ).where(
                VehicleResidentAssociation.unit_id == unit_id,
                VehicleResidentAssociation.status == "ACTIVE",
            )

        count_stmt = select(func.count()).select_from(base_stmt.subquery())
        total_res = await self.session.execute(count_stmt)
        total = total_res.scalar_one() or 0

        offset = (page - 1) * size
        stmt = (
            base_stmt.options(
                selectinload(Vehicle.associations).selectinload(VehicleResidentAssociation.unit),
                selectinload(Vehicle.associations).selectinload(VehicleResidentAssociation.user),
                selectinload(Vehicle.verifications),
                selectinload(Vehicle.documents),
                selectinload(Vehicle.parking_associations),
            )
            .order_by(Vehicle.created_at.desc())
            .offset(offset)
            .limit(size)
        )
        res = await self.session.execute(stmt)
        return list(res.scalars().all()), total

    async def get_vehicles_for_resident(
        self,
        society_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> list[Vehicle]:
        """Fetch all vehicles associated with a resident user."""
        stmt = (
            select(Vehicle)
            .join(
                VehicleResidentAssociation,
                VehicleResidentAssociation.vehicle_id == Vehicle.id,
            )
            .options(
                selectinload(Vehicle.associations).selectinload(VehicleResidentAssociation.unit),
                selectinload(Vehicle.associations).selectinload(VehicleResidentAssociation.user),
                selectinload(Vehicle.verifications),
                selectinload(Vehicle.documents),
                selectinload(Vehicle.parking_associations),
            )
            .where(
                Vehicle.society_id == society_id,
                VehicleResidentAssociation.user_id == user_id,
                VehicleResidentAssociation.status == "ACTIVE",
            )
            .order_by(VehicleResidentAssociation.is_primary.desc(), Vehicle.created_at.desc())
        )
        res = await self.session.execute(stmt)
        return list(res.scalars().all())

    async def save(self, vehicle: Vehicle) -> Vehicle:
        """Persist or update vehicle."""
        self.session.add(vehicle)
        await self.session.flush()
        return vehicle


class VehicleAssociationRepository:
    """Repository for VehicleResidentAssociation queries."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(
        self,
        association_id: uuid.UUID,
        society_id: uuid.UUID,
    ) -> VehicleResidentAssociation | None:
        """Fetch association by ID."""
        stmt = (
            select(VehicleResidentAssociation)
            .options(
                selectinload(VehicleResidentAssociation.unit),
                selectinload(VehicleResidentAssociation.user),
            )
            .where(
                VehicleResidentAssociation.id == association_id,
                VehicleResidentAssociation.society_id == society_id,
            )
        )
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def get_active_for_vehicle(
        self,
        society_id: uuid.UUID,
        vehicle_id: uuid.UUID,
    ) -> list[VehicleResidentAssociation]:
        """Fetch all active associations for a vehicle."""
        stmt = (
            select(VehicleResidentAssociation)
            .options(
                selectinload(VehicleResidentAssociation.unit),
                selectinload(VehicleResidentAssociation.user),
            )
            .where(
                VehicleResidentAssociation.society_id == society_id,
                VehicleResidentAssociation.vehicle_id == vehicle_id,
                VehicleResidentAssociation.status == "ACTIVE",
            )
        )
        res = await self.session.execute(stmt)
        return list(res.scalars().all())

    async def get_active_primary(
        self,
        society_id: uuid.UUID,
        unit_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> VehicleResidentAssociation | None:
        """Fetch active primary vehicle association for a specific (unit, user) pair."""
        stmt = select(VehicleResidentAssociation).where(
            VehicleResidentAssociation.society_id == society_id,
            VehicleResidentAssociation.unit_id == unit_id,
            VehicleResidentAssociation.user_id == user_id,
            VehicleResidentAssociation.is_primary.is_(True),
            VehicleResidentAssociation.status == "ACTIVE",
        )
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def find_existing_active(
        self,
        society_id: uuid.UUID,
        vehicle_id: uuid.UUID,
        user_id: uuid.UUID,
        unit_id: uuid.UUID,
    ) -> VehicleResidentAssociation | None:
        """Find existing active association for (vehicle, user, unit)."""
        stmt = select(VehicleResidentAssociation).where(
            VehicleResidentAssociation.society_id == society_id,
            VehicleResidentAssociation.vehicle_id == vehicle_id,
            VehicleResidentAssociation.user_id == user_id,
            VehicleResidentAssociation.unit_id == unit_id,
            VehicleResidentAssociation.status == "ACTIVE",
        )
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def save(self, association: VehicleResidentAssociation) -> VehicleResidentAssociation:
        self.session.add(association)
        await self.session.flush()
        return association


class VehicleVerificationRepository:
    """Repository for VehicleVerification history."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_history_for_vehicle(
        self,
        society_id: uuid.UUID,
        vehicle_id: uuid.UUID,
    ) -> list[VehicleVerification]:
        stmt = (
            select(VehicleVerification)
            .where(
                VehicleVerification.society_id == society_id,
                VehicleVerification.vehicle_id == vehicle_id,
            )
            .order_by(VehicleVerification.created_at.desc())
        )
        res = await self.session.execute(stmt)
        return list(res.scalars().all())

    async def save(self, verification: VehicleVerification) -> VehicleVerification:
        self.session.add(verification)
        await self.session.flush()
        return verification


class VehicleDocumentRepository:
    """Repository for VehicleDocument queries."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(
        self,
        document_id: uuid.UUID,
        society_id: uuid.UUID,
    ) -> VehicleDocument | None:
        stmt = select(VehicleDocument).where(
            VehicleDocument.id == document_id,
            VehicleDocument.society_id == society_id,
            VehicleDocument.archived_at.is_(None),
        )
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def get_for_vehicle(
        self,
        society_id: uuid.UUID,
        vehicle_id: uuid.UUID,
    ) -> list[VehicleDocument]:
        stmt = (
            select(VehicleDocument)
            .where(
                VehicleDocument.society_id == society_id,
                VehicleDocument.vehicle_id == vehicle_id,
                VehicleDocument.archived_at.is_(None),
            )
            .order_by(VehicleDocument.created_at.desc())
        )
        res = await self.session.execute(stmt)
        return list(res.scalars().all())

    async def save(self, document: VehicleDocument) -> VehicleDocument:
        self.session.add(document)
        await self.session.flush()
        return document

    async def delete(self, document: VehicleDocument) -> None:
        """Soft-archive document record without deleting physical file from storage."""
        document.archived_at = datetime.now(UTC)
        self.session.add(document)
        await self.session.flush()


class VehicleParkingRepository:
    """Repository for VehicleParkingAssociation queries."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(
        self,
        parking_id: uuid.UUID,
        society_id: uuid.UUID,
    ) -> VehicleParkingAssociation | None:
        stmt = select(VehicleParkingAssociation).where(
            VehicleParkingAssociation.id == parking_id,
            VehicleParkingAssociation.society_id == society_id,
        )
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def get_active_for_vehicle(
        self,
        society_id: uuid.UUID,
        vehicle_id: uuid.UUID,
    ) -> list[VehicleParkingAssociation]:
        stmt = select(VehicleParkingAssociation).where(
            VehicleParkingAssociation.society_id == society_id,
            VehicleParkingAssociation.vehicle_id == vehicle_id,
            VehicleParkingAssociation.status == "ACTIVE",
        )
        res = await self.session.execute(stmt)
        return list(res.scalars().all())

    async def get_for_vehicle(
        self,
        society_id: uuid.UUID,
        vehicle_id: uuid.UUID,
    ) -> list[VehicleParkingAssociation]:
        stmt = (
            select(VehicleParkingAssociation)
            .where(
                VehicleParkingAssociation.society_id == society_id,
                VehicleParkingAssociation.vehicle_id == vehicle_id,
            )
            .order_by(VehicleParkingAssociation.created_at.desc())
        )
        res = await self.session.execute(stmt)
        return list(res.scalars().all())

    async def save(self, parking: VehicleParkingAssociation) -> VehicleParkingAssociation:
        self.session.add(parking)
        await self.session.flush()
        return parking


class VehicleAccessRecordRepository:
    """Repository for append-only VehicleAccessRecord logs."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(
        self,
        record_id: uuid.UUID,
        society_id: uuid.UUID,
    ) -> VehicleAccessRecord | None:
        stmt = select(VehicleAccessRecord).where(
            VehicleAccessRecord.id == record_id,
            VehicleAccessRecord.society_id == society_id,
        )
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def search(
        self,
        society_id: uuid.UUID,
        query: str | None = None,
        vehicle_id: uuid.UUID | None = None,
        access_type: str | None = None,
        gate_identifier: str | None = None,
        page: int = 1,
        size: int = 50,
    ) -> tuple[list[VehicleAccessRecord], int]:
        base_stmt = select(VehicleAccessRecord).where(VehicleAccessRecord.society_id == society_id)

        if query:
            q_clean = query.strip()
            from apps.api.src.vehicles.domain.normalization import normalize_registration_number

            try:
                norm_q = normalize_registration_number(q_clean)
            except ValueError:
                norm_q = q_clean.upper()

            base_stmt = base_stmt.where(
                or_(
                    VehicleAccessRecord.registration_number_snapshot.ilike(f"%{q_clean}%"),
                    VehicleAccessRecord.normalized_registration_number_snapshot.ilike(f"%{norm_q}%"),
                    VehicleAccessRecord.gate_identifier.ilike(f"%{q_clean}%"),
                )
            )

        if vehicle_id:
            base_stmt = base_stmt.where(VehicleAccessRecord.vehicle_id == vehicle_id)
        if access_type:
            base_stmt = base_stmt.where(VehicleAccessRecord.access_type == access_type)
        if gate_identifier:
            base_stmt = base_stmt.where(VehicleAccessRecord.gate_identifier == gate_identifier)

        count_stmt = select(func.count()).select_from(base_stmt.subquery())
        total_res = await self.session.execute(count_stmt)
        total = total_res.scalar_one() or 0

        offset = (page - 1) * size
        stmt = base_stmt.order_by(VehicleAccessRecord.access_time.desc()).offset(offset).limit(size)
        res = await self.session.execute(stmt)
        return list(res.scalars().all()), total

    async def save(self, record: VehicleAccessRecord) -> VehicleAccessRecord:
        """Append new immutable access record."""
        self.session.add(record)
        await self.session.flush()
        return record

    async def update(self, *args, **kwargs) -> None:
        """Access records are immutable and cannot be updated."""
        raise VehicleAccessRecordImmutableError()

    async def delete(self, *args, **kwargs) -> None:
        """Access records are immutable and cannot be deleted."""
        raise VehicleAccessRecordImmutableError()
