"""Phase 19 Emergency & Incident Management Domain Finalization Test Suite."""

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.database.models.billing import Invoice, Payment
from apps.api.src.database.models.finance import JournalEntry
from apps.api.src.incidents.concurrency import acquire_incident_number_lock, acquire_incident_triage_lock
from apps.api.src.incidents.enums import ActionPriority, ActionStatus, IncidentSeverity
from apps.api.src.incidents.exceptions import IncidentNotFoundError, InvalidIncidentStateError
from apps.api.src.incidents.incident_service import IncidentService
from apps.api.src.incidents.privacy import IncidentPrivacyFilter
from apps.api.src.incidents.schemas import (
    IncidentActionCreate,
    IncidentActionUpdate,
    IncidentCategoryCreate,
    IncidentCreate,
    IncidentTriageRequest,
)

UUID_SOCIETY_A = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
UUID_SOCIETY_B = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
UUID_USER_REPORTER_A = uuid.UUID("22222222-2222-2222-2222-22222222222a")
UUID_USER_REPORTER_B = uuid.UUID("55555555-5555-5555-5555-55555555555b")
UUID_USER_ADMIN = uuid.UUID("11111111-1111-1111-1111-11111111111a")


@pytest.mark.asyncio
async def test_cross_tenant_incident_isolation(seeded_session: AsyncSession):
    """Verify that Society A cannot access or mutate Society B's emergency incident records."""
    service = IncidentService(seeded_session)

    society_a = UUID_SOCIETY_A
    society_b = UUID_SOCIETY_B

    # Create category & incident in Society A
    cat_a = await service.create_category(
        society_a,
        IncidentCategoryCreate(name="Fire Safety A", code="FIRE_A"),
    )
    inc_a = await service.report_incident(
        society_a,
        UUID_USER_REPORTER_A,
        "RESIDENT",
        IncidentCreate(
            title="Smoke in Basement A",
            description="Minor smoke detected in trash chute",
            category_id=cat_a.id,
        ),
    )

    # Society B listing incidents should return empty list
    incidents_b = await service.list_incidents(society_b)
    assert len(incidents_b) == 0

    # Society B requesting Society A's incident by ID must raise IncidentNotFoundError
    with pytest.raises(IncidentNotFoundError):
        await service.get_incident(society_b, inc_a.id)

    # Society B attempting to triage Society A's incident must raise IncidentNotFoundError
    with pytest.raises(IncidentNotFoundError):
        await service.triage_incident(
            society_b,
            inc_a.id,
            UUID_USER_REPORTER_B,
            "ADMIN",
            IncidentTriageRequest(severity=IncidentSeverity.HIGH),
        )


@pytest.mark.asyncio
async def test_financial_ledger_isolation(seeded_session: AsyncSession):
    """Verify that emergency incident operations perform 0 mutations or interactions with financial ledgers."""
    service = IncidentService(seeded_session)
    society_id = UUID_SOCIETY_A

    # Record baseline counts
    res_journal = await seeded_session.execute(select(JournalEntry))
    baseline_journals = len(res_journal.scalars().all())

    res_invoice = await seeded_session.execute(select(Invoice))
    baseline_invoices = len(res_invoice.scalars().all())

    res_payment = await seeded_session.execute(select(Payment))
    baseline_payments = len(res_payment.scalars().all())

    # Perform Incident Operations
    cat = await service.create_category(
        society_id,
        IncidentCategoryCreate(name="Water Leakage", code="WATER_LEAK"),
    )

    inc = await service.report_incident(
        society_id,
        UUID_USER_REPORTER_A,
        "RESIDENT",
        IncidentCreate(
            title="Basement Water Line Burst",
            description="Flooding near B2 parking",
            category_id=cat.id,
        ),
    )

    await service.triage_incident(
        society_id,
        inc.id,
        UUID_USER_ADMIN,
        "ADMIN",
        IncidentTriageRequest(severity=IncidentSeverity.HIGH),
    )

    await service.contain_hazard(society_id, inc.id, UUID_USER_ADMIN, "ADMIN")

    await service.resolve_incident(society_id, inc.id, UUID_USER_ADMIN, "ADMIN", reason="Pipe repaired")

    # Re-check financial counts
    res_journal_after = await seeded_session.execute(select(JournalEntry))
    assert len(res_journal_after.scalars().all()) == baseline_journals

    res_invoice_after = await seeded_session.execute(select(Invoice))
    assert len(res_invoice_after.scalars().all()) == baseline_invoices

    res_payment_after = await seeded_session.execute(select(Payment))
    assert len(res_payment_after.scalars().all()) == baseline_payments


