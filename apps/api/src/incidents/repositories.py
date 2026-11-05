"""Phase 19 Incident Management Repositories."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from apps.api.src.database.models.incidents import (
    EmergencyContact,
    Incident,
    IncidentAcknowledgement,
    IncidentAction,
    IncidentAssignment,
    IncidentAttachment,
    IncidentCategory,
    IncidentEscalation,
    IncidentStatusHistory,
    IncidentTimeline,
)
from apps.api.src.incidents.concurrency import acquire_incident_number_lock


class IncidentCategoryRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, category_id: UUID) -> IncidentCategory | None:
        stmt = select(IncidentCategory).where(IncidentCategory.id == category_id)
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def get_by_code(self, society_id: UUID, code: str) -> IncidentCategory | None:
        stmt = select(IncidentCategory).where(
            or_(IncidentCategory.society_id == society_id, IncidentCategory.society_id.is_(None)),
            IncidentCategory.code == code,
            IncidentCategory.is_active.is_(True),
        )
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def list_categories(self, society_id: UUID) -> list[IncidentCategory]:
        stmt = (
            select(IncidentCategory)
            .where(
                or_(IncidentCategory.society_id == society_id, IncidentCategory.society_id.is_(None)),
                IncidentCategory.is_active.is_(True),
            )
            .order_by(IncidentCategory.name)
        )
        res = await self.session.execute(stmt)
        return list(res.scalars().all())

    async def create_category(self, category: IncidentCategory) -> IncidentCategory:
        self.session.add(category)
        await self.session.flush()
        return category


class EmergencyContactRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, contact_id: UUID) -> EmergencyContact | None:
        stmt = select(EmergencyContact).where(EmergencyContact.id == contact_id)
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def list_contacts(self, society_id: UUID) -> list[EmergencyContact]:
        stmt = (
            select(EmergencyContact)
            .where(
                or_(EmergencyContact.society_id == society_id, EmergencyContact.society_id.is_(None)),
                EmergencyContact.is_active.is_(True),
            )
            .order_by(EmergencyContact.display_order, EmergencyContact.name)
        )
        res = await self.session.execute(stmt)
        return list(res.scalars().all())

    async def create_contact(self, contact: EmergencyContact) -> EmergencyContact:
        self.session.add(contact)
        await self.session.flush()
        return contact

    async def update_contact(self, contact: EmergencyContact) -> EmergencyContact:
        await self.session.flush()
        return contact


class IncidentRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def generate_incident_number(self, society_id: UUID) -> str:
        """Generate sequential INC-YYYY-XXXXXX number under PostgreSQL transaction advisory lock."""
        await acquire_incident_number_lock(self.session, society_id)
        year = datetime.now().year
        prefix = f"INC-{year}-"

        stmt = (
            select(func.count(1))
            .select_from(Incident)
            .where(Incident.society_id == society_id, Incident.incident_number.like(f"{prefix}%"))
        )
        res = await self.session.execute(stmt)
        count = res.scalar() or 0
        return f"{prefix}{count + 1:06d}"

    async def create_incident(self, incident: Incident) -> Incident:
        self.session.add(incident)
        await self.session.flush()
        return incident

    async def get_by_id(self, incident_id: UUID, society_id: UUID) -> Incident | None:
        stmt = (
            select(Incident)
            .options(
                selectinload(Incident.category),
                selectinload(Incident.assignments),
                selectinload(Incident.actions),
                selectinload(Incident.escalations),
                selectinload(Incident.attachments),
                selectinload(Incident.acknowledgements),
            )
            .where(Incident.id == incident_id, Incident.society_id == society_id)
        )
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def get_by_number(self, incident_number: str, society_id: UUID) -> Incident | None:
        stmt = (
            select(Incident)
            .options(
                selectinload(Incident.category),
                selectinload(Incident.assignments),
                selectinload(Incident.actions),
                selectinload(Incident.escalations),
                selectinload(Incident.attachments),
                selectinload(Incident.acknowledgements),
            )
            .where(Incident.incident_number == incident_number, Incident.society_id == society_id)
        )
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def list_incidents(
        self,
        society_id: UUID,
        status: str | None = None,
        severity: str | None = None,
        category_id: UUID | None = None,
        reported_by_id: UUID | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Incident]:
        stmt = (
            select(Incident)
            .options(
                selectinload(Incident.category),
                selectinload(Incident.assignments),
            )
            .where(Incident.society_id == society_id)
        )

        if status:
            stmt = stmt.where(Incident.status == status)
        if severity:
            stmt = stmt.where(Incident.severity == severity)
        if category_id:
            stmt = stmt.where(Incident.category_id == category_id)
        if reported_by_id:
            stmt = stmt.where(Incident.reported_by_id == reported_by_id)

        stmt = stmt.order_by(Incident.created_at.desc()).limit(limit).offset(offset)
        res = await self.session.execute(stmt)
        return list(res.scalars().all())

    async def update_incident(self, incident: Incident) -> Incident:
        await self.session.flush()
        return incident

    async def create_assignment(self, assignment: IncidentAssignment) -> IncidentAssignment:
        self.session.add(assignment)
        await self.session.flush()
        return assignment

    async def create_timeline(self, timeline: IncidentTimeline) -> IncidentTimeline:
        self.session.add(timeline)
        await self.session.flush()
        return timeline

    async def list_timelines(self, incident_id: UUID, society_id: UUID) -> list[IncidentTimeline]:
        stmt = (
            select(IncidentTimeline)
            .where(IncidentTimeline.incident_id == incident_id, IncidentTimeline.society_id == society_id)
            .order_by(IncidentTimeline.created_at.asc())
        )
        res = await self.session.execute(stmt)
        return list(res.scalars().all())

    async def create_action(self, action: IncidentAction) -> IncidentAction:
        self.session.add(action)
        await self.session.flush()
        return action

    async def list_actions(self, incident_id: UUID, society_id: UUID) -> list[IncidentAction]:
        stmt = (
            select(IncidentAction)
            .where(IncidentAction.incident_id == incident_id, IncidentAction.society_id == society_id)
            .order_by(IncidentAction.created_at.desc())
        )
        res = await self.session.execute(stmt)
        return list(res.scalars().all())

    async def get_action_by_id(self, action_id: UUID, society_id: UUID) -> IncidentAction | None:
        stmt = select(IncidentAction).where(
            IncidentAction.id == action_id, IncidentAction.society_id == society_id
        )
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def update_action(self, action: IncidentAction) -> IncidentAction:
        await self.session.flush()
        return action

    async def create_escalation(self, escalation: IncidentEscalation) -> IncidentEscalation:
        self.session.add(escalation)
        await self.session.flush()
        return escalation

    async def list_escalations(self, incident_id: UUID, society_id: UUID) -> list[IncidentEscalation]:
        stmt = (
            select(IncidentEscalation)
            .where(IncidentEscalation.incident_id == incident_id, IncidentEscalation.society_id == society_id)
            .order_by(IncidentEscalation.escalated_at.desc())
        )
        res = await self.session.execute(stmt)
        return list(res.scalars().all())

    async def create_attachment(self, attachment: IncidentAttachment) -> IncidentAttachment:
        self.session.add(attachment)
        await self.session.flush()
        return attachment

    async def list_attachments(self, incident_id: UUID, society_id: UUID) -> list[IncidentAttachment]:
        stmt = (
            select(IncidentAttachment)
            .where(IncidentAttachment.incident_id == incident_id, IncidentAttachment.society_id == society_id)
            .order_by(IncidentAttachment.created_at.desc())
        )
        res = await self.session.execute(stmt)
        return list(res.scalars().all())

    async def create_status_history(self, history: IncidentStatusHistory) -> IncidentStatusHistory:
        self.session.add(history)
        await self.session.flush()
        return history

    async def create_acknowledgement(self, ack: IncidentAcknowledgement) -> IncidentAcknowledgement:
        self.session.add(ack)
        await self.session.flush()
        return ack
