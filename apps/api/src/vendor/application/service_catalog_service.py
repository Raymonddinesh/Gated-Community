"""Vendor Services & Contacts Catalog Application Service."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.database.models.vendor import (
    VendorContact,
    VendorService,
)
from apps.api.src.vendor.domain.exceptions import (
    VendorCategoryNotFoundException,
    VendorNotFoundException,
)
from apps.api.src.vendor.infrastructure.repositories import (
    VendorCategoryRepository,
    VendorContactRepository,
    VendorProfileRepository,
    VendorServiceRepository,
)
from apps.api.src.vendor.schemas import (
    VendorContactCreate,
    VendorServiceCreate,
)


class VendorCatalogService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.vendor_repo = VendorProfileRepository(db)
        self.contact_repo = VendorContactRepository(db)
        self.service_repo = VendorServiceRepository(db)
        self.category_repo = VendorCategoryRepository(db)

    async def add_contact(
        self, vendor_id: UUID, data: VendorContactCreate, society_id: UUID
    ) -> VendorContact:
        vendor = await self.vendor_repo.get_by_id(vendor_id, society_id)
        if not vendor:
            raise VendorNotFoundException(str(vendor_id))

        contact = VendorContact(
            society_id=society_id,
            vendor_id=vendor_id,
            name=data.name,
            designation=data.designation,
            phone=data.phone,
            alternate_phone=data.alternate_phone,
            email=data.email,
            preferred_contact_method=data.preferred_contact_method.value,
            is_primary=data.is_primary,
        )
        return await self.contact_repo.create(contact)

    async def list_contacts(self, vendor_id: UUID, society_id: UUID) -> list[VendorContact]:
        vendor = await self.vendor_repo.get_by_id(vendor_id, society_id)
        if not vendor:
            raise VendorNotFoundException(str(vendor_id))
        return await self.contact_repo.list_by_vendor(vendor_id, society_id)

    async def add_service(
        self, vendor_id: UUID, data: VendorServiceCreate, society_id: UUID
    ) -> VendorService:
        vendor = await self.vendor_repo.get_by_id(vendor_id, society_id)
        if not vendor:
            raise VendorNotFoundException(str(vendor_id))

        if data.category_id:
            category = await self.category_repo.get_by_id(data.category_id, society_id)
            if not category:
                raise VendorCategoryNotFoundException(str(data.category_id))

        service = VendorService(
            society_id=society_id,
            vendor_id=vendor_id,
            service_name=data.service_name,
            description=data.description,
            category_id=data.category_id or vendor.primary_category_id,
            is_active=data.is_active,
        )
        return await self.service_repo.create(service)

    async def list_services(
        self, vendor_id: UUID, society_id: UUID, active_only: bool = False
    ) -> list[VendorService]:
        vendor = await self.vendor_repo.get_by_id(vendor_id, society_id)
        if not vendor:
            raise VendorNotFoundException(str(vendor_id))
        return await self.service_repo.list_by_vendor(vendor_id, society_id, active_only=active_only)
