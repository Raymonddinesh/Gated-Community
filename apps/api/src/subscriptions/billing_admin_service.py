"""Phase 21E.5 — SaaS Platform Commercial Billing Administration Domain Service.

Provides administrative business logic for:
1. Subscription plan catalog management (CRUD, soft-archival, entitlements).
2. Global subscription monitoring across tenant societies.
3. Payment transaction and outbound refund audit inspection.
4. Manual billing adjustments (goodwill waivers, advance balances).
5. Society advance balance aggregation.

Strictly preserves historical financial integrity and requires SUPER_ADMIN authorization.
"""

import logging
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import case, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from apps.api.src.core.exceptions import ConflictException, NotFoundException
from apps.api.src.database.models.platform_billing import (
    PlatformBillingAdjustment,
    PlatformPayment,
    PlatformRefund,
    PlatformSubscriptionAuditLog,
)
from apps.api.src.database.models.society import Society
from apps.api.src.database.models.subscription import (
    PlatformSubscriptionPlan,
    SocietySubscription,
    SubscriptionPlanEntitlement,
)
from apps.api.src.subscriptions.billing_api_schemas import (
    PaginatedResponse,
    PlanEntitlementItem,
    PlatformBillingAdjustmentCreate,
    PlatformBillingAdjustmentResponse,
    PlatformPaymentDetailResponse,
    PlatformPaymentListItemResponse,
    PlatformPlanCreateRequest,
    PlatformPlanUpdateRequest,
    PlatformRefundListItemResponse,
    PlatformSubscriptionListItemResponse,
    PlatformSubscriptionPlanResponse,
    SocietyAdvanceBalanceResponse,
)

logger = logging.getLogger("societysphere.subscriptions.billing_admin")


def _utc_now() -> datetime:
    """Return naive UTC datetime."""
    return datetime.now(UTC).replace(tzinfo=None)


