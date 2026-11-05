# ADR 004: Immutable Financial Ledger & Audit Trail Strategy

## Status
Accepted

## Context
Housing societies handle millions of rupees in maintenance dues, sinking funds, vendor disbursements, and penalty assessments. Disputes between residents, treasurers, and auditors are frequent. 
Under legal cooperative housing society acts and financial accounting standards:
1. Financial entries must be permanently traceable.
2. Hard deletes of financial records, invoices, or transactions are unacceptable.
3. Every sensitive administrative action (penalty waivers, dues revisions, gate approvals) must record an indelible audit trail.

## Decision
1. **Double-Entry General Ledger**:
   - Every financial transaction records balancing debit and credit entries in `ledger_lines`.
   - Invariant: $\sum \text{Debit} = \sum \text{Credit}$ enforced within an ACID database transaction.
   - Financial entries have no `deleted_at` column; they are **strictly append-only**.
   - Corrections require explicit reversing journal entries (credit notes or debit notes) with an associated reason and authorized committee sign-off.
2. **Audit Logging Framework**:
   - An append-only `audit_logs` table records every state change on operational and governance entities.
   - Captured metadata: `actor_id`, `actor_role`, `society_id`, `resource_type`, `resource_id`, `action`, `before_state`, `after_state`, `diff`, `ip_address`, `user_agent`, `created_at`.
   - Audit logs are written via an asynchronous NestJS Interceptor with direct database writes to guarantee no user action completes without audit registration.
   - Audit tables are partitioned monthly and configured with PostgreSQL `REVOKE DELETE, UPDATE` privileges for regular application database roles to prevent tampering.

## Consequences
### Positive
- 100% compliance with cooperative housing society audit norms.
- Incontrovertible financial reconciliation and fraud prevention.
- Comprehensive forensic analysis for any gate security or administrative anomalies.

### Negative / Trade-offs
- Increased storage footprint over time; mitigated by PostgreSQL monthly table partitioning and cold storage archival after 7 years.
