# ADR-014: Maintenance Billing Lifecycle, Deterministic Invoicing, and General Ledger Integration

## Status
Accepted

## Context
Apartment societies rely on predictable, equitable, and transparent collection of recurring dues (maintenance, sinking funds, amenities, utility charges). Failure to maintain financial discipline leads to disputes, unpaid dues, and cash flow crises.

Previous phases established:
- Multi-tenancy isolation and row-level security (`Phase 2`).
- Identity, session security, and role-based access control (`Phase 3`).
- Double-entry accounting engine with immutable journal entries, balanced vouchers (`Σ Debits == Σ Credits`), and financial period enforcement (`Phase 4`).

Phase 5 introduces the **Maintenance Billing & Resident Financial Obligations** engine. Key architectural challenges include:
1. Multi-tier charge calculation (fixed, per-sqft, unit-type, slab).
2. Deterministic, idempotent invoice generation across billing periods (preventing duplicate billing for the same unit and period).
3. Explicit invoice lifecycle: `DRAFT -> REVIEW/GENERATED -> APPROVED -> PUBLISHED -> PAID / PARTIALLY_PAID / OVERDUE / CANCELLED`.
4. Strict immutability of published invoices with formal adjustments and credit/debit notes.
5. Deterministic late fee calculations without compounding or double charging.
6. Multi-method payment recording and allocation (FIFO and explicit per-invoice allocation) with per-society sequential receipts.
7. Seamless bridge to Phase 4 `JournalService` for dual-entry financial ledger postings on invoice publication and payment collection.
8. Resident financial visibility protected against Insecure Direct Object References (IDOR).
9. Total isolation from live payment gateways (Razorpay, Stripe) and live external Tally transport at this phase.

## Decision

### 1. Separation of Billing Domain from Core Accounting Ledger
Maintenance billing is modeled as an operational sub-domain that integrates into the Phase 4 General Ledger:
- Billing records operational intent: `SocietyBillingConfig`, `MaintenanceChargeRule`, `BillingPeriod`, `Invoice`, `InvoiceLine`, `BillingAdjustment`, `CreditDebitNote`, `Payment`, `PaymentAllocation`, `Receipt`.
- When an invoice is published, the billing domain invokes the Phase 4 `JournalService` to create a `POSTED` journal entry:
  - **Debit**: Accounts Receivable (1200)
  - **Credit**: Respective Revenue Accounts (4100 Maintenance Income, 4200 Sinking Fund, etc. configured on each rule).
- When a payment is recorded, the billing domain invokes `JournalService`:
  - **Debit**: Bank or Cash Account (1100 or 1110)
  - **Credit**: Accounts Receivable (1200).
- Credit and debit notes similarly emit balanced journal vouchers.

### 2. Deterministic & Idempotent Invoice Generation
- Invoices are scoped to `(society_id, billing_period_id, unit_id)` enforced via database unique constraints (`uq_invoices_period_unit`).
- Batch generation inspects active charge rules, active unit occupancies (or primary owners if vacant), and generates line items freezing calculation rate snapshots.
- Re-running invoice generation skips already generated units, ensuring strict idempotency.

### 3. Immutability & Adjustments
- Once an invoice transitions to `PUBLISHED`, its core line items, subtotal, and tax cannot be edited or deleted (`InvoiceImmutableException`).
- Adjustments (discounts, waivers, surcharges) are modeled as distinct child entities (`BillingAdjustment`) with mandatory audit reasons and approver IDs.
- Substantive billing corrections emit `CreditDebitNote` records referencing the original invoice, adjusting the outstanding balance and posting offsetting journal entries.

### 4. Deterministic Allocation & Receipts
- Payments record the full amount collected and maintain unallocated balances.
- Allocation engine supports FIFO (oldest unpaid invoice first) and explicit allocation to targeted invoices.
- Total allocations cannot exceed payment amount (`PaymentOverAllocationException`) nor target invoice outstanding amount.
- Allocation across different societies is strictly rejected (`CrossTenantBillingException`).
- Receipts are issued with society-scoped sequential receipt numbers (`RCP-000001`).

### 5. Deterministic Late Fee Engine
- Billing configuration defines grace period days and late fee policy (Percentage vs. Fixed).
- Overdue evaluation checks invoice due date against current date; late fee lines or debit notes are applied idempotently with tracking flags to prevent duplicate assessments.

### 6. Strict Tenant Isolation and PostgreSQL RLS
- All 10 billing tables enforce `FORCE ROW LEVEL SECURITY` with tenant-scoped policies checking `app.current_society_id`.
- Foreign keys and domain queries enforce that units, periods, rules, users, accounts, and payments belong strictly to the same society.

### 7. Resident Visibility and IDOR Protection
- Residents are restricted to querying invoices, payments, and receipts where `responsible_user_id == current_user.id` or matching their occupied units.
- Attempts to inspect other units' invoices return 404 or 403.
- Committee/admin members retain society-wide access controlled by `billing.invoices.view_all` and `billing.reports.view`.

## Consequences
- **Positive**:
  - Full auditability: Operational billing and general ledger accounting remain synchronized and verifiable.
  - Financial consistency: All debits equal credits at every financial event.
  - Zero financial discrepancies from rounding or floating point errors due to mandatory 4-decimal `Decimal` quantization.
  - Resident trust: Clear itemized breakdowns, immutable receipts, and complete historical ledger tracking.
- **Negative / Trade-offs**:
  - Operational overhead: Invoices cannot simply be modified post-publication; adjustments or credit notes must be issued.
  - Two-stage lifecycle: Invoicing requires approval before publication if configured.
