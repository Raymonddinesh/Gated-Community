"""Phase 21E.3 — Payment Gateway, Order, Webhook, and Reconciliation Schemas."""

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

# ==============================================================================
# 1. Provider Internal DTOs
# ==============================================================================


class GatewayOrderResponse(BaseModel):
    """Raw order created by an external payment gateway provider."""

    model_config = ConfigDict(frozen=True)

    order_id: str
    amount: Decimal
    currency: str
    receipt: str | None = None
    status: str = "created"
    raw_payload: dict[str, Any] = Field(default_factory=dict)


class GatewayPaymentDetails(BaseModel):
    """Authoritative payment state fetched directly from provider."""

    model_config = ConfigDict(frozen=True)

    payment_id: str
    order_id: str | None = None
    amount: Decimal
    currency: str
    status: str  # 'captured', 'failed', 'refunded', etc.
    method: str = "CARD"  # 'CARD', 'UPI', 'NETBANKING', 'OFFLINE'
    captured_at: datetime | None = None
    card_network: str | None = None
    card_last4: str | None = None
    upi_vpa: str | None = None
    gateway_fee: Decimal = Decimal("0.00")
    gateway_tax: Decimal = Decimal("0.00")
    raw_payload: dict[str, Any] = Field(default_factory=dict)


class GatewayRefundResponse(BaseModel):
    """Authoritative refund response returned from gateway."""

    model_config = ConfigDict(frozen=True)

    refund_id: str
    payment_id: str
    amount: Decimal
    currency: str
    status: str  # 'processed', 'pending', 'failed'
    raw_payload: dict[str, Any] = Field(default_factory=dict)


# ==============================================================================
# 2. Payment Order API Schemas
# ==============================================================================


class PaymentOrderCreateRequest(BaseModel):
    """Client request to initialize an authoritative server-side checkout order."""

    invoice_id: UUID
    idempotency_key: str | None = Field(
        None, max_length=100, description="Client idempotency key for safe replay"
    )


class PaymentOrderResponse(BaseModel):
    """Server-side payment order ready for client checkout SDK integration."""

    model_config = ConfigDict(from_attributes=True)

    attempt_id: UUID
    invoice_id: UUID
    gateway_provider: str
    order_id: str
    amount: Decimal
    currency_code: str
    key_id: str
    checkout_url: str | None = None
    expires_at: datetime | None = None


# ==============================================================================
# 3. Payment Verification API Schemas
# ==============================================================================


class PaymentVerificationRequest(BaseModel):
    """Payload submitted by client after completing checkout SDK flow."""

    invoice_id: UUID
    gateway_order_id: str
    gateway_payment_id: str
    signature: str


class PaymentVerificationResponse(BaseModel):
    """Server-verified payment settlement response."""

    model_config = ConfigDict(from_attributes=True)

    success: bool
    payment_id: UUID
    gateway_payment_id: str
    status: str
    amount: Decimal
    currency_code: str
    invoice_id: UUID
    invoice_status: str
    subscription_status: str | None = None
    settled_at: datetime | None = None


# ==============================================================================
# 4. Webhook Ingestion Schemas
# ==============================================================================


class WebhookIngestResponse(BaseModel):
    """Synchronous HTTP 200 response returned upon durable webhook ingestion."""

    status: str
    event_id: str
    processing_status: str
    message: str


# ==============================================================================
# 5. Refund API Schemas
# ==============================================================================


class RefundInitiationRequest(BaseModel):
    """Request to initiate a full or partial refund for a captured payment."""

    payment_id: UUID
    amount: Decimal | None = Field(
        None, gt=Decimal("0.00"), description="Partial refund amount; omit for full refund"
    )
    reason: str = Field(..., min_length=3, max_length=100)


class RefundResponse(BaseModel):
    """Refund transaction record."""

    model_config = ConfigDict(from_attributes=True)

    refund_id: UUID
    payment_id: UUID
    gateway_refund_id: str | None
    amount: Decimal
    currency_code: str
    status: str
    reason: str
    initiated_by: str
    created_at: datetime
    processed_at: datetime | None = None


# ==============================================================================
# 6. Financial Reconciliation Schemas
# ==============================================================================


class ReconciliationDiscrepancy(BaseModel):
    """Detailed financial discrepancy item identified during reconciliation."""

    payment_reference: str
    type: str  # 'MISSING_PROVIDER_CAPTURE', 'AMOUNT_MISMATCH', 'ORPHANED_PAYMENT', etc.
    details: dict[str, Any] = Field(default_factory=dict)


class ReconciliationReportResponse(BaseModel):
    """Summary and itemized report produced by payment reconciliation."""

    reconciled_count: int
    discrepancy_count: int
    orphaned_count: int
    discrepancies: list[ReconciliationDiscrepancy]
    started_at: datetime
    completed_at: datetime
