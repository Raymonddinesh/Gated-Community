"""Pydantic V2 Schemas for Maintenance & Work Order Management Domain."""

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from apps.api.src.maintenance.domain.enums import (
    WorkOrderAssignmentType,
    WorkOrderCommentType,
    WorkOrderFileType,
    WorkOrderPriority,
    WorkOrderResolutionStatus,
    WorkOrderSource,
    WorkOrderStatus,
)

# --- Category & Subcategory Schemas ---


class MaintenanceSubcategoryResponse(BaseModel):
    id: uuid.UUID
    society_id: uuid.UUID
    category_id: uuid.UUID
    name: str
    code: str
    description: str | None = None
    is_active: bool
    display_order: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class MaintenanceCategoryResponse(BaseModel):
    id: uuid.UUID
    society_id: uuid.UUID
    name: str
    code: str
    description: str | None = None
    icon: str | None = None
    is_active: bool
    display_order: int
    created_at: datetime
    updated_at: datetime
    subcategories: list[MaintenanceSubcategoryResponse] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class MaintenanceCategoryCreateRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    code: str = Field(..., min_length=2, max_length=50)
    description: str | None = Field(None, max_length=500)
    icon: str | None = Field(None, max_length=100)
    display_order: int = Field(0, ge=0)


class MaintenanceCategoryUpdateRequest(BaseModel):
    name: str | None = Field(None, min_length=2, max_length=100)
    description: str | None = Field(None, max_length=500)
    icon: str | None = Field(None, max_length=100)
    is_active: bool | None = None
    display_order: int | None = Field(None, ge=0)


class MaintenanceSubcategoryCreateRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    code: str = Field(..., min_length=2, max_length=50)
    description: str | None = Field(None, max_length=500)
    display_order: int = Field(0, ge=0)


class MaintenanceSubcategoryUpdateRequest(BaseModel):
    name: str | None = Field(None, min_length=2, max_length=100)
    description: str | None = Field(None, max_length=500)
    is_active: bool | None = None
    display_order: int | None = Field(None, ge=0)


# --- Priority Policy Schemas ---


class MaintenancePriorityPolicyResponse(BaseModel):
    id: uuid.UUID
    society_id: uuid.UUID
    category_id: uuid.UUID | None = None
    priority: WorkOrderPriority
    target_resolution_hours: int
    escalation_threshold_hours: int
    requires_approval: bool
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class MaintenancePriorityPolicyCreateRequest(BaseModel):
    category_id: uuid.UUID | None = None
    priority: WorkOrderPriority
    target_resolution_hours: int = Field(72, gt=0)
    escalation_threshold_hours: int = Field(48, gt=0)
    requires_approval: bool = False


# --- Assignment Schemas ---


class WorkOrderAssignmentResponse(BaseModel):
    id: uuid.UUID
    society_id: uuid.UUID
    work_order_id: uuid.UUID
    assignment_type: WorkOrderAssignmentType
    target_user_id: uuid.UUID | None = None
    target_team_id: uuid.UUID | None = None
    assigned_by_user_id: uuid.UUID | None = None
    assigned_at: datetime
    unassigned_at: datetime | None = None
    reason: str | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class WorkOrderAssignmentCreateRequest(BaseModel):
    assignment_type: WorkOrderAssignmentType = WorkOrderAssignmentType.INTERNAL_USER
    target_user_id: uuid.UUID | None = None
    target_team_id: uuid.UUID | None = None
    reason: str | None = Field(None, max_length=500)


# --- Comment Schemas ---


class WorkOrderCommentResponse(BaseModel):
    id: uuid.UUID
    society_id: uuid.UUID
    work_order_id: uuid.UUID
    user_id: uuid.UUID
    user_name: str | None = None
    comment_text: str
    comment_type: WorkOrderCommentType
    is_internal: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class WorkOrderCommentCreateRequest(BaseModel):
    comment_text: str = Field(..., min_length=1, max_length=4000)
    comment_type: WorkOrderCommentType = WorkOrderCommentType.PUBLIC


# --- Attachment Schemas ---


class WorkOrderAttachmentResponse(BaseModel):
    id: uuid.UUID
    society_id: uuid.UUID
    work_order_id: uuid.UUID
    uploaded_by_user_id: uuid.UUID
    file_name: str
    file_type: WorkOrderFileType
    file_size: int
    mime_type: str
    is_archived: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# --- History, Activity, Escalation & Resolution Schemas ---


