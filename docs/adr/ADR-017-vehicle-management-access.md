# ADR-017: Vehicle Management, Registration Normalization, and Access Hardware Provider Abstraction

## Status
Accepted

## Context
Apartment societies manage resident vehicles for parking allocation, security identification, and gate access.
However, vehicle registration numbers are subject to varying human entry formats (e.g., spaces, dashes, dots, uppercase/lowercase), which can lead to accidental duplicates or missed lookups at gate entrypoints.
Furthermore, modern societies are transitioning from manual security guard barrier logging to RFID tags (FastTag) and Automatic Number Plate Recognition (ANPR) cameras.

To ensure long-term stability and prevent premature coupling to specific hardware vendors, SocietySphere requires:
1. Deterministic normalization of vehicle registration numbers.
2. Tenant-scoped uniqueness of active vehicles.
3. Separation of legal vehicle ownership from resident/unit authorization links.
4. Support for EV attributes (charging requirement, battery capacity) without introducing charging transaction billing prematurely.
5. Hardware provider abstraction isolating manual gate operations from future RFID and ANPR camera protocols.
6. Immutable audit logs for vehicle entry/exit access events.

## Decision

### 1. Deterministic Plate Normalization
- All vehicle registration numbers are stripped of non-alphanumeric characters and uppercased upon input and stored in `normalized_registration_number`.
  - Example: `"mh-02 ab 1234"` $\to$ `"MH02AB1234"`.
- A PostgreSQL partial unique index `uq_vehicles_society_active_normalized_reg` enforces uniqueness of `normalized_registration_number` per `society_id` where `status = 'ACTIVE'`.
- Deactivated vehicles (`INACTIVE`, `SOLD`, `TRANSFERRED`, `SCRAPPED`) do not block future registrations of the plate.

### 2. Decoupled Vehicle-Resident Association
- Vehicles are not tied directly to a single resident or unit. Instead, the `VehicleResidentAssociation` entity links a vehicle to a resident user and unit with:
  - Association type: `OWNER`, `TENANT`, `RESIDENT`, `AUTHORIZED_DELEGATE`.
  - Primary vehicle designation: `is_primary` scoped to `(unit_id, user_id)`.
  - Setting `is_primary = True` automatically demotes any previously active primary association for that specific user and unit.

### 3. Provider Abstraction for Gate Access Hardware
- Introduced `VehicleAccessProvider` protocol with three implementations:
  1. `ManualVehicleAccessProvider`: Standard operator/guard entry.
  2. `RFIDVehicleAccessProvider` (stub): Prepares for RFID tag / FastTag readers.
  3. `ANPRVehicleAccessProvider` (stub): Prepares for OCR ANPR camera feeds with confidence scoring and frame snapshot references.
- All gate events append immutable `VehicleAccessRecord` entries. Records cannot be edited or deleted.

### 4. EV Vehicle Readiness
- First-class support for `is_ev`, `fuel_type`, `battery_capacity_kwh`, and `charging_required` on the vehicle record.
- Strict boundary: EV charging session metering and billing are deferred to future phases.

### 5. Multi-Tenancy & Row-Level Security (RLS)
- All 6 vehicle tables (`vehicles`, `vehicle_resident_associations`, `vehicle_verifications`, `vehicle_documents`, `vehicle_parking_associations`, `vehicle_access_records`) enforce PostgreSQL RLS:
  - `ENABLE ROW LEVEL SECURITY`
  - `FORCE ROW LEVEL SECURITY`
  - Policy with matching `USING` and `WITH CHECK` clauses keyed to `app.current_society_id`.

## Consequences
- **Positive**:
  - Plate lookups at security gates are 100% deterministic regardless of space/hyphen formatting.
  - Hardware integrations can be slotted in via provider adapters without altering database schemas or business services.
  - Complete historical audit trail of vehicle entry/exit events.
  - Multi-tenant data isolation is mathematically enforced at the database level.
- **Negative / Trade-offs**:
  - Plate re-registration requires explicitly deactivating the prior vehicle record.
