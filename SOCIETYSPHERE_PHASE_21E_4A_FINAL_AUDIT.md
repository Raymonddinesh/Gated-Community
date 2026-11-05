# SocietySphere — Phase 21E.4A Final Audit Report
## SaaS Billing: GST Tax Engine & Tax Configuration

**Project:** SocietySphere — Enterprise Multi-Tenant Apartment Management SaaS  
**Phase:** Phase 21E.4A Final Closure Audit  
**Auditor Roles:** Principal SaaS Architect, Indian GST Domain Reviewer, PostgreSQL Security Reviewer, Senior QA Engineer  
**Audit Date:** November 1, 2026  
**Audit Type:** Strictly Read-Only Source-Code & Test Verification  
**Final Verdict:** **PASS WITH CONDITIONS**  

---

## 1. Executive Verdict & Summary

### Verdict: PASS WITH CONDITIONS

Phase 21E.4A (**GST Tax Engine & Tax Configuration**) provides a mathematically rigorous, statutory-compliant, and secure foundation for Indian Goods and Services Tax (GST) computation in SocietySphere. All core tax formulas, rounding algorithms, Place of Supply rules under Section 12 of the IGST Act 2017, GSTIN Luhn Mod-36 checksum algorithms, and PostgreSQL FORCE RLS tenant isolation have been verified directly in the source code and executed against live PostgreSQL 16.

### Summary Scorecard

| Domain | Audit Scope | Status | Severity Findings |
|:---|:---|:---:|:---:|
| **Audit A: Configuration** | Tax rule registry, SAC defaults, versioning, persistence | **PASS WITH CONDITIONS** | 1 Medium, 1 Low |
| **Audit B: Place of Supply** | Sections 12 & 13 IGST Act, B2B/B2C, intra vs inter-state | **PASS** | 1 Low (Scope Clarification) |
| **Audit C: Tax Engine** | Decimal precision, ROUND_HALF_UP, ordering, reversal | **PASS WITH CONDITIONS** | 1 Medium |
| **Audit D: GSTIN Validation** | 15-char syntax, state codes, PAN entity, Luhn Mod-36 | **PASS** | None |
| **Audit E: Snapshot Persistence**| Durability, SHA-256 integrity, audit vs dedicated table | **PASS WITH CONDITIONS** | 1 Medium |
| **Audit F: PostgreSQL Security** | FORCE RLS, unprivileged role, tenant isolation | **PASS** | None |
| **Audit G: Migrations & QA** | Migrations 0001–0022, regression suite, skipped tests | **PASS** | None |

---

## 2. Findings Summary by Severity

### Medium Severity Findings
1. **[Finding M-1] In-Memory Tax Configuration Lacks Multi-Worker Synchronization and Restart Durability**
   - *Source:* `apps/api/src/subscriptions/tax/tax_config.py:56-69`
   - *Impact:* `TaxConfigurationService` stores registered tax rules in an in-memory Python list (`self._rules`). In a multi-worker production deployment (e.g. Uvicorn with multiple workers or Kubernetes pods), runtime rule additions/deactivations in one worker will not replicate to other workers, and modifications will not survive process restarts.
   - *Condition for Production:* Acceptable for Phase 21E.4A because defaults are statutory and stable, but dynamic tax rule updates in production must either be backed by a database table or configured via environment/configuration files before enabling admin tax management APIs.

2. **[Finding M-2] Credit Note Snapshot References Active Tax Rule Version Instead of Historical Rule**
   - *Source:* `apps/api/src/subscriptions/tax/engine.py:251`
   - *Impact:* In `calculate_credit_note_tax`, the credit note snapshot creation calls `self.config_service.get_rule(original_invoice_snapshot.sac_code)`. While the calculation math correctly uses the rates from `original_invoice_snapshot`, the resulting credit note snapshot (`cn_snapshot`) adopts the *currently active* rule's version string rather than preserving the historical version from the original invoice.
   - *Condition for Invoice Generation:* During Phase 21E.4B invoice/credit-note finalization, pass `tax_rule_version=original_invoice_snapshot.tax_config_version` or construct `TaxRateConfig` directly from the original snapshot.

