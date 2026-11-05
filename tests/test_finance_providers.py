"""Tests for Accounting Provider Abstractions, Tally Stub, and Import/Export Provider."""

from datetime import date
from decimal import Decimal
from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.finance.infrastructure.repositories import AccountingConfigRepository
from apps.api.src.finance.providers.base import JournalEntryDTO, JournalLineDTO
from apps.api.src.finance.providers.factory import get_accounting_provider
from apps.api.src.finance.providers.import_export import ImportExportProvider
from apps.api.src.finance.providers.native import NativeAccountingProvider
from apps.api.src.finance.providers.tally import TallyProvider

SOCIETY_A_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
SOCIETY_B_ID = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")


@pytest.mark.asyncio
async def test_native_provider_lifecycle(seeded_session: AsyncSession) -> None:
    """NativeAccountingProvider successfully executes create, post, balance, and export."""
    provider = NativeAccountingProvider(seeded_session)

    entry = JournalEntryDTO(
        journal_number=None,
        entry_date=date(2026, 6, 1),
        description="Native Provider Test Entry",
        lines=[
            JournalLineDTO(account_code="1010", debit_amount=Decimal("1200.0000")),
            JournalLineDTO(account_code="4000", credit_amount=Decimal("1200.0000")),
        ],
    )

    # 1. Create entry
    res = await provider.create_entry(SOCIETY_A_ID, entry)
    assert res.success is True
    assert res.record_id is not None
    journal_id = UUID(res.record_id)

    # 2. Post entry
    post_res = await provider.post_entry(SOCIETY_A_ID, journal_id)
    assert post_res.success is True

    # 3. Get balance
    bal = await provider.get_balance(SOCIETY_A_ID, "1010")
    assert bal > Decimal("0.0000")

    # 4. Export entries
    exported = await provider.export_entries(SOCIETY_A_ID)
    assert len(exported) >= 2
    assert any(e["description"] == "Native Provider Test Entry" for e in exported)

    # 5. Reverse entry
    rev_res = await provider.reverse_entry(SOCIETY_A_ID, journal_id, reason="Provider test reversal")
    assert rev_res.success is True


@pytest.mark.asyncio
async def test_tally_provider_not_configured_handling(seeded_session: AsyncSession) -> None:
    """Tally provider returns clear error responses when not configured."""
    provider = TallyProvider(seeded_session)

    entry = JournalEntryDTO(
        journal_number="JV-TALLY-01",
        entry_date=date(2026, 6, 1),
        description="Tally Sync Test",
        lines=[
            JournalLineDTO(account_code="1010", debit_amount=Decimal("500.0000")),
            JournalLineDTO(account_code="4000", credit_amount=Decimal("500.0000")),
        ],
    )

    # In Society A, mode is NATIVE, so Tally should fail with NOT_CONFIGURED
    res = await provider.create_entry(SOCIETY_A_ID, entry)
    assert res.success is False
    assert "TALLY_NOT_CONFIGURED" in res.errors

    # Sync status
    sync_status = await provider.get_sync_status(SOCIETY_A_ID)
    assert sync_status["configured"] is False

    # Health check is False
    healthy = await provider.health_check(SOCIETY_A_ID)
    assert healthy is False


@pytest.mark.asyncio
async def test_import_export_provider_csv_flow(seeded_session: AsyncSession) -> None:
    """ImportExportProvider correctly validates CSV content and performs dry-run checks."""
    provider = ImportExportProvider(seeded_session)

    csv_data = """journal_number,entry_date,description,reference_number,account_code,account_name,debit_amount,credit_amount,line_description
JV-IMP-01,2026-06-15,External Bank Interest,REF100,1010,Bank Account,450.0000,0.0000,Interest Credit
JV-IMP-01,2026-06-15,External Bank Interest,REF100,4000,Interest Income,0.0000,450.0000,Interest Income
"""

    parsed_entries = await provider.parse_csv_to_entries(csv_data)
    assert len(parsed_entries) == 1
    assert len(parsed_entries[0].lines) == 2

    # Dry run import
    dry_result = await provider.import_entries(SOCIETY_A_ID, parsed_entries, dry_run=True)
    assert dry_result.success is True
    assert dry_result.details.get("dry_run") is True

    # Actual import
    import_result = await provider.import_entries(SOCIETY_A_ID, parsed_entries, dry_run=False)
    assert import_result.success is True
    assert import_result.details.get("imported_count") == 1


@pytest.mark.asyncio
async def test_provider_factory_resolution(seeded_session: AsyncSession) -> None:
    """Provider factory resolves correct implementation based on society configuration."""
    # Society A is configured with NATIVE
    provider_a = await get_accounting_provider(seeded_session, SOCIETY_A_ID)
    assert isinstance(provider_a, NativeAccountingProvider)

    # Change Society B config to TALLY
    config_repo = AccountingConfigRepository(seeded_session)
    await config_repo.update_config(
        SOCIETY_B_ID,
        accounting_mode="TALLY",
        tally_company_name="Greenwood CHS",
        tally_guid="GUID-12345",
    )
    provider_b = await get_accounting_provider(seeded_session, SOCIETY_B_ID)
    assert isinstance(provider_b, TallyProvider)
