"""Application service for Gate Vehicle Access Records and Provider Dispatch."""

import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.database.models.vehicle import VehicleAccessRecord
from apps.api.src.vehicles.domain.exceptions import VehicleAccessRecordImmutableError
from apps.api.src.vehicles.domain.providers import get_vehicle_access_provider
from apps.api.src.vehicles.infrastructure.repositories import (
    VehicleAccessRecordRepository,
    VehicleRepository,
)
from apps.api.src.vehicles.schemas import VehicleAccessRecordCreateRequest


class VehicleAccessService:
    """Service handling gate access entry/exit logs, hardware provider dispatch, and queries."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.access_repo = VehicleAccessRecordRepository(session)
        self.vehicle_repo = VehicleRepository(session)

    async def record_access(
        self,
        society_id: uuid.UUID,
        operator_user_id: uuid.UUID | None,
        data: VehicleAccessRecordCreateRequest,
    ) -> VehicleAccessRecord:
        """
        Record a vehicle gate event (entry or exit).
        Dispatches detection payload through the designated provider abstraction.
        Matches against registered society vehicles if present.
        Appends an immutable audit log.
        """
        provider = get_vehicle_access_provider(data.source_provider)
        detection = await provider.process_detection(
            {
                "registration_number": data.registration_number,
                "captured_image_ref": data.captured_image_ref,
                "confidence_score": data.confidence_score,
            }
        )

        # Attempt to link with known active registered vehicle in this society
        matched_vehicle = await self.vehicle_repo.get_active_by_normalized_reg(
            society_id=society_id,
            normalized_reg=detection.normalized_plate,
        )

        record = VehicleAccessRecord(
            id=uuid.uuid4(),
            society_id=society_id,
            vehicle_id=matched_vehicle.id if matched_vehicle else None,
            registration_number_snapshot=detection.raw_plate,
            normalized_registration_number_snapshot=detection.normalized_plate,
            access_type=data.access_type.value,
            gate_identifier=data.gate_identifier.strip(),
            access_time=datetime.now(UTC),
            detection_method=detection.detection_method,
            captured_image_ref=detection.captured_image_ref,
            operator_user_id=operator_user_id,
            source_provider=detection.source_provider,
            confidence_score=detection.confidence_score,
            notes=data.notes,
            created_at=datetime.now(UTC),
        )

        await self.access_repo.save(record)
        return record

    async def search_records(
        self,
        society_id: uuid.UUID,
        query: str | None = None,
        vehicle_id: uuid.UUID | None = None,
        access_type: str | None = None,
        gate_identifier: str | None = None,
        page: int = 1,
        size: int = 50,
    ) -> tuple[list[VehicleAccessRecord], int]:
        """Search access history."""
        return await self.access_repo.search(
            society_id=society_id,
            query=query,
            vehicle_id=vehicle_id,
            access_type=access_type,
            gate_identifier=gate_identifier,
            page=page,
            size=size,
        )

    async def prevent_modification(self) -> None:
        """Guard method confirming access records are immutable. Raises VehicleAccessRecordImmutableError."""
        raise VehicleAccessRecordImmutableError()

    async def update_record(self, *args, **kwargs) -> None:
        """Vehicle access records are append-only audit logs and cannot be updated."""
        raise VehicleAccessRecordImmutableError()

    async def delete_record(self, *args, **kwargs) -> None:
        """Vehicle access records are append-only audit logs and cannot be deleted."""
        raise VehicleAccessRecordImmutableError()
