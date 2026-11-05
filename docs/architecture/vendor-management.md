# Vendor & Service Provider Management Architecture

## Overview
Phase 13 establishes the production-grade foundation for external vendor and service provider management in SocietySphere.

## Architectural Boundaries & Principles
1. **Multi-Tenant RLS Guarantee**: All 9 vendor tables carry `society_id` and have PostgreSQL `ENABLE ROW LEVEL SECURITY` and `FORCE ROW LEVEL SECURITY` with tenant isolation policies using `app.current_society_id`.
2. **Work Order Integration**: Integrates directly with Phase 11 `WorkOrderAssignmentService` for `assignment_type == VENDOR`. Only vendors with `ACTIVE` vendor profiles and active society associations can receive work assignments.
3. **No Financial Mutations**: Zero mutations on `Invoice`, `Payment`, `Receipt`, or `JournalEntry`. Accounting integration remains isolated for future procurement/payable modules.
4. **Audit Logging & State Machine**: Vendor status transitions are governed by strict state machine rules (`ONBOARDING` -> `ACTIVE` -> `INACTIVE`/`SUSPENDED`/`BLACKLISTED` -> `OFFBOARDED`) with immutable history stored in `vendor_status_histories`.

## Data Model
- `VendorCategory`: Society-configurable service categories (e.g. Electrical, Plumbing, Lifts).
- `VendorProfile`: Core profile with generated `VND-YYYY-XXXXXX` lock-protected sequential vendor codes.
- `VendorSocietyAssociation`: Tenant-association table linking vendors to societies.
- `VendorContact`: Multi-contact person entries per vendor.
- `VendorAddress`: Multi-address entries per vendor.
- `VendorService`: Catalog of services offered by vendor.
- `VendorDocument`: Compliance, insurance, and registration documents.
- `VendorStatusHistory`: Immutable audit log for status transitions.
- `VendorAssignmentHistory`: Immutable record of work orders assigned to vendors.
