# SocietySphere — Phase 21E.4A Implementation Report
## GST Tax Engine & Tax Configuration

**Project:** SocietySphere — Enterprise Multi-Tenant Apartment Management SaaS  
**Phase:** Phase 21E.4A (SaaS Billing: GST Tax Engine & Tax Configuration)  
**Author:** Principal FinTech Architect, Indian GST Domain Specialist & Senior Backend Engineer  
**Date:** October 31, 2026  
**Status:** **COMPLETED & VERIFIED (LOCKED)**  

---

## 1. Executive Summary

Phase 21E.4A (**GST Tax Engine & Tax Configuration**) has been successfully implemented, verified with live PostgreSQL 16 database tests, type-checked with MyPy, linted with Ruff, and fully integrated into the SocietySphere SaaS platform.

### Scope & Compliance Highlights
1. **Configurable Tax Rules & SAC Classification:** Implemented a versioned, thread-safe tax configuration registry supporting statutory Service Accounting Code (SAC) classifications (proposing SAC **998313** for IT consulting/support and **998314** for IT infrastructure provisioning/hosting as configurable defaults, never hardcoded), tax rates (CGST, SGST, IGST), effective date intervals (`effective_from` / `effective_to`), rule status (`ACTIVE`, `INACTIVE`, `SUPERSEDED`), and zero/exempt rate handling.
2. **Statutory Place of Supply Engine (IGST Act 2017):** Implemented statutory determination under Sections 12 and 13 of the Integrated Goods and Services Tax (IGST) Act 2017. Accurately determines intra-state (CGST + SGST) versus inter-state (IGST) supply based on supplier location, recipient GSTIN registered state (B2B, Section 12(2)(a)), and customer billing state on record (B2C, Section 12(2)(b)). Fails safely with domain exceptions on missing or ambiguous inputs.
3. **GST Tax Calculation Engine:** Implemented server-side monetary calculation using Python `Decimal` with strict `ROUND_HALF_UP` quantization to `0.01` (2 decimal places). Enforces the exact statutory order of operations:
   $$\text{Gross Amount} \rightarrow \text{Commercial Discount} \rightarrow \text{Prorated Credit} \rightarrow \text{Net Taxable Amount} \rightarrow \text{Component Tax} \rightarrow \text{Final Payable Amount}$$
   Enforces mathematical invariants: $CGST + SGST == Total\ GST$ (preventing 1-paise split rounding discrepancies) and mutual exclusivity between intra-state ($CGST, SGST$) and inter-state ($IGST$) components.
4. **GSTIN Validator & Luhn Mod-36 Verification:** Full statutory 15-character syntax validation, state code verification against the official CBIC registry (01–38, 97), PAN entity type character verification (4th character: `C`, `P`, `H`, `F`, `A`, `T`, `B`, `L`, `J`, `G`), and 15th-character **Luhn Mod-36 checksum** verification algorithm. Explicitly distinguishes format/checksum validity from active GST registration status.
5. **Immutable Tax Snapshots & SHA-256 Integrity:** Generated canonical tax snapshots computing a deterministic SHA-256 digest across tax components, rates, and supply attributes. Ensures historical issued invoices never drift when tax rates or SAC rules change, with runtime tamper detection.
6. **Credit Note & Proration Reversal:** Full integration with Phase 21E.2 `ProrationEngine`. Discounts and proration credits apply *before* tax calculation. Credit notes reverse tax strictly at the original invoice's historical snapshot rates, not current tax rates. Strictly maintains that refunds never generate credit notes or touch tax ledger entries.
7. **Database & Schema Invariant:** Existing migrations `0001`–`0022` remain completely untouched. **Migration 0023 does not exist**. Migration 0022's existing schema (`platform_invoices`, `platform_invoice_items`, `platform_credit_notes`) and JSONB audit logging (`platform_subscription_audit_logs.after_state`) fully accommodate all tax calculations, component breakdowns, and immutable snapshots.
8. **Phase Boundary Enforcement:** Phase 21E.4A is **100% complete**. Phase 21E.4B (**Invoice Generation & Delivery**) has **NOT** been started.

