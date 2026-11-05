import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from apps.api.src.subscriptions.enums import EntitlementSource, EntitlementType


class EffectiveEntitlement(BaseModel):
    """Result of resolving an entitlement through the approved precedence pipeline."""

    model_config = ConfigDict(frozen=True)

    entitlement_key: str
    entitlement_type: EntitlementType
    value: str
    source: EntitlementSource
    is_enabled: bool
    limit: int | None = None
    is_unlimited: bool = False
    society_id: UUID
    plan_code: str | None = None
    override_id: UUID | None = None
    diagnostics: dict[str, Any] = Field(default_factory=dict)


class EffectiveQuota(BaseModel):
    """Result of evaluating effective quota availability and limits for a society."""

    model_config = ConfigDict(frozen=True)

    quota_key: str
    is_allowed: bool
    is_unlimited: bool
    max_limit: int | None = None
    source: EntitlementSource
    society_id: UUID
    plan_code: str | None = None


class UsageReservationResult(BaseModel):
    """Result of an atomic, race-safe quota reservation."""

    model_config = ConfigDict(frozen=True)

    quota_key: str
    previous_usage: int
    requested_increment: int
    new_usage: int
    max_limit: int | None = None
    is_unlimited: bool = False
    society_id: UUID


class UsageDiagnostic(BaseModel):
    """Usage diagnostics and utilization calculation for a society usage metric."""

    model_config = ConfigDict(frozen=True)

    metric_key: str
    current_value: int
    last_calculated_at: datetime
    quota_limit: int | None = None
    is_unlimited: bool = False
    utilization_percentage: float | None = None
    society_id: UUID


class InitialAdminPayload(BaseModel):
    """Payload for primary society administrator user."""

    model_config = ConfigDict(extra="forbid")

    email: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=32)
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)

    @field_validator("email")
    @classmethod
    def validate_email_format(cls, v: str | None) -> str | None:
        if v is not None:
            v = v.strip().lower()
            if "@" not in v or "." not in v:
                raise ValueError("Invalid email format.")
        return v


class InitialSpatialPayload(BaseModel):
    """Payload for initial spatial structure."""

    model_config = ConfigDict(extra="forbid")

    create_default_block: bool = Field(default=True)
    default_block_name: str = Field(default="Tower A", max_length=100)


class ProvisionSocietyRequest(BaseModel):
    """Validated input contract for provisioning a new tenant society."""

    model_config = ConfigDict(extra="forbid")

    provisioning_request_id: UUID = Field(
        default_factory=uuid.uuid4,
        description="Client-supplied or auto-generated idempotency identifier.",
    )
    legal_name: str = Field(..., min_length=3, max_length=255)
    display_name: str = Field(..., min_length=2, max_length=255)
    registration_number: str | None = Field(default=None, max_length=100)
    address_line1: str = Field(..., min_length=3, max_length=255)
    address_line2: str | None = Field(default=None, max_length=255)
    city: str = Field(..., min_length=2, max_length=100)
    state: str = Field(..., min_length=2, max_length=100)
    country: str = Field(default="IN", min_length=2, max_length=10)
    postal_code: str = Field(..., min_length=3, max_length=20)
    timezone: str = Field(default="Asia/Kolkata", max_length=50)
    default_language: str = Field(default="en", max_length=10)

    # Subscription Plan
    plan_code: str = Field(..., min_length=2, max_length=50)
    skip_trial: bool = Field(default=False)

    # Initial Admin & Spatial
    admin_user: InitialAdminPayload
    spatial: InitialSpatialPayload = Field(default_factory=InitialSpatialPayload)

    @field_validator("legal_name", "display_name", "address_line1", "city", "state", "postal_code")
    @classmethod
    def validate_non_empty_strings(cls, v: str) -> str:
        trimmed = v.strip()
        if not trimmed:
            raise ValueError("Field cannot be blank or whitespace-only.")
        return trimmed


