# ADR 003: Authentication & Multi-Role Authorization Strategy

## Status
Accepted

## Context
SocietySphere caters to 13 distinct personas, many of whom hold multiple contextual roles (e.g., an Owner in Society A who is simultaneously a Tenant in Society B, or an Owner who is elected as Society Secretary). 
Authorization decisions must never depend on frontend visibility controls. 
Session revocation must be instantaneous when a resident vacates or when a staff/security guard is dismissed.

## Decision
1. **Authentication Flow**:
   - Primary credential verification yields an Identity JWT Access Token (15-minute TTL) containing the user's global ID and verified identity.
   - Long-lived Rotating Refresh Tokens (7-day TTL) are securely hashed and stored in Redis with client device fingerprinting (`device_id`, `ip_address`, `user_agent`).
   - Session revocation is immediate by deleting or blacklisting the refresh token key in Redis.
2. **Contextual Society Scoping**:
   - A user selects their active Society context from their authorized societies list.
   - The backend validates membership and issues a `Context Token` (or handles `X-Society-ID` verification on every request) linking the user to their specific `UserSocietyRole` and unit mapping.
3. **Authorization Pipeline**:
   - **Authentication Guard**: Validates JWT signature, expiration, and ensures token is not in Redis revocation blacklist.
   - **Tenant Context Guard**: Ensures the user belongs to the requested `society_id` and sets tenant state.
   - **Hierarchical RBAC Guard**: Checks whether the user holds one of the required roles (`@Roles(Role.TREASURER, Role.SOCIETY_ADMIN)`).
   - **Fine-Grained Permission Guard (ABAC/PBAC)**: Evaluates granular capabilities (e.g., `BILLING_WRITE`, `GATE_PASS_APPROVE`).
   - **Resource Ownership Guard**: Ensures residents can only view/mutate their own unit records, complaints, or visitor approvals.

## Consequences
### Positive
- Strict isolation of identities across multiple societies.
- High security: compromised tokens expire in 15 minutes, and rogue sessions can be terminated instantly via Redis.
- Granular permission checking prevents privilege escalation.

### Negative / Trade-offs
- Users associated with multiple units or societies must switch context when performing actions in different societies.
