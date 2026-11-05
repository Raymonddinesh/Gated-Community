"""Phase 19 Emergency & Incident Management Core Test Suite."""

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.incidents.enums import (
    EmergencyContactType,
    IncidentSeverity,
    IncidentStatus,
    ReporterType,
    ResponderType,
)
from apps.api.src.incidents.exceptions import (
    VoiceDurationExceededError,
)
from apps.api.src.incidents.incident_service import IncidentService
from apps.api.src.incidents.schemas import (
    EmergencyContactCreate,
    IncidentAcknowledgementCreate,
    IncidentAssignmentCreate,
    IncidentCategoryCreate,
    IncidentCreate,
    IncidentOverrideRequest,
    IncidentTriageRequest,
)

UUID_SOCIETY_A = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
UUID_SOCIETY_B = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
UUID_USER_REPORTER = uuid.UUID("22222222-2222-2222-2222-22222222222a")
UUID_USER_RESPONDER = uuid.UUID("33333333-3333-3333-3333-33333333333a")
UUID_USER_ADMIN = uuid.UUID("11111111-1111-1111-1111-11111111111a")


@pytest.mark.asyncio
async def test_report_and_triage_incident_lifecycle(seeded_session: AsyncSession):
    """Test full incident reporting, triage, acknowledgement, containment, resolution, and closure."""
    service = IncidentService(seeded_session)
    society_id = UUID_SOCIETY_A

    # 1. Create Category
    category = await service.create_category(
        society_id,
        IncidentCategoryCreate(
            name="Electrical Hazard",
            code="ELEC_HAZ",
            description="Electrical power failure, short circuit, or spark hazard",
            default_severity=IncidentSeverity.MEDIUM,
            default_sla_minutes=30,
        ),
    )

    # 2. Report Incident
    incident = await service.report_incident(
        society_id,
        UUID_USER_REPORTER,
        "RESIDENT",
        IncidentCreate(
            title="Transformer Fire Spark in Basement B",
            description="Active electrical sparks and smoke detected near Block B sub-station",
            category_id=category.id,
            reporter_type=ReporterType.RESIDENT,
            reporter_contact="+91 98765 43210",
        ),
    )

    assert incident.id is not None
    assert incident.incident_number.startswith("INC-")
    # Title contains 'fire' keyword so severity auto-escalated to CRITICAL
    assert incident.severity == IncidentSeverity.CRITICAL.value
    assert incident.status == IncidentStatus.REPORTED.value

    # 3. Triage Incident
    triaged = await service.triage_incident(
        society_id,
        incident.id,
        UUID_USER_ADMIN,
        "ADMIN",
        IncidentTriageRequest(
            severity=IncidentSeverity.CRITICAL,
            requires_governance_review=True,
            requires_work_order=True,
            triage_notes="Triaged as critical fire hazard. Dispatched emergency response unit.",
        ),
    )
    assert triaged.status == IncidentStatus.TRIAGED.value
    assert triaged.requires_governance_review is True
    assert triaged.requires_work_order is True

    # 4. Acknowledge Incident
    ack = await service.acknowledge_incident(
        society_id,
        incident.id,
        UUID_USER_RESPONDER,
        IncidentAcknowledgementCreate(
            responder_role="SECURITY_HEAD",
            notes="Security team on-site with fire extinguishers.",
        ),
    )
    assert ack.id is not None

    # Fetch updated incident
    updated_inc = await service.get_incident(society_id, incident.id)
    assert updated_inc.status == IncidentStatus.ACKNOWLEDGED.value

    # 5. Assign Responder
    assignment = await service.assign_responder(
        society_id,
        incident.id,
        UUID_USER_ADMIN,
        "ADMIN",
        IncidentAssignmentCreate(
            responder_type=ResponderType.SECURITY,
            assigned_user_id=UUID_USER_RESPONDER,
            assigned_role="SECURITY_CAPTAIN",
            assignment_notes="Lead containment on ground level",
            is_primary=True,
        ),
    )
    assert assignment.id is not None

    # 6. Contain Hazard
    contained_inc = await service.contain_hazard(
        society_id,
        incident.id,
        UUID_USER_RESPONDER,
        "SECURITY_CAPTAIN",
    )
    assert contained_inc.status == IncidentStatus.CONTAINED.value
    assert contained_inc.is_hazard_contained is True
    assert contained_inc.hazard_contained_at is not None

    # 7. Resolve Incident
    resolved_inc = await service.resolve_incident(
        society_id,
        incident.id,
        UUID_USER_RESPONDER,
        "SECURITY_CAPTAIN",
        reason="Electrical main isolate valve triggered. Power supply stabilized.",
    )
    assert resolved_inc.status == IncidentStatus.RESOLVED.value
    assert resolved_inc.resolved_at is not None

    # 8. Close Incident
    closed_inc = await service.close_incident(
        society_id,
        incident.id,
        UUID_USER_ADMIN,
        "ADMIN",
        reason="Post-incident audit completed. Final closure approved.",
    )
    assert closed_inc.status == IncidentStatus.CLOSED.value
    assert closed_inc.closed_at is not None


