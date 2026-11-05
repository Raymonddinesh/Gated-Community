# SocietySphere — Phase 21E: Final Architecture Approval Specification
**Document ID:** `SOCIETYSPHERE_PHASE_21E_FINAL_ARCHITECTURE_APPROVAL`  
**Roles:** Principal FinTech Architect & PostgreSQL Security Architect  
**Status:** Architecture Approved — Ready for Phase 21E.1 Implementation Authorization  
**Scope:** SaaS Platform Billing & Subscription Lifecycle Management  
**Compliance Baseline:** PostgreSQL 16 `FORCE RLS`, Unprivileged `app_user` (`NOSUPERUSER`, `NOBYPASSRLS`), Indian GST Act 2017, PCI-DSS SAQ A  

---

## 1. Executive Summary & Architecture Baseline

This specification establishes the final, production-grade architectural design for **Phase 21E: SaaS Billing & Subscription Lifecycle Management** of the SocietySphere SaaS platform.

### Core Architectural Decisions & Invariants
1. **Domain Isolation**: Absolute decoupling between **Domain A** (resident maintenance billing, unit ledgers, society bank accounts in `invoices`, `payments`, `journal_entries`) and **Domain B** (B2B SaaS subscription billing between SocietySphere Ltd and tenant societies in `platform_*` tables). Zero shared foreign keys, zero shared tables.
2. **Subscription State Machine Independence**: `Society.status` (`ACTIVE`, `SUSPENDED`) and `SocietySubscription.status` (`TRIAL`, `ACTIVE`, `PAST_DUE`, `SUSPENDED`, `CANCELLED`) are completely independent state machines. Payment success clears billing delinquency, but **never** reactivates an administratively suspended society.
3. **Cancelled Subscription Invariant**: A `CANCELLED` subscription is terminal and **never** silently reactivated. Webhook events arriving for cancelled subscriptions are acknowledged (HTTP 200) to prevent gateway retry storms, verified, durably persisted, and processed for automated refunds.
4. **PostgreSQL Security**: Strict `FORCE ROW LEVEL SECURITY` on all tenant-owned billing tables. The application database user (`app_user`) operates with `NOSUPERUSER` and `NOBYPASSRLS`. Zero platform-admin RLS bypass policies; platform operations utilize the trusted session context `SELECT set_config('app.current_society_id', :id, true)`.
5. **Deterministic Concurrency & Webhooks**: Replaced 32-bit hash locks with deterministic 64-bit signed integer advisory locks (`pg_try_advisory_xact_lock(bigint)`). Database unique constraints `(gateway_provider, event_id)` remain the primary duplicate prevention mechanism.
6. **Legally Rigorous Invoicing & Proration**: Gapless fiscal-year sequence allocation strictly at invoice finalization. Deterministic second-accurate proration in UTC with IST (`Asia/Kolkata`) calendar boundaries, `ROUND_HALF_UP` commercial rounding, and Indian GST rules.

---

## 2. Sequential vs. Legally Gapless Invoice Numbering Architecture

### 2.1 Sequential Numbering vs. Legally Gapless Numbering
* **Sequential Numbering (Technical)**: Monotonically increasing numbers (e.g. 1, 2, 3...) allocated by database sequences or auto-incrementing integers. In PostgreSQL, standard sequences (`CREATE SEQUENCE`) allocate numbers outside transaction rollback boundaries. If an `INSERT` aborts, rolls back, or encounters an exception, the allocated number is lost forever, resulting in physical sequence gaps (e.g. `SS-2627-00001`, `SS-2627-00002`, `SS-2627-00004`).
* **Legally Gapless Numbering (Statutory)**: Under Section 31 of the Central Goods and Services Tax (CGST) Act, 2017 read with Rule 46(b) of the CGST Rules, 2017, a tax invoice must contain:
  > *"a consecutive serial number not exceeding sixteen characters, in one or multiple series, containing only alphabets or numerals or special characters... unique for a financial year"*.
  
  Tax authorities consider unexplained gaps in tax invoice sequences prima facie evidence of suppressed sales, unrecorded cash transactions, or tax evasion, exposing the company to statutory penalties and scrutiny under Section 122 of the CGST Act.