@pytest.mark.asyncio
async def test_state_machine_invalid_transition(seeded_session: AsyncSession):
    """Verify state machine blocks invalid direct transitions (e.g., REPORTED directly to RESOLVED without triage/acknowledgement)."""
    service = IncidentService(seeded_session)
    society_id = UUID_SOCIETY_A

    cat = await service.create_category(
        society_id,
        IncidentCategoryCreate(name="Gas Smell", code="GAS_SMELL"),
    )

    inc = await service.report_incident(
        society_id,
        UUID_USER_REPORTER_A,
        "RESIDENT",
        IncidentCreate(
            title="Gas odor in Block D",
            description="Piped gas odor reported by resident",
            category_id=cat.id,
        ),
    )

    # Attempting to directly resolve an un-triaged, un-acknowledged incident without containment or override must fail
    with pytest.raises(InvalidIncidentStateError):
        await service.resolve_incident(
            society_id,
            inc.id,
            UUID_USER_ADMIN,
            "ADMIN",
            reason="Illegal jump to RESOLVED",
        )


@pytest.mark.asyncio
async def test_privacy_filtering(seeded_session: AsyncSession):
    """Verify IncidentPrivacyFilter masks reporter contact info for general users."""
    incident_dict = {
        "id": str(uuid.uuid4()),
        "reported_by_id": str(UUID_USER_REPORTER_A),
        "reporter_contact": "+91 99999 88888",
        "title": "Medical Incident",
    }

    # Admin user gets unmasked contact
    admin_filtered = IncidentPrivacyFilter.apply_privacy_filter(
        incident_dict,
        user_id_str=str(UUID_USER_ADMIN),
        user_permissions={"incident.view_all"},
    )
    assert admin_filtered["reporter_contact"] == "+91 99999 88888"

    # General resident gets masked contact
    resident_filtered = IncidentPrivacyFilter.apply_privacy_filter(
        incident_dict,
        user_id_str=str(UUID_USER_REPORTER_B),
        user_permissions={"incident.view_own"},
    )
    assert resident_filtered["reporter_contact"] == "[CONFIDENTIAL]"


@pytest.mark.asyncio
async def test_concurrency_locks(seeded_session: AsyncSession):
    """Verify advisory lock helpers execute safely."""
    await acquire_incident_number_lock(seeded_session, UUID_SOCIETY_A)
    await acquire_incident_triage_lock(seeded_session, uuid.uuid4())


@pytest.mark.asyncio
async def test_incident_actions_lifecycle(seeded_session: AsyncSession):
    """Verify creation and update of incident action items."""
    service = IncidentService(seeded_session)
    society_id = UUID_SOCIETY_A

    cat = await service.create_category(
        society_id, IncidentCategoryCreate(name="Elevator Malfunction", code="ELEVATOR")
    )
    inc = await service.report_incident(
        society_id,
        UUID_USER_REPORTER_A,
        "RESIDENT",
        IncidentCreate(title="Elevator #3 stuck", description="Stuck on Floor 2", category_id=cat.id),
    )

    action = await service.create_action(
        society_id,
        inc.id,
        UUID_USER_ADMIN,
        IncidentActionCreate(
            title="Dispatch Technician",
            description="Call OTIS elevator engineer",
            priority=ActionPriority.HIGH,
        ),
    )
    assert action.id is not None
    assert action.status == ActionStatus.PENDING.value

    updated_action = await service.update_action(
        society_id,
        action.id,
        UUID_USER_ADMIN,
        IncidentActionUpdate(status=ActionStatus.COMPLETED),
    )
    assert updated_action.status == ActionStatus.COMPLETED.value
    assert updated_action.completed_at is not None
