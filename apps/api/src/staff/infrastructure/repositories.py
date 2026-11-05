"""Infrastructure Repositories for Staff Workforce Management."""

import uuid
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.database.models.staff import (
    StaffContact,
    StaffDocument,
    StaffProfile,
    StaffRole,
    StaffRoleAssignment,
    StaffStatusHistory,
    StaffTeam,
    StaffTeamMembership,
)
from apps.api.src.staff.domain.concurrency import acquire_staff_code_lock


class StaffProfileRepository:
    """Async repository for StaffProfile ORM persistence."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def generate_next_staff_code(self, society_id: uuid.UUID, year: int) -> str:
        """Generate next STF-YYYY-XXXXXX staff code using PostgreSQL transaction advisory locks."""
        await acquire_staff_code_lock(self.session, society_id, year)
        prefix = f"STF-{year}-"
        query = select(func.count(StaffProfile.id)).where(
            StaffProfile.society_id == society_id,
            StaffProfile.staff_code.like(f"{prefix}%"),
        )
        count = (await self.session.execute(query)).scalar() or 0
        return f"{prefix}{count + 1:06d}"

    async def create_staff(self, staff: StaffProfile, contact: StaffContact) -> StaffProfile:
        """Persist staff profile and contact."""
        self.session.add(staff)
        await self.session.flush()
        contact.staff_id = staff.id
        contact.society_id = staff.society_id
        self.session.add(contact)
        await self.session.flush()
        return staff

    async def get_by_id(self, staff_id: uuid.UUID, society_id: uuid.UUID) -> StaffProfile | None:
        """Fetch staff profile by ID and society_id."""
        query = select(StaffProfile).where(
            StaffProfile.id == staff_id,
            StaffProfile.society_id == society_id,
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_by_code(self, staff_code: str, society_id: uuid.UUID) -> StaffProfile | None:
        """Fetch staff profile by code and society_id."""
        query = select(StaffProfile).where(
            StaffProfile.staff_code == staff_code,
            StaffProfile.society_id == society_id,
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def list_staff(
        self,
        society_id: uuid.UUID,
        status: str | None = None,
        engagement_type: str | None = None,
        role_id: uuid.UUID | None = None,
        team_id: uuid.UUID | None = None,
        search: str | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> list[StaffProfile]:
        """List staff profiles with optional status, engagement, role, and search filters."""
        query = select(StaffProfile).where(StaffProfile.society_id == society_id)

        if status:
            query = query.where(StaffProfile.status == status)
        if engagement_type:
            query = query.where(StaffProfile.engagement_type == engagement_type)
        if role_id:
            query = query.where(StaffProfile.primary_role_id == role_id)
        if team_id:
            query = query.join(StaffTeamMembership, StaffTeamMembership.staff_id == StaffProfile.id).where(
                StaffTeamMembership.team_id == team_id,
                StaffTeamMembership.ended_at.is_(None),
            )
        if search:
            search_pattern = f"%{search}%"
            query = query.where(
                (StaffProfile.display_name.ilike(search_pattern))
                | (StaffProfile.first_name.ilike(search_pattern))
                | (StaffProfile.last_name.ilike(search_pattern))
                | (StaffProfile.staff_code.ilike(search_pattern))
            )

        query = query.order_by(StaffProfile.created_at.desc()).offset(offset).limit(limit)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_contact(self, staff_id: uuid.UUID, society_id: uuid.UUID) -> StaffContact | None:
        """Fetch contact details for a staff member."""
        query = select(StaffContact).where(
            StaffContact.staff_id == staff_id,
            StaffContact.society_id == society_id,
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def add_status_history(self, history: StaffStatusHistory) -> StaffStatusHistory:
        """Persist staff status transition history."""
        self.session.add(history)
        await self.session.flush()
        return history

    async def list_status_history(
        self, staff_id: uuid.UUID, society_id: uuid.UUID
    ) -> list[StaffStatusHistory]:
        """List status transition logs for staff member."""
        query = (
            select(StaffStatusHistory)
            .where(
                StaffStatusHistory.staff_id == staff_id,
                StaffStatusHistory.society_id == society_id,
            )
            .order_by(StaffStatusHistory.created_at.desc())
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())


class StaffRoleRepository:
    """Async repository for operational StaffRole persistence."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_role(self, role: StaffRole) -> StaffRole:
        """Create a new staff role."""
        self.session.add(role)
        await self.session.flush()
        return role

    async def get_role_by_id(self, role_id: uuid.UUID, society_id: uuid.UUID) -> StaffRole | None:
        """Fetch staff role by ID."""
        query = select(StaffRole).where(
            StaffRole.id == role_id,
            StaffRole.society_id == society_id,
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def list_roles(self, society_id: uuid.UUID) -> list[StaffRole]:
        """List operational staff roles for a society."""
        query = (
            select(StaffRole)
            .where(StaffRole.society_id == society_id, StaffRole.is_active.is_(True))
            .order_by(StaffRole.display_order.asc(), StaffRole.name.asc())
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def assign_role(self, assignment: StaffRoleAssignment) -> StaffRoleAssignment:
        """Persist staff role assignment."""
        self.session.add(assignment)
        await self.session.flush()
        return assignment


class StaffTeamRepository:
    """Async repository for StaffTeam persistence."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_team(self, team: StaffTeam) -> StaffTeam:
        """Create a new staff team."""
        self.session.add(team)
        await self.session.flush()
        return team

    async def get_team_by_id(self, team_id: uuid.UUID, society_id: uuid.UUID) -> StaffTeam | None:
        """Fetch staff team by ID."""
        query = select(StaffTeam).where(
            StaffTeam.id == team_id,
            StaffTeam.society_id == society_id,
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def list_teams(self, society_id: uuid.UUID) -> list[StaffTeam]:
        """List active staff teams."""
        query = (
            select(StaffTeam)
            .where(StaffTeam.society_id == society_id, StaffTeam.is_active.is_(True))
            .order_by(StaffTeam.name.asc())
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def add_membership(self, membership: StaffTeamMembership) -> StaffTeamMembership:
        """Persist team membership."""
        self.session.add(membership)
        await self.session.flush()
        return membership


class StaffDocumentRepository:
    """Async repository for StaffDocument persistence."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_document(self, doc: StaffDocument) -> StaffDocument:
        """Persist staff document metadata."""
        self.session.add(doc)
        await self.session.flush()
        return doc

    async def get_document(self, doc_id: uuid.UUID, society_id: uuid.UUID) -> StaffDocument | None:
        """Fetch document metadata by ID."""
        query = select(StaffDocument).where(
            StaffDocument.id == doc_id,
            StaffDocument.society_id == society_id,
            StaffDocument.archived_at.is_(None),
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def list_documents(self, staff_id: uuid.UUID, society_id: uuid.UUID) -> list[StaffDocument]:
        """List active documents for staff."""
        query = (
            select(StaffDocument)
            .where(
                StaffDocument.staff_id == staff_id,
                StaffDocument.society_id == society_id,
                StaffDocument.archived_at.is_(None),
            )
            .order_by(StaffDocument.created_at.desc())
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def archive_document(self, doc: StaffDocument) -> StaffDocument:
        """Soft-archive staff document."""
        doc.archived_at = datetime.utcnow()
        await self.session.flush()
        return doc