* **Engineering Reality & Legal Disclaimer**: In software engineering, gaplessness can be guaranteed within the database boundary by locking a sequence counter within the finalization transaction. However, **no software system can claim "certified legal gaplessness" without formal validation and procedural sign-off by a licensed Chartered Accountant (CA) or Tax Legal Counsel**, as legal compliance requires business continuity controls, void reconciliation registers, and audit-approved operational runbooks.

```
+---------------------------------------------------------------------------------------------------+
|                               INVOICE NUMBERING LIFECYCLE                                        |
+---------------------------------------------------------------------------------------------------+
|  [ DRAFT INVOICE CREATION ]                                                                       |
|  - Status: DRAFT                                                                                  |
|  - invoice_number: NULL (or provisional UUID draft ref)                                          |
|  - Uncommitted line items, recalculations, or deletions do NOT touch sequence counter.           |
+---------------------------------------------------------------------------------------------------+
                                              |
                                              v
+---------------------------------------------------------------------------------------------------+
|  [ INVOICE FINALIZATION TRANSACTION (ATOMIC) ]                                                    |
|  1. BEGIN TRANSACTION (ISOLATION LEVEL READ COMMITTED)                                            |
|  2. SELECT current_sequence FROM platform_invoice_sequences                                       |
|     WHERE fiscal_year = :fy FOR UPDATE;  <-- EXCLUSIVE ROW LOCK ON FY COUNTER                     |
|  3. next_sequence = current_sequence + 1                                                          |
|  4. formatted_number = 'SS-' || :fy || '-' || LPAD(next_sequence::text, 5, '0')                   |
|  5. UPDATE platform_invoice_sequences SET current_sequence = next_sequence WHERE fiscal_year = :fy|
|  6. UPDATE platform_invoices SET invoice_number = formatted_number, status = 'ISSUED',             |
|     issued_at = now() WHERE id = :invoice_id AND invoice_number IS NULL;                          |
|  7. COMMIT;                                                                                       |
+---------------------------------------------------------------------------------------------------+
                                              |
                     +------------------------+------------------------+
                     |                                                 |
                     v                                                 v
      [ SUCCESSFUL COMMIT ]                                  [ TRANSACTION FAILURE ]
      - Sequence counter advances.                           - Transaction rolls back.
      - Number permanently issued.                           - Row lock released.
      - Never reused or deleted.                             - Counter DOES NOT advance.
      - Guaranteed zero technical gap.                       - Zero gap created.
```

### 2.2 Sequence Counter Locking Table
A dedicated counter table guarantees single-threaded, concurrency-safe counter incrementation per Indian Financial Year (April 1 to March 31):

```sql
CREATE TABLE platform_invoice_sequences (
    fiscal_year VARCHAR(10) PRIMARY KEY, -- e.g., '2627' for FY 2026-2027
    current_sequence INTEGER NOT NULL DEFAULT 0,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);
```

### 2.3 Numbering Invariants and Rules
1. **Allocation Strictly at Finalization**: A draft invoice has `invoice_number = NULL`. An invoice receives a number only when transitioning to `ISSUED` status.
2. **Atomic Transaction Scope**: The sequence lock (`SELECT ... FOR UPDATE`), counter increment, and invoice update execute in the exact same database transaction.
3. **Global Uniqueness**: `platform_invoices` enforces `CONSTRAINT uq_platform_invoices_number UNIQUE (invoice_number)`.
4. **No Reuse of Issued Numbers**: Once committed, an invoice number is permanently consumed. Even if the invoice is voided or cancelled, its number is never reallocated.
5. **Voided Invoice Retention**: Cancelled invoices are marked `status = 'VOID'` or reversed via `platform_credit_notes`. The original record remains in `platform_invoices` permanently for tax reconciliation.
6. **Immutable Audit Trail**: Every sequence increment and status transition is recorded in `platform_subscription_audit_logs`.

---

## 3. Cancelled Subscription and Late Payment Workflow

### 3.1 Problem Definition
A society cancels its subscription at $T_0$ (`SocietySubscription.status = 'CANCELLED'`). At $T_1 > T_0$, a delayed recurring charge, mandate settlement (e.g. NACH / UPI Autopay), or asynchronous bank transfer is captured by the gateway. The gateway fires a `payment.captured` webhook.

