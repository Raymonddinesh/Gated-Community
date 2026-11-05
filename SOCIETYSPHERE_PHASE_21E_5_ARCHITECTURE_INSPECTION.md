# SOCIETYSPHERE — PHASE 21E.5 ARCHITECTURE INSPECTION
## Tenant & Platform SaaS Commercial Billing APIs

**Document Version:** 1.0.0  
**Phase:** 21E.5  
**Current Alembic Head:** `0024_saas_billing_documents`  
**Status:** ARCHITECTURAL INSPECTION & PROPOSAL (READ-ONLY AUDIT)  
**Date:** November 2, 2026  
**Author:** Principal Software Architect & Senior Backend Engineer  

---

## 1. Executive Summary

Phase 21E.5 establishes the unified HTTP API surface for SocietySphere's commercial SaaS subscription billing system. While Phases 21E.1 through 21E.4D built and locked the foundational financial models, proration math, payment gateway integration, GST tax calculation, invoice/credit note lifecycles, and ReportLab PDF document rendering with S3 storage, the API surface currently exists as an administrative prototype concentrated solely under the `/api/v1/platform` prefix requiring `SUPER_ADMIN` privileges.

**Crucially, there is currently NO tenant-facing commercial billing API surface.** Society treasurers and administrators have no HTTP endpoints to inspect their society's SaaS subscription, evaluate available plans, preview or execute upgrades, schedule downgrades, view and pay SaaS invoices via payment gateway checkout, download official GST tax invoices or credit notes, or inspect their advance credit balances. Furthermore, several critical Platform Super Admin operations (such as plan catalog management, global payment inspection, and manual balance adjustments) lack dedicated REST endpoints.

This inspection report:
1. Conducts an exhaustive audit of all existing SaaS billing APIs across Phases 21E.1–21E.4D.
2. Identifies functional gaps between current backend services and public API contracts.
3. Architecturally decouples commercial APIs into **Society/Tenant-Facing APIs**, **Platform Super Admin APIs**, and **Internal Asynchronous Services**.
4. Formalizes the RBAC authorization matrix, multi-tenant PostgreSQL Row Level Security (RLS) enforcement, and audit trail guarantees.
5. Evaluates database schema requirements and definitively proves that **Migration 0025 is NOT necessary**; the existing Alembic head `0024_saas_billing_documents` fully supports all required operations.
6. Defines an orderly implementation sequence and testing strategy.

---

## 2. Existing SaaS Billing API Inventory (Phases 21E.1–21E.4D)