class WorkOrderStatusHistoryResponse(BaseModel):
    id: uuid.UUID
    society_id: uuid.UUID
    work_order_id: uuid.UUID
    from_status: str | None = None
    to_status: str
    changed_by_user_id: uuid.UUID
    reason: str | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class WorkOrderActivityResponse(BaseModel):
    id: uuid.UUID
    society_id: uuid.UUID
    work_order_id: uuid.UUID
    event_type: str
    description: str
    actor_user_id: uuid.UUID | None = None
    metadata_json: str | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class WorkOrderEscalationResponse(BaseModel):
    id: uuid.UUID
    society_id: uuid.UUID
    work_order_id: uuid.UUID
    escalation_level: int
    reason: str
    status: str
    triggered_at: datetime
    triggered_by_user_id: uuid.UUID | None = None
    target_user_id: uuid.UUID | None = None
    target_team_id: uuid.UUID | None = None
    resolved_at: datetime | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class WorkOrderResolutionResponse(BaseModel):
    id: uuid.UUID
    society_id: uuid.UUID
    work_order_id: uuid.UUID
    resolved_by_user_id: uuid.UUID
    resolution_summary: str
    resolution_code: str | None = None
    resolution_evidence: str | None = None
    verification_required: bool
    verified_by_user_id: uuid.UUID | None = None
    verified_at: datetime | None = None
    verification_comment: str | None = None
    status: WorkOrderResolutionStatus
    resolved_at: datetime
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class WorkOrderResolutionCreateRequest(BaseModel):
    resolution_summary: str = Field(..., min_length=5, max_length=4000)
    resolution_code: str | None = Field(None, max_length=50)
    resolution_evidence: str | None = Field(None, max_length=500)
    verification_required: bool = True


class WorkOrderResolutionVerifyRequest(BaseModel):
    accepted: bool
    verification_comment: str | None = Field(None, max_length=2000)


# --- Material Usage Schemas ---


class WorkOrderMaterialUsageResponse(BaseModel):
    id: uuid.UUID
    society_id: uuid.UUID
    work_order_id: uuid.UUID
    material_name: str
    description: str | None = None
    quantity: Decimal
    unit: str
    estimated_unit_cost: Decimal | None = None
    actual_unit_cost: Decimal | None = None
    notes: str | None = None
    created_by_user_id: uuid.UUID
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class WorkOrderMaterialUsageCreateRequest(BaseModel):
    material_name: str = Field(..., min_length=2, max_length=150)
    description: str | None = Field(None, max_length=500)
    quantity: Decimal = Field(Decimal("1.00"), gt=0)
    unit: str = Field("units", max_length=50)
    estimated_unit_cost: Decimal | None = Field(None, ge=0)
    actual_unit_cost: Decimal | None = Field(None, ge=0)
    notes: str | None = Field(None, max_length=500)


# --- Work Order Core Schemas ---


class WorkOrderCreateRequest(BaseModel):
    title: str = Field(..., min_length=3, max_length=200)
    description: str = Field(..., min_length=5, max_length=4000)
    category_id: uuid.UUID
    subcategory_id: uuid.UUID | None = None
    source: WorkOrderSource = WorkOrderSource.ADMIN
    complaint_id: uuid.UUID | None = None
    unit_id: uuid.UUID | None = None
    block_id: uuid.UUID | None = None
    priority: WorkOrderPriority = WorkOrderPriority.MEDIUM
    requested_for_unit_id: uuid.UUID | None = None
    vehicle_id: uuid.UUID | None = None
    visitor_id: uuid.UUID | None = None
    scheduled_start_at: datetime | None = None
    scheduled_end_at: datetime | None = None


class WorkOrderUpdateRequest(BaseModel):
    title: str | None = Field(None, min_length=3, max_length=200)
    description: str | None = Field(None, min_length=5, max_length=4000)
    category_id: uuid.UUID | None = None
    subcategory_id: uuid.UUID | None = None
    priority: WorkOrderPriority | None = None


class WorkOrderScheduleRequest(BaseModel):
    scheduled_start_at: datetime
    scheduled_end_at: datetime
    estimated_start_at: datetime | None = None


class WorkOrderStatusUpdateRequest(BaseModel):
    status: WorkOrderStatus
    reason: str | None = Field(None, max_length=1000)


class WorkOrderResponse(BaseModel):
    id: uuid.UUID
    society_id: uuid.UUID
    work_order_number: str
    title: str
    description: str
    category_id: uuid.UUID
    subcategory_id: uuid.UUID | None = None
    source: WorkOrderSource
    complaint_id: uuid.UUID | None = None
    unit_id: uuid.UUID | None = None
    block_id: uuid.UUID | None = None
    priority: WorkOrderPriority
    status: WorkOrderStatus
    requested_by_user_id: uuid.UUID | None = None
    requested_for_unit_id: uuid.UUID | None = None
    current_assignment_id: uuid.UUID | None = None
    estimated_start_at: datetime | None = None
    scheduled_start_at: datetime | None = None
    scheduled_end_at: datetime | None = None
    actual_start_at: datetime | None = None
    actual_end_at: datetime | None = None
    due_at: datetime | None = None
    resolved_at: datetime | None = None
    closed_at: datetime | None = None
    cancelled_at: datetime | None = None
    resolution_summary: str | None = None
    vehicle_id: uuid.UUID | None = None
    visitor_id: uuid.UUID | None = None
    created_by_user_id: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime

    category: MaintenanceCategoryResponse | None = None
    subcategory: MaintenanceSubcategoryResponse | None = None
    resolution: WorkOrderResolutionResponse | None = None

    model_config = ConfigDict(from_attributes=True)