### 3.2 Resilient Webhook Ingestion & HTTP Acknowledgment
* **Gateway Acknowledgment Requirement**: If SocietySphere returns HTTP 409 Conflict or 5xx, payment gateways (Razorpay, Stripe) treat the delivery as failed and initiate aggressive exponential retry storms for up to 72 hours.
* **Resilient Solution**: Because the incoming webhook represents a real-world financial transaction captured on banking rails, SocietySphere **must durably record the event and return HTTP 200 OK**, while triggering an automated refund workflow rather than rejecting the payload.

```
[ Gateway Webhook: payment.captured ]
                 |
                 v
[ 1. Verify HMAC-SHA256 Signature ]
                 |
                 v
[ 2. Deterministic 64-Bit Advisory Lock: pg_try_advisory_xact_lock(bigint) ]
                 |
                 v
[ 3. Idempotent Deduplication Check in platform_webhook_events ]
     - If already PROCESSED: Return HTTP 200 OK immediately.
                 |
                 v
[ 4. Query Provider REST API to Validate Captured Payment ]
                 |
                 v
[ 5. Record Payment in platform_payments (status = 'CAPTURED') ]
     - Mark reconciliation_status = 'ORPHAN_ON_CANCELLED_SUBSCRIPTION'
                 |
                 v
[ 6. Inspect SocietySubscription.status ]
     - Status == 'CANCELLED'
     - INVARIANT ENFORCED: Subscription status REMAINS 'CANCELLED'
     - Society.status is NOT MODIFIED
                 |
                 v
[ 7. Evaluate Explicit Refund Policy ]
     - Standard Policy: Immediate Automated Gateway Refund
                 |
                 v
[ 8. Execute Gateway Refund API Call: gateway.refund(...) ]
     +----------------------------------+----------------------------------+
     | (Refund API Success)                                                | (Refund API Error/Timeout)
     v                                                                     v
[ 9A. Record platform_refunds ]                                   [ 9B. Record platform_refunds ]
      - status = 'COMPLETED'                                            - status = 'PENDING_RETRY'
      - gateway_refund_id populated                                     - Queue for background reconciliation
      - platform_payments.status = 'REFUNDED'                           - Alert Platform Operations
                 |                                                                 |
                 +----------------------------------+------------------------------+
                                                    |
                                                    v
[ 10. Update platform_webhook_events: processing_status = 'PROCESSED_REFUND_INITIATED' ]
[ 11. Record platform_subscription_audit_logs ]
[ 12. Return HTTP 200 OK to Gateway ]  <-- Stops Gateway Retry Storms
```

### 3.3 Strict Lifecycle Invariants
1. **Never Reactivate Cancelled Subscription**: The subscription remains in `CANCELLED` status. Late payment captured by a gateway does not revive access.
2. **Society Isolation**: `Society.status` remains unaffected.
3. **Explicit Refund Audit**: The refund is recorded as a dedicated entity in `platform_refunds` with full gateway references (`gateway_refund_id`), preserving complete ledger traceability.

---

## 4. Webhook Concurrency & Deterministic 64-Bit Advisory Locking

### 4.1 Flaws of 32-Bit `hashtext(:event_id)`
PostgreSQL `hashtext()` outputs a signed 32-bit integer (`int4`, range $-2^{31}$ to $2^{31}-1$). Under the Birthday Paradox, a 32-bit space exhibits a 50% collision probability after only $\approx 77{,}000$ distinct webhook events. Two entirely distinct webhooks for different societies or gateways colliding on the same 32-bit hash would falsely block or abort each other.

### 4.2 Deterministic 64-Bit Signed Integer Lock Strategy
PostgreSQL provides `pg_try_advisory_xact_lock(bigint)` which accepts a 64-bit signed integer (`int8`). The collision space expands to $2^{64}$ ($1.84 \times 10^{19}$ values), where $50\%$ collision probability requires $2^{32} \approx 4.3 \times 10^9$ webhook events.

#### Python Key Derivation:
```python
import hashlib
import struct

def derive_webhook_lock_key(gateway_provider: str, event_id: str) -> int:
    """
    Derives a deterministic signed 64-bit integer from gateway_provider and event_id.
    Uses SHA-256 truncated to 8 bytes and unpacked as a big-endian signed 64-bit integer.
    """
    digest = hashlib.sha256(f"{gateway_provider}:{event_id}".encode("utf-8")).digest()
    return struct.unpack(">q", digest[:8])[0]
```