---

## 2. Architecture & Modular Placement

The tax engine is housed under `apps/api/src/subscriptions/tax/` adhering to Clean Architecture principles. It maintains zero tight coupling to external presentation layers, allowing direct reuse across subscription billing, credit note issuance, proration adjustment, and administrative APIs.

```
apps/api/src/subscriptions/tax/
├── __init__.py               # Public API exports
├── exceptions.py             # Domain tax exceptions (HTTP 422 mapping)
├── state_codes.py            # Official CBIC 2-digit Indian State/UT registry
├── gstin_validator.py        # 15-character regex + Luhn Mod-36 checksum
├── models.py                 # Pydantic schemas, Enums (StrEnum), TaxSnapshot
├── place_of_supply.py        # Statutory logic (Sec 12 & 13 IGST Act 2017)
├── tax_config.py             # Versioned, thread-safe tax rule registry
├── snapshot.py               # Immutable TaxSnapshot generation & SHA-256 verification
└── engine.py                 # Core GST calculation, ordering & credit note reversal
```

### Clean Architecture Boundaries
- **Domain Models & Enums (`models.py`):** `TaxComponentType`, `SupplyType`, `SupplyCategory`, `TaxRuleStatus` (subclassing `enum.StrEnum` for modern Python 3.11 compatibility), `TaxRateConfig`, `PlaceOfSupplyInput`, `PlaceOfSupplyResult`, `TaxCalculationInput`, `TaxSnapshot`, `TaxCalculationResult`.
- **Domain Exceptions (`exceptions.py`):** Subclassed from `TaxDomainException` with explicit error codes: `INVALID_PLACE_OF_SUPPLY`, `INVALID_GSTIN`, `TAX_CONFIGURATION_NOT_FOUND`, `TAX_CALCULATION_ERROR`, `TAX_SNAPSHOT_TAMPERED`, `INCOMPATIBLE_CREDIT_NOTE_TAX`. Mapped cleanly to HTTP 422 Unprocessable Content.
- **Statutory State Registry (`state_codes.py`):** Authoritative mapping of 2-digit state codes (01–38, 97) to canonical state names and common aliases (e.g., `"KA"` $\rightarrow$ `"29"`, `"Karnataka"` $\rightarrow$ `"29"`).

---

## 3. Source Files Created

| File Path | Description | Symbols / Exports |
|:---|:---|:---|
| `apps/api/src/subscriptions/tax/__init__.py` | Public tax package exports | All core models, services, exceptions, validators |
| `apps/api/src/subscriptions/tax/exceptions.py` | Domain tax exceptions | `TaxDomainException`, `InvalidPlaceOfSupplyException`, `InvalidGSTINException`, `TaxConfigurationNotFoundException`, `TaxCalculationException`, `TaxSnapshotTamperedException`, `IncompatibleCreditNoteTaxException` |
| `apps/api/src/subscriptions/tax/state_codes.py` | Statutory 2-digit State Registry | `GST_STATE_CODES`, `STATE_NAME_TO_CODE`, `normalize_state()`, `get_state_code()`, `get_canonical_state_name()`, `is_valid_state_code()` |
| `apps/api/src/subscriptions/tax/gstin_validator.py` | GSTIN validation & Luhn Mod-36 | `GSTINValidator`, `GSTINValidationResult` |
| `apps/api/src/subscriptions/tax/models.py` | Pydantic tax data models | `TaxComponentType`, `SupplyType`, `SupplyCategory`, `TaxRuleStatus`, `TaxRateConfig`, `PlaceOfSupplyInput`, `PlaceOfSupplyResult`, `TaxCalculationInput`, `TaxSnapshot`, `TaxCalculationResult` |
| `apps/api/src/subscriptions/tax/place_of_supply.py` | Statutory Place of Supply engine | `PlaceOfSupplyService` |
| `apps/api/src/subscriptions/tax/tax_config.py` | Versioned tax rule registry | `TaxConfigurationService`, `tax_config_service` |
| `apps/api/src/subscriptions/tax/snapshot.py` | SHA-256 snapshot service | `TaxSnapshotService` |
| `apps/api/src/subscriptions/tax/engine.py` | Core calculation & credit note engine | `GSTTaxEngine` |
| `tests/test_phase21e4a_tax_engine.py` | Comprehensive unit test suite (15 tests) | Unit tests covering all 16 prompt specifications |
| `tests/test_phase21e4a_pg.py` | Live PostgreSQL 16 integration tests (2 tests) | DB persistence, RLS isolation under unprivileged role |

