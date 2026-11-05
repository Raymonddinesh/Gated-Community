"""Phase 21E.4A — Indian GST Tax Calculation Engine.

Statutory GST calculation engine adhering strictly to Indian Goods and Services Tax laws:
- Calculation order:
    1. Base Gross Amount (B).
    2. Subtract Direct Commercial Discounts (D).
    3. Subtract Prorated Unused Subscription Credits (C).
    4. Compute Net Taxable Amount: T = max(0.00, (B - D) - C).
    5. Component Calculation based on Place of Supply:
       - Intra-State: CGST = round_half_up(T × (cgst_rate/100))
                      SGST = round_half_up(T × (sgst_rate/100))
                      Total GST = CGST + SGST (exact sum).
       - Inter-State: IGST = round_half_up(T × (igst_rate/100))
                      Total GST = IGST.
    6. Final Payable Amount = T + Total GST.
    7. Generate immutable, cryptographically verifiable TaxSnapshot.
- Strict Decimal arithmetic; zero float arithmetic.
- Monetary rounding using Decimal ROUND_HALF_UP to 2 decimal places (0.01).
- Invariant: CGST/SGST and IGST are mutually exclusive (never applied simultaneously).
"""

from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Final

from apps.api.src.subscriptions.tax.exceptions import (
    IncompatibleCreditNoteTaxException,
    TaxCalculationException,
)
from apps.api.src.subscriptions.tax.models import (
    PlaceOfSupplyResult,
    SupplyType,
    TaxCalculationInput,
    TaxCalculationResult,
    TaxComponentType,
    TaxRateConfig,
    TaxRuleStatus,
    TaxSnapshot,
)
from apps.api.src.subscriptions.tax.snapshot import TaxSnapshotService
from apps.api.src.subscriptions.tax.tax_config import (
    TaxConfigurationService,
    tax_config_service,
)

CURRENCY_PRECISION: Final[Decimal] = Decimal("0.01")
PERCENT_DIVISOR: Final[Decimal] = Decimal("100.00")


def _utc_now() -> datetime:
    return datetime.now(UTC)


def quantize_money(amount: Decimal) -> Decimal:
    """Quantize an arbitrary Decimal amount to 2 decimal places using ROUND_HALF_UP."""
    return amount.quantize(CURRENCY_PRECISION, rounding=ROUND_HALF_UP)


