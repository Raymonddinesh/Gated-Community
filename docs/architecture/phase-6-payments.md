# SocietySphere — Phase 6: Resident Payments, Receipts & Financial Reconciliation

## 1. Overview & Architecture Boundaries
Phase 6 establishes the settlement and reconciliation layer of SocietySphere. It completes the financial lifecycle initiated by Phase 4 (Accounting & Financial Core) and Phase 5 (Maintenance Billing).

```
   ┌────────────────────────────────────────────────────────┐
   │            Phase 5: Maintenance Billing                │
   │  - Charges, Rules, Invoices, AR Subledger               │
   └──────────────────────────┬─────────────────────────────┘
                              │ Settles
                              ▼
   ┌────────────────────────────────────────────────────────┐
   │         Phase 6: Resident Payments & Receipts          │
   │  - Offline / Manual Payment Recording (Cash, Bank, UPI)│
   │  - Payment Allocations (1:M, M:1)                      │
   │  - Immutable Sequential Receipts (REC-XXXXXX)          │
   │  - Non-Destructive Reversal & Allocation History       │
   │  - Bank & Cash Account Reconciliation                  │
   └──────────────────────────┬─────────────────────────────┘
                              │ Posts Journal
                              ▼
   ┌────────────────────────────────────────────────────────┐
   │          Phase 4: Double-Entry Accounting Core         │
   │  - General Ledger, Balance Sheet, Trial Balance        │
   │  - Debit Bank / Credit Accounts Receivable             │
   └────────────────────────────────────────────────────────┘
```

## 2. Payment Lifecycle & Accounting Posting Timing
The preferred and implemented architecture strictly enforces:
```
RECORDED (Uncleared) ──(Reconciled/Cleared)──> CLEARED ──(Posts GL)──> ALLOCATED / PARTIALLY_ALLOCATED
```

- **RECORDED**: When an offline instrument (cheque, draft, pending NEFT transfer) is recorded, no GL entry is posted. Cleared Bank/Cash balances are never inflated with uncleared money.
- **CLEARED**: When verified as credited in the bank/cash account (via explicit `clear_payment` or bank reconciliation statement matching), the balanced double-entry GL journal is posted:
  - **Debit**: Bank Account (or Cash-in-Hand Account)
  - **Credit**: Resident Accounts Receivable (`receivable_account_id`)
  - **Deterministic Key**: `PAYMENT:{society_id}:{payment_id}:CLEARED`
- **BOUNCED**: If an uncleared cheque bounces, status becomes `BOUNCED` with zero ledger impact. If cleared prior to bounce, journal is reversed.
- **REVERSED**: Posts mirror reversal journal entry (`Debit AR, Credit Bank`) via Phase 4 `JournalService.reverse_journal`.
- **REFUNDED**: Unallocated balance returned to resident, posting balanced payout journal (`Debit AR, Credit Bank`).

## 3. Non-Destructive Allocation Reversal
- Historical `PaymentAllocation` records are **never deleted**.
- Upon payment reversal or bounce:
  - Allocation status transitions to `REVERSED`.
  - Captures `reversed_at`, `reversed_by`, `reversal_reason`, and `reversal_reference`.
  - Invoices have `paid_amount` reduced and `outstanding_amount` restored.
  - Full audit provenance is maintained.

## 4. Reconciliation Architecture
- **Sessions**: Scoped per society and bank account (`ReconciliationSession`), tracking `opening_balance`, `closing_balance`, `reconciled_amount`, and `unreconciled_amount`.
- **Items**: Statement lines (`ReconciliationItem`) categorized as `UNMATCHED`, `MATCHED`, `MISMATCH`, or `EXCLUDED`.
- **Auto-Clearance on Match**: Matching an uncleared payment against a statement credit automatically triggers `clear_payment`, posting GL entries.
- **Closure Safety**: Closed sessions are immutable and reject subsequent modifications.

## 5. Security & Isolation
- **PostgreSQL RLS with WITH CHECK**:
  All tables (`payments`, `receipts`, `payment_allocations`, `reconciliation_sessions`, `reconciliation_items`) enforce:
  - `ENABLE ROW LEVEL SECURITY;`
  - `FORCE ROW LEVEL SECURITY;`
  - `USING (society_id = NULLIF(current_setting('app.current_society_id', true), '')::uuid)`
  - `WITH CHECK (society_id = NULLIF(current_setting('app.current_society_id', true), '')::uuid)`
- **RBAC**:
  - `billing:read` / Resident: Self-service access to own payments and receipts.
  - `billing:admin`, `finance:admin`: Privileged management.
