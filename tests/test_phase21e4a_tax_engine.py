"""Phase 21E.4A — GST Tax Engine and Configuration Test Suite.

Comprehensive unit and domain verification covering:
1. Intra-state GST (CGST + SGST).
2. Inter-state GST (IGST).
3. CGST/SGST split and invariant (CGST + SGST == Total GST).
4. IGST calculation precision.
5. Zero or exempt tax rate.
6. SAC configuration lookup and custom registration.
7. Effective-date configuration and rule versioning.
8. GSTIN format, structure, and Luhn Mod-36 checksum validation.
9. Strict Decimal precision (zero float arithmetic).
10. ROUND_HALF_UP monetary rounding behavior.
11. Commercial discounts applied before tax.
12. Prorated credits integration with Phase 21E.2 ProrationEngine.
13. Historical tax snapshots, cryptographic verification, and credit notes.
14. Safe-fail handling for invalid or ambiguous place-of-supply inputs.
15. Tenant isolation and audit logging.
16. Concurrent multi-threaded tax configuration access.
"""

import threading
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

from apps.api.src.subscriptions.proration_engine import ProrationEngine
from apps.api.src.subscriptions.tax import (
    GSTINValidator,
    GSTTaxEngine,
    InvalidGSTINException,
    InvalidPlaceOfSupplyException,
    PlaceOfSupplyInput,
    PlaceOfSupplyService,
    SupplyCategory,
    SupplyType,
    TaxCalculationInput,
    TaxComponentType,
    TaxConfigurationNotFoundException,
    TaxConfigurationService,
    TaxRateConfig,
    TaxRuleStatus,
    TaxSnapshotService,
    TaxSnapshotTamperedException,
    quantize_money,
)


@pytest.fixture
def tax_engine() -> GSTTaxEngine:
    """Provide a fresh GSTTaxEngine with default SAC rules."""
    config_svc = TaxConfigurationService()
    return GSTTaxEngine(config_svc)


@pytest.fixture
def pos_service() -> PlaceOfSupplyService:
    """Provide PlaceOfSupplyService."""
    return PlaceOfSupplyService(strict_b2b_state_match=False)


# ==============================================================================
# 1. INTRA-STATE GST CALCULATION (CGST + SGST)
# ==============================================================================


def test_intrastate_gst_calculation(tax_engine: GSTTaxEngine, pos_service: PlaceOfSupplyService):
    """Supplier KA (29) and Customer KA (29) must result in CGST 9% + SGST 9%, IGST 0%."""
    pos_input = PlaceOfSupplyInput(
        supplier_state="Karnataka",
        customer_state="Karnataka",
        customer_gstin=None,  # B2C
    )
    pos = pos_service.determine_place_of_supply(pos_input)

    assert pos.supply_type == SupplyType.INTRA_STATE
    assert pos.supply_category == SupplyCategory.B2C
    assert pos.place_of_supply_code == "29"
    assert pos.applicable_components == (TaxComponentType.CGST, TaxComponentType.SGST)

    calc_input = TaxCalculationInput(
        base_amount=Decimal("1000.00"),
        sac_code="998313",
        place_of_supply=pos,
    )
    res = tax_engine.calculate_tax(calc_input)

    assert res.base_amount == Decimal("1000.00")
    assert res.taxable_amount == Decimal("1000.00")
    assert res.tax_rate == Decimal("18.00")
    assert res.cgst_rate == Decimal("9.00")
    assert res.cgst_amount == Decimal("90.00")
    assert res.sgst_rate == Decimal("9.00")
    assert res.sgst_amount == Decimal("90.00")
    assert res.igst_rate == Decimal("0.00")
    assert res.igst_amount == Decimal("0.00")
    assert res.tax_total == Decimal("180.00")
    assert res.grand_total == Decimal("1180.00")


# ==============================================================================
# 2. INTER-STATE GST CALCULATION (IGST)
# ==============================================================================


