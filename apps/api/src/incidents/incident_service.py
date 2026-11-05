"""Phase 19 Incident Management Domain Service."""

from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.database.models.incidents import (
    EmergencyContact,
    Incident,
    IncidentAcknowledgement,
    IncidentAction,
    IncidentAssignment,
    IncidentAttachment,
    IncidentCategory,
    IncidentEscalation,
    IncidentStatusHistory,
    IncidentTimeline,
)
from apps.api.src.incidents.enums import ActionStatus, IncidentSeverity, IncidentStatus, TimelineEventType
from apps.api.src.incidents.event_hooks import IncidentDomainHooks
from apps.api.src.incidents.exceptions import (
    EmergencyContactNotFoundError,
    IncidentCategoryNotFoundError,
    IncidentNotFoundError,
    VoiceDurationExceededError,
)
from apps.api.src.incidents.repositories import (
    EmergencyContactRepository,
    IncidentCategoryRepository,
    IncidentRepository,
)
from apps.api.src.incidents.schemas import (
    EmergencyContactCreate,
    EmergencyContactUpdate,
    IncidentAcknowledgementCreate,
    IncidentActionCreate,
    IncidentActionUpdate,
    IncidentAssignmentCreate,
    IncidentAttachmentCreate,
    IncidentCategoryCreate,
    IncidentCreate,
    IncidentEscalationCreate,
    IncidentOverrideRequest,
    IncidentTriageRequest,
)
from apps.api.src.incidents.state_machine import IncidentStateMachine


