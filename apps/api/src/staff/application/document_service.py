"""Staff Document Application Service."""

import hashlib
import re
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.core.exceptions import AppException
from apps.api.src.database.models.identity import User
from apps.api.src.database.models.staff import StaffDocument
from apps.api.src.staff.domain.enums import StaffDocumentType
from apps.api.src.staff.domain.exceptions import (
    StaffDocumentNotFoundError,
    StaffNotFoundError,
)
from apps.api.src.staff.infrastructure.repositories import (
    StaffDocumentRepository,
    StaffProfileRepository,
)

ALLOWED_MIME_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}
MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB


class StaffDocumentService:
    """Application Service managing secure Staff Document metadata and uploads."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = StaffDocumentRepository(session)
        self.staff_repo = StaffProfileRepository(session)

    async def upload_document(
        self,
        staff_id: uuid.UUID,
        society_id: uuid.UUID,
        original_filename: str,
        content_type: str,
        file_bytes: bytes,
        document_type: StaffDocumentType,
        uploaded_by_user: User,
    ) -> StaffDocument:
        """Validate and log metadata for uploaded staff document."""
        # 1. Check staff exists and matches society
        staff = await self.staff_repo.get_by_id(staff_id, society_id)
        if not staff:
            raise StaffNotFoundError(str(staff_id))

        # 2. File size validation
        file_size = len(file_bytes)
        if file_size > MAX_FILE_SIZE_BYTES:
            raise AppException(code="FILE_SIZE_EXCEEDED", message="File size exceeds 10MB limit.")

        # 3. MIME type validation
        if content_type.lower() not in ALLOWED_MIME_TYPES:
            raise AppException(code="INVALID_MIME_TYPE", message=f"Unsupported MIME type: {content_type}")

        # 4. Compute checksum and sanitize filename
        checksum = hashlib.sha256(file_bytes).hexdigest()
        sanitized_filename = re.sub(r"[^a-zA-Z0-9_.-]", "_", original_filename)

        # 5. Generate private storage key (no public URL)
        storage_key = f"staff-docs/{society_id}/{staff_id}/{uuid.uuid4().hex}_{sanitized_filename}"

        doc = StaffDocument(
            society_id=society_id,
            staff_id=staff.id,
            document_type=document_type.value,
            storage_key=storage_key,
            original_filename=sanitized_filename,
            content_type=content_type,
            file_size=file_size,
            checksum=checksum,
            uploaded_by_user_id=uploaded_by_user.id,
        )

        return await self.repo.create_document(doc)

    async def list_documents(self, staff_id: uuid.UUID, society_id: uuid.UUID) -> list[StaffDocument]:
        """List active documents for a staff member."""
        staff = await self.staff_repo.get_by_id(staff_id, society_id)
        if not staff:
            raise StaffNotFoundError(str(staff_id))
        return await self.repo.list_documents(staff_id, society_id)

    async def archive_document(self, doc_id: uuid.UUID, society_id: uuid.UUID) -> StaffDocument:
        """Soft-archive staff document."""
        doc = await self.repo.get_document(doc_id, society_id)
        if not doc:
            raise StaffDocumentNotFoundError(str(doc_id))
        return await self.repo.archive_document(doc)
