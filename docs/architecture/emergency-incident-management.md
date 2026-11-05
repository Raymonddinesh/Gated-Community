# Phase 19 — Emergency & Incident Management Foundation Architecture Specification

## 1. Domain Overview & Purpose
Phase 19 introduces the Emergency & Incident Management Foundation for SocietySphere SaaS. It provides a secure, multi-tenant incident reporting, severity evaluation, location tracking, responder triage, escalation, containment, and resolution architecture for apartment societies.

The domain establishes a dedicated operational boundary while integrating cleanly with existing core domains via explicit interfaces and provider-neutral domain events.

## 2. Reusable Architecture from Phases 1–18
1. **Multi-Tenancy & Tenant Context**: Reuse `request.state.tenant_id` resolution, `resolve_society_context`, and `set_db_tenant_context` from Phase 2/Phase 3 auth dependencies.
2. **PostgreSQL RLS + FORCE RLS**: Enforce `society_id = current_setting('app.current_society_id')::uuid` across all Phase 19 tables using Alembic pattern established in Phase 2–18 migrations.
3. **RBAC & Authorization**: Use `require_permission(...)` factory from `apps/api/src/auth/dependencies.py`.
4. **Advisory Locking**: Reuse `pg_advisory_xact_lock` pattern with PostgreSQL dialect protection (`bind.dialect.name == "postgresql"`) for sequential numbering (`INC-YYYY-XXXXXX`) and response triage concurrency.
5. **State Machine Pattern**: Use declarative state machine validators with allowed transition graphs established in Phase 10/11/15/17/18.
6. **Object Storage**: Reuse `ObjectStorageClient` singleton from `apps/api/src/storage/s3_client.py` for encrypted incident attachments and presigned URLs.
7. **Decoupled Domain Events**: Reuse `logger.info("DOMAIN_EVENT: ...")` async event emitter pattern from `apps/api/src/events/event_hooks.py`.
8. **Spatial Location Hierarchy**: Reference Phase 2 `Block`, `Floor`, `Unit` models and Phase 14 `Facility`, `FacilityArea` entities via foreign keys without data duplication.
9. **Responder Resources**: Reference Phase 12 `Staff`, Phase 13 `Vendor`, Phase 18 `CommitteeMember`, and Phase 9 Security Personnel via foreign keys without creating parallel responder tables.
10. **Frontend UI & i18n**: Reuse Next.js Tailwind component system with Easy, Standard, and Admin view modes and English (`en`) / Tamil (`ta`) dictionaries.

## 3. Entity Blueprint (10 Normalized Entities)
1. **Incident**: Central incident record with sequential `INC-YYYY-XXXXXX` numbering.
2. **IncidentCategory**: Configurable category taxonomy (FIRE, MEDICAL, SECURITY, ELECTRICAL, WATER, LIFT, GAS, STRUCTURAL, NATURAL_DISASTER, OTHER).
3. **IncidentAssignment**: Multi-responder assignment mapping (STAFF, SECURITY, COMMITTEE, VENDOR, EMERGENCY_CONTACT).
4. **IncidentTimeline**: Append-only operational incident log (distinction from security audit log).
5. **IncidentAction**: Immediate response tasks (decoupled from Phase 11 WorkOrders).
6. **IncidentEscalation**: Audit log of escalation levels, triggers, and recipients.
7. **IncidentAttachment**: Secure evidence files (photos, audio notes, docs) stored in S3/MinIO.
8. **EmergencyContact**: Society-level and platform-seeded emergency service contacts.
9. **IncidentStatusHistory**: Immutable lifecycle state transition history.
10. **IncidentAcknowledgement**: Formal responder and manager triage acknowledgement records.

## 4. Server-Authoritative Severity & State Machine
- **Severity Levels**: `LOW`, `MEDIUM`, `HIGH`, `CRITICAL` (Server-authoritative, deterministic).
- **State Machine Transitions**:
  `REPORTED` -> `TRIAGED` -> `ACKNOWLEDGED` -> `RESPONSE_STARTED` -> `CONTAINED` -> `RESOLVED` -> `CLOSED`.
  (Alternative terminal/branch states: `ESCALATED`, `CANCELLED`).

## 5. Domain Event Architecture
Emits provider-neutral events:
- `INCIDENT_REPORTED`
- `INCIDENT_TRIAGED`
- `INCIDENT_ACKNOWLEDGED`
- `INCIDENT_RESPONSE_STARTED`
- `INCIDENT_ESCALATED`
- `INCIDENT_CONTAINED`
- `INCIDENT_RESOLVED`
- `INCIDENT_CLOSED`
- `INCIDENT_CANCELLED`
- `INCIDENT_ACTION_CREATED`
- `INCIDENT_ACTION_COMPLETED`

## 6. Financial Isolation
Phase 19 maintains **ZERO** direct mutations to financial ledgers (`JournalEntry`, `Invoice`, `Payment`). Emergency operational expenditure triggers domain events to cross into Phase 4/11 financial boundaries explicitly.
