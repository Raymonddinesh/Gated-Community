# Phase 7 Architecture: Resident, Owner, Tenant & Occupancy Management

## 1. Executive Summary
Phase 7 establishes the authoritative operational domain for **Resident, Owner, Tenant, and Occupancy Management** within SocietySphere. It cleanly models property title, residential occupancy, household relations, and administrative delegation on top of the established multi-tenant PostgreSQL Row-Level Security (RLS) and RBAC foundations.

---

## 2. Domain Hierarchy & Data Architecture

```
Society (Tenant)
  └── Block
        └── Floor
              └── Unit
                    ├── UnitOwnership (1..N Co-Owners, Total % <= 100.00)
                    ├── UnitOccupancy (Time-bound Resident Tenancy)
                    ├── ResidentFamilyMember (Spouse, Child, Parent with Scopes)
                    └── ResidentDelegate (Time-bound, Scoped Permissions)
```

### Entity Model

1. **`UnitOwnership`** (`unit_ownerships`)
   - **Fields**: `id`, `society_id`, `unit_id`, `user_id`, `ownership_percentage` (`Numeric(5,2)`), `start_date`, `end_date`, `is_primary`, `status` (`ACTIVE`, `TRANSFERRED`, `CANCELLED`), `notes`.
   - **Constraints**: `ck_unit_ownership_percentage` (`ownership_percentage > 0 AND ownership_percentage <= 100`).
   - **Lifecycle**: Ownership transfers record `end_date` and update `status = "TRANSFERRED"`. Records are never deleted.

2. **`UnitOccupancy`** (`unit_occupancies`)
   - **Fields**: `id`, `society_id`, `unit_id`, `user_id`, `relationship_type` (`OWNER`, `TENANT`, `FAMILY_MEMBER`, `AUTHORIZED_DELEGATE`), `is_primary_contact`, `valid_from`, `valid_to`, `status` (`ACTIVE`, `ENDED`, `CANCELLED`), `notes`.
   - **Business Rules**: Disjoint rental leases cannot temporally overlap. When the last occupant moves out, physical `Unit.occupancy_status` reverts to `"VACANT"`.

3. **`ResidentProfile`** (`resident_profiles`)
   - **Fields**: `id`, `society_id`, `user_id`, `emergency_contact_name`, `emergency_contact_phone`, `alternate_phone`, `preferred_contact_method`, `preferred_language`, `accessibility_preferences` (`easy_mode`, `high_contrast`, `font_size`), `communication_preferences`, `status` (`ACTIVE`, `INACTIVE`, `MOVED_OUT`, `SUSPENDED`), `notes`.
   - **Tenant Scoping**: Specific to a society. Preferences do not leak across multi-society memberships.

4. **`ResidentFamilyMember`** (`resident_family_members`)
   - **Fields**: `id`, `society_id`, `unit_id`, `primary_resident_user_id`, `user_id` (optional), `name`, `relationship` (`SPOUSE`, `CHILD`, `PARENT`, `SIBLING`, `OTHER`), `phone`, `email`, `access_scope` (JSONB), `status` (`ACTIVE`, `INACTIVE`).

5. **`ResidentDelegate`** (`resident_delegates`)
   - **Fields**: `id`, `society_id`, `unit_id`, `delegator_user_id`, `delegate_user_id`, `permissions` (JSON array), `valid_from`, `valid_to`, `status` (`ACTIVE`, `REVOKED`, `EXPIRED`), `revoked_at`, `revoked_by`, `revocation_reason`, `notes`.
   - **Permissions Whitelist**: `resident.view`, `resident.update`, `unit.view`, `billing.view`, `payment.view`, `complaint.create`, `visitor.manage`.

---

## 3. Deterministic Business Rules

### A. Ownership Percentage Invariant
$$\sum_{i=1}^{n} \text{ownership\_percentage}_i \le 100.00\%$$
- Evaluated prior to granting new ownership.
- If total percentage exceeds 100.00%, rejects with HTTP 400 (`InvalidOwnershipPercentageError`).

### B. Tenancy Lease Overlap Detection
Two intervals $[S_A, E_A]$ and $[S_B, E_B]$ conflict if:
$$\text{Overlap} \iff (E_A \text{ is None or } E_A \ge S_B) \land (E_B \text{ is None or } E_B \ge S_A)$$
- Open-ended intervals ($E = \text{None}$) represent ongoing leases extending to $+\infty$.
- Conflicting tenant leases abort with HTTP 409 (`OccupancyOverlapError`).

### C. Deterministic Profile Completeness
- Evaluates 6 key attributes without AI:
  1. `display_name` (Weight 20)
  2. `phone` (Weight 20)
  3. `email` (Weight 20)
  4. `emergency_contact_name` (Weight 15)
  5. `emergency_contact_phone` (Weight 15)
  6. `preferred_language` (Weight 10)
- Returns exact `score_percent` (0–100%), `is_complete` boolean, and lists of missing required and optional fields.

### D. Privacy Masking Invariant
- **Masked Phone**: Visible 4-character prefix and 4-character suffix with middle digits masked with asterisks (e.g., `+919876543210` $\to$ `+919*****3210`).
- **Masked Email**: First character of local part, asterisks for remaining local characters, last character, followed by domain (e.g., `resident@example.com` $\to$ `r******t@example.com`).

---

## 4. PostgreSQL Row-Level Security (RLS)

Alembic migration `20261003_0007_resident_occupancy_management.py` creates tables with:
```sql
ALTER TABLE unit_ownerships ENABLE ROW LEVEL SECURITY;
ALTER TABLE unit_ownerships FORCE ROW LEVEL SECURITY;

CREATE POLICY rls_unit_ownerships_tenant_select
    ON unit_ownerships FOR SELECT
    USING (society_id = NULLIF(current_setting('app.current_society_id', true), '')::uuid);

CREATE POLICY rls_unit_ownerships_tenant_write
    ON unit_ownerships FOR ALL
    USING (society_id = NULLIF(current_setting('app.current_society_id', true), '')::uuid)
    WITH CHECK (society_id = NULLIF(current_setting('app.current_society_id', true), '')::uuid);
```
Applied identically to `resident_family_members` and `resident_delegates`.

---

## 5. Billing & Accounting Separation

- **Historical Immutability**: Existing posted invoices (`invoices`), payment allocations (`payment_allocations`), receipts (`receipts`), and general ledger entries (`journal_entries`) remain unmodified when residents move out or ownership transfers.
- **Vacant Unit Responsibility**: When a unit has no active tenant or resident occupant, billing generation automatically resolves financial liability to the active primary owner from `unit_ownerships`.

---

## 6. Verification & Quality Gates

- **Test Suite**: 142/142 tests passing (`tests/test_resident_occupancy.py` + all Phase 1–6 regression tests).
- **Linter (Ruff)**: 0 errors, full formatting compliance.
- **Type Checker (Mypy)**: Clean (`Success: no issues found in 139 source files`).
- **Frontend Typecheck (TypeScript)**: Clean (`tsc --noEmit` exited 0).
- **Frontend Linter (ESLint)**: Clean (0 errors, 0 warnings).