class ProvisioningStepLogResponse(BaseModel):
    """Step execution status log for diagnostics."""

    model_config = ConfigDict(from_attributes=True)

    step_key: str
    status: str
    started_at: datetime
    completed_at: datetime | None = None
    message: str | None = None


class ProvisionSocietyResponse(BaseModel):
    """Successful provisioning response contract."""

    model_config = ConfigDict(from_attributes=True)

    provisioning_request_id: UUID
    society_id: UUID
    legal_name: str
    display_name: str
    status: str
    onboarding_status: str
    plan_code: str
    subscription_status: str
    trial_ends_at: datetime | None = None
    current_period_end: datetime
    admin_user_id: UUID
    admin_email: str | None = None
    created_at: datetime
    completed_at: datetime
    is_idempotent_replay: bool = False
    steps: list[ProvisioningStepLogResponse] = Field(default_factory=list)


# ==============================================================================
# Phase 21D: Platform Administration Schemas
# ==============================================================================


class SocietyDirectoryItemResponse(BaseModel):
    """Summarized society record for platform directory search and listing."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    legal_name: str
    display_name: str
    registration_number: str | None = None
    city: str
    state: str
    country: str = "IN"
    postal_code: str
    status: str
    onboarding_status: str
    plan_code: str | None = None
    subscription_status: str | None = None
    created_at: datetime
    updated_at: datetime


class SocietyDirectoryResponse(BaseModel):
    """Paginated response contract for platform society directory."""

    model_config = ConfigDict(from_attributes=True)

    items: list[SocietyDirectoryItemResponse]
    total: int
    page: int
    page_size: int
    pages: int


class SocietySubscriptionBriefResponse(BaseModel):
    """Brief subscription status contract for society administration views."""

    model_config = ConfigDict(from_attributes=True)

    plan_code: str
    plan_name: str
    status: str
    starts_at: datetime
    trial_ends_at: datetime | None = None
    current_period_end: datetime
    past_due_since: datetime | None = None
    suspended_at: datetime | None = None
    cancelled_at: datetime | None = None


class SocietyPrimaryAdminResponse(BaseModel):
    """Masked identity metadata for a society's primary administrator."""

    model_config = ConfigDict(from_attributes=True)

    user_id: UUID
    name: str
    email_masked: str | None = None
    phone_masked: str | None = None
    status: str