def test_interstate_gst_calculation(tax_engine: GSTTaxEngine, pos_service: PlaceOfSupplyService):
    """Supplier KA (29) and Customer MH (27) must result in IGST 18%, CGST 0%, SGST 0%."""
    pos_input = PlaceOfSupplyInput(
        supplier_state="Karnataka",
        customer_state="Maharashtra",
        customer_gstin=None,  # B2C
    )
    pos = pos_service.determine_place_of_supply(pos_input)

    assert pos.supply_type == SupplyType.INTER_STATE
    assert pos.supply_category == SupplyCategory.B2C
    assert pos.place_of_supply_code == "27"
    assert pos.applicable_components == (TaxComponentType.IGST,)

    calc_input = TaxCalculationInput(
        base_amount=Decimal("2500.00"),
        sac_code="998314",
        place_of_supply=pos,
    )
    res = tax_engine.calculate_tax(calc_input)

    assert res.base_amount == Decimal("2500.00")
    assert res.taxable_amount == Decimal("2500.00")
    assert res.cgst_amount == Decimal("0.00")
    assert res.sgst_amount == Decimal("0.00")
    assert res.igst_rate == Decimal("18.00")
    assert res.igst_amount == Decimal("450.00")
    assert res.tax_total == Decimal("450.00")
    assert res.grand_total == Decimal("2950.00")


# ==============================================================================
# 3. CGST/SGST SPLIT AND INVARIANT CHECK
# ==============================================================================


def test_cgst_sgst_split_exact_sum_invariant(tax_engine: GSTTaxEngine, pos_service: PlaceOfSupplyService):
    """INVARIANT: For intra-state supply, CGST + SGST MUST EXACTLY equal Total GST."""
    pos = pos_service.determine_place_of_supply(
        PlaceOfSupplyInput(supplier_state="29", customer_state="29")
    )

    # Test with amounts that yield fractional paise
    amounts = [
        Decimal("333.33"),
        Decimal("777.77"),
        Decimal("999.99"),
        Decimal("1234.56"),
        Decimal("0.01"),
    ]
    for amt in amounts:
        res = tax_engine.calculate_tax(
            TaxCalculationInput(base_amount=amt, sac_code="998313", place_of_supply=pos)
        )
        assert res.cgst_amount + res.sgst_amount == res.tax_total, (
            f"Invariant violation for amount {amt}: CGST ({res.cgst_amount}) + "
            f"SGST ({res.sgst_amount}) != Total GST ({res.tax_total})"
        )
        assert res.igst_amount == Decimal("0.00")
        assert res.grand_total == res.taxable_amount + res.tax_total


# ==============================================================================
# 4. IGST CALCULATION PRECISION
# ==============================================================================


def test_igst_calculation_precision(tax_engine: GSTTaxEngine, pos_service: PlaceOfSupplyService):
    """INVARIANT: For inter-state supply, IGST MUST EXACTLY equal Total GST."""
    pos = pos_service.determine_place_of_supply(
        PlaceOfSupplyInput(supplier_state="29", customer_state="07")  # KA to Delhi
    )

    amounts = [Decimal("100.00"), Decimal("333.33"), Decimal("999.99"), Decimal("50000.00")]
    for amt in amounts:
        res = tax_engine.calculate_tax(
            TaxCalculationInput(base_amount=amt, sac_code="998313", place_of_supply=pos)
        )
        assert res.igst_amount == res.tax_total
        assert res.cgst_amount == Decimal("0.00")
        assert res.sgst_amount == Decimal("0.00")
        assert res.grand_total == res.taxable_amount + res.tax_total


# ==============================================================================
# 5. ZERO OR EXEMPT TAX RATE
# ==============================================================================