class PlatformBillingAdminService:
    """Domain service managing platform-wide commercial billing catalog, transactions, and adjustments."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ==========================================================================
    # 1. Subscription Plan Catalog CRUD
    # ==========================================================================

    async def list_plans(
        self,
        include_archived: bool = False,
        is_active: bool | None = None,
    ) -> list[PlatformSubscriptionPlanResponse]:
        """List subscription plans with entitlements."""
        stmt = (
            select(PlatformSubscriptionPlan)
            .options(selectinload(PlatformSubscriptionPlan.entitlements))
            .order_by(PlatformSubscriptionPlan.monthly_price.asc())
        )
        if not include_archived:
            stmt = stmt.where(PlatformSubscriptionPlan.archived_at.is_(None))
        if is_active is not None:
            stmt = stmt.where(PlatformSubscriptionPlan.is_active == is_active)

        rows = (await self.session.execute(stmt)).scalars().all()
        return [self._plan_to_response(p) for p in rows]

    async def get_plan(self, plan_id: UUID) -> PlatformSubscriptionPlanResponse:
        """Retrieve single subscription plan by UUID with entitlements."""
        stmt = (
            select(PlatformSubscriptionPlan)
            .options(selectinload(PlatformSubscriptionPlan.entitlements))
            .where(PlatformSubscriptionPlan.id == plan_id)
        )
        plan = (await self.session.execute(stmt)).scalar_one_or_none()
        if not plan:
            raise NotFoundException(f"Subscription plan with ID '{plan_id}' not found.")
        return self._plan_to_response(plan)

    async def create_plan(
        self,
        payload: PlatformPlanCreateRequest,
        actor_id: UUID | None = None,
    ) -> PlatformSubscriptionPlanResponse:
        """Create a new subscription plan with entitlements."""
        # 1. Check plan_code uniqueness
        existing_stmt = select(PlatformSubscriptionPlan).where(
            PlatformSubscriptionPlan.plan_code == payload.plan_code
        )
        existing = (await self.session.execute(existing_stmt)).scalar_one_or_none()
        if existing:
            raise ConflictException(
                f"Subscription plan with code '{payload.plan_code}' already exists.",
                details={"plan_code": payload.plan_code},
            )

        now = _utc_now()
        plan_id = uuid4()
        created_entitlements = [
            SubscriptionPlanEntitlement(
                id=uuid4(),
                plan_id=plan_id,
                entitlement_key=ent.entitlement_key,
                entitlement_type=ent.entitlement_type,
                entitlement_value=ent.entitlement_value,
                created_at=now,
                updated_at=now,
            )
            for ent in payload.entitlements
        ]

        plan = PlatformSubscriptionPlan(
            id=plan_id,
            plan_code=payload.plan_code,
            display_name=payload.display_name,
            description=payload.description,
            monthly_price=float(payload.monthly_price),
            annual_price=float(payload.annual_price),
            currency_code=payload.currency_code,
            trial_days=payload.trial_days,
            is_active=payload.is_active,
            created_at=now,
            updated_at=now,
            entitlements=created_entitlements,
        )
        self.session.add(plan)
        await self.session.flush()

        logger.info(
            "AUDIT: Subscription plan created plan_code=%s plan_id=%s actor_id=%s",
            plan.plan_code,
            plan.id,
            actor_id,
        )

        return self._plan_to_response(plan)

    async def update_plan(
        self,
        plan_id: UUID,
        payload: PlatformPlanUpdateRequest,
        actor_id: UUID | None = None,
    ) -> PlatformSubscriptionPlanResponse:
        """Update mutable fields on an existing subscription plan."""
        stmt = (
            select(PlatformSubscriptionPlan)
            .options(selectinload(PlatformSubscriptionPlan.entitlements))
            .where(PlatformSubscriptionPlan.id == plan_id)
        )
        plan = (await self.session.execute(stmt)).scalar_one_or_none()
        if not plan:
            raise NotFoundException(f"Subscription plan with ID '{plan_id}' not found.")

        now = _utc_now()
        before_state: dict[str, Any] = {
            "display_name": plan.display_name,
            "monthly_price": str(plan.monthly_price),
            "annual_price": str(plan.annual_price),
            "is_active": plan.is_active,
        }

        if payload.display_name is not None:
            plan.display_name = payload.display_name
        if payload.description is not None:
            plan.description = payload.description
        if payload.monthly_price is not None:
            plan.monthly_price = float(payload.monthly_price)
        if payload.annual_price is not None:
            plan.annual_price = float(payload.annual_price)
        if payload.trial_days is not None:
            plan.trial_days = payload.trial_days
        if payload.is_active is not None:
            plan.is_active = payload.is_active

        plan.updated_at = now

        # Update entitlements if provided
        if payload.entitlements is not None:
            plan.entitlements.clear()
            await self.session.flush()
            for ent in payload.entitlements:
                plan.entitlements.append(
                    SubscriptionPlanEntitlement(
                        id=uuid4(),
                        plan_id=plan.id,
                        entitlement_key=ent.entitlement_key,
                        entitlement_type=ent.entitlement_type,
                        entitlement_value=ent.entitlement_value,
                        created_at=now,
                        updated_at=now,
                    )
                )

        after_state: dict[str, Any] = {
            "display_name": plan.display_name,
            "monthly_price": str(plan.monthly_price),
            "annual_price": str(plan.annual_price),
            "is_active": plan.is_active,
        }

        logger.info(
            "AUDIT: Subscription plan updated plan_id=%s actor_id=%s before=%s after=%s",
            plan.id,
            actor_id,
            before_state,
            after_state,
        )
        await self.session.flush()

        return self._plan_to_response(plan)

    async def archive_plan(
        self,
        plan_id: UUID,
        actor_id: UUID | None = None,
    ) -> PlatformSubscriptionPlanResponse:
        """Soft-archive a subscription plan so existing subscriptions remain valid."""
        stmt = (
            select(PlatformSubscriptionPlan)
            .options(selectinload(PlatformSubscriptionPlan.entitlements))
            .where(PlatformSubscriptionPlan.id == plan_id)
        )
        plan = (await self.session.execute(stmt)).scalar_one_or_none()
        if not plan:
            raise NotFoundException(f"Subscription plan with ID '{plan_id}' not found.")

        now = _utc_now()
        plan.is_active = False
        plan.archived_at = now
        plan.updated_at = now

        logger.info(
            "AUDIT: Subscription plan archived plan_id=%s actor_id=%s",
            plan.id,
            actor_id,
        )
        await self.session.flush()

        return self._plan_to_response(plan)

    def _plan_to_response(self, plan: PlatformSubscriptionPlan) -> PlatformSubscriptionPlanResponse:
        entitlements = [
            PlanEntitlementItem(
                id=e.id,
                entitlement_key=e.entitlement_key,
                entitlement_type=e.entitlement_type,
                entitlement_value=e.entitlement_value,
            )
            for e in (plan.entitlements or [])
        ]
        return PlatformSubscriptionPlanResponse(
            id=plan.id,
            plan_code=plan.plan_code,
            display_name=plan.display_name,
            description=plan.description,
            monthly_price=Decimal(str(plan.monthly_price)),
            annual_price=Decimal(str(plan.annual_price)),
            currency_code=plan.currency_code,
            trial_days=plan.trial_days,
            is_active=plan.is_active,
            created_at=plan.created_at,
            updated_at=plan.updated_at,
            archived_at=plan.archived_at,
            entitlements=entitlements,
        )

    # ==========================================================================
    # 2. Global Subscription Monitoring
    # ==========================================================================

    async def list_subscriptions(
        self,
        society_id: UUID | None = None,
        status: str | None = None,
        plan_code: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> PaginatedResponse[PlatformSubscriptionListItemResponse]:
        """Paginated global listing of society subscriptions."""
        base_query = (
            select(
                SocietySubscription,
                Society.legal_name,
                PlatformSubscriptionPlan.plan_code,
                PlatformSubscriptionPlan.display_name,
            )
            .join(Society, Society.id == SocietySubscription.society_id)
            .join(PlatformSubscriptionPlan, PlatformSubscriptionPlan.id == SocietySubscription.plan_id)
        )
        count_query = (
            select(func.count(SocietySubscription.id))
            .join(Society, Society.id == SocietySubscription.society_id)
            .join(PlatformSubscriptionPlan, PlatformSubscriptionPlan.id == SocietySubscription.plan_id)
        )

        if society_id:
            base_query = base_query.where(SocietySubscription.society_id == society_id)
            count_query = count_query.where(SocietySubscription.society_id == society_id)
        if status:
            target_status = status.strip().upper()
            base_query = base_query.where(SocietySubscription.status == target_status)
            count_query = count_query.where(SocietySubscription.status == target_status)
        if plan_code:
            target_code = plan_code.strip().upper()
            base_query = base_query.where(PlatformSubscriptionPlan.plan_code == target_code)
            count_query = count_query.where(PlatformSubscriptionPlan.plan_code == target_code)

        total = (await self.session.execute(count_query)).scalar() or 0
        pages = (total + page_size - 1) // page_size if total > 0 else 1

        offset = (page - 1) * page_size
        stmt = base_query.order_by(desc(SocietySubscription.created_at)).limit(page_size).offset(offset)
        rows = (await self.session.execute(stmt)).all()

        items = [
            PlatformSubscriptionListItemResponse(
                id=sub.id,
                society_id=sub.society_id,
                society_name=soc_name,
                plan_id=sub.plan_id,
                plan_code=p_code,
                plan_name=p_name,
                status=sub.status,
                billing_cycle=sub.billing_cycle,
                auto_renew=sub.auto_renew,
                starts_at=sub.starts_at,
                trial_ends_at=sub.trial_ends_at,
                current_period_start=sub.current_period_start,
                current_period_end=sub.current_period_end,
                next_billing_at=sub.next_billing_at,
                past_due_since=sub.past_due_since,
                suspended_at=sub.suspended_at,
                cancelled_at=sub.cancelled_at,
            )
            for sub, soc_name, p_code, p_name in rows
        ]

        return PaginatedResponse(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            pages=pages,
        )

    # ==========================================================================
    # 3. Global Payment & Refund Listing
    # ==========================================================================

    async def list_payments(
        self,
        society_id: UUID | None = None,
        invoice_id: UUID | None = None,
        status: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> PaginatedResponse[PlatformPaymentListItemResponse]:
        """Paginated listing of captured platform payment transactions."""
        count_stmt = select(func.count(PlatformPayment.id))
        stmt = select(PlatformPayment)

        if society_id:
            count_stmt = count_stmt.where(PlatformPayment.society_id == society_id)
            stmt = stmt.where(PlatformPayment.society_id == society_id)
        if invoice_id:
            count_stmt = count_stmt.where(PlatformPayment.invoice_id == invoice_id)
            stmt = stmt.where(PlatformPayment.invoice_id == invoice_id)
        if status:
            target_status = status.strip().upper()
            count_stmt = count_stmt.where(PlatformPayment.status == target_status)
            stmt = stmt.where(PlatformPayment.status == target_status)

        total = (await self.session.execute(count_stmt)).scalar() or 0
        pages = (total + page_size - 1) // page_size if total > 0 else 1

        offset = (page - 1) * page_size
        stmt = stmt.order_by(desc(PlatformPayment.captured_at)).limit(page_size).offset(offset)
        rows = (await self.session.execute(stmt)).scalars().all()

        items = [
            PlatformPaymentListItemResponse(
                id=p.id,
                society_id=p.society_id,
                invoice_id=p.invoice_id,
                gateway_provider=p.gateway_provider,
                gateway_payment_id=p.gateway_payment_id,
                payment_method=p.payment_method,
                amount=p.amount,
                refunded_amount=p.refunded_amount,
                currency_code=p.currency_code,
                status=p.status,
                reconciliation_status=p.reconciliation_status,
                captured_at=p.captured_at,
                is_settled=p.is_settled,
                settled_at=p.settled_at,
            )
            for p in rows
        ]

        return PaginatedResponse(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            pages=pages,
        )

    async def get_payment_detail(self, payment_id: UUID) -> PlatformPaymentDetailResponse:
        """Retrieve full details of a payment transaction including refunds."""
        stmt = (
            select(PlatformPayment)
            .options(selectinload(PlatformPayment.refunds))
            .where(PlatformPayment.id == payment_id)
        )
        payment = (await self.session.execute(stmt)).scalar_one_or_none()
        if not payment:
            raise NotFoundException(f"Payment with ID '{payment_id}' not found.")

        refund_items = [
            {
                "id": str(r.id),
                "gateway_refund_id": r.gateway_refund_id,
                "amount": str(r.amount),
                "reason": r.reason,
                "status": r.status,
                "created_at": r.created_at.isoformat(),
            }
            for r in (payment.refunds or [])
        ]

        return PlatformPaymentDetailResponse(
            id=payment.id,
            society_id=payment.society_id,
            invoice_id=payment.invoice_id,
            gateway_provider=payment.gateway_provider,
            gateway_payment_id=payment.gateway_payment_id,
            payment_method=payment.payment_method,
            amount=payment.amount,
            refunded_amount=payment.refunded_amount,
            currency_code=payment.currency_code,
            status=payment.status,
            reconciliation_status=payment.reconciliation_status,
            captured_at=payment.captured_at,
            is_settled=payment.is_settled,
            settled_at=payment.settled_at,
            card_network=payment.card_network,
            card_last4=payment.card_last4,
            upi_vpa=payment.upi_vpa,
            gateway_fee=payment.gateway_fee,
            gateway_tax=payment.gateway_tax,
            refunds=refund_items,
        )

    async def list_refunds(
        self,
        society_id: UUID | None = None,
        payment_id: UUID | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> PaginatedResponse[PlatformRefundListItemResponse]:
        """Paginated listing of outbound payment refunds."""
        count_stmt = select(func.count(PlatformRefund.id))
        stmt = select(PlatformRefund)

        if society_id:
            count_stmt = count_stmt.where(PlatformRefund.society_id == society_id)
            stmt = stmt.where(PlatformRefund.society_id == society_id)
        if payment_id:
            count_stmt = count_stmt.where(PlatformRefund.payment_id == payment_id)
            stmt = stmt.where(PlatformRefund.payment_id == payment_id)

        total = (await self.session.execute(count_stmt)).scalar() or 0
        pages = (total + page_size - 1) // page_size if total > 0 else 1

        offset = (page - 1) * page_size
        stmt = stmt.order_by(desc(PlatformRefund.created_at)).limit(page_size).offset(offset)
        rows = (await self.session.execute(stmt)).scalars().all()

        items = [
            PlatformRefundListItemResponse(
                id=r.id,
                payment_id=r.payment_id,
                society_id=r.society_id,
                gateway_provider=r.gateway_provider,
                gateway_refund_id=r.gateway_refund_id,
                amount=r.amount,
                currency_code=r.currency_code,
                reason=r.reason,
                status=r.status,
                created_at=r.created_at,
            )
            for r in rows
        ]

        return PaginatedResponse(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            pages=pages,
        )

    # ==========================================================================
    # 4. Manual Billing Adjustments & Advance Balances
    # ==========================================================================

    async def list_adjustments(
        self,
        society_id: UUID,
        page: int = 1,
        page_size: int = 20,
    ) -> PaginatedResponse[PlatformBillingAdjustmentResponse]:
        """List billing adjustments for a society."""
        count_stmt = select(func.count(PlatformBillingAdjustment.id)).where(
            PlatformBillingAdjustment.society_id == society_id
        )
        total = (await self.session.execute(count_stmt)).scalar() or 0
        pages = (total + page_size - 1) // page_size if total > 0 else 1

        offset = (page - 1) * page_size
        stmt = (
            select(PlatformBillingAdjustment)
            .where(PlatformBillingAdjustment.society_id == society_id)
            .order_by(desc(PlatformBillingAdjustment.applied_at))
            .limit(page_size)
            .offset(offset)
        )
        rows = (await self.session.execute(stmt)).scalars().all()

        items = [
            PlatformBillingAdjustmentResponse(
                id=a.id,
                society_id=a.society_id,
                invoice_id=a.invoice_id,
                credit_note_id=a.credit_note_id,
                adjustment_type=a.adjustment_type,
                amount=a.amount,
                currency_code=a.currency_code,
                idempotency_key=a.idempotency_key,
                reason=a.reason,
                applied_at=a.applied_at,
                created_by=a.created_by,
                created_at=a.created_at,
            )
            for a in rows
        ]

        return PaginatedResponse(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            pages=pages,
        )

    async def create_adjustment(
        self,
        society_id: UUID,
        payload: PlatformBillingAdjustmentCreate,
        actor_id: UUID | None = None,
    ) -> PlatformBillingAdjustmentResponse:
        """Create a manual billing adjustment (goodwill waiver, manual credit, etc.)."""
        # 1. Verify society exists
        soc_stmt = select(Society).where(Society.id == society_id)
        soc = (await self.session.execute(soc_stmt)).scalar_one_or_none()
        if not soc:
            raise NotFoundException(f"Society with ID '{society_id}' not found.")

        # 2. Idempotency check
        if payload.idempotency_key:
            idem_stmt = select(PlatformBillingAdjustment).where(
                PlatformBillingAdjustment.idempotency_key == payload.idempotency_key
            )
            existing_adj = (await self.session.execute(idem_stmt)).scalar_one_or_none()
            if existing_adj:
                logger.info("Idempotent replay for billing adjustment key '%s'", payload.idempotency_key)
                return PlatformBillingAdjustmentResponse.model_validate(existing_adj)

        now = _utc_now()
        adj = PlatformBillingAdjustment(
            id=uuid4(),
            society_id=society_id,
            invoice_id=payload.invoice_id,
            adjustment_type=payload.adjustment_type,
            amount=payload.amount,
            currency_code="INR",
            idempotency_key=payload.idempotency_key,
            reason=payload.reason,
            applied_at=now,
            created_by=actor_id,
            created_at=now,
        )
        self.session.add(adj)

        # Audit log
        audit = PlatformSubscriptionAuditLog(
            id=uuid4(),
            society_id=society_id,
            entity_type="BILLING_ADJUSTMENT",
            entity_id=adj.id,
            action="CREATE_ADJUSTMENT",
            actor_type="USER",
            actor_id=actor_id,
            before_state=None,
            after_state={
                "adjustment_type": adj.adjustment_type,
                "amount": str(adj.amount),
                "reason": adj.reason,
            },
            created_at=now,
        )
        self.session.add(audit)
        await self.session.flush()

        return PlatformBillingAdjustmentResponse.model_validate(adj)

    async def get_society_advance_balance(self, society_id: UUID) -> SocietyAdvanceBalanceResponse:
        """Aggregate total advance balance and credits ledger for a society."""
        stmt = select(
            func.coalesce(
                func.sum(
                    case((PlatformBillingAdjustment.amount > 0, PlatformBillingAdjustment.amount), else_=0)
                ),
                0,
            ).label("total_granted"),
            func.coalesce(
                func.sum(
                    case(
                        (PlatformBillingAdjustment.amount < 0, func.abs(PlatformBillingAdjustment.amount)), else_=0
                    )
                ),
                0,
            ).label("total_utilized"),
            func.coalesce(func.sum(PlatformBillingAdjustment.amount), 0).label("balance"),
        ).where(PlatformBillingAdjustment.society_id == society_id)

        res = (await self.session.execute(stmt)).one()
        granted = Decimal(str(res.total_granted))
        utilized = Decimal(str(res.total_utilized))
        balance = Decimal(str(res.balance))

        return SocietyAdvanceBalanceResponse(
            society_id=society_id,
            currency_code="INR",
            current_balance=max(balance, Decimal("0.00")),
            total_credits_granted=granted,
            total_credits_utilized=utilized,
        )
