# ADR 009: AI Assistant & Voice Integration Boundaries

## Status
Accepted

## Context
AI natural language processing and voice capabilities enhance usability, especially for elderly residents and busy committee members (e.g., summarizing AGM minutes, answering society bye-law FAQs, drafting complaint tickets). 
However, LLM-based autonomous actions pose immense security risks if granted direct database access, bypassed authorization guards, or allowed to perform destructive mutations (e.g., waiving dues, approving unknown visitors, or publishing unvetted notices).

## Decision
1. **Zero Authorization Bypass**:
   - The AI Assistant has **zero direct database access** and zero administrative privilege bypass.
   - Any API call invoked on behalf of a user via AI passes through the exact same HTTP authentication (`JwtAuthGuard`), tenant context (`TenantContextGuard`), and role permissions (`RolesGuard`/`PermissionsGuard`) as the web/mobile UI.
2. **Strict Operation Mode Separation**:
   - **Mode A: Read-Only Query Assistance (Autonomous)**:
     - Society bye-laws lookup, FAQ answering, summarization of public notices, checking personal dues balance.
     - Strictly scoped to data the user is already authorized to read.
   - **Mode B: Mutation Intent Drafting (Human-in-the-Loop Required)**:
     - When a user asks the AI to create a complaint ticket, book an amenity, or submit a payment, the AI only generates a structured draft preview.
     - The application renders an explicit confirmation modal displaying the exact payload, financial implications, and requires explicit user tap/PIN confirmation before executing the mutation.
3. **Audit Trail for AI-Initiated Actions**:
   - Every mutation initiated via AI or voice carries `initiated_via: "AI_VOICE_ASSISTANT"` in the audit record alongside the confirming user's `actor_id`.

## Consequences
### Positive
- Total protection against prompt injection attacks and unauthorized actions.
- Preserves the sanctity of society governance and financial operations.
- Compliant with strict safety, security, and enterprise SaaS governance standards.

### Negative / Trade-offs
- AI cannot perform fully automated hands-off workflows for sensitive operations without user confirmation.
