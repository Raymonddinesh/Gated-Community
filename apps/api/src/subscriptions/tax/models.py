"""Phase 21E.4A — Indian GST Domain Models, Schemas, and Snapshots.

Provides immutable data structures, schemas, and enums for:
- GST Tax Rate Configurations (SAC, CGST, SGST, IGST, effective dates, versions).
- Place of Supply inputs and resolution results.
- Tax Calculation Inputs and Detailed Itemized Results.
- Cryptographically verifiable, immutable Tax Snapshots.
"""

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator


class TaxComponentType(StrEnum):
    """Applicable Indian GST tax components."""

    CGST = "CGST"
    SGST = "SGST"
    IGST = "IGST"


class SupplyType(StrEnum):
    """Classification of supply under the IGST Act."""

    INTRA_STATE = "INTRA_STATE"  # Supplier State == Place of Supply (CGST + SGST)
    INTER_STATE = "INTER_STATE"  # Supplier State != Place of Supply (IGST)


class SupplyCategory(StrEnum):
    """Recipient commercial status for GST tax determination."""

    B2B = "B2B"  # Registered customer with valid GSTIN
    B2C = "B2C"  # Unregistered society/customer without GSTIN


class TaxRuleStatus(StrEnum):
    """Lifecycle status for a tax rate rule."""

    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    SUPERSEDED = "SUPERSEDED"


class TaxRateConfig(BaseModel):
    """Configurable tax rate rule for a specific SAC code with versioning and date validity."""

    model_config = ConfigDict(frozen=True)

    sac_code: str = Field(..., min_length=4, max_length=20, description="Service Accounting Code")
    description: str = Field(..., max_length=255, description="Official service description")
    total_rate: Decimal = Field(..., ge=Decimal("0.00"), le=Decimal("100.00"), description="Total applicable GST rate %")
    cgst_rate: Decimal = Field(default=Decimal("0.00"), ge=Decimal("0.00"), le=Decimal("50.00"))
    sgst_rate: Decimal = Field(default=Decimal("0.00"), ge=Decimal("0.00"), le=Decimal("50.00"))
    igst_rate: Decimal = Field(default=Decimal("0.00"), ge=Decimal("0.00"), le=Decimal("100.00"))
    effective_from: date = Field(..., description="Date from which this tax rule applies (inclusive)")
    effective_to: date | None = Field(default=None, description="Date until which this tax rule applies (inclusive), or None if currently active")
    status: TaxRuleStatus = Field(default=TaxRuleStatus.ACTIVE)
    version: str = Field(default="1.0", max_length=20)
    is_reverse_charge: bool = Field(default=False)
    is_exempt: bool = Field(default=False)

    @field_validator("igst_rate")
    @classmethod
    def validate_rate_symmetry(cls, v: Decimal, info) -> Decimal:
        data = info.data
        total = data.get("total_rate")
        cgst = data.get("cgst_rate")
        sgst = data.get("sgst_rate")
        if total is not None:
            if v != total:
                raise ValueError(f"IGST rate ({v}%) must equal total tax rate ({total}%).")
            if cgst is not None and sgst is not None:
                if (cgst + sgst) != total:
                    raise ValueError(f"CGST ({cgst}%) + SGST ({sgst}%) must equal total tax rate ({total}%).")
        return v


class PlaceOfSupplyInput(BaseModel):
    """Input payload to resolve legal place of supply and applicable tax components."""

    model_config = ConfigDict(frozen=True)

    supplier_state: str = Field(..., min_length=2, max_length=100, description="State of supplier (e.g. 'Karnataka' or '29')")
    customer_state: str | None = Field(default=None, max_length=100, description="Customer billing address state")
    customer_gstin: str | None = Field(default=None, max_length=50, description="Customer GSTIN if registered (B2B)")
    transaction_date: date | None = Field(default=None, description="Transaction date for place of supply policy evaluation")
    supply_classification: str = Field(default="SAAS_SUBSCRIPTION", max_length=50)


class PlaceOfSupplyResult(BaseModel):
    """Authoritative result of resolving place of supply under Section 12/13 of IGST Act."""

    model_config = ConfigDict(frozen=True)

    place_of_supply_state: str = Field(..., description="Canonical state name of place of supply")
    place_of_supply_code: str = Field(..., min_length=2, max_length=2, description="2-digit GST state code of place of supply")
    supplier_state: str
    supplier_state_code: str
    customer_state: str | None = None
    customer_state_code: str | None = None
    customer_gstin: str | None = None
    supply_type: SupplyType
    supply_category: SupplyCategory
    applicable_components: tuple[TaxComponentType, ...]
    policy_applied: str = Field(..., description="Statutory policy basis, e.g. IGST_ACT_SECTION_12_2_A_B2B")
    reason: str


class TaxCalculationInput(BaseModel):
    """Input parameters for itemized GST tax computation."""

    model_config = ConfigDict(frozen=True)

    base_amount: Decimal = Field(..., ge=Decimal("0.00"), description="Gross base charge before discounts and proration")
    sac_code: str = Field(default="998313", description="Service Accounting Code to look up tax rule")
    place_of_supply: PlaceOfSupplyResult
    discount_amount: Decimal = Field(default=Decimal("0.00"), ge=Decimal("0.00"), description="Direct commercial discount")
    prorated_credit: Decimal = Field(default=Decimal("0.00"), ge=Decimal("0.00"), description="Prorated unused subscription credit")
    transaction_date: date | None = None
    currency_code: str = Field(default="INR", min_length=3, max_length=3)
    invoice_id: UUID | None = Field(default=None, description="Optional invoice ID associated with calculation")


class TaxSnapshot(BaseModel):
    """Cryptographically verifiable, immutable snapshot of tax calculation for historical invoices."""

    model_config = ConfigDict(frozen=True)

    snapshot_id: UUID = Field(default_factory=uuid4)
    invoice_id: UUID | None = None
    sac_code: str
    tax_rate: Decimal
    taxable_value: Decimal
    commercial_discount: Decimal = Decimal("0.00")
    prorated_credit: Decimal = Decimal("0.00")
    cgst_rate: Decimal
    cgst_amount: Decimal
    sgst_rate: Decimal
    sgst_amount: Decimal
    igst_rate: Decimal
    igst_amount: Decimal
    total_tax: Decimal
    grand_total: Decimal
    supplier_state: str
    supplier_state_code: str
    customer_state: str
    customer_state_code: str
    customer_gstin: str | None = None
    place_of_supply: str
    place_of_supply_code: str
    supply_type: SupplyType
    supply_category: SupplyCategory
    tax_config_version: str
    calculation_timestamp: datetime
    currency_code: str = "INR"
    integrity_hash: str = Field(..., description="SHA-256 HMAC digest of canonical snapshot fields")


class TaxCalculationResult(BaseModel):
    """Complete itemized result of GST calculation with snapshot and financial totals."""

    model_config = ConfigDict(frozen=True)

    base_amount: Decimal
    discount_amount: Decimal
    discounted_base: Decimal
    prorated_credit: Decimal
    taxable_amount: Decimal
    sac_code: str
    tax_rate: Decimal
    supply_type: SupplyType
    cgst_rate: Decimal
    cgst_amount: Decimal
    sgst_rate: Decimal
    sgst_amount: Decimal
    igst_rate: Decimal
    igst_amount: Decimal
    tax_total: Decimal
    grand_total: Decimal
    currency_code: str = "INR"
    calculation_timestamp: datetime
    tax_snapshot: TaxSnapshot