class SocietyAdminDetailResponse(BaseModel):
    """Detailed administrative view of a society including subscription and primary admin."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    legal_name: str
    display_name: str
    registration_number: str | None = None
    address_line1: str
    address_line2: str | None = None
    city: str
    state: str
    country: str
    postal_code: str
    timezone: str
    default_language: str
    status: str
    onboarding_status: str
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None = None
    subscription: SocietySubscriptionBriefResponse | None = None
    primary_admin: SocietyPrimaryAdminResponse | None = None


class SocietyLifecycleActionRequest(BaseModel):
    """Request payload for administrative lifecycle transitions (suspend, reactivate)."""

    model_config = ConfigDict(extra="forbid")

    reason: str = Field(
        ...,
        min_length=10,
        max_length=500,
        description="Mandatory administrative reason (at least 10 non-whitespace characters).",
    )
    notes: str | None = Field(default=None, max_length=1000)

    @field_validator("reason")
    @classmethod
    def validate_reason(cls, v: str) -> str:
        trimmed = v.strip()
        if len(trimmed) < 10:
            raise ValueError("Reason must contain at least 10 non-whitespace characters.")
        return trimmed


class SocietyLifecycleActionResponse(BaseModel):
    """Response contract following an administrative society lifecycle state transition."""

    model_config = ConfigDict(from_attributes=True)

    society_id: UUID
    previous_status: str
    current_status: str
    reason: str
    actor_user_id: UUID
    executed_at: datetime
    subscription_status: str | None = None


class SocietySubscriptionOverviewResponse(BaseModel):
    """Consolidated view of society subscription, effective features, and quota usage."""

    model_config = ConfigDict(from_attributes=True)

    society_id: UUID
    plan_code: str
    plan_name: str
    subscription_status: str
    starts_at: datetime
    trial_ends_at: datetime | None = None
    current_period_end: datetime
    features: list[EffectiveEntitlement]
    quotas: list[EffectiveQuota]


class SocietyProvisioningDiagnosticsResponse(BaseModel):
    """Diagnostic breakdown of provisioning steps and last recorded failure."""

    model_config = ConfigDict(from_attributes=True)

    society_id: UUID
    onboarding_status: str
    is_retryable: bool
    steps: list[ProvisioningStepLogResponse] = Field(default_factory=list)
    last_failure: dict[str, Any] | None = None


# ==============================================================================
# Phase 21E.2 — Subscription State Machine & Proration Engine Schemas
# ==============================================================================


class SubscriptionTransitionRequest(BaseModel):
    """Request contract for initiating a subscription state machine transition."""

    model_config = ConfigDict(extra="forbid")

    to_status: str = Field(
        ...,
        description="Target subscription state (ACTIVE, PAST_DUE, SUSPENDED, CANCELLED).",
    )
    reason: str = Field(
        ...,
        min_length=5,
        max_length=500,
        description="Mandatory business reason for lifecycle state transition.",
    )
    actor_type: str = Field(
        default="USER",
        description="Originating actor type (USER, SYSTEM, WEBHOOK).",
    )
    actor_id: UUID | None = Field(
        default=None,
        description="User UUID initiating transition, if applicable.",
    )
    correlation_id: str | None = Field(
        default=None,
        max_length=100,
        description="Optional tracking or correlation identifier.",
    )


class SubscriptionTransitionResponse(BaseModel):
    """Response contract emitted following an atomic subscription state transition."""

    model_config = ConfigDict(from_attributes=True)

    subscription_id: UUID
    society_id: UUID
    previous_status: str
    current_status: str
    transition_reason: str
    executed_at: datetime

    @property
    def new_status(self) -> str:
        return self.current_status

    @property
    def status(self) -> str:
        return self.current_status


class ProrationResult(BaseModel):
    """Detailed mathematical breakdown of an unused time proration calculation."""

    model_config = ConfigDict(frozen=True)

    total_seconds: Decimal
    remaining_seconds: Decimal
    unused_fraction: Decimal
    eligible_amount: Decimal
    prorated_amount: Decimal
    is_zero_duration: bool = False

    @property
    def remaining_fraction(self) -> Decimal:
        return self.unused_fraction

    @property
    def used_fraction(self) -> Decimal:
        return Decimal("1.00000000") - self.unused_fraction


class UpgradeCalculationResult(BaseModel):
    """Deterministic calculation of plan upgrade payable amount with prorated credit."""

    model_config = ConfigDict(frozen=True)

    current_plan_id: UUID
    current_plan_code: str
    target_plan_id: UUID
    target_plan_code: str
    current_plan_rate: Decimal
    target_plan_rate: Decimal
    unused_credit: Decimal
    target_charge: Decimal
    net_payable: Decimal
    proration_fraction: Decimal
    effective_at: datetime
    period_start: datetime
    period_end: datetime
    credit_note_amount: Decimal = Decimal("0.00")
    is_minimum_charge_waived: bool = False

    @property
    def new_plan_charge(self) -> Decimal:
        return self.target_charge

    @property
    def remaining_fraction(self) -> Decimal:
        return self.proration_fraction


class ScheduledDowngradeResponse(BaseModel):
    """Response contract for a scheduled subscription plan downgrade."""

    model_config = ConfigDict(from_attributes=True)

    subscription_id: UUID
    society_id: UUID
    current_plan_id: UUID
    scheduled_plan_id: UUID
    target_plan_code: str | None = None
    effective_date: datetime
    reason: str
    status: str

    @property
    def effective_at(self) -> datetime:
        return self.effective_date

    @property
    def active_until(self) -> datetime:
        return self.effective_date



