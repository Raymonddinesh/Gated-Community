# Phase 14 — Facility & Asset Management Foundation

## Architecture Overview

The Facility & Asset Management module provides physical infrastructure and asset lifecycle tracking for SocietySphere enterprise SaaS. It manages physical facilities, sub-areas, asset taxonomy, physical locations, status histories, assignments, operational documents, and links to Phase 11 Maintenance Work Orders and Phase 10 Complaints.

## Key Entities
1. **Facility**: Physical amenities and infrastructure (`FAC-YYYY-XXXXXX`).
2. **FacilityArea**: Sub-areas within facilities (e.g. Badminton Court 1 in Clubhouse).
3. **AssetCategory**: Hierarchical asset taxonomy with criticality flags.
4. **Asset**: Physical equipment and machinery (`AST-YYYY-XXXXXX`).
5. **AssetLocation**: Historical log of physical asset movement across facilities/areas.
6. **AssetStatusHistory**: Immutable status change audit log (`IN_SERVICE`, `UNDER_MAINTENANCE`, `OUT_OF_SERVICE`, `DECOMMISSIONED`, `DISPOSED`).
7. **AssetAssignmentHistory**: Historical assignments to staff, vendor, department, or location.
8. **AssetDocument**: Operational manuals, warranties, and purchase invoices.
9. **FacilityDocument**: Layout plans, permits, and compliance certificates.
10. **AssetMaintenanceLink**: Links facilities/assets to Phase 11 Maintenance Work Orders and Phase 10 Complaints.

## Security & Tenant Isolation
- **Row Level Security (RLS)**: PostgreSQL RLS and `FORCE RLS` enabled on all 10 tables.
- **Tenant Scope**: Strict `society_id` filtering enforced across all queries and API endpoints.
- **RBAC Enforcement**: Fine-grained `facility.*` (9) and `asset.*` (12) permissions.

## Financial & Work Order Scope Boundaries
- Zero direct mutation on financial tables (`Invoice`, `Payment`, `JournalEntry`, `ChartOfAccounts`).
- Asset maintenance link integrates with Phase 11 `MaintenanceWorkOrder` without modifying Phase 11 tables or duplicating work order lifecycles.
