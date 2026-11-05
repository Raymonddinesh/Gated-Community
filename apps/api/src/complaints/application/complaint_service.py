"""Application Service for Complaint CRUD, Categories, Subcategories, and Policies."""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.complaints.domain.exceptions import (
    ComplaintCategoryNotFoundError,
    ComplaintNotFoundError,
    ComplaintSubcategoryNotFoundError,
    CrossSocietyComplaintError,
)
from apps.api.src.complaints.infrastructure.repositories import (
    ComplaintCategoryRepository,
    ComplaintRepository,
    ComplaintSLAPolicyRepository,
    ComplaintStatusHistoryRepository,
    ComplaintSubcategoryRepository,
)
from apps.api.src.complaints.schemas import (
    ComplaintCategoryCreateRequest,
    ComplaintCreateRequest,
    ComplaintSLAPolicyCreateRequest,
    ComplaintSubcategoryCreateRequest,
    ComplaintUpdateRequest,
)
from apps.api.src.database.models.audit import AuditLog
from apps.api.src.database.models.complaint import (
    Complaint,
    ComplaintCategory,
    ComplaintSLAPolicy,
    ComplaintStatusHistory,
    ComplaintSubcategory,
)
from apps.api.src.database.models.society import Unit
from apps.api.src.database.models.vehicle import Vehicle
from apps.api.src.database.models.visitor import Visitor


