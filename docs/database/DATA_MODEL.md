# SocietySphere Data Model Specification

## 1. Architectural Overview

SocietySphere implements a multi-tenant relational schema on PostgreSQL 16+. The data model enforces a strict separation between **Platform-Level Entities** (entities that exist independently of any housing society) and **Tenant-Scoped Entities** (entities that are owned strictly by a specific `Society`).

All tenant-scoped entities include a `society_id` foreign key referencing `societies(id)` and are protected both in the application domain layer and at the database engine layer via PostgreSQL Row-Level Security (RLS).

---

## 2. Global Conventions & Standard Mixins

### 2.1 Constraint & Index Naming Convention
Alembic and SQLAlchemy use standard automated naming conventions:
- **Indexes:** `ix_%(column_0_label)s`
- **Unique Constraints:** `uq_%(table_name)s_%(column_0_name)s`
- **Check Constraints:** `ck_%(table_name)s_%(constraint_name)s`
- **Foreign Keys:** `fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s`
- **Primary Keys:** `pk_%(table_name)s`

### 2.2 Standard Mixins
- **`TimestampMixin`**:
  - `created_at`: `TIMESTAMPTZ` (UTC), non-null, defaults to current UTC timestamp.
  - `updated_at`: `TIMESTAMPTZ` (UTC), non-null, updated on every modification.
- **`ArchiveMixin`**:
  - `archived_at`: `TIMESTAMPTZ` (UTC), nullable. When populated, indicates soft-archival without physical data destruction.
- **`TenantScopedMixin`**:
  - `society_id`: `UUID`, non-null, indexed, foreign key referencing `societies(id)` with `ON DELETE RESTRICT`.

---

## 3. Detailed Entity Dictionary

### 3.1 Global Identity: `users`
Represents an individual person in the platform. A user may own units in Society A, rent an apartment in Society B, and serve as Secretary in Society C. User identity is globally unique and detached from any individual society.

| Column | Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `id` | `UUID` | `PRIMARY KEY` | Globally unique identifier |
| `email` | `VARCHAR(255)` | `NULLABLE` | Primary email address |
| `phone` | `VARCHAR(32)` | `NULLABLE` | E.164 formatted telephone number |
| `password_hash` | `VARCHAR(255)` | `NULLABLE` | Argon2id password hash |
| `first_name` | `VARCHAR(100)` | `NOT NULL` | Legal given name |
| `last_name` | `VARCHAR(100)` | `NOT NULL` | Legal family name |
| `display_name` | `VARCHAR(200)` | `NOT NULL` | User's preferred presentation name |
| `preferred_language`| `VARCHAR(10)` | `NOT NULL`, Default `'en'` | ISO language code |
| `status` | `VARCHAR(32)` | `NOT NULL`, Default `'ACTIVE'` | Account status (`ACTIVE`, `SUSPENDED`, `LOCKED`) |
| `last_login_at` | `TIMESTAMPTZ` | `NULLABLE` | Timestamp of most recent authentication |
| `created_at` | `TIMESTAMPTZ` | `NOT NULL` | Record creation timestamp |
| `updated_at` | `TIMESTAMPTZ` | `NOT NULL` | Record modification timestamp |
| `archived_at` | `TIMESTAMPTZ` | `NULLABLE` | Soft-archival timestamp |

**Table Constraints & Indexes:**
- Check: `ck_users_email_or_phone_required` (`email IS NOT NULL OR phone IS NOT NULL`)
- Partial Unique Index: `ix_users_email_lower` on `LOWER(email)` where `email IS NOT NULL`
- Partial Unique Index: `ix_users_phone` on `phone` where `phone IS NOT NULL`

---

### 3.2 Primary Tenant Boundary: `societies`
Represents an autonomous Apartment Society, Housing Cooperative, or Residential Welfare Association (RWA).

| Column | Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `id` | `UUID` | `PRIMARY KEY` | Tenant boundary identifier |
| `legal_name` | `VARCHAR(255)` | `NOT NULL` | Official registered legal society name |
| `display_name` | `VARCHAR(255)` | `NOT NULL` | Common name for UI displays |
| `registration_number`| `VARCHAR(100)`| `NULLABLE`, Indexed | Government registration or cooperative act certificate number |
| `address_line1`| `VARCHAR(255)` | `NOT NULL` | Street address line 1 |
| `address_line2`| `VARCHAR(255)` | `NULLABLE` | Street address line 2 |
| `city` | `VARCHAR(100)` | `NOT NULL` | City/Town |
| `state` | `VARCHAR(100)` | `NOT NULL` | State/Province |
| `country` | `VARCHAR(10)` | `NOT NULL`, Default `'IN'` | ISO country code |
| `postal_code` | `VARCHAR(20)` | `NOT NULL` | Postal PIN code |
| `timezone` | `VARCHAR(50)` | `NOT NULL`, Default `'Asia/Kolkata'` | IANA timezone string |
| `default_language`| `VARCHAR(10)` | `NOT NULL`, Default `'en'` | Default society locale |
| `status` | `VARCHAR(32)` | `NOT NULL`, Default `'ACTIVE'` | Operational status (`ACTIVE`, `SUSPENDED`, `ONBOARDING`) |
| `onboarding_status`| `VARCHAR(32)`| `NOT NULL`, Default `'COMPLETED'`| Onboarding progress |
| `created_at` | `TIMESTAMPTZ` | `NOT NULL` | Creation timestamp |
| `updated_at` | `TIMESTAMPTZ` | `NOT NULL` | Modification timestamp |
| `archived_at` | `TIMESTAMPTZ` | `NULLABLE` | Archival timestamp |

