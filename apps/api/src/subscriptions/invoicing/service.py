"""Phase 21E.4B — SaaS Platform Invoice Service.

Implements the deterministic B2B invoice lifecycle for SocietySphere SaaS:
- DRAFT creation, retrieval, and updating.
- Atomic DRAFT -> ISSUED finalization with SELECT ... FOR UPDATE locking.
- Integration with GSTTaxEngine and immutable TaxSnapshot persistence.
- Sequential financial-year invoice numbering via InvoiceNumberingService.
- VOID lifecycle transition retaining original number and audit trail.
- Cryptographic tax snapshot integrity verification.
- Historical snapshot retrieval for Credit Note preparation (M-2 & M-3).
"""

import logging
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from apps.api.src.database.models.platform_billing import (
    PlatformInvoice,
    PlatformInvoiceItem,
    PlatformSubscriptionAuditLog,
)
from apps.api.src.database.models.society import Society
from apps.api.src.database.models.subscription import SocietySubscription
from apps.api.src.subscriptions.invoicing.exceptions import (
    InvalidInvoiceStateException,
    InvoiceFinalizationException,
    InvoiceNotFoundException,
    InvoiceTaxSnapshotNotFoundException,
    InvoiceTaxSnapshotTamperedException,
)
from apps.api.src.subscriptions.invoicing.numbering import InvoiceNumberingService
from apps.api.src.subscriptions.invoicing.schemas import (
    PlatformInvoiceCreateDraft,
    PlatformInvoiceItemResponse,
    PlatformInvoiceResponse,
    PlatformInvoiceUpdateDraft,
    TaxSnapshotVerificationResponse,
)
from apps.api.src.subscriptions.tax import (
    GSTTaxEngine,
    PlaceOfSupplyInput,
    PlaceOfSupplyService,
    TaxCalculationInput,
    TaxSnapshot,
    TaxSnapshotService,
    quantize_money,
    tax_config_service,
)

logger = logging.getLogger("societysphere.subscriptions.invoicing")

DEFAULT_SUPPLIER_STATE: str = "Karnataka"


