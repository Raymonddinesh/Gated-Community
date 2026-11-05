"""Application Service for Visitor Profile Management, Invitations, and Approvals."""

import secrets
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.core.exceptions import NotFoundException
from apps.api.src.database.models.membership import UserSocietyMembership
from apps.api.src.database.models.society import Unit
from apps.api.src.database.models.visitor import (
    Visitor,
    VisitorApproval,
    VisitorInvitation,
)
from apps.api.src.visitors.domain.concurrency import get_invitation_lock, get_visitor_lock
from apps.api.src.visitors.domain.exceptions import (
    InvalidVisitorStatusError,
    VisitorApprovalNotFoundError,
    VisitorInvitationNotFoundError,
    VisitorNotFoundError,
)
from apps.api.src.visitors.domain.state_machine import (
    validate_approval_transition,
    validate_invitation_transition,
)
from apps.api.src.visitors.infrastructure.repositories import (
    VisitorApprovalRepository,
    VisitorInvitationRepository,
    VisitorRepository,
)
from apps.api.src.visitors.schemas import (
    VisitorApprovalDecisionRequest,
    VisitorCreateRequest,
    VisitorInvitationCreateRequest,
    VisitorStatusEnum,
    VisitorUpdateRequest,
    WalkInVisitorEntryRequest,
)


