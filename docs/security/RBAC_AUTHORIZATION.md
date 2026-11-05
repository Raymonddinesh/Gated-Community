# Role-Based Access Control (RBAC) & Tenant Authorization

## 1. Multi-Tenant Authorization Model

SocietySphere separates role scopes into two distinct tiers: **Platform Scope** and **Society Scope**.

```
                           +-------------------------+
                           |       Global User       |
                           +------------+------------+
                                        |
                 +----------------------+----------------------+
                 | (scope_type = PLATFORM)                     | (scope_type = SOCIETY)
                 v                                             v
     +-----------------------+                    +-------------------------+
     |  Platform Assignment  |                    |   Society Assignment    |
     |  society_id = NULL    |                    |   society_id = Valid UUID|
     |  Role: SUPER_ADMIN    |                    |   Role: SECRETARY / ... |
     +-----------------------+                    +-------------------------+
                 |                                             |
                 v                                             v
     +-----------------------+                    +-------------------------+
     | Global System Actions |                    | Scoped Tenant Actions   |
     | (Full Tenant Bypass)  |                    | (PostgreSQL RLS Bound)  |
     +-----------------------+                    +-------------------------+
```

### Table Structure & Check Constraints
```sql
CREATE TABLE role_assignments (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users(id),
    role_id UUID NOT NULL REFERENCES roles(id),
    society_id UUID REFERENCES societies(id),
    scope_type VARCHAR(20) NOT NULL, -- 'PLATFORM' or 'SOCIETY'
    status VARCHAR(32) NOT NULL DEFAULT 'ACTIVE',
    assigned_at TIMESTAMPTZ NOT NULL,
    revoked_at TIMESTAMPTZ,
    CONSTRAINT ck_role_assignments_scope_validity CHECK (
        (scope_type = 'PLATFORM' AND society_id IS NULL) OR
        (scope_type = 'SOCIETY' AND society_id IS NOT NULL)
    ),
    CONSTRAINT uq_role_assignment UNIQUE (user_id, role_id, society_id)
);
```

---

## 2. Standard System Roles & Capabilities

| Role Code | Scope Type | Key Permissions | Target Personas |
| :--- | :--- | :--- | :--- |
| **`SUPER_ADMIN`** | `PLATFORM` | `platform.admin`, `society.create`, `society.read`, `audit.read` | SaaS Platform Operators |
| **`SOCIETY_ADMIN`** | `SOCIETY` | `society.manage`, `units.manage`, `occupancy.manage`, `roles.assign`, `audit.read` | Elected Management Committee President |
| **`SECRETARY`** | `SOCIETY` | `society.manage`, `units.read`, `occupancy.manage`, `audit.read` | Society Honorary Secretary |
| **`TREASURER`** | `SOCIETY` | `society.read`, `units.read`, `occupancy.read` | Society Honorary Treasurer |
| **`COMMITTEE_MEMBER`** | `SOCIETY` | `society.read`, `units.read`, `occupancy.read` | Managing Committee Board Members |
| **`RESIDENT`** | `SOCIETY` | `society.read`, `units.read`, `occupancy.read` | Flat Owners & Residents |
| **`TENANT`** | `SOCIETY` | `society.read`, `units.read` | Verified Renters / Leaseholders |
| **`SECURITY`** | `SOCIETY` | `society.read`, `units.read` | Main Gate / Guard Post Personnel |

---

## 3. Privilege Escalation & IDOR Guards

### Guard 1: Role Escalation Prevention
- A user possessing a `SOCIETY`-scoped role (such as `SOCIETY_ADMIN` or `SECRETARY`) is strictly forbidden from granting `SUPER_ADMIN` or any `PLATFORM`-scoped role.
- Only an active user possessing the `SUPER_ADMIN` platform role can assign platform-level capabilities.

### Guard 2: Mandatory Prior Membership Verification
- Before any role can be assigned to a user within a society, the server verifies that the user already possesses an active `UserSocietyMembership` in that specific society (`verify_user_society_membership()`).
- Attempting to assign roles to non-members fails with HTTP 403 (`AUTHORIZATION_ERROR`).

### Guard 3: Insecure Direct Object Reference (IDOR) Mitigation
- All endpoints requiring tenant context validate that URL path parameters (e.g., `/societies/{society_id}`) and `X-Society-ID` headers match.
- If they conflict, the request is aborted with HTTP 400 (`TENANT_CONTEXT_MISMATCH`).
- The authenticated user's membership in the target society is verified on every request, establishing an impenetrable barrier against horizontal privilege escalation.
