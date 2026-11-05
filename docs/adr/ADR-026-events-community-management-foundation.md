# ADR-026: Phase 17 — Events & Community Management Foundation Architecture

## Context

SocietySphere requires a multi-tenant, auditable Event & Community Management Foundation module for handling society cultural programs, sports activities, festivals, workshops, community gatherings, and awareness programs.

The implementation must strictly adhere to the locked architecture of Phases 1–16, maintaining multi-tenant RLS isolation, RBAC controls, non-destructive financial boundaries, and decoupled domain event patterns.

## Decisions

1. **Normalized Entities**: Implemented 8 normalized database entities (`Event`, `EventParticipant`, `EventRegistration`, `EventApproval`, `EventSchedule`, `EventAttendance`, `EventAttachment`, `EventStatusHistory`).
2. **Sequential Numbering**: Used `EVT-YYYY-XXXXXX` generated via PostgreSQL advisory locking (`acquire_event_number_lock`) with fallbacks for SQLite test environments.
3. **Deterministic State Machine**: Enforced strict lifecycle transitions (`DRAFT` -> `PENDING_APPROVAL` -> `APPROVED` -> `SCHEDULED` -> `PUBLISHED` -> `REGISTRATION_OPEN` -> `IN_PROGRESS` -> `COMPLETED`, plus `CANCELLED` and `REJECTED`).
4. **Facility Booking Integration**: Reused Phase 14 `Facility` and Phase 15 `FacilityBooking` service boundary (`FacilityBookingService.create_booking`) without creating duplicate facility entities or bypassing Phase 15 availability/conflict checks.
5. **Transactional Capacity & Waitlist**: Implemented `acquire_event_capacity_lock` for transactional capacity enforcement. Overflow registrations are assigned status `WAITLISTED` with sequential `waitlist_position`. Confirmations automatically promote waitlisted registrants upon cancellation.
6. **Participant Privacy**: Implemented `EventParticipantPrivacyFilter` to mask individual participant identifiers for regular residents while making unmasked details available to authorized administrators.
7. **Financial Isolation**: Enforced strict zero-mutation policy on financial ledgers (`JournalEntry`, `Invoice`, `Payment`, `Receipt`). Paid events are OUT OF SCOPE.

## Status

Approved and Implemented.
