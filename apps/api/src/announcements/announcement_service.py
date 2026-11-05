"""Phase 16 Announcement Domain Service."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.announcements.audience_resolver import AnnouncementAudienceResolver
from apps.api.src.announcements.concurrency import generate_announcement_number
from apps.api.src.announcements.enums import AnnouncementPriority, AnnouncementStatus, ScheduleStatus
from apps.api.src.announcements.event_hooks import AnnouncementEventHooks
from apps.api.src.announcements.exceptions import (
    AcknowledgementNotRequiredError,
    AlreadyAcknowledgedError,
    AnnouncementNotFoundError,
    InvalidPublicationTimeError,
)
from apps.api.src.announcements.repositories import (
    AnnouncementAcknowledgementRepository,
    AnnouncementAttachmentRepository,
    AnnouncementAudienceRepository,
    AnnouncementReadReceiptRepository,
    AnnouncementRepository,
    AnnouncementScheduleRepository,
    AnnouncementStatusHistoryRepository,
    AnnouncementVersionRepository,
)
from apps.api.src.announcements.schemas import (
    AnnouncementCreate,
    AnnouncementMetricsResponse,
    AnnouncementScheduleCreate,
    AnnouncementUpdate,
)
from apps.api.src.announcements.state_machine import AnnouncementStateMachine
from apps.api.src.database.models.announcements import (
    Announcement,
    AnnouncementAcknowledgement,
    AnnouncementAttachment,
    AnnouncementAudience,
    AnnouncementReadReceipt,
    AnnouncementSchedule,
    AnnouncementStatusHistory,
    AnnouncementVersion,
)


class AnnouncementService:
    """Core domain service for announcement lifecycle, audience resolution, and tracking."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = AnnouncementRepository(db)
        self.audience_repo = AnnouncementAudienceRepository(db)
        self.attachment_repo = AnnouncementAttachmentRepository(db)
        self.ack_repo = AnnouncementAcknowledgementRepository(db)
        self.read_repo = AnnouncementReadReceiptRepository(db)
        self.schedule_repo = AnnouncementScheduleRepository(db)
        self.history_repo = AnnouncementStatusHistoryRepository(db)
        self.version_repo = AnnouncementVersionRepository(db)
        self.audience_resolver = AnnouncementAudienceResolver(db)

    # ---------------------------------------------------------------------------
    # Announcement Lifecycle & Creation
    # ---------------------------------------------------------------------------

    async def create_announcement(
        self,
        society_id: UUID,
        author_id: UUID,
        payload: AnnouncementCreate,
    ) -> Announcement:
        if payload.published_at and payload.expires_at and payload.published_at >= payload.expires_at:
            raise InvalidPublicationTimeError("published_at must be prior to expires_at")

        # Validate audience targets against tenant
        for aud in payload.audiences:
            await self.audience_resolver.validate_audience_target_tenant(
                society_id,
                aud.audience_type,
                aud.target_block_id,
                aud.target_floor_id,
                aud.target_unit_id,
                aud.target_user_id,
            )

        number = await generate_announcement_number(self.db, society_id)

        announcement = Announcement(
            society_id=society_id,
            announcement_number=number,
            title=payload.title,
            summary=payload.summary,
            body=payload.body,
            priority=payload.priority.value,
            status=AnnouncementStatus.DRAFT.value,
            author_id=author_id,
            requires_acknowledgement=payload.requires_acknowledgement,
            is_pinned=payload.is_pinned,
            published_at=payload.published_at,
            expires_at=payload.expires_at,
            version_number=1,
        )
        announcement = await self.repo.create(announcement)

        # Create audiences
        if payload.audiences:
            audiences = [
                AnnouncementAudience(
                    society_id=society_id,
                    announcement_id=announcement.id,
                    audience_type=a.audience_type.value,
                    target_block_id=a.target_block_id,
                    target_floor_id=a.target_floor_id,
                    target_unit_id=a.target_unit_id,
                    target_user_id=a.target_user_id,
                    role_filter=a.role_filter.value if a.role_filter else None,
                )
                for a in payload.audiences
            ]
            await self.audience_repo.create_many(audiences)

        # Create attachments
        if payload.attachments:
            attachments = [
                AnnouncementAttachment(
                    society_id=society_id,
                    announcement_id=announcement.id,
                    file_name=att.file_name,
                    file_size=att.file_size,
                    mime_type=att.mime_type,
                    storage_object_key=att.storage_object_key,
                    uploaded_by=author_id,
                )
                for att in payload.attachments
            ]
            await self.attachment_repo.create_many(attachments)

        # Log initial status history
        history = AnnouncementStatusHistory(
            society_id=society_id,
            announcement_id=announcement.id,
            old_status="",
            new_status=AnnouncementStatus.DRAFT.value,
            changed_by_user_id=author_id,
            reason="Initial announcement draft creation",
        )
        await self.history_repo.create(history)

        AnnouncementEventHooks.on_announcement_created(
            announcement.id, society_id, author_id, number, announcement.priority
        )

        return await self.repo.get_by_id(society_id, announcement.id)  # type: ignore[return-value]

    async def update_announcement(
        self,
        society_id: UUID,
        announcement_id: UUID,
        editor_user_id: UUID,
        payload: AnnouncementUpdate,
    ) -> Announcement:
        announcement = await self.repo.get_by_id(society_id, announcement_id)
        if not announcement:
            raise AnnouncementNotFoundError(f"Announcement {announcement_id} not found")

        is_published = announcement.status == AnnouncementStatus.PUBLISHED.value

        # If modifying published content materially, record AnnouncementVersion snapshot
        if is_published and (payload.title or payload.body or payload.summary):
            version_snapshot = AnnouncementVersion(
                society_id=society_id,
                announcement_id=announcement.id,
                version_number=announcement.version_number,
                title=announcement.title,
                summary=announcement.summary,
                body=announcement.body,
                priority=announcement.priority,
                edited_by_user_id=editor_user_id,
                edit_reason=payload.edit_reason or "Material update after publication",
            )
            await self.version_repo.create(version_snapshot)
            announcement.version_number += 1

        update_data = payload.model_dump(exclude_unset=True, exclude={"edit_reason"})
        for k, v in update_data.items():
            if v is not None:
                setattr(announcement, k, v.value if isinstance(v, AnnouncementPriority) else v)

        await self.db.flush()

        AnnouncementEventHooks.on_announcement_updated(
            announcement.id, society_id, announcement.version_number
        )
        return await self.repo.get_by_id(society_id, announcement.id)  # type: ignore[return-value]

    # ---------------------------------------------------------------------------
    # Status Workflow Transitions
    # ---------------------------------------------------------------------------

    async def _change_status(
        self,
        society_id: UUID,
        announcement_id: UUID,
        user_id: UUID,
        target_status: AnnouncementStatus,
        reason: str | None = None,
    ) -> Announcement:
        announcement = await self.repo.get_by_id(society_id, announcement_id)
        if not announcement:
            raise AnnouncementNotFoundError(f"Announcement {announcement_id} not found")

        old_status = AnnouncementStatus(announcement.status)
        AnnouncementStateMachine.validate_transition(old_status, target_status)

        announcement.status = target_status.value

        if target_status == AnnouncementStatus.PUBLISHED:
            announcement.publisher_id = user_id
            if not announcement.published_at:
                announcement.published_at = datetime.now(UTC)

        await self.db.flush()

        history = AnnouncementStatusHistory(
            society_id=society_id,
            announcement_id=announcement.id,
            old_status=old_status.value,
            new_status=target_status.value,
            changed_by_user_id=user_id,
            reason=reason or f"Transition to {target_status.value}",
        )
        await self.history_repo.create(history)

        return await self.repo.get_by_id(society_id, announcement.id)  # type: ignore[return-value]

    async def submit_announcement(
        self, society_id: UUID, announcement_id: UUID, user_id: UUID
    ) -> Announcement:
        ann = await self._change_status(
            society_id, announcement_id, user_id, AnnouncementStatus.PENDING_REVIEW, "Submitted for review"
        )
        AnnouncementEventHooks.on_announcement_submitted(ann.id, society_id, ann.announcement_number)
        return ann

    async def approve_announcement(
        self, society_id: UUID, announcement_id: UUID, approver_id: UUID, reason: str | None = None
    ) -> Announcement:
        ann = await self._change_status(
            society_id,
            announcement_id,
            approver_id,
            AnnouncementStatus.APPROVED,
            reason or "Approved by admin",
        )
        AnnouncementEventHooks.on_announcement_approved(
            ann.id, society_id, approver_id, ann.announcement_number
        )
        return ann

    async def reject_announcement(
        self, society_id: UUID, announcement_id: UUID, reviewer_id: UUID, reason: str | None = None
    ) -> Announcement:
        return await self._change_status(
            society_id,
            announcement_id,
            reviewer_id,
            AnnouncementStatus.REJECTED,
            reason or "Rejected during review",
        )

    async def publish_announcement(
        self, society_id: UUID, announcement_id: UUID, publisher_id: UUID
    ) -> Announcement:
        ann = await self._change_status(
            society_id, announcement_id, publisher_id, AnnouncementStatus.PUBLISHED, "Published immediately"
        )
        AnnouncementEventHooks.on_announcement_published(
            ann.id, society_id, ann.announcement_number, ann.priority, ann.requires_acknowledgement
        )
        return ann

    async def schedule_announcement(
        self, society_id: UUID, announcement_id: UUID, publisher_id: UUID, payload: AnnouncementScheduleCreate
    ) -> Announcement:
        now = datetime.now(UTC)
        publish_at = payload.publish_at
        if publish_at.tzinfo is None:
            publish_at = publish_at.replace(tzinfo=UTC)

        if publish_at <= now:
            raise InvalidPublicationTimeError("Schedule publish_at must be in the future")

        if payload.expires_at:
            exp_at = payload.expires_at
            if exp_at.tzinfo is None:
                exp_at = exp_at.replace(tzinfo=UTC)
            if publish_at >= exp_at:
                raise InvalidPublicationTimeError("publish_at must be prior to expires_at")

        ann = await self._change_status(
            society_id,
            announcement_id,
            publisher_id,
            AnnouncementStatus.SCHEDULED,
            "Scheduled for deferred publication",
        )
        ann.published_at = publish_at
        ann.expires_at = payload.expires_at
        await self.db.flush()

        schedule = AnnouncementSchedule(
            society_id=society_id,
            announcement_id=ann.id,
            publish_at=publish_at,
            expires_at=payload.expires_at,
            status=ScheduleStatus.PENDING.value,
        )
        await self.schedule_repo.create(schedule)

        AnnouncementEventHooks.on_announcement_scheduled(
            ann.id, society_id, publish_at.isoformat(), ann.announcement_number
        )
        return ann

    async def expire_announcement(
        self, society_id: UUID, announcement_id: UUID, user_id: UUID
    ) -> Announcement:
        ann = await self._change_status(
            society_id, announcement_id, user_id, AnnouncementStatus.EXPIRED, "Manually expired"
        )
        AnnouncementEventHooks.on_announcement_expired(ann.id, society_id, ann.announcement_number)
        return ann

    async def archive_announcement(
        self, society_id: UUID, announcement_id: UUID, user_id: UUID
    ) -> Announcement:
        return await self._change_status(
            society_id, announcement_id, user_id, AnnouncementStatus.ARCHIVED, "Archived"
        )

    # ---------------------------------------------------------------------------
    # Read & Acknowledgement Tracking
    # ---------------------------------------------------------------------------

    async def mark_as_read(self, society_id: UUID, announcement_id: UUID, user_id: UUID) -> None:
        ann = await self.repo.get_by_id(society_id, announcement_id)
        if not ann:
            raise AnnouncementNotFoundError(f"Announcement {announcement_id} not found")

        existing = await self.read_repo.get_user_read(society_id, announcement_id, user_id)
        if not existing:
            read_receipt = AnnouncementReadReceipt(
                society_id=society_id,
                announcement_id=announcement_id,
                user_id=user_id,
            )
            await self.read_repo.create(read_receipt)

    async def acknowledge_announcement(
        self, society_id: UUID, announcement_id: UUID, user_id: UUID
    ) -> AnnouncementAcknowledgement:
        ann = await self.repo.get_by_id(society_id, announcement_id)
        if not ann:
            raise AnnouncementNotFoundError(f"Announcement {announcement_id} not found")

        if not ann.requires_acknowledgement:
            raise AcknowledgementNotRequiredError(
                "This announcement does not require explicit acknowledgement"
            )

        existing = await self.ack_repo.get_user_ack(society_id, announcement_id, user_id, ann.version_number)
        if existing:
            raise AlreadyAcknowledgedError("User has already acknowledged this announcement version")

        ack = AnnouncementAcknowledgement(
            society_id=society_id,
            announcement_id=announcement_id,
            user_id=user_id,
            version_number=ann.version_number,
        )
        ack = await self.ack_repo.create(ack)

        AnnouncementEventHooks.on_announcement_acknowledged(ann.id, society_id, user_id, ann.version_number)
        return ack

    # ---------------------------------------------------------------------------
    # Queries & Metrics
    # ---------------------------------------------------------------------------

    async def get_announcement(self, society_id: UUID, announcement_id: UUID, user_id: UUID) -> Announcement:
        ann = await self.repo.get_by_id(society_id, announcement_id)
        if not ann:
            raise AnnouncementNotFoundError(f"Announcement {announcement_id} not found")

        # Audience eligibility check
        is_eligible = await self.audience_resolver.is_user_eligible(society_id, ann, user_id, ann.audiences)
        if not is_eligible:
            raise AnnouncementNotFoundError(f"Announcement {announcement_id} not found for user")

        return ann

    async def list_announcements_for_user(
        self,
        society_id: UUID,
        user_id: UUID,
        status: AnnouncementStatus | None = None,
        priority: AnnouncementPriority | None = None,
        page: int = 1,
        size: int = 50,
    ) -> tuple[list[Announcement], int]:
        all_items, _ = await self.repo.list_announcements(
            society_id=society_id,
            status=status or AnnouncementStatus.PUBLISHED,
            priority=priority,
            page=1,
            size=100,
        )

        filtered = []
        for ann in all_items:
            if await self.audience_resolver.is_user_eligible(society_id, ann, user_id, ann.audiences):
                filtered.append(ann)

        total = len(filtered)
        offset = (page - 1) * size
        paged = filtered[offset : offset + size]
        return paged, total

    async def get_metrics(self, society_id: UUID, announcement_id: UUID) -> AnnouncementMetricsResponse:
        ann = await self.repo.get_by_id(society_id, announcement_id)
        if not ann:
            raise AnnouncementNotFoundError(f"Announcement {announcement_id} not found")

        reads = await self.read_repo.count_reads(society_id, announcement_id)
        acks = await self.ack_repo.count_acknowledgements(society_id, announcement_id)

        return AnnouncementMetricsResponse(
            announcement_id=ann.id,
            society_id=society_id,
            total_read_count=reads,
            total_acknowledged_count=acks,
            version_number=ann.version_number,
        )
