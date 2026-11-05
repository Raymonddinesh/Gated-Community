# ADR 008: Extensibility for Deferred Vehicle Management & Gate IoT

## Status
Accepted

## Context
The immediate product scope excludes resident vehicle management (4-wheelers, 3-wheelers, 2-wheelers, bicycles, parking slot allocation, ANPR, RFID, automatic barrier gates, vehicle entry/exit history, and EV charging integration). 
However, as a production SaaS platform, the core architecture must guarantee that these capabilities can be plugged in later without major refactoring or database schema redesign.

## Decision
1. **Domain Abstraction in Security/Gate Module**:
   - The gate entry domain is decoupled from human vs vehicle discrimination via an abstract `EntrySubject` pattern:
     ```typescript
     export interface EntrySubject {
       subjectType: 'VISITOR_PEDESTRIAN' | 'VISITOR_CAB' | 'DELIVERY' | 'SERVICE_STAFF' | 'RESIDENT_VEHICLE' (future);
       referenceId: string;
       identifier: string; // Phone number or future License Plate / RFID tag
     }
     ```
2. **Pluggable Gate Hardware & Validator Interfaces**:
   - We define abstract interfaces `IVehicleAccessValidator` and `IGateHardwareAdapter`:
     ```typescript
     export interface IGateHardwareAdapter {
       triggerBoomBarrier(gateId: string, direction: 'IN' | 'OUT'): Promise<boolean>;
     }
     ```
   - In the current scope, standard visitor approval and manual security guard check-ins utilize default implementations.
3. **Database Schema Preparation**:
   - `units` table reserves an optional relation for future parking slots.
   - `gate_entries` table includes generic payload fields `entry_mode` (`MANUAL_GUARD`, `QR_CODE`, future `ANPR_CAMERA`, `RFID_BOOM_BARRIER`) and optional metadata JSONB for vehicle registration numbers.
4. **Event-Driven Extension**:
   - Gate movements emit `GateEntryRecordedEvent`. When the vehicle module is introduced, new event listeners will ingest plate numbers, check resident vehicle registries, or coordinate EV charging billing without modifying the visitor check-in engine.

## Consequences
### Positive
- Zero disruption to current scope delivery.
- Future vehicle and IoT boom-barrier hardware integrations can be introduced as clean, isolated plugins.
- Preserves database integrity with zero breaking migrations in future phases.

### Negative / Trade-offs
- Slight architectural abstraction overhead in the `gate-visitor` module to maintain interface separation.
