# Phase 19 — Emergency & Incident Management Foundation Pre-Implementation Architecture Report

## 1. Existing Phase 1–18 Inspection Summary
A detailed codebase audit of SocietySphere across locked Phases 1–18 confirms:
- **Phase 1 (Foundation)**: Operational logging (`societysphere.storage`), global exception hierarchy, correlation middleware, `ObjectStorageClient` for S3/MinIO.
- **Phase 2 (Multi-Tenancy & RLS)**: Spatial hierarchy (`Society`, `Block`, `Floor`, `Unit`), `resolve_society_context`, `set_db_tenant_context`, and PostgreSQL RLS + `FORCE RLS` framework.
- **Phase 3 (Auth & RBAC)**: Session validation (`decode_access_token`), `require_permission(...)` factory, role resolution (`AuthorizationRepository`, `MembershipRepository`).
- **Phases 4–6 (Financial Core, Billing, Reconciliation)**: Double-entry financial ledgers (`JournalEntry`, `Invoice`, `Payment`) guarded with strict financial isolation.
- **Phase 7 (Resident / Owner / Tenant)**: User profiles, occupancy mappings, resident delegates.
- **Phase 8–9 (Vehicles, Visitors, Security)**: Security desk context, vehicle & visitor logs.
- **Phase 10 (Complaints & Helpdesk)**: State machine validation patterns, SLA timers, attachment linkage.
- **Phase 11 (Maintenance & Work Orders)**: Operational state transitions, priority policies, material tracking.
- **Phase 12 (Staff & Workforce)**: Staff profiles, roles, operational teams.
- **Phase 13 (Vendor Management)**: Service provider profiles and compliance documents.
- **Phase 14 (Facility & Asset)**: Physical facilities, sub-areas, assets.
- **Phase 15 (Facility Booking)**: Operational availability, reservation rules, blackout periods.
- **Phase 16 (Announcements & Communications)**: Decoupled notification hooks, audience targeting.
- **Phase 17 (Events & Community)**: Domain event emitters (`EventDomainHooks`), presigned GET/PUT URLs, PII privacy filters.
- **Phase 18 (Committee, Meetings & Resolutions)**: Transactional advisory locking (`pg_advisory_xact_lock`), sequential numbering generators, maker-checker validation.

## 2. Reusable Components Identified
- **Tenant Context & RLS**: `resolve_society_context`, `set_db_tenant_context`, RLS macro `society_id = current_setting('app.current_society_id')::uuid`.
- **RBAC Dependency**: `require_permission(permission_code)`.
- **Storage Client**: `get_storage_client().generate_presigned_upload_url`, `generate_presigned_download_url`.
- **Advisory Locks**: `pg_advisory_xact_lock` with PostgreSQL dialect protection (`bind.dialect.name == "postgresql"`).
- **Spatial Master Data**: Foreign key references to `Block`, `Floor`, `Unit`, `Facility`, `FacilityArea`.
- **Responder Master Data**: Foreign key references to `User`, `Staff`, `Vendor`, `CommitteeMember`.
- **Domain Event Pattern**: Decoupled async event logger (`IncidentDomainHooks`).
- **Frontend UI & i18n**: Next.js Tailwind component structure, Easy/Standard/Admin mode switchers, English (`en`) and Tamil (`ta`) dictionary dictionaries.

## 3. Proposed Phase 19 Domain Boundary
`apps/api/src/incidents/`
- `domain/`: `models.py`, `enums.py`, `exceptions.py`, `state_machine.py`, `privacy.py`, `event_hooks.py`, `concurrency.py`
- `repositories/`: `repositories.py`
- `services/`: `incident_service.py`
- `schemas/`: `schemas.py`
- `api/`: `incidents.py`, `assignments.py`, `actions.py`, `contacts.py`, `router.py`

## 4. Final Entity List (10 Normalized Entities)
1. `Incident`: Master emergency record.
2. `IncidentCategory`: Incident category taxonomy.
3. `IncidentAssignment`: Multi-responder assignments.
4. `IncidentTimeline`: Append-only operational incident log.
5. `IncidentAction`: Immediate response tasks.
6. `IncidentEscalation`: Escalation history audit log.
7. `IncidentAttachment`: Presigned object storage attachment metadata.
8. `EmergencyContact`: Society & platform emergency directory.
9. `IncidentStatusHistory`: Lifecycle state change history.
10. `IncidentAcknowledgement`: Responder triage receipts.

## 5. Entity Relationships
- `Society` (1) -> (N) `Incident`
- `Incident` (1) -> (N) `IncidentAssignment`
- `Incident` (1) -> (N) `IncidentTimeline`
- `Incident` (1) -> (N) `IncidentAction`
- `Incident` (1) -> (N) `IncidentEscalation`
- `Incident` (1) -> (N) `IncidentAttachment`
- `Incident` (1) -> (N) `IncidentStatusHistory`
- `Incident` (1) -> (N) `IncidentAcknowledgement`
- `Society` (1) -> (N) `EmergencyContact`

