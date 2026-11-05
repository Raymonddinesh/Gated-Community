"""Data access repositories for Residents, Occupancies, Ownerships, Family, and Delegates."""

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from apps.api.src.database.models.identity import User
from apps.api.src.database.models.membership import (
    ResidentDelegate,
    ResidentFamilyMember,
    ResidentProfile,
    UnitOccupancy,
    UnitOwnership,
    UserSocietyMembership,
)
from apps.api.src.database.models.society import Block, Unit
from apps.api.src.residents.domain.models import check_date_overlap


class ResidentRepository:
    """Repository for Resident Profile queries and tenant-scoped search."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_profile(self, user_id: UUID, society_id: UUID) -> ResidentProfile | None:
        """Fetch resident profile by user and society."""
        stmt = (
            select(ResidentProfile)
            .options(selectinload(ResidentProfile.user))
            .where(
                ResidentProfile.user_id == user_id,
                ResidentProfile.society_id == society_id,
                ResidentProfile.archived_at.is_(None),
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_profile_by_id(self, profile_id: UUID, society_id: UUID) -> ResidentProfile | None:
        """Fetch resident profile by its ID and society."""
        stmt = (
            select(ResidentProfile)
            .options(selectinload(ResidentProfile.user))
            .where(
                ResidentProfile.id == profile_id,
                ResidentProfile.society_id == society_id,
                ResidentProfile.archived_at.is_(None),
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def create_profile(
        self,
        user_id: UUID,
        society_id: UUID,
        emergency_contact_name: str | None = None,
        emergency_contact_phone: str | None = None,
        alternate_phone: str | None = None,
        preferred_contact_method: str = "APP",
        preferred_language: str = "en",
        accessibility_preferences: dict | None = None,
        communication_preferences: dict | None = None,
        status: str = "ACTIVE",
        notes: str | None = None,
    ) -> ResidentProfile:
        """Create new resident profile."""
        profile = ResidentProfile(
            id=uuid.uuid4(),
            user_id=user_id,
            society_id=society_id,
            emergency_contact_name=emergency_contact_name,
            emergency_contact_phone=emergency_contact_phone,
            alternate_phone=alternate_phone,
            preferred_contact_method=preferred_contact_method,
            preferred_language=preferred_language,
            accessibility_preferences=accessibility_preferences or {},
            communication_preferences=communication_preferences or {},
            status=status,
            notes=notes,
        )
        self.session.add(profile)
        await self.session.flush()
        # reload with user
        return await self.get_profile(user_id, society_id) or profile

    async def search_residents(
        self,
        society_id: UUID,
        query_str: str | None = None,
        unit_number: str | None = None,
        block_code: str | None = None,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[tuple[User, ResidentProfile]]:
        """
        Tenant-scoped resident search across users, memberships, and resident profiles.
        Never allows cross-society access.
        """
        stmt = (
            select(User, ResidentProfile)
            .join(
                UserSocietyMembership,
                (UserSocietyMembership.user_id == User.id)
                & (UserSocietyMembership.society_id == society_id)
                & (UserSocietyMembership.membership_status == "ACTIVE"),
            )
            .outerjoin(
                ResidentProfile,
                (ResidentProfile.user_id == User.id)
                & (ResidentProfile.society_id == society_id)
                & (ResidentProfile.archived_at.is_(None)),
            )
        )

        if status:
            stmt = stmt.where(ResidentProfile.status == status)

        if query_str:
            pattern = f"%{query_str}%"
            stmt = stmt.where(
                or_(
                    User.first_name.ilike(pattern),
                    User.last_name.ilike(pattern),
                    User.display_name.ilike(pattern),
                    User.phone.ilike(pattern),
                    User.email.ilike(pattern),
                )
            )

        if unit_number or block_code:
            stmt = stmt.join(UnitOccupancy, UnitOccupancy.user_id == User.id).join(
                Unit, Unit.id == UnitOccupancy.unit_id
            )
            if unit_number:
                stmt = stmt.where(Unit.unit_number.ilike(f"%{unit_number}%"))
            if block_code:
                stmt = stmt.join(Block, Block.id == Unit.block_id).where(Block.code.ilike(f"%{block_code}%"))

        stmt = stmt.distinct().order_by(User.display_name).limit(limit).offset(offset)
        result = await self.session.execute(stmt)
        return list(result.all())


class OccupancyRepository:
    """Repository for Unit Occupancy records."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_occupancy(self, occupancy_id: UUID, society_id: UUID) -> UnitOccupancy | None:
        """Fetch a specific occupancy record within tenant boundary."""
        stmt = (
            select(UnitOccupancy)
            .options(selectinload(UnitOccupancy.user), selectinload(UnitOccupancy.unit))
            .where(
                UnitOccupancy.id == occupancy_id,
                UnitOccupancy.society_id == society_id,
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_active_occupancies_for_unit(self, unit_id: UUID, society_id: UUID) -> list[UnitOccupancy]:
        """Fetch active occupancies for a unit."""
        stmt = (
            select(UnitOccupancy)
            .options(selectinload(UnitOccupancy.user), selectinload(UnitOccupancy.unit))
            .where(
                UnitOccupancy.unit_id == unit_id,
                UnitOccupancy.society_id == society_id,
                UnitOccupancy.status == "ACTIVE",
            )
            .order_by(UnitOccupancy.is_primary_contact.desc(), UnitOccupancy.valid_from.desc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_all_occupancies_for_unit(self, unit_id: UUID, society_id: UUID) -> list[UnitOccupancy]:
        """Fetch all occupancies (active and historical) for a unit."""
        stmt = (
            select(UnitOccupancy)
            .options(selectinload(UnitOccupancy.user), selectinload(UnitOccupancy.unit))
            .where(
                UnitOccupancy.unit_id == unit_id,
                UnitOccupancy.society_id == society_id,
            )
            .order_by(UnitOccupancy.valid_from.desc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_occupancies_for_user(
        self, user_id: UUID, society_id: UUID, active_only: bool = True
    ) -> list[UnitOccupancy]:
        """Fetch occupancies for a specific user."""
        stmt = (
            select(UnitOccupancy)
            .options(
                selectinload(UnitOccupancy.unit).selectinload(Unit.block),
                selectinload(UnitOccupancy.unit).selectinload(Unit.floor),
            )
            .where(
                UnitOccupancy.user_id == user_id,
                UnitOccupancy.society_id == society_id,
            )
        )
        if active_only:
            stmt = stmt.where(UnitOccupancy.status == "ACTIVE")
        stmt = stmt.order_by(UnitOccupancy.valid_from.desc())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def check_tenant_overlap(
        self,
        unit_id: UUID,
        society_id: UUID,
        start_date: date,
        end_date: date | None,
        exclude_occupancy_id: UUID | None = None,
    ) -> bool:
        """
        Check if an active TENANT occupancy overlaps with the specified date window.
        Multiple co-owners can occupy simultaneously, but disjoint rental leases cannot overlap.
        """
        stmt = select(UnitOccupancy).where(
            UnitOccupancy.unit_id == unit_id,
            UnitOccupancy.society_id == society_id,
            UnitOccupancy.relationship_type == "TENANT",
            UnitOccupancy.status == "ACTIVE",
        )
        if exclude_occupancy_id:
            stmt = stmt.where(UnitOccupancy.id != exclude_occupancy_id)

        result = await self.session.execute(stmt)
        existing_tenants = result.scalars().all()

        for occ in existing_tenants:
            occ_start = occ.valid_from or date.min
            occ_end = occ.valid_to
            if check_date_overlap(occ_start, occ_end, start_date, end_date):
                return True
        return False

    async def create_occupancy(
        self,
        society_id: UUID,
        unit_id: UUID,
        user_id: UUID,
        relationship_type: str,
        valid_from: date,
        valid_to: date | None = None,
        is_primary_contact: bool = False,
        status: str = "ACTIVE",
        notes: str | None = None,
    ) -> UnitOccupancy:
        """Create new unit occupancy."""
        occupancy = UnitOccupancy(
            id=uuid.uuid4(),
            society_id=society_id,
            unit_id=unit_id,
            user_id=user_id,
            relationship_type=relationship_type,
            is_primary_contact=is_primary_contact,
            valid_from=valid_from,
            valid_to=valid_to,
            status=status,
            notes=notes,
        )
        self.session.add(occupancy)
        await self.session.flush()
        return await self.get_occupancy(occupancy.id, society_id) or occupancy


class OwnershipRepository:
    """Repository for Unit Ownership records."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_ownership(self, ownership_id: UUID, society_id: UUID) -> UnitOwnership | None:
        """Fetch ownership record by ID within tenant boundary."""
        stmt = (
            select(UnitOwnership)
            .options(selectinload(UnitOwnership.user), selectinload(UnitOwnership.unit))
            .where(
                UnitOwnership.id == ownership_id,
                UnitOwnership.society_id == society_id,
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_active_ownerships_for_unit(self, unit_id: UUID, society_id: UUID) -> list[UnitOwnership]:
        """Fetch active ownerships for a unit."""
        stmt = (
            select(UnitOwnership)
            .options(selectinload(UnitOwnership.user), selectinload(UnitOwnership.unit))
            .where(
                UnitOwnership.unit_id == unit_id,
                UnitOwnership.society_id == society_id,
                UnitOwnership.status == "ACTIVE",
                or_(UnitOwnership.end_date.is_(None), UnitOwnership.end_date >= date.today()),
            )
            .order_by(UnitOwnership.is_primary.desc(), UnitOwnership.start_date.asc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_all_ownerships_for_unit(self, unit_id: UUID, society_id: UUID) -> list[UnitOwnership]:
        """Fetch all ownership records (active and historical) for a unit."""
        stmt = (
            select(UnitOwnership)
            .options(selectinload(UnitOwnership.user), selectinload(UnitOwnership.unit))
            .where(
                UnitOwnership.unit_id == unit_id,
                UnitOwnership.society_id == society_id,
            )
            .order_by(UnitOwnership.start_date.desc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_ownerships_for_user(
        self, user_id: UUID, society_id: UUID, active_only: bool = True
    ) -> list[UnitOwnership]:
        """Fetch ownership records for a user."""
        stmt = (
            select(UnitOwnership)
            .options(
                selectinload(UnitOwnership.unit).selectinload(Unit.block),
                selectinload(UnitOwnership.unit).selectinload(Unit.floor),
            )
            .where(
                UnitOwnership.user_id == user_id,
                UnitOwnership.society_id == society_id,
            )
        )
        if active_only:
            stmt = stmt.where(
                UnitOwnership.status == "ACTIVE",
                or_(UnitOwnership.end_date.is_(None), UnitOwnership.end_date >= date.today()),
            )
        stmt = stmt.order_by(UnitOwnership.start_date.desc())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_total_active_ownership_percentage(
        self, unit_id: UUID, society_id: UUID, exclude_ownership_id: UUID | None = None
    ) -> Decimal:
        """Sum active ownership percentages for a unit."""
        active = await self.get_active_ownerships_for_unit(unit_id, society_id)
        total = Decimal("0.00")
        for own in active:
            if exclude_ownership_id and own.id == exclude_ownership_id:
                continue
            total += own.ownership_percentage
        return total

    async def create_ownership(
        self,
        society_id: UUID,
        unit_id: UUID,
        user_id: UUID,
        ownership_percentage: Decimal,
        start_date: date,
        end_date: date | None = None,
        is_primary: bool = True,
        status: str = "ACTIVE",
        notes: str | None = None,
    ) -> UnitOwnership:
        """Create new unit ownership."""
        ownership = UnitOwnership(
            id=uuid.uuid4(),
            society_id=society_id,
            unit_id=unit_id,
            user_id=user_id,
            ownership_percentage=ownership_percentage,
            start_date=start_date,
            end_date=end_date,
            is_primary=is_primary,
            status=status,
            notes=notes,
        )
        self.session.add(ownership)
        await self.session.flush()
        return await self.get_ownership(ownership.id, society_id) or ownership


class FamilyRepository:
    """Repository for Resident Family Member records."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_family_member(self, member_id: UUID, society_id: UUID) -> ResidentFamilyMember | None:
        """Fetch a specific family member record within tenant boundary."""
        stmt = select(ResidentFamilyMember).where(
            ResidentFamilyMember.id == member_id,
            ResidentFamilyMember.society_id == society_id,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_family_members(
        self,
        unit_id: UUID,
        society_id: UUID,
        primary_resident_user_id: UUID | None = None,
        active_only: bool = True,
    ) -> list[ResidentFamilyMember]:
        """List family members for a unit or resident."""
        stmt = select(ResidentFamilyMember).where(
            ResidentFamilyMember.unit_id == unit_id,
            ResidentFamilyMember.society_id == society_id,
        )
        if primary_resident_user_id:
            stmt = stmt.where(ResidentFamilyMember.primary_resident_user_id == primary_resident_user_id)
        if active_only:
            stmt = stmt.where(ResidentFamilyMember.status == "ACTIVE")
        stmt = stmt.order_by(ResidentFamilyMember.created_at.asc())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def create_family_member(
        self,
        society_id: UUID,
        unit_id: UUID,
        primary_resident_user_id: UUID,
        name: str,
        relationship: str,
        phone: str | None = None,
        email: str | None = None,
        user_id: UUID | None = None,
        access_scope: dict | None = None,
        status: str = "ACTIVE",
    ) -> ResidentFamilyMember:
        """Add new family member."""
        member = ResidentFamilyMember(
            id=uuid.uuid4(),
            society_id=society_id,
            unit_id=unit_id,
            primary_resident_user_id=primary_resident_user_id,
            user_id=user_id,
            name=name,
            relationship=relationship,
            phone=phone,
            email=email,
            access_scope=access_scope or {},
            status=status,
        )
        self.session.add(member)
        await self.session.flush()
        return member


class DelegateRepository:
    """Repository for Resident Delegate authorizations."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_delegate(self, delegate_id: UUID, society_id: UUID) -> ResidentDelegate | None:
        """Fetch delegate record by ID within tenant boundary."""
        stmt = (
            select(ResidentDelegate)
            .options(
                selectinload(ResidentDelegate.delegator),
                selectinload(ResidentDelegate.delegate),
                selectinload(ResidentDelegate.unit),
            )
            .where(
                ResidentDelegate.id == delegate_id,
                ResidentDelegate.society_id == society_id,
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_delegates(
        self,
        unit_id: UUID | None = None,
        society_id: UUID | None = None,
        delegator_user_id: UUID | None = None,
        delegate_user_id: UUID | None = None,
        active_only: bool = True,
    ) -> list[ResidentDelegate]:
        """List delegates filtered by unit, delegator, or delegate."""
        stmt = select(ResidentDelegate).options(
            selectinload(ResidentDelegate.delegator),
            selectinload(ResidentDelegate.delegate),
            selectinload(ResidentDelegate.unit),
        )
        if society_id:
            stmt = stmt.where(ResidentDelegate.society_id == society_id)
        if unit_id:
            stmt = stmt.where(ResidentDelegate.unit_id == unit_id)
        if delegator_user_id:
            stmt = stmt.where(ResidentDelegate.delegator_user_id == delegator_user_id)
        if delegate_user_id:
            stmt = stmt.where(ResidentDelegate.delegate_user_id == delegate_user_id)
        if active_only:
            today = date.today()
            stmt = stmt.where(
                ResidentDelegate.status == "ACTIVE",
                ResidentDelegate.valid_from <= today,
                or_(ResidentDelegate.valid_to.is_(None), ResidentDelegate.valid_to >= today),
            )
        stmt = stmt.order_by(ResidentDelegate.created_at.desc())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def create_delegate(
        self,
        society_id: UUID,
        unit_id: UUID,
        delegator_user_id: UUID,
        delegate_user_id: UUID,
        permissions: list[str],
        valid_from: date,
        valid_to: date | None = None,
        notes: str | None = None,
    ) -> ResidentDelegate:
        """Create new delegate assignment."""
        del_obj = ResidentDelegate(
            id=uuid.uuid4(),
            society_id=society_id,
            unit_id=unit_id,
            delegator_user_id=delegator_user_id,
            delegate_user_id=delegate_user_id,
            permissions=permissions,
            valid_from=valid_from,
            valid_to=valid_to,
            status="ACTIVE",
            notes=notes,
        )
        self.session.add(del_obj)
        await self.session.flush()
        return await self.get_delegate(del_obj.id, society_id) or del_obj

    async def revoke_delegate(
        self,
        delegate_id: UUID,
        society_id: UUID,
        revoked_by: UUID,
        reason: str | None = None,
    ) -> ResidentDelegate:
        """Revoke a delegation."""
        delegate = await self.get_delegate(delegate_id, society_id)
        if not delegate:
            from apps.api.src.residents.domain.exceptions import DelegateNotFoundError

            raise DelegateNotFoundError()
        delegate.status = "REVOKED"
        delegate.revoked_at = datetime.now(UTC)
        delegate.revoked_by = revoked_by
        delegate.revocation_reason = reason
        await self.session.flush()
        return delegate

    async def has_active_delegation(
        self,
        delegate_user_id: UUID,
        unit_id: UUID,
        society_id: UUID,
        required_permission: str,
    ) -> bool:
        """Verify if delegate has an active delegation granting the required permission for the unit."""
        delegations = await self.list_delegates(
            unit_id=unit_id,
            society_id=society_id,
            delegate_user_id=delegate_user_id,
            active_only=True,
        )
        for d in delegations:
            if required_permission in d.permissions:
                return True
        return False

    async def is_delegate_authorized(
        self,
        society_id: UUID,
        delegate_user_id: UUID,
        unit_id: UUID,
        permission_code: str,
    ) -> bool:
        """
        Verify if a delegate user is actively authorized for a specific permission on a unit.
        Enforces:
        - Active delegation exists for this society, unit, and delegate user
        - Valid date window (valid_from <= today <= valid_to or valid_to is None)
        - Status is ACTIVE and not revoked (revoked_at is None)
        - Permission code is strictly in delegate's permissions list
        - Canonical RBAC module support: permissions for unreleased modules
          (e.g., complaint.create, visitor.manage) return False until corresponding
          domain routers and RBAC permissions are live.
        """
        ACTIVE_LIVE_PERMISSIONS = {"billing.view", "notice.view"}
        if permission_code not in ACTIVE_LIVE_PERMISSIONS:
            return False

        today = date.today()
        stmt = select(ResidentDelegate).where(
            ResidentDelegate.society_id == society_id,
            ResidentDelegate.unit_id == unit_id,
            ResidentDelegate.delegate_user_id == delegate_user_id,
            ResidentDelegate.status == "ACTIVE",
            ResidentDelegate.revoked_at.is_(None),
            ResidentDelegate.valid_from <= today,
            or_(ResidentDelegate.valid_to.is_(None), ResidentDelegate.valid_to >= today),
        )
        result = await self.session.execute(stmt)
        delegates = result.scalars().all()
        for d in delegates:
            if permission_code in d.permissions:
                return True
        return False