class IncidentService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.incident_repo = IncidentRepository(session)
        self.category_repo = IncidentCategoryRepository(session)
        self.contact_repo = EmergencyContactRepository(session)

    # ==========================================
    # Categories & Contacts
    # ==========================================
    async def list_categories(self, society_id: UUID) -> list[IncidentCategory]:
        return await self.category_repo.list_categories(society_id)

    async def create_category(self, society_id: UUID, data: IncidentCategoryCreate) -> IncidentCategory:
        cat = IncidentCategory(
            society_id=society_id,
            name=data.name,
            code=data.code.upper(),
            description=data.description,
            default_severity=data.default_severity.value,
            default_sla_minutes=data.default_sla_minutes,
            is_active=data.is_active,
        )
        return await self.category_repo.create_category(cat)

    async def list_emergency_contacts(self, society_id: UUID) -> list[EmergencyContact]:
        return await self.contact_repo.list_contacts(society_id)

    async def create_emergency_contact(
        self, society_id: UUID, data: EmergencyContactCreate
    ) -> EmergencyContact:
        contact = EmergencyContact(
            society_id=society_id if not data.is_platform_default else None,
            contact_type=data.contact_type.value,
            name=data.name,
            phone_number=data.phone_number,
            alt_phone_number=data.alt_phone_number,
            email=data.email,
            address=data.address,
            is_platform_default=data.is_platform_default,
            is_active=data.is_active,
            display_order=data.display_order,
            notes=data.notes,
        )
        return await self.contact_repo.create_contact(contact)

    async def update_emergency_contact(
        self, contact_id: UUID, data: EmergencyContactUpdate
    ) -> EmergencyContact:
        contact = await self.contact_repo.get_by_id(contact_id)
        if not contact:
            raise EmergencyContactNotFoundError()

        if data.contact_type:
            contact.contact_type = data.contact_type.value
        if data.name:
            contact.name = data.name
        if data.phone_number:
            contact.phone_number = data.phone_number
        if data.alt_phone_number is not None:
            contact.alt_phone_number = data.alt_phone_number
        if data.email is not None:
            contact.email = data.email
        if data.address is not None:
            contact.address = data.address
        if data.is_active is not None:
            contact.is_active = data.is_active
        if data.display_order is not None:
            contact.display_order = data.display_order
        if data.notes is not None:
            contact.notes = data.notes

        return await self.contact_repo.update_contact(contact)

    # ==========================================
    # Core Incident Lifecycle
    # ==========================================
    async def report_incident(
        self,
        society_id: UUID,
        reporter_id: UUID,
        reporter_role: str,
        data: IncidentCreate,
    ) -> Incident:
        # Server-side validation of voice note duration
        if data.voice_note_duration_seconds and data.voice_note_duration_seconds > 60:
            raise VoiceDurationExceededError("Voice note duration cannot exceed 60 seconds")

        cat = await self.category_repo.get_by_id(data.category_id)
        if not cat:
            raise IncidentCategoryNotFoundError()

        # Compute server-authoritative severity
        severity = data.severity.value if data.severity else cat.default_severity
        lower_text = f"{data.title} {data.description}".lower()
        if any(kw in lower_text for kw in ["fire", "explosion", "gas leak", "collapse", "electrocution"]):
            severity = IncidentSeverity.CRITICAL.value

        incident_number = await self.incident_repo.generate_incident_number(society_id)

        incident = Incident(
            society_id=society_id,
            incident_number=incident_number,
            title=data.title,
            description=data.description,
            category_id=data.category_id,
            severity=severity,
            status=IncidentStatus.REPORTED.value,
            reported_by_id=reporter_id,
            reporter_type=data.reporter_type.value,
            reporter_contact=data.reporter_contact,
            block_id=data.block_id,
            floor_id=data.floor_id,
            unit_id=data.unit_id,
            facility_id=data.facility_id,
            facility_area_id=data.facility_area_id,
            location_details=data.location_details,
            latitude=data.latitude,
            longitude=data.longitude,
            voice_note_url=data.voice_note_url,
            voice_note_duration_seconds=data.voice_note_duration_seconds,
        )
        await self.incident_repo.create_incident(incident)

        # Record timeline & status history
        await self.incident_repo.create_timeline(
            IncidentTimeline(
                society_id=society_id,
                incident_id=incident.id,
                actor_id=reporter_id,
                actor_role=reporter_role,
                event_type=TimelineEventType.REPORTED.value,
                summary=f"Incident reported: {incident.title}",
                details=incident.description,
            )
        )
        await self.incident_repo.create_status_history(
            IncidentStatusHistory(
                society_id=society_id,
                incident_id=incident.id,
                from_status=None,
                to_status=IncidentStatus.REPORTED.value,
                changed_by_id=reporter_id,
                reason="Initial emergency report created",
            )
        )

        await IncidentDomainHooks.emit_incident_reported(
            society_id=society_id,
            incident_id=incident.id,
            incident_number=incident.incident_number,
            severity=incident.severity,
            title=incident.title,
        )

        return incident

    async def get_incident(self, society_id: UUID, incident_id: UUID) -> Incident:
        incident = await self.incident_repo.get_by_id(incident_id, society_id)
        if not incident:
            raise IncidentNotFoundError()
        return incident

    async def list_incidents(
        self,
        society_id: UUID,
        status: str | None = None,
        severity: str | None = None,
        category_id: UUID | None = None,
        reported_by_id: UUID | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Incident]:
        return await self.incident_repo.list_incidents(
            society_id=society_id,
            status=status,
            severity=severity,
            category_id=category_id,
            reported_by_id=reported_by_id,
            limit=limit,
            offset=offset,
        )

    async def triage_incident(
        self,
        society_id: UUID,
        incident_id: UUID,
        triaged_by_id: UUID,
        triaged_by_role: str,
        data: IncidentTriageRequest,
    ) -> Incident:
        incident = await self.get_incident(society_id, incident_id)
        IncidentStateMachine.validate_transition(incident.status, IncidentStatus.TRIAGED.value)

        old_status = incident.status
        incident.severity = data.severity.value
        incident.status = IncidentStatus.TRIAGED.value
        incident.requires_governance_review = data.requires_governance_review
        incident.requires_work_order = data.requires_work_order

        await self.incident_repo.update_incident(incident)

        await self.incident_repo.create_status_history(
            IncidentStatusHistory(
                society_id=society_id,
                incident_id=incident.id,
                from_status=old_status,
                to_status=IncidentStatus.TRIAGED.value,
                changed_by_id=triaged_by_id,
                reason=data.triage_notes or f"Triaged to severity {data.severity.value}",
            )
        )

        await self.incident_repo.create_timeline(
            IncidentTimeline(
                society_id=society_id,
                incident_id=incident.id,
                actor_id=triaged_by_id,
                actor_role=triaged_by_role,
                event_type=TimelineEventType.STATUS_CHANGED.value,
                summary=f"Incident triaged with severity {data.severity.value}",
                details=data.triage_notes,
            )
        )

        await IncidentDomainHooks.emit_incident_triaged(
            society_id=society_id,
            incident_id=incident.id,
            incident_number=incident.incident_number,
            severity=incident.severity,
            triaged_by_id=triaged_by_id,
        )

        if incident.requires_governance_review:
            await IncidentDomainHooks.emit_governance_review_required(
                society_id, incident.id, incident.incident_number
            )

        if incident.requires_work_order:
            await IncidentDomainHooks.emit_work_order_required(
                society_id, incident.id, incident.incident_number
            )

        return incident

    async def acknowledge_incident(
        self,
        society_id: UUID,
        incident_id: UUID,
        responder_id: UUID,
        data: IncidentAcknowledgementCreate,
    ) -> IncidentAcknowledgement:
        incident = await self.get_incident(society_id, incident_id)
        if incident.status in [IncidentStatus.REPORTED.value, IncidentStatus.TRIAGED.value]:
            old_status = incident.status
            incident.status = IncidentStatus.ACKNOWLEDGED.value
            await self.incident_repo.update_incident(incident)

            await self.incident_repo.create_status_history(
                IncidentStatusHistory(
                    society_id=society_id,
                    incident_id=incident.id,
                    from_status=old_status,
                    to_status=IncidentStatus.ACKNOWLEDGED.value,
                    changed_by_id=responder_id,
                    reason=f"Acknowledged by responder role {data.responder_role}",
                )
            )

        ack = IncidentAcknowledgement(
            society_id=society_id,
            incident_id=incident_id,
            acknowledged_by_id=responder_id,
            responder_role=data.responder_role,
            notes=data.notes,
        )
        await self.incident_repo.create_acknowledgement(ack)

        await self.incident_repo.create_timeline(
            IncidentTimeline(
                society_id=society_id,
                incident_id=incident.id,
                actor_id=responder_id,
                actor_role=data.responder_role,
                event_type=TimelineEventType.ACTION_TAKEN.value,
                summary=f"Incident acknowledged by responder role '{data.responder_role}'",
                details=data.notes,
            )
        )

        await IncidentDomainHooks.emit_incident_acknowledged(
            society_id=society_id,
            incident_id=incident.id,
            incident_number=incident.incident_number,
            responder_id=responder_id,
            responder_role=data.responder_role,
        )

        return ack

    async def assign_responder(
        self,
        society_id: UUID,
        incident_id: UUID,
        assigned_by_id: UUID,
        assigned_by_role: str,
        data: IncidentAssignmentCreate,
    ) -> IncidentAssignment:
        incident = await self.get_incident(society_id, incident_id)

        assignment = IncidentAssignment(
            society_id=society_id,
            incident_id=incident_id,
            responder_type=data.responder_type.value,
            assigned_user_id=data.assigned_user_id,
            assigned_staff_id=data.assigned_staff_id,
            assigned_vendor_id=data.assigned_vendor_id,
            assigned_role=data.assigned_role,
            assignment_notes=data.assignment_notes,
            is_primary=data.is_primary,
            assigned_by_id=assigned_by_id,
        )
        await self.incident_repo.create_assignment(assignment)

        if incident.status in [IncidentStatus.TRIAGED.value, IncidentStatus.ACKNOWLEDGED.value]:
            old_status = incident.status
            incident.status = IncidentStatus.RESPONSE_STARTED.value
            await self.incident_repo.update_incident(incident)

            await self.incident_repo.create_status_history(
                IncidentStatusHistory(
                    society_id=society_id,
                    incident_id=incident.id,
                    from_status=old_status,
                    to_status=IncidentStatus.RESPONSE_STARTED.value,
                    changed_by_id=assigned_by_id,
                    reason=f"Responder assigned ({data.responder_type.value})",
                )
            )

        await self.incident_repo.create_timeline(
            IncidentTimeline(
                society_id=society_id,
                incident_id=incident.id,
                actor_id=assigned_by_id,
                actor_role=assigned_by_role,
                event_type=TimelineEventType.ASSIGNED.value,
                summary=f"Responder assigned: {data.responder_type.value}",
                details=data.assignment_notes,
            )
        )

        await IncidentDomainHooks.emit_responder_assigned(
            society_id=society_id,
            incident_id=incident.id,
            incident_number=incident.incident_number,
            responder_type=data.responder_type.value,
            assigned_id=data.assigned_user_id
            or data.assigned_staff_id
            or data.assigned_vendor_id
            or assigned_by_id,
        )

        return assignment

    async def escalate_incident(
        self,
        society_id: UUID,
        incident_id: UUID,
        triggered_by_id: UUID,
        triggered_by_role: str,
        data: IncidentEscalationCreate,
    ) -> IncidentEscalation:
        incident = await self.get_incident(society_id, incident_id)

        # Determine level
        existing_escalations = await self.incident_repo.list_escalations(incident_id, society_id)
        next_level = len(existing_escalations) + 1

        old_status = incident.status
        IncidentStateMachine.validate_transition(old_status, IncidentStatus.ESCALATED.value)
        incident.status = IncidentStatus.ESCALATED.value
        await self.incident_repo.update_incident(incident)

        escalation = IncidentEscalation(
            society_id=society_id,
            incident_id=incident_id,
            escalation_level=next_level,
            triggered_by_id=triggered_by_id,
            target_role=data.target_role,
            reason=data.reason,
        )
        await self.incident_repo.create_escalation(escalation)

        await self.incident_repo.create_status_history(
            IncidentStatusHistory(
                society_id=society_id,
                incident_id=incident.id,
                from_status=old_status,
                to_status=IncidentStatus.ESCALATED.value,
                changed_by_id=triggered_by_id,
                reason=f"Escalated to {data.target_role}: {data.reason}",
            )
        )

        await self.incident_repo.create_timeline(
            IncidentTimeline(
                society_id=society_id,
                incident_id=incident.id,
                actor_id=triggered_by_id,
                actor_role=triggered_by_role,
                event_type=TimelineEventType.ESCALATED.value,
                summary=f"Incident escalated to level {next_level} ({data.target_role})",
                details=data.reason,
            )
        )

        await IncidentDomainHooks.emit_incident_escalated(
            society_id=society_id,
            incident_id=incident.id,
            incident_number=incident.incident_number,
            escalation_level=next_level,
            target_role=data.target_role,
            reason=data.reason,
        )

        return escalation

    async def contain_hazard(
        self, society_id: UUID, incident_id: UUID, actor_id: UUID, actor_role: str
    ) -> Incident:
        incident = await self.get_incident(society_id, incident_id)
        old_status = incident.status

        IncidentStateMachine.validate_transition(old_status, IncidentStatus.CONTAINED.value)
        incident.status = IncidentStatus.CONTAINED.value
        incident.is_hazard_contained = True
        incident.hazard_contained_at = datetime.now()
        await self.incident_repo.update_incident(incident)

        await self.incident_repo.create_status_history(
            IncidentStatusHistory(
                society_id=society_id,
                incident_id=incident.id,
                from_status=old_status,
                to_status=IncidentStatus.CONTAINED.value,
                changed_by_id=actor_id,
                reason="Hazard contained by responder",
            )
        )

        await self.incident_repo.create_timeline(
            IncidentTimeline(
                society_id=society_id,
                incident_id=incident.id,
                actor_id=actor_id,
                actor_role=actor_role,
                event_type=TimelineEventType.ACTION_TAKEN.value,
                summary="Hazard successfully contained",
            )
        )

        await IncidentDomainHooks.emit_incident_contained(society_id, incident.id, incident.incident_number)

        return incident

    async def resolve_incident(
        self,
        society_id: UUID,
        incident_id: UUID,
        resolver_id: UUID,
        resolver_role: str,
        reason: str | None = None,
    ) -> Incident:
        incident = await self.get_incident(society_id, incident_id)
        old_status = incident.status

        IncidentStateMachine.validate_transition(old_status, IncidentStatus.RESOLVED.value)
        incident.status = IncidentStatus.RESOLVED.value
        incident.resolved_at = datetime.now()
        await self.incident_repo.update_incident(incident)

        await self.incident_repo.create_status_history(
            IncidentStatusHistory(
                society_id=society_id,
                incident_id=incident.id,
                from_status=old_status,
                to_status=IncidentStatus.RESOLVED.value,
                changed_by_id=resolver_id,
                reason=reason or "Incident resolved",
            )
        )

        await self.incident_repo.create_timeline(
            IncidentTimeline(
                society_id=society_id,
                incident_id=incident.id,
                actor_id=resolver_id,
                actor_role=resolver_role,
                event_type=TimelineEventType.STATUS_CHANGED.value,
                summary="Incident resolved",
                details=reason,
            )
        )

        await IncidentDomainHooks.emit_incident_resolved(
            society_id, incident.id, incident.incident_number, resolver_id
        )

        return incident

    async def close_incident(
        self,
        society_id: UUID,
        incident_id: UUID,
        closed_by_id: UUID,
        closed_by_role: str,
        reason: str | None = None,
    ) -> Incident:
        incident = await self.get_incident(society_id, incident_id)
        old_status = incident.status

        IncidentStateMachine.validate_transition(old_status, IncidentStatus.CLOSED.value)
        incident.status = IncidentStatus.CLOSED.value
        incident.closed_at = datetime.now()
        await self.incident_repo.update_incident(incident)

        await self.incident_repo.create_status_history(
            IncidentStatusHistory(
                society_id=society_id,
                incident_id=incident.id,
                from_status=old_status,
                to_status=IncidentStatus.CLOSED.value,
                changed_by_id=closed_by_id,
                reason=reason or "Incident closed",
            )
        )

        await self.incident_repo.create_timeline(
            IncidentTimeline(
                society_id=society_id,
                incident_id=incident.id,
                actor_id=closed_by_id,
                actor_role=closed_by_role,
                event_type=TimelineEventType.STATUS_CHANGED.value,
                summary="Incident closed",
                details=reason,
            )
        )

        await IncidentDomainHooks.emit_incident_closed(
            society_id, incident.id, incident.incident_number, closed_by_id
        )

        return incident

    async def apply_administrative_override(
        self,
        society_id: UUID,
        incident_id: UUID,
        overridden_by_id: UUID,
        overridden_by_role: str,
        data: IncidentOverrideRequest,
    ) -> Incident:
        incident = await self.get_incident(society_id, incident_id)
        old_status = incident.status

        # Admin override bypasses standard transition graph
        IncidentStateMachine.validate_transition(old_status, data.target_status.value, is_override=True)

        incident.status = data.target_status.value
        incident.override_applied = True
        incident.override_reason = data.override_reason
        incident.overridden_by_id = overridden_by_id
        incident.overridden_at = datetime.now()

        await self.incident_repo.update_incident(incident)

        await self.incident_repo.create_status_history(
            IncidentStatusHistory(
                society_id=society_id,
                incident_id=incident.id,
                from_status=old_status,
                to_status=data.target_status.value,
                changed_by_id=overridden_by_id,
                reason=f"ADMIN OVERRIDE: {data.override_reason}",
            )
        )

        await self.incident_repo.create_timeline(
            IncidentTimeline(
                society_id=society_id,
                incident_id=incident.id,
                actor_id=overridden_by_id,
                actor_role=overridden_by_role,
                event_type=TimelineEventType.OVERRIDE_APPLIED.value,
                summary=f"Administrative status override to {data.target_status.value}",
                details=data.override_reason,
                is_internal_only=True,
            )
        )

        await IncidentDomainHooks.emit_incident_override_applied(
            society_id=society_id,
            incident_id=incident.id,
            incident_number=incident.incident_number,
            overridden_by_id=overridden_by_id,
            reason=data.override_reason,
        )

        return incident

    # ==========================================
    # Actions & Attachments
    # ==========================================
    async def create_action(
        self,
        society_id: UUID,
        incident_id: UUID,
        created_by_id: UUID,
        data: IncidentActionCreate,
    ) -> IncidentAction:
        await self.get_incident(society_id, incident_id)
        action = IncidentAction(
            society_id=society_id,
            incident_id=incident_id,
            title=data.title,
            description=data.description,
            priority=data.priority.value,
            assigned_user_id=data.assigned_user_id,
            due_at=data.due_at,
            created_by_id=created_by_id,
        )
        return await self.incident_repo.create_action(action)

    async def update_action(
        self,
        society_id: UUID,
        action_id: UUID,
        updated_by_id: UUID,
        data: IncidentActionUpdate,
    ) -> IncidentAction:
        action = await self.incident_repo.get_action_by_id(action_id, society_id)
        if not action:
            raise IncidentNotFoundError("Incident action item not found")

        if data.title:
            action.title = data.title
        if data.description is not None:
            action.description = data.description
        if data.priority:
            action.priority = data.priority.value
        if data.assigned_user_id is not None:
            action.assigned_user_id = data.assigned_user_id
        if data.due_at is not None:
            action.due_at = data.due_at
        if data.status:
            action.status = data.status.value
            if data.status == ActionStatus.COMPLETED:
                action.completed_at = datetime.now()
                action.completed_by_id = updated_by_id

        return await self.incident_repo.update_action(action)

    async def create_attachment(
        self,
        society_id: UUID,
        incident_id: UUID,
        uploaded_by_id: UUID,
        uploaded_by_role: str,
        data: IncidentAttachmentCreate,
    ) -> IncidentAttachment:
        incident = await self.get_incident(society_id, incident_id)

        attachment = IncidentAttachment(
            society_id=society_id,
            incident_id=incident_id,
            file_name=data.file_name,
            file_type=data.file_type.value,
            file_size_bytes=data.file_size_bytes,
            storage_path=data.storage_path,
            mime_type=data.mime_type,
            duration_seconds=data.duration_seconds,
            uploaded_by_id=uploaded_by_id,
        )
        await self.incident_repo.create_attachment(attachment)

        await self.incident_repo.create_timeline(
            IncidentTimeline(
                society_id=society_id,
                incident_id=incident.id,
                actor_id=uploaded_by_id,
                actor_role=uploaded_by_role,
                event_type=TimelineEventType.ATTACHMENT_ADDED.value,
                summary=f"Attachment added: {attachment.file_name}",
            )
        )

        return attachment