## 6. Lifecycle / State-Machine Design
`REPORTED` -> `TRIAGED` -> `ACKNOWLEDGED` -> `RESPONSE_STARTED` -> `CONTAINED` -> `RESOLVED` -> `CLOSED`.
Branch states: `ESCALATED`, `CANCELLED`.
Transitions enforced via `IncidentStateMachine.validate_transition(old_status, new_status)`.

## 7. Numbering Strategy
Sequential `INC-YYYY-XXXXXX` generated per society under PostgreSQL advisory lock `acquire_incident_number_lock`.

## 8. Severity Strategy
Server-authoritative levels: `LOW`, `MEDIUM`, `HIGH`, `CRITICAL`. Deterministic calculations based on category and reported threat.

## 9. Location Strategy
References Phase 2 `Block`, `Floor`, `Unit` or Phase 14 `Facility`, `FacilityArea` without duplicating location tables.

## 10. Assignment Strategy
Supports `STAFF`, `SECURITY`, `COMMITTEE`, `VENDOR`, `EMERGENCY_CONTACT` responder types referencing existing domain models.

## 11. Escalation Strategy
`IncidentEscalation` entity logs escalation level, triggered_by, target_role, reason, timestamp, and response SLA.

## 12. Timeline Strategy
Append-only `IncidentTimeline` records operational responder log entries separate from system security audit logs.

## 13. Attachment Strategy
Secure presigned PUT/GET URLs (`societies/{society_id}/incidents/{incident_id}/{file_size}_{filename}`) via `ObjectStorageClient`.

## 14. Emergency-Contact Strategy
`EmergencyContact` directory configurable per society (`POLICE`, `FIRE`, `AMBULANCE`, `HOSPITAL`, `ELECTRICITY`, `GAS`, `SECURITY`).

## 15. Emergency-Override Decision
Narrowly scoped administrative override requiring explicit `incident.override` permission and mandatory logged reason.

## 16. Privacy Model
Server-side PII masking (`IncidentPrivacyFilter`) hides medical details, reporter identity, and unit number from unauthorized residents.

## 17. RBAC Permission Matrix (21 Canonical Permissions)
`incident.report`, `incident.view_own`, `incident.view`, `incident.view_all`, `incident.create`, `incident.triage`, `incident.acknowledge`, `incident.assign`, `incident.respond`, `incident.escalate`, `incident.resolve`, `incident.close`, `incident.timeline.view`, `incident.timeline.manage`, `incident.action.view`, `incident.action.create`, `incident.action.assign`, `incident.action.update`, `incident.contact.view`, `incident.contact.manage`, `incident.override`.

## 18. API Specification
REST endpoints under `/api/v1/incidents` and `/api/v1/emergency-contacts` with OpenAPI schemas and Bearer JWT + `X-Society-ID` headers.

## 19. Database Schema Proposal
10 tables with UUID primary keys, foreign key constraints, indexing on `(society_id, status)`, `(society_id, severity)`, and `created_at`.

## 20. RLS Strategy
`ALTER TABLE <table_name> ENABLE ROW LEVEL SECURITY;`

## 21. FORCE RLS Strategy
`ALTER TABLE <table_name> FORCE ROW LEVEL SECURITY;`

## 22. IDOR Protection
Every endpoint verifies `society_id` matches tenant context and verifies object ownership/responder permission before returning records.

## 23. Concurrency Strategy
PostgreSQL advisory locks (`acquire_incident_number_lock`, `acquire_incident_triage_lock`) with dialect check (`bind.dialect.name == "postgresql"`).

## 24. Idempotency Strategy
Mutations accept `X-Idempotency-Key` headers stored in Redis/DB cache for 24 hours.

## 25. Audit Architecture
All lifecycle transitions and overrides written to `IncidentStatusHistory` and core `AuditLog`.

## 26. Domain-Event Architecture
Decoupled domain events emitted via `IncidentDomainHooks` (`INCIDENT_REPORTED`, `INCIDENT_ACKNOWLEDGED`, `INCIDENT_RESOLVED`, etc.).

## 27. AI Boundary
AI features (voice transcription, translation, summary) are strictly advisory. AI MUST NOT dispatch responders or alter authoritative severity/status.

## 28. Financial Isolation
**0** direct mutations to financial ledgers (`JournalEntry`, `Invoice`, `Payment`). Emergency capex triggers domain events to Phase 11/4.

## 29. Phase 7 Integration
References `ResidentProfile`, `UnitOccupancy`, `UnitOwnership`, `ResidentDelegate`.

## 30. Phase 9 Integration
References Security personnel desk context.

## 31. Phase 10 Integration
Allows cross-referencing between incidents and complaints via domain links.

