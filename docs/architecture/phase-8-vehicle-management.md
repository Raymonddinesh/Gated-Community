# Phase 8 — Vehicle Management & Vehicle Access Foundation

## 1. Executive Summary
Phase 8 delivers the multi-tenant vehicle registry and gate access foundation for SocietySphere.
It bridges residents, parking slots, and security gates through normalized plate storage, decoupled occupancy-linked associations, audited verifications, document management, and hardware provider abstractions (Manual, RFID, ANPR).

---

## 2. Domain Entities & Database Schema

### 2.1 `vehicles`
- `id`: UUID (Primary Key)
- `society_id`: UUID (Foreign Key $\to$ `societies.id`)
- `registration_number`: Original entered string (e.g., `"MH 02 EV 1001"`)
- `normalized_registration_number`: Uppercase alphanumeric string (e.g., `"MH02EV1001"`)
- `vehicle_type`: `FOUR_WHEELER`, `THREE_WHEELER`, `TWO_WHEELER`, `BICYCLE`
- `make`, `model`, `variant`, `color`: Vehicle specifications
- `fuel_type`: `PETROL`, `DIESEL`, `CNG`, `ELECTRIC`, `HYBRID`, `OTHER`, `NOT_APPLICABLE`
- `is_ev`: Boolean flag
- `battery_capacity_kwh`: Decimal(6, 2)
- `charging_required`: Boolean flag
- `status`: `ACTIVE`, `INACTIVE`, `SOLD`, `TRANSFERRED`, `SCRAPPED`
- `verification_status`: `PENDING`, `VERIFIED`, `REJECTED`, `EXPIRED`
- Partial unique index: `uq_vehicles_society_active_normalized_reg` on `(society_id, normalized_registration_number)` WHERE `status = 'ACTIVE'`.

### 2.2 `vehicle_resident_associations`
- `id`: UUID
- `society_id`: UUID
- `vehicle_id`: UUID (Foreign Key $\to$ `vehicles.id`)
- `user_id`: UUID (Foreign Key $\to$ `users.id`)
- `unit_id`: UUID (Foreign Key $\to$ `units.id`)
- `association_type`: `OWNER`, `TENANT`, `RESIDENT`, `AUTHORIZED_DELEGATE`
- `is_primary`: Boolean (scoped to `(unit_id, user_id)`)
- `valid_from`, `valid_to`: Date range
- `status`: `ACTIVE`, `ENDED`, `REVOKED`

### 2.3 `vehicle_verifications`
- `id`: UUID
- `society_id`: UUID
- `vehicle_id`: UUID
- `verifier_user_id`: UUID
- `verification_status`: `VERIFIED`, `REJECTED`, `EXPIRED`
- `verification_date`: Date
- `reason`, `supporting_document_ref`, `notes`: Audit context

### 2.4 `vehicle_documents`
- `id`: UUID
- `society_id`: UUID
- `vehicle_id`: UUID
- `document_type`: `RC`, `INSURANCE`, `PUC`, `PERMIT`, `OTHER`
- `document_number`, `file_key`, `file_name`, `file_size_bytes`, `content_type`
- `valid_from`, `valid_to`

### 2.5 `vehicle_parking_associations`
- `id`: UUID
- `society_id`: UUID
- `vehicle_id`: UUID
- `parking_slot_number`: String (e.g. `"P-101"`)
- `valid_from`, `valid_to`
- `status`: `ACTIVE`, `ENDED`

### 2.6 `vehicle_access_records`
- `id`: UUID
- `society_id`: UUID
- `vehicle_id`: Nullable UUID (matched to active vehicle if registered)
- `registration_number_snapshot`: String
- `normalized_registration_number_snapshot`: String
- `access_type`: `ENTRY`, `EXIT`
- `gate_identifier`: String (e.g. `"GATE-MAIN-01"`)
- `access_time`: DateTime (UTC)
- `detection_method`: `MANUAL`, `RFID`, `ANPR`
- `captured_image_ref`: Nullable String
- `operator_user_id`: Nullable UUID
- `source_provider`: `MANUAL`, `RFID_STUB`, `ANPR_STUB`
- `confidence_score`: Nullable Decimal(4, 3)
- Append-only immutability enforced.

---

## 3. Hardware & Protocol Provider Abstraction

```
                +---------------------------------------+
                |         VehicleAccessProvider         |
                +---------------------------------------+
                                    |
           +------------------------+------------------------+
           |                        |                        |
+---------------------+  +---------------------+  +---------------------+
| ManualAccessProvider|  |   RFIDAccessProvider|  |   ANPRAccessProvider|
|   (Security Guard)  |  |      (FastTag)      |  |     (Camera OCR)    |
+---------------------+  +---------------------+  +---------------------+
           |                        |                        |
           +------------------------+------------------------+
                                    |
                     +-----------------------------+
                     |    VehicleDetectionResult   |
                     +-----------------------------+
                                    |
                     +-----------------------------+
                     |     VehicleAccessRecord     |
                     |   (Immutable Gate Log)      |
                     +-----------------------------+
```

---

## 4. Granular RBAC Permissions
| Permission Code | Name | Description | Default Roles |
|---|---|---|---|
| `vehicle.view` | View Vehicle | View registered vehicles and access logs | All roles |
| `vehicle.create` | Register Vehicle | Register new vehicle in society | Super Admin, Admin, Secretary, Resident, Tenant |
| `vehicle.update` | Update Vehicle | Modify specs, color, or associations | Super Admin, Admin, Secretary, Resident, Tenant |
| `vehicle.verify` | Verify Vehicle | Approve/reject verification audit | Super Admin, Admin, Secretary |
| `vehicle.deactivate` | Deactivate Vehicle | Mark as Inactive, Sold, Scrapped | Super Admin, Admin, Secretary |
| `vehicle.document.view` | View Documents | View RC, Insurance, PUC records | All roles except Security |
| `vehicle.document.manage`| Manage Documents | Upload and remove documents | Super Admin, Admin, Secretary, Resident, Tenant |
| `vehicle.access.view` | View Access Logs | View gate entry/exit logs | Super Admin, Admin, Secretary, Treasurer, Committee, Security |
| `vehicle.access.record` | Record Gate Access | Record gate movement events | Super Admin, Admin, Secretary, Security |

---

## 5. Row-Level Security (RLS)
Every table is locked down with PostgreSQL RLS:
```sql
ALTER TABLE vehicles ENABLE ROW LEVEL SECURITY;
ALTER TABLE vehicles FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation_vehicles ON vehicles
  FOR ALL
  USING (society_id = NULLIF(current_setting('app.current_society_id', true), '')::uuid)
  WITH CHECK (society_id = NULLIF(current_setting('app.current_society_id', true), '')::uuid);
```
Applied identically across all 6 Phase 8 tables in Alembic migration `0008_vehicle_management`.
