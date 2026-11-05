# ADR-028: Phase 19 Emergency & Incident Management Architecture

## Status
Proposed (Pre-Implementation Architecture Blueprint)

## Context
Apartment societies require immediate, high-priority emergency reporting, triage, responder dispatch, escalation, and auditability. The emergency domain must operate with high availability and concurrency safety while protecting resident privacy and maintaining strict tenant isolation.

## Decision Drivers
1. **Domain Boundary Integrity**: Emergency Incident is NOT a Complaint, WorkOrder, Visitor, or Governance entity. It requires its own dedicated operational boundary.
2. **Reuse Existing Master Data**: Do not duplicate spatial hierarchy (Block, Floor, Unit, Facility) or personnel entities (Staff, Vendor, CommitteeMember).
3. **Server-Authoritative Control**: Severity, lifecycle state transitions, and privacy masking are server-authoritative. AI suggestions remain strictly advisory.
4. **Financial Isolation**: 0 direct financial mutations. Emergency expenditures cross domain boundaries via domain events (`INCIDENT_ACTION_COMPLETED`).
5. **Accessibility & i18n**: Support Easy Mode for high-stress situations with Tamil (`ta`) and English (`en`) UI dictionaries.

## Architectural Decisions
1. **Normalized Entity Structure**: 10 normalized entities with PostgreSQL RLS + `FORCE RLS` enabled in Alembic migration `0019_emergency_incident_management`.
2. **Advisory Locking**: Use `acquire_incident_number_lock` for sequential `INC-YYYY-XXXXXX` numbering and `acquire_incident_triage_lock` for concurrent response management.
3. **Operational Timeline Separation**: Separate `IncidentTimeline` (operational log for responders) from system `AuditLog` (security audit).
4. **Maker-Checker & Override Safety**: Narrowly scoped administrative emergency override requiring mandatory log reason and explicit `incident.override` permission.

## Consequences
- Guaranteed multi-tenant isolation and security compliance.
- Fast, low-friction emergency reporting for residents under stress.
- Full architectural compatibility with locked Phases 1–18.
