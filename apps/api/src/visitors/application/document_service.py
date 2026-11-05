"""Application Service for Visitor Identification Photos and Documents."""

import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.database.models.visitor import VisitorDocument
from apps.api.src.visitors.domain.exceptions import (
    VisitorDocumentNotFoundError,
    VisitorNotFoundError,
)
from apps.api.src.visitors.infrastructure.repositories import (
    VisitorDocumentRepository,
    VisitorRepository,
)
from apps.api.src.visitors.schemas import VisitorDocumentCreateRequest


class VisitorDocumentService:
    """Service managing metadata and object storage references for visitor documents/photos."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.doc_repo = VisitorDocumentRepository(session)
        self.visitor_repo = VisitorRepository(session)

    async def add_document(
        self,
        society_id: uuid.UUID,
        visitor_id: uuid.UUID,
        uploaded_by_user_id: uuid.UUID | None,
        data: VisitorDocumentCreateRequest,
    ) -> VisitorDocument:
        """Register document metadata for a visitor profile."""
        visitor = await self.visitor_repo.get_by_id(visitor_id, society_id)
        if not visitor:
            raise VisitorNotFoundError(visitor_id)

        doc = VisitorDocument(
            id=uuid.uuid4(),
            society_id=society_id,
            visitor_id=visitor_id,
            document_type=data.document_type.value,
            file_key=data.file_key.strip(),
            file_name=data.file_name.strip(),
            file_size_bytes=data.file_size_bytes,
            content_type=data.content_type.strip(),
            uploaded_by=uploaded_by_user_id,
            created_at=datetime.now(UTC),
        )
        await self.doc_repo.save(doc)

        # Update visitor photo reference if document type is PHOTO
        if data.document_type.value == "PHOTO":
            visitor.photo_file_key = data.file_key.strip()
            await self.visitor_repo.save(visitor)

        return doc

    async def list_documents(
        self,
        society_id: uuid.UUID,
        visitor_id: uuid.UUID,
    ) -> list[VisitorDocument]:
        """List active (non-archived) documents for a visitor."""
        visitor = await self.visitor_repo.get_by_id(visitor_id, society_id)
        if not visitor:
            raise VisitorNotFoundError(visitor_id)
        return await self.doc_repo.get_for_visitor(society_id, visitor_id)

    async def get_document(
        self,
        society_id: uuid.UUID,
        document_id: uuid.UUID,
    ) -> VisitorDocument:
        """Fetch single document by ID."""
        doc = await self.doc_repo.get_by_id(document_id, society_id)
        if not doc:
            raise VisitorDocumentNotFoundError(document_id)
        return doc

    async def delete_document(
        self,
        society_id: uuid.UUID,
        document_id: uuid.UUID,
    ) -> None:
        """Soft-archive document record."""
        doc = await self.get_document(society_id, document_id)
        await self.doc_repo.delete(doc)
