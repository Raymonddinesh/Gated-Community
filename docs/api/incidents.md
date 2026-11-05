# Phase 19 — Emergency & Incident Management REST API Specification

## Base Path
`/api/v1/incidents` & `/api/v1/emergency-contacts`

## Endpoint Blueprint

### 1. Incident Reporting & Lifecycle
- `POST /api/v1/incidents`: Report new emergency/incident (`incident.report`)
- `GET /api/v1/incidents`: List incidents with status/severity filters (`incident.view`)
- `GET /api/v1/incidents/{id}`: Get incident details with privacy masking (`incident.view`)
- `PATCH /api/v1/incidents/{id}`: Triage/update incident details (`incident.triage`)
- `POST /api/v1/incidents/{id}/transition`: Advance lifecycle state (`incident.respond`)
- `POST /api/v1/incidents/{id}/acknowledge`: Acknowledge incident (`incident.acknowledge`)
- `POST /api/v1/incidents/{id}/escalate`: Escalate incident (`incident.escalate`)
- `POST /api/v1/incidents/{id}/resolve`: Mark incident resolved (`incident.resolve`)
- `POST /api/v1/incidents/{id}/close`: Close incident after audit (`incident.close`)

### 2. Responders & Assignments
- `POST /api/v1/incidents/{id}/assignments`: Assign responders (`incident.assign`)
- `GET /api/v1/incidents/{id}/assignments`: List assigned responders (`incident.view`)
- `DELETE /api/v1/incidents/{id}/assignments/{assignment_id}`: Release responder (`incident.assign`)

### 3. Immediate Response Actions
- `POST /api/v1/incidents/{id}/actions`: Create immediate response action (`incident.action.create`)
- `GET /api/v1/incidents/{id}/actions`: List response actions (`incident.action.view`)
- `PATCH /api/v1/incidents/{id}/actions/{action_id}`: Update action status (`incident.action.update`)

### 4. Operational Timeline & Evidence Attachments
- `GET /api/v1/incidents/{id}/timeline`: Retrieve operational log timeline (`incident.timeline.view`)
- `POST /api/v1/incidents/{id}/timeline`: Add manual operational log note (`incident.timeline.manage`)
- `POST /api/v1/incidents/{id}/attachments`: Upload incident photo/audio (`incident.report`)
- `GET /api/v1/incidents/{id}/attachments`: List attachments with presigned URLs (`incident.view`)

### 5. Emergency Contacts Directory
- `GET /api/v1/emergency-contacts`: Get active emergency contacts directory (`incident.contact.view`)
- `POST /api/v1/emergency-contacts`: Add society emergency contact (`incident.contact.manage`)
- `PATCH /api/v1/emergency-contacts/{id}`: Update emergency contact (`incident.contact.manage`)
- `DELETE /api/v1/emergency-contacts/{id}`: Deactivate contact (`incident.contact.manage`)

## Idempotency & Tenant Requirements
- All POST/PATCH mutation endpoints accept `X-Idempotency-Key` header.
- Tenant context is strictly enforced via `X-Society-ID` header or URL parameter matching `request.state.tenant_id`.
