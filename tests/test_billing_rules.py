"""Tests for Maintenance Charge Rules and Deterministic Formula Calculations."""

from datetime import date
from decimal import Decimal
from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.billing.application.rule_service import ChargeRuleService
from apps.api.src.billing.domain.exceptions import InvalidChargeRuleException
from apps.api.src.core.exceptions import ConflictException
from apps.api.src.finance.infrastructure.repositories import AccountRepository

SOCIETY_A_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")


@pytest.mark.asyncio
async def test_fixed_charge_rule_creation_and_listing(seeded_session: AsyncSession) -> None:
    """Fixed charge rule can be created and queried by effective date."""
    rule_service = ChargeRuleService(seeded_session)
    account_repo = AccountRepository(seeded_session)

    income_acc = await account_repo.get_by_code(SOCIETY_A_ID, "4000")
    assert income_acc is not None

    rule = await rule_service.create_rule(
        society_id=SOCIETY_A_ID,
        name="Security Surcharge",
        code="RULE_SEC_01",
        calculation_type="FIXED_PER_UNIT",
        rate_or_amount=Decimal("500.0000"),
        income_account_id=income_acc.id,
        effective_from=date(2026, 4, 1),
    )
    assert rule.id is not None
    assert rule.rate_or_amount == Decimal("500.0000")

    # List rules active on 2026-04-15
    rules = await rule_service.list_rules(SOCIETY_A_ID, on_date=date(2026, 4, 15))
    codes = [r.code for r in rules]
    assert "RULE_SEC_01" in codes
    assert "MAINT_FIXED" in codes


@pytest.mark.asyncio
async def test_per_sqft_and_unit_type_rule_configuration(seeded_session: AsyncSession) -> None:
    """Per sqft and unit type rule structures are validated and saved."""
    rule_service = ChargeRuleService(seeded_session)
    account_repo = AccountRepository(seeded_session)

    income_acc = await account_repo.get_by_code(SOCIETY_A_ID, "4000")
    assert income_acc is not None

    # 1. Per sqft rule
    sqft_rule = await rule_service.create_rule(
        society_id=SOCIETY_A_ID,
        name="Area Maintenance",
        code="RULE_SQFT_01",
        calculation_type="PER_SQFT",
        rate_or_amount=Decimal("3.5000"),
        income_account_id=income_acc.id,
        effective_from=date(2026, 4, 1),
    )
    assert sqft_rule.rate_or_amount == Decimal("3.5000")

    # 2. Unit type rule with custom rates
    unit_type_rule = await rule_service.create_rule(
        society_id=SOCIETY_A_ID,
        name="Tiered Maintenance",
        code="RULE_TYPE_01",
        calculation_type="UNIT_TYPE",
        rate_or_amount=Decimal("2000.0000"),
        unit_type_rates={"2BHK": "2500.0000", "3BHK": "3500.0000"},
        income_account_id=income_acc.id,
        effective_from=date(2026, 4, 1),
    )
    assert unit_type_rule.unit_type_rates == {"2BHK": "2500.0000", "3BHK": "3500.0000"}


@pytest.mark.asyncio
async def test_duplicate_rule_code_rejected(seeded_session: AsyncSession) -> None:
    """Creating a rule with a duplicate code in the same society must raise ConflictException."""
    rule_service = ChargeRuleService(seeded_session)
    account_repo = AccountRepository(seeded_session)
    income_acc = await account_repo.get_by_code(SOCIETY_A_ID, "4000")
    assert income_acc is not None

    with pytest.raises(ConflictException):
        await rule_service.create_rule(
            society_id=SOCIETY_A_ID,
            name="Duplicate Code",
            code="MAINT_FIXED",  # Already seeded
            calculation_type="FIXED_PER_UNIT",
            rate_or_amount=Decimal("1000.0000"),
            income_account_id=income_acc.id,
            effective_from=date(2026, 4, 1),
        )


@pytest.mark.asyncio
async def test_invalid_calculation_type_and_dates_rejected(seeded_session: AsyncSession) -> None:
    """Invalid calculation type or inverted date range must be rejected."""
    rule_service = ChargeRuleService(seeded_session)
    account_repo = AccountRepository(seeded_session)
    income_acc = await account_repo.get_by_code(SOCIETY_A_ID, "4000")
    assert income_acc is not None

    with pytest.raises(InvalidChargeRuleException):
        await rule_service.create_rule(
            society_id=SOCIETY_A_ID,
            name="Invalid Calc",
            code="INVALID_01",
            calculation_type="NON_EXISTENT_TYPE",
            rate_or_amount=Decimal("100.0000"),
            income_account_id=income_acc.id,
            effective_from=date(2026, 4, 1),
        )

    with pytest.raises(InvalidChargeRuleException):
        await rule_service.create_rule(
            society_id=SOCIETY_A_ID,
            name="Inverted Dates",
            code="INVERTED_01",
            calculation_type="FIXED_PER_UNIT",
            rate_or_amount=Decimal("100.0000"),
            income_account_id=income_acc.id,
            effective_from=date(2026, 4, 10),
            effective_to=date(2026, 4, 1),  # Earlier!
        )
