"""Phase 21E.4B — SaaS Invoice Schemas and DTOs."""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class PlatformInvoiceItemCreate(BaseModel):
    """Line item creation payload for a platform invoice."""

    model_config = ConfigDict(frozen=True)

    item_type: str = Field(default="BASE_PLAN", description="BASE_PLAN, PRORATION_CREDIT, PRORATION_CHARGE, DISCOUNT, OVERAGE, ADJUSTMENT")
    description: str = Field(..., min_length=2, max_length=255)
    sac_code: str = Field(default="998313", min_length=4, max_length=20)
    quantity: Decimal = Field(default=Decimal("1.0000"), gt=Decimal("0.0000"))
    unit_price: Decimal = Field(..., ge=Decimal("0.00"))
    discount_amount: Decimal = Field(default=Decimal("0.00"), ge=Decimal("0.00"))


class PlatformInvoiceCreateDraft(BaseModel):
    """Draft invoice creation request payload."""

    model_config = ConfigDict(frozen=True)

    society_id: UUID
    subscription_id: UUID
    billing_cycle: str = Field(default="MONTHLY", description="MONTHLY or ANNUAL")
    period_start: datetime
    period_end: datetime
    due_date: date
    customer_gstin: str | None = Field(default=None, max_length=15)
    place_of_supply: str | None = Field(default=None, max_length=100)
    prorated_credit: Decimal = Field(default=Decimal("0.00"), ge=Decimal("0.00"))
    idempotency_key: str | None = Field(default=None, max_length=150)
    items: list[PlatformInvoiceItemCreate] = Field(..., min_length=1)


class PlatformInvoiceUpdateDraft(BaseModel):
    """Draft invoice update payload (only permitted when status == 'DRAFT')."""

    model_config = ConfigDict(frozen=True)

    due_date: date | None = None
    customer_gstin: str | None = Field(default=None, max_length=15)
    place_of_supply: str | None = Field(default=None, max_length=100)
    prorated_credit: Decimal | None = Field(default=None, ge=Decimal("0.00"))
    items: list[PlatformInvoiceItemCreate] | None = None


class PlatformInvoiceItemResponse(BaseModel):
    """Itemized breakdown of a platform invoice."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    invoice_id: UUID
    item_index: int
    item_type: str
    description: str
    sac_code: str
    quantity: Decimal
    unit_price: Decimal
    discount_amount: Decimal
    taxable_amount: Decimal
    tax_rate: Decimal
    tax_amount: Decimal
    total_amount: Decimal


class PlatformInvoiceResponse(BaseModel):
    """Complete platform invoice representation."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    society_id: UUID
    subscription_id: UUID
    invoice_number: str | None = None
    fiscal_year: str | None = None
    billing_cycle: str
    period_start: datetime
    period_end: datetime
    subtotal: Decimal
    discount_total: Decimal
    prorated_credit: Decimal
    taxable_amount: Decimal
    cgst_amount: Decimal
    sgst_amount: Decimal
    igst_amount: Decimal
    tax_total: Decimal
    grand_total: Decimal
    credits_applied: Decimal
    amount_paid: Decimal
    amount_due: Decimal
    currency_code: str
    status: str
    due_date: date
    issued_at: datetime | None = None
    paid_at: datetime | None = None
    voided_at: datetime | None = None
    void_reason: str | None = None
    sac_code: str
    place_of_supply: str
    customer_gstin: str | None = None
    idempotency_key: str | None = None
    items: list[PlatformInvoiceItemResponse] = Field(default_factory=list)


class PlatformInvoiceVoidRequest(BaseModel):
    """Void invoice request payload."""

    model_config = ConfigDict(frozen=True)

    reason: str = Field(..., min_length=3, max_length=255, description="Auditable justification for voiding the issued invoice")


class TaxSnapshotVerificationResponse(BaseModel):
    """Cryptographic verification response for an invoice tax snapshot."""

    model_config = ConfigDict(frozen=True)

    invoice_id: UUID
    snapshot_id: UUID
    is_valid: bool
    snapshot_hash: str
    recalculated_hash: str
    sac_code: str
    tax_rate: Decimal
    taxable_value: Decimal
    tax_total: Decimal
    grand_total: Decimal
    calculation_timestamp: datetime
    error_message: str | None = None
