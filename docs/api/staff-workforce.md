# Staff & Workforce Management API Specification

## Endpoints Summary

### Staff Profiles
- `POST /api/v1/staff/profiles` — Create a new staff profile (`staff.create`)
- `GET /api/v1/staff/profiles` — List staff profiles with filters (`staff.read`)
- `GET /api/v1/staff/profiles/{staff_id}` — Get staff detail (`staff.read` / `staff.read_sensitive`)
- `PATCH /api/v1/staff/profiles/{staff_id}/status` — Transition staff status lifecycle (`staff.status.manage`)

### Staff Roles
- `POST /api/v1/staff/roles` — Create operational role (`staff.role.manage`)
- `GET /api/v1/staff/roles` — List active operational roles
- `POST /api/v1/staff/roles/assignments` — Assign role to staff (`staff.role.manage`)

### Staff Teams
- `POST /api/v1/staff/teams` — Create staff team (`staff.team.manage`)
- `GET /api/v1/staff/teams` — List active staff teams
- `POST /api/v1/staff/teams/memberships` — Add staff member to team (`staff.team.assign`)

### Staff Documents
- `POST /api/v1/staff/documents/upload` — Upload staff document metadata (`staff.document.manage`)
- `GET /api/v1/staff/documents` — List staff documents (`staff.document.read`)
- `POST /api/v1/staff/documents/{document_id}/archive` — Soft-archive document (`staff.document.manage`)
