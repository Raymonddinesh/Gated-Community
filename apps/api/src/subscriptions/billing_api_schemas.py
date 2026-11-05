"""Phase 21E.5 — Tenant & Platform Billing API Contracts and Schemas.

Defines standardized Pydantic request and response models for:
- Platform subscription plans and plan entitlements.
- Global subscription monitoring and administrative state transitions.
- Global payment transactions and outbound refund history.
- Billing adjustments and tenant advance credit balances.
- Standardized PaginatedResponse[T] container.
- Tenant-facing plan upgrade, downgrade, cancellation, and checkout contracts.
"""

from datetime import datetime
from decimal import Decimal
from typing import Any, Generic, TypeVar
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

T = TypeVar("T")


class PaginatedResponse(BaseModel, Generic[T]):  # noqa: UP046
    """Standardized generic paginated response container."""

    model_config = ConfigDict(from_attributes=True)

    items: list[T]
    total: int
    page: int
    page_size: int
    pages: int


# ==============================================================================
# 1. Platform Subscription Plan & Entitlement Schemas
# ==============================================================================


class PlanEntitlementItem(BaseModel):
    """Single entitlement item within a platform subscription plan."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID | None = None
    entitlement_key: str = Field(..., min_length=2, max_length=100)
    entitlement_type: str = Field(..., pattern="^(BOOLEAN|NUMERIC|UNLIMITED)$")
    entitlement_value: str = Field(..., min_length=1, max_length=255)


class PlatformSubscriptionPlanResponse(BaseModel):
    """Complete platform subscription plan definition including entitlements."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    plan_code: str
    display_name: str
    description: str | None = None
    monthly_price: Decimal
    annual_price: Decimal
    currency_code: str
    trial_days: int
    is_active: bool
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None = None
    entitlements: list[PlanEntitlementItem] = Field(default_factory=list)


class PlatformPlanCreateRequest(BaseModel):
    """Payload to create a new subscription plan."""

    model_config = ConfigDict(extra="forbid")

    plan_code: str = Field(..., min_length=2, max_length=50, pattern="^[A-Z0-9_-]+$")
    display_name: str = Field(..., min_length=2, max_length=100)
    description: str | None = Field(default=None, max_length=1000)
    monthly_price: Decimal = Field(..., ge=0)
    annual_price: Decimal = Field(..., ge=0)
    currency_code: str = Field(default="INR", min_length=3, max_length=3)
    trial_days: int = Field(default=14, ge=0)
    is_active: bool = Field(default=True)
    entitlements: list[PlanEntitlementItem] = Field(default_factory=list)


class PlatformPlanUpdateRequest(BaseModel):
    """Payload to update an existing subscription plan."""

    model_config = ConfigDict(extra="forbid")

    display_name: str | None = Field(default=None, min_length=2, max_length=100)
    description: str | None = Field(default=None, max_length=1000)
    monthly_price: Decimal | None = Field(default=None, ge=0)
    annual_price: Decimal | None = Field(default=None, ge=0)
    trial_days: int | None = Field(default=None, ge=0)
    is_active: bool | None = None
    entitlements: list[PlanEntitlementItem] | None = None


# ==============================================================================
# 2. Global Platform Subscription Monitoring Schemas
# ==============================================================================


class PlatformSubscriptionListItemResponse(BaseModel):
    """Summary item for global subscription monitoring."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    society_id: UUID
    society_name: str
    plan_id: UUID
    plan_code: str
    plan_name: str
    status: str
    billing_cycle: str
    auto_renew: bool
    starts_at: datetime
    trial_ends_at: datetime | None = None
    current_period_start: datetime
    current_period_end: datetime
    next_billing_at: datetime | None = None
    past_due_since: datetime | None = None
    suspended_at: datetime | None = None
    cancelled_at: datetime | None = None


# ==============================================================================
# 3. Global Platform Payment & Refund Schemas
# ==============================================================================


class PlatformPaymentListItemResponse(BaseModel):
    """Summary item for captured payments listing."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    society_id: UUID
    invoice_id: UUID | None = None
    gateway_provider: str
    gateway_payment_id: str
    payment_method: str
    amount: Decimal
    refunded_amount: Decimal
    currency_code: str
    status: str
    reconciliation_status: str
    captured_at: datetime
    is_settled: bool
    settled_at: datetime | None = None


class PlatformPaymentDetailResponse(PlatformPaymentListItemResponse):
    """Detailed payment transaction record."""

    card_network: str | None = None
    card_last4: str | None = None
    upi_vpa: str | None = None
    gateway_fee: Decimal = Decimal("0.00")
    gateway_tax: Decimal = Decimal("0.00")
    refunds: list[Any] = Field(default_factory=list)