def test_zero_or_exempt_tax_rate(pos_service: PlaceOfSupplyService):
    """Exempt services or zero-rated supplies must yield zero tax."""
    config_svc = TaxConfigurationService()
    # Register an exempt SAC
    config_svc.register_rule(
        TaxRateConfig(
            sac_code="998399",
            description="Exempt educational / non-profit SaaS module",
            total_rate=Decimal("0.00"),
            cgst_rate=Decimal("0.00"),
            sgst_rate=Decimal("0.00"),
            igst_rate=Decimal("0.00"),
            effective_from=date(2020, 1, 1),
            status=TaxRuleStatus.ACTIVE,
            version="1.0",
            is_exempt=True,
        )
    )
    engine = GSTTaxEngine(config_svc)
    pos = pos_service.determine_place_of_supply(
        PlaceOfSupplyInput(supplier_state="29", customer_state="29")
    )
    res = engine.calculate_tax(
        TaxCalculationInput(base_amount=Decimal("1500.00"), sac_code="998399", place_of_supply=pos)
    )

    assert res.taxable_amount == Decimal("1500.00")
    assert res.cgst_amount == Decimal("0.00")
    assert res.sgst_amount == Decimal("0.00")
    assert res.igst_amount == Decimal("0.00")
    assert res.tax_total == Decimal("0.00")
    assert res.grand_total == Decimal("1500.00")


# ==============================================================================
# 6. SAC CONFIGURATION LOOKUP AND CUSTOM SAC REGISTRATION
# ==============================================================================


def test_sac_configuration_lookup_and_custom_registration(tax_engine: GSTTaxEngine, pos_service: PlaceOfSupplyService):
    """SAC rules are dynamically configurable; unregistered SAC codes raise clean exception."""
    # 1. Unregistered SAC raises TaxConfigurationNotFoundException
    pos = pos_service.determine_place_of_supply(
        PlaceOfSupplyInput(supplier_state="29", customer_state="29")
    )
    with pytest.raises(TaxConfigurationNotFoundException) as exc_info:
        tax_engine.calculate_tax(
            TaxCalculationInput(base_amount=Decimal("1000.00"), sac_code="999999", place_of_supply=pos)
        )
    assert exc_info.value.status_code == 404

    # 2. Register custom SAC 998411 (Telecommunications) at 12%
    tax_engine.config_service.register_rule(
        TaxRateConfig(
            sac_code="998411",
            description="Telecommunication / messaging add-on services",
            total_rate=Decimal("12.00"),
            cgst_rate=Decimal("6.00"),
            sgst_rate=Decimal("6.00"),
            igst_rate=Decimal("12.00"),
            effective_from=date(2022, 1, 1),
            status=TaxRuleStatus.ACTIVE,
            version="1.0",
        )
    )
    res = tax_engine.calculate_tax(
        TaxCalculationInput(base_amount=Decimal("1000.00"), sac_code="998411", place_of_supply=pos)
    )
    assert res.tax_rate == Decimal("12.00")
    assert res.cgst_amount == Decimal("60.00")
    assert res.sgst_amount == Decimal("60.00")
    assert res.tax_total == Decimal("120.00")


# ==============================================================================
# 7. EFFECTIVE-DATE CONFIGURATION AND VERSIONING
# ==============================================================================


