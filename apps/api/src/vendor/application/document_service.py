"""Vendor Document Application Service."""

from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.database.models.vendor import VendorDocument
from apps.api.src.vendor.domain.exceptions import (
    VendorDocumentNotFoundException,
    VendorNotFoundException,
)
from apps.api.src.vendor.infrastructure.repositories import (
    VendorDocumentRepository,
    VendorProfileRepository,
)
from apps.api.src.vendor.schemas import VendorDocumentCreate


class VendorDocumentService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.vendor_repo = VendorProfileRepository(db)
        self.doc_repo = VendorDocumentRepository(db)

    async def upload_document(
        self,
        vendor_id: UUID,
        data: VendorDocumentCreate,
        storage_key: str,
        society_id: UUID,
        current_user_id: UUID,
    ) -> VendorDocument:
        vendor = await self.vendor_repo.get_by_id(vendor_id, society_id)
        if not vendor:
            raise VendorNotFoundException(str(vendor_id))

        doc = VendorDocument(
            society_id=society_id,
            vendor_id=vendor_id,
            document_type=data.document_type.value,
            storage_key=storage_key,
            original_filename=data.original_filename,
            content_type=data.content_type,
            file_size=data.file_size,
            checksum=data.checksum,
            uploaded_by_user_id=current_user_id,
        )
        return await self.doc_repo.create(doc)

    async def list_documents(
        self, vendor_id: UUID, society_id: UUID, include_archived: bool = False
    ) -> list[VendorDocument]:
        vendor = await self.vendor_repo.get_by_id(vendor_id, society_id)
        if not vendor:
            raise VendorNotFoundException(str(vendor_id))
        return await self.doc_repo.list_by_vendor(vendor_id, society_id, include_archived=include_archived)

    async def archive_document(self, document_id: UUID, society_id: UUID) -> VendorDocument:
        doc = await self.doc_repo.get_by_id(document_id, society_id)
        if not doc:
            raise VendorDocumentNotFoundException(str(document_id))

        doc.archived_at = datetime.utcnow()
        await self.db.flush()
        return doc
