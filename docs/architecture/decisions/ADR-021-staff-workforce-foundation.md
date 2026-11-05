# ADR-021: Staff & Workforce Management Foundation Architecture

## Status
Approved

## Context
SocietySphere requires a production-grade Staff & Workforce Management Foundation to manage internal society operational personnel, teams, roles, status lifecycles, and privacy-controlled contact information. It integrates with Phase 11 Maintenance Work Orders without introducing prematurely built HRMS, Payroll, or Vendor Management modules.

## Decisions
1. **Identity Integration**: Maintain the global `User` entity for authentication. `StaffProfile` links optionally to `User` via `user_id`.
2. **Operational Roles**: Separate `StaffRole` (operational title like Electrician) from Phase 3 application RBAC permissions.
3. **Tenant Isolation & Security**: Apply PostgreSQL Row Level Security (`ENABLE` and `FORCE`) across all 9 Phase 12 database tables using `app.current_society_id`.
4. **Staff Code Concurrency**: Generate sequential staff codes in `STF-YYYY-XXXXXX` format under transaction-scoped PostgreSQL advisory locks (`pg_advisory_xact_lock`) on `(society_id, year)`.
5. **Work Order Integration**: Integrate `StaffProfile` with Phase 11 `WorkOrderAssignment` and `MaintenanceAssignmentTarget` abstraction. Assigning work orders requires `ACTIVE` staff status.
6. **Financial Boundary**: Zero mutations on accounting ledgers or billing records. Defer payroll and attendance.

## Consequences
- Clean separation between operational staff management, application authentication, and financial accounting.
- Strict multi-tenant isolation and Privacy-aware PII protection.
