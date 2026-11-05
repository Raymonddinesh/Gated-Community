# Phase 19 — Emergency & Incident Management Architecture Specification

## 1. Architectural Mandate
SocietySphere Phase 19 establishes a multi-tenant, high-availability Emergency & Incident Management Foundation.
This document defines the pre-implementation blueprint for database models, security, RLS, RBAC, domain events, API schemas, frontend views, and test strategies.

NO PRODUCTION IMPLEMENTATION OR MIGRATION HAS BEEN EXECUTED.

## 2. Reusable Core Assets (Phases 1–18 Inspection)
- **Phase 1 Infrastructure**: Logging (`societysphere.storage`, `seed`), Base Exceptions, Health probe (`check_health`), S3 Storage client (`ObjectStorageClient`), Correlation IDs.
- **Phase 2 Tenant Context & Spatial Hierarchy**: RLS / `FORCE RLS` framework, `resolve_society_context`, `Block`, `Floor`, `Unit` spatial hierarchy.
- **Phase 3 Auth & RBAC**: `require_permission(...)` factory, JWT session validation, `AuthorizationRepository`, `MembershipRepository`.
- **Phase 7 Resident Domain**: `ResidentProfile`, `UnitOwnership`, `UnitOccupancy`, `ResidentDelegate`.
- **Phase 9 Visitor & Security**: Security desk context, access records.
- **Phase 10 Complaints Domain**: Status transition history pattern, attachment management patterns.
- **Phase 11 Work Order Domain**: State machine pattern, material tracking pattern.
- **Phase 12 Staff Domain**: `Staff`, `StaffRole`, operational teams.
- **Phase 13 Vendor Domain**: `Vendor`, service provider profiles.
- **Phase 14 Facility & Asset Domain**: `Facility`, `FacilityArea`, `Asset`.
- **Phase 15 Booking Domain**: Availability and blackout rules.
- **Phase 16 Announcement Domain**: Public notification hooks, audience targeting.
- **Phase 17 Events Domain**: Decoupled `EventDomainHooks`, media attachment presigned URLs, privacy filtering.
- **Phase 18 Governance Domain**: Sequential numbering locks, advisory locking (`pg_advisory_xact_lock`), maker-checker validation, domain hooks.

## 3. Entity Blueprint (10 Entities)
1. `Incident`: Core entity, `INC-YYYY-XXXXXX`.
2. `IncidentCategory`: Configurable incident taxonomy.
3. `IncidentAssignment`: Responders mapping (`STAFF`, `SECURITY`, `COMMITTEE`, `VENDOR`, `EMERGENCY_CONTACT`).
4. `IncidentTimeline`: Operational log entries.
5. `IncidentAction`: Immediate response tasks.
6. `IncidentEscalation`: Escalation audit trail.
7. `IncidentAttachment`: Evidence files (photo, audio, docs).
8. `EmergencyContact`: Emergency contacts directory.
9. `IncidentStatusHistory`: State transition audit log.
10. `IncidentAcknowledgement`: Responders triage receipts.

## 4. RLS & FORCE RLS Strategy
Alembic migration `0019_emergency_incident_management` will enable PostgreSQL RLS and `FORCE RLS` on all 10 tables:
`ALTER TABLE <table_name> ENABLE ROW LEVEL SECURITY;`
`ALTER TABLE <table_name> FORCE ROW LEVEL SECURITY;`
`CREATE POLICY <table_name>_tenant_isolation ON <table_name> USING (society_id = current_setting('app.current_society_id')::uuid);`

## 5. Security & Privacy Model
- **Server-Authoritative Severity**: `LOW`, `MEDIUM`, `HIGH`, `CRITICAL`.
- **Server-Side PII Masking**: PII masking for medical emergencies, domestic incidents, or sensitive resident identity.
- **Idempotency**: All mutation APIs support `X-Idempotency-Key` headers.
- **Financial Isolation**: **0** direct changes to financial ledgers (`JournalEntry`, `Invoice`, `Payment`).

## 6. Implementation Sequence
1. Database Models & Enums (`apps/api/src/incidents/domain/models.py`, `enums.py`)
2. Alembic Migration (`0019_emergency_incident_management.py`)
3. Repositories & Concurrency Advisory Locks (`repositories.py`, `concurrency.py`)
4. State Machines & Privacy Filters (`state_machine.py`, `privacy.py`)
5. Domain Event Hooks & Incident Service (`event_hooks.py`, `incident_service.py`)
6. REST API Endpoints & v1 Router (`apps/api/src/incidents/api/`)
7. RBAC Permission Seeding (`seed_dev_data.py`)
8. Frontend UI (`apps/web/src/app/incidents/page.tsx`)
9. Unit, Security, IDOR, RLS, and Finalization Test Suite
10. Final Architectural Verification & Report