SocietySphere currently mounts 35 platform-level billing and administration endpoints across two router modules:
- [`apps/api/src/api/v1/endpoints/platform.py`](file:///c:/SocApp/apps/api/src/api/v1/endpoints/platform.py) (Phase 21C/21D)
- [`apps/api/src/api/v1/endpoints/platform_billing.py`](file:///c:/SocApp/apps/api/src/api/v1/endpoints/platform_billing.py) (Phases 21E.3–21E.4D)

### 2.1 Current Endpoints Inventory

| Index | Method | Endpoint Path | Auth / Role | Domain & Summary |
|---|---|---|---|---|
| 1 | `GET` | `/api/v1/platform/societies` | `SUPER_ADMIN` | Global directory search, filtering, and pagination of societies. |
| 2 | `GET` | `/api/v1/platform/societies/{society_id}` | `SUPER_ADMIN` | Detailed society metadata, subscription, and primary admin. |
| 3 | `POST` | `/api/v1/platform/societies/{society_id}/suspend` | `SUPER_ADMIN` | Administrative suspension with pessimistic row locking. |
| 4 | `POST` | `/api/v1/platform/societies/{society_id}/reactivate` | `SUPER_ADMIN` | Administrative reactivation (decoupled from subscription). |
| 5 | `GET` | `/api/v1/platform/societies/{society_id}/subscription-overview` | `SUPER_ADMIN` | Subscription, entitlements, and quota utilization overview. |
| 6 | `GET` | `/api/v1/platform/societies/{society_id}/provisioning-logs` | `SUPER_ADMIN` | Diagnostic provisioning steps and failure logs under RLS. |
| 7 | `POST` | `/api/v1/platform/societies/provision` | `SUPER_ADMIN` | Atomic tenant onboarding and subscription provisioning. |
| 8 | `POST` | `/api/v1/platform/societies/{society_id}/provisioning-retry` | `SUPER_ADMIN` | Concurrency-safe retry for failed provisioning steps. |
| 9 | `POST` | `/api/v1/platform/webhooks/{provider}` | Public (HMAC) | Ingests, verifies, and stores gateway webhooks (e.g., Razorpay). |
| 10 | `POST` | `/api/v1/platform/payments/orders` | `SUPER_ADMIN` | Server-side checkout order creation for an issued invoice. |
| 11 | `POST` | `/api/v1/platform/payments/verify` | `SUPER_ADMIN` | Cryptographic signature verification and atomic settlement. |
| 12 | `POST` | `/api/v1/platform/payments/{payment_id}/refund` | `SUPER_ADMIN` | Full or partial refund initiation against captured payment. |
| 13 | `POST` | `/api/v1/platform/reconciliation` | `SUPER_ADMIN` | Independent non-mutating gateway vs database reconciliation. |
| 14 | `POST` | `/api/v1/platform/invoices/draft` | `SUPER_ADMIN` | Create commercial invoice in `DRAFT` status. |
| 15 | `GET` | `/api/v1/platform/invoices` | `SUPER_ADMIN` | List platform invoices with status/society filter & offset limit. |
| 16 | `GET` | `/api/v1/platform/invoices/{invoice_id}` | `SUPER_ADMIN` | Retrieve single invoice details and SAC 998315 line items. |
| 17 | `PATCH` | `/api/v1/platform/invoices/{invoice_id}` | `SUPER_ADMIN` | Update editable fields on an unfinalized `DRAFT` invoice. |
| 18 | `POST` | `/api/v1/platform/invoices/{invoice_id}/finalize` | `SUPER_ADMIN` | Atomically finalize invoice (`DRAFT` &rarr; `ISSUED`, FY sequence). |
| 19 | `POST` | `/api/v1/platform/invoices/{invoice_id}/void` | `SUPER_ADMIN` | Void an issued/draft invoice with audit reason retention. |
| 20 | `GET` | `/api/v1/platform/invoices/{invoice_id}/tax-snapshot/verify` | `SUPER_ADMIN` | Verify SHA-256 cryptographic digest of invoice tax snapshot. |
| 21 | `POST` | `/api/v1/platform/credit-notes/draft` | `SUPER_ADMIN` | Create credit note in `DRAFT` status against issued invoice. |
| 22 | `GET` | `/api/v1/platform/credit-notes/{credit_note_id}` | `SUPER_ADMIN` | Retrieve single credit note details and line items. |
| 23 | `PUT` | `/api/v1/platform/credit-notes/draft/{credit_note_id}` | `SUPER_ADMIN` | Update editable fields on unissued `DRAFT` credit note. |
| 24 | `POST` | `/api/v1/platform/credit-notes/preview` | `SUPER_ADMIN` | Simulate credit note tax reversal and invoice balance adjustments. |
| 25 | `POST` | `/api/v1/platform/credit-notes/{credit_note_id}/issue` | `SUPER_ADMIN` | Atomically issue credit note (`DRAFT` &rarr; `ISSUED`, FY sequence). |
| 26 | `POST` | `/api/v1/platform/credit-notes/{credit_note_id}/void` | `SUPER_ADMIN` | Void an issued credit note and reverse balance adjustments. |
| 27 | `GET` | `/api/v1/platform/credit-notes/{credit_note_id}/tax-snapshot/verify` | `SUPER_ADMIN` | Verify SHA-256 cryptographic digest of credit note snapshot. |
| 28 | `GET` | `/api/v1/platform/credit-notes` | `SUPER_ADMIN` | List platform credit notes with status/society filters. |
| 29 | `GET` | `/api/v1/platform/invoices/{invoice_id}/pdf` | `SUPER_ADMIN` | Retrieve or generate binary ReportLab invoice PDF. |
| 30 | `GET` | `/api/v1/platform/invoices/{invoice_id}/download-url` | `SUPER_ADMIN` | Generate short-lived presigned S3 download URL ($\le 300\text{s}$). |
| 31 | `POST` | `/api/v1/platform/invoices/{invoice_id}/send-email` | `SUPER_ADMIN` | Queue and execute transactional email outbox dispatch. |
| 32 | `GET` | `/api/v1/platform/credit-notes/{credit_note_id}/pdf` | `SUPER_ADMIN` | Retrieve or generate binary ReportLab credit note PDF. |
| 33 | `GET` | `/api/v1/platform/credit-notes/{credit_note_id}/download-url` | `SUPER_ADMIN` | Generate short-lived presigned S3 download URL ($\le 300\text{s}$). |
| 34 | `POST` | `/api/v1/platform/credit-notes/{credit_note_id}/send-email` | `SUPER_ADMIN` | Queue and execute transactional email outbox dispatch. |
| 35 | `GET` | `/api/v1/platform/documents/{document_id}/deliveries` | `SUPER_ADMIN` | Retrieve delivery attempt audit log for a billing document. |

---

## 3. Gap Analysis: Missing Functionality

A rigorous analysis of SocietySphere's requirements reveals significant functional gaps:

### 3.1 Total Absence of Tenant/Society-Facing Commercial Endpoints
1. **Subscription Inspection & Self-Service:** Tenant treasurers cannot view their society's active commercial plan, trial expiration, next renewal date, billing cycle (`MONTHLY`/`ANNUAL`), or auto-renewal toggle.
2. **Catalog Exploration:** Tenants cannot list available platform plans to assess feature differences or pricing.
3. **Mid-Cycle Plan Upgrades:** While [`SubscriptionUpgradeService`](file:///c:/SocApp/apps/api/src/subscriptions/upgrade_service.py) accurately calculates second-level proration credits and net payables, no tenant endpoint exists to request an upgrade preview or execute an upgrade.
4. **Scheduled Plan Downgrades:** While [`SubscriptionDowngradeService`](file:///c:/SocApp/apps/api/src/subscriptions/downgrade_service.py) enforces quota pre-checks, no tenant endpoint exists to schedule a downgrade for the next renewal date.
5. **Subscription Cancellation & Renewal Resumption:** Tenants cannot schedule cancellation at period end or re-enable auto-renewal.
6. **Invoice & Credit Note Access:** Tenants cannot query their own society's commercial invoice history, inspect line-item breakdowns, or view issued credit notes.
7. **Document Self-Service:** Tenants cannot download official GST-compliant PDF invoices/credit notes or trigger email delivery to their registered billing address.
8. **In-App Checkout & Settlement:** While `order_service.py` and `verification_service.py` support Razorpay order creation and signature verification, the existing endpoints require `SUPER_ADMIN`. Tenants cannot initiate checkout or submit signatures for payment settlement.
9. **Advance Balance / Wallet Visibility:** When a credit note is issued against an already-paid invoice, the system generates an `ADVANCE_BALANCE` adjustment on `PlatformBillingAdjustment`, but tenants cannot view their current credit balance.

### 3.2 Platform Super Admin Gaps
1. **Plan Catalog CRUD:** Platform administrators cannot list, create, update, or archive `PlatformSubscriptionPlan` records or their associated `SubscriptionPlanEntitlement` entries via REST APIs.
2. **Global Payment Inspection:** Super Admins cannot list all captured payments (`PlatformPayment`) or search payments across societies.
3. **Manual Billing Adjustments:** Super Admins cannot grant goodwill waivers, manual credits, or correct billing discrepancies via an adjustment endpoint.
4. **Standardized Pagination Contracts:** Current endpoints `GET /platform/invoices` and `GET /platform/credit-notes` return bare JSON lists `list[PlatformInvoiceResponse]` using primitive `limit` and `offset` queries, failing the platform standard of `PaginatedResponse[T]` (`items`, `total`, `page`, `page_size`, `pages`).

---

## 4. Proposed Architectural Separation

To guarantee strict multi-tenant security, separation of concerns, and clean API design, Phase 21E.5 separates the billing API surface into three distinct tiers:

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                                   API CONSUMERS                                        │
└────────────────────────────────────────────────────────────────────────────────────────┘
          │                                                    │
          ▼                                                    ▼
┌───────────────────────────────────────┐    ┌───────────────────────────────────────────┐
│       TIER A: TENANT BILLING          │    │       TIER B: PLATFORM ADMIN BILLING      │
│  /api/v1/societies/{society_id}/...   │    │            /api/v1/platform/...           │
│                                       │    │                                           │
│ • Tenant-Context & URL Match Guard    │    │ • Global SUPER_ADMIN Scope Only           │
│ • Roles: SOCIETY_ADMIN, TREASURER     │    │ • Cross-Tenant Catalog & Analytics        │
│ • PostgreSQL FORCE RLS Enabled        │    │ • Plan Catalog & System Management        │
│ • Self-Service Payments & Documents   │    │ • Manual Adjustments & Reconciliation     │
└───────────────────────────────────────┘    └───────────────────────────────────────────┘
          │                                                    │
          └──────────────────────────┬─────────────────────────┘
                                     ▼
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                     TIER C: INTERNAL ASYNCHRONOUS SERVICES                             │
│                                                                                        │
│ • Webhook Background Worker (Event Ingestion -> Settlement Pipeline)                   │
│ • Scheduled Billing Cycle Engine (Automated Periodic Invoicing at next_billing_at)     │
│ • Transactional Email Dispatch Sweeper (Outbox Retry Exponential Backoff)             │
│ • Delinquency & Grace Period Monitor (PAST_DUE -> Grace Expiry -> SUSPENDED)           │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 5. Comprehensive Proposed Endpoint Inventory

### 5.1 Tier A: Society/Tenant-Facing Billing APIs
**Base Route:** `/api/v1/societies/{society_id}/billing`  
**Security Invariant:** Requires active session, valid bearer token, URL parameter validation matching `X-Society-ID` header (if provided), active society membership, and `SOCIETY_ADMIN` or `TREASURER` role assignment. Executes under transaction-local `set_db_tenant_context(session, society_id)`.

#### 1. Subscription & Plan Management
- `GET /api/v1/societies/{society_id}/billing/subscription`
  - **Summary:** Retrieve active society subscription status, current plan details, billing cycle, renewal dates, auto-renew flag, and feature/quota usage.
  - **Permissions:** `SOCIETY_ADMIN`, `TREASURER`, `SECRETARY`, `COMMITTEE_MEMBER` (Read-Only).
- `GET /api/v1/societies/{society_id}/billing/plans`
  - **Summary:** Browse active public subscription plans catalog with entitlement limits and annual/monthly pricing for upgrade consideration.
  - **Permissions:** `SOCIETY_ADMIN`, `TREASURER`.
- `POST /api/v1/societies/{society_id}/billing/subscription/upgrade-preview`
  - **Summary:** Simulate immediate mid-cycle plan upgrade; returns second-accurate prorated credit, new plan charge, and net payable balance using `SubscriptionUpgradeService`.
  - **Permissions:** `SOCIETY_ADMIN`, `TREASURER`.
- `POST /api/v1/societies/{society_id}/billing/subscription/upgrade`
  - **Summary:** Execute immediate plan upgrade. If net payable $> 0$, generates an issued upgrade invoice and returns payment order metadata; if net payable $\le 0$, immediately activates new plan and records credit adjustment.
  - **Permissions:** `SOCIETY_ADMIN`, `TREASURER`.
- `POST /api/v1/societies/{society_id}/billing/subscription/downgrade`
  - **Summary:** Schedule plan downgrade effective at the next renewal boundary (`next_billing_at`), validating current tenant usage against target plan limits via `SubscriptionDowngradeService`.
  - **Permissions:** `SOCIETY_ADMIN`, `TREASURER`.
- `POST /api/v1/societies/{society_id}/billing/subscription/cancel`
  - **Summary:** Schedule subscription cancellation at period end (`auto_renew = False`), maintaining active status until `current_period_end`.
  - **Permissions:** `SOCIETY_ADMIN`, `TREASURER`.
- `POST /api/v1/societies/{society_id}/billing/subscription/resume`
  - **Summary:** Re-enable automatic subscription renewal for a subscription scheduled for cancellation.
  - **Permissions:** `SOCIETY_ADMIN`, `TREASURER`.

#### 2. Tenant Commercial Invoices
- `GET /api/v1/societies/{society_id}/billing/invoices`
  - **Summary:** List commercial subscription invoices issued to this society with standardized pagination (`page`, `page_size`, `pages`, `total`) and status filtering (`ISSUED`, `PAID`, `OVERDUE`).
  - **Permissions:** `SOCIETY_ADMIN`, `TREASURER`.
- `GET /api/v1/societies/{society_id}/billing/invoices/{invoice_id}`
  - **Summary:** Retrieve full invoice details including SAC 998315 line items, GST breakdown (CGST, SGST, IGST), and payment status. Rejects access if invoice does not belong to `society_id` (404/403).
  - **Permissions:** `SOCIETY_ADMIN`, `TREASURER`.
- `GET /api/v1/societies/{society_id}/billing/invoices/{invoice_id}/pdf`
  - **Summary:** Direct binary stream download of finalized ReportLab PDF invoice.
  - **Permissions:** `SOCIETY_ADMIN`, `TREASURER`.
- `GET /api/v1/societies/{society_id}/billing/invoices/{invoice_id}/download-url`
  - **Summary:** Generate short-lived presigned S3 download URL ($\le 300\text{ seconds}$).
  - **Permissions:** `SOCIETY_ADMIN`, `TREASURER`.
- `POST /api/v1/societies/{society_id}/billing/invoices/{invoice_id}/send-email`
  - **Summary:** Trigger transactional email delivery of invoice PDF to the society's registered treasurer/admin.
  - **Permissions:** `SOCIETY_ADMIN`, `TREASURER`.

#### 3. Tenant Checkout & Invoice Settlement
- `POST /api/v1/societies/{society_id}/billing/invoices/{invoice_id}/checkout`
  - **Summary:** Create a server-authoritative payment gateway checkout order (e.g., Razorpay `order_id`) for an unpaid issued invoice.
  - **Guarantees:** Authoritative amount derived from `invoice.amount_due`; rejects paid/void invoices; uses `X-Idempotency-Key`.
  - **Permissions:** `SOCIETY_ADMIN`, `TREASURER`.
- `POST /api/v1/societies/{society_id}/billing/payments/verify`
  - **Summary:** Verify payment signature (`order_id|payment_id|signature`) following checkout completion and trigger atomic settlement via `PaymentVerificationService`.
  - **Permissions:** `SOCIETY_ADMIN`, `TREASURER`.

#### 4. Tenant Credit Notes & Balances
- `GET /api/v1/societies/{society_id}/billing/credit-notes`
  - **Summary:** List credit notes issued to this society with pagination and status filters.
  - **Permissions:** `SOCIETY_ADMIN`, `TREASURER`.
- `GET /api/v1/societies/{society_id}/billing/credit-notes/{credit_note_id}`
  - **Summary:** Retrieve single credit note details, reason code, and line items.
  - **Permissions:** `SOCIETY_ADMIN`, `TREASURER`.
- `GET /api/v1/societies/{society_id}/billing/credit-notes/{credit_note_id}/pdf`
  - **Summary:** Direct binary stream download of issued credit note PDF.
  - **Permissions:** `SOCIETY_ADMIN`, `TREASURER`.
- `GET /api/v1/societies/{society_id}/billing/credit-notes/{credit_note_id}/download-url`
  - **Summary:** Presigned S3 download URL ($\le 300\text{ seconds}$) for credit note PDF.
  - **Permissions:** `SOCIETY_ADMIN`, `TREASURER`.
- `GET /api/v1/societies/{society_id}/billing/balance`
  - **Summary:** Retrieve society's active credit/advance balance aggregated from `PlatformBillingAdjustment` records.
  - **Permissions:** `SOCIETY_ADMIN`, `TREASURER`.
- `GET /api/v1/societies/{society_id}/billing/payments`
  - **Summary:** View historical payment receipts and settlement transactions for the society.
  - **Permissions:** `SOCIETY_ADMIN`, `TREASURER`.

---

### 5.2 Tier B: Platform Super Admin Billing APIs
**Base Route:** `/api/v1/platform/...`  
**Security Invariant:** Strictly guarded by `Depends(require_role("SUPER_ADMIN"))`. Unrestricted cross-tenant scope with mandatory audit trail logging in `PlatformSubscriptionAuditLog`.

#### 1. Subscription Plan Catalog Management
- `GET /api/v1/platform/plans`
  - **Summary:** List all subscription plans (active, inactive, archived) with complete entitlement definitions.
- `GET /api/v1/platform/plans/{plan_id}`
  - **Summary:** Retrieve individual plan details, pricing, trial days, and entitlement limits.
- `POST /api/v1/platform/plans`
  - **Summary:** Create a new subscription plan with feature keys and quota limits.
- `PATCH /api/v1/platform/plans/{plan_id}`
  - **Summary:** Update plan pricing, display name, description, or toggle active/archived state.

#### 2. Global Subscription & Tenant Overrides
- `GET /api/v1/platform/subscriptions`
  - **Summary:** Paginated search and listing of all society subscriptions across the platform (filterable by `status`, `plan_code`, `past_due`, `society_name`).
- `POST /api/v1/platform/subscriptions/{society_id}/transition`
  - **Summary:** Administrative state machine transition (`SubscriptionLifecycleService.transition_subscription`) with mandatory audit reason.

#### 3. Invoices, Credit Notes & Adjustments (Standardized & Extended)
- `GET /api/v1/platform/invoices` *(Enhanced)*
  - **Upgrade:** Transition return model to `PaginatedResponse[PlatformInvoiceResponse]` (`items`, `total`, `page`, `page_size`, `pages`).
- `GET /api/v1/platform/credit-notes` *(Enhanced)*
  - **Upgrade:** Transition return model to `PaginatedResponse[PlatformCreditNoteResponse]`.
- `GET /api/v1/platform/societies/{society_id}/adjustments`
  - **Summary:** List all proration credits, goodwill waivers, advance balances, and manual adjustments for a specific society.
- `POST /api/v1/platform/societies/{society_id}/adjustments`
  - **Summary:** Issue an administrative goodwill waiver or manual credit adjustment to a society's account balance.

#### 4. Payments, Refunds & Reconciliation
- `GET /api/v1/platform/payments`
  - **Summary:** Paginated list of all captured payment transactions across all societies.
- `GET /api/v1/platform/payments/{payment_id}`
  - **Summary:** Detailed view of captured payment, gateway transaction identifiers, signature verification status, and refund history.
- `GET /api/v1/platform/refunds`
  - **Summary:** Paginated global listing of all outbound payment refunds.
- `POST /api/v1/platform/payments/{payment_id}/refund` *(Existing)*
  - **Summary:** Outbound gateway refund initiation.
- `POST /api/v1/platform/reconciliation` *(Existing)*
  - **Summary:** Non-mutating payment gateway state reconciliation.

---

### 5.3 Tier C: Internal Asynchronous Services

These background operations execute outside the synchronous HTTP request-response cycle:
1. **Webhook Processing Worker:** Consumes persisted `PlatformWebhookEvent` rows (`STATUS = PENDING`), deserializes payload, verifies order reference, and delegates to `PaymentSettlementService`.
2. **Scheduled Billing Cycle Engine:** Periodic worker evaluating `society_subscriptions` where `status = 'ACTIVE'`, `auto_renew = True`, and `next_billing_at <= now()`; generates new draft/issued invoices and advances billing periods.
3. **Email Outbox Dispatch Sweeper:** Asynchronous background worker inspecting `platform_document_deliveries` where `status = 'RETRYING'` and `next_retry_at <= now()`; executes exponential retry attempts (30s, 120s, 480s).
4. **Grace Period Delinquency Monitor:** Daily job evaluating subscriptions where `status = 'PAST_DUE'`; transitions accounts past the 7-day grace window to `SUSPENDED`.

---

## 6. RBAC Authorization & Multi-Tenant Security Design

### 6.1 RBAC Matrix

| Endpoint Group | `SUPER_ADMIN` | `SOCIETY_ADMIN` | `TREASURER` | `SECRETARY` | `RESIDENT` |
|---|:---:|:---:|:---:|:---:|:---:|
| **Tenant Subscription View** | ✅ | ✅ | ✅ | ✅ | ❌ |
| **Tenant Plan Catalog View** | ✅ | ✅ | ✅ | ❌ | ❌ |
| **Tenant Upgrade / Downgrade** | ✅ | ✅ | ✅ | ❌ | ❌ |
| **Tenant Invoices & PDFs** | ✅ | ✅ | ✅ | ❌ | ❌ |
| **Tenant Invoice Checkout & Pay** | ✅ | ✅ | ✅ | ❌ | ❌ |
| **Tenant Credit Notes & Balance** | ✅ | ✅ | ✅ | ❌ | ❌ |
| **Platform Plan Catalog CRUD** | ✅ | ❌ | ❌ | ❌ | ❌ |
| **Platform Invoicing Lifecycle** | ✅ | ❌ | ❌ | ❌ | ❌ |
| **Platform Credit Note Issuance** | ✅ | ❌ | ❌ | ❌ | ❌ |
| **Platform Refunds & Reconcile** | ✅ | ❌ | ❌ | ❌ | ❌ |
| **Platform Manual Adjustments** | ✅ | ❌ | ❌ | ❌ | ❌ |

### 6.2 PostgreSQL 16 Row Level Security (RLS) Enforcement
1. **Tenant Context Configuration:**
   For all `/societies/{society_id}/billing/...` routes, the FastAPI dependency pipeline:
   ```python
   target_society_id = await resolve_society_context(request, x_society_id, current_user, session)
   set_current_tenant_id(target_society_id)
   await set_db_tenant_context(session, target_society_id)
   ```
2. **FORCE RLS Table Verification:**
   All underlying tables—`platform_invoices`, `platform_payments`, `platform_credit_notes`, `platform_billing_adjustments`, `platform_billing_documents`, and `platform_document_deliveries`—enforce `ENABLE ROW LEVEL SECURITY` and `FORCE ROW LEVEL SECURITY`.
3. **Anti-Leakage Guarantee:**
   Even if an application developer omits `where(society_id == current_society_id)` in an internal query, PostgreSQL's query planner automatically injects the tenant isolation predicate `society_id = current_setting('app.current_tenant_id')::UUID`. Unprivileged database users (`app_user`) cannot read or mutate data across tenant boundaries under any circumstances.

---

## 7. Review of Architectural Standards

### 7.1 Standardized Pagination & Filtering
All listing endpoints must implement uniform query contracts:
```python
class PaginatedParams:
    page: int = Query(1, ge=1, description="Page number (1-based)")
    page_size: int = Query(20, ge=1, le=100, description="Items per page")
    sort_by: str = Query("created_at", description="Field to sort by")
    sort_order: str = Query("desc", regex="^(asc|desc)$")
```
Responses must adhere to the generic pagination schema:
```python
class PaginatedResponse[T](BaseModel):
    items: list[T]
    total: int
    page: int
    page_size: int
    pages: int
```

### 7.2 Presentation-Layer Immutability & Financial Precision
1. **Zero Runtime Calculation in Presentation Layer:** No monetary sum, tax split, or discount calculation may be computed in endpoint response formatters or PDF templates. All financial data must be retrieved from persisted, finalized database fields.
2. **Decimal Arithmetic:** All currency quantities are mapped as `Decimal` with exact 2-decimal scale (`Numeric(12, 2)`). Floating-point arithmetic is strictly prohibited.
3. **Cryptographic Anti-Tamper:** Document PDF downloads verify SHA-256 binary digests against `PlatformBillingDocument.sha256_checksum`.

### 7.3 Idempotency & Concurrency Safety
1. **`X-Idempotency-Key` Header:** Enforced on mutation endpoints (`/checkout`, `/upgrade`, `/invoices/draft`, `/send-email`, `/adjustments`).
2. **Pessimistic Row Locking:** All state transitions and balance deductions use `SELECT ... FOR UPDATE` row locks to eliminate race conditions.
3. **Gateway Signature Verification:** Checkout verification requires timing-safe HMAC-SHA256 comparison before recording payment settlement.

---

## 8. Database Schema Impact & Migration 0025 Evaluation

### 8.1 Is Migration 0025 Necessary?
**NO. Migration 0025 is NOT necessary.**

A comprehensive audit of existing schema definitions demonstrates that all required tables, columns, indexes, foreign keys, and RLS policies are already fully provisioned:
- `platform_subscription_plans` & `subscription_plan_entitlements` &rarr; Provisioned in Migration 0020.
- `society_subscriptions` & `society_feature_overrides` & `society_quota_overrides` &rarr; Provisioned in Migration 0020.
- `platform_invoices` & `platform_invoice_items` &rarr; Provisioned in Migration 0021.
- `platform_payment_attempts` & `platform_payments` & `platform_refunds` &rarr; Provisioned in Migration 0021.
- `platform_billing_adjustments` &rarr; Provisioned in Migration 0021 (Supports `PRORATION_CREDIT`, `GOODWILL_WAIVER`, `ADVANCE_BALANCE`, `MINIMUM_CHARGE_ROUNDOFF`).
- `platform_subscription_history` & `platform_subscription_audit_logs` &rarr; Provisioned in Migration 0021.
- `platform_credit_notes` & `platform_credit_note_items` & `platform_credit_note_sequences` &rarr; Provisioned in Migration 0023.
- `platform_billing_documents` & `platform_document_deliveries` & `platform_document_delivery_attempts` &rarr; Provisioned in Migration 0024.

**Architectural Recommendation:**
Phase 21E.5 is purely an **API Routing, Application Controller, and RBAC Integration Layer**. Introducing an empty or redundant Migration 0025 would pollute the Alembic version tree. **The Alembic head must remain at `0024_saas_billing_documents`.**

---

## 9. Recommended Implementation Sequence

When authorized, implementation should proceed in three disciplined stages:

```
┌────────────────────────────────────────────────────────────────────────┐
│ STAGE 1: ROUTER RESTRUCTURING & PLATFORM EXTENSIONS                    │
│ • Retain apps/api/src/api/v1/endpoints/platform_billing.py for admin.  │
│ • Upgrade list_invoices and list_credit_notes to PaginatedResponse.    │
│ • Add Platform Plans CRUD (/platform/plans).                           │
│ • Add Platform Subscriptions List (/platform/subscriptions).           │
│ • Add Platform Adjustments (/platform/societies/{id}/adjustments).     │
│ • Add Platform Global Payments & Refunds Listing.                      │
└──────────────────────────────────┬─────────────────────────────────────┘
                                   │
                                   ▼
┌────────────────────────────────────────────────────────────────────────┐
│ STAGE 2: TENANT BILLING ROUTER IMPLEMENTATION                          │
│ • Create apps/api/src/api/v1/endpoints/society_billing.py              │
│ • Implement Tenant Subscription & Plan Browsing endpoints.             │
│ • Implement Tenant Upgrade Preview & Upgrade Execution endpoints.      │
│ • Implement Tenant Downgrade & Cancellation Scheduling endpoints.      │
│ • Implement Tenant Invoices, Credit Notes & Balance endpoints.         │
│ • Implement Tenant Document Downloads & Presigned URL endpoints.       │
│ • Implement Tenant Checkout Order Creation & Signature Verification.   │
│ • Register society_billing router in apps/api/src/api/v1/router.py.    │
└──────────────────────────────────┬─────────────────────────────────────┘
                                   │
                                   ▼
┌────────────────────────────────────────────────────────────────────────┐
│ STAGE 3: TEST SUITE & VERIFICATION                                     │
│ • Unit & Integration Suite: tests/test_phase21e5_tenant_billing.py     │
│ • Platform Admin Suite: tests/test_phase21e5_platform_billing.py       │
│ • Cross-Tenant Access Denial & RLS Security Tests.                     │
│ • Full Repository Regression (ensure 535+ tests pass with zero errors).│
└────────────────────────────────────────────────────────────────────────┘
```

---

## 10. Testing Strategy

1. **Tenant Isolation & RLS Verification:**
   - Attempt to access Society B's invoice, credit note, or document download URL while authenticated as Society A's treasurer. Must return HTTP 403 Forbidden or HTTP 404 Not Found.
   - Verify unprivileged `app_user` database queries cannot leak cross-tenant billing records.
2. **RBAC Authorization Tests:**
   - Verify `RESIDENT` and `TENANT` roles are rejected with HTTP 403 on all `/societies/{society_id}/billing/...` endpoints.
   - Verify `SECRETARY` can view subscriptions and invoices but cannot initiate payments, plan upgrades, or cancellations.
   - Verify non-`SUPER_ADMIN` users are rejected with HTTP 403 on all `/platform/...` endpoints.
3. **Financial & Checkout Flow Tests:**
   - Complete checkout creation and settlement simulation for an issued tenant invoice.
   - Verify mid-cycle upgrade calculation returns accurate proration credit and net payable amount.
   - Verify downgrade scheduling prevents target plans where current society quota usage exceeds new plan limits.
4. **Presigned URLs & Document Integrity:**
   - Verify presigned URLs expire within $\le 300\text{ seconds}$.
   - Verify tamper detection rejects modified PDF binaries.
5. **Full Regression Verification:**
   - Execute all historic test suites (`tests/test_phase21e1_*.py` through `tests/test_phase21e4d_*.py`) and the full repository test suite.

---

## 11. Risks & Recommendations

| Risk | Severity | Mitigation Strategy |
|---|:---:|---|
| **Accidental Cross-Tenant Data Leakage** | Critical | Enforce `resolve_society_context` and PostgreSQL `set_db_tenant_context` on every tenant endpoint. Rely on `FORCE ROW LEVEL SECURITY`. |
| **Financial Recalculation Drift** | High | Forbid any client-side or presentation-layer arithmetic. All payable amounts and tax splits must originate from finalized database entities. |
| **Checkout Tampering** | High | Derive gateway payment order amounts strictly from `PlatformInvoice.amount_due`. Never accept amount overrides from client request bodies. |
| **Unnecessary Schema Migrations** | Medium | Maintain Alembic head at `0024_saas_billing_documents`. Do not create migration 0025. |
| **Router Clutter** | Low | Keep `/platform/...` administrative endpoints in `platform_billing.py` and isolate `/societies/{society_id}/billing/...` endpoints in a new dedicated file `society_billing.py`. |

---

## 12. Conclusion & Authorization Request

Phase 21E.5 architecture is fully specified, verified against existing infrastructure, and ready for development. The existing database schema (head `0024`) requires **no alterations**. All domain services ([`SubscriptionLifecycleService`](file:///c:/SocApp/apps/api/src/subscriptions/subscription_lifecycle_service.py), [`SubscriptionUpgradeService`](file:///c:/SocApp/apps/api/src/subscriptions/upgrade_service.py), [`SubscriptionDowngradeService`](file:///c:/SocApp/apps/api/src/subscriptions/downgrade_service.py), [`PlatformInvoiceService`](file:///c:/SocApp/apps/api/src/subscriptions/invoicing/service.py), [`PlatformCreditNoteService`](file:///c:/SocApp/apps/api/src/subscriptions/credit_notes/service.py), [`PlatformBillingDocumentService`](file:///c:/SocApp/apps/api/src/subscriptions/documents/document_orchestrator.py), [`PaymentOrderService`](file:///c:/SocApp/apps/api/src/subscriptions/payments/order_service.py), and [`PaymentVerificationService`](file:///c:/SocApp/apps/api/src/subscriptions/payments/verification_service.py)) are implemented, tested, and ready to be surfaced.

**Awaiting Architectural Approval to proceed with Phase 21E.5 implementation.**
