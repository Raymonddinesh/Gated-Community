"""Phase 21E.6 — Automated Renewal Invoicing Service.

Generates statutory commercial invoices for renewing SaaS subscriptions:
- Reuses PlatformInvoiceService, InvoiceNumberingService, TaxSnapshotService, GSTTaxEngine.
- Strictly idempotent: checks for existing non-VOID invoices per (subscription_id, period_start, period_end) or idempotency_key.
- Reconciles existing finalized invoices without duplicate creation.
- Preserves statutory GST tax snapshots and legal sequence numbering (SS-2627-XXXXX).
- Never calculates tax independently in the automation layer.
"""

import logging
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from apps.api.src.database.models.platform_billing import (
    PlatformInvoice,
)
from apps.api.src.database.models.society import Society
from apps.api.src.database.models.subscription import (
    PlatformSubscriptionPlan,
    SocietySubscription,
)
from apps.api.src.subscriptions.billing_period_service import BillingPeriodService
from apps.api.src.subscriptions.invoicing.schemas import (
    PlatformInvoiceCreateDraft,
    PlatformInvoiceItemCreate,
    PlatformInvoiceResponse,
)
from apps.api.src.subscriptions.invoicing.service import PlatformInvoiceService

logger = logging.getLogger("societysphere.subscriptions.automation.renewal")


def _utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class AutomatedRenewalInvoicingService:
    """Service managing automated statutory renewal invoice generation for subscription periods."""

    def __init__(
        self,
        invoice_service: PlatformInvoiceService | None = None,
    ) -> None:
        self.invoice_service = invoice_service or PlatformInvoiceService()

    async def get_existing_renewal_invoice(
        self,
        session: AsyncSession,
        subscription_id: UUID,
        period_start: datetime,
        period_end: datetime,
        idempotency_key: str | None = None,
    ) -> PlatformInvoice | None:
        """Query existing non-VOID invoice matching subscription and period or idempotency key."""
        # 1. Check by idempotency key if provided
        if idempotency_key:
            stmt_key = (
                select(PlatformInvoice)
                .options(selectinload(PlatformInvoice.items))
                .where(
                    PlatformInvoice.idempotency_key == idempotency_key,
                    PlatformInvoice.status != "VOID",
                )
            )
            res_key = await session.execute(stmt_key)
            inv = res_key.scalar_one_or_none()
            if inv:
                return inv

        # 2. Check by subscription and exact period
        stmt_period = (
            select(PlatformInvoice)
            .options(selectinload(PlatformInvoice.items))
            .where(
                PlatformInvoice.subscription_id == subscription_id,
                PlatformInvoice.period_start == period_start,
                PlatformInvoice.period_end == period_end,
                PlatformInvoice.status != "VOID",
            )
        )
        res_period = await session.execute(stmt_period)
        return res_period.scalar_one_or_none()

    async def generate_renewal_invoice(
        self,
        session: AsyncSession,
        subscription: SocietySubscription,
        society: Society,
        period_start: datetime,
        period_end: datetime,
        idempotency_key: str | None = None,
        due_days: int = 7,
    ) -> PlatformInvoiceResponse:
        """Idempotently generate and finalize a renewal invoice for a subscription period.

        Guarantees:
        1. Checks database for existing non-VOID invoice.
        2. If already finalized (ISSUED, PAID, etc.), returns response immediately.
        3. If existing DRAFT, finalizes it atomically.
        4. If not found, creates draft with base plan pricing and SAC 998313,
           runs server-authoritative GSTTaxEngine, persists immutable TaxSnapshot,
           and allocates legal financial-year invoice number.
        """
        # Ensure subscription plan is loaded
        plan: PlatformSubscriptionPlan | None = subscription.plan
        if not plan:
            plan = await session.get(PlatformSubscriptionPlan, subscription.plan_id)
            if not plan:
                raise ValueError(f"Subscription plan '{subscription.plan_id}' does not exist.")

        # 1. Idempotency Check
        existing_invoice = await self.get_existing_renewal_invoice(
            session=session,
            subscription_id=subscription.id,
            period_start=period_start,
            period_end=period_end,
            idempotency_key=idempotency_key,
        )

        if existing_invoice:
            if existing_invoice.status in ("ISSUED", "PAID", "PARTIALLY_PAID", "OVERDUE"):
                logger.info(
                    "Reusing existing finalized invoice %s (%s) for subscription %s period %s to %s",
                    existing_invoice.invoice_number,
                    existing_invoice.id,
                    subscription.id,
                    period_start,
                    period_end,
                )
                return self.invoice_service._to_response(existing_invoice)
            elif existing_invoice.status == "DRAFT":
                logger.info(
                    "Finalizing existing DRAFT invoice %s for subscription %s",
                    existing_invoice.id,
                    subscription.id,
                )
                return await self.invoice_service.finalize_invoice(
                    session=session,
                    invoice_id=existing_invoice.id,
                    society_id=society.id,
                    actor_type="SYSTEM",
                )

        # 2. Derive Pricing and Cycle
        cycle = subscription.billing_cycle.upper()
        if cycle == "MONTHLY":
            unit_price = Decimal(str(plan.monthly_price))
            cycle_label = "Monthly"
        else:
            unit_price = Decimal(str(plan.annual_price))
            cycle_label = "Annual"

        # 3. Derive Due Date (7 days from period start, evaluated in IST)
        ist_period_start = BillingPeriodService.to_ist(period_start)
        due_date = ist_period_start.date() + timedelta(days=due_days)

        # Period label for invoice description
        ist_start_fmt = ist_period_start.strftime("%d %b %Y")
        ist_end_fmt = BillingPeriodService.to_ist(period_end).strftime("%d %b %Y")
        description = (
            f"SocietySphere SaaS Subscription — {plan.display_name} "
            f"({cycle_label}: {ist_start_fmt} – {ist_end_fmt})"
        )

        customer_gstin = getattr(society, "tax_id", None) or getattr(society, "gstin", None)
        place_of_supply = getattr(society, "state", None)

        payload = PlatformInvoiceCreateDraft(
            society_id=society.id,
            subscription_id=subscription.id,
            billing_cycle=cycle,
            period_start=period_start,
            period_end=period_end,
            due_date=due_date,
            customer_gstin=customer_gstin,
            place_of_supply=place_of_supply,
            prorated_credit=Decimal("0.00"),
            idempotency_key=idempotency_key,
            items=[
                PlatformInvoiceItemCreate(
                    item_type="BASE_PLAN",
                    description=description,
                    sac_code="998313",
                    quantity=Decimal("1.0000"),
                    unit_price=unit_price,
                    discount_amount=Decimal("0.00"),
                )
            ],
        )

        # 4. Create Draft Invoice
        draft_response = await self.invoice_service.create_draft_invoice(
            session=session,
            payload=payload,
            actor_type="SYSTEM",
        )

        # 5. Finalize Invoice Atomically
        finalized_response = await self.invoice_service.finalize_invoice(
            session=session,
            invoice_id=draft_response.id,
            society_id=society.id,
            actor_type="SYSTEM",
        )

        logger.info(
            "Automated renewal invoice %s (%s) generated and finalized for society %s (grand_total=%s)",
            finalized_response.invoice_number,
            finalized_response.id,
            society.id,
            finalized_response.grand_total,
        )
        return finalized_response