#### SQL Advisory Lock Invocation:
```sql
SELECT pg_try_advisory_xact_lock(:lock_key) AS acquired;
```

### 4.3 Primary Defense vs. Lock Optimization
1. **Primary Correctness Mechanism**: Database uniqueness constraint `CONSTRAINT uq_platform_webhook_provider_event UNIQUE (gateway_provider, event_id)` on `platform_webhook_events`. The database constraint is absolute, ACID-enforced, and authoritative.
2. **Secondary Lock Role**: The non-blocking advisory lock is an optimization to prevent duplicate concurrent workers from executing redundant signature verifications and duplicate gateway REST API requests.

### 4.4 Lock Acquisition Failure & Retry Protocol
When `pg_try_advisory_xact_lock` returns `false`:
1. Another worker is currently processing this exact webhook event.
2. The waiting worker pauses for 500ms and queries `platform_webhook_events` for `(gateway_provider, event_id)`.
3. If the record exists and `processing_status IN ('PROCESSED', 'PROCESSED_REFUND_INITIATED', 'SKIPPED')`:
   - Return **HTTP 200 OK** immediately with body `{"status": "already_processed"}` (idempotent duplicate acknowledgment).
4. If the record is still in `PROCESSING` after a 2-second timeout:
   - Return **HTTP 429 Too Many Requests** with header `Retry-After: 5`. The gateway will retry cleanly after the active worker commits.

---

## 5. Comprehensive Table-by-Table PostgreSQL RLS & Security Matrix

All tenant-scoped tables enforce `FORCE ROW LEVEL SECURITY`. The database application role (`app_user`) operates under strict `NOSUPERUSER` and `NOBYPASSRLS`. Zero RLS bypass policies are permitted.

| # | Table Name | Scope | `society_id` Column | RLS Status | Tenant Context Required | Platform Service Authorization | Unique Constraints | Audit Trail Requirement |
|---|---|---|---|---|---|---|---|---|
| 1 | `platform_invoices` | Tenant | `UUID NOT NULL REFERENCES societies(id)` | **FORCE RLS** | Yes (`app.current_society_id`) | Platform `SUPER_ADMIN` via trusted session context | `UNIQUE (invoice_number)` | State transitions logged to `platform_subscription_audit_logs` |
| 2 | `platform_invoice_items` | Tenant | `UUID NOT NULL REFERENCES societies(id)` | **FORCE RLS** | Yes (`app.current_society_id`) | Platform `SUPER_ADMIN` via trusted session context | `UNIQUE (invoice_id, item_index)` | Immutable once invoice `ISSUED` |
| 3 | `platform_payments` | Tenant | `UUID NOT NULL REFERENCES societies(id)` | **FORCE RLS** | Yes (`app.current_society_id`) | Platform `SUPER_ADMIN` & Webhook Settlement Worker | `UNIQUE (gateway_provider, gateway_payment_id)` | Financial audit log on payment capture |
| 4 | `platform_payment_attempts` | Tenant | `UUID NOT NULL REFERENCES societies(id)` | **FORCE RLS** | Yes (`app.current_society_id`) | Platform `SUPER_ADMIN` & Checkout Service | `UNIQUE (gateway_order_id)` | Ephemeral checkout tracking |
| 5 | `platform_refunds` | Tenant | `UUID NOT NULL REFERENCES societies(id)` | **FORCE RLS** | Yes (`app.current_society_id`) | Platform `SUPER_ADMIN` & Settlement Worker | `UNIQUE (gateway_refund_id)` | Full financial audit on refund completion |
| 6 | `platform_credit_notes` | Tenant | `UUID NOT NULL REFERENCES societies(id)` | **FORCE RLS** | Yes (`app.current_society_id`) | Platform `SUPER_ADMIN` via trusted session context | `UNIQUE (credit_note_number)` | Legal GST credit note register |
| 7 | `platform_billing_adjustments` | Tenant | `UUID NOT NULL REFERENCES societies(id)` | **FORCE RLS** | Yes (`app.current_society_id`) | Platform `SUPER_ADMIN` via trusted session context | `UNIQUE (idempotency_key)` | Adjustment reason & actor tracking |
| 8 | `platform_subscription_history` | Tenant | `UUID NOT NULL REFERENCES societies(id)` | **FORCE RLS** | Yes (`app.current_society_id`) | Platform `SUPER_ADMIN` via trusted session context | None (Append-only) | Immutable lifecycle state transition log |
| 9 | `platform_subscription_audit_logs`| Tenant | `UUID NOT NULL REFERENCES societies(id)` | **FORCE RLS** | Yes (`app.current_society_id`) | Platform `SUPER_ADMIN` via trusted session context | None (Append-only) | Sensitive data redacted (PCI-DSS compliant) |
| 10| `platform_webhook_events` | Global | `UUID NULL REFERENCES societies(id)` | **NO RLS** | No (Global ingestion table) | Internal Webhook Ingestion Service only | `UNIQUE (gateway_provider, event_id)` | Raw payload & processing status tracked |
| 11| `platform_payment_gateway_configs`| Global | `None` (Platform Merchant Config) | **NO RLS** | No (Global platform configuration) | Platform `SUPER_ADMIN` only | `UNIQUE (gateway_provider)` | Encrypted credentials; key rotation logged |
| 12| `platform_invoice_sequences` | Global | `None` (Fiscal Year Counter) | **NO RLS** | No (Global sequence counter) | Invoice Finalization Service only | `PRIMARY KEY (fiscal_year)` | Sequential increment tracking |

