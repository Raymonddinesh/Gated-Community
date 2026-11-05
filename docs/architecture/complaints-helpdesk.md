# Phase 10 — Complaints & Helpdesk Management Architecture Specification

## 1. Overview
The Complaints & Helpdesk Management module provides a tenant-isolated, production-grade service request and issue tracking framework for apartment societies in SocietySphere. It enables residents to lodge complaints, upload evidence attachments (photos, voice notes, documents), communicate with helpdesk staff via comments, track status transitions, and request reopenings. Helpdesk administrators can manage categories, SLA policies, assign tickets to staff, update priorities, escalate delayed issues, and record resolutions.

## 2. Core Entities & Schema Blueprint
The domain consists of 10 primary entities, each scoped to a single society via mandatory `society_id`:

1. **`ComplaintCategory`**: Society-scoped complaint categories (e.g., Plumbing, Electrical, Security, General Maintenance).
2. **`ComplaintSubcategory`**: Fine-grained subcategories with default priority levels.
3. **`ComplaintSLAPolicy`**: Response, resolution, and escalation time targets configured per priority (`CRITICAL`, `HIGH`, `MEDIUM`, `LOW`).
4. **`Complaint`**: Central ticket aggregate storing complaint details, status, priority, unit link, resident link, SLA due dates, resolution details, and escalation state.
5. **`ComplaintAssignment`**: Staff/Helpdesk assignment history log.
6. **`ComplaintComment`**: Discussion thread supporting public comments and internal staff notes.
7. **`ComplaintAttachment`**: Evidence photo, video, audio, or document metadata with soft-archival support.
8. **`ComplaintStatusHistory`**: Immutable log of all status transitions, timestamps, actors, and reasons.
9. **`ComplaintEscalation`**: Log of ticket escalations with level, target assignee, and reason.
10. **`ComplaintResolution`**: Detailed resolution summary, category, and confirmation state.

## 3. State Machine & Transitions
Complaints follow an explicit state lifecycle:

- `OPEN` -> Initial state upon creation.
- `ACKNOWLEDGED` -> Ticket received by helpdesk team.
- `ASSIGNED` -> Assigned to a staff member or vendor.
- `IN_PROGRESS` -> Maintenance work in progress.
- `WAITING_FOR_RESIDENT` -> Waiting for resident clarification or access.
- `RESOLVED` -> Work completed and marked resolved by staff.
- `CLOSED` -> Formally closed after confirmation.
- `REOPENED` -> Reopened by resident/admin if issue recurs (`RESOLVED`/`CLOSED` -> `REOPENED`).
- `CANCELLED` -> Withdrawn by resident or admin (`OPEN` -> `CANCELLED`).

Invalid state transitions (e.g. `OPEN` -> `CLOSED` or `RESOLVED` -> `ASSIGNED`) raise `InvalidComplaintStatusTransitionError` and return `400 Bad Request`.

## 4. Security & Tenant Isolation
- **Row-Level Security (RLS)**: Alembic migration `20261003_0010_complaints_helpdesk.py` applies `ENABLE ROW LEVEL SECURITY` and `FORCE ROW LEVEL SECURITY` across all 10 tables, filtering rows by `app.current_society_id`.
- **Granular RBAC Permissions**:
  - `complaint.create`, `complaint.view_own`, `complaint.view_all`, `complaint.comment`, `complaint.comment_internal`, `complaint.assign`, `complaint.priority.manage`, `complaint.status.manage`, `complaint.sla.manage`, `complaint.escalate`, `complaint.resolve`, `complaint.close`, `complaint.reopen`, `complaint.cancel`, `complaint.category.manage`, `complaint.attachment.manage`, `complaint.audit.view`.
- **Comment Visibility**: Residents see public comments only (`is_internal=False`). Internal notes (`is_internal=True`) require `complaint.comment_internal` permission.

## 5. Concurrency Protection
- **Human-Readable Complaint Numbering**: Uses transaction advisory locking (`pg_advisory_xact_lock`) based on `society_id` hash to sequentially generate format `CMP-YYYY-000001` without race conditions or sequence gaps under concurrent requests.

## 6. Financial & Domain Boundaries
- **Financial Isolation**: The Complaints module does NOT modify chart of accounts, post journal entries, or issue invoices/receipts.
- **Cross-Domain Integration**: Links safely to `Unit`, `User`, `ResidentProfile`, `Vehicle`, or `Visitor` records via FK and domain references without crossing society boundaries.