3. **[Finding M-3] Architectural Distinction: Tax Snapshot Stored in Audit Log Rather Than Dedicated Column**
   - *Source:* `apps/api/src/database/models/platform_billing.py:206-388`, `tests/test_phase21e4a_pg.py:243-255`
   - *Impact:* While tabular tax figures (`taxable_amount`, `cgst_amount`, `sgst_amount`, `igst_amount`, `tax_total`, `grand_total`, `sac_code`, `place_of_supply`, `customer_gstin`) are persisted as dedicated columns on `PlatformInvoice`, the complete cryptographic `TaxSnapshot` JSON payload is persisted in `PlatformSubscriptionAuditLog.after_state`. The audit log record is tenant-isolated and immutable, but it is not linked via an explicit foreign key to `PlatformInvoice.id`.
   - *Condition for Invoice Generation:* In Phase 21E.4B, implement a dedicated repository method to query the snapshot from audit logs or store the JSONB snapshot directly in an invoice-associated payload.

### Low Severity Findings
1. **[Finding L-1] Lexicographical Version String Comparison in Configuration Service**
   - *Source:* `apps/api/src/subscriptions/tax/tax_config.py:102`
   - *Impact:* `candidates.sort(key=lambda x: x.version, reverse=True)` uses raw string sorting. If versions exceed single digits (e.g., `"10.0"` vs `"2.0"`), `"2.0"` will sort higher than `"10.0"`.
   - *Recommendation:* Use semantic version parsing (e.g. `packaging.version.Version` or tuple integer splitting).

2. **[Finding L-2] Transaction Date Not Utilized in Place of Supply Service**
   - *Source:* `apps/api/src/subscriptions/tax/place_of_supply.py:53-175`, `models.py:69`
   - *Impact:* `PlaceOfSupplyInput.transaction_date` is accepted but not referenced in `PlaceOfSupplyService.determine_place_of_supply`. State code mapping is static (38 codes + 97). For current SaaS billing (2024–2026), this is fully valid, but does not adjust for historical territorial reorganizations prior to 2020.
   - *Recommendation:* Retain as low priority; not relevant for active operations.

3. **[Finding L-3] Section 13 (International Supplies) and SEZ Zero-Rating Are Out of Scope**
   - *Source:* `apps/api/src/subscriptions/tax/place_of_supply.py:1-175`
   - *Impact:* Non-Indian addresses (e.g., "US", "California") fail safely with `CUSTOMER_STATE_UNRESOLVED`. The system does not currently process overseas cross-border supplies or SEZ zero-rating without IGST payment.
   - *Assumption:* SocietySphere operates exclusively for housing societies located in India.

---

## 3. Detailed Audit Evidence by Area

### AUDIT A — TAX CONFIGURATION

| Audit Checkpoint | Source Location | Verified Fact | Assessment |
|:---|:---|:---|:---:|
| **Storage Mechanism** | `tax_config.py:56-59` | Initialized as `self._rules = list(DEFAULT_RULES)` in memory. | In-Memory Only |
| **Restart Persistence** | `tax_config.py:58` | State resets to `DEFAULT_RULES` on process restart. | Non-Persistent |
| **Multi-Worker Consistency** | `tax_config.py:147` | Module-level singleton `tax_config_service`. Each worker has its own copy. | Independent per Worker |
| **Effective Date Boundaries** | `tax_config.py:89-92` | Evaluates `effective_from <= target_date <= effective_to`. | Deterministic |
| **Version Selection** | `tax_config.py:102` | `candidates.sort(key=lambda x: x.version, reverse=True)` | Lexicographical String Sort |
| **Authorization Controls** | `tax_config.py:60, 113` | `register_rule` and `deactivate_rule` lack caller permission checks. | Unrestricted in code |
| **Audit Logging** | `tax_config.py:60-69` | Mutations do not emit `PlatformSubscriptionAuditLog` entries. | No Audit Log on Mutation |
| **Historical Retention** | `snapshot.py:98-124` | Historical invoices lock their applied version in `TaxSnapshot`. | Retained via Snapshot |

**Evidence:**
```python
# apps/api/src/subscriptions/tax/tax_config.py:56-59
class TaxConfigurationService:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._rules: list[TaxRateConfig] = list(DEFAULT_RULES)
```

---

### AUDIT B — PLACE OF SUPPLY (SECTIONS 12 & 13 IGST ACT)