class ComplaintService:
    """Service handling complaints lifecycle, category configuration, and searching."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.complaint_repo = ComplaintRepository(session)
        self.category_repo = ComplaintCategoryRepository(session)
        self.subcategory_repo = ComplaintSubcategoryRepository(session)
        self.sla_repo = ComplaintSLAPolicyRepository(session)
        self.history_repo = ComplaintStatusHistoryRepository(session)

    # --- Category Management ---

    async def create_category(
        self,
        society_id: uuid.UUID,
        data: ComplaintCategoryCreateRequest,
    ) -> ComplaintCategory:
        category = ComplaintCategory(
            id=uuid.uuid4(),
            society_id=society_id,
            name=data.name.strip(),
            code=data.code.upper().strip(),
            description=data.description.strip() if data.description else None,
            icon=data.icon.strip() if data.icon else None,
            is_active=data.is_active,
            display_order=data.display_order,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        category.subcategories = []
        return await self.category_repo.save(category)

    async def list_categories(
        self,
        society_id: uuid.UUID,
        active_only: bool = True,
    ) -> list[ComplaintCategory]:
        return await self.category_repo.list_categories(society_id, active_only)

    async def create_subcategory(
        self,
        society_id: uuid.UUID,
        data: ComplaintSubcategoryCreateRequest,
    ) -> ComplaintSubcategory:
        category = await self.category_repo.get_by_id(data.category_id, society_id)
        if not category:
            raise ComplaintCategoryNotFoundError(data.category_id)

        subcategory = ComplaintSubcategory(
            id=uuid.uuid4(),
            society_id=society_id,
            category_id=data.category_id,
            name=data.name.strip(),
            code=data.code.upper().strip(),
            description=data.description.strip() if data.description else None,
            is_active=data.is_active,
            display_order=data.display_order,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        return await self.subcategory_repo.save(subcategory)

    # --- SLA Policy Management ---

    async def create_sla_policy(
        self,
        society_id: uuid.UUID,
        data: ComplaintSLAPolicyCreateRequest,
    ) -> ComplaintSLAPolicy:
        if data.category_id:
            category = await self.category_repo.get_by_id(data.category_id, society_id)
            if not category:
                raise ComplaintCategoryNotFoundError(data.category_id)

        policy = ComplaintSLAPolicy(
            id=uuid.uuid4(),
            society_id=society_id,
            category_id=data.category_id,
            priority=data.priority.value,
            acknowledgement_target_hours=data.acknowledgement_target_hours,
            resolution_target_hours=data.resolution_target_hours,
            is_active=data.is_active,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        return await self.sla_repo.save(policy)

    async def list_sla_policies(
        self,
        society_id: uuid.UUID,
    ) -> list[ComplaintSLAPolicy]:
        return await self.sla_repo.list_policies(society_id)

    # --- Complaint Core Lifecycle ---

    async def create_complaint(
        self,
        society_id: uuid.UUID,
        raised_by_user_id: uuid.UUID,
        data: ComplaintCreateRequest,
    ) -> Complaint:
        """Create a new complaint with strict same-society relational checks and SLA targets."""
        # 1. Validate Category
        category = await self.category_repo.get_by_id(data.category_id, society_id)
        if not category or not category.is_active:
            raise ComplaintCategoryNotFoundError(data.category_id)

        # 2. Validate Subcategory if provided
        if data.subcategory_id:
            subcategory = await self.subcategory_repo.get_by_id(data.subcategory_id, society_id)
            if not subcategory or subcategory.category_id != data.category_id or not subcategory.is_active:
                raise ComplaintSubcategoryNotFoundError(data.subcategory_id)

        # 3. Validate Unit if provided
        if data.unit_id:
            unit_res = await self.session.execute(
                select(Unit).where(Unit.id == data.unit_id, Unit.society_id == society_id)
            )
            if not unit_res.scalar_one_or_none():
                raise CrossSocietyComplaintError(f"Unit '{data.unit_id}' not found in this society")

        # 4. Validate Vehicle if provided
        if data.vehicle_id:
            veh_res = await self.session.execute(
                select(Vehicle).where(Vehicle.id == data.vehicle_id, Vehicle.society_id == society_id)
            )
            if not veh_res.scalar_one_or_none():
                raise CrossSocietyComplaintError(f"Vehicle '{data.vehicle_id}' not found in this society")

        # 5. Validate Visitor if provided
        if data.visitor_id:
            vis_res = await self.session.execute(
                select(Visitor).where(Visitor.id == data.visitor_id, Visitor.society_id == society_id)
            )
            if not vis_res.scalar_one_or_none():
                raise CrossSocietyComplaintError(f"Visitor '{data.visitor_id}' not found in this society")

        # 6. Generate Complaint Number atomically
        complaint_number = await self.complaint_repo.generate_complaint_number(society_id)

        # 7. Compute SLA deadlines
        sla_policy = await self.sla_repo.find_matching_policy(
            society_id=society_id,
            category_id=data.category_id,
            priority=data.priority.value,
        )

        now = datetime.now(UTC)
        ack_due_at = None
        due_at = None

        if sla_policy:
            ack_due_at = now + timedelta(hours=sla_policy.acknowledgement_target_hours)
            due_at = now + timedelta(hours=sla_policy.resolution_target_hours)

        complaint = Complaint(
            id=uuid.uuid4(),
            society_id=society_id,
            complaint_number=complaint_number,
            title=data.title.strip(),
            description=data.description.strip(),
            category_id=data.category_id,
            subcategory_id=data.subcategory_id,
            raised_by_user_id=raised_by_user_id,
            raised_for_unit_id=data.unit_id,
            priority=data.priority.value,
            source=data.source.value,
            status="OPEN",
            sla_policy_id=sla_policy.id if sla_policy else None,
            due_at=due_at,
            ack_due_at=ack_due_at,
            vehicle_id=data.vehicle_id,
            visitor_id=data.visitor_id,
            created_at=now,
            updated_at=now,
        )
        complaint.category = category
        await self.complaint_repo.save(complaint)

        # Record Initial Status History
        history = ComplaintStatusHistory(
            id=uuid.uuid4(),
            society_id=society_id,
            complaint_id=complaint.id,
            actor_user_id=raised_by_user_id,
            from_status=None,
            to_status="OPEN",
            reason="Complaint created",
            created_at=now,
        )
        await self.history_repo.save(history)

        # Audit event
        audit = AuditLog(
            id=uuid.uuid4(),
            society_id=society_id,
            actor_user_id=raised_by_user_id,
            action="complaint.created",
            entity_type="Complaint",
            entity_id=str(complaint.id),
            after_state={
                "complaint_number": complaint_number,
                "title": complaint.title,
                "category_id": str(data.category_id),
                "priority": data.priority.value,
                "source": data.source.value,
            },
        )
        self.session.add(audit)
        await self.session.flush()

        return complaint

    async def get_complaint(
        self,
        society_id: uuid.UUID,
        complaint_id: uuid.UUID,
    ) -> Complaint:
        complaint = await self.complaint_repo.get_by_id(complaint_id, society_id)
        if not complaint:
            raise ComplaintNotFoundError(complaint_id)
        return complaint

    async def search_complaints(
        self,
        society_id: uuid.UUID,
        query: str | None = None,
        status: str | None = None,
        priority: str | None = None,
        category_id: uuid.UUID | None = None,
        subcategory_id: uuid.UUID | None = None,
        unit_id: uuid.UUID | None = None,
        raised_by_user_id: uuid.UUID | None = None,
        assigned_user_id: uuid.UUID | None = None,
        page: int = 1,
        size: int = 50,
    ) -> tuple[list[Complaint], int]:
        return await self.complaint_repo.search(
            society_id=society_id,
            query=query,
            status=status,
            priority=priority,
            category_id=category_id,
            subcategory_id=subcategory_id,
            unit_id=unit_id,
            raised_by_user_id=raised_by_user_id,
            assigned_user_id=assigned_user_id,
            page=page,
            size=size,
        )

    async def update_complaint(
        self,
        society_id: uuid.UUID,
        complaint_id: uuid.UUID,
        data: ComplaintUpdateRequest,
    ) -> Complaint:
        complaint = await self.complaint_repo.get_by_id(complaint_id, society_id)
        if not complaint:
            raise ComplaintNotFoundError(complaint_id)

        if data.title is not None:
            complaint.title = data.title.strip()
        if data.description is not None:
            complaint.description = data.description.strip()
        if data.priority is not None:
            complaint.priority = data.priority.value
            sla_policy = await self.sla_repo.find_matching_policy(
                society_id=society_id,
                category_id=complaint.category_id,
                priority=data.priority.value,
            )
            if sla_policy:
                now = datetime.now(UTC)
                complaint.sla_policy_id = sla_policy.id
                complaint.ack_due_at = now + timedelta(hours=sla_policy.acknowledgement_target_hours)
                complaint.due_at = now + timedelta(hours=sla_policy.resolution_target_hours)

        complaint.updated_at = datetime.now(UTC)
        return await self.complaint_repo.save(complaint)
