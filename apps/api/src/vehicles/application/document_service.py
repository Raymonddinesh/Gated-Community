"""Application service for Vehicle Documents."""

import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.database.models.vehicle import VehicleDocument
from apps.api.src.vehicles.domain.exceptions import (
    VehicleDocumentNotFoundError,
    VehicleNotFoundError,
)
from apps.api.src.vehicles.infrastructure.repositories import (
    VehicleDocumentRepository,
    VehicleRepository,
)
from apps.api.src.vehicles.schemas import VehicleDocumentCreateRequest


class VehicleDocumentService:
    """Service managing metadata and references for vehicle documents (RC, Insurance, PUC, etc.)."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.doc_repo = VehicleDocumentRepository(session)
        self.vehicle_repo = VehicleRepository(session)

    async def add_document(
        self,
        society_id: uuid.UUID,
        vehicle_id: uuid.UUID,
        uploaded_by_user_id: uuid.UUID | None,
        data: VehicleDocumentCreateRequest,
    ) -> VehicleDocument:
        """Register a new document against a vehicle."""
        veh = await self.vehicle_repo.get_by_id(vehicle_id, society_id)
        if not veh:
            raise VehicleNotFoundError(vehicle_id)

        doc = VehicleDocument(
            id=uuid.uuid4(),
            society_id=society_id,
            vehicle_id=vehicle_id,
            document_type=data.document_type.value,
            document_number=data.document_number.strip() if data.document_number else None,
            file_key=data.file_key.strip(),
            file_name=data.file_name.strip(),
            file_size_bytes=data.file_size_bytes,
            content_type=data.content_type.strip(),
            valid_from=data.valid_from,
            valid_to=data.valid_to,
            uploaded_by=uploaded_by_user_id,
            created_at=datetime.now(UTC),
        )

        await self.doc_repo.save(doc)
        return doc

    async def list_documents(
        self,
        society_id: uuid.UUID,
        vehicle_id: uuid.UUID,
    ) -> list[VehicleDocument]:
        """List all documents for a vehicle."""
        veh = await self.vehicle_repo.get_by_id(vehicle_id, society_id)
        if not veh:
            raise VehicleNotFoundError(vehicle_id)
        return await self.doc_repo.get_for_vehicle(society_id, vehicle_id)

    async def get_document(
        self,
        society_id: uuid.UUID,
        document_id: uuid.UUID,
    ) -> VehicleDocument:
        """Fetch single document by ID."""
        doc = await self.doc_repo.get_by_id(document_id, society_id)
        if not doc:
            raise VehicleDocumentNotFoundError(document_id)
        return doc

    async def delete_document(
        self,
        society_id: uuid.UUID,
        document_id: uuid.UUID,
    ) -> None:
        """Remove document record."""
        doc = await self.get_document(society_id, document_id)
        await self.doc_repo.delete(doc)
