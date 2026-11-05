# Staff & Workforce Management Security & Privacy

## Multi-Tenancy & Row Level Security (RLS)
All 9 Phase 12 database tables enforce PostgreSQL Row Level Security:
```sql
ALTER TABLE staff_profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE staff_profiles FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation_staff_profiles ON staff_profiles
FOR ALL
USING (society_id = NULLIF(current_setting('app.current_society_id', true), '')::uuid)
WITH CHECK (society_id = NULLIF(current_setting('app.current_society_id', true), '')::uuid);
```

## Privacy & Sensitive PII Scoping
- **Public / Resident View**: Residents can view staff names, preferred names, photos, and operational role titles (`staff:read`). Direct phone numbers, emails, emergency contacts, notes, and documents are masked.
- **Sensitive Contact Access**: Unmasked contact numbers and emergency details require explicit `staff.read_sensitive` permission.
- **Document Access**: Access restricted via `staff.document.read` and `staff.document.manage`.

## Role & Permission Boundaries
- Operational `StaffRole` (e.g., Electrician) does **NOT** grant application-level administrative privileges. Application authorization remains strictly controlled by Phase 3 RBAC permissions.