## 32. Phase 11 Integration
Triggers `GOVERNANCE_ACTION_ITEM_CREATED` / `WORK_ORDER_REQUIRED` domain events for maintenance follow-ups without duplicating WorkOrders.

## 33. Phase 12 Integration
Assigns operational `Staff` and staff teams as emergency responders.

## 34. Phase 13 Integration
Assigns contracted `Vendor` service providers for specialized containment.

## 35. Phase 14 Integration
Links incidents to physical `Facility` and `Asset` entities.

## 36. Phase 16 Integration
Emits broadcast domain events for critical society emergency circulars.

## 37. Phase 17 Integration
Links emergency incidents occurring during community events.

## 38. Phase 18 Integration
Notifies managing committee members for escalation review.

## 39. Frontend Architecture
Next.js page `apps/web/src/app/incidents/page.tsx` with Easy Mode (1-click emergency reporting), Standard Mode, and Admin Mode.

## 40. Accessibility Design
Large touch targets, high contrast, ARIA screen-reader labels, mobile-first design, usable under extreme stress.

## 41. Performance Design
Indexes on `(society_id, status)`, `(society_id, severity)`, paginated lists, N+1 query prevention via eager joins.

## 42. Migration Plan
Next migration: `0019_emergency_incident_management.py` (down_revision = `0018_committee_meetings_resolutions_governance`).

## 43. Testing Strategy
Unit tests, state-machine tests, RLS tests, FORCE RLS tests, IDOR tests, financial isolation tests, concurrency tests, full regression (303+ tests).

## 44. Security Gate Blueprint
38 security & architecture validation gates (Gate A to Gate AP).

## 45. Scope Exclusions
No third-party fire/police APIs, no automatic CCTV AI dispatch, no SMS/WhatsApp direct integrations, no medical diagnoses.

## 46. Open Architectural Decisions
- Emergency contact seed defaults (Platform vs Society).
- Incident voice note recording duration cap (60s vs 120s).
- Mandatory SMS notification hook configuration.

## 47. Implementation Sequence Proposal
1. Domain models & enums (`incidents/domain/`)
2. Migration `0019_emergency_incident_management.py`
3. Repositories & advisory locks (`repositories.py`, `concurrency.py`)
4. State machine & privacy filter (`state_machine.py`, `privacy.py`)
5. Service & domain hooks (`incident_service.py`, `event_hooks.py`)
6. REST API routes & v1 router (`incidents/api/`)
7. RBAC permission seeding (`seed_dev_data.py`)
8. Frontend UI (`apps/web/src/app/incidents/page.tsx`)
9. Test suites (`test_emergency_incident_management.py`, `test_incidents_domain_finalization.py`)
10. Final validation & full regression pass.

---

## Final Summary & Status Confirmation
1. **Architecture Summary**: Multi-tenant emergency reporting, severity evaluation, responder triage, timeline logging, and privacy filtering.
2. **Reuse Analysis**: Fully reuses RLS, auth dependencies, S3 storage client, advisory locks, spatial hierarchy, and domain hook logging.
3. **Entity Model**: 10 normalized entities designed with strict foreign key references.
4. **API Design**: Complete REST specification under `/api/v1/incidents`.
5. **RBAC Matrix**: 21 canonical permissions defined and mapped to personas.
6. **Security Architecture**: Multi-tenant RLS, FORCE RLS, IDOR protection, PII masking, presigned GET/PUT storage URLs.
7. **RLS/FORCE RLS Strategy**: Enforced via Alembic migration `0019_emergency_incident_management`.
8. **Concurrency Strategy**: PostgreSQL advisory locks for sequential numbering (`INC-YYYY-XXXXXX`) and triage race prevention.
9. **Integration Boundaries**: Clean integration with Phases 1–18 via domain events without data duplication.
10. **Frontend Architecture**: Easy, Standard, and Admin modes with English & Tamil i18n support.
11. **Migration Plan**: `0019_emergency_incident_management` defined.
12. **Test Strategy**: Comprehensive unit, security, RLS, IDOR, concurrency, and full regression strategy.
13. **Security Gate Blueprint**: 38 architectural validation gates.
14. **Open Architectural Decisions**: Documented for architect review.
15. **Implementation Sequence**: 10-step implementation roadmap.
16. **Files Created**:
    - `docs/architecture/emergency-incident-management.md`
    - `docs/security/emergency-incident-management-security.md`
    - `docs/api/incidents.md`
    - `docs/adr/ADR-028-emergency-incident-management.md`
    - `PHASE_19_ARCHITECTURE_SPEC.md`
    - `PHASE_19_PRE_IMPLEMENTATION_REPORT.md`
17. **Confirmation**: **NO PRODUCTION CODE OR MIGRATIONS WERE EXECUTED**. Phases 1–18 remain 100% untouched and locked.

FINAL STATUS: READY FOR ARCHITECT REVIEW