---

### 3.3 Physical Spatial Hierarchy: `blocks`, `floors`, `units`

#### `blocks`
Physical building, tower, or wing within a society.
- `id`: `UUID PRIMARY KEY`
- `society_id`: `UUID NOT NULL REFERENCES societies(id) ON DELETE RESTRICT`
- `code`: `VARCHAR(50) NOT NULL` (e.g., `'BLK-A'`, `'TOWER-1'`)
- `display_name`: `VARCHAR(100) NOT NULL`
- `sequence_order`: `INTEGER NOT NULL DEFAULT 0`
- `status`: `VARCHAR(32) NOT NULL DEFAULT 'ACTIVE'`
- **Constraint:** `uq_blocks_society_code` (`UNIQUE(society_id, code)`)

#### `floors`
Vertical level within a physical block.
- `id`: `UUID PRIMARY KEY`
- `society_id`: `UUID NOT NULL REFERENCES societies(id) ON DELETE RESTRICT`
- `block_id`: `UUID NOT NULL REFERENCES blocks(id) ON DELETE RESTRICT`
- `floor_number`: `INTEGER NOT NULL`
- `display_name`: `VARCHAR(100) NOT NULL`
- `sequence_order`: `INTEGER NOT NULL DEFAULT 0`
- `status`: `VARCHAR(32) NOT NULL DEFAULT 'ACTIVE'`
- **Constraint:** `uq_floors_block_number` (`UNIQUE(society_id, block_id, floor_number)`)

#### `units`
Specific residential apartment, villa, flat, or commercial space.
- `id`: `UUID PRIMARY KEY`
- `society_id`: `UUID NOT NULL REFERENCES societies(id) ON DELETE RESTRICT`
- `block_id`: `UUID NOT NULL REFERENCES blocks(id) ON DELETE RESTRICT`
- `floor_id`: `UUID NOT NULL REFERENCES floors(id) ON DELETE RESTRICT`
- `unit_number`: `VARCHAR(50) NOT NULL` (e.g., `'101'`, `'PH-2'`)
- `unit_type`: `VARCHAR(50) NOT NULL DEFAULT '2BHK'`
- `carpet_area_sqft`: `FLOAT NULLABLE`
- `occupancy_status`: `VARCHAR(32) NOT NULL DEFAULT 'VACANT'`
- `status`: `VARCHAR(32) NOT NULL DEFAULT 'ACTIVE'`
- **Constraint:** `uq_units_society_block_number` (`UNIQUE(society_id, block_id, unit_number)`)

---

### 3.4 Memberships & Occupancies

#### `user_society_memberships`
Explicit association establishing that a global `User` belongs to a `Society`.
- `id`: `UUID PRIMARY KEY`
- `user_id`: `UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT`
- `society_id`: `UUID NOT NULL REFERENCES societies(id) ON DELETE RESTRICT`
- `membership_status`: `VARCHAR(32) NOT NULL DEFAULT 'ACTIVE'`
- `joined_at`: `TIMESTAMPTZ NULLABLE`
- `activated_at`: `TIMESTAMPTZ NULLABLE`
- `deactivated_at`: `TIMESTAMPTZ NULLABLE`
- **Constraint:** `uq_membership_user_society` (`UNIQUE(user_id, society_id)`)

#### `unit_occupancies`
Historical and current relationship linking a `User` to a specific `Unit` (Owner, Tenant, Family, Delegate). Never overwritten upon change of tenancy.
- `id`: `UUID PRIMARY KEY`
- `society_id`: `UUID NOT NULL REFERENCES societies(id) ON DELETE RESTRICT`
- `unit_id`: `UUID NOT NULL REFERENCES units(id) ON DELETE RESTRICT`
- `user_id`: `UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT`
- `relationship_type`: `VARCHAR(32) NOT NULL` (`OWNER`, `TENANT`, `FAMILY_MEMBER`, `AUTHORIZED_DELEGATE`)
- `is_primary_contact`: `BOOLEAN NOT NULL DEFAULT FALSE`
- `valid_from`: `DATE NULLABLE`
- `valid_to`: `DATE NULLABLE`
- `status`: `VARCHAR(32) NOT NULL DEFAULT 'ACTIVE'` (`ACTIVE`, `EXPIRED`, `PENDING_VERIFICATION`)
- `notes`: `VARCHAR(500) NULLABLE`