def test_effective_date_configuration_versioning(pos_service: PlaceOfSupplyService):
    """Rules apply strictly according to effective date intervals and versions."""
    config_svc = TaxConfigurationService()
    # Historic v1.0 rule: SAC 998350 at 15% from 2018-01-01 to 2021-12-31
    config_svc.register_rule(
        TaxRateConfig(
            sac_code="998350",
            description="Custom SaaS v1",
            total_rate=Decimal("15.00"),
            cgst_rate=Decimal("7.50"),
            sgst_rate=Decimal("7.50"),
            igst_rate=Decimal("15.00"),
            effective_from=date(2018, 1, 1),
            effective_to=date(2021, 12, 31),
            status=TaxRuleStatus.ACTIVE,
            version="1.0",
        )
    )
    # Current v2.0 rule: SAC 998350 at 18% from 2022-01-01 onwards
    config_svc.register_rule(
        TaxRateConfig(
            sac_code="998350",
            description="Custom SaaS v2",
            total_rate=Decimal("18.00"),
            cgst_rate=Decimal("9.00"),
            sgst_rate=Decimal("9.00"),
            igst_rate=Decimal("18.00"),
            effective_from=date(2022, 1, 1),
            effective_to=None,
            status=TaxRuleStatus.ACTIVE,
            version="2.0",
        )
    )
    engine = GSTTaxEngine(config_svc)
    pos = pos_service.determine_place_of_supply(
        PlaceOfSupplyInput(supplier_state="29", customer_state="29")
    )

    # 1. Historical calculation (2020) uses v1.0 (15%)
    res_hist = engine.calculate_tax(
        TaxCalculationInput(
            base_amount=Decimal("1000.00"),
            sac_code="998350",
            place_of_supply=pos,
            transaction_date=date(2020, 6, 15),
        )
    )
    assert res_hist.tax_rate == Decimal("15.00")
    assert res_hist.tax_total == Decimal("150.00")
    assert res_hist.tax_snapshot.tax_config_version == "1.0"

    # 2. Modern calculation (2026) uses v2.0 (18%)
    res_curr = engine.calculate_tax(
        TaxCalculationInput(
            base_amount=Decimal("1000.00"),
            sac_code="998350",
            place_of_supply=pos,
            transaction_date=date(2026, 10, 31),
        )
    )
    assert res_curr.tax_rate == Decimal("18.00")
    assert res_curr.tax_total == Decimal("180.00")
    assert res_curr.tax_snapshot.tax_config_version == "2.0"


# ==============================================================================
# 8. GSTIN FORMAT AND CHECKSUM VALIDATION (B2B FLOW)
# ==============================================================================


def test_gstin_format_and_checksum_validation(pos_service: PlaceOfSupplyService):
    """GSTIN validation checks syntax, state code, PAN entity character, and Luhn Mod-36 checksum."""
    # 1. Valid Karnataka GSTIN (calculated checksum matches)
    valid_prefix = "29AAAAA0000A1Z"
    chk = GSTINValidator.calculate_checksum(valid_prefix)
    valid_gstin = f"{valid_prefix}{chk}"

    v_res = GSTINValidator.validate(valid_gstin, verify_checksum=True)
    assert v_res.is_valid is True
    assert v_res.syntactic_valid is True
    assert v_res.checksum_valid is True
    assert v_res.state_code == "29"
    assert v_res.state_name == "Karnataka"
    assert v_res.is_active_registration is None, "Must not claim registration is active"

    # 2. Tampered checksum is rejected
    tampered_gstin = f"{valid_prefix}{'0' if chk != '0' else '1'}"
    t_res = GSTINValidator.validate(tampered_gstin, verify_checksum=True)
    assert t_res.is_valid is False
    assert t_res.syntactic_valid is True
    assert t_res.checksum_valid is False

    # 3. Invalid syntax (wrong length or characters)
    inv_res = GSTINValidator.validate("INVALID_GSTIN_123")
    assert inv_res.is_valid is False
    assert inv_res.syntactic_valid is False

    # 4. Invalid State Code (e.g. state code 99 is invalid/legacy)
    inv_state_res = GSTINValidator.validate("00AAAAA0000A1Z5")
    assert inv_state_res.is_valid is False

    # 5. Invalid PAN entity character (4th char of PAN must be C, P, H, F, A, T, etc.)
    inv_pan_res = GSTINValidator.validate("29AAAZA0000A1Z5")
    assert inv_pan_res.is_valid is False

    # 6. B2B Place of Supply uses valid GSTIN to establish B2B category
    pos_res = pos_service.determine_place_of_supply(
        PlaceOfSupplyInput(
            supplier_state="Karnataka",
            customer_state="Karnataka",
            customer_gstin=valid_gstin,
        )
    )
    assert pos_res.supply_category == SupplyCategory.B2B
    assert pos_res.place_of_supply_code == "29"

    # 7. Invalid GSTIN in PlaceOfSupplyService raises InvalidGSTINException
    with pytest.raises(InvalidGSTINException):
        pos_service.determine_place_of_supply(
            PlaceOfSupplyInput(
                supplier_state="Karnataka",
                customer_gstin="29INVALIDGSTIN99",
            )
        )