class PlatformRefundListItemResponse(BaseModel):
    """Summary item for refunds listing."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    payment_id: UUID
    society_id: UUID
    gateway_provider: str
    gateway_refund_id: str | None = None
    amount: Decimal
    currency_code: str
    reason: str
    status: str
    created_at: datetime


# ==============================================================================
# 4. Platform Billing Adjustment & Advance Balance Schemas
# ==============================================================================


class PlatformBillingAdjustmentCreate(BaseModel):
    """Payload to create a manual billing adjustment or goodwill waiver."""

    model_config = ConfigDict(extra="forbid")

    adjustment_type: str = Field(
        ...,
        pattern="^(GOODWILL_WAIVER|ADVANCE_BALANCE|PRORATION_CREDIT|MINIMUM_CHARGE_ROUNDOFF)$",
    )
    amount: Decimal = Field(
        ...,
        description="Adjustment amount in INR (positive for credits, negative for deductions)",
    )
    reason: str = Field(..., min_length=5, max_length=255, description="Administrative justification")
    idempotency_key: str | None = Field(default=None, max_length=150)
    invoice_id: UUID | None = None

    @field_validator("amount")
    @classmethod
    def validate_amount_nonzero(cls, v: Decimal) -> Decimal:
        if v == Decimal("0.00"):
            raise ValueError("Adjustment amount cannot be zero.")
        return v


class PlatformBillingAdjustmentResponse(BaseModel):
    """Representation of an applied billing adjustment."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    society_id: UUID
    invoice_id: UUID | None = None
    credit_note_id: UUID | None = None
    adjustment_type: str
    amount: Decimal
    currency_code: str
    idempotency_key: str | None = None
    reason: str
    applied_at: datetime
    created_by: UUID | None = None
    created_at: datetime


class SocietyAdvanceBalanceResponse(BaseModel):
    """Aggregated advance balance for a society."""

    model_config = ConfigDict(from_attributes=True)

    society_id: UUID
    currency_code: str = "INR"
    current_balance: Decimal
    total_credits_granted: Decimal
    total_credits_utilized: Decimal


# ==============================================================================
# 5. Tenant-Facing Upgrade & Lifecycle Schemas
# ==============================================================================


class TenantUpgradePreviewRequest(BaseModel):
    """Request payload to simulate a mid-cycle plan upgrade."""

    model_config = ConfigDict(extra="forbid")

    target_plan_id: UUID


class TenantUpgradeExecuteRequest(BaseModel):
    """Request payload to execute a mid-cycle plan upgrade."""

    model_config = ConfigDict(extra="forbid")

    target_plan_id: UUID
    idempotency_key: str | None = Field(default=None, max_length=100)


class TenantUpgradeExecuteResponse(BaseModel):
    """Response returned upon plan upgrade execution."""

    model_config = ConfigDict(from_attributes=True)

    society_id: UUID
    previous_plan_code: str
    new_plan_code: str
    prorated_credit: Decimal
    target_charge: Decimal
    net_payable: Decimal
    is_instant_upgrade: bool
    invoice_id: UUID | None = None
    payment_order: Any | None = None


class TenantDowngradeRequest(BaseModel):
    """Request payload to schedule a plan downgrade at renewal."""

    model_config = ConfigDict(extra="forbid")

    target_plan_id: UUID
    reason: str = Field(..., min_length=5, max_length=255)


class TenantSubscriptionCancelRequest(BaseModel):
    """Request payload to schedule cancellation at period end."""

    model_config = ConfigDict(extra="forbid")

    reason: str = Field(..., min_length=5, max_length=500)


class TenantSubscriptionResumeResponse(BaseModel):
    """Response returned when auto-renew is re-enabled."""

    model_config = ConfigDict(from_attributes=True)

    society_id: UUID
    subscription_id: UUID
    status: str
    auto_renew: bool
    message: str


class TenantCheckoutResponse(BaseModel):
    """Server-side payment order details for frontend checkout modal."""

    model_config = ConfigDict(from_attributes=True)

    order_id: str
    invoice_id: UUID
    amount: Decimal
    currency: str
    gateway_provider: str
    key_id: str | None = None


class TenantSubscriptionOverview(BaseModel):
    """Consolidated tenant-facing subscription status with plan and entitlements."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    society_id: UUID
    plan_id: UUID
    plan: PlatformSubscriptionPlanResponse
    status: str
    billing_cycle: str
    auto_renew: bool
    starts_at: datetime
    trial_ends_at: datetime | None = None
    current_period_start: datetime
    current_period_end: datetime
    next_billing_at: datetime | None = None
    past_due_since: datetime | None = None
    suspended_at: datetime | None = None
    cancelled_at: datetime | None = None
    cancellation_reason: str | None = None
    pending_downgrade_plan_id: UUID | None = None
    pending_downgrade_effective_date: datetime | None = None


class SubscriptionHistoryItemResponse(BaseModel):
    """Immutable audit entry of a subscription transition or plan modification."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    society_id: UUID
    subscription_id: UUID
    previous_plan_id: UUID | None = None
    new_plan_id: UUID
    previous_status: str | None = None
    new_status: str
    previous_cycle: str | None = None
    new_cycle: str
    transition_reason: str
    changed_by: UUID | None = None
    effective_at: datetime


class TenantUsageMetricItemResponse(BaseModel):
    """Current usage and quota allocation for a single metric."""

    model_config = ConfigDict(from_attributes=True)

    metric_key: str
    current_value: int
    quota_limit: int | None = None
    is_unlimited: bool = False
    utilization_percentage: float | None = None
    last_calculated_at: datetime


class TenantCheckoutRequest(BaseModel):
    """Request payload to initiate checkout order session."""

    model_config = ConfigDict(extra="forbid")

    provider: str = Field(default="RAZORPAY", max_length=50)
    idempotency_key: str | None = Field(default=None, max_length=100)


class TenantPaymentVerifyRequest(BaseModel):
    """Request payload to verify gateway payment and execute settlement."""

    model_config = ConfigDict(extra="forbid")

    invoice_id: UUID
    gateway_order_id: str = Field(..., min_length=1, max_length=100)
    gateway_payment_id: str = Field(..., min_length=1, max_length=100)
    signature: str = Field(..., min_length=1, max_length=255)
    provider: str = Field(default="RAZORPAY", max_length=50)
