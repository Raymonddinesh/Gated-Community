# ADR-016: Resident, Owner, Tenant & Occupancy Management

## Status
Approved

## Context
Following the completion and verification of Platform Foundation (Phase 1), Multi-Tenancy & RLS (Phase 2), Authentication & RBAC (Phase 3), Accounting Core (Phase 4), Maintenance Billing (Phase 5), and Payment Reconciliation (Phase 6), SocietySphere requires an authoritative operational domain for managing:
1. **Unit Ownership**: Legal and beneficial ownership records for units, supporting both single owners and joint co-owners with percentage validation.
2. **Unit Occupancy**: Time-bound resident residency tracking (Owners, Tenants, Family Members, Delegates) with move-in and move-out workflows and temporal overlap conflict prevention.
3. **Household & Family Relationships**: Explicit family member links with designated access scopes and privacy controls.
4. **Authorized Delegates**: Scoped, time-bound, and revocable delegation of unit-related administrative rights.
5. **Resident Self-Service & Directory**: Privacy-preserving resident profiles, emergency contact management, deterministic profile completeness scoring, and directory masking.
6. **Billing & Accounting Separation**: Strict guarantee that occupancy transitions do not retroactively alter historical invoices or posted accounting records.

## Decisions

### 1. Architectural Separation: Ownership vs Occupancy
We explicitly decouple legal/beneficial **Ownership** from physical **Occupancy**:
- **`UnitOwnership`**: Represents property title/undivided share. A unit may have a single owner (100%) or multiple joint co-owners whose active shares sum to $\le 100\%$. Ownership records are append-only; transferring ownership sets `status = "TRANSFERRED"` and records `end_date`, never deleting the historical row.
- **`UnitOccupancy`**: Represents physical residency in the unit (e.g. Owner residing, Tenant leasing, Family member residing). Rental leases strictly prohibit overlapping date ranges (returning HTTP 409 Conflict). Physical `Unit.occupancy_status` is synchronized automatically (`OCCUPIED` vs `VACANT`).
- When a unit is vacant (no active tenant or resident occupant), maintenance billing responsibility automatically resolves to the primary active owner in `UnitOwnership`.

### 2. Single & Joint Co-Ownership Validation & Open Business Rule
- Ownership percentages are tracked using `Numeric(5, 2)` (2 decimal places) with a database check constraint `ownership_percentage > 0 AND ownership_percentage <= 100`.
- The `OwnershipService` calculates the sum of existing active ownership percentages for the target unit prior to granting new ownership. If the cumulative sum exceeds 100.00%, the request is rejected with `InvalidOwnershipPercentageError` (HTTP 400).
- Co-owners are designated as `is_primary = True` for the primary titleholder, ensuring deterministic communication and billing resolution.
- **OPEN BUSINESS RULE: Active Ownership Total < 100%**:
  Active ownership totals MAY legitimately be $< 100\%$ (e.g., builder/developer unsold inventory, conveyancing in escrow, pending inheritance probate, or fractional title transfers). This is an explicit open business rule. The system strictly guarantees $\sum \text{percentage} \le 100.00\%$ and $0 < \text{percentage} \le 100\%$, but does not force a mandatory 100% total.

### 3. Concurrency Protection & Locking Invariants
- To eliminate race conditions where concurrent additions exceed 100% or concurrent leases overlap:
  1. **PostgreSQL Row-Level Locks**: Every mutating operation executes `SELECT ... FROM units WHERE id = :unit_id FOR UPDATE` ensuring row-level serialization in PostgreSQL transactions.
  2. **Application-Level Coroutine Serialization**: An asynchronous mutex (`get_unit_lock(unit_id)`) guarantees serialized access per unit within the application process.

### 4. Strict Domain Separation: Ownership vs Occupancy vs Delegation
The domain model enforces total decoupling across three distinct concepts:
- **`UnitOwnership` (Legal Title)**: Governs property rights and unsold developer liabilities. Does NOT grant physical residency.
- **`UnitOccupancy` (Physical Presence)**: Governs residency (Owner, Tenant, Family). Does NOT confer property title. Moving out does NOT alter ownership or revoke delegations.
- **`ResidentDelegate` (Authority to Act)**: Governs scoped administrative agency. Does NOT grant occupancy rights or ownership title. Revoking a delegation does NOT terminate occupancy or ownership.
- Explicit non-implication guarantees:
  * Creating a delegate NEVER creates an occupancy or ownership record.
  * Moving in an occupant NEVER creates a delegate or ownership record.
  * Revoking delegation NEVER ends or modifies occupancy.
  * Moving out of a unit NEVER revokes unrelated delegation authority.

### 5. Auto-Membership Creation Security & Privilege Escalation Protection
- Moving into a unit or registering ownership ensures the user has a `UserSocietyMembership` in the target society.
- **Security Protections**:
  * Auto-membership creates **only** a basic `UserSocietyMembership` row with `membership_status = "ACTIVE"`.
  * Auto-membership assigns **ZERO privileged roles** (no Admin, Treasurer, Secretary, or Manager roles).
  * System records an immutable audit log (`action = "membership.auto_enrolled"`).
  * Cross-tenant rejection: Move-in or ownership operations verify `Unit.society_id == context.society_id`, preventing unauthorized enrollment across society boundaries.

### 6. Delegate Permission Model & Escalation Prevention
- Delegate permissions are strictly whitelisted against `ALLOWED_DELEGATE_PERMISSIONS`.
- **Anti-Delegation & Self-Escalation Guards**:
  * Only active unit owners or primary occupants may designate a delegate. A delegate **cannot** delegate authority to another user.
  * Delegates cannot expand their own permissions or grant administrative capabilities.
- **Canonical RBAC Integration (`is_delegate_authorized`)**:
  * Canonical check verifies active status, unrevoked state (`revoked_at IS NULL`), and active temporal window (`valid_from <= today <= valid_to`).
  * Permissions for unreleased future modules (`complaint.create`, `visitor.manage`) strictly evaluate to `False` until canonical RBAC modules are implemented in Phase 8+.

### 7. Atomic Ownership Transfer Workflow
- Supports 100% transfer or partial share divestment in a single database transaction under unit concurrency lock:
  * **100% Transfer**: Source ownership marked `TRANSFERRED` with `end_date`, new ownership created for recipient with transferred share, primary contact transferred.
  * **Partial Transfer**: Source ownership percentage reduced by transfer percentage, new ownership created for recipient with transferred share.
  * Audit logging records `ownership.transferred` on source and `ownership.acquired` on destination.
  * Preserves full ownership history; records are never deleted.

### 8. Historical Billing & Financial Invariance
- Past invoices, payments, receipts, payment allocations, and General Ledger journal entries are strictly immutable.
- Move-out or ownership transfer touches only occupancy and ownership relations. Historical financial transactions are 100% preserved.

## Consequences

### Positive
- Strict separation of legal ownership and residential occupancy matches real-world property law.
- Overlapping rental leases are structurally prevented.
- Complete audit trail preserved for all ownership changes, move-outs, and delegate revocations.
- Deterministic profile completeness promotes data quality without external AI latency or non-determinism.
- High-contrast and Easy Mode preferences stored per society without mutating global user identity.

### Negative / Trade-offs
- Multiple co-owners require careful handling in downstream voting or approval workflows (reserved for future governance modules).
- Queries for unit status must check both occupancy and ownership tables when resolving vacant unit liabilities.