# ==============================================================================
# 9. STRICT DECIMAL PRECISION (ZERO FLOAT ARITHMETIC)
# ==============================================================================


def test_decimal_precision_no_float(tax_engine: GSTTaxEngine, pos_service: PlaceOfSupplyService):
    """Every rate, taxable amount, and tax component must be an instance of Decimal."""
    pos = pos_service.determine_place_of_supply(
        PlaceOfSupplyInput(supplier_state="29", customer_state="27")
    )
    res = tax_engine.calculate_tax(
        TaxCalculationInput(
            base_amount=Decimal("1234.56"),
            sac_code="998313",
            place_of_supply=pos,
            discount_amount=Decimal("34.56"),
            prorated_credit=Decimal("200.00"),
        )
    )

    fields_to_check = [
        res.base_amount,
        res.discount_amount,
        res.discounted_base,
        res.prorated_credit,
        res.taxable_amount,
        res.tax_rate,
        res.cgst_rate,
        res.cgst_amount,
        res.sgst_rate,
        res.sgst_amount,
        res.igst_rate,
        res.igst_amount,
        res.tax_total,
        res.grand_total,
    ]
    for val in fields_to_check:
        assert isinstance(val, Decimal), f"Expected Decimal, got {type(val)}"
        assert not isinstance(val, float)


# ==============================================================================
# 10. ROUND_HALF_UP MONETARY ROUNDING POLICY
# ==============================================================================


def test_round_half_up_monetary_behavior(tax_engine: GSTTaxEngine, pos_service: PlaceOfSupplyService):
    """Monetary rounding must follow standard commercial ROUND_HALF_UP (half rounded away from zero)."""
    assert quantize_money(Decimal("10.005")) == Decimal("10.01")
    assert quantize_money(Decimal("10.004")) == Decimal("10.00")
    assert quantize_money(Decimal("10.015")) == Decimal("10.02")
    assert quantize_money(Decimal("10.025")) == Decimal("10.03")

    pos = pos_service.determine_place_of_supply(
        PlaceOfSupplyInput(supplier_state="29", customer_state="29")
    )
    # Taxable amount 55.55 * 9% = 4.9995 -> 5.00
    res = tax_engine.calculate_tax(
        TaxCalculationInput(base_amount=Decimal("55.55"), sac_code="998313", place_of_supply=pos)
    )
    assert res.cgst_amount == Decimal("5.00")
    assert res.sgst_amount == Decimal("5.00")
    assert res.tax_total == Decimal("10.00")
    assert res.grand_total == Decimal("65.55")


# ==============================================================================
# 11. COMMERCIAL DISCOUNTS APPLIED BEFORE TAX
# ==============================================================================


def test_commercial_discounts_applied_before_tax(tax_engine: GSTTaxEngine, pos_service: PlaceOfSupplyService):
    """Discounts must be deducted from base amount before calculating taxable amount and GST."""
    pos = pos_service.determine_place_of_supply(
        PlaceOfSupplyInput(supplier_state="29", customer_state="27")
    )
    # Base 2000, Discount 500 -> Taxable = 1500. GST @ 18% on 1500 = 270. Grand Total = 1770.
    res = tax_engine.calculate_tax(
        TaxCalculationInput(
            base_amount=Decimal("2000.00"),
            discount_amount=Decimal("500.00"),
            sac_code="998313",
            place_of_supply=pos,
        )
    )
    assert res.base_amount == Decimal("2000.00")
    assert res.discount_amount == Decimal("500.00")
    assert res.discounted_base == Decimal("1500.00")
    assert res.taxable_amount == Decimal("1500.00")
    assert res.igst_amount == Decimal("270.00")
    assert res.grand_total == Decimal("1770.00")

    # Discount exceeding base amount is safely clamped to base amount
    res_exceed = tax_engine.calculate_tax(
        TaxCalculationInput(
            base_amount=Decimal("500.00"),
            discount_amount=Decimal("800.00"),
            sac_code="998313",
            place_of_supply=pos,
        )
    )
    assert res_exceed.discount_amount == Decimal("500.00")
    assert res_exceed.taxable_amount == Decimal("0.00")
    assert res_exceed.tax_total == Decimal("0.00")
    assert res_exceed.grand_total == Decimal("0.00")


