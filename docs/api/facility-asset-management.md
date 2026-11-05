# Phase 14 — Facility & Asset Management API Reference

## Endpoints Summary

### Facilities
- `POST /api/v1/facility-asset/facilities` - Register new physical facility (`facility.create`)
- `GET /api/v1/facility-asset/facilities` - List facilities with filters (`facility.view`)
- `GET /api/v1/facility-asset/facilities/{facility_id}` - Get facility details (`facility.view`)
- `PATCH /api/v1/facility-asset/facilities/{facility_id}` - Update facility (`facility.update`)
- `POST /api/v1/facility-asset/facilities/{facility_id}/status` - Transition status (`facility.status.manage`)
- `POST /api/v1/facility-asset/facilities/{facility_id}/areas` - Add sub-area (`facility.area.manage`)
- `POST /api/v1/facility-asset/facilities/{facility_id}/documents` - Upload document (`facility.document.manage`)
- `GET /api/v1/facility-asset/facilities/{facility_id}/documents` - List documents (`facility.document.view`)
- `GET /api/v1/facility-asset/facilities/{facility_id}/maintenance-links` - List maintenance links (`facility.view`)

### Asset Categories
- `POST /api/v1/facility-asset/asset-categories` - Create asset category (`asset.category.manage`)
- `GET /api/v1/facility-asset/asset-categories` - List categories (`asset.view`)

### Assets
- `POST /api/v1/facility-asset/assets` - Register asset (`asset.create`)
- `GET /api/v1/facility-asset/assets` - List assets with filters (`asset.view`)
- `GET /api/v1/facility-asset/assets/{asset_id}` - Get asset details (`asset.view`)
- `PATCH /api/v1/facility-asset/assets/{asset_id}` - Update asset (`asset.update`)
- `POST /api/v1/facility-asset/assets/{asset_id}/status` - Transition asset status (`asset.status.manage`)
- `POST /api/v1/facility-asset/assets/{asset_id}/location` - Move asset location (`asset.location.manage`)
- `GET /api/v1/facility-asset/assets/{asset_id}/locations` - Get location history (`asset.audit.view`)
- `POST /api/v1/facility-asset/assets/{asset_id}/assignments` - Assign asset (`asset.assignment.manage`)
- `GET /api/v1/facility-asset/assets/{asset_id}/assignments` - Get assignment history (`asset.audit.view`)
- `GET /api/v1/facility-asset/assets/{asset_id}/status-history` - Get status history (`asset.audit.view`)
- `POST /api/v1/facility-asset/assets/{asset_id}/documents` - Upload document (`asset.document.manage`)
- `GET /api/v1/facility-asset/assets/{asset_id}/documents` - List documents (`asset.document.view`)
- `POST /api/v1/facility-asset/assets/{asset_id}/maintenance-links` - Link work order (`asset.maintenance.link`)
- `GET /api/v1/facility-asset/assets/{asset_id}/maintenance-links` - List maintenance links (`asset.view`)
