# Maintenance Billing & Resident Financial Obligations Specification

## Overview
The Maintenance Billing module coordinates recurring and ad-hoc assessment generation for units within an apartment society. It maintains a deterministic bridge between property occupancies and the general ledger accounting system.

## 1. Domain Entities & Database Architecture

The billing sub-domain consists of 10 tenant-scoped tables protected by PostgreSQL Row Level Security:

1. `society_billing_configs`: Society-level billing preferences, frequencies, due days, grace periods, late fee structures, and default GL accounts.
2. `maintenance_charge_rules`: Rules defining how maintenance is calculated (FIXED, PER_SQFT, UNIT_TYPE, SLAB), rates, applicable accounting income accounts, and effective dates.
3. `billing_periods`: Distinct time periods (e.g., Monthly `2026-04`) tracking statuses `OPEN`, `GENERATED`, `CLOSED`, and `LOCKED`.
4. `invoices`: Master invoice records tracking billing period, unit, responsible party, amounts (subtotal, grand total, paid, outstanding), status, and general ledger journal link.
5. `invoice_lines`: Detailed line items freezing calculation rate snapshots and rule parameters.
6. `billing_adjustments`: Formal audit records for waivers, discounts, or surcharges applied to an invoice.
7. `credit_debit_notes`: Formal balance adjustments linked to general ledger journal vouchers.
8. `payments`: Record of funds received from residents via cash, bank transfer, cheque, or UPI (manual).
9. `payment_allocations`: Mapping attributing payments towards specific invoices.
10. `receipts`: Sequential, immutable receipts generated for payments.

## 2. Calculation Engine

The calculation engine supports 4 calculation models:
- **FIXED**: Flat charge per unit (e.g., ₹3,000 / month).
- **PER_SQFT**: Pro-rated charge based on unit super built-up or carpet area (e.g., ₹3.50 / sqft).
- **UNIT_TYPE**: Specific rate based on unit classification (`1BHK`, `2BHK`, `3BHK`, `PENTHOUSE`, `VILLA`, `COMMERCIAL`).
- **SLAB / HYBRID**: Tiered calculations for utility meters or consumption tiers.

All calculations use Python `Decimal` quantized to 4 decimal places (`Decimal("0.0000")`), preventing floating-point imprecision.

## 3. Invoice Lifecycle State Machine

```
[ OPEN PERIOD ]
       │
       ▼ (Batch Generation)
   [ DRAFT ] ── (If approval required) ──► [ REVIEW / GENERATED ]
       │                                            │
       │                                            ▼ (Admin / Treasurer Approval)
       └───────────────────────────────────► [ APPROVED ]
                                                    │
                                                    ▼ (Publish & Post to GL)
                                              [ PUBLISHED ]
                                                    │
                             ┌──────────────────────┴──────────────────────┐
                             ▼                                             ▼
                 (Partial / Full Payment)                          (Past Due Date)
                             ▼                                             ▼
               [ PARTIALLY_PAID / PAID ]                              [ OVERDUE ]
                                                                           │
                                                                           ▼ (Apply Late Fee)
                                                                    [ LATE FEE APPLIED ]
```

### Invariant Rules:
1. **Immutability**: Invoices in `PUBLISHED` or downstream statuses cannot have their line items, unit, or period modified.
2. **Posting Balance**: Every invoice published creates an accounting journal voucher where:
   $$\text{Debit}(\text{Accounts Receivable}) = \sum \text{Credit}(\text{Line Item Income Accounts})$$
3. **Adjustment Traceability**: Adjustments do not delete lines; they append audit records that reduce or increase `outstanding_amount`.

## 4. Payment Recording & Allocation

- **Recording**: Payments can be logged by Treasurer or Admin with transaction references. An unallocated balance is maintained.
- **Allocation**:
  - **FIFO Allocation**: Automatically settles the oldest overdue invoices for the specified unit.
  - **Explicit Allocation**: The payer or administrator attributes specific portions of the payment to specific invoices.
- **Over-allocation Protection**: System asserts $\sum \text{Allocations} \le \text{Payment Amount}$.
- **Accounting Posting**:
  $$\text{Debit}(\text{Bank / Cash}) = \text{Credit}(\text{Accounts Receivable})$$

## 5. Security & IDOR Protections

1. **PostgreSQL RLS**: All 10 tables enforce `tenant_id = app.current_society_id`.
2. **Tenant Context Verification**: Cross-tenant requests are intercepted at the API gateway layer.
3. **Resident Self-Service Restrictions**:
   - Residents can only list and view invoices and receipts tied to their own user ID or their occupied units.
   - Residents cannot trigger billing generation, approve billing periods, modify rules, post adjustments, or view other residents' balances.
   - Resident attempts to access foreign invoices return HTTP 403 Forbidden or 404 Not Found.