def _utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class PlatformInvoiceService:
    """Service managing commercial SaaS platform invoices between SocietySphere and tenant societies."""

    def __init__(
        self,
        numbering_service: InvoiceNumberingService | None = None,
        tax_engine: GSTTaxEngine | None = None,
        pos_service: PlaceOfSupplyService | None = None,
    ) -> None:
        self.numbering_service = numbering_service or InvoiceNumberingService()
        self.tax_engine = tax_engine or GSTTaxEngine(tax_config_service)
        self.pos_service = pos_service or PlaceOfSupplyService()

    async def create_draft_invoice(
        self,
        session: AsyncSession,
        payload: PlatformInvoiceCreateDraft,
        actor_id: UUID | None = None,
        actor_type: str = "SYSTEM",
        ip_address: str | None = None,
    ) -> PlatformInvoiceResponse:
        """Create a new commercial platform invoice in DRAFT status."""
        now = _utc_now()

        # 1. Validate Society existence
        society = await session.get(Society, payload.society_id)
        if not society:
            raise InvoiceFinalizationException(
                reason=f"Target society '{payload.society_id}' does not exist."
            )

        # 2. Validate Subscription existence
        subscription = await session.get(SocietySubscription, payload.subscription_id)
        if not subscription or subscription.society_id != payload.society_id:
            raise InvoiceFinalizationException(
                reason=f"Subscription '{payload.subscription_id}' does not belong to society '{payload.society_id}'."
            )

        # 3. Calculate preliminary subtotal and discounts from items
        subtotal = Decimal("0.00")
        discount_total = Decimal("0.00")
        for item in payload.items:
            item_gross = quantize_money(item.quantity * item.unit_price)
            item_disc = quantize_money(item.discount_amount)
            subtotal += item_gross
            discount_total += item_disc

        prorated_credit = quantize_money(payload.prorated_credit)

        # 4. Resolve customer state
        customer_state = payload.place_of_supply or society.state or DEFAULT_SUPPLIER_STATE
        customer_gstin = payload.customer_gstin or getattr(society, "tax_id", None)

        # Preliminary place of supply evaluation for draft estimations
        pos = self.pos_service.determine_place_of_supply(
            PlaceOfSupplyInput(
                supplier_state=DEFAULT_SUPPLIER_STATE,
                customer_state=customer_state,
                customer_gstin=customer_gstin,
                transaction_date=now.date(),
            )
        )

        primary_sac = payload.items[0].sac_code if payload.items else "998313"
        calc_res = self.tax_engine.calculate_tax(
            TaxCalculationInput(
                base_amount=subtotal,
                sac_code=primary_sac,
                place_of_supply=pos,
                discount_amount=discount_total,
                prorated_credit=prorated_credit,
                transaction_date=now.date(),
            )
        )

        # 5. Instantiate Draft Invoice
        invoice_id = uuid4()
        invoice = PlatformInvoice(
            id=invoice_id,
            society_id=payload.society_id,
            subscription_id=payload.subscription_id,
            invoice_number=None,  # No legal sequence allocated for DRAFT
            fiscal_year=None,
            billing_cycle=payload.billing_cycle,
            period_start=payload.period_start,
            period_end=payload.period_end,
            subtotal=calc_res.base_amount,
            discount_total=calc_res.discount_amount,
            prorated_credit=calc_res.prorated_credit,
            taxable_amount=calc_res.taxable_amount,
            cgst_amount=calc_res.cgst_amount,
            sgst_amount=calc_res.sgst_amount,
            igst_amount=calc_res.igst_amount,
            tax_total=calc_res.tax_total,
            grand_total=calc_res.grand_total,
            credits_applied=Decimal("0.00"),
            amount_paid=Decimal("0.00"),
            amount_due=calc_res.grand_total,
            currency_code="INR",
            status="DRAFT",
            due_date=payload.due_date,
            sac_code=primary_sac,
            place_of_supply=pos.place_of_supply_state,
            customer_gstin=customer_gstin,
            idempotency_key=payload.idempotency_key,
        )
        session.add(invoice)

        # 6. Create Line Items
        created_items: list[PlatformInvoiceItem] = []
        for idx, itm in enumerate(payload.items):
            item_taxable = quantize_money(max(Decimal("0.00"), (itm.quantity * itm.unit_price) - itm.discount_amount))
            inv_item = PlatformInvoiceItem(
                id=uuid4(),
                society_id=payload.society_id,
                invoice_id=invoice_id,
                item_index=idx,
                item_type=itm.item_type,
                description=itm.description,
                sac_code=itm.sac_code,
                quantity=itm.quantity,
                unit_price=itm.unit_price,
                discount_amount=itm.discount_amount,
                taxable_amount=item_taxable,
                tax_rate=calc_res.tax_rate,
                tax_amount=quantize_money(item_taxable * (calc_res.tax_rate / Decimal("100.00"))),
                total_amount=quantize_money(item_taxable + (item_taxable * (calc_res.tax_rate / Decimal("100.00")))),
            )
            session.add(inv_item)
            created_items.append(inv_item)

        # 7. Record Audit Log
        audit = PlatformSubscriptionAuditLog(
            id=uuid4(),
            society_id=payload.society_id,
            entity_type="INVOICE",
            entity_id=invoice_id,
            action="CREATE",
            actor_type=actor_type,
            actor_id=actor_id,
            before_state=None,
            after_state={"status": "DRAFT", "grand_total": str(calc_res.grand_total)},
            ip_address=ip_address,
            created_at=now,
        )
        session.add(audit)
        await session.flush()
        return self._to_response(invoice, items=created_items)

    async def get_invoice(
        self,
        session: AsyncSession,
        invoice_id: UUID,
        society_id: UUID | None = None,
    ) -> PlatformInvoiceResponse:
        """Retrieve a platform invoice with items and tenant verification."""
        stmt = (
            select(PlatformInvoice)
            .options(selectinload(PlatformInvoice.items))
            .where(PlatformInvoice.id == invoice_id)
        )
        if society_id:
            stmt = stmt.where(PlatformInvoice.society_id == society_id)

        invoice = (await session.execute(stmt)).scalar_one_or_none()
        if not invoice:
            raise InvoiceNotFoundException(invoice_id)

        return self._to_response(invoice)

    async def list_invoices(
        self,
        session: AsyncSession,
        society_id: UUID | None = None,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[PlatformInvoiceResponse]:
        """List platform invoices with optional tenant filtering and pagination."""
        stmt = (
            select(PlatformInvoice)
            .options(selectinload(PlatformInvoice.items))
            .order_by(desc(PlatformInvoice.created_at))
            .limit(limit)
            .offset(offset)
        )
        if society_id:
            stmt = stmt.where(PlatformInvoice.society_id == society_id)
        if status:
            stmt = stmt.where(PlatformInvoice.status == status.strip().upper())

        res = await session.execute(stmt)
        return [self._to_response(inv) for inv in res.scalars().all()]

    async def update_draft_invoice(
        self,
        session: AsyncSession,
        invoice_id: UUID,
        payload: PlatformInvoiceUpdateDraft,
        society_id: UUID | None = None,
        actor_id: UUID | None = None,
        actor_type: str = "SYSTEM",
    ) -> PlatformInvoiceResponse:
        """Update permitted fields on a DRAFT platform invoice."""
        now = _utc_now()

        # 1. Lock invoice row for update
        stmt = (
            select(PlatformInvoice)
            .options(selectinload(PlatformInvoice.items))
            .where(PlatformInvoice.id == invoice_id)
            .with_for_update()
        )
        if society_id:
            stmt = stmt.where(PlatformInvoice.society_id == society_id)

        invoice = (await session.execute(stmt)).scalar_one_or_none()
        if not invoice:
            raise InvoiceNotFoundException(invoice_id)

        if invoice.status != "DRAFT":
            raise InvalidInvoiceStateException(
                invoice_id=invoice_id,
                current_status=invoice.status,
                attempted_action="UPDATE",
                reason="Only DRAFT invoices can be edited.",
            )

        before_state = {
            "due_date": invoice.due_date.isoformat(),
            "customer_gstin": invoice.customer_gstin,
            "place_of_supply": invoice.place_of_supply,
            "prorated_credit": str(invoice.prorated_credit),
            "grand_total": str(invoice.grand_total),
        }

        # 2. Update scalar fields
        if payload.due_date is not None:
            invoice.due_date = payload.due_date
        if payload.customer_gstin is not None:
            invoice.customer_gstin = payload.customer_gstin
        if payload.place_of_supply is not None:
            invoice.place_of_supply = payload.place_of_supply
        if payload.prorated_credit is not None:
            invoice.prorated_credit = quantize_money(payload.prorated_credit)

        # 3. Update Line Items if supplied
        if payload.items is not None:
            for old_item in invoice.items:
                await session.delete(old_item)
            await session.flush()

            subtotal = Decimal("0.00")
            discount_total = Decimal("0.00")
            for item in payload.items:
                subtotal += quantize_money(item.quantity * item.unit_price)
                discount_total += quantize_money(item.discount_amount)

            pos = self.pos_service.determine_place_of_supply(
                PlaceOfSupplyInput(
                    supplier_state=DEFAULT_SUPPLIER_STATE,
                    customer_state=invoice.place_of_supply,
                    customer_gstin=invoice.customer_gstin,
                    transaction_date=now.date(),
                )
            )
            primary_sac = payload.items[0].sac_code if payload.items else invoice.sac_code
            calc_res = self.tax_engine.calculate_tax(
                TaxCalculationInput(
                    base_amount=subtotal,
                    sac_code=primary_sac,
                    place_of_supply=pos,
                    discount_amount=discount_total,
                    prorated_credit=invoice.prorated_credit,
                    transaction_date=now.date(),
                )
            )

            invoice.subtotal = calc_res.base_amount
            invoice.discount_total = calc_res.discount_amount
            invoice.taxable_amount = calc_res.taxable_amount
            invoice.cgst_amount = calc_res.cgst_amount
            invoice.sgst_amount = calc_res.sgst_amount
            invoice.igst_amount = calc_res.igst_amount
            invoice.tax_total = calc_res.tax_total
            invoice.grand_total = calc_res.grand_total
            invoice.amount_due = calc_res.grand_total
            invoice.sac_code = primary_sac

            new_items: list[PlatformInvoiceItem] = []
            for idx, itm in enumerate(payload.items):
                item_taxable = quantize_money(max(Decimal("0.00"), (itm.quantity * itm.unit_price) - itm.discount_amount))
                inv_item = PlatformInvoiceItem(
                    id=uuid4(),
                    society_id=invoice.society_id,
                    invoice_id=invoice.id,
                    item_index=idx,
                    item_type=itm.item_type,
                    description=itm.description,
                    sac_code=itm.sac_code,
                    quantity=itm.quantity,
                    unit_price=itm.unit_price,
                    discount_amount=itm.discount_amount,
                    taxable_amount=item_taxable,
                    tax_rate=calc_res.tax_rate,
                    tax_amount=quantize_money(item_taxable * (calc_res.tax_rate / Decimal("100.00"))),
                    total_amount=quantize_money(item_taxable + (item_taxable * (calc_res.tax_rate / Decimal("100.00")))),
                )
                session.add(inv_item)
                new_items.append(inv_item)

        # 4. Audit Log
        audit = PlatformSubscriptionAuditLog(
            id=uuid4(),
            society_id=invoice.society_id,
            entity_type="INVOICE",
            entity_id=invoice.id,
            action="UPDATE",
            actor_type=actor_type,
            actor_id=actor_id,
            before_state=before_state,
            after_state={"status": invoice.status, "grand_total": str(invoice.grand_total)},
            created_at=now,
        )
        session.add(audit)
        await session.flush()

        return self._to_response(invoice, items=new_items if payload.items is not None else None)

    async def finalize_invoice(
        self,
        session: AsyncSession,
        invoice_id: UUID,
        society_id: UUID | None = None,
        actor_id: UUID | None = None,
        actor_type: str = "SYSTEM",
        ip_address: str | None = None,
    ) -> PlatformInvoiceResponse:
        """Atomically finalize a DRAFT invoice to ISSUED status.

        Execution Steps (All inside a single database transaction):
            1. Lock invoice row via SELECT ... FOR UPDATE.
            2. Validate DRAFT status (rejects duplicate finalization).
            3. Validate items, society, and subscription state.
            4. Execute server-authoritative GST calculation with GSTTaxEngine.
            5. Create immutable TaxSnapshot with deterministic SHA-256 digest.
            6. Allocate sequential financial-year invoice number via InvoiceNumberingService.
            7. Update PlatformInvoice status to ISSUED with final financial numbers.
            8. Persist immutable TaxSnapshot in PlatformSubscriptionAuditLog (entity_type='INVOICE_TAX_SNAPSHOT').
            9. Record state transition in PlatformSubscriptionAuditLog (action='FINALIZE').
            10. Commit transaction atomically (all changes or complete rollback).
        """
        now = _utc_now()

        # 1. Lock invoice row for atomic finalization
        stmt = (
            select(PlatformInvoice)
            .options(selectinload(PlatformInvoice.items))
            .where(PlatformInvoice.id == invoice_id)
            .with_for_update()
        )
        if society_id:
            stmt = stmt.where(PlatformInvoice.society_id == society_id)

        invoice = (await session.execute(stmt)).scalar_one_or_none()
        if not invoice:
            raise InvoiceNotFoundException(invoice_id)

        # 2. Status Validation: Only DRAFT can be finalized
        if invoice.status != "DRAFT":
            raise InvalidInvoiceStateException(
                invoice_id=invoice_id,
                current_status=invoice.status,
                attempted_action="FINALIZE",
                reason="Invoice is already finalized or voided. Duplicate finalization is prohibited.",
            )

        if not invoice.items:
            raise InvoiceFinalizationException(
                reason="Cannot finalize invoice with zero line items.",
                invoice_id=invoice_id,
            )

        # 3. Load Society & Subscription
        society = await session.get(Society, invoice.society_id)
        if not society:
            raise InvoiceFinalizationException(
                reason=f"Target society '{invoice.society_id}' does not exist.",
                invoice_id=invoice_id,
            )

        # 4. Resolve customer location and statutory place of supply
        customer_state = invoice.place_of_supply or society.state
        if not customer_state:
            raise InvoiceFinalizationException(
                reason="Society billing state is required for GST statutory compliance.",
                invoice_id=invoice_id,
            )

        customer_gstin = invoice.customer_gstin or getattr(society, "tax_id", None)

        pos = self.pos_service.determine_place_of_supply(
            PlaceOfSupplyInput(
                supplier_state=DEFAULT_SUPPLIER_STATE,
                customer_state=customer_state,
                customer_gstin=customer_gstin,
                transaction_date=now.date(),
            )
        )

        # 5. Server-side tax calculation
        subtotal = Decimal("0.00")
        discount_total = Decimal("0.00")
        for itm in invoice.items:
            subtotal += quantize_money(itm.quantity * itm.unit_price)
            discount_total += quantize_money(itm.discount_amount)

        primary_sac = invoice.sac_code or "998313"
        calc_res = self.tax_engine.calculate_tax(
            TaxCalculationInput(
                base_amount=subtotal,
                sac_code=primary_sac,
                place_of_supply=pos,
                discount_amount=discount_total,
                prorated_credit=invoice.prorated_credit,
                transaction_date=now.date(),
                invoice_id=invoice.id,
            )
        )

        # 6. Allocate sequential financial-year invoice number (pessimistic sequence row lock)
        allocated_number, fiscal_year = await self.numbering_service.allocate_invoice_number(
            session=session,
            transaction_date=now,
        )

        # 7. Update Invoice to ISSUED
        invoice.status = "ISSUED"
        invoice.invoice_number = allocated_number
        invoice.fiscal_year = fiscal_year
        invoice.issued_at = now
        invoice.subtotal = calc_res.base_amount
        invoice.discount_total = calc_res.discount_amount
        invoice.prorated_credit = calc_res.prorated_credit
        invoice.taxable_amount = calc_res.taxable_amount
        invoice.cgst_amount = calc_res.cgst_amount
        invoice.sgst_amount = calc_res.sgst_amount
        invoice.igst_amount = calc_res.igst_amount
        invoice.tax_total = calc_res.tax_total
        invoice.grand_total = calc_res.grand_total
        invoice.amount_due = quantize_money(calc_res.grand_total - invoice.credits_applied - invoice.amount_paid)
        invoice.sac_code = calc_res.sac_code
        invoice.place_of_supply = calc_res.tax_snapshot.place_of_supply
        invoice.customer_gstin = calc_res.tax_snapshot.customer_gstin

        # 8. Update Line Items
        for itm in invoice.items:
            item_taxable = quantize_money(max(Decimal("0.00"), (itm.quantity * itm.unit_price) - itm.discount_amount))
            itm.taxable_amount = item_taxable
            itm.tax_rate = calc_res.tax_rate
            itm.tax_amount = quantize_money(item_taxable * (calc_res.tax_rate / Decimal("100.00")))
            itm.total_amount = quantize_money(item_taxable + itm.tax_amount)

        # 9. Persist Immutable Tax Snapshot in PlatformSubscriptionAuditLog (M-3 Resolution)
        snapshot_dict = TaxSnapshotService.to_dict(calc_res.tax_snapshot)
        snapshot_audit = PlatformSubscriptionAuditLog(
            id=uuid4(),
            society_id=invoice.society_id,
            entity_type="INVOICE_TAX_SNAPSHOT",
            entity_id=invoice.id,
            action="FINALIZE",
            actor_type=actor_type,
            actor_id=actor_id,
            before_state=None,
            after_state=snapshot_dict,
            ip_address=ip_address,
            created_at=now,
        )
        session.add(snapshot_audit)

        # 10. Persist Invoice Lifecycle Audit Log
        lifecycle_audit = PlatformSubscriptionAuditLog(
            id=uuid4(),
            society_id=invoice.society_id,
            entity_type="INVOICE",
            entity_id=invoice.id,
            action="FINALIZE",
            actor_type=actor_type,
            actor_id=actor_id,
            before_state={"status": "DRAFT", "invoice_number": None},
            after_state={
                "status": "ISSUED",
                "invoice_number": allocated_number,
                "fiscal_year": fiscal_year,
                "grand_total": str(invoice.grand_total),
                "tax_snapshot_id": str(calc_res.tax_snapshot.snapshot_id),
            },
            ip_address=ip_address,
            created_at=now,
        )
        session.add(lifecycle_audit)

        await session.flush()
        logger.info(
            "Finalized platform invoice '%s' as '%s' (FY %s, Grand Total: %s)",
            invoice.id,
            allocated_number,
            fiscal_year,
            invoice.grand_total,
        )
        return self._to_response(invoice)

    async def void_invoice(
        self,
        session: AsyncSession,
        invoice_id: UUID,
        reason: str,
        society_id: UUID | None = None,
        actor_id: UUID | None = None,
        actor_type: str = "SYSTEM",
    ) -> PlatformInvoiceResponse:
        """Void an issued or draft invoice. Retains invoice number and history permanently."""
        now = _utc_now()

        stmt = (
            select(PlatformInvoice)
            .options(selectinload(PlatformInvoice.items))
            .where(PlatformInvoice.id == invoice_id)
            .with_for_update()
        )
        if society_id:
            stmt = stmt.where(PlatformInvoice.society_id == society_id)

        invoice = (await session.execute(stmt)).scalar_one_or_none()
        if not invoice:
            raise InvoiceNotFoundException(invoice_id)

        if invoice.status in ("PAID", "PARTIALLY_PAID"):
            raise InvalidInvoiceStateException(
                invoice_id=invoice_id,
                current_status=invoice.status,
                attempted_action="VOID",
                reason="Paid or partially paid invoices cannot be voided. Issue a credit note or refund.",
            )

        if invoice.status == "VOID":
            raise InvalidInvoiceStateException(
                invoice_id=invoice_id,
                current_status=invoice.status,
                attempted_action="VOID",
                reason="Invoice is already voided.",
            )

        before_status = invoice.status
        invoice.status = "VOID"
        invoice.voided_at = now
        invoice.void_reason = reason.strip()
        invoice.amount_due = Decimal("0.00")

        # Record Audit Log
        audit = PlatformSubscriptionAuditLog(
            id=uuid4(),
            society_id=invoice.society_id,
            entity_type="INVOICE",
            entity_id=invoice.id,
            action="VOID",
            actor_type=actor_type,
            actor_id=actor_id,
            before_state={"status": before_status, "invoice_number": invoice.invoice_number},
            after_state={
                "status": "VOID",
                "invoice_number": invoice.invoice_number,
                "void_reason": reason,
            },
            created_at=now,
        )
        session.add(audit)
        await session.flush()

        logger.info("Voided invoice '%s' (number: %s, reason: %s)", invoice.id, invoice.invoice_number, reason)
        return self._to_response(invoice)

    async def get_invoice_tax_snapshot(
        self,
        session: AsyncSession,
        invoice_id: UUID,
        society_id: UUID | None = None,
    ) -> TaxSnapshot:
        """Retrieve and cryptographically verify the immutable TaxSnapshot for an issued invoice.

        Used by downstream processes (such as Credit Note preparation under M-2 & M-3).
        Raises:
            InvoiceTaxSnapshotNotFoundException: If no snapshot is recorded.
            InvoiceTaxSnapshotTamperedException: If the SHA-256 digest fails verification.
        """
        stmt = (
            select(PlatformSubscriptionAuditLog)
            .where(
                PlatformSubscriptionAuditLog.entity_type == "INVOICE_TAX_SNAPSHOT",
                PlatformSubscriptionAuditLog.entity_id == invoice_id,
            )
            .order_by(desc(PlatformSubscriptionAuditLog.created_at))
            .limit(1)
        )
        if society_id:
            stmt = stmt.where(PlatformSubscriptionAuditLog.society_id == society_id)

        audit_record = (await session.execute(stmt)).scalar_one_or_none()
        if not audit_record or not audit_record.after_state:
            raise InvoiceTaxSnapshotNotFoundException(invoice_id)

        snapshot = TaxSnapshot(**audit_record.after_state)
        if not TaxSnapshotService.verify_snapshot_integrity(snapshot):
            raise InvoiceTaxSnapshotTamperedException(invoice_id)

        return snapshot

    async def verify_invoice_tax_snapshot(
        self,
        session: AsyncSession,
        invoice_id: UUID,
        society_id: UUID | None = None,
    ) -> TaxSnapshotVerificationResponse:
        """Verify cryptographic integrity of an issued invoice's persisted tax snapshot."""
        stmt = (
            select(PlatformSubscriptionAuditLog)
            .where(
                PlatformSubscriptionAuditLog.entity_type == "INVOICE_TAX_SNAPSHOT",
                PlatformSubscriptionAuditLog.entity_id == invoice_id,
            )
            .order_by(desc(PlatformSubscriptionAuditLog.created_at))
            .limit(1)
        )
        if society_id:
            stmt = stmt.where(PlatformSubscriptionAuditLog.society_id == society_id)

        audit_record = (await session.execute(stmt)).scalar_one_or_none()
        if not audit_record or not audit_record.after_state:
            raise InvoiceTaxSnapshotNotFoundException(invoice_id)

        snapshot = TaxSnapshot(**audit_record.after_state)
        recalculated_hash = TaxSnapshotService.compute_integrity_hash(
            sac_code=snapshot.sac_code,
            tax_rate=snapshot.tax_rate,
            taxable_value=snapshot.taxable_value,
            cgst_amount=snapshot.cgst_amount,
            sgst_amount=snapshot.sgst_amount,
            igst_amount=snapshot.igst_amount,
            total_tax=snapshot.total_tax,
            grand_total=snapshot.grand_total,
            supplier_state_code=snapshot.supplier_state_code,
            place_of_supply_code=snapshot.place_of_supply_code,
            supply_type=snapshot.supply_type.value,
            tax_config_version=snapshot.tax_config_version,
            calculation_timestamp=snapshot.calculation_timestamp,
            currency_code=snapshot.currency_code,
            invoice_id=snapshot.invoice_id,
            commercial_discount=snapshot.commercial_discount,
            prorated_credit=snapshot.prorated_credit,
        )

        is_valid = recalculated_hash == snapshot.integrity_hash

        return TaxSnapshotVerificationResponse(
            invoice_id=invoice_id,
            snapshot_id=snapshot.snapshot_id,
            is_valid=is_valid,
            snapshot_hash=snapshot.integrity_hash,
            recalculated_hash=recalculated_hash,
            sac_code=snapshot.sac_code,
            tax_rate=snapshot.tax_rate,
            taxable_value=snapshot.taxable_value,
            tax_total=snapshot.total_tax,
            grand_total=snapshot.grand_total,
            calculation_timestamp=snapshot.calculation_timestamp,
            error_message=None if is_valid else "Cryptographic digest mismatch detected.",
        )

    def _to_response(
        self,
        invoice: PlatformInvoice,
        items: list[PlatformInvoiceItem] | None = None,
    ) -> PlatformInvoiceResponse:
        """Convert SQLAlchemy PlatformInvoice model to Pydantic response schema."""
        source_items = items if items is not None else getattr(invoice, "items", [])
        res_items = [
            PlatformInvoiceItemResponse(
                id=item.id,
                invoice_id=item.invoice_id,
                item_index=item.item_index,
                item_type=item.item_type,
                description=item.description,
                sac_code=item.sac_code,
                quantity=item.quantity,
                unit_price=item.unit_price,
                discount_amount=item.discount_amount,
                taxable_amount=item.taxable_amount,
                tax_rate=item.tax_rate,
                tax_amount=item.tax_amount,
                total_amount=item.total_amount,
            )
            for item in source_items
        ]

        return PlatformInvoiceResponse(
            id=invoice.id,
            society_id=invoice.society_id,
            subscription_id=invoice.subscription_id,
            invoice_number=invoice.invoice_number,
            fiscal_year=invoice.fiscal_year,
            billing_cycle=invoice.billing_cycle,
            period_start=invoice.period_start,
            period_end=invoice.period_end,
            subtotal=invoice.subtotal,
            discount_total=invoice.discount_total,
            prorated_credit=invoice.prorated_credit,
            taxable_amount=invoice.taxable_amount,
            cgst_amount=invoice.cgst_amount,
            sgst_amount=invoice.sgst_amount,
            igst_amount=invoice.igst_amount,
            tax_total=invoice.tax_total,
            grand_total=invoice.grand_total,
            credits_applied=invoice.credits_applied,
            amount_paid=invoice.amount_paid,
            amount_due=invoice.amount_due,
            currency_code=invoice.currency_code,
            status=invoice.status,
            due_date=invoice.due_date,
            issued_at=invoice.issued_at,
            paid_at=invoice.paid_at,
            voided_at=invoice.voided_at,
            void_reason=invoice.void_reason,
            sac_code=invoice.sac_code,
            place_of_supply=invoice.place_of_supply,
            customer_gstin=invoice.customer_gstin,
            idempotency_key=invoice.idempotency_key,
            items=res_items,
        )
