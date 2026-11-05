# SocietySphere Data Retention & Archival Strategy

## 1. Overview and Legal Rationale

Housing societies and cooperative housing bodies are legally mandated under applicable cooperative societies acts and financial regulations to maintain historical records:
- Historical ownership and share certificate transfer records must be maintained indefinitely.
- Tenancy agreements and police verification audit logs must be preserved for statutory inspection periods.
- Financial transactions and accounting ledgers must remain immutable for at least 7 to 10 financial years.

Consequently, SocietySphere strictly prohibits destructive `DELETE` operations on core domain tables.

---

## 2. Soft-Archival Strategy (`ArchiveMixin`)

Entities that support decommissioning or deactivation utilize `ArchiveMixin`:
```python
class ArchiveMixin:
    archived_at: Mapped[Optional[datetime]] = mapped_column(
        default=None,
        nullable=True,
    )
```

### Operational Rules:
1. When a user deactivates a block, floor, or unit, `archived_at` is set to the current UTC timestamp.
2. Active queries filter on `WHERE archived_at IS NULL`.
3. Historical reporting, audit trails, and legal export queries retain full visibility by omitting the `archived_at` filter.
4. Physical `DELETE` statements are restricted and blocked by foreign key constraints (`ON DELETE RESTRICT`).

---

## 3. Historical Occupancy Preservation (`UnitOccupancy`)

In many legacy systems, when a tenant moves out and a new tenant moves in, the tenant row is overwritten or updated in place. This destroys the audit trail of who lived in the apartment on any given date.

In SocietySphere:
- A new `UnitOccupancy` record is appended for every tenancy event.
- When an occupant departs:
  - `status` is set to `'EXPIRED'`.
  - `valid_to` is populated with the departure date.
- The previous tenancy record remains permanently preserved in the database.
- Historical queries can reconstruct the exact occupant roster for any past date or incident investigation.

---

## 4. Append-Only Audit Logging (`AuditLog`)

All state modifications generate immutable records in the `audit_logs` table:
- **Actor:** User ID or system service executing the mutation.
- **Tenant Context:** `society_id` (or `NULL` for platform operations).
- **Snapshot Diffs:** JSONB fields capturing `before_state`, `after_state`, and computed `diff`.
- **Correlation ID:** Request correlation token linking HTTP logs to database audit records.

`AuditLog` records are never updated or deleted under any standard application flow.
