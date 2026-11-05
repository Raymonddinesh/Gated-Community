"""Invoice Application Service: Generation, Lifecycle, Adjustments, Late Fees, and Accounting."""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.billing.domain.exceptions import (
    BillingAccountingIntegrationException,
    BillingConfigNotFoundException,
    BillingPeriodClosedException,
    BillingPeriodNotFoundException,
    InvalidAdjustmentException,
    InvalidChargeRuleException,
    InvoiceImmutableException,
    InvoiceNotFoundException,
    UndeterminedResponsiblePartyException,
)
from apps.api.src.billing.domain.models import (
    AdjustmentType,
    BillingPeriodStatus,
    ChargeCalculationType,
    InvoiceStatus,
    LateFeeType,
    NoteType,
)
from apps.api.src.billing.infrastructure.repositories import (
    BillingConfigRepository,
    BillingPeriodRepository,
    ChargeRuleRepository,
    InvoiceRepository,
)
from apps.api.src.database.models.billing import (
    BillingPeriod,
    CreditDebitNote,
    Invoice,
    MaintenanceChargeRule,
)
from apps.api.src.database.models.membership import UnitOccupancy
from apps.api.src.database.models.society import Unit
from apps.api.src.database.repositories.audit_repository import AuditRepository
from apps.api.src.finance.application.journal_service import JournalService
from apps.api.src.finance.domain.models import quantize_amount


