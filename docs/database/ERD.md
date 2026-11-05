# SocietySphere Entity-Relationship Diagram (ERD)

## 1. High-Level Entity Relationship Diagram

The following Mermaid diagram models the relationships across all Phase 2 entities. 
Platform-level entities exist outside tenant boundaries, while Tenant-scoped entities are strictly partitioned by `society_id`.

```mermaid
erDiagram
    %% Platform Level Entities
    User ||--o{ UserSocietyMembership : "holds"
    User ||--o{ UnitOccupancy : "occupies"
    User ||--o{ ResidentProfile : "configures"
    User ||--o{ RoleAssignment : "assigned"
    User ||--o{ AuditLog : "acts in"

    Role ||--o{ RolePermission : "contains"
    Permission ||--o{ RolePermission : "granted in"
    Role ||--o{ RoleAssignment : "allocated to"

    %% Tenant Boundary
    Society ||--o{ Block : "contains"
    Society ||--o{ Floor : "encloses"
    Society ||--o{ Unit : "comprises"
    Society ||--o{ UserSocietyMembership : "members"
    Society ||--o{ UnitOccupancy : "occupancies"
    Society ||--o{ ResidentProfile : "resident preferences"
    Society ||--o{ RoleAssignment : "tenant roles"
    Society ||--o{ AuditLog : "audit records"

    %% Physical Spatial Hierarchy
    Block ||--o{ Floor : "has levels"
    Block ||--o{ Unit : "contains units"
    Floor ||--o{ Unit : "houses flats"

    %% Occupancy Links
    Unit ||--o{ UnitOccupancy : "tenancy history"

    User {
        uuid id PK
        string email UK "nullable"
        string phone UK "nullable"
        string password_hash "nullable"
        string first_name
        string last_name
        string display_name
        string status
        timestamptz created_at
    }

    Society {
        uuid id PK
        string legal_name
        string display_name
        string registration_number "indexed"
        string city
        string state
        string country
        string status
        timestamptz created_at
    }

    Block {
        uuid id PK
        uuid society_id FK
        string code "scoped unique"
        string display_name
        int sequence_order
    }

    Floor {
        uuid id PK
        uuid society_id FK
        uuid block_id FK
        int floor_number "scoped unique"
        string display_name
    }

    Unit {
        uuid id PK
        uuid society_id FK
        uuid block_id FK
        uuid floor_id FK
        string unit_number "scoped unique"
        string unit_type
        float carpet_area_sqft
        string occupancy_status
    }

    UserSocietyMembership {
        uuid id PK
        uuid user_id FK
        uuid society_id FK
        string membership_status
        timestamptz joined_at
    }

    UnitOccupancy {
        uuid id PK
        uuid society_id FK
        uuid unit_id FK
        uuid user_id FK
        string relationship_type
        boolean is_primary_contact
        date valid_from
        date valid_to
        string status
    }

    ResidentProfile {
        uuid id PK
        uuid society_id FK
        uuid user_id FK
        string emergency_contact_name
        string emergency_contact_phone
        jsonb accessibility_preferences
        jsonb communication_preferences
    }

    Role {
        uuid id PK
        string code
        string name
        string scope_type
        boolean is_system_role
    }

    Permission {
        uuid id PK
        string code UK
        string name
        string module
    }

    RolePermission {
        uuid role_id PK,FK
        uuid permission_id PK,FK
    }

    RoleAssignment {
        uuid id PK
        uuid user_id FK
        uuid role_id FK
        uuid society_id FK "nullable for PLATFORM scope"
        string scope_type
        string status
    }

    AuditLog {
        uuid id PK
        uuid society_id FK "nullable for platform actions"
        uuid actor_user_id FK "nullable"
        string action
        string entity_type
        string entity_id
        string correlation_id
        jsonb before_state
        jsonb after_state
        jsonb diff
        timestamptz created_at
    }
```

---

## 2. Structural Isolation Boundaries

```
[PLATFORM SCOPE]
  └── users (Global Identity)
  └── permissions (Global Action Definitions)
  └── roles [scope_type='PLATFORM'] (Platform Super Admin)
  └── audit_logs [society_id IS NULL] (Platform operations)

[TENANT BOUNDARY: Society]
  ├── Physical Spatial Hierarchy
  │     └── blocks -> floors -> units
  ├── Identity Associations
  │     ├── user_society_memberships
  │     ├── unit_occupancies (historical & current)
  │     └── resident_profiles (preferences, emergency contacts)
  ├── Security & Authorization
  │     └── role_assignments [scope_type='SOCIETY', society_id=Society.id]
  └── Audit Records
        └── audit_logs [society_id=Society.id]
```
