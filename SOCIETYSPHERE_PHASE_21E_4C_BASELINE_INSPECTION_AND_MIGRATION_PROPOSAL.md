# SOCIETYSPHERE — PHASE 21E.4C BASELINE INSPECTION & MIGRATION PROPOSAL

**Author:** Principal SaaS Architect, Senior Financial Domain Engineer, Indian GST Domain Reviewer, PostgreSQL Security Engineer & Senior QA Engineer  
**Date:** November 1, 2026  
**Status:** ARCHITECTURAL GATE — STOPPED FOR APPROVAL  
**Phase:** 21E.4C — Credit Note Workflow & Balance Adjustments  
**Action:** Inspection completed; Schema Gaps Identified; Migration 0023 Proposed; Awaiting Explicit Approval  

---

## 1. Executive Summary & Authorization Check

In accordance with the mandatory instructions for **Phase 21E.4C**, this document constitutes the formal **Baseline Inspection Report** (Section 2) and **Migration Proposal** (Section 13).

The authorized scope is strictly Phase 21E.4C (Credit Note Workflow & Balance Adjustments). Phase 21E.4A (GST Tax Engine) and Phase 21E.4B (Invoice Generation & Finalization) are complete, verified, and locked.

### The Stop Gate Trigger
Section 13 and the Final Stop Gate explicitly mandate:
> *"Inspect whether PlatformCreditNote and existing related tables support the required workflow. Reuse existing schema where safe. If schema changes are required, STOP and provide a migration proposal... Do not create migration 0023 or any later migration without explicit approval."*
>
> *"FINAL STOP GATE: If a migration is required: STOP and submit the migration proposal. Do not implement it without approval."*

Our thorough inspection of the actual source code and PostgreSQL 16 schema confirms that **Migration 0022 cannot support the required Credit Note domain and lifecycle without schema alterations**. Specifically, PostgreSQL check constraints, NOT NULL column definitions, and the total absence of a credit note line-item table prevent draft persistence and granular partial credit note issuance.

Therefore, execution is **strictly stopped at this gate**, and the complete Migration 0023 specification is submitted herein for architectural review and explicit authorization.

---

## 2. Baseline Inspection: Existing Implementation vs. Requirements

### 2.1 Existing Functionality (Phases 21E.1 – 21E.4B)

| Component | Location | Existing Capabilities |
|---|---|---|
| **`PlatformCreditNote`** | `apps/api/src/database/models/platform_billing.py:774` | Relational table `platform_credit_notes`, foreign key to `platform_invoices`, financial year, monetary amount columns (`taxable_amount`, `cgst_amount`, `sgst_amount`, `igst_amount`, `tax_total`, `grand_total`), tenant-scoped with PostgreSQL FORCE RLS. |
| **`PlatformInvoice`** | `apps/api/src/database/models/platform_billing.py:205` | Tracks `grand_total`, `credits_applied`, `amount_paid`, and `amount_due`. Has `credit_notes` relationship. Enforces `amount_due >= 0`. |
| **`PlatformBillingAdjustment`** | `apps/api/src/database/models/platform_billing.py:877` | Pre-existing FK `credit_note_id` to `platform_credit_notes.id`. Supports `adjustment_type IN ('PRORATION_CREDIT', 'GOODWILL_WAIVER', 'ADVANCE_BALANCE', 'MINIMUM_CHARGE_ROUNDOFF')`. |
| **`PlatformInvoiceSequence`** | `apps/api/src/database/models/platform_billing.py:261` | Table `platform_invoice_sequences` with `fiscal_year VARCHAR(10) PRIMARY KEY`, `current_sequence INTEGER NOT NULL DEFAULT 0`. Used by `InvoiceNumberingService` with `SELECT ... FOR UPDATE` pessimistic row locking. |
| **`PlatformRefund` & `RefundService`** | `apps/api/src/subscriptions/payments/refund_service.py` | Handles outbound gateway refunds against captured payments. Strictly decoupled: refunds never automatically generate credit notes. |
| **`PaymentSettlementService`** | `apps/api/src/subscriptions/payments/settlement_service.py` | Atomic payment settlement updating `PlatformInvoice.amount_paid` and `amount_due`. |
| **`GSTTaxEngine` & `calculate_credit_note_tax`** | `apps/api/src/subscriptions/tax/engine.py:198` | Reconstructs symmetric `historical_rule` directly from original invoice's `TaxSnapshot`, preserving historical rates, SAC codes, and configuration version (Resolving Finding M-2). |
| **`TaxSnapshotService`** | `apps/api/src/subscriptions/tax/snapshot.py` | Computes and verifies SHA-256 cryptographic digest across canonical snapshot fields (Resolving Finding M-3). |
| **`PlatformInvoiceService`** | `apps/api/src/subscriptions/invoicing/service.py` | Complete invoice lifecycle (`DRAFT` $\rightarrow$ `ISSUED` $\rightarrow$ `PAID` / `VOID`). Persists tax snapshots in `PlatformSubscriptionAuditLog`. |