| Audit Checkpoint | Source Location | Verified Fact | Assessment |
|:---|:---|:---|:---:|
| **B2B Determination** | `place_of_supply.py:88-129` | Validates customer GSTIN; extracts first 2 digits; applies Sec 12(2)(a). | **VERIFIED** |
| **B2C Determination** | `place_of_supply.py:130-142` | Uses customer billing address state; applies Sec 12(2)(b)(i). | **VERIFIED** |
| **Address-on-Record** | `place_of_supply.py:132-136` | Missing customer state in B2C raises `CUSTOMER_BILLING_STATE_REQUIRED_FOR_B2C`. | **VERIFIED (Safe-Fail)** |
| **Supplier Location** | `place_of_supply.py:60-69` | Resolves supplier state; fails safe if unresolvable. | **VERIFIED** |
| **Intra vs Inter-State** | `place_of_supply.py:145-160` | Supplier code == POS code $\rightarrow$ `INTRA_STATE`; else `INTER_STATE`. | **VERIFIED** |
| **Ambiguous Address** | `place_of_supply.py:63, 79` | Unresolved state names/codes raise `InvalidPlaceOfSupplyException`. | **VERIFIED** |
| **B2B State Mismatch** | `place_of_supply.py:106-123` | GSTIN state legally governs; logs warning; fails if `strict_b2b_state_match=True`. | **VERIFIED** |
| **Section 13 (International)** | `place_of_supply.py` | Non-Indian addresses fail safe with `CUSTOMER_STATE_UNRESOLVED`. | **Out of Scope** |

**Evidence:**
```python
# apps/api/src/subscriptions/tax/place_of_supply.py:145-160
if pos_state_code == supplier_state_code:
    supply_type = SupplyType.INTRA_STATE
    components = (TaxComponentType.CGST, TaxComponentType.SGST)
else:
    supply_type = SupplyType.INTER_STATE
    components = (TaxComponentType.IGST,)
```

---

### AUDIT C — GST TAX ENGINE & MATHEMATICAL PRECISION

| Audit Checkpoint | Source Location | Verified Fact | Assessment |
|:---|:---|:---|:---:|
| **Decimal Precision** | `engine.py:23, 44, 52-54` | All variables are `decimal.Decimal`. Zero `float` usage. | **VERIFIED** |
| **ROUND_HALF_UP** | `engine.py:53-54` | Explicit `amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)`. | **VERIFIED** |
| **Calculation Order** | `engine.py:85-155` | Base $\rightarrow$ Discount $\rightarrow$ Prorated Credit $\rightarrow$ Net Taxable $\rightarrow$ Tax $\rightarrow$ Grand Total. | **VERIFIED** |
| **CGST + SGST Invariant** | `engine.py:135` | `tax_total = quantize_money(cgst_amt + sgst_amt)`. Zero 1-paise discrepancy. | **VERIFIED** |
| **IGST Exclusivity** | `engine.py:128, 140` | CGST/SGST zeroed in inter-state; IGST zeroed in intra-state. | **VERIFIED** |
| **Negative Value Clamping** | `engine.py:86, 91, 99` | Negative base/discount/credit raises `TaxCalculationException`. Base floored at 0. | **VERIFIED** |
| **Zero/Exempt Handling** | `engine.py:115-123` | `is_exempt` or `total_rate == 0` evaluates all tax components to ₹0.00. | **VERIFIED** |
| **Credit Note Reversal** | `engine.py:193-245` | Reverses tax strictly at `original_invoice_snapshot` rates. | **VERIFIED** |

**Evidence:**
```python
# apps/api/src/subscriptions/tax/engine.py:130-135
cgst_amt = quantize_money(taxable_amt * (cgst_rate / PERCENT_DIVISOR))
sgst_amt = quantize_money(taxable_amt * (sgst_rate / PERCENT_DIVISOR))
igst_amt = Decimal("0.00")
tax_total = quantize_money(cgst_amt + sgst_amt)
```

---

### AUDIT D — GSTIN VALIDATION & CHECKSUM

| Checkpoint | Source Location | Verified Fact | Test Evidence |
|:---|:---|:---|:---:|
| **15-Character Pattern** | `gstin_validator.py:29-35` | Regex enforces state(2) + PAN(10) + entity(1) + 'Z' + checksum(1). | `test_gstin_format_and_checksum_validation` |
| **State Code Verification** | `gstin_validator.py:140` | Validates against `GST_STATE_CODES` registry (01–38, 97). | Code 00 rejected |
| **PAN Entity Character** | `gstin_validator.py:153-154`| 4th PAN char verified against `{C, P, H, F, A, T, B, L, J, G}`. | 'Z' rejected |
| **Luhn Mod-36 Checksum** | `gstin_validator.py:73-96` | ISO/IEC 7064 Mod 36, 36 alternating weights (1, 2). | Verified against real-world GSTIN `27AABCU9603R1ZN` (Checksum: `N`) |
| **Registration Status Boundary**| `gstin_validator.py:65, 43-47`| `is_active_registration=None` with explicit disclaimer. | No portal validation claimed |

