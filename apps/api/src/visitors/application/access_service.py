"""Application Service for Visitor Gate Access Records, Check-in/out, and Emergency Overrides."""

import uuid
from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.core.exceptions import NotFoundException
from apps.api.src.database.models.membership import UserSocietyMembership
from apps.api.src.database.models.society import Unit
from apps.api.src.database.models.vehicle import Vehicle
from apps.api.src.database.models.visitor import VisitorAccessRecord
from apps.api.src.visitors.domain.concurrency import get_visitor_entry_lock
from apps.api.src.visitors.domain.exceptions import (
    InvalidVisitorStatusError,
    VisitorAccessDeniedError,
    VisitorAccessRecordImmutableError,
    VisitorAccessRecordNotFoundError,
    VisitorNotFoundError,
)
from apps.api.src.visitors.infrastructure.repositories import (
    VisitorAccessRecordRepository,
    VisitorApprovalRepository,
    VisitorInvitationRepository,
    VisitorRepository,
)
from apps.api.src.visitors.schemas import (
    EmergencyOverrideEntryRequest,
    VisitorGateEntryRequest,
    VisitorGateExitRequest,
)


class VisitorAccessService:
    """Service managing visitor gate check-in, check-out, access history, and emergency overrides."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.access_repo = VisitorAccessRecordRepository(session)
        self.visitor_repo = VisitorRepository(session)
        self.invitation_repo = VisitorInvitationRepository(session)
        self.approval_repo = VisitorApprovalRepository(session)

    async def record_entry(
        self,
        society_id: uuid.UUID,
        security_user_id: uuid.UUID | None,
        data: VisitorGateEntryRequest,
    ) -> VisitorAccessRecord:
        """
        Record visitor gate entry check-in.
        Validates visitor status, host unit, resident approval, time-bound invitation window, and prevents double entry.
        """
        async with get_visitor_entry_lock(society_id, data.unit_id, data.visitor_id):
            # 1. Fetch visitor profile
            visitor = await self.visitor_repo.get_by_id(data.visitor_id, society_id)
            if not visitor:
                raise VisitorNotFoundError(data.visitor_id)

            if visitor.status != "ACTIVE":
                raise VisitorAccessDeniedError(f"Visitor '{visitor.name}' status is '{visitor.status}'")

            # 2. Validate same-society Unit
            unit_res = await self.session.execute(
                select(Unit).where(Unit.id == data.unit_id, Unit.society_id == society_id)
            )
            if not unit_res.scalar_one_or_none():
                raise NotFoundException(f"Unit with ID '{data.unit_id}' not found in this society")

            # 3. Validate host membership
            mem_res = await self.session.execute(
                select(UserSocietyMembership).where(
                    UserSocietyMembership.user_id == data.host_user_id,
                    UserSocietyMembership.society_id == society_id,
                    UserSocietyMembership.membership_status == "ACTIVE",
                )
            )
            if not mem_res.scalar_one_or_none():
                raise NotFoundException("Host user does not have an active membership in this society")

            # 4. Prevent duplicate entry (already inside)
            active_visit = await self.access_repo.get_active_inside_visit(
                society_id=society_id,
                visitor_id=data.visitor_id,
                unit_id=data.unit_id,
            )
            if active_visit:
                raise VisitorAccessDeniedError(
                    f"Visitor '{visitor.name}' is already recorded inside unit '{data.unit_id}'"
                )

            # 5. Invitation & Pass Code validation if present
            invitation_id = data.invitation_id
            approval_id = None

            if data.pass_code:
                pass_inv = await self.invitation_repo.get_by_pass_code(society_id, data.pass_code)
                if not pass_inv:
                    raise VisitorAccessDeniedError("Invalid pass code provided")
                if pass_inv.visitor_id != data.visitor_id:
                    raise VisitorAccessDeniedError("Pass code does not match this visitor")
                invitation_id = pass_inv.id

            if invitation_id:
                inv = await self.invitation_repo.get_by_id(invitation_id, society_id)
                if not inv:
                    raise VisitorAccessDeniedError("Associated invitation not found in this society")

                if inv.status in ("REJECTED", "CANCELLED", "EXPIRED"):
                    raise VisitorAccessDeniedError(f"Invitation status is '{inv.status}'")

                # Verify expected date
                if inv.expected_date != date.today():
                    # Expire if past date
                    if inv.expected_date < date.today():
                        inv.status = "EXPIRED"
                        await self.invitation_repo.save(inv)
                        raise VisitorAccessDeniedError(
                            f"Invitation expired on {inv.expected_date} (today is {date.today()})"
                        )

                inv.status = "USED"
                await self.invitation_repo.save(inv)

            # 6. Check latest approval record if walk-in or manual entry
            latest_appr = await self.approval_repo.get_latest_for_visitor(
                society_id=society_id,
                visitor_id=data.visitor_id,
                unit_id=data.unit_id,
            )
            if latest_appr:
                if latest_appr.approval_status == "REJECTED":
                    raise VisitorAccessDeniedError("Entry rejected by resident host")
                approval_id = latest_appr.id

            # 7. Optional Phase 8 Vehicle linkage check
            if data.vehicle_id:
                v_res = await self.session.execute(
                    select(Vehicle).where(
                        Vehicle.id == data.vehicle_id,
                        Vehicle.society_id == society_id,
                    )
                )
                if not v_res.scalar_one_or_none():
                    raise NotFoundException(f"Vehicle with ID '{data.vehicle_id}' not found in this society")

            # 8. Append immutable VisitorAccessRecord
            record = VisitorAccessRecord(
                id=uuid.uuid4(),
                society_id=society_id,
                visitor_id=data.visitor_id,
                invitation_id=invitation_id,
                approval_id=approval_id,
                unit_id=data.unit_id,
                host_user_id=data.host_user_id,
                security_user_id=security_user_id,
                vehicle_id=data.vehicle_id,
                visitor_name_snapshot=visitor.name,
                visitor_phone_snapshot=visitor.phone,
                visitor_type_snapshot=visitor.visitor_type,
                gate_identifier=data.gate_identifier.strip(),
                access_type="ENTRY",
                access_time=datetime.now(UTC),
                entry_method=data.entry_method.value,
                delivery_company=data.delivery_company,
                service_type=data.service_type,
                notes=data.notes,
                created_at=datetime.now(UTC),
            )
            await self.access_repo.save(record)
            return record

    async def record_exit(
        self,
        society_id: uuid.UUID,
        record_id: uuid.UUID,
        security_user_id: uuid.UUID | None,
        data: VisitorGateExitRequest,
    ) -> VisitorAccessRecord:
        """Record visitor gate exit check-out."""
        record = await self.access_repo.get_by_id(record_id, society_id)
        if not record:
            raise VisitorAccessRecordNotFoundError(record_id)

        if record.exit_time is not None:
            raise InvalidVisitorStatusError(
                f"Visitor entry record '{record_id}' has already registered an exit"
            )

        record.exit_time = datetime.now(UTC)
        record.exit_gate_identifier = data.gate_identifier.strip()
        record.exit_security_user_id = security_user_id
        record.exit_method = data.exit_method.value
        if data.notes:
            record.notes = f"{record.notes or ''}\nExit: {data.notes}".strip()

        await self.access_repo.save(record)
        return record

    async def record_emergency_override_entry(
        self,
        society_id: uuid.UUID,
        authorized_user_id: uuid.UUID,
        data: EmergencyOverrideEntryRequest,
    ) -> VisitorAccessRecord:
        """Audit-logged emergency override entry authorization."""
        # 1. Validate same-society Unit
        unit_res = await self.session.execute(
            select(Unit).where(Unit.id == data.unit_id, Unit.society_id == society_id)
        )
        if not unit_res.scalar_one_or_none():
            raise NotFoundException(f"Unit with ID '{data.unit_id}' not found in this society")

        # 2. Get or create visitor
        from apps.api.src.visitors.application.visitor_service import VisitorService
        from apps.api.src.visitors.schemas import VisitorCreateRequest

        visitor_svc = VisitorService(self.session)
        visitor = await visitor_svc.get_or_create_visitor(
            society_id=society_id,
            user_id=authorized_user_id,
            data=VisitorCreateRequest(
                name=data.name,
                phone=data.phone,
                visitor_type=data.visitor_type,
                notes=f"Emergency override: {data.reason}",
            ),
        )

        # 3. Append access record with explicit emergency override reason
        record = VisitorAccessRecord(
            id=uuid.uuid4(),
            society_id=society_id,
            visitor_id=visitor.id,
            unit_id=data.unit_id,
            host_user_id=authorized_user_id,
            security_user_id=authorized_user_id,
            vehicle_id=data.vehicle_id,
            visitor_name_snapshot=visitor.name,
            visitor_phone_snapshot=visitor.phone,
            visitor_type_snapshot=visitor.visitor_type,
            gate_identifier=data.gate_identifier.strip(),
            access_type="ENTRY",
            access_time=datetime.now(UTC),
            entry_method="MANUAL",
            notes=data.notes,
            emergency_override_reason=data.reason.strip(),
            created_at=datetime.now(UTC),
        )
        await self.access_repo.save(record)
        return record

    async def search_records(
        self,
        society_id: uuid.UUID,
        query: str | None = None,
        visitor_id: uuid.UUID | None = None,
        unit_id: uuid.UUID | None = None,
        access_type: str | None = None,
        gate_identifier: str | None = None,
        page: int = 1,
        size: int = 50,
    ) -> tuple[list[VisitorAccessRecord], int]:
        """Search access history logs."""
        return await self.access_repo.search(
            society_id=society_id,
            query=query,
            visitor_id=visitor_id,
            unit_id=unit_id,
            access_type=access_type,
            gate_identifier=gate_identifier,
            page=page,
            size=size,
        )

    async def prevent_modification(self) -> None:
        """Guard method confirming access records are append-only. Raises VisitorAccessRecordImmutableError."""
        raise VisitorAccessRecordImmutableError()

    async def delete_record(self, *args, **kwargs) -> None:
        """Visitor access records are append-only audit logs and cannot be deleted."""
        raise VisitorAccessRecordImmutableError()
