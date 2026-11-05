# Phase 15 — Facility Booking Security & Isolation Specification

## Security Principles

### 1. Multi-Tenant Isolation
- Every table is associated with a mandatory `society_id` column.
- PostgreSQL Row Level Security (RLS) is enabled and forced (`FORCE ROW LEVEL SECURITY`) on all 8 tables.
- Tenant isolation policies restrict all `SELECT`, `INSERT`, `UPDATE`, and `DELETE` queries to the authenticated session's `app.current_society_id`.

### 2. Fine-Grained Authorization (RBAC)
Canonical permissions:
- `facility.booking.create`: Create facility booking request.
- `facility.booking.view`: View basic booking info.
- `facility.booking.view_own`: View personal booking history.
- `facility.booking.view_all`: View all society bookings.
- `facility.booking.update`: Update draft or pending booking request.
- `facility.booking.approve`: Approve pending booking request.
- `facility.booking.reject`: Reject pending booking request.
- `facility.booking.cancel`: Cancel facility booking.
- `facility.booking.override`: Administrative booking override.
- `facility.booking.manage_rules`: Configure facility booking rules & capacity.
- `facility.booking.manage_availability`: Configure facility operating hours.
- `facility.booking.manage_blackout`: Manage facility blackout periods.
- `facility.booking.checkin`: Perform booking check-in.
- `facility.booking.complete`: Mark booking completed.
- `facility.booking.no_show`: Mark booking no-show.
- `facility.booking.audit.view`: View booking status history and audit trail.

### 3. Financial & Scope Isolation
- Phase 15 does NOT perform direct database writes to Phase 4/5/6 accounting, invoice, ledger, or billing tables.
- Financial charges or deposit fees are handled asynchronously via notification event hooks.
