# ADR 010: Financial Core and Accounting Provider Abstraction

## Status
Accepted (with Open Integration Decision on Tally Transport Mechanism)

## Context
Housing societies and residential communities in India and globally employ divergent accounting workflows:
1. **Self-Contained Societies**: Rely entirely on native platform capabilities for invoicing, collection, expense logging, and balance sheet generation.
2. **Tally-Centric Societies**: Employ chartered accountants or external management agencies whose standard operating procedure mandates Tally (Tally ERP 9 / TallyPrime) as the primary statutory book of accounts.
3. **Hybrid Societies**: Utilize the SaaS platform for resident billing, automated collections, and maintenance tickets, while periodically synchronizing journal vouchers, payments, and vendor expenses with an external accounting system.
4. **File-Based Import/Export Societies**: Exchange accounting records periodically via standardized Excel or CSV formats for manual ingestion by external auditors.

A hard dependency between SocietySphere's financial core and Tally would violate architectural modularity, create vendor lock-in, and compromise system resilience if external sync APIs fail. Furthermore, financial reports and totals must never be computed non-deterministically (e.g., by AI or heuristic models), and resident visibility into society financials must be strictly governed by configurable transparency policies.

## Decision
1. **Strict Domain Decoupling**:
   The financial domain is split into eight discrete, decoupled conceptual subdomains:
   - **Billing**: Invoicing rules, rate cards, recurring dues generation, utility bill apportionment, debit notes.
   - **Payments**: Payment gateway webhooks, offline receipt capture, payment allocations, credit notes.
   - **Accounting**: Chart of accounts, general ledger, double-entry journal vouchers, closing balances.
   - **Expenses**: Vendor purchase orders, work order bills, expense categorization, petty cash disbursements.
   - **Reconciliation**: Bank statement matching, payment gateway settlement reconciliation, dispute resolution.
   - **Reporting**: Financial statement generation, variance tracking, audit schedules.
   - **Financial Periods**: Fiscal year management, period locking, year-end closing routines.
   - **Audit & History**: Append-only change tracking, versioned statement snapshots, operational diffs.

2. **Accounting Provider Strategy & Interface Abstraction**:
   The core financial engine communicates exclusively through a polymorphic `AccountingProvider` interface:
   ```typescript
   export interface AccountingProvider {
     readonly providerType: AccountingMode;
     
     // Master & Chart of Accounts
     syncChartOfAccounts(societyId: string, accounts: ChartOfAccountDto[]): Promise<SyncResult>;
     
     // Transaction Posting
     postJournalEntry(societyId: string, entry: JournalEntryDto): Promise<PostingResult>;
     postPaymentVoucher(societyId: string, voucher: PaymentVoucherDto): Promise<PostingResult>;
     postReceiptVoucher(societyId: string, voucher: ReceiptVoucherDto): Promise<PostingResult>;
     
     // Reconciliation & Status
     verifySyncStatus(societyId: string, batchId: string): Promise<BatchStatusDto>;
     reconcileBalances(societyId: string, periodId: string): Promise<ReconciliationReportDto>;
   }
   ```
   Concrete implementations:
   - `NativeAccountingProvider`: Direct execution against the platform's PostgreSQL double-entry general ledger.
   - `TallyProvider`: Adapter mapping domain journal entries into Tally-compatible vouchers, tracking synchronization state via a dedicated sync pipeline.
   - `ImportExportProvider`: Generates and ingests standardized CSV/Excel templates (e.g., Tally XML/Excel templates, standard society audit formats).
   - `FutureProviders`: Allows plug-and-play integration with Zoho Books, QuickBooks, SAP, or ERPNext without touching the financial domain.

3. **Supported Accounting Modes per Society**:
   - `NATIVE`: Platform general ledger is the single source of truth for all accounting.
   - `TALLY_INTEGRATED`: Platform handles billing and payments; accounting vouchers are synchronized bidirectionally/unidirectionally with Tally.
   - `HYBRID`: Platform maintains operational ledger; summary or periodic journal entries are synchronized with external accounting.
   - `IMPORT_EXPORT`: Offline manual data sync via structured CSV/Excel templates with validation and staging gates.

