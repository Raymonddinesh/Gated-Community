# Phase 14 — Facility & Asset Management Security Model

## Overview

Security in Phase 14 enforces multi-tenant isolation, advisory lock concurrency protection, fine-grained RBAC, and strict non-mutation of financial records.

## Row-Level Security (RLS)
PostgreSQL RLS policies are applied with `ENABLE ROW LEVEL SECURITY` and `FORCE ROW LEVEL SECURITY` across all 10 Phase 14 tables:
- `facilities`
- `facility_areas`
- `asset_categories`
- `assets`
- `asset_locations`
- `asset_status_history`
- `asset_assignment_history`
- `asset_documents`
- `asset_maintenance_links`
- `facility_documents`

Policy definition:
```sql
CREATE POLICY {table}_tenant_isolation ON {table}
USING (society_id = NULLIF(current_setting('app.current_society_id', true), '')::uuid);
```

## Canonical Permissions
- **Facility**: `facility.create`, `facility.view`, `facility.update`, `facility.status.manage`, `facility.area.manage`, `facility.document.manage`, `facility.document.view`, `facility.audit.view`, `facility.archive`.
- **Asset**: `asset.create`, `asset.view`, `asset.update`, `asset.status.manage`, `asset.category.manage`, `asset.location.manage`, `asset.assignment.manage`, `asset.document.manage`, `asset.document.view`, `asset.maintenance.link`, `asset.audit.view`, `asset.archive`.

## Concurrency Protection
Unique sequential codes (`FAC-YYYY-XXXXXX` and `AST-YYYY-XXXXXX`) are generated using PostgreSQL transactional advisory locks (`pg_advisory_xact_lock`) with fallback for SQLite tests.
