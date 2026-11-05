# Phase 17 — Events & Community Management Security Architecture

## Multi-Tenant Row-Level Security (RLS)

All 8 Phase 17 tables (`events`, `event_participants`, `event_registrations`, `event_approvals`, `event_schedules`, `event_attendances`, `event_attachments`, `event_status_histories`) enforce PostgreSQL `ENABLE RLS` and `FORCE RLS`.

### Policy Specification
```sql
CREATE POLICY <table_name>_tenant_isolation ON <table_name>
USING (society_id = NULLIF(current_setting('app.current_society_id', true), '')::uuid);
```

---

## Canonical RBAC Permissions

| Permission Code | Name | Scope / Role |
|---|---|---|
| `event.create` | Create Event Draft | Resident / Admin |
| `event.view` | View Eligible Events | All Residents |
| `event.view_all` | View All Events | Staff / Admin |
| `event.update` | Update Event Draft | Organizer / Admin |
| `event.submit` | Submit Event for Approval | Organizer |
| `event.review` | Review Event Request | Committee / Admin |
| `event.approve` | Approve Event | Committee / Admin |
| `event.publish` | Publish Event | Admin |
| `event.schedule` | Schedule Event | Admin |
| `event.cancel` | Cancel Event | Admin |
| `event.archive` | Archive Event | Admin |
| `event.participant.view` | View Unmasked Participants | Admin |
| `event.participant.manage` | Manage Event Participants | Admin |
| `event.registration.view` | View Registrations | Resident (own) / Admin (all) |
| `event.registration.manage` | Manage Registrations | Admin |
| `event.attendance.view` | View Attendance | Admin |
| `event.attendance.manage` | Record Attendance | Security / Staff / Admin |
| `event.facility.manage` | Manage Facility Booking | Admin |
| `event.attachment.manage` | Manage Attachments | Organizer / Admin |
| `event.audit.view` | View Audit History | Admin |

---

## Participant Privacy & Masking

Normal residents without `event.participant.view` or `event.participant.manage` permissions cannot view full unmasked participant lists. `EventParticipantPrivacyFilter` masks user names and unit numbers for non-admin viewers while presenting total registration metrics.

---

## Attachment Security & Path Traversal Prevention

1. **Storage Key Format**: `events/{society_id}/{event_id}/{file_size}_{file_name}`
2. **Sanitization**: Path separators (`/`, `\`) and directory traversal sequences (`..`) are stripped.
3. **MIME / Size Restrictions**: Max file size = 10 MB. Allowed MIME types include images (`image/jpeg`, `image/png`) and document PDFs (`application/pdf`).

---

## Financial Isolation Invariants

Zero direct mutations allowed on `JournalEntry`, `JournalEntryLine`, `Invoice`, `Payment`, `Receipt`, `FinancialPeriod`, or `ReconciliationSession`. Paid events are explicitly OUT OF SCOPE.
