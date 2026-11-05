# Phase 16 — Announcements Security & Isolation Specification

## Security Principles

### 1. Multi-Tenant Isolation (RLS + FORCE RLS)
- All 8 tables contain mandatory `society_id` foreign keys.
- PostgreSQL Row Level Security (RLS) is enabled and forced (`FORCE ROW LEVEL SECURITY`) on all 8 tables.
- Tenant isolation policies restrict `SELECT`, `INSERT`, `UPDATE`, `DELETE` queries to `app.current_society_id`.

### 2. Fine-Grained Authorization (RBAC)
Canonical permissions:
- `announcement.create`: Create draft announcement.
- `announcement.view`: View announcements targeted to user.
- `announcement.view_own`: View personal announcement drafts.
- `announcement.view_all`: View all society announcements.
- `announcement.update`: Update draft or pending announcement.
- `announcement.submit`: Submit announcement for review.
- `announcement.review`: Review pending announcement.
- `announcement.approve`: Approve pending announcement.
- `announcement.reject`: Reject pending announcement.
- `announcement.publish`: Publish approved announcement.
- `announcement.schedule`: Schedule future publication.
- `announcement.archive`: Archive announcement.
- `announcement.expire`: Manually expire announcement.
- `announcement.audience.manage`: Manage audience rules.
- `announcement.attachment.manage`: Manage attachment metadata.
- `announcement.acknowledgement.view`: View acknowledgement metrics.
- `announcement.read_receipt.view`: View read receipt metrics.
- `announcement.audit.view`: View announcement audit trail.

### 3. Audience Security & IDOR Protection
- `AnnouncementAudienceResolver` verifies all target blocks, floors, units, and users belong to the authenticated session's `society_id`.
- Cross-tenant audience selection attempts return `CrossTenantAudienceError` (HTTP 400).
- Unassigned or cross-tenant announcement detail requests return `AnnouncementNotFoundError` (HTTP 404).

### 4. Mandatory Acknowledgement Versioning
- Material edits to published mandatory announcements create `AnnouncementVersion` snapshots and increment `version_number`.
- Residents must explicitly acknowledge the updated `version_number`.
