"""Phase 14 Asset & Facility Document Service."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.database.models.facility_asset import AssetDocument, FacilityDocument
from apps.api.src.facility_asset.repositories import (
    AssetDocumentRepository,
    FacilityDocumentRepository,
)
from apps.api.src.facility_asset.schemas import (
    AssetDocumentCreate,
    FacilityDocumentCreate,
)


class DocumentService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.asset_doc_repo = AssetDocumentRepository(db)
        self.facility_doc_repo = FacilityDocumentRepository(db)

    async def add_asset_document(
        self, society_id: UUID, user_id: UUID | None, asset_id: UUID, payload: AssetDocumentCreate
    ) -> AssetDocument:
        doc = AssetDocument(
            society_id=society_id,
            asset_id=asset_id,
            document_type=payload.document_type.value,
            title=payload.title,
            file_path=payload.file_path,
            file_size_bytes=payload.file_size_bytes,
            mime_type=payload.mime_type,
            uploaded_by_user_id=user_id,
        )
        return await self.asset_doc_repo.create(doc)

    async def list_asset_documents(self, society_id: UUID, asset_id: UUID) -> list[AssetDocument]:
        return await self.asset_doc_repo.list_by_asset(society_id, asset_id)

    async def add_facility_document(
        self, society_id: UUID, user_id: UUID | None, facility_id: UUID, payload: FacilityDocumentCreate
    ) -> FacilityDocument:
        doc = FacilityDocument(
            society_id=society_id,
            facility_id=facility_id,
            document_type=payload.document_type.value,
            title=payload.title,
            file_path=payload.file_path,
            file_size_bytes=payload.file_size_bytes,
            mime_type=payload.mime_type,
            uploaded_by_user_id=user_id,
        )
        return await self.facility_doc_repo.create(doc)

    async def list_facility_documents(self, society_id: UUID, facility_id: UUID) -> list[FacilityDocument]:
        return await self.facility_doc_repo.list_by_facility(society_id, facility_id)
