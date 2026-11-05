# Financial Core & Accounting Foundation Documentation

## Overview
SocietySphere's Financial Core is an enterprise-grade, multi-tenant double-entry accounting engine built specifically for housing societies and apartment associations. It provides mathematical correctness, audit immutability, fiscal period governance, and pluggable accounting provider integration.

---

## Core Principles

### 1. Mathematical Rigor & Precision
- **No Floating Point**: All calculations use Python's `Decimal` type quantized to 4 decimal places (`0.0001`) with `ROUND_HALF_UP` rounding.
- **Database Storage**: All monetary fields are backed by `NUMERIC(18, 4)` columns in PostgreSQL.
- **Double-Entry Equation**: For every journal entry, the sum of debits must identically equal the sum of credits:
  $$\sum \text{Debits} - \sum \text{Credits} = 0$$
- **Line Constraints**: Every journal entry line must contain a non-zero debit or credit, but never both, enforced via database check constraints:
  ```sql
  CHECK ((debit_amount > 0 AND credit_amount = 0) OR (credit_amount > 0 AND debit_amount = 0))
  ```

### 2. Audit Immutability & Safe Reversals
- **No In-Place Modifications**: Once a journal entry moves to `POSTED`, its header and line items cannot be modified or deleted.
- **Balanced Reversals**: To correct an entry, the user executes a reversal. The system creates a linked `REVERSAL` journal entry with debit and credit amounts swapped, posts it immediately, links it to the original, and marks the original as `REVERSED` with a mandatory reason.
- **Append-Only Ledger**: All ledger entries, state changes, and reversals are recorded in immutable audit logs (`audit_logs` table).

### 3. Fiscal Period Management
- **Open vs Closed Periods**: Financial transactions can only be posted into `OPEN` financial periods.
- **Date Range Enclosure**: The transaction date (`entry_date`) must fall strictly within `start_date` and `end_date` of the target financial period.
- **Period Transition**: Society treasurers or admins can close a period once books are finalized, or reopen a period if audited adjustments are necessary.

### 4. Tenant Isolation & PostgreSQL RLS
All financial tables include `society_id` and are protected by PostgreSQL Row-Level Security:
- `financial_periods`
- `accounts`
- `journal_entries`
- `journal_entry_lines`
- `expenses`
- `financial_reports`
- `society_accounting_configs`

A transaction can never reference accounts or financial periods belonging to another society.

---

## Accounting Providers

The financial domain communicates with accounting engines via the `AccountingProvider` interface:

| Provider | Implementation | Description |
|---|---|---|
| **Native** | `NativeAccountingProvider` | Directly operates on the platform's PostgreSQL double-entry general ledger. |
| **Tally** | `TallyProvider` | Adapter stub for TallyPrime integration. Safely raises `TallyConfigurationException` if unconfigured. |
| **Import / Export** | `ImportExportProvider` | Supports batch CSV/JSON export and import with dry-run balance validation before posting. |

---

## Standard Chart of Accounts (COA) Structure

Each society is initialized with a standard Chart of Accounts:

| Code | Account Name | Type | Normal Balance |
|---|---|---|---|
| `1010` | Cash on Hand | ASSET | DEBIT |
| `1020` | Operating Bank Account | ASSET | DEBIT |
| `1030` | Maintenance Dues Receivable | ASSET | DEBIT |
| `2010` | Accounts Payable (Vendors) | LIABILITY | CREDIT |
| `2020` | Sinking Fund Reserve | LIABILITY | CREDIT |
| `3010` | Society Corpus Fund | EQUITY | CREDIT |
| `4010` | Resident Maintenance Fees | INCOME | CREDIT |
| `5010` | Security Services Expense | EXPENSE | DEBIT |
| `5020` | Electricity & Water Utilities | EXPENSE | DEBIT |

---

## REST API Endpoints (`/api/v1/finance`)

### Periods
- `GET /periods` — List society financial periods
- `POST /periods` — Create a new financial period
- `PUT /periods/{id}/close` — Close an open period
- `PUT /periods/{id}/reopen` — Reopen a closed period

### Chart of Accounts
- `GET /accounts` — List accounts (filter by active status or account type)
- `POST /accounts` — Create an account
- `GET /accounts/{id}` — Get account details
- `PUT /accounts/{id}/deactivate` — Deactivate an account

### Journal Entries
- `POST /journals` — Draft a balanced journal entry
- `GET /journals` — List journal entries with period, date, and status filters
- `GET /journals/{id}` — Get journal entry with lines
- `POST /journals/{id}/post` — Atomically validate and post a journal entry
- `POST /journals/{id}/reverse` — Reverse a posted journal entry with reason

### Expenses
- `POST /expenses` — Create an expense draft
- `GET /expenses` — List expenses
- `POST /expenses/{id}/approve` — Approve an expense (automatically generates and posts a balanced journal entry)

### Financial Reports (Deterministic)
- `GET /reports/trial-balance?period_id={id}` — Generate Trial Balance statement
- `GET /reports/general-ledger?account_id={id}&period_id={id}` — Account General Ledger running balance
- `GET /reports/income-expenditure?period_id={id}` — Income & Expenditure statement
- `GET /reports/balance-sheet?period_id={id}` — Balance Sheet
- `GET /reports/receipts-payments?period_id={id}` — Receipts & Payments summary

### Configuration
- `GET /config` — Get society accounting configuration
- `PUT /config` — Update accounting configuration (e.g., switch mode, configure authoritative source)
