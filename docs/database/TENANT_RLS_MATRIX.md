# SocietySphere Tenant Table & Row-Level Security (RLS) Matrix

## 1. Architectural Principles of Database Multi-Tenancy

Every entity in SocietySphere falls into one of three structural categories:
1. **Platform Root / Boundary Entity**: Entities that establish tenant boundaries (`societies`) or represent platform-wide identities (`users`).
2. **Platform Shared Catalog**: System-level role and permission taxonomy templates (`roles`, `permissions`, `role_permissions`).
3. **Tenant-Owned Entities**: Domain entities whose lifecycle, ownership, and data belongs strictly to an individual `Society`.

All tenant-owned tables implement **PostgreSQL Row-Level Security (RLS)** as a defense-in-depth kernel guarantee underneath the application service layer.

---

## 2. Complete Database Table / RLS Matrix

| Table | Tenant Owned? | `society_id` Column | RLS Enabled? | Policy Definition | Supporting Indexes | Notes |
| :--- | :---: | :---: | :---: | :--- | :--- | :--- |
| `societies` | **No** (Tenant Boundary) | N/A (Primary Key `id`) | No | N/A | `pk_societies`, `ix_societies_registration_number`, `ix_societies_status` | Primary tenant boundary. Queried at platform level and resolved by ID. |
| `users` | **No** (Global Identity) | No | No | N/A | `pk_users`, `ix_users_email_lower`, `ix_users_phone`, `ix_users_status` | Global platform user identity. Independent of any society. |
| `blocks` | **Yes** | `UUID NOT NULL REFERENCES societies(id)` | **Yes** | `society_id = NULLIF(current_setting('app.current_society_id', true), '')::uuid` | `ix_blocks_society_id`, `uq_blocks_society_code` | Physical building/wing. Uniqueness of block code is tenant-scoped. |
| `floors` | **Yes** | `UUID NOT NULL REFERENCES societies(id)` | **Yes** | `society_id = NULLIF(current_setting('app.current_society_id', true), '')::uuid` | `ix_floors_society_id`, `ix_floors_block_id`, `uq_floors_block_number` | Vertical floor level. Uniqueness of floor number is block/society scoped. |
| `units` | **Yes** | `UUID NOT NULL REFERENCES societies(id)` | **Yes** | `society_id = NULLIF(current_setting('app.current_society_id', true), '')::uuid` | `ix_units_society_id`, `ix_units_block_id`, `ix_units_floor_id`, `uq_units_society_block_number` | Residential flat/unit. Uniqueness of flat number is block/society scoped. |
| `user_society_memberships` | **Yes** | `UUID NOT NULL REFERENCES societies(id)` | **Yes** | `society_id = NULLIF(current_setting('app.current_society_id', true), '')::uuid` | `ix_user_society_memberships_society_id`, `ix_user_society_memberships_user_id`, `uq_membership_user_society` | Security-sensitive: Confines membership visibility strictly to the active society context. |
| `unit_occupancies` | **Yes** | `UUID NOT NULL REFERENCES societies(id)` | **Yes** | `society_id = NULLIF(current_setting('app.current_society_id', true), '')::uuid` | `ix_unit_occupancies_society_id`, `ix_unit_occupancies_unit_id`, `ix_unit_occupancies_user_id`, `ix_unit_occupancies_relationship_type` | Historical and current occupancy registry. Never overwritten on tenancy change. |
| `resident_profiles` | **Yes** | `UUID NOT NULL REFERENCES societies(id)` | **Yes** | `society_id = NULLIF(current_setting('app.current_society_id', true), '')::uuid` | `ix_resident_profiles_society_id`, `ix_resident_profiles_user_id`, `uq_resident_profile_user_society` | Society-specific resident settings (Easy Mode, emergency contacts). |
| `roles` | **No** (Catalog) | No | No | N/A | `pk_roles`, `ix_roles_code`, `uq_roles_code_scope` | Catalog of role definitions partitioned by `scope_type` (`PLATFORM` vs `SOCIETY`). |
| `permissions` | **No** (Catalog) | No | No | N/A | `pk_permissions`, `ix_permissions_code`, `ix_permissions_module`, `uq_permissions_code` | System capability tokens. Global across all tenants. |
| `role_permissions` | **No** (Catalog) | No | No | N/A | `pk_role_permissions`, `fk_role_permissions_role_id_roles`, `fk_role_permissions_permission_id_permissions` | Many-to-many junction between roles and permissions. |
| `role_assignments` | **Hybrid** (Tenant & Platform) | `UUID NULLABLE REFERENCES societies(id)` | **Yes** | `scope_type = 'PLATFORM' OR society_id = NULLIF(current_setting('app.current_society_id', true), '')::uuid` | `ix_role_assignments_society_id`, `ix_role_assignments_user_id`, `ix_role_assignments_role_id`, `ix_role_assignments_user_society_role` | Security-sensitive: Platform assignments visible globally; society assignments strictly isolated to active tenant. |
| `audit_logs` | **Hybrid** (Tenant & Platform) | `UUID NULLABLE REFERENCES societies(id)` | **Yes** | `society_id IS NULL OR society_id = NULLIF(current_setting('app.current_society_id', true), '')::uuid` | `ix_audit_logs_society_created`, `ix_audit_logs_entity`, `ix_audit_logs_actor` | Append-only immutable log. Platform events (`society_id IS NULL`) visible to platform services; tenant events strictly partitioned. |

