# Phase 15 — Facility Booking & Common Area Reservation Architecture

## Overview
Phase 15 provides a production-grade multi-tenant facility booking and reservation foundation for SocietySphere. It builds directly upon Phase 14's `facilities` entity (`facilities.id`) without duplicate facility schema definitions.

## Key Subsystems
1. **Booking Configuration & Operating Hours (`FacilityBookingConfig`, `FacilityAvailabilityWindow`)**:
   - Per-facility rules including advance booking window, min/max duration, capacity limits, cancellation notice requirements, and operating day/time windows.
2. **Maintenance & Blackout Periods (`FacilityBlackoutPeriod`)**:
   - Priority maintenance blocks (`SCHEDULED`, `ACTIVE`, `COMPLETED`, `CANCELLED`) that override resident reservation availability.
3. **Reservation Lifecycle State Machine (`FacilityBooking`)**:
   - `DRAFT` -> `PENDING_APPROVAL` / `APPROVED` -> `CHECKED_IN` -> `COMPLETED` / `NO_SHOW` / `EXPIRED`.
   - Cancellation transitions to `CANCELLED`.
4. **Concurrency & Double Booking Protection**:
   - Row-level lock (`pg_advisory_xact_lock`) on `facility_id` during reservation creation.
   - Prevents overlapping active reservations (`PENDING_APPROVAL`, `APPROVED`, `CHECKED_IN`).
5. **Multi-Tenancy & Financial Isolation**:
   - Enforced PostgreSQL Row Level Security (`ENABLE ROW LEVEL SECURITY` and `FORCE ROW LEVEL SECURITY`) with `society_id` tenant isolation on all 8 tables.
   - Zero direct mutation of core accounting, invoice, ledger, or payment tables.

## Table Architecture
- `facility_booking_configs`
- `facility_availability_windows`
- `facility_blackout_periods`
- `facility_bookings`
- `facility_booking_participants`
- `facility_booking_approvals`
- `facility_booking_cancellations`
- `facility_booking_status_history`