---

### 2.2 Missing Functionality & Architectural Gaps in Migration 0022

Our inspection revealed **five critical gaps** in the existing Migration 0022 schema:

#### Gap 1: Status Check Constraint Rejects `'DRAFT'`
In Migration 0022 (`20261030_0022_saas_platform_billing.py:550`) and `PlatformCreditNote`:
```sql
CONSTRAINT ck_platform_credit_notes_status CHECK (status IN ('ISSUED', 'VOID'))
```
* **Conflict:** Section 4 mandates lifecycle `DRAFT` $\rightarrow$ `ISSUED` $\rightarrow$ `VOID`. Section 12 mandates APIs to create, retrieve, and update draft credit notes.
* **Failure Mode:** Any attempt to persist a credit note in `DRAFT` state raises `asyncpg.exceptions.CheckViolationError`.

#### Gap 2: `credit_note_number` is `NOT NULL`
In Migration 0022 (`line 514`):
```sql
credit_note_number VARCHAR(50) NOT NULL UNIQUE
```
* **Conflict:** Under sequential numbering and accounting standards, official sequential numbers (`SS-CN-2627-00001`) must only be assigned upon final issuance (`DRAFT` $\rightarrow$ `ISSUED`). Drafts cannot have pre-allocated numbers.
* **Failure Mode:** Inserting a draft requires either a dummy placeholder number (which risks collisions and pollutes unique constraints) or violates the `NOT NULL` constraint.

#### Gap 3: `issued_at` is `NOT NULL`
In Migration 0022 (`line 526`):
```sql
issued_at TIMESTAMP WITH TIME ZONE NOT NULL
```
* **Conflict:** An unissued draft has no valid `issued_at` timestamp. Setting it at draft creation falsely records unfinalized drafts as issued.
* **Failure Mode:** Inserting a draft without an issue date violates `NOT NULL`.

#### Gap 4: Total Absence of a Credit Note Line-Item Table
* **Conflict:** Section 5 ("Full and Partial Credit Notes") mandates:
  - *"Credit a specified eligible invoice line or amount."*
  - *"Preserve original SAC and applicable tax rates."*
  - *"Per-line credit must never exceed the eligible original invoice line value."*
  - *"Add/remove permitted draft credit note lines."*
* **Failure Mode:** Migration 0022 contains `platform_invoice_items`, but **zero** table for credit note line items. Without a `platform_credit_note_items` table, per-line credit allocations, line-level SAC tracking, and item-level eligibility verification cannot be persisted relationally.

#### Gap 5: Sequence Counter Segregation
* **Conflict:** Credit notes require dedicated, auditable financial-year sequence numbers (e.g. `SS-CN-2627-00001`) that are distinct from invoice sequences (`SS-2627-00001`).
* **Failure Mode:** Reusing `platform_invoice_sequences` with a composite key hack (`fiscal_year="CN-2627"`) is fragile. A dedicated table `platform_credit_note_sequences` guarantees clean domain separation and isolated row locking.

---

## 3. Domain Boundary: Credit Note vs. Refund

Phase 21E.4C strictly maintains separation between accounting credit notes and payment refunds:

```
+-----------------------------------------------------------------------------------+
|                                 DOMAIN BOUNDARY                                   |
+-----------------------------------------+-----------------------------------------+
|               CREDIT NOTE               |                 REFUND                  |
|          (Accounting Adjustment)        |            (Cash Disbursal)             |
+-----------------------------------------+-----------------------------------------+
| Reduces or corrects invoice obligation. | Represents actual money returned.       |
| References original PlatformInvoice.    | References captured PlatformPayment.    |
| Reverses GST based on TaxSnapshot.      | Reverses gateway charge via Provider.   |
| Stored in platform_credit_notes.        | Stored in platform_refunds.             |
| NEVER initiates gateway refund.         | NEVER creates statutory credit note.    |
| Governed by GST Rule 53 / SAC codes.    | Governed by RBI / Gateway settlement.   |
+-----------------------------------------+-----------------------------------------+
```

### Invariant Rules
1. Issuing a credit note **never** triggers an automated gateway refund.
2. Gateway refunds through `RefundService` **never** automatically generate a credit note.
3. If a credit note is issued against an already paid invoice, the excess payment becomes an **unapplied customer credit balance** recorded in `PlatformBillingAdjustment` (`adjustment_type='ADVANCE_BALANCE'`), NOT an automated cash refund.

---

## 4. Invoice Balance Adjustment Mechanics

The outstanding invoice receivable balance is governed by:

$$\text{Outstanding Balance} = \max\left(0, \text{Original Grand Total} - \text{Settled Payments} - \text{Issued Credit Notes}\right)$$

### Verification of Prescribed Scenarios

#### Scenario 1: Unpaid Invoice with Partial Credit Note
* **Original Invoice:** ₹11,800.00
* **Settled Payments:** ₹0.00
* **Credit Note Issued:** ₹2,360.00
* **Calculation:**
  - $\text{Invoice Obligation} = ₹11,800.00 - ₹2,360.00 = ₹9,440.00$
  - $\text{Amount Paid} = ₹0.00$
  - $\text{Outstanding Balance (amount\_due)} = ₹9,440.00$
  - $\text{Customer Excess Credit} = ₹0.00$

#### Scenario 2: Partially Paid Invoice with Partial Credit Note
* **Original Invoice:** ₹11,800.00
* **Settled Payments:** ₹5,000.00
* **Credit Note Issued:** ₹2,000.00
* **Calculation:**
  - $\text{Adjusted Invoice Obligation} = ₹11,800.00 - ₹2,000.00 = ₹9,800.00$
  - $\text{Amount Paid} = ₹5,000.00$
  - $\text{Outstanding Balance (amount\_due)} = ₹9,800.00 - ₹5,000.00 = ₹4,800.00$
  - $\text{Customer Excess Credit} = ₹0.00$

#### Scenario 3: Fully Paid Invoice with Partial Credit Note
* **Original Invoice:** ₹11,800.00
* **Settled Payments:** ₹11,800.00 (`PAID` status)
* **Credit Note Issued:** ₹2,000.00
* **Calculation:**
  - $\text{Adjusted Invoice Obligation} = ₹11,800.00 - ₹2,000.00 = ₹9,800.00$
  - $\text{Amount Paid} = ₹11,800.00$
  - $\text{Outstanding Receivable (amount\_due)} = ₹0.00$
  - $\text{Invoice credits\_applied} = ₹2,000.00$
  - $\text{Unapplied Customer Credit Balance} = ₹2,000.00$
* **Ledger Treatment:**
  - The ₹2,000.00 excess is persisted in `PlatformBillingAdjustment` with `adjustment_type='ADVANCE_BALANCE'`, `credit_note_id=cn.id`, `amount=2000.00`.
  - The original `PlatformPayment` of ₹11,800.00 is **not** modified.
  - No gateway refund is triggered.

---

## 5. Accounting Integration Boundary (Section 9)

### Current Architecture Assessment
The existing `NativeAccountingProvider` (`apps/api/src/finance/providers/native.py`) manages society-internal resident accounting:
- Accounts: Resident maintenance dues, society bank accounts, amenity fee ledgers.
- Entities: `invoices`, `units`, `journal_entries`, `accounts`.

### Integration Boundary Declaration
* **Platform SaaS Billing is B2B:** SocietySphere charges Societies for SaaS subscription tiers.
* **Resident Accounting Isolation:** Posting platform subscription credit notes into a tenant's internal resident ledger would erroneously credit resident maintenance accounts and violate Clean Architecture.
* **Design Decision:** The credit note domain implements complete transactional consistency, balance tracking, and immutable audit logging within `PlatformCreditNote`, `PlatformBillingAdjustment`, and `PlatformSubscriptionAuditLog`.
* **Explicit Compliance Statement:** As mandated by Section 9, we **do not claim resident accounting posting is complete** and do not write fake entries to resident `journal_entries`. An enterprise platform-level ledger hook interface is specified for future multi-ledger integration.

