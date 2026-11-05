"""Core Vendor Profile Application Service."""

from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.database.models.vendor import (
    VendorAddress,
    VendorContact,
    VendorProfile,
    VendorSocietyAssociation,
    VendorStatusHistory,
)
from apps.api.src.database.models.vendor import (
    VendorService as VendorServiceModel,
)
from apps.api.src.vendor.domain.concurrency import generate_vendor_code
from apps.api.src.vendor.domain.enums import VendorAssocStatus, VendorStatus
from apps.api.src.vendor.domain.exceptions import (
    VendorCategoryNotFoundException,
    VendorNotFoundException,
)
from apps.api.src.vendor.domain.state_machine import validate_status_transition
from apps.api.src.vendor.infrastructure.repositories import (
    VendorAssignmentHistoryRepository,
    VendorCategoryRepository,
    VendorProfileRepository,
    VendorStatusHistoryRepository,
)
from apps.api.src.vendor.schemas import (
    VendorProfileCreate,
    VendorProfileUpdate,
    VendorStatusUpdate,
)


class VendorService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.vendor_repo = VendorProfileRepository(db)
        self.category_repo = VendorCategoryRepository(db)
        self.status_hist_repo = VendorStatusHistoryRepository(db)
        self.assign_hist_repo = VendorAssignmentHistoryRepository(db)

    async def create_vendor(
        self, data: VendorProfileCreate, society_id: UUID, current_user_id: UUID
    ) -> VendorProfile:
        if data.primary_category_id:
            category = await self.category_repo.get_by_id(data.primary_category_id, society_id)
            if not category:
                raise VendorCategoryNotFoundException(str(data.primary_category_id))

        vendor_code = await generate_vendor_code(self.db, society_id)

        vendor = VendorProfile(
            society_id=society_id,
            vendor_code=vendor_code,
            legal_name=data.legal_name,
            display_name=data.display_name,
            vendor_type=data.vendor_type.value,
            description=data.description,
            primary_category_id=data.primary_category_id,
            status=data.status.value,
            created_by_user_id=current_user_id,
        )

        for c in data.contacts:
            vendor.contacts.append(
                VendorContact(
                    society_id=society_id,
                    name=c.name,
                    designation=c.designation,
                    phone=c.phone,
                    alternate_phone=c.alternate_phone,
                    email=c.email,
                    preferred_contact_method=c.preferred_contact_method.value,
                    is_primary=c.is_primary,
                )
            )

        for a in data.addresses:
            vendor.addresses.append(
                VendorAddress(
                    society_id=society_id,
                    address_line1=a.address_line1,
                    address_line2=a.address_line2,
                    city=a.city,
                    state=a.state,
                    postal_code=a.postal_code,
                    country=a.country,
                    is_primary=a.is_primary,
                )
            )

        for s in data.services:
            vendor.services.append(
                VendorServiceModel(
                    society_id=society_id,
                    service_name=s.service_name,
                    description=s.description,
                    category_id=s.category_id or data.primary_category_id,
                    is_active=s.is_active,
                )
            )

        created_vendor = await self.vendor_repo.create(vendor)

        assoc = VendorSocietyAssociation(
            vendor_id=created_vendor.id,
            society_id=society_id,
            status=VendorAssocStatus.ACTIVE.value,
        )
        self.db.add(assoc)

        hist = VendorStatusHistory(
            society_id=society_id,
            vendor_id=created_vendor.id,
            from_status=None,
            to_status=created_vendor.status,
            changed_by_user_id=current_user_id,
            reason="Initial vendor profile registration.",
        )
        await self.status_hist_repo.create(hist)

        return created_vendor

    async def get_vendor(
        self, vendor_id: UUID, society_id: UUID, include_archived: bool = False
    ) -> VendorProfile:
        vendor = await self.vendor_repo.get_by_id(vendor_id, society_id, include_archived=include_archived)
        if not vendor:
            raise VendorNotFoundException(str(vendor_id))
        return vendor

    async def list_vendors(
        self,
        society_id: UUID,
        status: str | None = None,
        category_id: UUID | None = None,
        search: str | None = None,
        page: int = 1,
        page_size: int = 20,
        include_archived: bool = False,
    ) -> tuple[list[VendorProfile], int]:
        return await self.vendor_repo.list_vendors(
            society_id=society_id,
            status=status,
            category_id=category_id,
            search=search,
            page=page,
            page_size=page_size,
            include_archived=include_archived,
        )

    async def update_vendor(
        self, vendor_id: UUID, data: VendorProfileUpdate, society_id: UUID
    ) -> VendorProfile:
        vendor = await self.get_vendor(vendor_id, society_id)

        if data.primary_category_id:
            category = await self.category_repo.get_by_id(data.primary_category_id, society_id)
            if not category:
                raise VendorCategoryNotFoundException(str(data.primary_category_id))
            vendor.primary_category_id = data.primary_category_id

        if data.legal_name is not None:
            vendor.legal_name = data.legal_name
        if data.display_name is not None:
            vendor.display_name = data.display_name
        if data.vendor_type is not None:
            vendor.vendor_type = data.vendor_type.value
        if data.description is not None:
            vendor.description = data.description

        await self.db.flush()
        return vendor

    async def update_status(
        self,
        vendor_id: UUID,
        data: VendorStatusUpdate,
        society_id: UUID,
        current_user_id: UUID,
        is_admin_override: bool = False,
    ) -> VendorProfile:
        vendor = await self.get_vendor(vendor_id, society_id)
        current_status = vendor.status
        target_status = data.target_status.value

        validate_status_transition(current_status, target_status, is_admin_override=is_admin_override)

        vendor.status = target_status

        hist = VendorStatusHistory(
            society_id=society_id,
            vendor_id=vendor.id,
            from_status=current_status,
            to_status=target_status,
            changed_by_user_id=current_user_id,
            reason=data.reason,
        )
        await self.status_hist_repo.create(hist)

        await self.db.flush()
        return vendor

    async def archive_vendor(self, vendor_id: UUID, society_id: UUID, current_user_id: UUID) -> VendorProfile:
        vendor = await self.get_vendor(vendor_id, society_id)

        current_status = vendor.status
        vendor.status = VendorStatus.OFFBOARDED.value
        vendor.archived_at = datetime.utcnow()

        hist = VendorStatusHistory(
            society_id=society_id,
            vendor_id=vendor.id,
            from_status=current_status,
            to_status=VendorStatus.OFFBOARDED.value,
            changed_by_user_id=current_user_id,
            reason="Soft-archived vendor profile.",
        )
        await self.status_hist_repo.create(hist)

        await self.db.flush()
        return vendor