**Evidence from Live Python Verification:**
```
gstin='27AABCU9603R1ZN' is_valid=True syntactic_valid=True checksum_valid=True state_code='27' state_name='Maharashtra' pan='AABCU9603R' entity_code='1' calculated_checksum='N' error_message=None is_active_registration=None
```

---

### AUDIT E — TAX SNAPSHOT IMMUTABILITY & PERSISTENCE

| Lifecycle Stage | Implementation Reality | Evidence |
|:---|:---|:---|
| **1. Snapshot Generation** | Created in memory with deterministic SHA-256 integrity hash across 14 canonical fields. | `snapshot.py:27-62` |
| **2. Tabular Invoice Persistence** | `taxable_amount`, `cgst_amount`, `sgst_amount`, `igst_amount`, `tax_total`, `grand_total`, `sac_code`, `place_of_supply`, `customer_gstin` persist directly on `PlatformInvoice`. | `test_phase21e4a_pg.py:144-184` |
| **3. Full Snapshot Storage** | Full `TaxSnapshot` JSON dictionary persists inside `PlatformSubscriptionAuditLog.after_state` (JSONB) with `entity_type="TAX_SNAPSHOT"`. | `test_phase21e4a_pg.py:243-255` |
| **4. Historical Reconstruction** | Audit log record deserializes into `TaxSnapshot` and validates SHA-256 integrity hash. | `test_phase21e4a_pg.py:280-286` |
| **5. Tamper Detection** | Modifying any rate, amount, or code causes `verify_snapshot_integrity` to return `False`. | `test_historical_tax_snapshots_and_credit_note_reversal` |
| **6. Credit Note Reversal** | `calculate_credit_note_tax` accepts `original_invoice_snapshot` and applies historical rates. | `engine.py:207-246` |
| **7. Dedicated Table Distinction** | No dedicated `platform_invoice_tax_snapshots` table exists in Migration 0022; relies on audit log. | Verified against `platform_billing.py` |

---

### AUDIT F — POSTGRESQL MULTI-TENANT ISOLATION & SECURITY

| Security Checkpoint | Verification Method | Result | Evidence |
|:---|:---|:---:|:---|
| **FORCE RLS on Billing Tables** | `pg_class.relforcerowsecurity` query | **ENFORCED** | `test_phase21e1_platform_billing_pg.py` |
| **Unprivileged Database Role** | Inspected `app_user` role privileges | **ENFORCED** | `NOSUPERUSER NOBYPASSRLS` (`test_phase21e4a_pg.py:80-82`) |
| **Trusted Session Context** | `SET LOCAL app.current_society_id` | **ENFORCED** | Transaction-local context automatically cleared on commit/abort. |
| **Cross-Tenant Access Denial** | Tenant B queries Tenant A's audit log snapshot | **ZERO LEAKAGE** | Returned `None` (`test_phase21e4a_pg.py:265-266`) |
| **Tenant Access Confirmation** | Tenant A queries Tenant A's audit log snapshot | **ACCESSIBLE** | Returned exact snapshot (`test_phase21e4a_pg.py:276-286`) |
| **No Client-Controlled Bypass** | Code inspection of all tax modules | **CONFIRMED** | Zero dynamic SQL, zero role-switching parameters. |

---

### AUDIT G — MIGRATION AND TEST INTEGRITY

#### Migration Verification
- **Total Migrations:** 22
- **Head Migration:** `20261030_0022_saas_platform_billing.py`
- **Migration 0023:** **DOES NOT EXIST**
- **Schema Modifications:** Zero modifications to existing migrations 0001–0022.

#### Test Execution Evidence
1. **Phase 21E.4A Unit Tests (`tests/test_phase21e4a_tax_engine.py`):**
   - Collected: 15 items | **Passed: 15** | Failed: 0
2. **Phase 21E.4A PostgreSQL Integration Tests (`tests/test_phase21e4a_pg.py`):**
   - Collected: 2 items | **Passed: 2** | Failed: 0
3. **Combined Phase 21E Suite:**
   - Collected: 76 items | **Passed: 76** | Failed: 0 (32.46s)
4. **Full Repository Regression Suite:**
   - Collected: 484 items | **Passed: 482** | **Skipped: 2** | Failed: 0 (929.74s / 15m 29s)

#### Skipped Tests Analysis