---

## 6. Indian GST & Statutory Boundaries (Section 10)

The credit note engine implements deterministic financial arithmetic in compliance with Indian GST Section 34 / Rule 53 principles:
1. **Historical Snapshot Binding:** Credit note tax calculations consume the original invoice's `TaxSnapshot` via `GSTTaxEngine.calculate_credit_note_tax`, locking original SAC codes and tax rates.
2. **Cryptographic Verification:** Rejects issuance if the original snapshot SHA-256 digest fails verification.
3. **Statutory Non-Claims:**
   - Sequential numbering (`SS-CN-2627-00001`) is an internal system format; statutory gapless certification requires formal Chartered Accountant sign-off.
   - Government GST Portal filing, E-Invoicing (IRN), and signed QR generation are explicitly out of scope.
   - Output tax liability reduction eligibility under Section 34(2) depends on commercial circumstances and must be evaluated by a qualified tax advisor.

---

## 7. Migration 0023 Specification (Proposed)

To safely resolve Gaps 1–5 without compromising existing Phase 21E.1–21E.4B functionality, the following migration is submitted for approval:

### 7.1 Migration Metadata
* **File:** `apps/api/alembic/versions/20261102_0023_saas_credit_notes.py`
* **Revision:** `0023`
* **Down Revision:** `0022` (`20261030_0022_saas_platform_billing`)
* **Target Database:** PostgreSQL 16 with FORCE RLS

### 7.2 Proposed DDL Modifications

```python
"""Phase 21E.4C — SaaS Credit Note Schema Enhancements.

Revision ID: 0023
Revises: 0022
"""

from collections.abc import Sequence
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0023"
down_revision: str | None = "0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # -------------------------------------------------------------------------
    # 1. Update platform_credit_notes constraints & nullability for DRAFT support
    # -------------------------------------------------------------------------
    # Allow NULL credit_note_number during DRAFT status
    op.alter_column(
        "platform_credit_notes",
        "credit_note_number",
        existing_type=sa.String(50),
        nullable=True,
    )
    
    # Allow NULL issued_at during DRAFT status
    op.alter_column(
        "platform_credit_notes",
        "issued_at",
        existing_type=sa.DateTime(timezone=True),
        nullable=True,
    )
    
    # Update status check constraint to include 'DRAFT'
    op.drop_constraint("ck_platform_credit_notes_status", "platform_credit_notes", type_="check")
    op.create_check_constraint(
        "ck_platform_credit_notes_status",
        "platform_credit_notes",
        "status IN ('DRAFT', 'ISSUED', 'VOID')",
    )

    # -------------------------------------------------------------------------
    # 2. Create Global Table: platform_credit_note_sequences
    # -------------------------------------------------------------------------
    op.create_table(
        "platform_credit_note_sequences",
        sa.Column("fiscal_year", sa.String(10), primary_key=True),
        sa.Column("current_sequence", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "current_sequence >= 0",
            name="ck_platform_credit_note_sequences_non_negative",
        ),
    )

    # -------------------------------------------------------------------------
    # 3. Create Tenant Table: platform_credit_note_items
    # -------------------------------------------------------------------------
    op.create_table(
        "platform_credit_note_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "credit_note_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("platform_credit_notes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "society_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("societies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "invoice_item_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("platform_invoice_items.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("item_index", sa.Integer(), nullable=False),
        sa.Column("description", sa.String(255), nullable=False),
        sa.Column("sac_code", sa.String(20), nullable=False, server_default="998313"),
        sa.Column("quantity", sa.Numeric(12, 4), nullable=False, server_default="1.0000"),
        sa.Column("unit_price", sa.Numeric(12, 2), nullable=False),
        sa.Column("taxable_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("tax_rate", sa.Numeric(5, 2), nullable=False, server_default="18.00"),
        sa.Column("tax_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("total_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint(
            "credit_note_id", "item_index", name="uq_platform_credit_note_items_index"
        ),
        sa.CheckConstraint(
            "taxable_amount > 0",
            name="ck_platform_credit_note_items_taxable_positive",
        ),
    )
    op.create_index(
        "ix_platform_credit_note_items_credit_note",
        "platform_credit_note_items",
        ["credit_note_id"],
    )
    op.create_index(
        "ix_platform_credit_note_items_society",
        "platform_credit_note_items",
        ["society_id"],
    )
    op.create_index(
        "ix_platform_credit_note_items_invoice_item",
        "platform_credit_note_items",
        ["invoice_item_id"],
    )

    # -------------------------------------------------------------------------
    # 4. Enable & Force Row-Level Security on platform_credit_note_items
    # -------------------------------------------------------------------------
    op.execute("ALTER TABLE platform_credit_note_items ENABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE platform_credit_note_items FORCE ROW LEVEL SECURITY;")
    op.execute(
        "CREATE POLICY platform_credit_note_items_tenant_isolation ON platform_credit_note_items "
        "USING (society_id = NULLIF(current_setting('app.current_society_id', true), '')::uuid);"
    )


def downgrade() -> None:
    # 1. Drop RLS and table platform_credit_note_items
    op.execute("DROP POLICY IF EXISTS platform_credit_note_items_tenant_isolation ON platform_credit_note_items;")
    op.execute("ALTER TABLE platform_credit_note_items NO FORCE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE platform_credit_note_items DISABLE ROW LEVEL SECURITY;")
    op.drop_table("platform_credit_note_items")

    # 2. Drop table platform_credit_note_sequences
    op.drop_table("platform_credit_note_sequences")

    # 3. Revert platform_credit_notes constraints & nullability
    op.drop_constraint("ck_platform_credit_notes_status", "platform_credit_notes", type_="check")
    op.create_check_constraint(
        "ck_platform_credit_notes_status",
        "platform_credit_notes",
        "status IN ('ISSUED', 'VOID')",
    )
    op.alter_column(
        "platform_credit_notes",
        "issued_at",
        existing_type=sa.DateTime(timezone=True),
        nullable=False,
    )
    op.alter_column(
        "platform_credit_notes",
        "credit_note_number",
        existing_type=sa.String(50),
        nullable=False,
    )
```

