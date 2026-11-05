# ADR-015: Resident Payments, Receipts & Financial Reconciliation

## Status
Approved

## Context
In SocietySphere Phase 5, the Maintenance Billing engine was implemented, establishing charge rules, billing periods, invoice generation, line items, and journal posting (Debit Accounts Receivable, Credit Maintenance Income).

Phase 6 implements the financial settlement and reconciliation layer:
1. Recording offline and manual resident payments across multiple payment methods (Cash, Bank Transfer/NEFT/RTGS, UPI, Cheque, DD, Card).
2. Clearance and accounting posting lifecycle (`RECORDED` -> `CLEARED` -> `ACCOUNTING POSTED`).
3. Payment allocation to outstanding invoices with strict over-allocation guards.
4. Sequential, immutable payment receipts with cancellation tracking.
5. Non-destructive payment reversal preserving historical allocation audit records (`alloc.status = "REVERSED"`).
6. Safe refund foundation for unallocated balances.
7. Bank and Cash reconciliation sessions with statement line imports, matching against recorded payments, and discrepancy calculation.
8. Internal billing and accounting integrity auditing.

## Decisions

### 1. Payment Lifecycle & Accounting Posting Timing
Payments strictly follow the lifecycle:
```
RECORDED (uncleared instrument) -> CLEARED (verified funds) -> ACCOUNTING POSTED
```
- `RECORDED`: Payment recorded manually/offline (cheque, draft, pending NEFT). Zero GL journal entry is posted while in `RECORDED` status. Cleared Bank/Cash balances are never inflated with uncleared money.
- `CLEARED`: Payment verified as credited into society bank/cash account (via explicit `clear_payment` or bank reconciliation matching). The balanced double-entry GL journal is posted at clearance:
  - **Debit**: Society Bank Account or Cash-in-Hand Account (`target_bank_account_id`).
  - **Credit**: Resident Accounts Receivable (`receivable_account_id`).
  - **Deterministic Idempotency Key**: `PAYMENT:{society_id}:{payment_id}:CLEARED`.
  - **Financial Period Guard**: Posting date must fall within an `OPEN` financial reporting period.
- `ALLOCATED`: Payment amount fully allocated to one or more invoices (`unallocated_amount == 0`).
- `PARTIALLY_ALLOCATED`: Payment partially applied, remaining unallocated amount available.
- `BOUNCED`: Cheque or instrument dishonoured by issuing bank. If recorded only, no GL impact. If cleared, journal reversed.
- `CANCELLED`: Payment voided prior to clearance or allocation.
- `REVERSED`: Cleared/allocated payment reversed due to bounce, dispute, or audit correction.
- `REFUNDED`: Excess or unallocated payment returned to resident.

### 2. Non-Destructive Payment Reversal & Historical Allocation Preservation
- When a payment is reversed, `PaymentAllocation` records are **NEVER deleted**.
- Historical allocations are preserved in place with:
  - `status = "REVERSED"`
  - `reversed_at = datetime.now(UTC)`
  - `reversed_by = user_id`
  - `reversal_reason = reason`
  - `reversal_reference = f"REV:{payment.reference_number}"`
- Invoices have `paid_amount` reduced and `outstanding_amount` restored.
- Payment receipts are marked `status = "CANCELLED"`.
- Phase 4 `JournalService.reverse_journal` posts a balanced mirror reversal journal (`Debit AR, Credit Bank`).

### 3. Safe Refund Foundation
- Foundation implemented:
  - Refunds are restricted to unallocated payment balances (`refund_amount <= payment.unallocated_amount`).
  - If payment was cleared in GL, a balanced refund journal is posted:
    - **Debit**: Accounts Receivable
    - **Credit**: Bank/Cash Account
    - **Key**: `PAYMENT:{society_id}:{payment_id}:REFUND:{idx}`
  - Unallocated amount is reduced; status transitions to `REFUNDED` when balance reaches zero.
  - Append-only audit logging: `BILLING_PAYMENT_REFUNDED`.
- Deferred: Automated bank payout gateway APIs and multi-tier approval workflows.

### 4. Explicit RLS Policies with WITH CHECK & FORCE RLS
- All Phase 6 tenant-owned tables:
  - `payments`
  - `receipts`
  - `payment_allocations`
  - `reconciliation_sessions`
  - `reconciliation_items`
- Enforce explicit `USING` and `WITH CHECK` at the PostgreSQL engine level:
  ```sql
  CREATE POLICY tenant_isolation_{table} ON {table}
  FOR ALL
  USING (society_id = NULLIF(current_setting('app.current_society_id', true), '')::uuid)
  WITH CHECK (society_id = NULLIF(current_setting('app.current_society_id', true), '')::uuid);
  ```
- `FORCE ROW LEVEL SECURITY` is strictly enabled.

### 5. Explicit Non-Goals
- No payment gateway integrations (Razorpay, Stripe, UPI intents) in Phase 6.
- No live bank scraping or automated feeds.
- No AI or automated money calculations.
- No microservices or external ledger sync.

## Consequences
- Total ledger integrity: uncleared funds never inflate bank accounts.
- Complete auditability: all allocations and reversals remain permanently traceable.
- Mathematical invariants hold across all transitions.
