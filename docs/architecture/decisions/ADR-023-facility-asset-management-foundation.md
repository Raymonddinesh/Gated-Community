# ADR-023: Facility & Asset Management Foundation

## Status
Accepted

## Context
SocietySphere required physical infrastructure, amenity, and asset lifecycle tracking. Assets and facilities must be tenant-isolated, integrated with Phase 11 Maintenance Work Orders and Phase 10 Complaints, while strictly avoiding procurement/depreciation/HR engines or financial table mutations.

## Decision
1. Implement 10 database entities: `Facility`, `FacilityArea`, `AssetCategory`, `Asset`, `AssetLocation`, `AssetStatusHistory`, `AssetAssignmentHistory`, `AssetDocument`, `FacilityDocument`, `AssetMaintenanceLink`.
2. Apply PostgreSQL Row Level Security (RLS) + `FORCE RLS` on all 10 tables.
3. Use transactional advisory locks (`pg_advisory_xact_lock`) for generating `FAC-YYYY-XXXXXX` and `AST-YYYY-XXXXXX` codes.
4. Integrate with Phase 11 work orders via `AssetMaintenanceLink` without modifying Phase 11 tables or creating duplicate work order lifecycles.
5. Provide Easy, Standard, and Admin view modes with English and Tamil localization support in frontend UI.

## Consequences
- Maintains absolute financial isolation and zero mutations on accounting ledgers.
- Provides robust asset history tracking and tenant-isolated operations.