4. **Tally Synchronization Metadata & Pipeline**:
   All sync interactions record comprehensive traceability attributes:
   - `source_system`: Originating system (e.g., `SOCIETYSPHERE` or `TALLY`).
   - `source_record_id`: Originating primary key.
   - `sync_batch_id`: UUID grouping the synchronization run.
   - `idempotency_key`: Hash of payload and sequence to prevent duplicate voucher creation in Tally.
   - `validation_status`: Pre-sync schema and ledger head mapping verification (`VALID`, `MAPPING_ERROR`, `SCHEMA_INVALID`).
   - `sync_status`: `PENDING` | `IN_PROGRESS` | `SUCCESS` | `FAILED` | `RECONCILED`.
   - `error_tracking`: Detailed error stack and rejected record payload.
   - `audit_trail`: Immutable log of timestamps, sync payloads, and reconciliation state.

5. **Deterministic Calculations & AI Guardrails**:
   - Financial totals, ledgers, tax computations, and statements must be computed **strictly using deterministic domain algorithms** in backend services.
   - AI assistants (LLMs) are **strictly prohibited** from calculating, tallying, or modifying financial numbers.
   - AI may only consume verified, structured report outputs produced by the deterministic engine to explain terms, summarize trends, or draft human-readable executive summaries for committee members.
   - AI queries must execute through authenticated, authorized domain services subject to RBAC and tenant scoping; zero direct database or raw financial table access.

6. **Financial Reports Lifecycle & Governance**:
   - Standard 5-stage lifecycle for formal financial statements:
     $$\text{DRAFT} \longrightarrow \text{GENERATED} \longrightarrow \text{REVIEW} \longrightarrow \text{APPROVED} \longrightarrow \text{PUBLISHED}$$
   - Snapshots of published reports are stored as immutable, versioned documents (with hash verification).
   - Mandatory core financial report catalog:
     1. Income & Expenditure Statement
     2. Balance Sheet
     3. Receipts & Payments Statement
     4. Outstanding Maintenance / Defaulters List
     5. Expense Summary
     6. Vendor Payments Ledger
     7. Bank Summary & Reconciliation
     8. Budget vs Actual Variance Report
     9. Complete Financial Report (Consolidated Annual Audit Pack)

7. **Resident Financial Transparency Policy**:
   - Configurable per society by Society Admin / General Body:
     - *Level 1 (Strict/Private)*: Residents view only their own unit ledger; aggregate society balance sheets visible only when published.
     - *Level 2 (Semi-Transparent)*: Residents view their own unit ledger + published society summary reports. Defaulters list displayed with anonymized unit numbers or amounts.
     - *Level 3 (Open Society)*: Full transparency of approved society income/expenditure and defaulter lists as mandated by applicable cooperative housing society bye-laws.

## Open Integration Decision
- **Tally Transport Mechanism**: Tally ERP 9 and TallyPrime support multiple integration topologies:
  1. Local Windows Agent listening to Tally XML over HTTP (port 9000).
  2. Tally ODBC driver.
  3. Cloud-hosted Tally Virtual Office / Tally on Cloud REST API gateway.
  4. Scheduled XML file export/import via hot folder.
  *Decision*: The specific transport adapter mechanism is left as an **Open Integration Decision** to be evaluated and selected based on client deployment infrastructure before the implementation phase of the `TallyProvider` begins. The `AccountingProvider` interface insulates the entire application from this future technical selection.

## Consequences
### Positive
- Zero coupling between society billing/operations and external accounting software.
- Seamless compatibility with India's extensive Tally ecosystem without compromising cloud-native multi-tenancy.
- Guaranteed financial auditability and zero risk of AI hallucination in financial reports.
- Comprehensive governance lifecycle prevents premature or unverified financial statement publication.

### Negative / Trade-offs
- Synchronization state management and ledger head mapping introduce operational monitoring overhead for hybrid/Tally societies.
- Requires building a staging and reconciliation engine for imported spreadsheets and external vouchers.