class GSTTaxEngine:
    """Statutory Indian GST calculation engine for SaaS subscriptions."""

    def __init__(self, config_service: TaxConfigurationService | None = None) -> None:
        self.config_service = config_service or tax_config_service

    def calculate_tax(
        self,
        calc_input: TaxCalculationInput,
    ) -> TaxCalculationResult:
        """Execute deterministic GST calculation for a commercial supply.

        Calculation Sequence:
            1. Base Gross Amount: B = quantize(calc_input.base_amount).
            2. Commercial Discount: D = min(B, quantize(calc_input.discount_amount)).
            3. Discounted Base: B_d = B - D.
            4. Prorated Credit: C = min(B_d, quantize(calc_input.prorated_credit)).
            5. Net Taxable Amount: T = max(0.00, B_d - C).
            6. Tax Rule Lookup for SAC on transaction date.
            7. Place of Supply component calculation:
               - Intra-State: CGST + SGST = Total GST.
               - Inter-State: IGST = Total GST.
            8. Final Payable Amount: Grand Total = T + Total GST.
            9. Immutable Tax Snapshot creation.
        """
        now = _utc_now()
        target_date = calc_input.transaction_date or now.date()

        # Step 1: Base Gross Amount
        if calc_input.base_amount < Decimal("0.00"):
            raise TaxCalculationException("base_amount cannot be negative.")
        base_amt = quantize_money(calc_input.base_amount)

        # Step 2: Commercial Discount
        if calc_input.discount_amount < Decimal("0.00"):
            raise TaxCalculationException("discount_amount cannot be negative.")
        discount_amt = min(base_amt, quantize_money(calc_input.discount_amount))

        # Step 3: Discounted Base
        discounted_base = base_amt - discount_amt

        # Step 4: Prorated Credits / Adjustments
        if calc_input.prorated_credit < Decimal("0.00"):
            raise TaxCalculationException("prorated_credit cannot be negative.")
        prorated_credit = min(discounted_base, quantize_money(calc_input.prorated_credit))

        # Step 5: Net Taxable Amount
        taxable_amt = quantize_money(max(Decimal("0.00"), discounted_base - prorated_credit))

        # Step 6: Lookup applicable tax rule
        tax_rule = self.config_service.get_rule(
            sac_code=calc_input.sac_code,
            effective_date=target_date,
        )

        pos: PlaceOfSupplyResult = calc_input.place_of_supply

        # Step 7: Component Calculation
        if tax_rule.is_exempt or tax_rule.total_rate == Decimal("0.00") or taxable_amt == Decimal("0.00"):
            cgst_rate = Decimal("0.00")
            sgst_rate = Decimal("0.00")
            igst_rate = Decimal("0.00")
            cgst_amt = Decimal("0.00")
            sgst_amt = Decimal("0.00")
            igst_amt = Decimal("0.00")
            tax_total = Decimal("0.00")

        elif pos.supply_type == SupplyType.INTRA_STATE:
            # Intra-State: CGST + SGST apply; IGST must be strictly zero
            cgst_rate = tax_rule.cgst_rate
            sgst_rate = tax_rule.sgst_rate
            igst_rate = Decimal("0.00")

            cgst_amt = quantize_money(taxable_amt * (cgst_rate / PERCENT_DIVISOR))
            sgst_amt = quantize_money(taxable_amt * (sgst_rate / PERCENT_DIVISOR))
            igst_amt = Decimal("0.00")

            # Mandated invariant: For intra-state, CGST + SGST = Total GST
            tax_total = quantize_money(cgst_amt + sgst_amt)

        elif pos.supply_type == SupplyType.INTER_STATE:
            # Inter-State: IGST applies; CGST and SGST must be strictly zero
            cgst_rate = Decimal("0.00")
            sgst_rate = Decimal("0.00")
            igst_rate = tax_rule.igst_rate

            cgst_amt = Decimal("0.00")
            sgst_amt = Decimal("0.00")
            igst_amt = quantize_money(taxable_amt * (igst_rate / PERCENT_DIVISOR))

            # Mandated invariant: For inter-state, IGST = Total GST
            tax_total = igst_amt

        else:
            raise TaxCalculationException(f"Unsupported supply type: {pos.supply_type}")

        # Step 8: Final Payable Amount
        grand_total = quantize_money(taxable_amt + tax_total)

        # Step 9: Create Immutable Tax Snapshot
        snapshot = TaxSnapshotService.create_snapshot(
            sac_code=tax_rule.sac_code,
            tax_rule=tax_rule,
            pos_result=pos,
            taxable_value=taxable_amt,
            cgst_amount=cgst_amt,
            sgst_amount=sgst_amt,
            igst_amount=igst_amt,
            total_tax=tax_total,
            grand_total=grand_total,
            calculation_timestamp=now,
            currency_code=calc_input.currency_code,
            invoice_id=calc_input.invoice_id,
            commercial_discount=discount_amt,
            prorated_credit=prorated_credit,
        )

        return TaxCalculationResult(
            base_amount=base_amt,
            discount_amount=discount_amt,
            discounted_base=discounted_base,
            prorated_credit=prorated_credit,
            taxable_amount=taxable_amt,
            sac_code=tax_rule.sac_code,
            tax_rate=tax_rule.total_rate,
            supply_type=pos.supply_type,
            cgst_rate=cgst_rate,
            cgst_amount=cgst_amt,
            sgst_rate=sgst_rate,
            sgst_amount=sgst_amt,
            igst_rate=igst_rate,
            igst_amount=igst_amt,
            tax_total=tax_total,
            grand_total=grand_total,
            currency_code=calc_input.currency_code,
            calculation_timestamp=now,
            tax_snapshot=snapshot,
        )

    def calculate_credit_note_tax(
        self,
        taxable_credit_amount: Decimal,
        original_invoice_snapshot: TaxSnapshot,
    ) -> TaxCalculationResult:
        """Calculate GST tax reversal for a statutory Credit Note referencing an original invoice.

        Guarantees:
            - Verifies the cryptographic integrity of original_invoice_snapshot.
            - Reverses taxes proportionally using the exact historical rates and supply type
              from the snapshot, unaffected by any subsequent tax rate updates.
            - Validates that credit amount does not exceed the original invoice's taxable value.
        """
        now = _utc_now()
        TaxSnapshotService.assert_valid_snapshot(original_invoice_snapshot)

        taxable_credit = quantize_money(taxable_credit_amount)
        if taxable_credit <= Decimal("0.00"):
            raise IncompatibleCreditNoteTaxException(
                invoice_id=original_invoice_snapshot.snapshot_id,
                reason="Credit note taxable amount must be strictly greater than zero.",
            )

        if taxable_credit > original_invoice_snapshot.taxable_value:
            raise IncompatibleCreditNoteTaxException(
                invoice_id=original_invoice_snapshot.snapshot_id,
                reason=(
                    f"Credit note taxable amount ({taxable_credit}) cannot exceed original invoice "
                    f"taxable value ({original_invoice_snapshot.taxable_value})."
                ),
            )

        # Use rates directly from the immutable historical snapshot
        if original_invoice_snapshot.supply_type == SupplyType.INTRA_STATE:
            cgst_rate = original_invoice_snapshot.cgst_rate
            sgst_rate = original_invoice_snapshot.sgst_rate
            igst_rate = Decimal("0.00")

            cgst_amt = quantize_money(taxable_credit * (cgst_rate / PERCENT_DIVISOR))
            sgst_amt = quantize_money(taxable_credit * (sgst_rate / PERCENT_DIVISOR))
            igst_amt = Decimal("0.00")
            tax_total = quantize_money(cgst_amt + sgst_amt)

        else:
            cgst_rate = Decimal("0.00")
            sgst_rate = Decimal("0.00")
            igst_rate = original_invoice_snapshot.igst_rate

            cgst_amt = Decimal("0.00")
            sgst_amt = Decimal("0.00")
            igst_amt = quantize_money(taxable_credit * (igst_rate / PERCENT_DIVISOR))
            tax_total = igst_amt

        grand_total = quantize_money(taxable_credit + tax_total)

        # Build historical tax rule directly from original invoice snapshot (Resolving Finding M-2)
        total_rate = original_invoice_snapshot.tax_rate
        if original_invoice_snapshot.supply_type == SupplyType.INTRA_STATE:
            hist_cgst = original_invoice_snapshot.cgst_rate
            hist_sgst = original_invoice_snapshot.sgst_rate
            hist_igst = total_rate
        else:
            hist_igst = total_rate
            hist_cgst = quantize_money(total_rate / Decimal("2.00"))
            hist_sgst = total_rate - hist_cgst

        historical_rule = TaxRateConfig(
            sac_code=original_invoice_snapshot.sac_code,
            description=f"Historical tax rule locked for invoice {original_invoice_snapshot.snapshot_id}",
            total_rate=total_rate,
            cgst_rate=hist_cgst,
            sgst_rate=hist_sgst,
            igst_rate=hist_igst,
            effective_from=original_invoice_snapshot.calculation_timestamp.date(),
            effective_to=None,
            status=TaxRuleStatus.ACTIVE,
            version=original_invoice_snapshot.tax_config_version,
            is_reverse_charge=False,
            is_exempt=(total_rate == Decimal("0.00")),
        )

        # Synthesize a snapshot for the credit note referencing the original
        cn_snapshot = TaxSnapshotService.create_snapshot(
            sac_code=original_invoice_snapshot.sac_code,
            tax_rule=historical_rule,
            pos_result=PlaceOfSupplyResult(
                place_of_supply_state=original_invoice_snapshot.place_of_supply,
                place_of_supply_code=original_invoice_snapshot.place_of_supply_code,
                supplier_state=original_invoice_snapshot.supplier_state,
                supplier_state_code=original_invoice_snapshot.supplier_state_code,
                customer_state=original_invoice_snapshot.customer_state,
                customer_state_code=original_invoice_snapshot.customer_state_code,
                customer_gstin=original_invoice_snapshot.customer_gstin,
                supply_type=original_invoice_snapshot.supply_type,
                supply_category=original_invoice_snapshot.supply_category,
                applicable_components=(
                    (TaxComponentType.CGST, TaxComponentType.SGST)
                    if original_invoice_snapshot.supply_type == SupplyType.INTRA_STATE
                    else (TaxComponentType.IGST,)
                ),
                policy_applied="CREDIT_NOTE_HISTORICAL_SNAPSHOT_REFERENCE",
                reason=f"Credit note issued against original invoice snapshot {original_invoice_snapshot.snapshot_id}",
            ),
            taxable_value=taxable_credit,
            cgst_amount=cgst_amt,
            sgst_amount=sgst_amt,
            igst_amount=igst_amt,
            total_tax=tax_total,
            grand_total=grand_total,
            calculation_timestamp=now,
            currency_code=original_invoice_snapshot.currency_code,
        )

        return TaxCalculationResult(
            base_amount=taxable_credit,
            discount_amount=Decimal("0.00"),
            discounted_base=taxable_credit,
            prorated_credit=Decimal("0.00"),
            taxable_amount=taxable_credit,
            sac_code=original_invoice_snapshot.sac_code,
            tax_rate=original_invoice_snapshot.tax_rate,
            supply_type=original_invoice_snapshot.supply_type,
            cgst_rate=cgst_rate,
            cgst_amount=cgst_amt,
            sgst_rate=sgst_rate,
            sgst_amount=sgst_amt,
            igst_rate=igst_rate,
            igst_amount=igst_amt,
            tax_total=tax_total,
            grand_total=grand_total,
            currency_code=original_invoice_snapshot.currency_code,
            calculation_timestamp=now,
            tax_snapshot=cn_snapshot,
        )
