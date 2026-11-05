# ADR 001: Multi-Tenancy Isolation Strategy

## Status
Accepted

## Context
SocietySphere is a multi-tenant SaaS application serving multiple independent apartment societies, gated communities, and housing cooperatives. 
A critical requirement is that society data must never leak across tenants under any circumstances (including bugs in application-level queries). 
Furthermore, the architecture must support hundreds of societies cost-effectively without connection pool exhaustion or unmanageable database migration overhead.

We considered three tenancy models:
1. **Database-per-Tenant**: Highest isolation, but unacceptable operational overhead, high infrastructure cost for small societies, and connection pool starvation.
2. **Schema-per-Tenant**: Moderate isolation, but executing schema migrations across hundreds of schemas becomes slow, risky, and error-prone.
3. **Shared Database, Shared Schema with Discriminator Column (`society_id`) & PostgreSQL Row-Level Security (RLS)**: Highly scalable, unified migrations, defense-in-depth isolation enforced at the database kernel level.

## Decision
We adopt **Shared Database, Shared Schema with `society_id` and PostgreSQL Row-Level Security (RLS)**:
1. Every tenant-owned table contains `society_id UUID NOT NULL REFERENCES societies(id)`.
2. All database connections set a local session variable upon executing tenant requests:
   ```sql
   SET LOCAL app.current_society_id = 'c4b8e21a-...';
   ```
3. PostgreSQL Row-Level Security is enabled on all tenant tables:
   ```sql
   ALTER TABLE units ENABLE ROW LEVEL SECURITY;
   CREATE POLICY tenant_isolation_policy ON units
     USING (society_id = NULLIF(current_setting('app.current_society_id', true), '')::uuid);
   ```
4. The backend sets `app.current_society_id` via session-level execution inside the transactional unit of work.
5. **Tenant Context Security Rule**: The incoming `X-Society-ID` header is strictly an unverified client context hint. The backend must independently verify the user's active membership before setting tenant scope or executing RLS queries. Mismatched or unauthorized hints are immediately rejected with HTTP 403.

## Consequences
### Positive
- **Guaranteed Isolation**: Even if an application query forgets `where: { societyId }`, the database engine automatically restricts the results to the tenant set in `app.current_society_id`.
- **Streamlined Migrations**: One single migration command updates all tenants simultaneously in standard CI/CD.
- **Resource Efficiency**: Single database connection pool shared across tenants, maximizing query throughput and minimizing hosting cost.

### Negative / Trade-offs
- Super Admin operations that span multiple societies require explicit bypass role execution (`SET LOCAL app.bypass_rls = 'on'`) with strict audit logging.
- Requires PostgreSQL-specific RLS features; precludes switching to non-relational or RLS-incapable databases.