---

## 4. Tax Rule Configuration & SAC Classification

### Configurable SAC Codes
Under Indian GST law, services are classified under the Services Accounting Code (SAC).
SocietySphere SaaS services are categorized into two primary SAC classifications:
- **SAC 998313:** Information technology (IT) consulting and support services.
- **SAC 998314:** Information technology (IT) infrastructure provisioning and hosting services (SaaS subscriptions).

> [!IMPORTANT]
> Neither SAC 998313 nor SAC 998314 is hardcoded into calculation algorithms. The system provides them as standard pre-registered default rules via `TaxConfigurationService`, while allowing dynamic registration, updates, and custom SAC definitions at runtime without codebase modifications.

### Rate Breakdown & Versioning
- **Standard Tax Rate:** 18% total GST on SaaS services.
  - **Intra-state Supply:** 9% CGST (Central Goods and Services Tax) + 9% SGST (State Goods and Services Tax).
  - **Inter-state Supply:** 18% IGST (Integrated Goods and Services Tax).
  - **Exempt / Zero-rated Supply:** Configurable with 0% rate (`is_exempt=True` or `is_zero_rated=True`).
- **Temporal Versioning:** Each rule defines `effective_from: date` and optional `effective_to: Optional[date]`. If a rule expires or is superseded, `TaxConfigurationService.get_active_rule(sac_code, as_of_date)` selects the exact rule active on that date.
- **Status Lifecycle:** Rules transition through `ACTIVE` $\rightarrow$ `SUPERSEDED` $\rightarrow$ `INACTIVE`.
- **Thread Safety:** All registry operations are protected by a thread-safe `threading.RLock()`.

---

## 5. Statutory Place of Supply Service (IGST Act 2017)

The `PlaceOfSupplyService` implements statutory determination in accordance with Sections 12 and 13 of the IGST Act 2017:

### Statutory Determination Matrix