#### `resident_profiles`
Society-specific profile, emergency contact, and accessibility settings.
- `id`: `UUID PRIMARY KEY`
- `society_id`: `UUID NOT NULL REFERENCES societies(id) ON DELETE RESTRICT`
- `user_id`: `UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT`
- `emergency_contact_name`: `VARCHAR(150) NULLABLE`
- `emergency_contact_phone`: `VARCHAR(32) NULLABLE`
- `preferred_contact_method`: `VARCHAR(32) NOT NULL DEFAULT 'APP'`
- `accessibility_preferences`: `JSONB NOT NULL DEFAULT '{}'` (stores Easy Mode flags)
- `communication_preferences`: `JSONB NOT NULL DEFAULT '{}'`
- **Constraint:** `uq_resident_profile_user_society` (`UNIQUE(user_id, society_id)`)

---

### 3.5 Role-Based Authorization & Auditing

#### `roles`
Role templates defined at either `PLATFORM` or `SOCIETY` scope.
- `id`: `UUID PRIMARY KEY`
- `code`: `VARCHAR(50) NOT NULL`
- `name`: `VARCHAR(100) NOT NULL`
- `scope_type`: `VARCHAR(20) NOT NULL DEFAULT 'SOCIETY'` (`PLATFORM` or `SOCIETY`)
- `description`: `VARCHAR(255) NULLABLE`
- `is_system_role`: `BOOLEAN NOT NULL DEFAULT TRUE`
- **Constraint:** `uq_roles_code_scope` (`UNIQUE(code, scope_type)`)

#### `permissions`
Granular authorization capability tokens (e.g., `society.read`, `occupancy.manage`).
- `id`: `UUID PRIMARY KEY`
- `code`: `VARCHAR(100) NOT NULL UNIQUE`
- `name`: `VARCHAR(150) NOT NULL`
- `module`: `VARCHAR(50) NOT NULL`
- `description`: `VARCHAR(255) NULLABLE`

#### `role_permissions`
Many-to-many junction associating Roles with Permissions.
- `role_id`: `UUID NOT NULL REFERENCES roles(id) ON DELETE CASCADE`
- `permission_id`: `UUID NOT NULL REFERENCES permissions(id) ON DELETE CASCADE`
- **Primary Key:** `(role_id, permission_id)`

#### `role_assignments`
Assignment of a Role to a User with tenant boundary constraints.
- `id`: `UUID PRIMARY KEY`
- `user_id`: `UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT`
- `role_id`: `UUID NOT NULL REFERENCES roles(id) ON DELETE RESTRICT`
- `society_id`: `UUID NULLABLE REFERENCES societies(id) ON DELETE RESTRICT`
- `scope_type`: `VARCHAR(20) NOT NULL DEFAULT 'SOCIETY'`
- `assigned_at`: `TIMESTAMPTZ NOT NULL`
- `revoked_at`: `TIMESTAMPTZ NULLABLE`
- `status`: `VARCHAR(32) NOT NULL DEFAULT 'ACTIVE'`
- **Constraint:** `ck_role_assignments_scope_validity`:
  `"(scope_type = 'PLATFORM' AND society_id IS NULL) OR (scope_type = 'SOCIETY' AND society_id IS NOT NULL)"`
- **Index:** `ix_role_assignments_user_society_role` (`UNIQUE(user_id, role_id, society_id)`)

#### `audit_logs`
Append-only immutable audit trail capturing actor, entity, tenant, before/after states, and diffs.
- `id`: `UUID PRIMARY KEY`
- `society_id`: `UUID NULLABLE REFERENCES societies(id) ON DELETE RESTRICT`
- `actor_user_id`: `UUID NULLABLE REFERENCES users(id) ON DELETE SET NULL`
- `action`: `VARCHAR(50) NOT NULL`
- `entity_type`: `VARCHAR(50) NOT NULL`
- `entity_id`: `VARCHAR(100) NOT NULL`
- `request_id`: `VARCHAR(100) NULLABLE`
- `correlation_id`: `VARCHAR(100) NULLABLE`
- `before_state`: `JSONB NULLABLE`
- `after_state`: `JSONB NULLABLE`
- `diff`: `JSONB NULLABLE`
- `created_at`: `TIMESTAMPTZ NOT NULL DEFAULT UTC_NOW`
