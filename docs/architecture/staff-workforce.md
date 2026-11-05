# Staff & Workforce Management Architecture

## Overview
Phase 12 introduces a production-grade, multi-tenant **Staff & Workforce Management Foundation** to SocietySphere. It manages internal workforce identities, operational roles, teams, staff status lifecycles, emergency contact privacy, staff documents, and integration with Phase 11 Maintenance Work Orders.

## Architectural Principles
1. **User Identity Integration**: The global `User` model remains the single authentication entity. `StaffProfile` links optionally to `User` via `user_id`. Authentication and login management remain governed by Phase 3 RBAC.
2. **Operational Metadata**: `StaffRole` defines operational duties (e.g. Electrician, Plumber, Supervisor) and is separate from Phase 3 application permissions.
3. **Tenant & RLS Isolation**: All 9 Phase 12 database tables enforce PostgreSQL Row Level Security (RLS) via `app.current_society_id` DB context.
4. **Financial Boundary**: Zero mutations on accounting ledgers or billing records. Payroll and attendance modules are explicitly out of scope.

## Entity Model
- `StaffProfile`: Core workforce profile with `STF-YYYY-XXXXXX` sequence numbering.
- `StaffRole`: Operational roles (Electrician, Plumber, Supervisor, etc.).
- `StaffRoleAssignment`: Historical role assignments.
- `StaffTeam`: Operational staff teams (e.g., Maintenance Team).
- `StaffTeamMembership`: Staff membership in operational teams.
- `StaffContact`: Privacy-controlled contact details and emergency contacts.
- `StaffDocument`: Secure private document storage metadata.
- `StaffStatusHistory`: Immutable audit trail for staff status transitions (`ONBOARDING` -> `ACTIVE` -> `SUSPENDED` / `OFFBOARDED`).
- `StaffAssignmentHistory`: Audit log of work orders assigned to staff.
