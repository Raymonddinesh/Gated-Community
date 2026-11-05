# Phase 19 — Emergency & Incident Management Security & Privacy Architecture

## 1. Multi-Tenant Row Level Security (RLS)
Every tenant-owned table in Phase 19 must enforce PostgreSQL RLS and `FORCE RLS` via migration `0019_emergency_incident_management`:
- `incidents`
- `incident_categories`
- `incident_assignments`
- `incident_timelines`
- `incident_actions`
- `incident_escalations`
- `incident_attachments`
- `emergency_contacts`
- `incident_status_histories`
- `incident_acknowledgements`

RLS Policy Definition:
`ALTER TABLE <table_name> ENABLE ROW LEVEL SECURITY;`
`ALTER TABLE <table_name> FORCE ROW LEVEL SECURITY;`
`CREATE POLICY <table_name>_tenant_isolation ON <table_name> USING (society_id = current_setting('app.current_society_id')::uuid);`

## 2. Canonical RBAC Permissions
- `incident.report`: Report emergency or incident
- `incident.view_own`: View self-reported incidents
- `incident.view`: View eligible resident/responder incident details
- `incident.view_all`: Administrative view of all society incidents
- `incident.create`: Create/register incident on behalf of society
- `incident.triage`: Perform severity evaluation and initial triage
- `incident.acknowledge`: Acknowledge incident response
- `incident.assign`: Assign staff/responders to incident
- `incident.respond`: Record response actions and progress
- `incident.escalate`: Escalate incident to higher authority
- `incident.resolve`: Mark incident as contained/resolved
- `incident.close`: Close resolved incident after verification
- `incident.timeline.view`: View operational incident timeline
- `incident.timeline.manage`: Record timeline operational entries
- `incident.action.view`: View immediate response actions
- `incident.action.create`: Create immediate response action
- `incident.action.assign`: Assign response action
- `incident.action.update`: Update response action status
- `incident.contact.view`: View emergency contacts directory
- `incident.contact.manage`: Configure society emergency contacts
- `incident.override`: Emergency administrative override (strictly logged)

## 3. Privacy & Sensitivity Filtering
- **Medical & Identity Privacy**: Incident reports involving personal medical emergencies, domestic disputes, or sensitive resident details MUST mask PII from ordinary residents.
- **Role-Based Fields**: Reporter phone, exact unit number, and internal response notes are visible ONLY to assigned responders, security leads, and authorized admins.
- **Server-Side Enforcement**: Privacy masking is enforced in backend serializers (`IncidentPrivacyFilter`), never relied upon on the client side.

## 4. Emergency Override Boundary
Emergency override is NARROWLY SCOPED:
- DOES NOT bypass PostgreSQL RLS or tenant isolation.
- DOES NOT grant platform `SUPER_ADMIN` shortcuts.
- Requires explicit `incident.override` permission.
- Requires mandatory logged override reason, actor ID, timestamp, and incident context.

## 5. Attachment Security
- Cannonical S3 storage key: `societies/{society_id}/incidents/{incident_id}/{file_size}_{filename}`.
- Sanitized filenames (strip `..`, `/`, `\`).
- Restricted MIME types (images, PDF, audio/wav, audio/mp3).
- Presigned GET URLs with 60-second TTL. No public bucket access.
