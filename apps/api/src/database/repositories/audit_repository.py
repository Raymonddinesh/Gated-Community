"""Repository for Append-Only Tenant-Aware Audit Logs."""

import uuid
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.database.models.audit import AuditLog


class AuditRepository:
    """Data access layer for appending audit trail events."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def log_event(
        self,
        action: str,
        entity_type: str,
        entity_id: str,
        society_id: UUID | None = None,
        actor_user_id: UUID | None = None,
        request_id: str | None = None,
        correlation_id: str | None = None,
        before_state: dict[str, Any] | None = None,
        after_state: dict[str, Any] | None = None,
        diff: dict[str, Any] | None = None,
    ) -> AuditLog:
        """Append an unalterable audit log entry."""
        log_entry = AuditLog(
            id=uuid.uuid4(),
            society_id=society_id,
            actor_user_id=actor_user_id,
            action=action,
            entity_type=entity_type,
            entity_id=str(entity_id),
            request_id=request_id,
            correlation_id=correlation_id,
            before_state=before_state,
            after_state=after_state,
            diff=diff,
            created_at=datetime.now(UTC),
        )
        self.session.add(log_entry)
        await self.session.flush()
        return log_entry
