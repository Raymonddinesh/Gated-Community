"""Phase 21E.4C — SaaS Credit Note Request/Response DTO Schemas.

Pydantic v2 data models for credit note lifecycle:
- Draft creation, update, and preview.
- Line item breakdowns referencing original invoice items.
- Strict Decimal monetary enforcement with 2 decimal precision.
- Cryptographic tax snapshot verification response.
"""

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class PlatformCreditNoteItemCreate(BaseModel):
    """Payload to add or specify a credit note line item."""

    model_config = ConfigDict(frozen=True)

    invoice_item_id: UUID | None = Field(
        default=None,
        description="ID of original invoice item being credited, or None for general credit",
    )
    description: str = Field(..., min_length=1, max_length=255)
    sac_code: str = Field(default="998313", max_length=20)
    quantity: Decimal = Field(default=Decimal("1.0000"), gt=Decimal("0.0000"))
    unit_price: Decimal = Field(..., gt=Decimal("0.00"))
    taxable_amount: Decimal | None = Field(default=None, gt=Decimal("0.00"))
    tax_rate: Decimal = Field(default=Decimal("18.00"), ge=Decimal("0.00"))

    @model_validator(mode="before")
    @classmethod
    def populate_taxable_amount(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if data.get("taxable_amount") is None and data.get("unit_price") is not None:
                qty = Decimal(str(data.get("quantity", "1.0000")))
                price = Decimal(str(data["unit_price"]))
                data = dict(data)
                data["taxable_amount"] = qty * price
        return data


class PlatformCreditNoteCreateDraft(BaseModel):
    """Payload to initialize a new draft credit note."""

    model_config = ConfigDict(frozen=True)

    invoice_id: UUID = Field(..., description="Target finalized PlatformInvoice ID")
    reason: str = Field(..., min_length=2, max_length=100)
    notes: str | None = Field(default=None, max_length=2000)
    taxable_amount: Decimal | None = Field(
        default=None,
        gt=Decimal("0.00"),
        description="Optional lump-sum taxable credit amount if not specifying individual items",
    )
    items: list[PlatformCreditNoteItemCreate] = Field(
        default_factory=list,
        description="Optional itemized line breakdowns for partial line crediting",
    )


class PlatformCreditNoteUpdateDraft(BaseModel):
    """Payload to modify an unissued draft credit note."""

    model_config = ConfigDict(frozen=True)

    reason: str | None = Field(default=None, min_length=2, max_length=100)
    notes: str | None = Field(default=None, max_length=2000)
    taxable_amount: Decimal | None = Field(default=None, gt=Decimal("0.00"))
    items: list[PlatformCreditNoteItemCreate] | None = None


class PlatformCreditNotePreviewRequest(BaseModel):
    """Payload to simulate credit note calculations and invoice balance impact without saving."""

    model_config = ConfigDict(frozen=True)

    invoice_id: UUID
    taxable_credit_amount: Decimal | None = Field(default=None, gt=Decimal("0.00"))
    taxable_amount: Decimal | None = Field(default=None, gt=Decimal("0.00"))
    items: list[PlatformCreditNoteItemCreate] | None = None

    @property
    def effective_taxable_amount(self) -> Decimal | None:
        return self.taxable_credit_amount if self.taxable_credit_amount is not None else self.taxable_amount


class PlatformCreditNoteVoidRequest(BaseModel):
    """Payload to void an issued credit note."""

    model_config = ConfigDict(frozen=True)

    void_reason: str = Field(..., min_length=5, max_length=500)


class PlatformCreditNoteItemResponse(BaseModel):
    """Serialized representation of a credit note line item."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    credit_note_id: UUID
    invoice_item_id: UUID | None
    item_index: int
    description: str
    sac_code: str
    quantity: Decimal
    unit_price: Decimal
    taxable_amount: Decimal
    tax_rate: Decimal
    tax_amount: Decimal
    total_amount: Decimal
    created_at: datetime


class PlatformCreditNoteResponse(BaseModel):
    """Complete serialized representation of a PlatformCreditNote."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    society_id: UUID
    invoice_id: UUID
    credit_note_number: str | None
    fiscal_year: str
    taxable_amount: Decimal
    cgst_amount: Decimal
    sgst_amount: Decimal
    igst_amount: Decimal
    tax_total: Decimal
    grand_total: Decimal
    currency_code: str
    reason: str
    notes: str | None
    status: str
    issued_at: datetime | None
    created_by: UUID | None
    created_at: datetime
    updated_at: datetime
    items: list[PlatformCreditNoteItemResponse] = Field(default_factory=list)


class CreditNotePreviewResponse(BaseModel):
    """Detailed simulation of credit note amounts, tax reversal, and balance adjustments."""

    model_config = ConfigDict(frozen=True)

    invoice_id: UUID
    taxable_amount: Decimal
    cgst_amount: Decimal
    sgst_amount: Decimal
    igst_amount: Decimal
    tax_total: Decimal
    grand_total: Decimal
    currency_code: str
    original_invoice_total: Decimal
    invoice_settled_payments: Decimal
    prior_issued_credits: Decimal
    eligible_invoice_balance: Decimal
    new_invoice_outstanding: Decimal
    unapplied_credit_balance: Decimal
    tax_config_version: str


class CreditNoteTaxSnapshotVerificationResponse(BaseModel):
    """Cryptographic verification audit result for a credit note's tax snapshot."""

    model_config = ConfigDict(frozen=True)

    verified: bool
    tampered: bool
    snapshot_id: UUID
    credit_note_id: UUID
    original_invoice_id: UUID
    calculated_at: datetime
    tax_config_version: str
    stored_hash: str
    computed_hash: str
