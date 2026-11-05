# Phase 17 — Events REST API Specification

## Endpoints Summary

Base Path: `/api/v1/events`

### Event Management

- `POST /api/v1/events` — Create new draft event (`event.create`)
- `GET /api/v1/events` — List society events (`event.view`)
- `GET /api/v1/events/{event_id}` — Get event details & metrics (`event.view`)
- `PUT /api/v1/events/{event_id}` — Update event draft (`event.update`)
- `POST /api/v1/events/{event_id}/submit` — Submit event for review (`event.submit`)
- `POST /api/v1/events/{event_id}/approve` — Approve or reject event (`event.approve`)
- `POST /api/v1/events/{event_id}/publish` — Publish approved event (`event.publish`)
- `POST /api/v1/events/{event_id}/cancel` — Cancel event (`event.cancel`)
- `GET /api/v1/events/{event_id}/metrics` — Get registration and attendance metrics (`event.view`)

### Event Registrations

- `POST /api/v1/events/{event_id}/registrations` — Register participant (`event.view`)
- `POST /api/v1/events/{event_id}/registrations/cancel` — Cancel registration (`event.view`)
- `GET /api/v1/events/{event_id}/registrations` — List registrations (`event.registration.view`)

### Event Attendance

- `POST /api/v1/events/{event_id}/attendance/{user_id}` — Record attendance check-in (`event.attendance.manage`)
- `GET /api/v1/events/{event_id}/attendance` — List attendance records (`event.attendance.view`)

### Event Attachments

- `POST /api/v1/events/{event_id}/attachments` — Upload attachment metadata (`event.attachment.manage`)
- `GET /api/v1/events/{event_id}/attachments` — List event attachments (`event.view`)

---

## Example Payload & Response

### Create Event (`POST /api/v1/events`)

```json
{
  "title": "Pongal Celebration & Cultural Fest",
  "description": "Annual traditional Pongal cooking, rangoli contest, and evening dance performance.",
  "event_type": "FESTIVAL",
  "capacity": 100,
  "registration_required": true,
  "starts_at": "2026-01-15T18:00:00Z",
  "ends_at": "2026-01-15T21:00:00Z",
  "timezone": "Asia/Kolkata"
}
```

### Event Response (`201 Created`)

```json
{
  "id": "c477ee20-0519-47bc-b3bb-4b1715a582da",
  "society_id": "756824e9-6538-48e7-b540-ad4a9fc9864e",
  "event_number": "EVT-2026-000001",
  "title": "Pongal Celebration & Cultural Fest",
  "description": "Annual traditional Pongal cooking, rangoli contest, and evening dance performance.",
  "event_type": "FESTIVAL",
  "status": "DRAFT",
  "organizer_id": "7a4b4a55-7ec9-49bd-b190-45b034f83e5f",
  "capacity": 100,
  "registration_required": true,
  "starts_at": "2026-01-15T18:00:00Z",
  "ends_at": "2026-01-15T21:00:00Z",
  "timezone": "Asia/Kolkata",
  "created_at": "2026-10-05T12:00:00Z",
  "updated_at": "2026-10-05T12:00:00Z"
}
```