### 5.1 RLS Policy Definition for Tenant Tables
For each of the 9 tenant-scoped tables above, the exact RLS policy applied in Migration 0022 is:
```sql
ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;
ALTER TABLE {table} FORCE ROW LEVEL SECURITY;

CREATE POLICY {table}_tenant_isolation ON {table}
    USING (society_id = NULLIF(current_setting('app.current_society_id', true), '')::uuid);
```

---

## 6. Deterministic Proration, Timezone & GST Mathematical Rules

### 6.1 Timezone & Calendar Boundaries
* **Storage Standard**: All timestamps are stored in UTC (`TIMESTAMP WITH TIME ZONE`).
* **Operational Business Calendar**: `Asia/Kolkata` (Indian Standard Time, UTC+05:30).
* **Period Boundaries**: Billing cycles start at `00:00:00 IST` on the 1st of the cycle month and end at `23:59:59.999999 IST` on the final day.

### 6.2 Leap Year & Period Duration Handling
Proration avoids calendar-day approximations by computing the exact ratio of remaining seconds to total seconds in the billing period using UTC epoch timestamps:
$$\Delta t_{\text{total}} = \text{epoch}(t_{\text{period\_end\_utc}}) - \text{epoch}(t_{\text{period\_start\_utc}})$$
$$\Delta t_{\text{remaining}} = \max\left(0, \text{epoch}(t_{\text{period\_end\_utc}}) - \text{epoch}(t_{\text{effective\_utc}})\right)$$
$$\text{proration\_fraction} = \frac{\Delta t_{\text{remaining}}}{\Delta t_{\text{total}}}$$

* **Leap Year Exactness**: In a leap year (e.g. 2028), February automatically contains $29 \times 86{,}400 = 2{,}505{,}600$ seconds. In a non-leap year, February contains $28 \times 86{,}400 = 2{,}419{,}200$ seconds. The second-accurate calculation is mathematically exact in all cases.

### 6.3 Currency Precision & Rounding Rules
* **Intermediate Precision**: Ratios and unrounded amounts are calculated using Python `decimal.Decimal` with 8 decimal places.
* **Rounding Algorithm**: Python `decimal.ROUND_HALF_UP` (commercial rounding: 0.5 rounds away from zero, standard in Indian tax accounting).
* **Final Precision**: All persisted monetary fields are rounded to 2 decimal places (`Numeric(12, 2)`). Intermediate fractions are never rounded prematurely.