### 7.3 Data Integrity & Compatibility Guarantees
1. **Zero Data Loss:** All existing columns on `platform_credit_notes` are preserved. Nullability relaxation only applies to unissued drafts.
2. **Backward Compatibility:** All existing records in `platform_credit_notes` are in `ISSUED` or `VOID` status and already have non-null `credit_note_number` and `issued_at`. They remain 100% compliant.
3. **Phases 21E.1–21E.4B Immunity:** No queries, models, or constraints from previous phases are broken.
4. **PostgreSQL FORCE RLS:** Applied to `platform_credit_note_items`, maintaining the `NOBYPASSRLS` security boundary.

---

## 8. Architectural Decision Options

We present two potential paths forward for user decision:

### Option A (Recommended): Approve Migration 0023
* **Description:** Apply the proposed Migration 0023. Implement full persistent draft credit notes, itemized line crediting, dedicated sequence counters, and live PostgreSQL 16 verification.
* **Pros:** 100% compliant with enterprise clean architecture, durable draft persistence, granular line-item tracking, and audit integrity.
* **Cons:** Introduces Migration 0023.

### Option B: Immediate In-Line Issuance (Zero Migration)
* **Description:** Forgo persistent draft credit notes and per-line item tables. Credit notes are created and issued atomically in a single operation (`POST /platform/credit-notes/issue`) with aggregate amounts. Draft preview is calculated on-the-fly (`POST /platform/credit-notes/preview`) without saving draft rows to PostgreSQL.
* **Pros:** Strict zero-migration constraint preserved (head remains Migration 0022).
* **Cons:** Draft credit notes cannot be persisted or retrieved across sessions; line items are not stored in a dedicated relational table (stored only in the audit log tax snapshot).

---

## 9. Conclusion & Stop Gate Status

In compliance with the **Final Stop Gate**:
* **Migration 0023 has NOT been created.**
* **Source code has NOT been modified.**
* **Database migrations remain at head `0022_saas_platform_billing`.**
* **We are stopped and awaiting your explicit instruction on whether to proceed with Option A (Approve Migration 0023) or Option B (Zero-Migration Atomic Issuance).**