---

## 3. Security Analysis of Sensitive Tables

### 3.1 `user_society_memberships`
- **Sensitivity:** Determines which users belong to which societies. If leaked, an attacker could enumerate the resident roster of neighboring societies.
- **RLS Policy:** Strictly restricted to rows where `society_id = NULLIF(current_setting('app.current_society_id', true), '')::uuid`.
- **Guarantee:** A database session operating under Society A's context cannot view any memberships of Society B.

### 3.2 `role_assignments`
- **Sensitivity:** Controls privilege grants (e.g. Secretary, Treasurer, Resident).
- **RLS Policy:** Evaluates `scope_type = 'PLATFORM' OR society_id = NULLIF(current_setting('app.current_society_id', true), '')::uuid`.
- **Constraint Backing:** Check constraint `ck_role_assignments_scope_validity` guarantees that `scope_type = 'PLATFORM'` requires `society_id IS NULL`, while `scope_type = 'SOCIETY'` mandates a non-null `society_id`.
- **Guarantee:** Tenant users cannot inspect committee roles or administrative assignments of other societies.

### 3.3 `audit_logs`
- **Sensitivity:** Contains before/after state diffs, JSON payloads, and user actor IDs.
- **RLS Policy:** Evaluates `society_id IS NULL OR society_id = NULLIF(current_setting('app.current_society_id', true), '')::uuid`.
- **Guarantee:** Society administrators can only query their own society's audit records. Platform-level audit records (`society_id IS NULL`) are isolated from tenant-scoped queries.

---

## 4. RLS Bypass Policy Verification & Elimination

> [!IMPORTANT]
> **Vulnerability Eliminated:** The previous policy expression `OR current_setting('app.bypass_rls', true) = 'on'` has been **completely removed** from all database policies.

### Native PostgreSQL Bypass Mechanism:
- In production, RLS bypass is granted **exclusively** to the database migration superuser (`postgres`) or database roles possessing the PostgreSQL native `BYPASSRLS` attribute.
- The runtime application database role (`societysphere_app`) is created as:
  ```sql
  CREATE ROLE societysphere_app WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS;
  ```
- Because `societysphere_app` lacks `BYPASSRLS`, PostgreSQL enforces RLS on every single SQL query.
- No client-provided HTTP header, query string, JWT claim, or session property can ever enable database RLS bypass.
