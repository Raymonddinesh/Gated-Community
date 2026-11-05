# Phase 11 — Maintenance & Work Order Management Security Architecture

## 1. Multi-Tenant Row Level Security (RLS)

All 12 Phase 11 tables enforce PostgreSQL Row Level Security (`ENABLE` + `FORCE`):
- Tenant isolation policy: `society_id = NULLIF(current_setting('app.current_society_id', true), '')::uuid`
- Checked on `USING` and `WITH CHECK` for `ALL` operations.

## 2. Granular RBAC Permissions

Specific permission codes govern Phase 11 actions:
- `maintenance.create`: Create work orders
- `maintenance.view_own`: View own/unit work orders
- `maintenance.view_all`: View all society work orders
- `maintenance.assign`: Assign/reassign work orders
- `maintenance.schedule`: Update schedule
- `maintenance.priority.manage`: Manage operational priority
- `maintenance.status.manage`: Transition status machine
- `maintenance.comment`: Post public comments
- `maintenance.comment_internal`: Post and view internal staff notes
- `maintenance.attachment.manage`: Upload or archive evidence attachments
- `maintenance.material.manage`: Manage operational material usage
- `maintenance.sla.manage`: Configure SLA policies
- `maintenance.escalate`: Trigger SLA escalations
- `maintenance.resolve`: Mark work orders complete
- `maintenance.verify`: Verify resolutions
- `maintenance.close`: Close work orders
- `maintenance.reopen`: Reopen work orders
- `maintenance.cancel`: Cancel active work orders
- `maintenance.category.manage`: Manage categories/subcategories
- `maintenance.audit.view`: View activity timeline logs

## 3. IDOR & Resident Privacy Protection

- Residents without `maintenance.view_all` can only retrieve work orders where `requested_by_user_id == caller.id` or `created_by_user_id == caller.id`.
- Internal comments (`is_internal = True`) are filtered out from responses for users lacking `maintenance.comment_internal`.

## 4. Cross-Society Relational Integrity

All foreign key associations (categories, subcategories, units, blocks, users, complaints, vehicles, visitors) are strictly validated to ensure they belong to the same `society_id` before mutation.
