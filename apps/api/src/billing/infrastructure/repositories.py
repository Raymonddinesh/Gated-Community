"""Repositories for Billing Entities (Config, Rules, Periods, Invoices, Payments, Receipts)."""

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from apps.api.src.database.models.billing import (
    BillingAdjustment,
    BillingPeriod,
    CreditDebitNote,
    Invoice,
    InvoiceLine,
    MaintenanceChargeRule,
    Payment,
    PaymentAllocation,
    Receipt,
    SocietyBillingConfig,
)
from apps.api.src.database.models.reconciliation import (
    ReconciliationItem,
    ReconciliationSession,
)
from apps.api.src.finance.domain.models import quantize_amount


class BillingConfigRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_society_id(self, society_id: UUID) -> SocietyBillingConfig | None:
        res = await self.session.execute(
            select(SocietyBillingConfig).where(SocietyBillingConfig.society_id == society_id)
        )
        return res.scalar_one_or_none()

    async def create_or_update(
        self,
        society_id: UUID,
        receivable_account_id: UUID,
        income_account_id: UUID,
        currency: str = "INR",
        billing_frequency: str = "MONTHLY",
        billing_day: int = 1,
        default_due_days: int = 15,
        late_fee_enabled: bool = False,
        late_fee_type: str = "PERCENTAGE",
        late_fee_rate: Decimal = Decimal("0.0000"),
        grace_period_days: int = 0,
        max_late_fee: Decimal | None = None,
        interest_enabled: bool = False,
        auto_generate_enabled: bool = False,
        approval_required: bool = True,
        default_responsibility: str = "OWNER",
        bank_account_id: UUID | None = None,
        late_fee_income_account_id: UUID | None = None,
        actor_id: UUID | None = None,
    ) -> SocietyBillingConfig:
        config = await self.get_by_society_id(society_id)
        if config:
            config.receivable_account_id = receivable_account_id
            config.income_account_id = income_account_id
            config.currency = currency
            config.billing_frequency = billing_frequency
            config.billing_day = billing_day
            config.default_due_days = default_due_days
            config.late_fee_enabled = late_fee_enabled
            config.late_fee_type = late_fee_type
            config.late_fee_rate = quantize_amount(late_fee_rate)
            config.grace_period_days = grace_period_days
            config.max_late_fee = quantize_amount(max_late_fee) if max_late_fee is not None else None
            config.interest_enabled = interest_enabled
            config.auto_generate_enabled = auto_generate_enabled
            config.approval_required = approval_required
            config.default_responsibility = default_responsibility
            config.bank_account_id = bank_account_id
            config.late_fee_income_account_id = late_fee_income_account_id
            config.updated_by = actor_id
        else:
            config = SocietyBillingConfig(
                id=uuid.uuid4(),
                society_id=society_id,
                receivable_account_id=receivable_account_id,
                income_account_id=income_account_id,
                currency=currency,
                billing_frequency=billing_frequency,
                billing_day=billing_day,
                default_due_days=default_due_days,
                late_fee_enabled=late_fee_enabled,
                late_fee_type=late_fee_type,
                late_fee_rate=quantize_amount(late_fee_rate),
                grace_period_days=grace_period_days,
                max_late_fee=quantize_amount(max_late_fee) if max_late_fee is not None else None,
                interest_enabled=interest_enabled,
                auto_generate_enabled=auto_generate_enabled,
                approval_required=approval_required,
                default_responsibility=default_responsibility,
                bank_account_id=bank_account_id,
                late_fee_income_account_id=late_fee_income_account_id,
                created_by=actor_id,
                updated_by=actor_id,
            )
            self.session.add(config)
        await self.session.flush()
        return config


class ChargeRuleRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_active_rules(
        self, society_id: UUID, on_date: date | None = None
    ) -> list[MaintenanceChargeRule]:
        query = select(MaintenanceChargeRule).where(
            MaintenanceChargeRule.society_id == society_id,
            MaintenanceChargeRule.is_active == True,  # noqa: E712
        )
        if on_date:
            query = query.where(
                MaintenanceChargeRule.effective_from <= on_date,
                (MaintenanceChargeRule.effective_to.is_(None))
                | (MaintenanceChargeRule.effective_to >= on_date),
            )
        res = await self.session.execute(query.order_by(MaintenanceChargeRule.code.asc()))
        return list(res.scalars().all())

    async def get_by_id(self, rule_id: UUID, society_id: UUID) -> MaintenanceChargeRule | None:
        res = await self.session.execute(
            select(MaintenanceChargeRule).where(
                MaintenanceChargeRule.id == rule_id,
                MaintenanceChargeRule.society_id == society_id,
            )
        )
        return res.scalar_one_or_none()

    async def get_by_code(self, code: str, society_id: UUID) -> MaintenanceChargeRule | None:
        res = await self.session.execute(
            select(MaintenanceChargeRule).where(
                MaintenanceChargeRule.code == code,
                MaintenanceChargeRule.society_id == society_id,
            )
        )
        return res.scalar_one_or_none()

    async def create_rule(
        self,
        society_id: UUID,
        name: str,
        code: str,
        calculation_type: str,
        rate_or_amount: Decimal,
        income_account_id: UUID,
        effective_from: date,
        effective_to: date | None = None,
        unit_type_rates: dict[str, Any] | None = None,
        description: str | None = None,
        created_by: UUID | None = None,
    ) -> MaintenanceChargeRule:
        rule = MaintenanceChargeRule(
            id=uuid.uuid4(),
            society_id=society_id,
            name=name,
            code=code,
            calculation_type=calculation_type,
            rate_or_amount=quantize_amount(rate_or_amount),
            income_account_id=income_account_id,
            effective_from=effective_from,
            effective_to=effective_to,
            unit_type_rates=unit_type_rates,
            description=description,
            is_active=True,
            created_by=created_by,
        )
        self.session.add(rule)
        await self.session.flush()
        return rule


class BillingPeriodRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, period_id: UUID, society_id: UUID) -> BillingPeriod | None:
        res = await self.session.execute(
            select(BillingPeriod).where(
                BillingPeriod.id == period_id,
                BillingPeriod.society_id == society_id,
            )
        )
        return res.scalar_one_or_none()

    async def get_by_code(self, period_code: str, society_id: UUID) -> BillingPeriod | None:
        res = await self.session.execute(
            select(BillingPeriod).where(
                BillingPeriod.period_code == period_code,
                BillingPeriod.society_id == society_id,
            )
        )
        return res.scalar_one_or_none()

    async def list_periods(
        self, society_id: UUID, status: str | None = None, limit: int = 50, offset: int = 0
    ) -> list[BillingPeriod]:
        query = select(BillingPeriod).where(BillingPeriod.society_id == society_id)
        if status:
            query = query.where(BillingPeriod.status == status)
        query = query.order_by(BillingPeriod.start_date.desc()).limit(limit).offset(offset)
        res = await self.session.execute(query)
        return list(res.scalars().all())

    async def create_period(
        self,
        society_id: UUID,
        financial_period_id: UUID,
        period_code: str,
        name: str,
        start_date: date,
        end_date: date,
        billing_date: date,
        due_date: date,
        created_by: UUID | None = None,
    ) -> BillingPeriod:
        period = BillingPeriod(
            id=uuid.uuid4(),
            society_id=society_id,
            financial_period_id=financial_period_id,
            period_code=period_code,
            name=name,
            start_date=start_date,
            end_date=end_date,
            billing_date=billing_date,
            due_date=due_date,
            status="DRAFT",
            created_by=created_by,
        )
        self.session.add(period)
        await self.session.flush()
        return period


class InvoiceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def generate_invoice_number(self, society_id: UUID, prefix: str = "INV") -> str:
        count_res = await self.session.execute(
            select(func.count(Invoice.id)).where(Invoice.society_id == society_id)
        )
        next_seq = (count_res.scalar() or 0) + 1
        return f"{prefix}-{next_seq:06d}"

    async def generate_note_number(self, society_id: UUID, note_type: str = "CREDIT_NOTE") -> str:
        prefix = "CN" if note_type == "CREDIT_NOTE" else "DN"
        count_res = await self.session.execute(
            select(func.count(CreditDebitNote.id)).where(
                CreditDebitNote.society_id == society_id, CreditDebitNote.note_type == note_type
            )
        )
        next_seq = (count_res.scalar() or 0) + 1
        return f"{prefix}-{next_seq:06d}"

    async def get_by_id(self, invoice_id: UUID, society_id: UUID) -> Invoice | None:
        res = await self.session.execute(
            select(Invoice)
            .options(
                selectinload(Invoice.lines),
                selectinload(Invoice.adjustments),
                selectinload(Invoice.allocations),
                selectinload(Invoice.unit),
                selectinload(Invoice.billing_period),
            )
            .where(Invoice.id == invoice_id, Invoice.society_id == society_id)
        )
        return res.scalar_one_or_none()

    async def get_by_number(self, invoice_number: str, society_id: UUID) -> Invoice | None:
        res = await self.session.execute(
            select(Invoice)
            .options(
                selectinload(Invoice.lines),
                selectinload(Invoice.adjustments),
                selectinload(Invoice.allocations),
                selectinload(Invoice.unit),
                selectinload(Invoice.billing_period),
            )
            .where(Invoice.invoice_number == invoice_number, Invoice.society_id == society_id)
        )
        return res.scalar_one_or_none()

    async def get_by_period_and_unit(
        self, society_id: UUID, billing_period_id: UUID, unit_id: UUID
    ) -> Invoice | None:
        res = await self.session.execute(
            select(Invoice).where(
                Invoice.society_id == society_id,
                Invoice.billing_period_id == billing_period_id,
                Invoice.unit_id == unit_id,
            )
        )
        return res.scalar_one_or_none()

    async def create_invoice(
        self,
        society_id: UUID,
        billing_period_id: UUID,
        unit_id: UUID,
        responsible_user_id: UUID,
        invoice_number: str,
        invoice_date: date,
        due_date: date,
        subtotal: Decimal,
        grand_total: Decimal,
        lines_data: list[dict[str, Any]],
        currency: str = "INR",
        status: str = "DRAFT",
        created_by: UUID | None = None,
    ) -> Invoice:
        invoice = Invoice(
            id=uuid.uuid4(),
            society_id=society_id,
            billing_period_id=billing_period_id,
            unit_id=unit_id,
            responsible_user_id=responsible_user_id,
            invoice_number=invoice_number,
            invoice_date=invoice_date,
            due_date=due_date,
            subtotal=quantize_amount(subtotal),
            grand_total=quantize_amount(grand_total),
            paid_amount=Decimal("0.0000"),
            outstanding_amount=quantize_amount(grand_total),
            currency=currency,
            status=status,
            created_by=created_by,
        )

        for idx, line in enumerate(lines_data, start=1):
            inv_line = InvoiceLine(
                id=uuid.uuid4(),
                society_id=society_id,
                invoice_id=invoice.id,
                charge_rule_id=line.get("charge_rule_id"),
                charge_rule_snapshot=line.get("charge_rule_snapshot"),
                line_number=idx,
                description=line["description"],
                quantity=quantize_amount(line.get("quantity", Decimal("1.0000"))),
                unit_rate=quantize_amount(line["unit_rate"]),
                amount=quantize_amount(line["amount"]),
                accounting_account_id=line["accounting_account_id"],
            )
            invoice.lines.append(inv_line)

        self.session.add(invoice)
        await self.session.flush()
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
        query = (
            select(Invoice)
            .options(selectinload(Invoice.lines), selectinload(Invoice.unit))
            .where(Invoice.society_id == society_id)
        )
        if billing_period_id:
            query = query.where(Invoice.billing_period_id == billing_period_id)
        if unit_id:
            query = query.where(Invoice.unit_id == unit_id)
        if responsible_user_id:
            query = query.where(Invoice.responsible_user_id == responsible_user_id)
        if status:
            query = query.where(Invoice.status == status)

        query = (
            query.order_by(Invoice.invoice_date.desc(), Invoice.created_at.desc()).limit(limit).offset(offset)
        )
        res = await self.session.execute(query)
        return list(res.scalars().all())

    async def add_adjustment(
        self,
        society_id: UUID,
        invoice_id: UUID,
        adjustment_type: str,
        amount: Decimal,
        reason: str,
        created_by: UUID | None = None,
    ) -> BillingAdjustment:
        adj = BillingAdjustment(
            id=uuid.uuid4(),
            society_id=society_id,
            invoice_id=invoice_id,
            adjustment_type=adjustment_type,
            amount=quantize_amount(amount),
            reason=reason,
            created_by=created_by,
            created_at=datetime.now(UTC),
        )
        self.session.add(adj)
        await self.session.flush()
        return adj

    async def add_credit_debit_note(
        self,
        society_id: UUID,
        invoice_id: UUID,
        note_type: str,
        note_number: str,
        amount: Decimal,
        reason: str,
        journal_entry_id: UUID | None = None,
        created_by: UUID | None = None,
    ) -> CreditDebitNote:
        note = CreditDebitNote(
            id=uuid.uuid4(),
            society_id=society_id,
            invoice_id=invoice_id,
            note_type=note_type,
            note_number=note_number,
            amount=quantize_amount(amount),
            reason=reason,
            journal_entry_id=journal_entry_id,
            status="APPLIED",
            created_by=created_by,
        )
        self.session.add(note)
        await self.session.flush()
        return note


class PaymentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def generate_receipt_number(self, society_id: UUID, prefix: str = "REC") -> str:
        count_res = await self.session.execute(
            select(func.count(Receipt.id)).where(Receipt.society_id == society_id)
        )
        next_seq = (count_res.scalar() or 0) + 1
        return f"{prefix}-{next_seq:06d}"

    async def create_payment(
        self,
        society_id: UUID,
        payer_user_id: UUID,
        amount: Decimal,
        payment_date: date,
        reference_number: str,
        payment_method: str = "BANK_TRANSFER",
        unit_id: UUID | None = None,
        bank_account_id: UUID | None = None,
        notes: str | None = None,
        currency: str = "INR",
        idempotency_key: str | None = None,
        created_by: UUID | None = None,
    ) -> Payment:
        qty_amount = quantize_amount(amount)
        payment = Payment(
            id=uuid.uuid4(),
            society_id=society_id,
            payer_user_id=payer_user_id,
            unit_id=unit_id,
            bank_account_id=bank_account_id,
            amount=qty_amount,
            currency=currency,
            payment_date=payment_date,
            payment_method=payment_method,
            reference_number=reference_number,
            notes=notes,
            status="RECORDED",
            allocated_amount=Decimal("0.0000"),
            unallocated_amount=qty_amount,
            idempotency_key=idempotency_key,
            created_by=created_by,
        )
        self.session.add(payment)
        await self.session.flush()
        return payment

    async def get_by_idempotency_key(self, society_id: UUID, idempotency_key: str) -> Payment | None:
        res = await self.session.execute(
            select(Payment)
            .options(selectinload(Payment.allocations), selectinload(Payment.receipt))
            .where(Payment.society_id == society_id, Payment.idempotency_key == idempotency_key)
        )
        return res.scalar_one_or_none()

    async def get_by_id(self, payment_id: UUID, society_id: UUID) -> Payment | None:
        res = await self.session.execute(
            select(Payment)
            .options(
                selectinload(Payment.allocations),
                selectinload(Payment.receipt),
            )
            .where(Payment.id == payment_id, Payment.society_id == society_id)
        )
        return res.scalar_one_or_none()

    async def list_payments(
        self,
        society_id: UUID,
        payer_user_id: UUID | None = None,
        unit_id: UUID | None = None,
        bank_account_id: UUID | None = None,
        status: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Payment]:
        query = (
            select(Payment)
            .options(selectinload(Payment.allocations), selectinload(Payment.receipt))
            .where(Payment.society_id == society_id)
        )
        if payer_user_id:
            query = query.where(Payment.payer_user_id == payer_user_id)
        if unit_id:
            query = query.where(Payment.unit_id == unit_id)
        if bank_account_id:
            query = query.where(Payment.bank_account_id == bank_account_id)
        if status:
            query = query.where(Payment.status == status)

        query = (
            query.order_by(Payment.payment_date.desc(), Payment.created_at.desc()).limit(limit).offset(offset)
        )
        res = await self.session.execute(query)
        return list(res.scalars().all())

    async def create_allocation(
        self,
        society_id: UUID,
        payment_id: UUID,
        invoice_id: UUID,
        amount: Decimal,
        allocated_by: UUID | None = None,
    ) -> PaymentAllocation:
        alloc = PaymentAllocation(
            id=uuid.uuid4(),
            society_id=society_id,
            payment_id=payment_id,
            invoice_id=invoice_id,
            amount=quantize_amount(amount),
            allocated_at=datetime.now(UTC),
            allocated_by=allocated_by,
        )
        self.session.add(alloc)
        await self.session.flush()
        return alloc

    async def get_allocations_for_payment(
        self, payment_id: UUID, society_id: UUID, status: str | None = None
    ) -> list[PaymentAllocation]:
        query = select(PaymentAllocation).where(
            PaymentAllocation.payment_id == payment_id,
            PaymentAllocation.society_id == society_id,
        )
        if status:
            query = query.where(PaymentAllocation.status == status)
        res = await self.session.execute(query)
        return list(res.scalars().all())

    async def create_receipt(
        self,
        society_id: UUID,
        payment_id: UUID,
        receipt_number: str,
        receipt_date: date,
        amount: Decimal,
        payer_user_id: UUID,
        unit_id: UUID | None = None,
        created_by: UUID | None = None,
    ) -> Receipt:
        receipt = Receipt(
            id=uuid.uuid4(),
            society_id=society_id,
            payment_id=payment_id,
            receipt_number=receipt_number,
            receipt_date=receipt_date,
            amount=quantize_amount(amount),
            payer_user_id=payer_user_id,
            unit_id=unit_id,
            status="ISSUED",
            created_by=created_by,
        )
        self.session.add(receipt)
        await self.session.flush()
        return receipt

    async def get_receipt_by_id(self, receipt_id: UUID, society_id: UUID) -> Receipt | None:
        res = await self.session.execute(
            select(Receipt)
            .options(selectinload(Receipt.payment))
            .where(Receipt.id == receipt_id, Receipt.society_id == society_id)
        )
        return res.scalar_one_or_none()

    async def list_receipts(
        self,
        society_id: UUID,
        payer_user_id: UUID | None = None,
        unit_id: UUID | None = None,
        status: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Receipt]:
        query = select(Receipt).options(selectinload(Receipt.payment)).where(Receipt.society_id == society_id)
        if payer_user_id:
            query = query.where(Receipt.payer_user_id == payer_user_id)
        if unit_id:
            query = query.where(Receipt.unit_id == unit_id)
        if status:
            query = query.where(Receipt.status == status)
        query = (
            query.order_by(Receipt.receipt_date.desc(), Receipt.created_at.desc()).limit(limit).offset(offset)
        )
        res = await self.session.execute(query)
        return list(res.scalars().all())


class ReconciliationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def generate_session_number(self, society_id: UUID, prefix: str = "REC-SESS") -> str:
        count_res = await self.session.execute(
            select(func.count(ReconciliationSession.id)).where(ReconciliationSession.society_id == society_id)
        )
        next_seq = (count_res.scalar() or 0) + 1
        return f"{prefix}-{next_seq:04d}"

    async def create_session(
        self,
        society_id: UUID,
        session_number: str,
        account_id: UUID,
        statement_reference: str,
        statement_start_date: date,
        statement_end_date: date,
        opening_balance: Decimal,
        closing_balance: Decimal,
        notes: str | None = None,
        created_by: UUID | None = None,
    ) -> ReconciliationSession:
        recon_session = ReconciliationSession(
            id=uuid.uuid4(),
            society_id=society_id,
            session_number=session_number,
            account_id=account_id,
            statement_reference=statement_reference,
            statement_start_date=statement_start_date,
            statement_end_date=statement_end_date,
            opening_balance=quantize_amount(opening_balance),
            closing_balance=quantize_amount(closing_balance),
            reconciled_amount=Decimal("0.0000"),
            unreconciled_amount=quantize_amount(abs(closing_balance - opening_balance)),
            status="OPEN",
            notes=notes,
            created_by=created_by,
        )
        self.session.add(recon_session)
        await self.session.flush()
        return recon_session

    async def get_session_by_id(self, session_id: UUID, society_id: UUID) -> ReconciliationSession | None:
        res = await self.session.execute(
            select(ReconciliationSession)
            .options(
                selectinload(ReconciliationSession.items),
                selectinload(ReconciliationSession.account),
            )
            .where(ReconciliationSession.id == session_id, ReconciliationSession.society_id == society_id)
        )
        return res.scalar_one_or_none()

    async def list_sessions(
        self,
        society_id: UUID,
        account_id: UUID | None = None,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[ReconciliationSession]:
        query = (
            select(ReconciliationSession)
            .options(selectinload(ReconciliationSession.account))
            .where(ReconciliationSession.society_id == society_id)
        )
        if account_id:
            query = query.where(ReconciliationSession.account_id == account_id)
        if status:
            query = query.where(ReconciliationSession.status == status)

        query = (
            query.order_by(
                ReconciliationSession.statement_end_date.desc(), ReconciliationSession.created_at.desc()
            )
            .limit(limit)
            .offset(offset)
        )
        res = await self.session.execute(query)
        return list(res.scalars().all())

    async def add_item(
        self,
        society_id: UUID,
        session_id: UUID,
        transaction_date: date,
        reference_number: str,
        description: str,
        statement_amount: Decimal,
        payment_id: UUID | None = None,
        recorded_amount: Decimal | None = None,
        discrepancy_amount: Decimal = Decimal("0.0000"),
        match_status: str = "UNMATCHED",
        notes: str | None = None,
        matched_by: UUID | None = None,
    ) -> ReconciliationItem:
        item = ReconciliationItem(
            id=uuid.uuid4(),
            society_id=society_id,
            session_id=session_id,
            payment_id=payment_id,
            transaction_date=transaction_date,
            reference_number=reference_number,
            description=description,
            statement_amount=quantize_amount(statement_amount),
            recorded_amount=quantize_amount(recorded_amount) if recorded_amount is not None else None,
            discrepancy_amount=quantize_amount(discrepancy_amount),
            match_status=match_status,
            notes=notes,
            matched_at=datetime.now(UTC) if match_status == "MATCHED" else None,
            matched_by=matched_by,
        )
        self.session.add(item)
        await self.session.flush()
        return item
