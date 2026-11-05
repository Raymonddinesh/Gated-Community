"""Application Service for Complaint Communication & Comments."""

import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.complaints.domain.exceptions import (
    ComplaintCommentAccessDeniedError,
    ComplaintNotFoundError,
)
from apps.api.src.complaints.infrastructure.repositories import (
    ComplaintCommentRepository,
    ComplaintRepository,
)
from apps.api.src.complaints.schemas import ComplaintCommentCreateRequest
from apps.api.src.database.models.audit import AuditLog
from apps.api.src.database.models.complaint import ComplaintComment


class ComplaintCommentService:
    """Service managing public and internal comments on complaints."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.complaint_repo = ComplaintRepository(session)
        self.comment_repo = ComplaintCommentRepository(session)

    async def add_comment(
        self,
        society_id: uuid.UUID,
        complaint_id: uuid.UUID,
        author_user_id: uuid.UUID,
        data: ComplaintCommentCreateRequest,
        is_staff_or_admin: bool = False,
    ) -> ComplaintComment:
        """Add a comment to a complaint. Residents cannot post INTERNAL comments."""
        complaint = await self.complaint_repo.get_by_id(complaint_id, society_id)
        if not complaint:
            raise ComplaintNotFoundError(complaint_id)

        if data.comment_type == "INTERNAL" and not is_staff_or_admin:
            raise ComplaintCommentAccessDeniedError("Only authorized staff/admins can post internal comments")

        now = datetime.now(UTC)
        comment = ComplaintComment(
            id=uuid.uuid4(),
            society_id=society_id,
            complaint_id=complaint_id,
            author_user_id=author_user_id,
            comment_type=data.comment_type.value,
            body=data.body.strip(),
            created_at=now,
            updated_at=now,
        )
        await self.comment_repo.save(comment)

        # Audit event
        audit = AuditLog(
            id=uuid.uuid4(),
            society_id=society_id,
            actor_user_id=author_user_id,
            action="complaint.comment.add",
            entity_type="ComplaintComment",
            entity_id=str(comment.id),
            after_state={
                "complaint_id": str(complaint_id),
                "comment_type": data.comment_type.value,
            },
        )
        self.session.add(audit)
        await self.session.flush()

        return comment

    async def list_comments(
        self,
        society_id: uuid.UUID,
        complaint_id: uuid.UUID,
        include_internal: bool = False,
    ) -> list[ComplaintComment]:
        complaint = await self.complaint_repo.get_by_id(complaint_id, society_id)
        if not complaint:
            raise ComplaintNotFoundError(complaint_id)
        return await self.comment_repo.list_for_complaint(society_id, complaint_id, include_internal)
