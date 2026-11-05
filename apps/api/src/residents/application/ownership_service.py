"""Application service for Unit Ownership, Joint Co-owners, and Percentage Validation."""

from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.database.models.membership import UnitOwnership
from apps.api.src.database.models.society import Unit
from apps.api.src.database.repositories.audit_repository import AuditRepository
from apps.api.src.database.repositories.membership_repository import MembershipRepository
from apps.api.src.database.repositories.user_repository import UserRepository
from apps.api.src.residents.domain.concurrency import get_unit_lock
from apps.api.src.residents.domain.exceptions import (
    InvalidDateRangeError,
    InvalidOwnershipPercentageError,
    OwnershipNotFoundError,
    ResidentNotFoundError,
    UnitNotFoundError,
)
from apps.api.src.residents.infrastructure.repositories import OwnershipRepository
from apps.api.src.residents.schemas import (
    UnitOwnershipCreate,
    UnitOwnershipEndRequest,
    UnitOwnershipResponse,
    UnitOwnershipTransferRequest,
    UnitOwnershipTransferResponse,
    UnitOwnershipUpdate,
)


class OwnershipService:
    """Service managing legal and beneficial ownership records with joint ownership validation."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.ownership_repo = OwnershipRepository(session)
        self.user_repo = UserRepository(session)
        self.membership_repo = MembershipRepository(session)
        self.audit_repo = AuditRepository(session)

    def _to_response(self, own: UnitOwnership) -> UnitOwnershipResponse:
        user = own.user
        return UnitOwnershipResponse(
            id=own.id,
            society_id=own.society_id,
            unit_id=own.unit_id,
            user_id=own.user_id,
            user_name=user.display_name if user else "Unknown",
            user_phone=user.phone if user else None,
            user_email=user.email if user else None,
            ownership_percentage=own.ownership_percentage,
            start_date=own.start_date,
            end_date=own.end_date,
            is_primary=own.is_primary,
            status=own.status,
            notes=own.notes,
            created_at=own.created_at,
            updated_at=own.updated_at,
        )

    async def _get_unit(self, unit_id: UUID, society_id: UUID, for_update: bool = False) -> Unit:
        stmt = select(Unit).where(Unit.id == unit_id, Unit.society_id == society_id)
        if for_update:
            stmt = stmt.with_for_update()
        result = await self.session.execute(stmt)
        unit = result.scalar_one_or_none()
        if not unit:
            raise UnitNotFoundError(f"Unit {unit_id} not found in society.")
        return unit

    async def _ensure_membership(
        self, user_id: UUID, society_id: UUID, actor_user_id: UUID, source: str
    ) -> None:
        """Ensure active society membership, logging audit event if newly enrolled."""
        existing = await self.membership_repo.get_membership(user_id, society_id)
        if not existing:
            await self.membership_repo.create_membership(user_id=user_id, society_id=society_id)
            await self.audit_repo.log_event(
                action="membership.auto_enrolled",
                entity_type="user_society_membership",
                entity_id=str(user_id),
                society_id=society_id,
                actor_user_id=actor_user_id,
                after_state={"user_id": str(user_id), "source": source},
            )
        elif existing.membership_status != "ACTIVE":
            await self.membership_repo.create_membership(user_id=user_id, society_id=society_id)

    async def add_owner(
        self,
        society_id: UUID,
        unit_id: UUID,
        data: UnitOwnershipCreate,
        actor_user_id: UUID,
    ) -> UnitOwnershipResponse:
        """Add a single owner or joint co-owner with percentage validation and concurrency protection."""
        async with get_unit_lock(unit_id):
            await self._get_unit(unit_id, society_id, for_update=True)

            user = await self.user_repo.get_by_id(data.user_id)
            if not user:
                raise ResidentNotFoundError("Owner user not found.")

            # Ensure active society membership
            await self._ensure_membership(data.user_id, society_id, actor_user_id, "ownership.add")

            # Validate percentage limits
            if data.ownership_percentage <= Decimal("0") or data.ownership_percentage > Decimal("100"):
                raise InvalidOwnershipPercentageError(
                    "Ownership percentage must be greater than 0% and less than or equal to 100%."
                )

            current_total = await self.ownership_repo.get_total_active_ownership_percentage(
                unit_id, society_id
            )
            new_total = current_total + data.ownership_percentage
            if new_total > Decimal("100.00"):
                raise InvalidOwnershipPercentageError(
                    f"Total active ownership percentage cannot exceed 100%. "
                    f"Current active total: {current_total}%, attempted addition: {data.ownership_percentage}%."
                )

            # If marked primary, demote other active owners' primary status if appropriate
            if data.is_primary:
                active_owners = await self.ownership_repo.get_active_ownerships_for_unit(unit_id, society_id)
                for existing in active_owners:
                    if existing.is_primary:
                        existing.is_primary = False

            own = await self.ownership_repo.create_ownership(
                society_id=society_id,
                unit_id=unit_id,
                user_id=data.user_id,
                ownership_percentage=data.ownership_percentage,
                start_date=data.start_date,
                is_primary=data.is_primary,
                status="ACTIVE",
                notes=data.notes,
            )

            await self.audit_repo.log_event(
                action="ownership.add",
                entity_type="unit_ownership",
                entity_id=str(own.id),
                society_id=society_id,
                actor_user_id=actor_user_id,
                after_state={
                    "unit_id": str(unit_id),
                    "user_id": str(data.user_id),
                    "percentage": str(data.ownership_percentage),
                    "is_primary": data.is_primary,
                },
            )

            return self._to_response(own)

    async def update_ownership(
        self,
        society_id: UUID,
        ownership_id: UUID,
        data: UnitOwnershipUpdate,
        actor_user_id: UUID,
    ) -> UnitOwnershipResponse:
        """Update ownership percentage or primary status."""
        own = await self.ownership_repo.get_ownership(ownership_id, society_id)
        if not own:
            raise OwnershipNotFoundError()

        async with get_unit_lock(own.unit_id):
            await self._get_unit(own.unit_id, society_id, for_update=True)

            before_state = {
                "percentage": str(own.ownership_percentage),
                "is_primary": own.is_primary,
            }

            if data.ownership_percentage is not None:
                if data.ownership_percentage <= Decimal("0") or data.ownership_percentage > Decimal("100"):
                    raise InvalidOwnershipPercentageError("Ownership percentage must be between 0 and 100.")
                current_total_without = await self.ownership_repo.get_total_active_ownership_percentage(
                    own.unit_id, society_id, exclude_ownership_id=own.id
                )
                if current_total_without + data.ownership_percentage > Decimal("100.00"):
                    raise InvalidOwnershipPercentageError(
                        f"Total active ownership cannot exceed 100%. "
                        f"Other active owners: {current_total_without}%, attempted: {data.ownership_percentage}%."
                    )
                own.ownership_percentage = data.ownership_percentage

            if data.is_primary is not None:
                if data.is_primary:
                    active_owners = await self.ownership_repo.get_active_ownerships_for_unit(
                        own.unit_id, society_id
                    )
                    for existing in active_owners:
                        if existing.id != own.id and existing.is_primary:
                            existing.is_primary = False
                own.is_primary = data.is_primary

            if data.notes is not None:
                own.notes = data.notes

            await self.session.flush()

            await self.audit_repo.log_event(
                action="ownership.updated",
                entity_type="unit_ownership",
                entity_id=str(own.id),
                society_id=society_id,
                actor_user_id=actor_user_id,
                before_state=before_state,
                after_state={
                    "percentage": str(own.ownership_percentage),
                    "is_primary": own.is_primary,
                },
            )

            return self._to_response(own)

    async def end_ownership(
        self,
        society_id: UUID,
        ownership_id: UUID,
        data: UnitOwnershipEndRequest,
        actor_user_id: UUID,
    ) -> UnitOwnershipResponse:
        """Transfer or terminate ownership record, preserving historical data."""
        own = await self.ownership_repo.get_ownership(ownership_id, society_id)
        if not own:
            raise OwnershipNotFoundError()

        async with get_unit_lock(own.unit_id):
            await self._get_unit(own.unit_id, society_id, for_update=True)

            end_date = data.end_date or date.today()
            if end_date < own.start_date:
                raise InvalidDateRangeError("End date cannot precede ownership start date.")

            before_state = {
                "status": own.status,
                "end_date": str(own.end_date) if own.end_date else None,
            }

            own.end_date = end_date
            own.status = "TRANSFERRED"
            own.is_primary = False
            if data.reason:
                own.notes = f"{own.notes or ''} [Transfer Reason: {data.reason}]".strip()

            await self.session.flush()

            await self.audit_repo.log_event(
                action="ownership.ended",
                entity_type="unit_ownership",
                entity_id=str(own.id),
                society_id=society_id,
                actor_user_id=actor_user_id,
                before_state=before_state,
                after_state={"status": own.status, "end_date": str(own.end_date)},
            )

            return self._to_response(own)

    async def transfer_ownership(
        self,
        society_id: UUID,
        ownership_id: UUID,
        data: UnitOwnershipTransferRequest,
        actor_user_id: UUID,
    ) -> UnitOwnershipTransferResponse:
        """
        Execute an atomic ownership transfer workflow.
        Supports 100% transfer or partial share divestment.
        """
        own = await self.ownership_repo.get_ownership(ownership_id, society_id)
        if not own:
            raise OwnershipNotFoundError("Source ownership record not found.")

        async with get_unit_lock(own.unit_id):
            await self._get_unit(own.unit_id, society_id, for_update=True)

            if own.status != "ACTIVE":
                raise InvalidOwnershipPercentageError(
                    "Cannot transfer from an inactive or transferred ownership."
                )

            if data.new_owner_user_id == own.user_id:
                raise InvalidOwnershipPercentageError(
                    "Source owner and destination owner cannot be the same user."
                )

            new_user = await self.user_repo.get_by_id(data.new_owner_user_id)
            if not new_user:
                raise ResidentNotFoundError("Target owner user not found.")

            if (
                data.transfer_percentage <= Decimal("0")
                or data.transfer_percentage > own.ownership_percentage
            ):
                raise InvalidOwnershipPercentageError(
                    f"Transfer percentage must be between 0% and current active share of {own.ownership_percentage}%."
                )

            # Ensure destination user has active membership
            await self._ensure_membership(
                data.new_owner_user_id, society_id, actor_user_id, "ownership.transfer"
            )

            transfer_date = data.transfer_date or date.today()
            if transfer_date < own.start_date:
                raise InvalidDateRangeError("Transfer date cannot precede ownership start date.")

            before_source_percentage = own.ownership_percentage
            is_full_transfer = data.transfer_percentage == own.ownership_percentage

            if is_full_transfer:
                own.end_date = transfer_date
                own.status = "TRANSFERRED"
                own.is_primary = False
                note_suffix = (
                    f"[Transferred 100% to {new_user.display_name}: {data.reason or 'Ownership transfer'}]"
                )
                own.notes = f"{own.notes or ''} {note_suffix}".strip()
            else:
                own.ownership_percentage -= data.transfer_percentage
                note_suffix = (
                    f"[Partial transfer of {data.transfer_percentage}% to "
                    f"{new_user.display_name}: {data.reason or 'Co-owner divestment'}]"
                )
                own.notes = f"{own.notes or ''} {note_suffix}".strip()

            # Manage primary title holder designation
            if data.is_primary:
                active_owners = await self.ownership_repo.get_active_ownerships_for_unit(
                    own.unit_id, society_id
                )
                for existing in active_owners:
                    if existing.id != own.id and existing.is_primary:
                        existing.is_primary = False
                if not is_full_transfer:
                    own.is_primary = False

            new_own = await self.ownership_repo.create_ownership(
                society_id=society_id,
                unit_id=own.unit_id,
                user_id=data.new_owner_user_id,
                ownership_percentage=data.transfer_percentage,
                start_date=transfer_date,
                is_primary=data.is_primary,
                status="ACTIVE",
                notes=data.reason,
            )

            await self.session.flush()

            # Audit log on source
            await self.audit_repo.log_event(
                action="ownership.transferred",
                entity_type="unit_ownership",
                entity_id=str(own.id),
                society_id=society_id,
                actor_user_id=actor_user_id,
                before_state={"percentage": str(before_source_percentage), "status": "ACTIVE"},
                after_state={
                    "percentage": str(own.ownership_percentage),
                    "status": own.status,
                    "target_user_id": str(data.new_owner_user_id),
                },
            )

            # Audit log on destination
            await self.audit_repo.log_event(
                action="ownership.acquired",
                entity_type="unit_ownership",
                entity_id=str(new_own.id),
                society_id=society_id,
                actor_user_id=actor_user_id,
                after_state={
                    "percentage": str(new_own.ownership_percentage),
                    "from_ownership_id": str(own.id),
                    "is_primary": new_own.is_primary,
                },
            )

            # Re-fetch new_own with user joined
            dest_own = await self.ownership_repo.get_ownership(new_own.id, society_id) or new_own

            return UnitOwnershipTransferResponse(
                source_ownership=self._to_response(own),
                new_ownership=self._to_response(dest_own),
            )

    async def list_owners(self, society_id: UUID, unit_id: UUID) -> list[UnitOwnershipResponse]:
        """List active owners/co-owners for a unit."""
        await self._get_unit(unit_id, society_id)
        owners = await self.ownership_repo.get_active_ownerships_for_unit(unit_id, society_id)
        return [self._to_response(o) for o in owners]

    async def get_ownership_history(self, society_id: UUID, unit_id: UUID) -> list[UnitOwnershipResponse]:
        """List all historical and active ownership records for a unit."""
        await self._get_unit(unit_id, society_id)
        owners = await self.ownership_repo.get_all_ownerships_for_unit(unit_id, society_id)
        return [self._to_response(o) for o in owners]