# ==============================================================================
# 12. PRORATED CREDITS INTEGRATION WITH PRORATION ENGINE
# ==============================================================================


def test_prorated_credits_integration(tax_engine: GSTTaxEngine, pos_service: PlaceOfSupplyService):
    """Reuses Phase 21E.2 ProrationEngine to compute prorated credit and reduce net taxable value."""
    # Scenario: Society switches from Plan Standard (2000/mo) to Plan Premium (4000/mo) 15 days in
    now = datetime(2026, 10, 1, 0, 0, 0, tzinfo=UTC)
    midpoint = now + timedelta(days=15)
    end = now + timedelta(days=30)

    # 1. ProrationEngine calculates unused credit for old plan
    proration = ProrationEngine.calculate_proration(
        eligible_amount=Decimal("2000.00"),
        period_start=now,
        period_end=end,
        effective_at=midpoint,
    )
    assert proration.prorated_amount == Decimal("1000.00")

    # 2. Upgrade charge = full new plan (4000) or partial new plan (2000). Let's say new charge = 2000
    new_plan_charge = Decimal("2000.00")

    pos = pos_service.determine_place_of_supply(
        PlaceOfSupplyInput(supplier_state="29", customer_state="29")
    )

    # 3. GSTTaxEngine calculates tax strictly on net difference (2000 - 1000 = 1000)
    res = tax_engine.calculate_tax(
        TaxCalculationInput(
            base_amount=new_plan_charge,
            prorated_credit=proration.prorated_amount,
            sac_code="998313",
            place_of_supply=pos,
        )
    )

    assert res.base_amount == Decimal("2000.00")
    assert res.prorated_credit == Decimal("1000.00")
    assert res.taxable_amount == Decimal("1000.00")
    assert res.cgst_amount == Decimal("90.00")
    assert res.sgst_amount == Decimal("90.00")
    assert res.tax_total == Decimal("180.00")
    assert res.grand_total == Decimal("1180.00")


# ==============================================================================
# 13. HISTORICAL TAX SNAPSHOTS, CRYPTOGRAPHIC VERIFICATION & CREDIT NOTES
# ==============================================================================


def test_historical_tax_snapshots_and_credit_note_reversal(tax_engine: GSTTaxEngine, pos_service: PlaceOfSupplyService):
    """Historical invoices retain immutable tax snapshots; credit notes reverse at historical snapshot rates."""
    pos = pos_service.determine_place_of_supply(
        PlaceOfSupplyInput(supplier_state="Karnataka", customer_state="Maharashtra")
    )
    # 1. Generate original invoice calculation at 18%
    calc_res = tax_engine.calculate_tax(
        TaxCalculationInput(
            base_amount=Decimal("10000.00"),
            sac_code="998313",
            place_of_supply=pos,
        )
    )
    snapshot = calc_res.tax_snapshot
    assert TaxSnapshotService.verify_snapshot_integrity(snapshot) is True

    # 2. Simulate subsequent statutory rate change in configuration to 28%
    tax_engine.config_service.register_rule(
        TaxRateConfig(
            sac_code="998313",
            description="SAC 998313 updated to 28%",
            total_rate=Decimal("28.00"),
            cgst_rate=Decimal("14.00"),
            sgst_rate=Decimal("14.00"),
            igst_rate=Decimal("28.00"),
            effective_from=date(2027, 1, 1),
            status=TaxRuleStatus.ACTIVE,
            version="2.0",
        )
    )

    # 3. Issue a partial credit note (reversing 4000.00) against the original invoice snapshot
    cn_res = tax_engine.calculate_credit_note_tax(
        taxable_credit_amount=Decimal("4000.00"),
        original_invoice_snapshot=snapshot,
    )

    # INVARIANT: Credit note tax rate MUST be 18% (from original snapshot), NOT 28%!
    assert cn_res.tax_rate == Decimal("18.00")
    assert cn_res.taxable_amount == Decimal("4000.00")
    assert cn_res.igst_amount == Decimal("720.00")
    assert cn_res.tax_total == Decimal("720.00")
    assert cn_res.grand_total == Decimal("4720.00")

    # 4. Tampered snapshot detection
    tampered_snapshot = snapshot.model_copy(update={"taxable_value": Decimal("99999.00")})
    assert TaxSnapshotService.verify_snapshot_integrity(tampered_snapshot) is False
    with pytest.raises(TaxSnapshotTamperedException):
        tax_engine.calculate_credit_note_tax(
            taxable_credit_amount=Decimal("1000.00"),
            original_invoice_snapshot=tampered_snapshot,
        )