| Customer Classification | Statutory Basis | Determination Logic | Supply Type | Tax Components |
|:---|:---|:---|:---|:---|
| **B2B** (Customer GSTIN provided) | Section 12(2)(a) IGST Act | Place of supply is the registered place of business of the recipient (derived from the first 2 digits of the customer's validated GSTIN). If Customer State == Supplier State $\rightarrow$ Intra-state; Else $\rightarrow$ Inter-state. | `INTRA_STATE` or `INTER_STATE` | CGST (9%) + SGST (9%) or IGST (18%) |
| **B2C** (Customer GSTIN absent) | Section 12(2)(b)(i) IGST Act | Place of supply is the location of the recipient on record (Customer billing state address). If Customer State == Supplier State $\rightarrow$ Intra-state; Else $\rightarrow$ Inter-state. | `INTRA_STATE` or `INTER_STATE` | CGST (9%) + SGST (9%) or IGST (18%) |
| **B2C** (Missing/Unrecorded address) | Section 12(2)(b)(ii) IGST Act | If billing address is absent from records, the statutory fallback is the location of the supplier. However, in SocietySphere SaaS, society registration mandates a physical address. If missing or ambiguous, the service fails safely with `InvalidPlaceOfSupplyException`. | N/A (Fails Safe) | Exception Raised (`CUSTOMER_BILLING_STATE_REQUIRED_FOR_B2C`) |
| **Cross-Border / Export** | Section 13 IGST Act | Recipient located outside India (Non-resident / OIDAR). | `INTER_STATE` or `EXPORT` | IGST (18%) or Zero-Rated |

### Safe Failure on Ambiguity
If an unresolvable state name or code is supplied (e.g., `"XX"` or `"Unknown"`), or if an invalid GSTIN is supplied for a B2B transaction, `PlaceOfSupplyService` halts processing and raises `InvalidPlaceOfSupplyException` or `InvalidGSTINException` immediately. It **never** silently defaults to intra-state or inter-state tax.

---

## 6. GST Tax Calculation Engine & Order of Operations

The `GSTTaxEngine` enforces the exact statutory order of operations with strict Decimal precision:

```
[ Base Gross Amount (₹) ]
            │
            ▼
    Less: Commercial Discounts (₹)
            │
            ▼
    Less: Prorated Credits from ProrationEngine (₹)
            │
            ▼
[ Net Taxable Amount (₹) ] ── (Floor at ₹0.00)
            │
            ├─────────────────────────────────────────────────┐
            │ [Intra-State Supply]                            │ [Inter-State Supply]
            ▼                                                 ▼
   CGST = ROUND_HALF_UP(Net * 9%)                    IGST = ROUND_HALF_UP(Net * 18%)
   SGST = ROUND_HALF_UP(Net * 9%)                    CGST = 0.00, SGST = 0.00
   Tax Total = CGST + SGST                           Tax Total = IGST
            │                                                 │
            └───────────────────────┬─────────────────────────┘
                                    │
                                    ▼
                         [ Final Grand Total (₹) ]
                     Net Taxable Amount + Tax Total
```

### Invariants Enforced
1. **Paise Integrity ($CGST + SGST == Tax\ Total$):**
   To prevent single-paise rounding discrepancies when tax is divided into CGST and SGST, the engine computes $CGST$ and $SGST$ using `ROUND_HALF_UP` and defines total tax as:
   $$\text{Tax Total} = \text{CGST} + \text{SGST}$$
   This guarantees that the sum of the components equals the total tax on the invoice to the exact paise.
2. **Mutual Exclusivity:**
   An invoice or line item **must never** have both IGST and (CGST/SGST) simultaneously:
   - For `INTRA_STATE`: $IGST = 0.00$; $CGST > 0.00$, $SGST > 0.00$.
   - For `INTER_STATE`: $CGST = 0.00$, $SGST = 0.00$; $IGST > 0.00$.
3. **Credit Clamping:**
   Discounts and prorated credits cannot reduce the net taxable base below ₹0.00. Excess credits are preserved for future cycles.

---

## 7. Decimal & Monetary Precision Policy

- **Zero Float Rule:** The tax module does not use Python `float` or IEEE 754 floating-point primitives for financial calculations. All rates, gross amounts, discounts, credits, and tax components use `decimal.Decimal`.
- **Rounding Algorithm:** Rounding is strictly performed using `decimal.ROUND_HALF_UP` quantized to `Decimal("0.01")`.
  - For example:
    - Base ₹100.005 $\rightarrow$ ₹100.01
    - Base ₹100.004 $\rightarrow$ ₹100.00
    - Base ₹100.055 $\rightarrow$ ₹100.06
- **Test Verification:** Verified by `test_decimal_precision_no_float` and `test_round_half_up_monetary_behavior` with edge cases down to fractional paise.

---

## 8. GSTIN Validation & Luhn Mod-36 Checksum

The `GSTINValidator` performs a thorough 4-tier validation on Indian Goods and Services Tax Identification Numbers:

### 1. Structural Format (Regex)
Enforces the 15-character statutory alphanumeric pattern:
`^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}$`

### 2. State Code Verification
The first 2 digits must correspond to a valid state or union territory in the official CBIC registry (codes `01` through `38`, plus `97` for Other Territory).

### 3. PAN Entity Character Verification
The 4th character of the embedded 10-character PAN (characters 3–12) must represent a recognized legal entity type:
`C` (Company), `P` (Person/Individual), `H` (HUF), `F` (Firm/LLP), `A` (AOP), `T` (Trust), `B` (BOI), `L` (Local Authority), `J` (Artificial Juridical Person), `G` (Government).

### 4. Luhn Mod-36 Checksum Verification
The 15th character is a checksum digit calculated across the first 14 characters using the standard ISO/IEC 7064 Mod 36, 36 / Luhn Mod-36 algorithm:
$$\text{Character Set: } 0\text{--}9 \rightarrow 0\text{--}9,\; A\text{--}Z \rightarrow 10\text{--}35$$
$$\text{Weights: alternating between 1 and 2 for each character}$$
$$\text{Remainder: } (36 - (\sum \text{weighted\_values} \pmod{36})) \pmod{36}$$

### Format Validity vs Active GST Registration
> [!NOTE]
> The engine strictly distinguishes between:
> 1. **Syntactic & Mathematical Validity:** Formally valid structure, valid state, valid PAN entity, and correct Luhn Mod-36 checksum. Verified offline without external dependencies.
> 2. **Active Registration Status:** Whether the GSTIN is active, cancelled, or suspended on the live GSTN portal. Validating active status requires an external GST Suvidha Provider (GSP) or sandbox API connection. The validator reports `format_valid=True, checksum_valid=True, active_status_verified=False` to maintain this transparent boundary.

---

## 9. Immutable Tax Snapshots

To prevent historical tax drift when government tax rates or SAC classifications change, `TaxSnapshotService` captures a point-in-time snapshot upon invoice finalization.

### Snapshot Structure & Canonical Hashing
A `TaxSnapshot` contains:
- `tax_rule_id`: Identifier of the applied rule.
- `sac_code`: SAC code applied.
- `supply_type`: `INTRA_STATE` or `INTER_STATE`.
- `place_of_supply`: 2-digit state code and canonical name.
- `supplier_gstin` & `customer_gstin`: Party tax identifiers.
- `taxable_amount`: Net taxable amount base.
- `cgst_rate`, `cgst_amount`, `sgst_rate`, `sgst_amount`, `igst_rate`, `igst_amount`, `tax_total`.
- `created_at`: UTC timestamp.
- `snapshot_hash`: Deterministic SHA-256 digest.

### Integrity Hash Computation
The digest is calculated across a canonical JSON representation of sorted key-value pairs. Any modification to tax amounts, rates, or identifiers invalidates the hash. `TaxSnapshotService.verify_snapshot()` verifies integrity and raises `TaxSnapshotTamperedException` if tampering is detected.

---

## 10. Credit Note & Proration Tax Reversal

### Tax Reversal at Historical Rates
When an invoice is adjusted, cancelled, or credited via a `PlatformCreditNote`, the tax reversal **must not** use current tax configuration rates.
The engine invokes `GSTTaxEngine.calculate_credit_note_tax(credit_taxable_amount, original_snapshot)`:
- Reads the historical snapshot embedded in the original invoice.
- Reverses CGST, SGST, or IGST using the exact historical rates locked at the time of issuance.
- Validates that the credit taxable amount does not exceed the original invoice's net taxable base.

### Discount & Proration Integration
- Commercial discounts and Phase 21E.2 proration credits are applied to the base amount *before* tax computation. Tax is only calculated on the resulting net taxable amount.
- **Refund Invariant Preserved:** Phase 21E.3 refund transactions never generate credit notes or alter tax ledger entries. Credit notes are strictly accounting adjustments, whereas gateway refunds are financial reversals.

---

## 11. Multi-Tenant Isolation & PostgreSQL FORCE RLS

### Database Architecture Reuse
Phase 21E.1 Migration `0022_saas_platform_billing.py` pre-configured all required statutory columns on billing tables:
- `platform_invoices`: `sac_code`, `place_of_supply`, `customer_gstin`, `taxable_amount`, `cgst_amount`, `sgst_amount`, `igst_amount`, `tax_total`, `grand_total`.
- `platform_invoice_items`: `sac_code`, `tax_rate`, `tax_amount`, `cgst_amount`, `sgst_amount`, `igst_amount`, `total_amount`.
- `platform_credit_notes`: `taxable_amount`, `cgst_amount`, `sgst_amount`, `igst_amount`, `tax_total`, `grand_total`.
- `platform_subscription_audit_logs`: `JSONB` `after_state` column storing the complete canonical `TaxSnapshot` payload.

### Live PostgreSQL 16 RLS Verification
Verified under live PostgreSQL 16 in `tests/test_phase21e4a_pg.py`:
1. `test_pg_tax_calculation_persistence_and_invariants`: Verifies insertion, querying, and mathematical invariants of tax calculation fields under standard database sessions.
2. `test_pg_tax_snapshot_in_audit_log_rls_isolation`: Verifies that `TaxSnapshot` JSONB payloads stored in audit logs are strictly protected by `FORCE ROW LEVEL SECURITY` under the unprivileged `app_user` (`NOBYPASSRLS`). Setting `app.current_society_id` permits visibility only to the tenant's own tax records, and prevents access to other societies.

---

## 12. Database Migration Verification

```
Total Migrations: 22
Head Migration: 20261030_0022_saas_platform_billing.py
Migration 0023: DOES NOT EXIST (Not required)
```

No database migrations were created or modified during Phase 21E.4A. Migrations `0001` through `0022` remain locked and unchanged.

---

## 13. Quality Gates & Test Suite Results

### 1. Phase 21E.4A Tax Engine Unit Tests (`tests/test_phase21e4a_tax_engine.py`)
| Test Name | Focus | Result |
|:---|:---|:---:|
| `test_intrastate_gst_calculation` | Intra-state 9% CGST + 9% SGST split, place of supply | **PASSED** |
| `test_interstate_gst_calculation` | Inter-state 18% IGST calculation | **PASSED** |
| `test_cgst_sgst_split_exact_sum_invariant` | Mathematical invariant $CGST + SGST == Tax\ Total$ | **PASSED** |
| `test_igst_calculation_precision` | IGST calculation precision and mutual exclusivity | **PASSED** |
| `test_zero_or_exempt_tax_rate` | Zero-rate and exempt SAC rules | **PASSED** |
| `test_sac_configuration_lookup_and_custom_registration` | Dynamic SAC registration and retrieval | **PASSED** |
| `test_effective_date_configuration_versioning` | Temporal rule versioning and superseded rules | **PASSED** |
| `test_gstin_format_and_checksum_validation` | 15-char regex, state code, PAN entity, Luhn Mod-36 | **PASSED** |
| `test_decimal_precision_no_float` | Decimal type enforcement, zero float usage | **PASSED** |
| `test_round_half_up_monetary_behavior` | Strict ROUND_HALF_UP rounding down to fractional paise | **PASSED** |
| `test_commercial_discounts_applied_before_tax` | Order of operations: Gross $\rightarrow$ Discount $\rightarrow$ Net Taxable | **PASSED** |
| `test_prorated_credits_integration` | Proration credit integration before tax calculation | **PASSED** |
| `test_historical_tax_snapshots_and_credit_note_reversal` | SHA-256 snapshot integrity & historical credit reversal | **PASSED** |
| `test_invalid_place_of_supply_inputs_fail_safe` | Safe failure on invalid/ambiguous supply inputs | **PASSED** |
| `test_concurrent_tax_configuration_access` | Multi-threaded concurrency and thread safety | **PASSED** |

### 2. Phase 21E.4A Live PostgreSQL Tests (`tests/test_phase21e4a_pg.py`)
| Test Name | Focus | Result |
|:---|:---|:---:|
| `test_pg_tax_calculation_persistence_and_invariants` | DB persistence of tax amounts & database check constraints | **PASSED** |
| `test_pg_tax_snapshot_in_audit_log_rls_isolation` | JSONB tax snapshot persistence & FORCE RLS isolation under unprivileged role | **PASSED** |

### 3. Combined Phase 21E Test Suite
Running all Phase 21E tests (`test_phase21e1_*`, `test_phase21e2_*`, `test_phase21e3_*`, `test_phase21e4a_*`):
$$\mathbf{76\ passed\ in\ 32.46s\ (100\%\ Pass\ Rate)}$$

### 4. Full Repository Regression Test Suite
Running full repository test suite across all 21 phases:
$$\mathbf{482\ passed,\ 2\ skipped\ in\ 929.74s\ (15m\ 29s)\ (100\%\ Pass\ Rate)}$$
*(Note: 2 skipped tests are SQLite-specific skips for PostgreSQL concurrency locks).*

---

## 14. Static Analysis & Type Checking

### Ruff Linter
```bash
.venv\Scripts\ruff.exe check apps/api/src/subscriptions/tax/ tests/test_phase21e4a*
# Output:
All checks passed!
```

### MyPy Static Type Checker
```bash
.venv\Scripts\mypy.exe apps/api/src/subscriptions/tax/ tests/test_phase21e4a_tax_engine.py tests/test_phase21e4a_pg.py
# Output:
Success: no issues found in 11 source files
```

---

## 15. Known Limitations

1. **GSTN Live Portal Connectivity:** The `GSTINValidator` performs full syntactic, state code, PAN entity, and Luhn Mod-36 checksum verification offline. It does not perform live network calls to the government GSTN portal to verify active GSTIN filing status. Integrating live status verification requires contracting with a certified GST Suvidha Provider (GSP) or the NIC sandbox API.
2. **Special Economic Zone (SEZ) / EOU Documentation:** Supplies to SEZ units or developers can be treated as inter-state zero-rated supplies under Section 16 of the IGST Act, but require a Letter of Undertaking (LUT) or tax payment with refund claim. The engine supports zero-rate rules, but automated SEZ documentation collection is outside Phase 21E.4A.

---

## 16. Outstanding Chartered Accountant / Legal Consultation Items

1. **SAC Code Final Selection:** Confirm whether SocietySphere's cloud software subscription is officially billed under SAC **998314** (IT infrastructure provisioning/hosting) or SAC **998313** (IT consulting and support). Both are pre-configured, but corporate CA approval should be formally recorded before issuing live customer invoices.
2. **Reverse Charge Mechanism (RCM):** Under Section 9(3) / 9(4) of the CGST Act, confirm whether any services received from unregistered societies or vendors attract reverse charge. Currently, SocietySphere provides services as a forward charge SaaS platform.
3. **E-Invoicing Applicability (Rule 48(4) of CGST Rules):** If SocietySphere's aggregate turnover exceeds ₹5 Crores, B2B invoices must be reported to the Invoice Registration Portal (IRP) to generate an Invoice Reference Number (IRN) and signed QR code. Phase 21E.4B should account for IRN storage.

---

## 17. Phase Boundary & Next Steps

Phase 21E.4A is **fully implemented, tested, verified, and locked**.

> [!CAUTION]
> Phase 21E.4B (**Invoice Generation & Delivery: Numbering, PDF/HTML generation, and Email Delivery**) has **NOT** been started. Awaiting explicit user authorization before proceeding to Phase 21E.4B.
