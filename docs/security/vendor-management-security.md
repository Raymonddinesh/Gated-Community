# Vendor Management Security & Isolation Specifications

## 1. Multi-Tenant Row Level Security (RLS)
Every table created in Phase 13 is protected by PostgreSQL RLS:
- `vendor_categories`
- `vendor_profiles`
- `vendor_society_associations`
- `vendor_contacts`
- `vendor_addresses`
- `vendor_services`
- `vendor_documents`
- `vendor_status_histories`
- `vendor_assignment_histories`

Policy definition:
```sql
CREATE POLICY <table_name>_tenant_isolation ON <table_name>
USING (society_id = NULLIF(current_setting('app.current_society_id', true), '')::uuid);
```

## 2. Canonical RBAC Permissions
- `vendor.create`: Create vendor profiles.
- `vendor.view`: View basic vendor profiles and service directory.
- `vendor.view_sensitive`: View unmasked vendor contact person PII and compliance documents.
- `vendor.update`: Edit vendor profiles, contacts, and service offerings.
- `vendor.status.manage`: Transition vendor status lifecycle (activate, suspend, blacklist).
- `vendor.category.manage`: Create and edit service categories.
- `vendor.service.manage`: Manage offered service catalog.
- `vendor.contact.manage`: Manage contact persons.
- `vendor.document.manage`: Upload or archive vendor documents.
- `vendor.document.view`: Access uploaded vendor documents.
- `vendor.assignment.view`: Inspect vendor work order history.
- `vendor.assignment.manage`: Assign work orders to active vendors.
- `vendor.audit.view`: Access vendor status change audit logs.
- `vendor.archive`: Soft archive vendor profiles.

## 3. IDOR Protection
All vendor resource queries require explicit double-filtering on `society_id == current_user.society_id` at database repository and service boundaries. Cross-tenant access results in `404 Not Found`.
