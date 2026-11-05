# ADR-019: Complaints & Helpdesk Management Foundation Architecture

## Status
Approved / Implemented (Phase 10)

## Context
SocietySphere requires a multi-tenant, production-grade Complaints & Helpdesk module for apartment societies. The module must allow residents to raise service requests, categorize complaints, track progress via an explicit state machine, communicate via public comments, upload evidence attachments (photos, voice notes, documents), receive SLA calculations, and support resolution/reopening workflows. Helpdesk administrators and staff must be able to assign, adjust priority, add internal staff notes, escalate overdue issues, and resolve complaints while maintaining strict multi-tenant isolation, RBAC security, audit logging, and concurrency protection.

## Decision
1. **Domain & Data Model Isolation**:
   - Established 10 core entities: `ComplaintCategory`, `ComplaintSubcategory`, `ComplaintSLAPolicy`, `Complaint`, `ComplaintAssignment`, `ComplaintComment`, `ComplaintAttachment`, `ComplaintStatusHistory`, `ComplaintEscalation`, `ComplaintResolution`.
   - Every table enforces tenant isolation via mandatory `society_id` foreign keys and PostgreSQL Row-Level Security (`ENABLE ROW LEVEL SECURITY` and `FORCE ROW LEVEL SECURITY`).
   - Integrated with Phase 7 `User`, `Unit`, and `ResidentProfile` without violating previous phase boundaries.

2. **Explicit State Machine**:
   - Defined strict state transitions: `OPEN` -> `ACKNOWLEDGED` -> `ASSIGNED` -> `IN_PROGRESS` -> `WAITING_FOR_RESIDENT` -> `RESOLVED` -> `CLOSED`.
   - Allowed reopening (`RESOLVED`/`CLOSED` -> `REOPENED` -> `IN_PROGRESS`) and cancellation (`OPEN` -> `CANCELLED`).
   - Invalid jumps (e.g., `OPEN` -> `CLOSED`) are rejected at both domain and API layer with `400 Bad Request`.

3. **Concurrency-Safe Human-Readable Complaint Number Generation**:
   - Formatted numbers as `CMP-YYYY-XXXXXX` (e.g. `CMP-2026-000001`).
   - Implemented `pg_advisory_xact_lock` transaction advisory locking to guarantee concurrency-safe sequence generation without duplicates or race conditions.

4. **Comments & RBAC Visibility Filtering**:
   - Separated comments into public (`is_internal=False`) and internal staff notes (`is_internal=True`).
   - Non-admin residents with `complaint.comment` permission see only public comments. Helpdesk staff with `complaint.comment_internal` see all comments.

5. **SLA Calculation & Escalation Foundation**:
   - Configurable per-society SLA policies by priority (`CRITICAL`, `HIGH`, `MEDIUM`, `LOW`).
   - Automatically computes `response_due_at` and `resolution_due_at` upon creation and priority update.
   - Escalation tracking records escalation levels and reason logs.

6. **Evidence Attachment & Soft Archival**:
   - Supports `PHOTO`, `VIDEO`, `AUDIO`, `DOCUMENT`, `OTHER` attachments linked to object storage file keys.
   - Deletions perform soft archival (`is_archived=True`, `archived_at=now()`) for audit compliance.

7. **Financial Isolation**:
   - Zero journal entries, ledger transactions, or billing alterations are executed by the complaints module.

## Consequences
- Complete tenant data isolation under PostgreSQL Row-Level Security (`app.current_society_id`).
- Immutability of status history and comment logs.
- Extensible foundation for future vendor work orders, staff management, or automated notifications in future phases.
