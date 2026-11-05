# ADR 013: Financial Core, Double-Entry Engine & Accounting Provider Implementation

## Status
Accepted

## Context
Housing society management requires bulletproof financial accuracy, auditability, and regulatory compliance. Historical financial software in residential communities frequently suffers from:
1. Floating-point rounding errors and non-deterministic ledger calculations.
2. In-place modification or physical deletion of posted accounting vouchers.
3. Postings made retrospectively into closed fiscal periods.
4. Cross-tenant leakage of sensitive account books and vendor disbursements.
5. Tight coupling to specific third-party accounting suites (like Tally) that locks the system into external proprietary protocols.

In Phase 4 of SocietySphere, we implement the complete Financial Core Foundation to guarantee mathematical integrity, audit immutability, and clean provider extensibility.

## Decision

### 1. Fundamental Financial Invariants
- **Strict Double-Entry Invariant**: Every journal entry must have at least two lines, where each line is strictly either a debit or a credit (`(debit > 0 AND credit == 0) OR (credit > 0 AND debit == 0)`). Before posting, `TOTAL DEBITS` must equal `TOTAL CREDITS` exactly (`sum(debits) - sum(credits) == 0`).
- **Exact Decimal Arithmetic**: Floating-point types (`float`) are completely prohibited in the financial domain. All amounts are stored in PostgreSQL as `NUMERIC(18, 4)` and manipulated in Python exclusively via `Decimal`, quantized to 4 decimal places with `ROUND_HALF_UP`.
- **Audit Immutability**: Once a journal entry is `POSTED`, it can never be modified or deleted. Any correction requires creating a balanced mirror reversal entry (`REVERSAL`), swapping all debit and credit amounts, linking back to the original entry, and marking the original entry as `REVERSED` with a mandatory reason.
- **Financial Period Posting Guard**: Postings are strictly prohibited unless the journal's entry date falls within an `OPEN` financial period belonging to the tenant. Closed periods reject any new postings or modifications.
- **Deterministic Reporting**: Zero AI models are used for financial figures or report generation. Trial Balance, General Ledger, Balance Sheet, Income & Expenditure, and Receipts & Payments statements are generated entirely via deterministic SQL aggregations and Python double-entry mathematics.

### 2. Multi-Tenancy & Row-Level Security
All financial entities inherit `TenantScopedMixin` and include `society_id`:
- `financial_periods`
- `accounts`
- `journal_entries`
- `journal_entry_lines`
- `expenses`
- `financial_reports`
- `society_accounting_configs`

Every table is protected by PostgreSQL Row-Level Security (`ENABLE ROW LEVEL SECURITY` and `FORCE ROW LEVEL SECURITY`) with `tenant_isolation_policy` enforcing `society_id = NULLIF(current_setting('app.current_society_id', true), '')::uuid`. In addition, repository and service layers enforce tenant matching to prevent IDOR attacks.

### 3. Provider Abstraction Architecture
The platform isolates the financial core from external accounting software using the `AccountingProvider` interface:
```python
class AccountingProvider(ABC):
    @abstractmethod
    async def post_journal_entry(self, society_id: UUID, entry: JournalEntryDTO) -> ProviderResult: ...
    @abstractmethod
    async def sync_chart_of_accounts(
        self, society_id: UUID, accounts: list[AccountDTO]
    ) -> ProviderResult: ...
    @abstractmethod
    async def get_sync_status(self, society_id: UUID) -> dict[str, Any]: ...
```

Concrete implementations:
1. `NativeAccountingProvider`: Direct operation against SocietySphere's PostgreSQL double-entry general ledger.
2. `TallyProvider`: Adapter stub prepared for TallyPrime XML/ODBC sync. In Phase 4, unconfigured societies cleanly raise `TallyConfigurationException("TALLY_NOT_CONFIGURED")` with structured sync metadata.
3. `ImportExportProvider`: Batch data exchange supporting CSV parsing, column validation, double-entry balance verification, and dry-run execution before atomic commitment.
4. `get_accounting_provider`: Factory function resolving provider instances dynamically based on the society's active `SocietyAccountingConfig`.

### 4. Role-Based Access Control (RBAC)
Financial operations are protected by granular permissions:
- `finance.period.manage`
- `finance.account.manage`
- `finance.journal.create`
- `finance.journal.post`
- `finance.journal.reverse`
- `finance.expense.create`
- `finance.expense.approve`
- `finance.reports.view`
- `finance.config.manage`

Roles `SUPER_ADMIN`, `SOCIETY_ADMIN`, and `TREASURER` have full operational access; `SECRETARY` has operational and review access; general `RESIDENT` accounts are restricted from modifying journals, accounts, or approving expenses.

## Consequences
- **Positive**: Complete audit compliance, mathematical precision, zero cross-tenant contamination, and transparent support for hybrid and Tally-integrated housing societies.
- **Guardrails**: Invoice generation, resident billing rules, and payment gateway webhooks remain strictly deferred to Phase 5.