class VisitorService:
    """Service handling visitor profiles, resident pre-approved invitations, and resident approvals."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.visitor_repo = VisitorRepository(session)
        self.invitation_repo = VisitorInvitationRepository(session)
        self.approval_repo = VisitorApprovalRepository(session)

    # --- Visitor Management ---

    async def get_or_create_visitor(
        self,
        society_id: uuid.UUID,
        user_id: uuid.UUID | None,
        data: VisitorCreateRequest,
    ) -> Visitor:
        """Fetch existing visitor by phone or register a new visitor."""
        existing = await self.visitor_repo.get_by_phone(society_id, data.phone)
        if existing:
            # Update notes or visitor type if provided
            existing.visitor_type = data.visitor_type.value
            if data.notes:
                existing.notes = data.notes
            if data.identification_type:
                existing.identification_type = data.identification_type
            if data.identification_number:
                existing.identification_number = data.identification_number
            existing.updated_by = user_id
            await self.visitor_repo.save(existing)
            return existing

        visitor = Visitor(
            id=uuid.uuid4(),
            society_id=society_id,
            name=data.name.strip(),
            phone=data.phone.strip(),
            alternate_phone=data.alternate_phone.strip() if data.alternate_phone else None,
            visitor_type=data.visitor_type.value,
            identification_type=data.identification_type,
            identification_number=data.identification_number,
            photo_file_key=data.photo_file_key,
            notes=data.notes,
            status="ACTIVE",
            created_by=user_id,
            updated_by=user_id,
        )
        await self.visitor_repo.save(visitor)
        return visitor

    async def get_visitor(self, society_id: uuid.UUID, visitor_id: uuid.UUID) -> Visitor:
        """Fetch single visitor profile."""
        vis = await self.visitor_repo.get_by_id(visitor_id, society_id)
        if not vis:
            raise VisitorNotFoundError(visitor_id)
        return vis

    async def update_visitor(
        self,
        society_id: uuid.UUID,
        visitor_id: uuid.UUID,
        user_id: uuid.UUID,
        data: VisitorUpdateRequest,
    ) -> Visitor:
        """Update visitor details."""
        async with get_visitor_lock(visitor_id):
            vis = await self.get_visitor(society_id, visitor_id)

            if data.name is not None:
                vis.name = data.name.strip()
            if data.phone is not None:
                vis.phone = data.phone.strip()
            if data.alternate_phone is not None:
                vis.alternate_phone = data.alternate_phone.strip() if data.alternate_phone else None
            if data.visitor_type is not None:
                vis.visitor_type = data.visitor_type.value
            if data.identification_type is not None:
                vis.identification_type = data.identification_type
            if data.identification_number is not None:
                vis.identification_number = data.identification_number
            if data.photo_file_key is not None:
                vis.photo_file_key = data.photo_file_key
            if data.notes is not None:
                vis.notes = data.notes

            vis.updated_by = user_id
            await self.visitor_repo.save(vis)
            return vis

    async def update_status(
        self,
        society_id: uuid.UUID,
        visitor_id: uuid.UUID,
        user_id: uuid.UUID,
        target_status: VisitorStatusEnum,
        notes: str | None = None,
    ) -> Visitor:
        """Transition visitor status (ACTIVE, BLOCKED, ARCHIVED)."""
        async with get_visitor_lock(visitor_id):
            vis = await self.get_visitor(society_id, visitor_id)
            vis.status = target_status.value
            vis.updated_by = user_id
            if notes:
                vis.notes = f"{vis.notes or ''}\nStatus update: {notes}".strip()
            await self.visitor_repo.save(vis)
            return vis

    async def search(
        self,
        society_id: uuid.UUID,
        query: str | None = None,
        visitor_type: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 50,
    ) -> tuple[list[Visitor], int]:
        """Search society visitors."""
        return await self.visitor_repo.search(
            society_id=society_id,
            query=query,
            visitor_type=visitor_type,
            status=status,
            page=page,
            size=size,
        )

    # --- Resident Visitor Invitations ---

    async def create_invitation(
        self,
        society_id: uuid.UUID,
        host_user_id: uuid.UUID,
        data: VisitorInvitationCreateRequest,
    ) -> VisitorInvitation:
        """Create a pre-approved visitor invitation by resident host."""
        # 1. Validate same-society Unit
        unit_res = await self.session.execute(
            select(Unit).where(Unit.id == data.unit_id, Unit.society_id == society_id)
        )
        if not unit_res.scalar_one_or_none():
            raise NotFoundException(f"Unit with ID '{data.unit_id}' not found in this society")

        # 2. Validate host membership
        mem_res = await self.session.execute(
            select(UserSocietyMembership).where(
                UserSocietyMembership.user_id == host_user_id,
                UserSocietyMembership.society_id == society_id,
                UserSocietyMembership.membership_status == "ACTIVE",
            )
        )
        if not mem_res.scalar_one_or_none():
            raise NotFoundException(
                f"Host user with ID '{host_user_id}' does not have an active membership in this society"
            )

        # 3. Get or register visitor profile
        v_create = VisitorCreateRequest(
            name=data.visitor_name,
            phone=data.visitor_phone,
            visitor_type=data.visitor_type,
            notes=data.notes,
        )
        visitor = await self.get_or_create_visitor(society_id, host_user_id, v_create)

        # Generate a 6-digit alphanumeric pass code
        pass_code = f"V-{secrets.token_hex(3).upper()}"

        invitation = VisitorInvitation(
            id=uuid.uuid4(),
            society_id=society_id,
            visitor_id=visitor.id,
            host_user_id=host_user_id,
            unit_id=data.unit_id,
            expected_date=data.expected_date,
            expected_arrival_window_start=data.expected_arrival_window_start,
            expected_arrival_window_end=data.expected_arrival_window_end,
            expected_departure=data.expected_departure,
            purpose=data.purpose,
            pass_code=pass_code,
            delivery_company=data.delivery_company,
            service_type=data.service_type,
            status="APPROVED",  # Pre-approved by host resident
            notes=data.notes,
        )
        invitation.visitor = visitor
        await self.invitation_repo.save(invitation)

        # Create corresponding approval record
        approval = VisitorApproval(
            id=uuid.uuid4(),
            society_id=society_id,
            visitor_id=visitor.id,
            invitation_id=invitation.id,
            unit_id=data.unit_id,
            approving_user_id=host_user_id,
            approval_status="APPROVED",
            decision_reason="Resident created pre-approved invitation",
            decision_time=datetime.now(UTC),
            created_at=datetime.now(UTC),
        )
        await self.approval_repo.save(approval)

        return invitation

    async def get_invitation(
        self,
        society_id: uuid.UUID,
        invitation_id: uuid.UUID,
    ) -> VisitorInvitation:
        inv = await self.invitation_repo.get_by_id(invitation_id, society_id)
        if not inv:
            raise VisitorInvitationNotFoundError(invitation_id)
        return inv

    async def cancel_invitation(
        self,
        society_id: uuid.UUID,
        invitation_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> VisitorInvitation:
        """Cancel a pending/approved invitation."""
        async with get_invitation_lock(invitation_id):
            inv = await self.get_invitation(society_id, invitation_id)
            validate_invitation_transition(inv.status, "CANCELLED")
            inv.status = "CANCELLED"
            await self.invitation_repo.save(inv)
            return inv

    async def search_invitations(
        self,
        society_id: uuid.UUID,
        unit_id: uuid.UUID | None = None,
        host_user_id: uuid.UUID | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 50,
    ) -> tuple[list[VisitorInvitation], int]:
        return await self.invitation_repo.search(
            society_id=society_id,
            unit_id=unit_id,
            host_user_id=host_user_id,
            status=status,
            page=page,
            size=size,
        )

    # --- Resident Walk-in Approval / Rejection ---

    async def record_walkin_request(
        self,
        society_id: uuid.UUID,
        security_user_id: uuid.UUID,
        data: WalkInVisitorEntryRequest,
    ) -> tuple[Visitor, VisitorApproval]:
        """Security guard registers walk-in visitor and requests resident approval."""
        # Validate unit in society
        unit_res = await self.session.execute(
            select(Unit).where(Unit.id == data.unit_id, Unit.society_id == society_id)
        )
        unit = unit_res.scalar_one_or_none()
        if not unit:
            raise NotFoundException(f"Unit with ID '{data.unit_id}' not found in this society")

        # Get or register visitor
        v_create = VisitorCreateRequest(
            name=data.name,
            phone=data.phone,
            visitor_type=data.visitor_type,
            notes=data.notes,
        )
        visitor = await self.get_or_create_visitor(society_id, security_user_id, v_create)

        if visitor.status == "BLOCKED":
            raise InvalidVisitorStatusError(f"Visitor '{visitor.name}' is BLOCKED from entering the society")

        # Create pending approval workflow record
        approval = VisitorApproval(
            id=uuid.uuid4(),
            society_id=society_id,
            visitor_id=visitor.id,
            unit_id=data.unit_id,
            approving_user_id=security_user_id,  # Initially initiated by gate
            approval_status="PENDING",
            decision_reason="Walk-in arrival awaiting resident approval",
            decision_time=datetime.now(UTC),
            created_at=datetime.now(UTC),
        )
        await self.approval_repo.save(approval)
        return visitor, approval

    async def decide_approval(
        self,
        society_id: uuid.UUID,
        approval_id: uuid.UUID,
        approving_user_id: uuid.UUID,
        data: VisitorApprovalDecisionRequest,
    ) -> VisitorApproval:
        """Resident approves or rejects a pending visitor entry request."""
        appr = await self.approval_repo.get_by_id(approval_id, society_id)
        if not appr:
            raise VisitorApprovalNotFoundError(approval_id)

        # Validate approving user belongs to this society
        mem_res = await self.session.execute(
            select(UserSocietyMembership).where(
                UserSocietyMembership.user_id == approving_user_id,
                UserSocietyMembership.society_id == society_id,
                UserSocietyMembership.membership_status == "ACTIVE",
            )
        )
        if not mem_res.scalar_one_or_none():
            raise NotFoundException("Approving user does not have an active membership in this society")

        validate_approval_transition(appr.approval_status, data.approval_status.value)

        appr.approval_status = data.approval_status.value
        appr.approving_user_id = approving_user_id
        appr.decision_reason = data.reason or f"Decision: {data.approval_status.value}"
        appr.decision_time = datetime.now(UTC)

        await self.approval_repo.save(appr)

        # If invitation linked, update invitation state too
        if appr.invitation_id:
            inv = await self.invitation_repo.get_by_id(appr.invitation_id, society_id)
            if inv:
                inv.status = data.approval_status.value
                await self.invitation_repo.save(inv)

        return appr
