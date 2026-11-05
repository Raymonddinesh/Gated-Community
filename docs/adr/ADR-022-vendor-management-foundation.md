# ADR-022: Vendor & Service Provider Management Foundation Architecture

## Context
SocietySphere requires a production-grade external vendor management system to track AMC contractors, lift/STP service providers, and maintenance agencies without compromising tenant isolation, RBAC, or financial integrity.

## Decision
1. **Model Scope**: Implement 9 dedicated database tables under `app.current_society_id` RLS: `vendor_categories`, `vendor_profiles`, `vendor_society_associations`, `vendor_contacts`, `vendor_addresses`, `vendor_services`, `vendor_documents`, `vendor_status_histories`, and `vendor_assignment_histories`.
2. **Concurrency Control**: Use PostgreSQL transaction advisory locks (`pg_advisory_xact_lock`) to generate formatted, collision-free `VND-YYYY-XXXXXX` vendor codes per society.
3. **Status Governance**: Mandate state machine transitions (`ONBOARDING` -> `ACTIVE` -> `INACTIVE`/`SUSPENDED`/`BLACKLISTED` -> `OFFBOARDED`) with compulsory audit log recording in `vendor_status_histories`.
4. **Maintenance Integration**: Extend Phase 11 `WorkOrderAssignmentService` to validate `WorkOrderAssignmentType.VENDOR` assignments against active vendor profiles and record `VendorAssignmentHistory`.

## Status
Accepted.
