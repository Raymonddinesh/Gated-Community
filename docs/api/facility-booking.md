# Phase 15 — Facility Booking API Specification

## Endpoints

### Config & Availability Windows
- `GET /api/v1/facilities/{facility_id}/booking-config`
  - Get facility booking configuration rules.
- `PUT /api/v1/facilities/{facility_id}/booking-config`
  - Upsert facility booking configuration rules.
- `GET /api/v1/facilities/{facility_id}/availability-windows`
  - Get facility operating days and time slots.
- `PUT /api/v1/facilities/{facility_id}/availability-windows`
  - Replace facility availability windows.

### Blackout Periods
- `POST /api/v1/facilities/{facility_id}/blackouts`
  - Schedule a maintenance or blackout period.
- `GET /api/v1/facilities/{facility_id}/blackouts`
  - List facility blackout periods.
- `POST /api/v1/facilities/{facility_id}/blackouts/{blackout_id}/cancel`
  - Cancel a blackout period.

### Bookings Lifecycle
- `POST /api/v1/facility-bookings`
  - Create a new facility reservation (`BK-YYYY-XXXXXX`).
- `GET /api/v1/facility-bookings`
  - List bookings with filtering options (`facility_id`, `user_id`, `status`, dates).
- `GET /api/v1/facility-bookings/{booking_id}`
  - Retrieve detailed booking record with participants, approvals, cancellations.
- `POST /api/v1/facility-bookings/{booking_id}/approve`
  - Approve or reject a pending reservation request.
- `POST /api/v1/facility-bookings/{booking_id}/cancel`
  - Cancel a reservation.
- `POST /api/v1/facility-bookings/{booking_id}/check-in`
  - Perform resident check-in.
- `POST /api/v1/facility-bookings/{booking_id}/complete`
  - Complete reservation session.
- `POST /api/v1/facility-bookings/{booking_id}/no-show`
  - Mark reservation as no-show.
- `GET /api/v1/facility-bookings/{booking_id}/audit-trail`
  - Get status history audit log.
