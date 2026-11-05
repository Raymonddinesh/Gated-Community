"""Bank and Cash Reconciliation Application Service."""

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.billing.domain.exceptions import (
    CrossTenantBillingException,
    PaymentNotFoundException,
    ReconciliationClosedException,
    ReconciliationNotFoundException,
)
from apps.api.src.billing.domain.models import MatchStatus, ReconciliationSessionStatus
from apps.api.src.billing.infrastructure.repositories import PaymentRepository, ReconciliationRepository
from apps.api.src.core.exceptions import AppException
from apps.api.src.database.models.reconciliation import ReconciliationItem, ReconciliationSession
from apps.api.src.database.repositories.audit_repository import AuditRepository
from apps.api.src.finance.domain.models import quantize_amount
from apps.api.src.finance.infrastructure.repositories import AccountRepository


class ReconciliationService:
    """Manages Bank/Cash reconciliation sessions, statement item matching, and discrepancy tracking."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.recon_repo = ReconciliationRepository(session)
        self.payment_repo = PaymentRepository(session)
        self.account_repo = AccountRepository(session)
        self.audit_repo = AuditRepository(session)

    @property
    def payment_service(self) -> Any:
        from apps.api.src.billing.application.payment_service import PaymentService

        return PaymentService(self.session)

    async def get_session(self, session_id: UUID, society_id: UUID) -> ReconciliationSession:
        recon_session = await self.recon_repo.get_session_by_id(session_id, society_id)
        if not recon_session:
            raise ReconciliationNotFoundException(session_id)
        return recon_session

    async def list_sessions(
        self,
        society_id: UUID,
        account_id: UUID | None = None,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[ReconciliationSession]:
        return await self.recon_repo.list_sessions(
            society_id=society_id,
            account_id=account_id,
            status=status,
            limit=limit,
            offset=offset,
        )

    async def create_session(
        self,
        society_id: UUID,
        account_id: UUID,
        statement_reference: str,
        statement_start_date: date,
        statement_end_date: date,
        opening_balance: Decimal,
        closing_balance: Decimal,
        notes: str | None = None,
        created_by: UUID | None = None,
        correlation_id: str | None = None,
    ) -> ReconciliationSession:
        if statement_end_date < statement_start_date:
            raise AppException(
                code="INVALID_DATE_RANGE",
                message="Statement end date must be on or after start date.",
                status_code=400,
            )

        # Validate that account belongs to this society
        acc = await self.account_repo.get_by_id(account_id, society_id)
        if not acc:
            raise CrossTenantBillingException("Financial account does not exist or belong to this society.")

        session_number = await self.recon_repo.generate_session_number(society_id)
        recon_session = await self.recon_repo.create_session(
            society_id=society_id,
            session_number=session_number,
            account_id=account_id,
            statement_reference=statement_reference,
            statement_start_date=statement_start_date,
            statement_end_date=statement_end_date,
            opening_balance=opening_balance,
            closing_balance=closing_balance,
            notes=notes,
            created_by=created_by,
        )

        await self.audit_repo.log_event(
            action="RECONCILIATION_SESSION_CREATED",
            entity_type="reconciliation_session",
            entity_id=str(recon_session.id),
            society_id=society_id,
            actor_user_id=created_by,
            correlation_id=correlation_id,
            after_state={
                "session_number": recon_session.session_number,
                "statement_reference": recon_session.statement_reference,
                "account_id": str(recon_session.account_id),
                "opening_balance": str(recon_session.opening_balance),
                "closing_balance": str(recon_session.closing_balance),
            },
        )
        return recon_session

    async def add_statement_item(
        self,
        society_id: UUID,
        session_id: UUID,
        transaction_date: date,
        reference_number: str,
        description: str,
        statement_amount: Decimal,
        payment_id: UUID | None = None,
        notes: str | None = None,
        matched_by: UUID | None = None,
    ) -> ReconciliationItem:
        recon_session = await self.get_session(session_id, society_id)
        if recon_session.status in (
            ReconciliationSessionStatus.CLOSED.value,
            ReconciliationSessionStatus.CANCELLED.value,
        ):
            raise ReconciliationClosedException(recon_session.session_number)

        qty_statement_amount = quantize_amount(statement_amount)
        recorded_amount: Decimal | None = None
        discrepancy = Decimal("0.0000")
        match_status = MatchStatus.UNMATCHED.value

        if payment_id:
            payment = await self.payment_repo.get_by_id(payment_id, society_id)
            if not payment:
                raise PaymentNotFoundException(payment_id)
            recorded_amount = payment.amount
            discrepancy = quantize_amount(abs(qty_statement_amount - recorded_amount))
            match_status = (
                MatchStatus.MATCHED.value if discrepancy == Decimal("0.0000") else MatchStatus.MISMATCH.value
            )

        item = await self.recon_repo.add_item(
            society_id=society_id,
            session_id=recon_session.id,
            transaction_date=transaction_date,
            reference_number=reference_number,
            description=description,
            statement_amount=qty_statement_amount,
            payment_id=payment_id,
            recorded_amount=recorded_amount,
            discrepancy_amount=discrepancy,
            match_status=match_status,
            notes=notes,
            matched_by=matched_by if match_status == MatchStatus.MATCHED.value else None,
        )

        if match_status == MatchStatus.MATCHED.value:
            recon_session.reconciled_amount += qty_statement_amount
            recon_session.unreconciled_amount = quantize_amount(
                max(Decimal("0.0000"), recon_session.unreconciled_amount - qty_statement_amount)
            )
            recon_session.status = ReconciliationSessionStatus.IN_PROGRESS.value
            if payment_id:
                matched_payment = await self.payment_repo.get_by_id(payment_id, society_id)
                if matched_payment and matched_payment.status == "RECORDED":
                    await self.payment_service.clear_payment(
                        society_id=society_id,
                        payment_id=matched_payment.id,
                        cleared_by=matched_by,
                        cleared_date=transaction_date,
                    )

        await self.session.flush()
        return item

    async def match_item(
        self,
        society_id: UUID,
        session_id: UUID,
        item_id: UUID,
        payment_id: UUID,
        matched_by: UUID | None = None,
        correlation_id: str | None = None,
    ) -> ReconciliationItem:
        recon_session = await self.get_session(session_id, society_id)
        if recon_session.status in (
            ReconciliationSessionStatus.CLOSED.value,
            ReconciliationSessionStatus.CANCELLED.value,
        ):
            raise ReconciliationClosedException(recon_session.session_number)

        target_item: ReconciliationItem | None = None
        for item in recon_session.items:
            if item.id == item_id:
                target_item = item
                break

        if not target_item:
            raise AppException(
                code="RECON_ITEM_NOT_FOUND",
                message=f"Item '{item_id}' not found in session.",
                status_code=404,
            )

        payment = await self.payment_repo.get_by_id(payment_id, society_id)
        if not payment:
            raise PaymentNotFoundException(payment_id)

        target_item.payment_id = payment.id
        target_item.recorded_amount = payment.amount
        target_item.discrepancy_amount = quantize_amount(abs(target_item.statement_amount - payment.amount))

        if target_item.discrepancy_amount == Decimal("0.0000"):
            target_item.match_status = MatchStatus.MATCHED.value
            target_item.matched_at = datetime.now(UTC)
            target_item.matched_by = matched_by
            recon_session.reconciled_amount += target_item.statement_amount
            recon_session.unreconciled_amount = quantize_amount(
                max(Decimal("0.0000"), recon_session.unreconciled_amount - target_item.statement_amount)
            )
            recon_session.status = ReconciliationSessionStatus.IN_PROGRESS.value
            if payment.status == "RECORDED":
                await self.payment_service.clear_payment(
                    society_id=society_id,
                    payment_id=payment.id,
                    cleared_by=matched_by,
                    cleared_date=target_item.transaction_date,
                    correlation_id=correlation_id,
                )
        else:
            target_item.match_status = MatchStatus.MISMATCH.value

        await self.session.flush()

        await self.audit_repo.log_event(
            action="RECONCILIATION_ITEM_MATCHED",
            entity_type="reconciliation_item",
            entity_id=str(target_item.id),
            society_id=society_id,
            actor_user_id=matched_by,
            correlation_id=correlation_id,
            after_state={
                "match_status": target_item.match_status,
                "statement_amount": str(target_item.statement_amount),
                "recorded_amount": str(target_item.recorded_amount),
                "discrepancy": str(target_item.discrepancy_amount),
            },
        )
        return target_item

    async def close_session(
        self,
        society_id: UUID,
        session_id: UUID,
        closed_by: UUID | None = None,
        correlation_id: str | None = None,
    ) -> ReconciliationSession:
        recon_session = await self.get_session(session_id, society_id)
        if recon_session.status == ReconciliationSessionStatus.CLOSED.value:
            return recon_session

        recon_session.status = ReconciliationSessionStatus.CLOSED.value
        recon_session.closed_at = datetime.now(UTC)
        recon_session.closed_by = closed_by
        await self.session.flush()

        await self.audit_repo.log_event(
            action="RECONCILIATION_SESSION_CLOSED",
            entity_type="reconciliation_session",
            entity_id=str(recon_session.id),
            society_id=society_id,
            actor_user_id=closed_by,
            correlation_id=correlation_id,
            after_state={
                "session_number": recon_session.session_number,
                "status": recon_session.status,
                "reconciled_amount": str(recon_session.reconciled_amount),
                "unreconciled_amount": str(recon_session.unreconciled_amount),
            },
        )
        return recon_session
