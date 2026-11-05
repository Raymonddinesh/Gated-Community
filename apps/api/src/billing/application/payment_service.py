"""Payment Application Service: Recording, Allocation, Reversal, and Receipt Management."""

from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.billing.domain.exceptions import (
    BillingAccountingIntegrationException,
    BillingConfigNotFoundException,
    CrossTenantBillingException,
    InvoiceNotFoundException,
    PaymentImmutableException,
    PaymentNotFoundException,
    PaymentOverAllocationException,
    ReceiptImmutableException,
    ReceiptNotFoundException,
)
from apps.api.src.billing.domain.models import InvoiceStatus, PaymentMethod, PaymentStatus, ReceiptStatus
from apps.api.src.billing.infrastructure.repositories import (
    BillingConfigRepository,
    BillingPeriodRepository,
    InvoiceRepository,
    PaymentRepository,
)
from apps.api.src.core.exceptions import AppException
from apps.api.src.database.models.billing import Invoice, Payment, Receipt
from apps.api.src.database.repositories.audit_repository import AuditRepository
from apps.api.src.finance.application.journal_service import JournalService
from apps.api.src.finance.domain.models import quantize_amount
from apps.api.src.finance.infrastructure.repositories import AccountRepository, PeriodRepository


class PaymentService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.payment_repo = PaymentRepository(session)
        self.invoice_repo = InvoiceRepository(session)
        self.period_repo = BillingPeriodRepository(session)
        self.fin_period_repo = PeriodRepository(session)
        self.config_repo = BillingConfigRepository(session)
        self.account_repo = AccountRepository(session)
        self.journal_service = JournalService(session)
        self.audit_repo = AuditRepository(session)

    async def get_payment(self, payment_id: UUID, society_id: UUID) -> Payment:
        payment = await self.payment_repo.get_by_id(payment_id, society_id)
        if not payment:
            raise PaymentNotFoundException(payment_id)
        return payment

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
        return await self.payment_repo.list_payments(
            society_id=society_id,
            payer_user_id=payer_user_id,
            unit_id=unit_id,
            bank_account_id=bank_account_id,
            status=status,
            limit=limit,
            offset=offset,
        )

    async def _post_payment_journal(
        self,
        payment: Payment,
        fin_period_id: UUID,
        bank_account_id: UUID,
        receivable_account_id: UUID,
        created_by: UUID | None = None,
        correlation_id: str | None = None,
    ) -> UUID:
        """Post balanced double-entry payment journal to Phase 4 GL: Debit Bank/Cash, Credit AR."""
        journal_lines = [
            {
                "account_id": bank_account_id,
                "debit_amount": payment.amount,
                "credit_amount": Decimal("0.0000"),
                "description": f"Payment {payment.reference_number} received from resident",
            },
            {
                "account_id": receivable_account_id,
                "debit_amount": Decimal("0.0000"),
                "credit_amount": payment.amount,
                "description": f"Dues clearance for payment {payment.reference_number}",
            },
        ]
        journal_idempotency_key = f"PAYMENT:{payment.society_id}:{payment.id}:CLEARED"
        try:
            journal = await self.journal_service.create_draft_journal(
                society_id=payment.society_id,
                financial_period_id=fin_period_id,
                entry_date=payment.payment_date,
                description=f"Maintenance payment received ref {payment.reference_number}",
                lines_data=journal_lines,
                source_type="PAYMENT",
                source_record_id=str(payment.id),
                reference_number=payment.reference_number,
                currency=payment.currency,
                idempotency_key=journal_idempotency_key,
                created_by=created_by,
                correlation_id=correlation_id,
            )
            posted_journal = await self.journal_service.post_journal(
                journal_id=journal.id,
                society_id=payment.society_id,
                posted_by=created_by,
                correlation_id=correlation_id,
            )
            return posted_journal.id
        except Exception as exc:
            raise BillingAccountingIntegrationException(
                f"Failed to post accounting journal for payment '{payment.reference_number}': {exc}"
            ) from exc

    async def record_payment(
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
        auto_allocate: bool = True,
        auto_clear: bool | None = None,
        correlation_id: str | None = None,
    ) -> Payment:
        """
        Record a resident payment manually.
        If auto_clear is True (or for instant payment methods like CASH, UPI, CARD by default),
        posts a balanced double-entry GL journal:
          Debit: Selected Bank or Cash Account
          Credit: Resident Receivable Account
        If auto_clear is False (for offline/cheque instruments awaiting clearance),
        payment is marked RECORDED with zero bank inflation until cleared.
        """
        # 1. Idempotency Check
        if idempotency_key:
            existing = await self.payment_repo.get_by_idempotency_key(society_id, idempotency_key)
            if existing:
                return existing

        qty_amount = quantize_amount(amount)
        if qty_amount <= Decimal("0.0000"):
            raise AppException(
                code="INVALID_AMOUNT", message="Payment amount must be greater than zero.", status_code=400
            )

        # 2. Validate Payment Method
        valid_methods = {m.value for m in PaymentMethod}
        if payment_method not in valid_methods:
            raise AppException(
                code="INVALID_PAYMENT_METHOD",
                message=f"Invalid payment method '{payment_method}'. Valid methods: {', '.join(sorted(valid_methods))}",
                status_code=400,
            )

        config = await self.config_repo.get_by_society_id(society_id)
        if not config:
            raise BillingConfigNotFoundException(society_id)

        # 3. Validate Bank/Cash Account linkage
        target_bank_account_id = bank_account_id or config.bank_account_id or config.income_account_id
        if bank_account_id:
            acc = await self.account_repo.get_by_id(bank_account_id, society_id)
            if not acc:
                raise AppException(
                    code="ACCOUNT_NOT_FOUND",
                    message="Specified bank or cash account does not exist or belong to this society.",
                    status_code=400,
                )
            if not acc.is_active:
                raise AppException(
                    code="INACTIVE_ACCOUNT",
                    message=f"Account '{acc.account_code}' is inactive and cannot receive payments.",
                    status_code=400,
                )

        # 4. Financial Period Control: Check that payment_date falls in an OPEN financial period
        fin_period = await self.fin_period_repo.get_open_period_for_date(society_id, payment_date)
        if not fin_period:
            raise AppException(
                code="PERIOD_CLOSED",
                message=f"No OPEN financial reporting period covers payment date {payment_date.isoformat()}.",
                status_code=400,
            )

        # 5. Create Payment Record
        payment = await self.payment_repo.create_payment(
            society_id=society_id,
            payer_user_id=payer_user_id,
            amount=qty_amount,
            payment_date=payment_date,
            reference_number=reference_number,
            payment_method=payment_method,
            unit_id=unit_id,
            bank_account_id=target_bank_account_id,
            notes=notes,
            currency=currency,
            idempotency_key=idempotency_key,
            created_by=created_by,
        )

        # 6. Clearance & Accounting treatment
        should_clear = (
            auto_clear
            if auto_clear is not None
            else (
                payment_method
                in (PaymentMethod.CASH.value, PaymentMethod.UPI.value, PaymentMethod.CARD.value)
            )
        )

        if should_clear:
            journal_id = await self._post_payment_journal(
                payment=payment,
                fin_period_id=fin_period.id,
                bank_account_id=target_bank_account_id,
                receivable_account_id=config.receivable_account_id,
                created_by=created_by,
                correlation_id=correlation_id,
            )
            payment.journal_entry_id = journal_id
            payment.status = PaymentStatus.CLEARED.value
        else:
            payment.status = PaymentStatus.RECORDED.value
            payment.journal_entry_id = None

        # 7. Generate payment receipt
        receipt_no = await self.payment_repo.generate_receipt_number(society_id)
        await self.payment_repo.create_receipt(
            society_id=society_id,
            payment_id=payment.id,
            receipt_number=receipt_no,
            receipt_date=payment_date,
            amount=qty_amount,
            payer_user_id=payer_user_id,
            unit_id=unit_id,
            created_by=created_by,
        )

        # 8. Auto-allocate against oldest unpaid published invoices if requested
        if auto_allocate:
            if payment.status == PaymentStatus.RECORDED.value:
                await self.clear_payment(
                    society_id, payment.id, cleared_by=created_by, correlation_id=correlation_id
                )
            await self._auto_allocate_payment(society_id, payment, created_by)

        await self.session.flush()

        await self.audit_repo.log_event(
            action="BILLING_PAYMENT_RECORDED",
            entity_type="payment",
            entity_id=str(payment.id),
            society_id=society_id,
            actor_user_id=created_by,
            correlation_id=correlation_id,
            after_state={
                "amount": str(payment.amount),
                "reference_number": payment.reference_number,
                "status": payment.status,
                "allocated_amount": str(payment.allocated_amount),
                "unallocated_amount": str(payment.unallocated_amount),
            },
        )
        return payment

    async def clear_payment(
        self,
        society_id: UUID,
        payment_id: UUID,
        cleared_by: UUID | None = None,
        cleared_date: date | None = None,
        correlation_id: str | None = None,
    ) -> Payment:
        """
        Explicitly clear a recorded payment and post its double-entry GL journal:
          Debit: Selected Bank or Cash Account
          Credit: Resident Receivable Account
        """
        payment = await self.get_payment(payment_id, society_id)
        if payment.status in (
            PaymentStatus.CLEARED.value,
            PaymentStatus.ALLOCATED.value,
            PaymentStatus.PARTIALLY_ALLOCATED.value,
        ):
            if payment.journal_entry_id:
                return payment

        if payment.status in (
            PaymentStatus.BOUNCED.value,
            PaymentStatus.CANCELLED.value,
            PaymentStatus.REVERSED.value,
            PaymentStatus.REFUNDED.value,
        ):
            raise AppException(
                code="PAYMENT_NOT_CLEARABLE",
                message=f"Payment with status '{payment.status}' cannot be cleared.",
                status_code=400,
            )

        eff_date = cleared_date or payment.payment_date
        fin_period = await self.fin_period_repo.get_open_period_for_date(society_id, eff_date)
        if not fin_period:
            raise AppException(
                code="PERIOD_CLOSED",
                message=f"No OPEN financial reporting period covers clearance date {eff_date.isoformat()}.",
                status_code=400,
            )

        config = await self.config_repo.get_by_society_id(society_id)
        if not config:
            raise BillingConfigNotFoundException(society_id)

        target_bank_account_id = payment.bank_account_id or config.bank_account_id or config.income_account_id
        journal_id = await self._post_payment_journal(
            payment=payment,
            fin_period_id=fin_period.id,
            bank_account_id=target_bank_account_id,
            receivable_account_id=config.receivable_account_id,
            created_by=cleared_by,
            correlation_id=correlation_id,
        )
        payment.journal_entry_id = journal_id
        if payment.allocated_amount > Decimal("0.0000"):
            payment.status = (
                PaymentStatus.ALLOCATED.value
                if payment.unallocated_amount == Decimal("0.0000")
                else PaymentStatus.PARTIALLY_ALLOCATED.value
            )
        else:
            payment.status = PaymentStatus.CLEARED.value

        await self.session.flush()
        await self.audit_repo.log_event(
            action="BILLING_PAYMENT_CLEARED",
            entity_type="payment",
            entity_id=str(payment.id),
            society_id=society_id,
            actor_user_id=cleared_by,
            correlation_id=correlation_id,
            after_state={
                "status": payment.status,
                "journal_entry_id": str(journal_id),
                "cleared_amount": str(payment.amount),
            },
        )
        return payment

    async def allocate_payment(
        self,
        society_id: UUID,
        payment_id: UUID,
        invoice_id: UUID,
        amount: Decimal,
        allocated_by: UUID | None = None,
        correlation_id: str | None = None,
    ) -> Payment:
        payment = await self.get_payment(payment_id, society_id)
        invoice = await self.invoice_repo.get_by_id(invoice_id, society_id)
        if not invoice:
            raise InvoiceNotFoundException(invoice_id)

        if invoice.society_id != society_id or payment.society_id != society_id:
            raise CrossTenantBillingException()

        if invoice.status in (InvoiceStatus.CANCELLED.value, InvoiceStatus.DRAFT.value):
            raise AppException(
                code="INVOICE_NOT_PAYABLE",
                message=f"Invoice '{invoice.invoice_number}' has status '{invoice.status}' and cannot receive payment allocations.",
                status_code=400,
            )

        if payment.status in (
            PaymentStatus.CANCELLED.value,
            PaymentStatus.BOUNCED.value,
            PaymentStatus.REVERSED.value,
            PaymentStatus.REFUNDED.value,
        ):
            raise AppException(
                code="PAYMENT_NOT_ALLOCATABLE",
                message=f"Payment has status '{payment.status}' and cannot be allocated.",
                status_code=400,
            )

        # Ensure payment is cleared before allocating to maintain dues integrity
        if payment.status == PaymentStatus.RECORDED.value:
            payment = await self.clear_payment(
                society_id=society_id,
                payment_id=payment.id,
                cleared_by=allocated_by,
                correlation_id=correlation_id,
            )

        qty_amount = quantize_amount(amount)
        if qty_amount <= Decimal("0.0000"):
            raise AppException(
                code="INVALID_AMOUNT", message="Allocation amount must be greater than zero.", status_code=400
            )

        if qty_amount > payment.unallocated_amount:
            raise PaymentOverAllocationException(
                requested=str(qty_amount),
                available=str(payment.unallocated_amount),
            )

        if qty_amount > invoice.outstanding_amount:
            raise AppException(
                code="INVOICE_OVER_ALLOCATION",
                message=f"Cannot allocate {qty_amount}; invoice outstanding is only {invoice.outstanding_amount}.",
                status_code=400,
            )

        # Apply allocation
        await self.payment_repo.create_allocation(
            society_id=society_id,
            payment_id=payment.id,
            invoice_id=invoice.id,
            amount=qty_amount,
            allocated_by=allocated_by,
        )

        payment.allocated_amount += qty_amount
        payment.unallocated_amount -= qty_amount
        if payment.unallocated_amount == Decimal("0.0000"):
            payment.status = PaymentStatus.ALLOCATED.value
        else:
            payment.status = PaymentStatus.PARTIALLY_ALLOCATED.value

        invoice.paid_amount += qty_amount
        invoice.outstanding_amount -= qty_amount
        if invoice.outstanding_amount == Decimal("0.0000"):
            invoice.status = InvoiceStatus.PAID.value
        else:
            invoice.status = InvoiceStatus.PARTIALLY_PAID.value

        await self.session.flush()

        await self.audit_repo.log_event(
            action="BILLING_PAYMENT_ALLOCATED",
            entity_type="payment_allocation",
            entity_id=str(payment.id),
            society_id=society_id,
            actor_user_id=allocated_by,
            correlation_id=correlation_id,
            after_state={
                "allocated_amount": str(qty_amount),
                "invoice_number": invoice.invoice_number,
                "remaining_unallocated": str(payment.unallocated_amount),
                "invoice_outstanding": str(invoice.outstanding_amount),
            },
        )
        return payment

    async def bounce_payment(
        self,
        society_id: UUID,
        payment_id: UUID,
        reason: str,
        bounced_by: UUID | None = None,
        correlation_id: str | None = None,
    ) -> Payment:
        """
        Record cheque/instrument bounce.
        Unwinds allocations non-destructively, voids receipt, and reverses GL journal if cleared.
        """
        payment = await self.get_payment(payment_id, society_id)
        if payment.status in (
            PaymentStatus.BOUNCED.value,
            PaymentStatus.CANCELLED.value,
            PaymentStatus.REVERSED.value,
        ):
            raise PaymentImmutableException(payment.id, payment.status)

        # 1. Unwind invoice allocations non-destructively
        allocations = await self.payment_repo.get_allocations_for_payment(payment.id, society_id)
        for alloc in allocations:
            if alloc.status == "REVERSED":
                continue
            invoice = await self.invoice_repo.get_by_id(alloc.invoice_id, society_id)
            if invoice:
                invoice.paid_amount -= alloc.amount
                invoice.outstanding_amount += alloc.amount
                if invoice.outstanding_amount > Decimal("0.0000"):
                    invoice.status = (
                        InvoiceStatus.PARTIALLY_PAID.value
                        if invoice.paid_amount > Decimal("0.0000")
                        else InvoiceStatus.PUBLISHED.value
                    )
            alloc.status = "REVERSED"
            alloc.reversed_at = datetime.now(UTC)
            alloc.reversed_by = bounced_by
            alloc.reversal_reason = f"Payment bounced: {reason}"
            alloc.reversal_reference = f"BOUNCE:{payment.reference_number}"

        payment.allocated_amount = Decimal("0.0000")
        payment.unallocated_amount = payment.amount

        # 2. Cancel receipt if present
        if payment.receipt and payment.receipt.status == ReceiptStatus.ISSUED.value:
            payment.receipt.status = ReceiptStatus.CANCELLED.value
            payment.receipt.cancelled_at = datetime.now(UTC)
            payment.receipt.cancelled_by = bounced_by
            payment.receipt.cancellation_reason = f"Payment bounced: {reason}"

        # 3. If a GL journal was posted, reverse it
        if payment.journal_entry_id:
            reversal_journal = await self.journal_service.reverse_journal(
                journal_id=payment.journal_entry_id,
                society_id=society_id,
                reason=f"Payment {payment.reference_number} bounced: {reason}",
                reversed_by=bounced_by,
                correlation_id=correlation_id,
            )
            payment.reversal_journal_entry_id = reversal_journal.id

        payment.status = PaymentStatus.BOUNCED.value
        payment.reversed_at = datetime.now(UTC)
        payment.reversed_by = bounced_by
        payment.reversal_reason = reason
        await self.session.flush()

        await self.audit_repo.log_event(
            action="BILLING_PAYMENT_BOUNCED",
            entity_type="payment",
            entity_id=str(payment.id),
            society_id=society_id,
            actor_user_id=bounced_by,
            correlation_id=correlation_id,
            after_state={
                "status": payment.status,
                "reversal_reason": reason,
                "reference_number": payment.reference_number,
            },
        )
        return payment

    async def reverse_payment(
        self,
        society_id: UUID,
        payment_id: UUID,
        reason: str,
        reversed_by: UUID | None = None,
        correlation_id: str | None = None,
    ) -> Payment:
        """
        Reverse a cleared/allocated payment.
        1. De-allocates applied amounts from invoices non-destructively (status='REVERSED').
        2. Voids payment receipt with status='CANCELLED'.
        3. Posts balanced reversal journal in Phase 4 GL (reversing bank debit and AR credit).
        4. Sets payment status='REVERSED'.
        """
        payment = await self.get_payment(payment_id, society_id)
        if payment.status in (
            PaymentStatus.CANCELLED.value,
            PaymentStatus.BOUNCED.value,
            PaymentStatus.REVERSED.value,
            PaymentStatus.REFUNDED.value,
        ):
            raise PaymentImmutableException(payment.id, payment.status)

        # 1. Unwind invoice allocations non-destructively
        allocations = await self.payment_repo.get_allocations_for_payment(payment.id, society_id)
        for alloc in allocations:
            if alloc.status == "REVERSED":
                continue
            invoice = await self.invoice_repo.get_by_id(alloc.invoice_id, society_id)
            if invoice:
                invoice.paid_amount -= alloc.amount
                invoice.outstanding_amount += alloc.amount
                if invoice.outstanding_amount > Decimal("0.0000"):
                    invoice.status = (
                        InvoiceStatus.PARTIALLY_PAID.value
                        if invoice.paid_amount > Decimal("0.0000")
                        else InvoiceStatus.PUBLISHED.value
                    )
            alloc.status = "REVERSED"
            alloc.reversed_at = datetime.now(UTC)
            alloc.reversed_by = reversed_by
            alloc.reversal_reason = reason
            alloc.reversal_reference = f"REV:{payment.reference_number}"

        payment.allocated_amount = Decimal("0.0000")
        payment.unallocated_amount = payment.amount

        # 2. Cancel receipt if present
        if payment.receipt and payment.receipt.status == ReceiptStatus.ISSUED.value:
            payment.receipt.status = ReceiptStatus.CANCELLED.value
            payment.receipt.cancelled_at = datetime.now(UTC)
            payment.receipt.cancelled_by = reversed_by
            payment.receipt.cancellation_reason = f"Payment reversed: {reason}"

        # 3. Post reversal journal entry via Phase 4 GL if original entry was posted
        if payment.journal_entry_id:
            reversal_journal = await self.journal_service.reverse_journal(
                journal_id=payment.journal_entry_id,
                society_id=society_id,
                reason=f"Payment {payment.reference_number} reversed: {reason}",
                reversed_by=reversed_by,
                correlation_id=correlation_id,
            )
            payment.reversal_journal_entry_id = reversal_journal.id

        payment.status = PaymentStatus.REVERSED.value
        payment.reversed_at = datetime.now(UTC)
        payment.reversed_by = reversed_by
        payment.reversal_reason = reason
        await self.session.flush()

        await self.audit_repo.log_event(
            action="BILLING_PAYMENT_REVERSED",
            entity_type="payment",
            entity_id=str(payment.id),
            society_id=society_id,
            actor_user_id=reversed_by,
            correlation_id=correlation_id,
            after_state={
                "status": payment.status,
                "reversal_reason": reason,
                "reference_number": payment.reference_number,
            },
        )
        return payment

    async def refund_payment(
        self,
        society_id: UUID,
        payment_id: UUID,
        amount: Decimal,
        reason: str,
        refunded_by: UUID | None = None,
        correlation_id: str | None = None,
    ) -> Payment:
        """
        Refund unallocated payment balance back to resident.
        Posts a balanced refund journal (Debit AR, Credit Bank) in Phase 4 GL if payment was cleared.
        """
        payment = await self.get_payment(payment_id, society_id)
        if payment.status in (
            PaymentStatus.BOUNCED.value,
            PaymentStatus.CANCELLED.value,
            PaymentStatus.REVERSED.value,
            PaymentStatus.REFUNDED.value,
        ):
            raise AppException(
                code="PAYMENT_NOT_REFUNDABLE",
                message=f"Payment with status '{payment.status}' cannot be refunded.",
                status_code=400,
            )

        qty_refund = quantize_amount(amount)
        if qty_refund <= Decimal("0.0000"):
            raise AppException(
                code="INVALID_AMOUNT",
                message="Refund amount must be greater than zero.",
                status_code=400,
            )

        if qty_refund > payment.unallocated_amount:
            raise AppException(
                code="REFUND_EXCEEDS_UNALLOCATED",
                message=f"Cannot refund {qty_refund}; unallocated payment balance is only {payment.unallocated_amount}.",
                status_code=400,
            )

        # If payment was cleared in GL, post a balanced refund entry (Debit AR, Credit Bank)
        if payment.journal_entry_id:
            fin_period = await self.fin_period_repo.get_open_period_for_date(society_id, payment.payment_date)
            if not fin_period:
                raise AppException(
                    code="PERIOD_CLOSED",
                    message="No OPEN financial reporting period covers the refund date.",
                    status_code=400,
                )
            config = await self.config_repo.get_by_society_id(society_id)
            if not config:
                raise BillingConfigNotFoundException(society_id)

            target_bank_account_id = (
                payment.bank_account_id or config.bank_account_id or config.income_account_id
            )
            refund_lines = [
                {
                    "account_id": config.receivable_account_id,
                    "debit_amount": qty_refund,
                    "credit_amount": Decimal("0.0000"),
                    "description": f"Refund of unallocated dues ref {payment.reference_number}: {reason}",
                },
                {
                    "account_id": target_bank_account_id,
                    "debit_amount": Decimal("0.0000"),
                    "credit_amount": qty_refund,
                    "description": f"Bank payout for refund ref {payment.reference_number}",
                },
            ]
            refund_idemp = f"PAYMENT:{society_id}:{payment.id}:REFUND:{payment.amount - payment.unallocated_amount + qty_refund}"
            journal = await self.journal_service.create_draft_journal(
                society_id=society_id,
                financial_period_id=fin_period.id,
                entry_date=payment.payment_date,
                description=f"Payment refund ref {payment.reference_number}: {reason}",
                lines_data=refund_lines,
                source_type="PAYMENT_REFUND",
                source_record_id=str(payment.id),
                reference_number=f"REFUND-{payment.reference_number}",
                currency=payment.currency,
                idempotency_key=refund_idemp,
                created_by=refunded_by,
                correlation_id=correlation_id,
            )
            await self.journal_service.post_journal(
                journal_id=journal.id,
                society_id=society_id,
                posted_by=refunded_by,
                correlation_id=correlation_id,
            )

        payment.unallocated_amount -= qty_refund
        if payment.unallocated_amount == Decimal("0.0000") and payment.allocated_amount == Decimal("0.0000"):
            payment.status = PaymentStatus.REFUNDED.value

        await self.session.flush()
        await self.audit_repo.log_event(
            action="BILLING_PAYMENT_REFUNDED",
            entity_type="payment",
            entity_id=str(payment.id),
            society_id=society_id,
            actor_user_id=refunded_by,
            correlation_id=correlation_id,
            after_state={
                "status": payment.status,
                "refunded_amount": str(qty_refund),
                "remaining_unallocated": str(payment.unallocated_amount),
                "reason": reason,
            },
        )
        return payment

    async def get_receipt(self, receipt_id: UUID, society_id: UUID) -> Receipt:
        receipt = await self.payment_repo.get_receipt_by_id(receipt_id, society_id)
        if not receipt:
            raise ReceiptNotFoundException(receipt_id)
        return receipt

    async def cancel_receipt(
        self,
        receipt_id: UUID,
        society_id: UUID,
        reason: str,
        cancelled_by: UUID | None = None,
        correlation_id: str | None = None,
    ) -> Receipt:
        receipt = await self.get_receipt(receipt_id, society_id)
        if receipt.status == ReceiptStatus.CANCELLED.value:
            raise ReceiptImmutableException(receipt.receipt_number, receipt.status)

        receipt.status = ReceiptStatus.CANCELLED.value
        receipt.cancelled_at = datetime.now(UTC)
        receipt.cancelled_by = cancelled_by
        receipt.cancellation_reason = reason
        await self.session.flush()

        await self.audit_repo.log_event(
            action="BILLING_RECEIPT_CANCELLED",
            entity_type="receipt",
            entity_id=str(receipt.id),
            society_id=society_id,
            actor_user_id=cancelled_by,
            correlation_id=correlation_id,
            after_state={
                "receipt_number": receipt.receipt_number,
                "status": receipt.status,
                "reason": reason,
            },
        )
        return receipt

    async def list_receipts(
        self,
        society_id: UUID,
        payer_user_id: UUID | None = None,
        unit_id: UUID | None = None,
        status: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Receipt]:
        return await self.payment_repo.list_receipts(
            society_id=society_id,
            payer_user_id=payer_user_id,
            unit_id=unit_id,
            status=status,
            limit=limit,
            offset=offset,
        )

    async def _auto_allocate_payment(
        self, society_id: UUID, payment: Payment, allocated_by: UUID | None
    ) -> None:
        """Allocate unallocated funds to oldest published overdue/unpaid invoices first."""
        query = select(Invoice).where(
            Invoice.society_id == society_id,
            Invoice.status.in_(
                [
                    InvoiceStatus.PUBLISHED.value,
                    InvoiceStatus.PARTIALLY_PAID.value,
                    InvoiceStatus.OVERDUE.value,
                ]
            ),
            Invoice.outstanding_amount > Decimal("0.0000"),
        )
        if payment.unit_id:
            query = query.where(Invoice.unit_id == payment.unit_id)
        else:
            query = query.where(Invoice.responsible_user_id == payment.payer_user_id)

        query = query.order_by(Invoice.due_date.asc(), Invoice.invoice_date.asc())
        res = await self.session.execute(query)
        invoices = list(res.scalars().all())

        for inv in invoices:
            if payment.unallocated_amount <= Decimal("0.0000"):
                break

            alloc_amount = min(payment.unallocated_amount, inv.outstanding_amount)
            if alloc_amount > Decimal("0.0000"):
                await self.allocate_payment(
                    society_id=society_id,
                    payment_id=payment.id,
                    invoice_id=inv.id,
                    amount=alloc_amount,
                    allocated_by=allocated_by,
                )
