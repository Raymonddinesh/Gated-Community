# ADR-025: Announcements, Communications & Resident Notification Foundation Architecture

## Status
Accepted (Phase 16 Foundation)

## Context
SocietySphere requires an official announcement and communication system for broadcasting society notices to targeted audiences (Society, Block, Floor, Unit, Resident, Owner, Tenant) with deterministic priorities, mandatory explicit acknowledgements, read receipts, version history, and decoupled notification readiness.

## Decision
1. **Reuse Phase 2 & 7 Hierarchy & Membership**:
   - Resolve audience targeting against existing `Society`, `Block`, `Floor`, `Unit`, `UnitOwnership`, `UnitOccupancy`, `UserSocietyMembership`, and `ResidentDelegate` entities without duplicating hierarchy tables.
2. **Transaction-Level Advisory Locking**:
   - Acquire PostgreSQL transaction-level advisory locks (`pg_advisory_xact_lock`) on `society_id` during sequential number generation (`ANN-YYYY-XXXXXX`).
3. **Explicit State Machine**:
   - States: `DRAFT`, `PENDING_REVIEW`, `APPROVED`, `REJECTED`, `SCHEDULED`, `PUBLISHED`, `EXPIRED`, `ARCHIVED`.
4. **Tenant & Financial Isolation**:
   - PostgreSQL RLS enabled & forced on all 8 tables.
   - Zero direct database writes to accounting/billing tables.
5. **Decoupled Notification Events**:
   - Emit decoupled domain events (`AnnouncementEventHooks`) without vendor lock-in to external SMS, WhatsApp, Email, or Push delivery providers.

## Consequences
- Enables secure, targeted communications with explicit acknowledgement tracking and version history.
- Maintains clean architectural separation between domain communication readiness and future delivery vendor integration.