class InvoiceService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.invoice_repo = InvoiceRepository(session)
        self.period_repo = BillingPeriodRepository(session)
        self.rule_repo = ChargeRuleRepository(session)
        self.config_repo = BillingConfigRepository(session)
        self.journal_service = JournalService(session)
        self.audit_repo = AuditRepository(session)

    async def get_invoice(self, invoice_id: UUID, society_id: UUID) -> Invoice:
        invoice = await self.invoice_repo.get_by_id(invoice_id, society_id)
        if not invoice:
            raise InvoiceNotFoundException(invoice_id)
        return invoice

    async def list_invoices(
        self,
        society_id: UUID,
        billing_period_id: UUID | None = None,
        unit_id: UUID | None = None,
        responsible_user_id: UUID | None = None,
        status: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Invoice]:
        return await self.invoice_repo.list_invoices(
            society_id=society_id,
            billing_period_id=billing_period_id,
            unit_id=unit_id,
            responsible_user_id=responsible_user_id,
            status=status,
            limit=limit,
            offset=offset,
        )

    async def generate_invoices_for_period(
        self,
        society_id: UUID,
        billing_period_id: UUID,
        generated_by: UUID | None = None,
        correlation_id: str | None = None,
    ) -> list[Invoice]:
        """
        Deterministically and idempotently generate maintenance invoices for all eligible units.
        Guarantees transactional consistency, snapshotting charge rules, and double-entry safety.
        """
        period = await self.period_repo.get_by_id(billing_period_id, society_id)
        if not period:
            raise BillingPeriodNotFoundException(billing_period_id)

        if period.status in (BillingPeriodStatus.CLOSED.value, BillingPeriodStatus.CANCELLED.value):
            raise BillingPeriodClosedException(period.period_code)

        config = await self.config_repo.get_by_society_id(society_id)
        if not config:
            raise BillingConfigNotFoundException(society_id)

        # Retrieve active charge rules applicable to the period's billing date
        rules = await self.rule_repo.list_active_rules(society_id, on_date=period.billing_date)
        if not rules:
            raise InvalidChargeRuleException(
                f"No active charge rules found for billing date {period.billing_date.isoformat()}."
            )

        # Retrieve all active units for this society
        units_res = await self.session.execute(
            select(Unit)
            .where(Unit.society_id == society_id, Unit.status == "ACTIVE")
            .order_by(Unit.unit_number.asc())
        )
        units = list(units_res.scalars().all())
        if not units:
            raise InvalidChargeRuleException("No active residential units found in society.")

        created_invoices: list[Invoice] = []

        for unit in units:
            # Check idempotency constraint
            existing = await self.invoice_repo.get_by_period_and_unit(society_id, period.id, unit.id)
            if existing:
                continue

            # Determine responsible resident
            responsible_user_id = await self._resolve_responsible_user(
                society_id, unit, config.default_responsibility
            )

            # Calculate invoice lines deterministically
            lines_data: list[dict[str, Any]] = []
            subtotal = Decimal("0.0000")

            for rule in rules:
                line_amount, unit_rate = self._calculate_rule_charge(rule, unit)
                subtotal += line_amount
                lines_data.append(
                    {
                        "charge_rule_id": rule.id,
                        "charge_rule_snapshot": {
                            "code": rule.code,
                            "name": rule.name,
                            "calculation_type": rule.calculation_type,
                            "rate_or_amount": str(rule.rate_or_amount),
                        },
                        "description": f"{rule.name} ({rule.code})",
                        "quantity": Decimal("1.0000"),
                        "unit_rate": unit_rate,
                        "amount": line_amount,
                        "accounting_account_id": rule.income_account_id,
                    }
                )

            inv_number = await self.invoice_repo.generate_invoice_number(society_id)
            initial_status = "REVIEW" if config.approval_required else "GENERATED"

            inv = await self.invoice_repo.create_invoice(
                society_id=society_id,
                billing_period_id=period.id,
                unit_id=unit.id,
                responsible_user_id=responsible_user_id,
                invoice_number=inv_number,
                invoice_date=period.billing_date,
                due_date=period.due_date,
                subtotal=subtotal,
                grand_total=subtotal,
                lines_data=lines_data,
                currency=config.currency,
                status=initial_status,
                created_by=generated_by,
            )
            created_invoices.append(inv)

        period.generated_at = datetime.now(UTC)
        period.status = "REVIEW" if config.approval_required else "GENERATED"
        await self.session.flush()

        await self.audit_repo.log_event(
            action="BILLING_INVOICES_GENERATED",
            entity_type="billing_period",
            entity_id=str(period.id),
            society_id=society_id,
            actor_user_id=generated_by,
            correlation_id=correlation_id,
            after_state={
                "period_code": period.period_code,
                "invoices_generated": len(created_invoices),
                "status": period.status,
            },
        )
        return created_invoices

    async def approve_period(
        self,
        society_id: UUID,
        billing_period_id: UUID,
        approved_by: UUID | None = None,
        correlation_id: str | None = None,
    ) -> BillingPeriod:
        period = await self.period_repo.get_by_id(billing_period_id, society_id)
        if not period:
            raise BillingPeriodNotFoundException(billing_period_id)

        period.status = BillingPeriodStatus.APPROVED.value
        period.approved_at = datetime.now(UTC)
        period.approved_by = approved_by

        # Update invoices in period to APPROVED
        invoices = await self.invoice_repo.list_invoices(society_id, billing_period_id=period.id)
        for inv in invoices:
            if inv.status in (
                InvoiceStatus.DRAFT.value,
                InvoiceStatus.REVIEW.value,
                InvoiceStatus.GENERATED.value,
            ):
                inv.status = InvoiceStatus.APPROVED.value
                inv.approved_at = datetime.now(UTC)
                inv.approved_by = approved_by

        await self.session.flush()

        await self.audit_repo.log_event(
            action="BILLING_PERIOD_APPROVED",
            entity_type="billing_period",
            entity_id=str(period.id),
            society_id=society_id,
            actor_user_id=approved_by,
            correlation_id=correlation_id,
            after_state={"status": period.status},
        )
        return period

    async def publish_period(
        self,
        society_id: UUID,
        billing_period_id: UUID,
        published_by: UUID | None = None,
        correlation_id: str | None = None,
    ) -> BillingPeriod:
        """
        Publish invoices and integrate with Phase 4 Double-Entry General Ledger.
        Posts balanced journals atomically:
          Debit: Resident Receivable Account
          Credit: Maintenance Income Account
        """
        period = await self.period_repo.get_by_id(billing_period_id, society_id)
        if not period:
            raise BillingPeriodNotFoundException(billing_period_id)

        if period.status in (BillingPeriodStatus.CLOSED.value, BillingPeriodStatus.CANCELLED.value):
            raise BillingPeriodClosedException(period.period_code)

        config = await self.config_repo.get_by_society_id(society_id)
        if not config:
            raise BillingConfigNotFoundException(society_id)

        # Enforce approval workflow if required by society configuration
        if config.approval_required and period.status not in (
            BillingPeriodStatus.APPROVED.value,
            BillingPeriodStatus.PUBLISHED.value,
        ):
            from apps.api.src.core.exceptions import AppException

            raise AppException(
                code="BILLING_PERIOD_NOT_APPROVED",
                message=f"Billing period '{period.period_code}' requires approval before publication (current status: {period.status}).",
                status_code=400,
            )

        invoices = await self.invoice_repo.list_invoices(society_id, billing_period_id=period.id)

        for inv in invoices:
            if inv.status == InvoiceStatus.PUBLISHED.value:
                continue

            inv.status = InvoiceStatus.PUBLISHED.value
            inv.published_at = datetime.now(UTC)
            inv.published_by = published_by

            # Create and post accounting journal entry
            journal_lines = [
                {
                    "account_id": config.receivable_account_id,
                    "debit_amount": inv.grand_total,
                    "credit_amount": Decimal("0.0000"),
                    "description": f"Dues receivable for invoice {inv.invoice_number}",
                }
            ]
            for line in inv.lines:
                journal_lines.append(
                    {
                        "account_id": line.accounting_account_id,
                        "debit_amount": Decimal("0.0000"),
                        "credit_amount": line.amount,
                        "description": line.description,
                    }
                )

            try:
                journal = await self.journal_service.create_draft_journal(
                    society_id=society_id,
                    financial_period_id=period.financial_period_id,
                    entry_date=period.billing_date,
                    description=f"Maintenance billing for Invoice {inv.invoice_number} - Period {period.period_code}",
                    lines_data=journal_lines,
                    source_type="BILLING",
                    source_record_id=str(inv.id),
                    reference_number=inv.invoice_number,
                    currency=inv.currency,
                    created_by=published_by,
                    correlation_id=correlation_id,
                )
                posted_journal = await self.journal_service.post_journal(
                    journal_id=journal.id,
                    society_id=society_id,
                    posted_by=published_by,
                    correlation_id=correlation_id,
                )
                inv.journal_entry_id = posted_journal.id
                inv.accounting_status = "POSTED"
                inv.accounting_error = None
            except Exception as exc:
                inv.accounting_status = "FAILED"
                inv.accounting_error = str(exc)
                raise BillingAccountingIntegrationException(
                    f"Accounting journal posting failed for invoice '{inv.invoice_number}': {exc}"
                ) from exc

        period.status = BillingPeriodStatus.PUBLISHED.value
        period.published_at = datetime.now(UTC)
        period.published_by = published_by
        await self.session.flush()

        await self.audit_repo.log_event(
            action="BILLING_PERIOD_PUBLISHED",
            entity_type="billing_period",
            entity_id=str(period.id),
            society_id=society_id,
            actor_user_id=published_by,
            correlation_id=correlation_id,
            after_state={"status": period.status},
        )
        return period

    async def apply_adjustment(
        self,
        society_id: UUID,
        invoice_id: UUID,
        adjustment_type: str,
        amount: Decimal,
        reason: str,
        created_by: UUID | None = None,
        correlation_id: str | None = None,
    ) -> Invoice:
        invoice = await self.get_invoice(invoice_id, society_id)
        if invoice.status in (InvoiceStatus.CANCELLED.value, InvoiceStatus.PAID.value):
            raise InvoiceImmutableException(invoice.invoice_number, invoice.status)

        qty_amount = quantize_amount(amount)
        if qty_amount <= Decimal("0.0000"):
            raise InvalidAdjustmentException("Adjustment amount must be strictly greater than zero.")

        if adjustment_type not in (
            AdjustmentType.DISCOUNT.value,
            AdjustmentType.WAIVER.value,
            AdjustmentType.SURCHARGE.value,
            AdjustmentType.CORRECTION.value,
        ):
            raise InvalidAdjustmentException(f"Invalid adjustment type '{adjustment_type}'.")

        await self.invoice_repo.add_adjustment(
            society_id=society_id,
            invoice_id=invoice.id,
            adjustment_type=adjustment_type,
            amount=qty_amount,
            reason=reason,
            created_by=created_by,
        )

        if adjustment_type in (AdjustmentType.DISCOUNT.value, AdjustmentType.WAIVER.value):
            invoice.adjustment_total += qty_amount
            invoice.grand_total -= qty_amount
            invoice.outstanding_amount -= qty_amount
        else:
            invoice.adjustment_total -= qty_amount
            invoice.grand_total += qty_amount
            invoice.outstanding_amount += qty_amount

        if invoice.outstanding_amount <= Decimal("0.0000"):
            invoice.outstanding_amount = Decimal("0.0000")
            invoice.status = InvoiceStatus.PAID.value

        await self.session.flush()

        await self.audit_repo.log_event(
            action="BILLING_ADJUSTMENT_APPLIED",
            entity_type="invoice",
            entity_id=str(invoice.id),
            society_id=society_id,
            actor_user_id=created_by,
            correlation_id=correlation_id,
            after_state={
                "adjustment_type": adjustment_type,
                "amount": str(qty_amount),
                "grand_total": str(invoice.grand_total),
                "outstanding_amount": str(invoice.outstanding_amount),
            },
        )
        return invoice

    async def issue_credit_debit_note(
        self,
        society_id: UUID,
        invoice_id: UUID,
        note_type: str,
        amount: Decimal,
        reason: str,
        created_by: UUID | None = None,
        correlation_id: str | None = None,
    ) -> CreditDebitNote:
        invoice = await self.get_invoice(invoice_id, society_id)
        config = await self.config_repo.get_by_society_id(society_id)
        if not config:
            raise BillingConfigNotFoundException(society_id)

        if invoice.status in (InvoiceStatus.CANCELLED.value, InvoiceStatus.DRAFT.value):
            raise InvoiceImmutableException(invoice.invoice_number, invoice.status)

        qty_amount = quantize_amount(amount)
        if qty_amount <= Decimal("0.0000"):
            raise InvalidAdjustmentException("Note amount must be strictly greater than zero.")

        if note_type == NoteType.CREDIT_NOTE.value and qty_amount > invoice.outstanding_amount:
            raise InvalidAdjustmentException(
                f"Credit note amount ({qty_amount}) cannot exceed invoice outstanding balance ({invoice.outstanding_amount})."
            )

        note_number = await self.invoice_repo.generate_note_number(society_id, note_type)

        # Create balanced journal entry via Phase 4 accounting
        period = await self.period_repo.get_by_id(invoice.billing_period_id, society_id)
        if not period:
            raise BillingPeriodNotFoundException(invoice.billing_period_id)

        if note_type == NoteType.CREDIT_NOTE.value:
            # Credit Note reduces receivable
            journal_lines = [
                {
                    "account_id": config.income_account_id,
                    "debit_amount": qty_amount,
                    "credit_amount": Decimal("0.0000"),
                    "description": f"Credit note {note_number} on invoice {invoice.invoice_number}",
                },
                {
                    "account_id": config.receivable_account_id,
                    "debit_amount": Decimal("0.0000"),
                    "credit_amount": qty_amount,
                    "description": f"Receivable reduction from credit note {note_number}",
                },
            ]
            invoice.outstanding_amount -= qty_amount
            if invoice.outstanding_amount <= Decimal("0.0000"):
                invoice.outstanding_amount = Decimal("0.0000")
                invoice.status = InvoiceStatus.PAID.value
        else:
            # Debit Note increases receivable
            journal_lines = [
                {
                    "account_id": config.receivable_account_id,
                    "debit_amount": qty_amount,
                    "credit_amount": Decimal("0.0000"),
                    "description": f"Debit note {note_number} on invoice {invoice.invoice_number}",
                },
                {
                    "account_id": config.income_account_id,
                    "debit_amount": Decimal("0.0000"),
                    "credit_amount": qty_amount,
                    "description": f"Income addition from debit note {note_number}",
                },
            ]
            invoice.grand_total += qty_amount
            invoice.outstanding_amount += qty_amount

        journal = await self.journal_service.create_draft_journal(
            society_id=society_id,
            financial_period_id=period.financial_period_id,
            entry_date=date.today(),
            description=f"{note_type} {note_number} for {invoice.invoice_number}: {reason}",
            lines_data=journal_lines,
            source_type="BILLING",
            source_record_id=str(invoice.id),
            reference_number=note_number,
            currency=invoice.currency,
            created_by=created_by,
            correlation_id=correlation_id,
        )
        posted_journal = await self.journal_service.post_journal(
            journal_id=journal.id,
            society_id=society_id,
            posted_by=created_by,
            correlation_id=correlation_id,
        )

        note = await self.invoice_repo.add_credit_debit_note(
            society_id=society_id,
            invoice_id=invoice.id,
            note_type=note_type,
            note_number=note_number,
            amount=qty_amount,
            reason=reason,
            journal_entry_id=posted_journal.id,
            created_by=created_by,
        )
        await self.session.flush()

        await self.audit_repo.log_event(
            action="BILLING_NOTE_ISSUED",
            entity_type="credit_debit_note",
            entity_id=str(note.id),
            society_id=society_id,
            actor_user_id=created_by,
            correlation_id=correlation_id,
            after_state={
                "note_number": note.note_number,
                "note_type": note.note_type,
                "amount": str(note.amount),
            },
        )
        return note

    async def apply_late_fees(
        self,
        society_id: UUID,
        invoice_id: UUID,
        as_of_date: date,
        applied_by: UUID | None = None,
        correlation_id: str | None = None,
    ) -> Decimal:
        """
        Deterministically apply late fees based on society configuration.
        Prevents double application and respects grace periods.
        """
        invoice = await self.get_invoice(invoice_id, society_id)
        if invoice.status in (InvoiceStatus.PAID.value, InvoiceStatus.CANCELLED.value):
            return Decimal("0.0000")

        if invoice.late_fee_total > Decimal("0.0000"):
            # Already charged late fee
            return Decimal("0.0000")

        config = await self.config_repo.get_by_society_id(society_id)
        if not config or not config.late_fee_enabled:
            return Decimal("0.0000")

        overdue_threshold = invoice.due_date + timedelta(days=config.grace_period_days)
        if as_of_date <= overdue_threshold:
            return Decimal("0.0000")

        days_overdue = (as_of_date - invoice.due_date).days
        late_fee = Decimal("0.0000")

        if config.late_fee_type == LateFeeType.FIXED_AMOUNT.value:
            late_fee = config.late_fee_rate
        elif config.late_fee_type == LateFeeType.PERCENTAGE.value:
            late_fee = quantize_amount(
                invoice.outstanding_amount * (config.late_fee_rate / Decimal("100.0000"))
            )
        elif config.late_fee_type == LateFeeType.PER_DAY_PERCENTAGE.value:
            daily_factor = config.late_fee_rate / Decimal("100.0000")
            late_fee = quantize_amount(invoice.outstanding_amount * daily_factor * Decimal(days_overdue))

        if config.max_late_fee and late_fee > config.max_late_fee:
            late_fee = config.max_late_fee

        late_fee = quantize_amount(late_fee)
        if late_fee <= Decimal("0.0000"):
            return Decimal("0.0000")

        invoice.late_fee_total += late_fee
        invoice.grand_total += late_fee
        invoice.outstanding_amount += late_fee
        invoice.status = InvoiceStatus.OVERDUE.value
        await self.session.flush()

        await self.audit_repo.log_event(
            action="BILLING_LATE_FEE_APPLIED",
            entity_type="invoice",
            entity_id=str(invoice.id),
            society_id=society_id,
            actor_user_id=applied_by,
            correlation_id=correlation_id,
            after_state={
                "late_fee": str(late_fee),
                "days_overdue": days_overdue,
                "outstanding_amount": str(invoice.outstanding_amount),
            },
        )
        return late_fee

    async def _resolve_responsible_user(
        self, society_id: UUID, unit: Unit, default_responsibility: str
    ) -> UUID:
        occupancies_res = await self.session.execute(
            select(UnitOccupancy).where(
                UnitOccupancy.unit_id == unit.id,
                UnitOccupancy.society_id == society_id,
                UnitOccupancy.status == "ACTIVE",
            )
        )
        occupancies = list(occupancies_res.scalars().all())
        if not occupancies:
            raise UndeterminedResponsiblePartyException(
                unit.id, f"Unit '{unit.unit_number}' has no active occupancies."
            )

        # Try matching preferred responsibility
        for occ in occupancies:
            if default_responsibility == "TENANT" and occ.relationship_type == "TENANT":
                return occ.user_id
            if default_responsibility == "OWNER" and occ.relationship_type == "OWNER":
                return occ.user_id

        # Fallback to primary contact
        for occ in occupancies:
            if occ.is_primary_contact:
                return occ.user_id

        # Fallback to owner if tenant was requested but no tenant present
        for occ in occupancies:
            if occ.relationship_type == "OWNER":
                return occ.user_id

        # Fallback to any active occupant
        return occupancies[0].user_id

    def _calculate_rule_charge(self, rule: MaintenanceChargeRule, unit: Unit) -> tuple[Decimal, Decimal]:
        """Returns (line_amount, unit_rate)."""
        calc_type = rule.calculation_type

        if calc_type == ChargeCalculationType.FIXED_PER_UNIT.value:
            return rule.rate_or_amount, rule.rate_or_amount

        elif calc_type == ChargeCalculationType.PER_SQFT.value:
            if unit.carpet_area_sqft is None:
                raise InvalidChargeRuleException(
                    f"Unit '{unit.unit_number}' is missing carpet_area_sqft required for PER_SQFT charge rule '{rule.code}'."
                )
            if unit.carpet_area_sqft <= 0:
                raise InvalidChargeRuleException(
                    f"Unit '{unit.unit_number}' has non-positive carpet_area_sqft ({unit.carpet_area_sqft}) for PER_SQFT charge rule '{rule.code}'."
                )
            sqft = Decimal(str(unit.carpet_area_sqft))
            amount = quantize_amount(sqft * rule.rate_or_amount)
            return amount, rule.rate_or_amount

        elif calc_type == ChargeCalculationType.UNIT_TYPE.value:
            rate = rule.rate_or_amount
            if rule.unit_type_rates and unit.unit_type in rule.unit_type_rates:
                rate = Decimal(str(rule.unit_type_rates[unit.unit_type]))
            return quantize_amount(rate), quantize_amount(rate)

        return rule.rate_or_amount, rule.rate_or_amount
