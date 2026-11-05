# ADR-020: Maintenance & Work Order Management Foundation Architecture

## Status
Approved

## Context
SocietySphere requires a production-grade Maintenance & Work Order Management module that integrates with Phase 10 Complaints & Helpdesk while establishing clean abstractions for future Staff Management (Phase 12+) and Vendor Management (Phase 13+). Financial ledger mutations, inventory stock deductions, and premature staff/vendor table creation must be strictly avoided.

## Decisions
1. **Tenant Isolation & Security**: Apply PostgreSQL Row Level Security (`ENABLE` and `FORCE`) across all 12 Phase 11 tables using `app.current_society_id`.
2. **Work Order Number Concurrency**: Generate sequential numbers in `WO-YYYY-XXXXXX` format under transaction-scoped PostgreSQL advisory locks (`pg_advisory_xact_lock`) on `(society_id, year)`.
3. **State Machine**: Enforce strict server-side state machine governing transitions across 13 statuses: DRAFT, OPEN, ASSIGNED, SCHEDULED, IN_PROGRESS, ON_HOLD, WAITING_FOR_PARTS, WAITING_FOR_RESIDENT, COMPLETED, VERIFIED, CLOSED, REOPENED, CANCELLED.
4. **Complaint Synchronization**: Allow work orders to reference Phase 10 complaints (`complaint_id`). Synchronize resolution state cleanly using `ComplaintService` application boundaries.
5. **Operational Material Usage**: Maintain material usage tracking (`work_order_material_usages`) as operational records with Decimal precision. Defer all financial postings and accounting ledger mutations.
6. **Future Assignment Target Abstraction**: Implement `MaintenanceAssignmentTarget` abstraction for INTERNAL_USER, TEAM, STAFF, and VENDOR targets without introducing unbuilt tables.

## Consequences
- Clean separation between operational maintenance tracking and financial accounting.
- Zero cross-tenant data leakage.
- Full auditability across status transitions, comments, attachments, assignments, and resolution verifications.