@pytest.mark.asyncio
async def test_voice_note_duration_limit(seeded_session: AsyncSession):
    """Verify that voice note duration > 60s raises VoiceDurationExceededError."""
    service = IncidentService(seeded_session)
    society_id = UUID_SOCIETY_A

    category = await service.create_category(
        society_id,
        IncidentCategoryCreate(
            name="General Noise",
            code="NOISE",
        ),
    )

    with pytest.raises(VoiceDurationExceededError):
        await service.report_incident(
            society_id,
            UUID_USER_REPORTER,
            "RESIDENT",
            IncidentCreate(
                title="Loud Noise Voice Note",
                description="Audio clip attached",
                category_id=category.id,
                voice_note_url="https://storage.internal/audio.mp3",
                voice_note_duration_seconds=95,  # Exceeds 60s limit
            ),
        )


@pytest.mark.asyncio
async def test_emergency_contacts_management(seeded_session: AsyncSession):
    """Verify emergency contacts creation and listing."""
    service = IncidentService(seeded_session)
    society_id = UUID_SOCIETY_A

    contact = await service.create_emergency_contact(
        society_id,
        EmergencyContactCreate(
            contact_type=EmergencyContactType.FIRE,
            name="Central Fire Station",
            phone_number="101",
            display_order=1,
        ),
    )
    assert contact.id is not None

    contacts = await service.list_emergency_contacts(society_id)
    assert len(contacts) >= 1
    assert any(c.name == "Central Fire Station" for c in contacts)


@pytest.mark.asyncio
async def test_administrative_override(seeded_session: AsyncSession):
    """Verify administrative override transitions status directly to target with logged reason."""
    service = IncidentService(seeded_session)
    society_id = UUID_SOCIETY_A

    category = await service.create_category(
        society_id,
        IncidentCategoryCreate(name="Security Alarm", code="ALARM"),
    )

    incident = await service.report_incident(
        society_id,
        UUID_USER_REPORTER,
        "RESIDENT",
        IncidentCreate(
            title="False Burglar Alarm",
            description="Sensor malfunction triggered alarm in Block A",
            category_id=category.id,
        ),
    )

    # Perform Admin Override directly from REPORTED to CANCELLED
    overridden = await service.apply_administrative_override(
        society_id,
        incident.id,
        UUID_USER_ADMIN,
        "ADMIN",
        IncidentOverrideRequest(
            target_status=IncidentStatus.CANCELLED,
            override_reason="Confirmed false alarm caused by sensor maintenance test.",
        ),
    )

    assert overridden.status == IncidentStatus.CANCELLED.value
    assert overridden.override_applied is True
    assert overridden.override_reason == "Confirmed false alarm caused by sensor maintenance test."
    assert overridden.overridden_by_id == UUID_USER_ADMIN
