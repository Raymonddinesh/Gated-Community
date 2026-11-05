# ADR-024: Facility Booking & Common Area Reservation Foundation Architecture

## Status
Accepted (Phase 15 Foundation)

## Context
SocietySphere requires a multi-tenant facility booking system that enables residents and society admins to reserve common amenities (e.g., clubhouse, tennis court, party hall) while preventing double bookings, respecting operating hours, enforcing blackout maintenance windows, and maintaining financial and multi-tenant isolation.

## Decision
1. **Extend Phase 14 `Facility` Entity**:
   - Reference `facilities.id` (`Facility`) directly instead of creating duplicate facility tables.
2. **Transaction-Level Advisory Locking for Double Booking Prevention**:
   - Acquire PostgreSQL transaction-level advisory locks (`pg_advisory_xact_lock`) on `facility_id` during booking creation to serialize overlapping slot checks across concurrent requests.
3. **Explicit State Machine**:
   - Reservation states: `DRAFT`, `PENDING_APPROVAL`, `APPROVED`, `REJECTED`, `CANCELLED`, `CHECKED_IN`, `COMPLETED`, `NO_SHOW`, `EXPIRED`.
4. **Tenant & Financial Isolation**:
   - PostgreSQL RLS enabled & forced on all 8 tables.
   - Zero direct database writes to core accounting/invoice tables.

## Consequences
- Guarantees zero double bookings under heavy concurrent API calls.
- Preserves clean modular boundaries between Facility Assets (Phase 14) and Facility Bookings (Phase 15).