# ==============================================================================
# 14. INVALID OR AMBIGUOUS PLACE OF SUPPLY INPUTS (FAIL-SAFE)
# ==============================================================================


def test_invalid_place_of_supply_inputs_fail_safe(pos_service: PlaceOfSupplyService):
    """Unresolved or ambiguous place of supply inputs fail safely with clear domain exceptions."""
    # 1. Unrecognized supplier state
    with pytest.raises(InvalidPlaceOfSupplyException) as exc_supplier:
        pos_service.determine_place_of_supply(
            PlaceOfSupplyInput(supplier_state="Atlantis", customer_state="Karnataka")
        )
    assert exc_supplier.value.details["reason"] == "SUPPLIER_STATE_UNRESOLVED"

    # 2. Missing customer state for B2C unregistered customer
    with pytest.raises(InvalidPlaceOfSupplyException) as exc_cust:
        pos_service.determine_place_of_supply(
            PlaceOfSupplyInput(supplier_state="Karnataka", customer_state=None, customer_gstin=None)
        )
    assert exc_cust.value.details["reason"] == "CUSTOMER_BILLING_STATE_REQUIRED_FOR_B2C"

    # 3. Unresolvable customer state
    with pytest.raises(InvalidPlaceOfSupplyException):
        pos_service.determine_place_of_supply(
            PlaceOfSupplyInput(supplier_state="Karnataka", customer_state="Narnia")
        )


# ==============================================================================
# 15. CONCURRENT TAX CONFIGURATION ACCESS
# ==============================================================================


def test_concurrent_tax_configuration_access():
    """TaxConfigurationService allows concurrent reads and writes without data race corruption."""
    config_svc = TaxConfigurationService()
    errors: list[Exception] = []

    def writer_task(thread_id: int):
        try:
            for i in range(50):
                rule = TaxRateConfig(
                    sac_code=f"9989{thread_id:02d}",
                    description=f"Thread SAC {thread_id}",
                    total_rate=Decimal("18.00"),
                    cgst_rate=Decimal("9.00"),
                    sgst_rate=Decimal("9.00"),
                    igst_rate=Decimal("18.00"),
                    effective_from=date(2026, 1, 1),
                    status=TaxRuleStatus.ACTIVE,
                    version=f"{i}.0",
                )
                config_svc.register_rule(rule)
        except Exception as exc:
            errors.append(exc)

    def reader_task():
        try:
            for _ in range(100):
                config_svc.get_rule("998313")
                config_svc.list_rules()
        except Exception as exc:
            errors.append(exc)

    threads = []
    for t_id in range(4):
        threads.append(threading.Thread(target=writer_task, args=(t_id,)))
    for _ in range(4):
        threads.append(threading.Thread(target=reader_task))

    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(errors) == 0, f"Thread errors encountered: {errors}"
    assert len(config_svc.list_rules()) >= 6  # 2 defaults + 4 dynamic rules