### 6.4 Mathematical Tax Ordering
Tax computation follows strict statutory ordering:
```
1. Base Plan Cost (Target Plan)                     = P_new
2. Less: Prorated Credit from Unused Old Plan       = C_prorated
3. Less: Pre-tax Promotional Discount               = D_pretax
------------------------------------------------------------------
4. Net Taxable Value (NTV)                          = max(0.00, P_new - C_prorated - D_pretax)
------------------------------------------------------------------
5. GST Liability Calculation on NTV:
   Case A: Intra-State Supply (POS == Supplier State)
     - CGST (9%)                                    = ROUND_HALF_UP(NTV * 0.09, 2)
     - SGST (9%)                                    = ROUND_HALF_UP(NTV * 0.09, 2)
     - Tax Total                                    = CGST + SGST
   Case B: Inter-State Supply (POS != Supplier State)
     - IGST (18%)                                   = ROUND_HALF_UP(NTV * 0.18, 2)
     - Tax Total                                    = IGST
------------------------------------------------------------------
6. Gross Invoice Amount                             = NTV + Tax Total
7. Less: Post-tax Advance Wallet Balance Applied    = W_applied
------------------------------------------------------------------
8. Net Payable at Payment Gateway                   = max(0.00, Gross Invoice Amount - W_applied)
```

### 6.5 Minimum Charge Handling
Payment gateways enforce minimum charge floors (Razorpay: ₹1.00; Stripe India: ₹0.50). If calculated Net Payable is between ₹0.01 and ₹0.99:
* The amount is credited to the society's platform wallet balance (`platform_billing_adjustments`).
* The invoice is marked `PAID_BY_CREDIT` with ₹0.00 charged to the gateway, avoiding gateway transaction rejection.

### 6.6 Retry-Safe Idempotent Proration
Proration adjustments generate an immutable record in `platform_billing_adjustments` with a deterministic idempotency key:
$$\text{key} = \text{hash}\left(\text{"PRORATE:"} \parallel \text{society\_id} \parallel \text{old\_plan\_id} \parallel \text{new\_plan\_id} \parallel \text{effective\_timestamp}\right)$$
Re-evaluating the proration returns the existing adjustment record with zero divergence.

---

## 7. Database Schema Review & Migration 0022 Scope

### 7.1 Existing Reusable Assets (Migrations 0001–0021)
The following tables established in Phase 21A (Migration `0021_saas_platform_subscriptions`) are reused directly without recreation:
1. `platform_subscription_plans`: Plan tier catalog (`FREE`, `STANDARD`, `ENTERPRISE`).
2. `subscription_plan_entitlements`: Quotas and feature flags per plan tier.
3. `society_subscriptions`: Core subscription lifecycle record.
4. `society_feature_overrides`: Custom tenant feature overrides.
5. `society_quota_overrides`: Custom tenant quota overrides.
6. `society_usage_metrics`: Atomic usage metric counters.
7. `society_provisioning_logs`: Provisioning audit trail.

### 7.2 Tables Altered in Migration 0022
`society_subscriptions` will be augmented with operational billing columns:
* `billing_cycle VARCHAR(10) NOT NULL DEFAULT 'MONTHLY'` (`'MONTHLY'`, `'ANNUAL'`)
* `auto_renew BOOLEAN NOT NULL DEFAULT TRUE`
* `gateway_customer_id VARCHAR(100) NULL`
* `gateway_subscription_id VARCHAR(100) NULL`
* `next_billing_at TIMESTAMP WITH TIME ZONE NULL`

### 7.3 New Tables Created in Migration 0022
Migration 0022 will create exactly 12 new tables:
1. `platform_invoice_sequences`: Fiscal year sequential counter.
2. `platform_invoices`: Official B2B SaaS tax invoices.
3. `platform_invoice_items`: Itemized invoice line items with HSN/SAC codes.
4. `platform_payment_attempts`: Transient checkout / payment session tracking.
5. `platform_payments`: Captured gateway payment ledger.
6. `platform_refunds`: Outflow refund records tied to captured payments.
7. `platform_credit_notes`: Formal GST credit notes issued against platform invoices.
8. `platform_billing_adjustments`: Credits, waivers, and proration balance adjustments.
9. `platform_webhook_events`: Gateway webhook ingestion registry and idempotency log.
10. `platform_subscription_history`: Snapshot history of subscription plan and cycle changes.
11. `platform_subscription_audit_logs`: Immutable security and financial audit trail.
12. `platform_payment_gateway_configs`: Encrypted platform gateway API credentials and webhook secrets.

---

## 8. Implementation Roadmap (Phases 21E.1 – 21E.5)