| Skipped Test Path | Skipped Test Name | Reason for Skip | Verification |
|:---|:---|:---|:---:|
| `tests/test_phase21b_reconciliation_targeted.py` | `test_03_concurrent_reservation_during_reconciliation` | `SELECT ... FOR UPDATE` row locking is a no-op in SQLite. Skipped only when test engine dialect is SQLite. | Passes on PostgreSQL 16 |
| `tests/test_phase21b_reconciliation_targeted.py` | `test_05_two_concurrent_reconciliation_attempts` | Two concurrent reconciliation lock serialization requires PostgreSQL. Skipped only on SQLite. | Passes on PostgreSQL 16 |

#### Code Quality Gates
- **Ruff:** `All checks passed!` (0 lint errors across all tax files and tests).
- **MyPy:** `Success: no issues found in 11 source files` (Strict type safety).

---

## 4. Legal & Chartered Accountant Dependent Assumptions

Before deploying live billing in production, the following legal and accounting assumptions require formal sign-off:

1. **SAC Code Formal Confirmation:**
   - *Current Proposal:* SAC **998314** (Internet telecommunication / IT infrastructure provision / SaaS web hosting) as the primary billing code, and SAC **998313** (IT consulting and maintenance) as secondary.
   - *CA Action Required:* Formally approve whether SocietySphere subscription fees are billed under SAC 998314 or SAC 998313.
2. **Reverse Charge Mechanism (RCM) Applicability:**
   - *Current Stance:* Forward charge billing where SocietySphere collects 18% GST from tenant societies.
   - *CA Action Required:* Confirm that supplies to unregistered housing societies (RWAs) do not attract RCM under Section 9(4) of the CGST Act.
3. **E-Invoicing Applicability (Rule 48(4) CGST Rules):**
   - *Current Stance:* Invoices do not yet contain an IRN (Invoice Reference Number) or signed QR code.
   - *CA Action Required:* Verify whether SocietySphere's aggregate company turnover exceeds the statutory e-invoicing threshold (currently ₹5 Crores), which would necessitate integration with the Invoice Registration Portal (IRP).
4. **Place of Supply Fallback Discrepancy:**
   - *Current Stance:* The engine fails safe if an unregistered customer (B2C) lacks a billing address state.
   - *CA Action Required:* Validate that mandatory collection of housing society billing state aligns with Section 12(2)(b) compliance without requiring the fallback to supplier location under Section 12(2)(b)(ii).

---

## 5. Foundation Readiness for Phase 21E.4B (Invoice Generation)

### Is Phase 21E.4A a Safe Foundation?
**YES, IT IS SAFE TO PROCEED TO PHASE 21E.4B SUBJECT TO THE CONDITIONS BELOW.**

### Mandatory Conditions for Phase 21E.4B Implementation
1. **Invoice Tax Snapshot Persistence:** When generating a final invoice in Phase 21E.4B, store the complete canonical `TaxSnapshot` JSON dictionary either in an invoice-associated record or ensure the `PlatformSubscriptionAuditLog` is created atomically in the invoice finalization transaction with `entity_type="INVOICE_TAX_SNAPSHOT"` and `entity_id=invoice.id`.
2. **Credit Note Version Preservation:** When generating credit notes, resolve the tax rule version directly from the original invoice's historical snapshot rather than querying the currently active rule from `TaxConfigurationService`.
3. **Multi-Worker Configuration Deployment:** Maintain static configuration files or database backing before exposing any administrative API endpoints for tax rule modification.

---

## 6. Remediation Recommendations (For Future Phases)

1. **Dedicated JSONB Column on `platform_invoices`:** In a future migration (e.g. Migration 0023 or when approved), add a `tax_snapshot` JSONB column directly to `platform_invoices` to eliminate reliance on audit log queries for credit note reversals.
2. **Semantic Versioning Helper:** Update `tax_config.py` candidate sorting to use `packaging.version.Version` or tuple parsing `tuple(map(int, v.split('.')))` to avoid lexicographical string sort anomalies.
3. **Live GSTN Portal Connector:** In a future compliance enhancement, implement a secure client for an authorized GST Suvidha Provider (GSP) sandbox to enable live GSTIN status verification (`is_active_registration=True/False`).

---

## 7. Final Sign-Off & Phase Boundary Enforcement

Phase 21E.4A audit is formally closed with verdict **PASS WITH CONDITIONS**.

> [!IMPORTANT]
> **Strict Phase Boundary Notice:**
> - Phase 21E.4A is locked.
> - No source code, tests, migrations, or database schemas were modified during this audit.
> - Phase 21E.4B (**Invoice Generation & Delivery: Sequential Numbering, HTML/PDF rendering, and Email Delivery**) has **NOT** been started.
> - Awaiting explicit user authorization before starting Phase 21E.4B.