```
[ Phase 21E.1: Database Schema & Migration 0022 ]
  - Create migration 0022 with 12 new tables and alter society_subscriptions.
  - Apply FORCE RLS on all 9 tenant-scoped tables.
  - SQLAlchemy 2.0 declarative models in apps/api/src/database/models/platform_billing.py.
  - Unit tests verifying clean upgrade/downgrade and RLS enforcement.
                         |
                         v
[ Phase 21E.2: Subscription State Machine & Proration Engine ]
  - Implement SubscriptionStateMachine (TRIAL, ACTIVE, PAST_DUE, SUSPENDED, CANCELLED).
  - Implement deterministic second-accurate ProrationEngine.
  - Implement Indian GST TaxEngine (Intra/Inter-state split, SAC 998313).
  - Implement gapless invoice sequence generator with FY row-level locking.
                         |
                         v
[ Phase 21E.3: Payment Gateway Integration & Webhook Ingestion ]
  - Implement PaymentGatewayClient protocol (Razorpay & Stripe adapters).
  - Implement raw-payload HMAC-SHA256 signature verification with dual-secret rotation.
  - Implement deterministic 64-bit advisory locking for webhook ingestion.
  - Handle captured payments on CANCELLED subscriptions with automated refunds.
                         |
                         v
[ Phase 21E.4: Platform Admin & Tenant Billing APIs ]
  - Tenant Billing Endpoints: View invoices, download tax invoice PDF, initiate plan change.
  - Platform Admin Endpoints: Manage plans, manual offline payment entry, refund authorization.
  - Strictly enforce platform SUPER_ADMIN and tenant isolation via set_config.
                         |
                         v
[ Phase 21E.5: End-to-End Verification & Concurrency Audit ]
  - Live PostgreSQL 16 concurrency testing: webhook race conditions, advisory locking.
  - Gapless invoice numbering stress tests under concurrent transactions.
  - Full regression test suite run, Ruff clean, MyPy clean.
```

---

## 9. Acceptance Criteria & Quality Gates

| Area | Quality Gate / Acceptance Criteria |
|---|---|
| **RLS Isolation** | `app_user` with `NOSUPERUSER` and `NOBYPASSRLS` cannot access any tenant's invoices or payments without explicit `set_config('app.current_society_id', :id, true)`. |
| **Invoice Gaplessness** | 100 concurrent invoice finalization transactions produce strictly sequential, unbroken numbers (`SS-2627-00001` through `SS-2627-000100`) without a single missing number or duplicate error. |
| **Webhook Concurrency** | 50 concurrent deliveries of the same gateway webhook event result in exactly 1 processed record and 49 idempotent acknowledgments (HTTP 200) without race conditions. |
| **Cancelled Late Payment** | Payment captured after subscription cancellation records `platform_payments`, preserves `CANCELLED` status, initiates `platform_refunds`, and acknowledges gateway webhook with HTTP 200. |
| **Proration Math** | Upgrade mid-cycle calculates second-accurate credit, applies GST correctly, and rounds to 2 decimal places using `ROUND_HALF_UP` without paisa discrepancy. |
| **Code Quality** | Ruff linting clean, MyPy type checking clean, 100% passing test suite across all existing Phases 1–21D. |

---

## 10. Remaining Business & Chartered Accountant Decisions

The following business and tax questions require formal consultation and sign-off by a qualified Indian Chartered Accountant (CA) prior to live commercial deployment:
1. **HSN/SAC Code Confirmation**: Confirm whether SocietySphere SaaS subscription falls under SAC `998313` (Information technology software services) or SAC `998314` (Information technology infrastructure provisioning).
2. **GST Invoicing Requirements**: Review invoice template against Rule 46 of CGST Rules, 2017 (display of supplier GSTIN, recipient GSTIN, place of supply, HSN/SAC, tax break-up, digital signature/QR code requirements).
3. **Credit Note Time Limit**: Confirm statutory cut-off dates for issuing GST credit notes under Section 34(2) of CGST Act (by 30th November following the end of the financial year).
4. **B2B vs B2C RCM Rules**: Confirm reverse charge mechanism applicability when billing unregistered housing societies without GSTIN.

---

## 11. Integrity Confirmation & Architecture Sign-Off

* **Migrations 0001–0021**: Unchanged and intact.
* **Migration 0022**: Does not exist.
* **Source Code**: No application files modified.
* **Implementation Status**: Zero implementation started.

**READ-ONLY ARCHITECTURE REVIEW COMPLETE.**  
Awaiting explicit user authorization to begin **Phase 21E.1: Database Schema & Migration 0022**.
