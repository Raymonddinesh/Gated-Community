"""Phase 21E.4C — SaaS Platform Credit Note Service.

Coordinates complete lifecycle for statutory B2B credit notes:
- DRAFT creation, updating, and simulated preview.
- Concurrency-safe atomic ISSUED finalization with SELECT ... FOR UPDATE sequence locking.
- Reversal of GST taxes using exact historical TaxSnapshot from original invoice (M-2 & M-3).
- Strict over-credit prevention at invoice level and per-line level.
- Deterministic invoice balance adjustments with explicit unapplied credit balance (ADVANCE_BALANCE).
- Permanent record retention upon VOID with audit logging.
- Strict tenant isolation via PostgreSQL FORCE RLS.
"""

import logging
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from apps.api.src.database.models.platform_billing import (
    PlatformBillingAdjustment,
    PlatformCreditNote,
    PlatformCreditNoteItem,
    PlatformInvoice,
    PlatformInvoiceItem,
    PlatformSubscriptionAuditLog,
)
from apps.api.src.subscriptions.credit_notes.exceptions import (
    CreditNoteExceedsEligibleBalanceException,
    CreditNoteInvoiceNotEligibleException,
    CreditNoteItemExceedsLineEligibilityException,
    CreditNoteNotFoundException,
    CreditNoteTaxSnapshotNotFoundException,
    CreditNoteTaxSnapshotTamperedException,
    CreditNoteValidationException,
    InvalidCreditNoteStateException,
)
from apps.api.src.subscriptions.credit_notes.numbering import CreditNoteNumberingService
from apps.api.src.subscriptions.credit_notes.schemas import (
    CreditNotePreviewResponse,
    CreditNoteTaxSnapshotVerificationResponse,
    PlatformCreditNoteCreateDraft,
    PlatformCreditNoteItemCreate,
    PlatformCreditNoteItemResponse,
    PlatformCreditNotePreviewRequest,
    PlatformCreditNoteResponse,
    PlatformCreditNoteUpdateDraft,
    PlatformCreditNoteVoidRequest,
)
from apps.api.src.subscriptions.tax import (
    GSTTaxEngine,
    TaxSnapshot,
    TaxSnapshotService,
    quantize_money,
)

logger = logging.getLogger("societysphere.subscriptions.credit_notes")

ELIGIBLE_INVOICE_STATUSES = {"ISSUED", "PAID", "PARTIALLY_PAID", "OVERDUE"}


def _utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class PlatformCreditNoteService:
    """Domain service managing the complete SaaS statutory credit note lifecycle."""

    def __init__(
        self,
        session: AsyncSession,
        numbering_service: CreditNoteNumberingService | None = None,
        tax_engine: GSTTaxEngine | None = None,
    ) -> None:
        self.session = session
        self.numbering_service = numbering_service or CreditNoteNumberingService()
        self.tax_engine = tax_engine or GSTTaxEngine()

    async def create_draft_credit_note(
        self,
        payload: PlatformCreditNoteCreateDraft,
        society_id: UUID | None = None,
        creator_user_id: UUID | None = None,
    ) -> PlatformCreditNoteResponse:
        """Create a new unissued draft credit note referencing an eligible invoice."""
        now = _utc_now()

        # 1. Fetch target invoice and assert tenant isolation
        invoice = await self._fetch_invoice_for_update(payload.invoice_id, society_id)
        effective_society_id = society_id or invoice.society_id

        # 2. Verify invoice status eligibility
        if invoice.status not in ELIGIBLE_INVOICE_STATUSES:
            raise CreditNoteInvoiceNotEligibleException(
                invoice_id=invoice.id,
                invoice_status=invoice.status,
                reason=f"Credit notes can only be issued against finalized invoices ({ELIGIBLE_INVOICE_STATUSES}).",
            )

        # 3. Retrieve and verify original invoice tax snapshot
        original_snapshot = await self._get_verified_invoice_tax_snapshot(invoice.id, effective_society_id)

        # 4. Calculate credit note taxable amount and line items
        taxable_credit, items_to_create = self._resolve_credit_items(
            invoice=invoice,
            snapshot=original_snapshot,
            items_payload=payload.items,
            taxable_amount_override=payload.taxable_amount,
        )

        # 5. Check remaining eligible invoice balance
        prior_credits = await self._get_total_issued_credits(invoice.id, effective_society_id)
        eligible_balance = max(Decimal("0.00"), invoice.grand_total - prior_credits)

        # 6. Compute tax calculation via GSTTaxEngine using original snapshot rates
        calc_result = self.tax_engine.calculate_credit_note_tax(
            taxable_credit_amount=taxable_credit,
            original_invoice_snapshot=original_snapshot,
        )

        if calc_result.grand_total > eligible_balance:
            raise CreditNoteExceedsEligibleBalanceException(
                invoice_id=invoice.id,
                requested_amount=str(calc_result.grand_total),
                eligible_balance=str(eligible_balance),
            )

        # 7. Check line-level eligibility if items are specified
        await self._validate_line_level_eligibility(invoice.id, effective_society_id, items_to_create)

        # 8. Create draft PlatformCreditNote entity (number is NULL for draft)
        from apps.api.src.subscriptions.credit_notes.numbering import get_financial_year

        fy = get_financial_year(now)

        credit_note = PlatformCreditNote(
            id=uuid4(),
            society_id=effective_society_id,
            invoice_id=invoice.id,
            credit_note_number=None,
            fiscal_year=fy,
            taxable_amount=calc_result.taxable_amount,
            cgst_amount=calc_result.cgst_amount,
            sgst_amount=calc_result.sgst_amount,
            igst_amount=calc_result.igst_amount,
            tax_total=calc_result.tax_total,
            grand_total=calc_result.grand_total,
            currency_code=invoice.currency_code,
            reason=payload.reason,
            notes=payload.notes,
            status="DRAFT",
            issued_at=None,
            created_by=creator_user_id,
            created_at=now,
            updated_at=now,
        )
        self.session.add(credit_note)
        await self.session.flush()

        # 9. Create line items
        persisted_items = self._persist_credit_note_items(
            credit_note=credit_note,
            items_data=items_to_create,
            calc_result=calc_result,
            now=now,
        )
        await self.session.flush()

        logger.info(
            "Draft credit note %s created for invoice %s (taxable: %s, total: %s)",
            credit_note.id,
            invoice.id,
            credit_note.taxable_amount,
            credit_note.grand_total,
        )
        return self._to_response(credit_note, persisted_items)

    async def get_credit_note(
        self,
        credit_note_id: UUID,
        society_id: UUID | None = None,
    ) -> PlatformCreditNoteResponse:
        """Retrieve a credit note by ID with optional tenant scope enforcement."""
        stmt = (
            select(PlatformCreditNote)
            .options(selectinload(PlatformCreditNote.items))
            .where(PlatformCreditNote.id == credit_note_id)
        )
        if society_id:
            stmt = stmt.where(PlatformCreditNote.society_id == society_id)

        cn = (await self.session.execute(stmt)).scalar_one_or_none()
        if not cn:
            raise CreditNoteNotFoundException(credit_note_id=credit_note_id)

        return self._to_response(cn, cn.items)

    async def update_draft_credit_note(
        self,
        credit_note_id: UUID,
        payload: PlatformCreditNoteUpdateDraft,
        society_id: UUID | None = None,
    ) -> PlatformCreditNoteResponse:
        """Update fields or line items of an unissued draft credit note."""
        now = _utc_now()
        stmt = (
            select(PlatformCreditNote)
            .options(selectinload(PlatformCreditNote.items))
            .where(PlatformCreditNote.id == credit_note_id)
            .with_for_update()
        )
        if society_id:
            stmt = stmt.where(PlatformCreditNote.society_id == society_id)

        cn = (await self.session.execute(stmt)).scalar_one_or_none()
        if not cn:
            raise CreditNoteNotFoundException(credit_note_id=credit_note_id)

        if cn.status != "DRAFT":
            raise InvalidCreditNoteStateException(
                current_status=cn.status,
                target_status="DRAFT",
                reason="Cannot update a credit note that is already ISSUED or VOID. Issued credit notes are immutable.",
            )

        effective_soc_id = society_id or cn.society_id
        invoice = await self._fetch_invoice_for_update(cn.invoice_id, effective_soc_id)
        original_snapshot = await self._get_verified_invoice_tax_snapshot(invoice.id, effective_soc_id)

        if payload.reason is not None:
            cn.reason = payload.reason
        if payload.notes is not None:
            cn.notes = payload.notes

        # Re-resolve items if payload provides items or taxable_amount
        if payload.items is not None or payload.taxable_amount is not None:
            taxable_credit, items_to_create = self._resolve_credit_items(
                invoice=invoice,
                snapshot=original_snapshot,
                items_payload=payload.items or [],
                taxable_amount_override=payload.taxable_amount,
            )

            # Check remaining eligible invoice balance (excluding this draft)
            prior_credits = await self._get_total_issued_credits(invoice.id, society_id)
            eligible_balance = max(Decimal("0.00"), invoice.grand_total - prior_credits)

            calc_result = self.tax_engine.calculate_credit_note_tax(
                taxable_credit_amount=taxable_credit,
                original_invoice_snapshot=original_snapshot,
            )

            if calc_result.grand_total > eligible_balance:
                raise CreditNoteExceedsEligibleBalanceException(
                    invoice_id=invoice.id,
                    requested_amount=str(calc_result.grand_total),
                    eligible_balance=str(eligible_balance),
                )

            # Check line eligibility
            await self._validate_line_level_eligibility(invoice.id, society_id, items_to_create)

            # Delete old items
            for old_item in list(cn.items):
                await self.session.delete(old_item)
            await self.session.flush()

            # Update amounts
            cn.taxable_amount = calc_result.taxable_amount
            cn.cgst_amount = calc_result.cgst_amount
            cn.sgst_amount = calc_result.sgst_amount
            cn.igst_amount = calc_result.igst_amount
            cn.tax_total = calc_result.tax_total
            cn.grand_total = calc_result.grand_total
            cn.updated_at = now

            persisted_items = self._persist_credit_note_items(
                credit_note=cn,
                items_data=items_to_create,
                calc_result=calc_result,
                now=now,
            )
        else:
            persisted_items = cn.items
            cn.updated_at = now

        await self.session.flush()
        return self._to_response(cn, persisted_items)

    async def calculate_preview(
        self,
        payload: PlatformCreditNotePreviewRequest,
        society_id: UUID | None = None,
    ) -> CreditNotePreviewResponse:
        """Calculate credit note amounts and simulate invoice balance adjustments without saving."""
        invoice = await self._fetch_invoice_for_update(payload.invoice_id, society_id)
        effective_society_id = society_id or invoice.society_id

        if invoice.status not in ELIGIBLE_INVOICE_STATUSES:
            raise CreditNoteInvoiceNotEligibleException(
                invoice_id=invoice.id,
                invoice_status=invoice.status,
                reason=f"Credit notes can only be issued against finalized invoices ({ELIGIBLE_INVOICE_STATUSES}).",
            )

        original_snapshot = await self._get_verified_invoice_tax_snapshot(invoice.id, effective_society_id)

        taxable_credit, items_to_create = self._resolve_credit_items(
            invoice=invoice,
            snapshot=original_snapshot,
            items_payload=payload.items or [],
            taxable_amount_override=payload.effective_taxable_amount,
        )

        prior_credits = await self._get_total_issued_credits(invoice.id, effective_society_id)
        eligible_balance = max(Decimal("0.00"), invoice.grand_total - prior_credits)

        calc_result = self.tax_engine.calculate_credit_note_tax(
            taxable_credit_amount=taxable_credit,
            original_invoice_snapshot=original_snapshot,
        )

        # Calculate simulated balance
        total_credits = prior_credits + calc_result.grand_total
        adjusted_obligation = max(Decimal("0.00"), invoice.grand_total - total_credits)
        new_outstanding = max(Decimal("0.00"), adjusted_obligation - invoice.amount_paid)
        unapplied_credit = max(Decimal("0.00"), invoice.amount_paid - adjusted_obligation)

        return CreditNotePreviewResponse(
            invoice_id=invoice.id,
            taxable_amount=calc_result.taxable_amount,
            cgst_amount=calc_result.cgst_amount,
            sgst_amount=calc_result.sgst_amount,
            igst_amount=calc_result.igst_amount,
            tax_total=calc_result.tax_total,
            grand_total=calc_result.grand_total,
            currency_code=invoice.currency_code,
            original_invoice_total=invoice.grand_total,
            invoice_settled_payments=invoice.amount_paid,
            prior_issued_credits=prior_credits,
            eligible_invoice_balance=eligible_balance,
            new_invoice_outstanding=new_outstanding,
            unapplied_credit_balance=unapplied_credit,
            tax_config_version=original_snapshot.tax_config_version,
        )

    async def issue_credit_note(
        self,
        credit_note_id: UUID,
        society_id: UUID | None = None,
        issuer_user_id: UUID | None = None,
    ) -> PlatformCreditNoteResponse:
        """Atomically transition DRAFT -> ISSUED, allocate sequential number, apply balance adjustment."""
        now = _utc_now()

        # 1. Fetch credit note with lock
        stmt = (
            select(PlatformCreditNote)
            .options(selectinload(PlatformCreditNote.items))
            .where(PlatformCreditNote.id == credit_note_id)
            .with_for_update()
        )
        if society_id:
            stmt = stmt.where(PlatformCreditNote.society_id == society_id)

        cn = (await self.session.execute(stmt)).scalar_one_or_none()
        if not cn:
            raise CreditNoteNotFoundException(credit_note_id=credit_note_id)

        effective_soc_id = society_id or cn.society_id

        if cn.status == "ISSUED":
            raise InvalidCreditNoteStateException(
                current_status="ISSUED",
                target_status="ISSUED",
                reason=f"Credit note {credit_note_id} is already in 'ISSUED' state.",
            )

        if cn.status != "DRAFT":
            raise InvalidCreditNoteStateException(
                current_status=cn.status,
                target_status="ISSUED",
                reason=f"Cannot issue credit note with status '{cn.status}'. Only DRAFT can be issued.",
            )

        # 2. Lock target invoice
        invoice = await self._fetch_invoice_for_update(cn.invoice_id, effective_soc_id)
        if invoice.status not in ELIGIBLE_INVOICE_STATUSES:
            raise CreditNoteInvoiceNotEligibleException(
                invoice_id=invoice.id,
                invoice_status=invoice.status,
                reason=f"Target invoice status '{invoice.status}' is not eligible for credit issuance.",
            )

        # 3. Retrieve and verify snapshot
        original_snapshot = await self._get_verified_invoice_tax_snapshot(invoice.id, effective_soc_id)

        # 4. Pessimistic check of remaining invoice eligibility
        prior_credits = await self._get_total_issued_credits(invoice.id, effective_soc_id)
        eligible_balance = max(Decimal("0.00"), invoice.grand_total - prior_credits)

        if cn.grand_total > eligible_balance:
            raise CreditNoteExceedsEligibleBalanceException(
                invoice_id=invoice.id,
                requested_amount=str(cn.grand_total),
                eligible_balance=str(eligible_balance),
            )

        # 5. Allocate sequential credit note number under row lock
        cn_number, fy = await self.numbering_service.allocate_credit_note_number(
            session=self.session,
            transaction_date=now,
        )

        # 6. Reconstruct and store credit note tax snapshot
        calc_result = self.tax_engine.calculate_credit_note_tax(
            taxable_credit_amount=cn.taxable_amount,
            original_invoice_snapshot=original_snapshot,
        )
        cn_snapshot = calc_result.tax_snapshot

        # 7. Update credit note entity
        cn.credit_note_number = cn_number
        cn.fiscal_year = fy
        cn.status = "ISSUED"
        cn.issued_at = now
        cn.updated_at = now

        # 8. Record immutable snapshot audit log entry
        audit_log = PlatformSubscriptionAuditLog(
            id=uuid4(),
            society_id=effective_soc_id,
            entity_type="CREDIT_NOTE_TAX_SNAPSHOT",
            entity_id=cn.id,
            action="ISSUE",
            actor_type="USER" if issuer_user_id else "SYSTEM",
            actor_id=issuer_user_id,
            correlation_id=cn_number,
            before_state=None,
            after_state=TaxSnapshotService.to_dict(cn_snapshot),
            ip_address=None,
            created_at=now,
        )
        self.session.add(audit_log)

        # 9. Apply invoice balance adjustments
        await self._apply_invoice_balance_adjustments(
            invoice=invoice,
            credit_note=cn,
            prior_credits=prior_credits,
            user_id=issuer_user_id,
            now=now,
        )

        await self.session.flush()
        logger.info(
            "Credit note %s (%s) issued for invoice %s. Total: %s",
            cn.id,
            cn.credit_note_number,
            invoice.id,
            cn.grand_total,
        )
        return self._to_response(cn, cn.items)

    async def void_credit_note(
        self,
        credit_note_id: UUID,
        payload: PlatformCreditNoteVoidRequest,
        society_id: UUID | None = None,
        actor_user_id: UUID | None = None,
    ) -> PlatformCreditNoteResponse:
        """Void an issued credit note with permanent record retention and invoice balance restoration."""
        now = _utc_now()
        stmt = (
            select(PlatformCreditNote)
            .options(selectinload(PlatformCreditNote.items))
            .where(PlatformCreditNote.id == credit_note_id)
            .with_for_update()
        )
        if society_id:
            stmt = stmt.where(PlatformCreditNote.society_id == society_id)

        cn = (await self.session.execute(stmt)).scalar_one_or_none()
        if not cn:
            raise CreditNoteNotFoundException(credit_note_id=credit_note_id)

        if cn.status == "VOID":
            return self._to_response(cn, cn.items)

        if cn.status != "ISSUED":
            raise InvalidCreditNoteStateException(
                current_status=cn.status,
                target_status="VOID",
                reason=f"Only ISSUED credit notes can be voided. Current status is '{cn.status}'.",
            )

        effective_soc_id = society_id or cn.society_id

        # 1. Lock invoice
        invoice = await self._fetch_invoice_for_update(cn.invoice_id, effective_soc_id)

        # 2. Transition status to VOID
        old_status = cn.status
        cn.status = "VOID"
        cn.notes = f"{cn.notes or ''}\n[VOIDED on {now.isoformat()}]: {payload.void_reason}".strip()
        cn.updated_at = now

        # 3. Restore invoice balance: recalculate total remaining issued credits
        remaining_credits = await self._get_total_issued_credits(
            invoice.id, effective_soc_id, exclude_cn_id=cn.id
        )
        adjusted_obligation = max(Decimal("0.00"), invoice.grand_total - remaining_credits)
        new_amount_due = max(Decimal("0.00"), adjusted_obligation - invoice.amount_paid)

        invoice.credits_applied = remaining_credits
        invoice.amount_due = new_amount_due

        # If an unapplied advance balance was created for this credit note, delete or reverse it
        adj_stmt = select(PlatformBillingAdjustment).where(
            PlatformBillingAdjustment.credit_note_id == cn.id,
            PlatformBillingAdjustment.adjustment_type == "ADVANCE_BALANCE",
        )
        existing_adj = (await self.session.execute(adj_stmt)).scalar_one_or_none()
        if existing_adj:
            await self.session.delete(existing_adj)

        # 4. Audit log entry for VOID
        audit_log = PlatformSubscriptionAuditLog(
            id=uuid4(),
            society_id=effective_soc_id,
            entity_type="PLATFORM_CREDIT_NOTE",
            entity_id=cn.id,
            action="VOID",
            actor_type="USER" if actor_user_id else "SYSTEM",
            actor_id=actor_user_id,
            correlation_id=cn.credit_note_number,
            before_state={"status": old_status},
            after_state={"status": "VOID", "reason": payload.void_reason},
            ip_address=None,
            created_at=now,
        )
        self.session.add(audit_log)

        await self.session.flush()
        logger.info("Credit note %s (%s) marked VOID. Reason: %s", cn.id, cn.credit_note_number, payload.void_reason)
        return self._to_response(cn, cn.items)

    async def get_credit_note_tax_snapshot(
        self,
        credit_note_id: UUID,
        society_id: UUID | None = None,
    ) -> CreditNoteTaxSnapshotVerificationResponse:
        """Retrieve the immutable credit note tax snapshot and verify its SHA-256 digest."""
        stmt = select(PlatformSubscriptionAuditLog).where(
            PlatformSubscriptionAuditLog.entity_id == credit_note_id,
            PlatformSubscriptionAuditLog.entity_type == "CREDIT_NOTE_TAX_SNAPSHOT",
        )
        if society_id:
            stmt = stmt.where(PlatformSubscriptionAuditLog.society_id == society_id)

        audit_row = (await self.session.execute(stmt)).scalar_one_or_none()
        if not audit_row or not audit_row.after_state:
            raise CreditNoteTaxSnapshotNotFoundException(
                entity_id=credit_note_id, entity_type="CREDIT_NOTE"
            )

        data = audit_row.after_state
        stored_hash = data.get("integrity_hash", "")
        calc_dt = datetime.fromisoformat(data["calculation_timestamp"])

        inv_id_val = UUID(str(data["invoice_id"])) if data.get("invoice_id") else None

        computed_hash = TaxSnapshotService.compute_integrity_hash(
            sac_code=data["sac_code"],
            tax_rate=Decimal(str(data["tax_rate"])),
            taxable_value=Decimal(str(data["taxable_value"])),
            cgst_amount=Decimal(str(data["cgst_amount"])),
            sgst_amount=Decimal(str(data["sgst_amount"])),
            igst_amount=Decimal(str(data["igst_amount"])),
            total_tax=Decimal(str(data["total_tax"])),
            grand_total=Decimal(str(data["grand_total"])),
            supplier_state_code=data["supplier_state_code"],
            place_of_supply_code=data["place_of_supply_code"],
            supply_type=data["supply_type"],
            tax_config_version=data["tax_config_version"],
            calculation_timestamp=calc_dt,
            currency_code=data.get("currency_code", "INR"),
            invoice_id=inv_id_val,
            commercial_discount=Decimal(str(data.get("commercial_discount", "0.00"))),
            prorated_credit=Decimal(str(data.get("prorated_credit", "0.00"))),
        )

        is_tampered = stored_hash != computed_hash
        if is_tampered:
            raise CreditNoteTaxSnapshotTamperedException(
                snapshot_id=UUID(str(data["snapshot_id"])),
                stored_hash=stored_hash,
                computed_hash=computed_hash,
            )

        # Lookup credit note's invoice_id if not present in snapshot
        if inv_id_val is None:
            cn_stmt = select(PlatformCreditNote.invoice_id).where(PlatformCreditNote.id == credit_note_id)
            inv_id_val = (await self.session.execute(cn_stmt)).scalar_one_or_none() or uuid4()

        return CreditNoteTaxSnapshotVerificationResponse(
            verified=True,
            tampered=False,
            snapshot_id=UUID(str(data["snapshot_id"])),
            credit_note_id=credit_note_id,
            original_invoice_id=inv_id_val,
            calculated_at=calc_dt,
            tax_config_version=data["tax_config_version"],
            stored_hash=stored_hash,
            computed_hash=computed_hash,
        )

    async def list_credit_notes(
        self,
        society_id: UUID | None = None,
        invoice_id: UUID | None = None,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[PlatformCreditNoteResponse]:
        """List credit notes with optional tenant, invoice, and status filtering."""
        stmt = (
            select(PlatformCreditNote)
            .options(selectinload(PlatformCreditNote.items))
        )
        if society_id:
            stmt = stmt.where(PlatformCreditNote.society_id == society_id)
        if invoice_id:
            stmt = stmt.where(PlatformCreditNote.invoice_id == invoice_id)
        if status:
            stmt = stmt.where(PlatformCreditNote.status == status.upper())

        stmt = stmt.order_by(desc(PlatformCreditNote.created_at)).limit(limit).offset(offset)
        rows = (await self.session.execute(stmt)).scalars().all()
        return [self._to_response(cn, cn.items) for cn in rows]

    # -------------------------------------------------------------------------
    # Internal Helpers
    # -------------------------------------------------------------------------

    async def _fetch_invoice_for_update(self, invoice_id: UUID, society_id: UUID | None = None) -> PlatformInvoice:
        stmt = (
            select(PlatformInvoice)
            .options(selectinload(PlatformInvoice.items))
            .where(PlatformInvoice.id == invoice_id)
            .with_for_update()
        )
        if society_id:
            stmt = stmt.where(PlatformInvoice.society_id == society_id)

        inv = (await self.session.execute(stmt)).scalar_one_or_none()
        if not inv:
            from apps.api.src.subscriptions.invoicing.exceptions import InvoiceNotFoundException

            raise InvoiceNotFoundException(invoice_id=invoice_id)
        return inv

    async def _get_total_issued_credits(
        self,
        invoice_id: UUID,
        society_id: UUID | None = None,
        exclude_cn_id: UUID | None = None,
    ) -> Decimal:
        stmt = select(func.coalesce(func.sum(PlatformCreditNote.grand_total), Decimal("0.00"))).where(
            PlatformCreditNote.invoice_id == invoice_id,
            PlatformCreditNote.status == "ISSUED",
        )
        if society_id:
            stmt = stmt.where(PlatformCreditNote.society_id == society_id)
        if exclude_cn_id:
            stmt = stmt.where(PlatformCreditNote.id != exclude_cn_id)
        val = await self.session.scalar(stmt)
        return quantize_money(val or Decimal("0.00"))

    async def _get_verified_invoice_tax_snapshot(
        self,
        invoice_id: UUID,
        society_id: UUID | None = None,
    ) -> TaxSnapshot:
        stmt = select(PlatformSubscriptionAuditLog).where(
            PlatformSubscriptionAuditLog.entity_id == invoice_id,
            PlatformSubscriptionAuditLog.entity_type == "INVOICE_TAX_SNAPSHOT",
        )
        if society_id:
            stmt = stmt.where(PlatformSubscriptionAuditLog.society_id == society_id)
        audit_row = (await self.session.execute(stmt)).scalar_one_or_none()
        if not audit_row or not audit_row.after_state:
            raise CreditNoteTaxSnapshotNotFoundException(entity_id=invoice_id, entity_type="INVOICE")

        data = audit_row.after_state
        stored_hash = data.get("integrity_hash", "")
        calc_dt = datetime.fromisoformat(data["calculation_timestamp"])

        computed_hash = TaxSnapshotService.compute_integrity_hash(
            sac_code=data["sac_code"],
            tax_rate=Decimal(str(data["tax_rate"])),
            taxable_value=Decimal(str(data["taxable_value"])),
            cgst_amount=Decimal(str(data["cgst_amount"])),
            sgst_amount=Decimal(str(data["sgst_amount"])),
            igst_amount=Decimal(str(data["igst_amount"])),
            total_tax=Decimal(str(data["total_tax"])),
            grand_total=Decimal(str(data["grand_total"])),
            supplier_state_code=data["supplier_state_code"],
            place_of_supply_code=data["place_of_supply_code"],
            supply_type=data["supply_type"],
            tax_config_version=data["tax_config_version"],
            calculation_timestamp=calc_dt,
            currency_code=data.get("currency_code", "INR"),
            invoice_id=UUID(data["invoice_id"]) if data.get("invoice_id") else None,
            commercial_discount=Decimal(str(data.get("commercial_discount", "0.00"))),
            prorated_credit=Decimal(str(data.get("prorated_credit", "0.00"))),
        )

        if stored_hash != computed_hash:
            raise CreditNoteTaxSnapshotTamperedException(
                snapshot_id=UUID(data["snapshot_id"]),
                stored_hash=stored_hash,
                computed_hash=computed_hash,
            )

        return TaxSnapshot.model_validate(data)

    def _resolve_credit_items(
        self,
        invoice: PlatformInvoice,
        snapshot: TaxSnapshot,
        items_payload: list[PlatformCreditNoteItemCreate],
        taxable_amount_override: Decimal | None,
    ) -> tuple[Decimal, list[dict]]:
        """Resolve taxable credit amount and item structures."""
        if items_payload:
            total_taxable = sum(
                ((item.taxable_amount if item.taxable_amount is not None else item.quantity * item.unit_price) for item in items_payload),
                Decimal("0.00"),
            )
            items_data = [
                {
                    "invoice_item_id": it.invoice_item_id,
                    "description": it.description,
                    "sac_code": it.sac_code,
                    "quantity": it.quantity,
                    "unit_price": it.unit_price,
                    "taxable_amount": it.taxable_amount if it.taxable_amount is not None else it.quantity * it.unit_price,
                    "tax_rate": it.tax_rate,
                }
                for it in items_payload
            ]
            return quantize_money(total_taxable), items_data

        if taxable_amount_override is not None:
            taxable_credit = quantize_money(taxable_amount_override)
            items_data = [
                {
                    "invoice_item_id": None,
                    "description": f"Credit adjustment for invoice {invoice.invoice_number or invoice.id}",
                    "sac_code": snapshot.sac_code,
                    "quantity": Decimal("1.0000"),
                    "unit_price": taxable_credit,
                    "taxable_amount": taxable_credit,
                    "tax_rate": snapshot.tax_rate,
                }
            ]
            return taxable_credit, items_data

        # Full credit: entire invoice taxable amount
        taxable_credit = snapshot.taxable_value
        items_data = [
            {
                "invoice_item_id": None,
                "description": f"Full credit note for invoice {invoice.invoice_number or invoice.id}",
                "sac_code": snapshot.sac_code,
                "quantity": Decimal("1.0000"),
                "unit_price": taxable_credit,
                "taxable_amount": taxable_credit,
                "tax_rate": snapshot.tax_rate,
            }
        ]
        return taxable_credit, items_data

    async def _validate_line_level_eligibility(
        self,
        invoice_id: UUID,
        society_id: UUID | None = None,
        items_data: list[dict[str, Any]] | None = None,
    ) -> None:
        """Assert that individual line items do not exceed the original invoice item's eligible value."""
        if not items_data:
            return
        for item in items_data:
            inv_item_id = item.get("invoice_item_id")
            if not inv_item_id:
                continue

            inv_item_stmt = select(PlatformInvoiceItem).where(
                PlatformInvoiceItem.id == inv_item_id,
                PlatformInvoiceItem.invoice_id == invoice_id,
            )
            inv_item = (await self.session.execute(inv_item_stmt)).scalar_one_or_none()
            if not inv_item:
                raise CreditNoteValidationException(
                    f"Invoice item {inv_item_id} does not belong to target invoice {invoice_id}."
                )

            # Query prior credits against this specific invoice item
            prior_line_credits_stmt = (
                select(func.coalesce(func.sum(PlatformCreditNoteItem.taxable_amount), Decimal("0.00")))
                .join(PlatformCreditNote, PlatformCreditNoteItem.credit_note_id == PlatformCreditNote.id)
                .where(
                    PlatformCreditNoteItem.invoice_item_id == inv_item_id,
                    PlatformCreditNote.status == "ISSUED",
                )
            )
            prior_line_taxable = await self.session.scalar(prior_line_credits_stmt) or Decimal("0.00")
            line_eligible = max(Decimal("0.00"), inv_item.taxable_amount - prior_line_taxable)

            if item["taxable_amount"] > line_eligible:
                raise CreditNoteItemExceedsLineEligibilityException(
                    invoice_item_id=inv_item_id,
                    requested_amount=str(item["taxable_amount"]),
                    eligible_amount=str(line_eligible),
                )

    def _persist_credit_note_items(
        self,
        credit_note: PlatformCreditNote,
        items_data: list[dict],
        calc_result: Any,
        now: datetime,
    ) -> list[PlatformCreditNoteItem]:
        created_items: list[PlatformCreditNoteItem] = []
        effective_rate = calc_result.tax_snapshot.tax_rate

        for idx, it in enumerate(items_data):
            taxable = quantize_money(it["taxable_amount"])
            tax_amt = quantize_money(taxable * (effective_rate / Decimal("100.00")))
            total = quantize_money(taxable + tax_amt)

            item_obj = PlatformCreditNoteItem(
                id=uuid4(),
                credit_note_id=credit_note.id,
                society_id=credit_note.society_id,
                invoice_item_id=it.get("invoice_item_id"),
                item_index=idx,
                description=it["description"],
                sac_code=it.get("sac_code", "998313"),
                quantity=it.get("quantity", Decimal("1.0000")),
                unit_price=quantize_money(it["unit_price"]),
                taxable_amount=taxable,
                tax_rate=effective_rate,
                tax_amount=tax_amt,
                total_amount=total,
                created_at=now,
            )
            self.session.add(item_obj)
            created_items.append(item_obj)

        return created_items

    async def _apply_invoice_balance_adjustments(
        self,
        invoice: PlatformInvoice,
        credit_note: PlatformCreditNote,
        prior_credits: Decimal,
        user_id: UUID | None,
        now: datetime,
    ) -> None:
        """Apply credit note amount to invoice obligations and record advance balance if excess paid."""
        total_credits = prior_credits + credit_note.grand_total
        adjusted_obligation = max(Decimal("0.00"), invoice.grand_total - total_credits)
        new_amount_due = max(Decimal("0.00"), adjusted_obligation - invoice.amount_paid)
        excess_paid = max(Decimal("0.00"), invoice.amount_paid - adjusted_obligation)

        invoice.credits_applied = total_credits
        invoice.amount_due = new_amount_due

        # If customer has paid more than the adjusted obligation, record unapplied credit
        if excess_paid > Decimal("0.00"):
            adj = PlatformBillingAdjustment(
                id=uuid4(),
                society_id=invoice.society_id,
                invoice_id=invoice.id,
                credit_note_id=credit_note.id,
                adjustment_type="ADVANCE_BALANCE",
                amount=excess_paid,
                currency_code=invoice.currency_code,
                idempotency_key=f"ADV-BAL-{credit_note.id}",
                reason=(
                    f"Unapplied credit balance of ₹{excess_paid} from credit note "
                    f"{credit_note.credit_note_number} on settled invoice {invoice.invoice_number}."
                ),
                applied_at=now,
                created_by=user_id,
                created_at=now,
            )
            self.session.add(adj)

    def _to_response(
        self,
        cn: PlatformCreditNote,
        items: list[PlatformCreditNoteItem] | None = None,
    ) -> PlatformCreditNoteResponse:
        item_responses: list[PlatformCreditNoteItemResponse] = []
        if items is not None:
            for item in items:
                item_responses.append(
                    PlatformCreditNoteItemResponse(
                        id=item.id,
                        credit_note_id=item.credit_note_id,
                        invoice_item_id=item.invoice_item_id,
                        item_index=item.item_index,
                        description=item.description,
                        sac_code=item.sac_code,
                        quantity=item.quantity,
                        unit_price=item.unit_price,
                        taxable_amount=item.taxable_amount,
                        tax_rate=item.tax_rate,
                        tax_amount=item.tax_amount,
                        total_amount=item.total_amount,
                        created_at=item.created_at,
                    )
                )

        return PlatformCreditNoteResponse(
            id=cn.id,
            society_id=cn.society_id,
            invoice_id=cn.invoice_id,
            credit_note_number=cn.credit_note_number,
            fiscal_year=cn.fiscal_year,
            taxable_amount=cn.taxable_amount,
            cgst_amount=cn.cgst_amount,
            sgst_amount=cn.sgst_amount,
            igst_amount=cn.igst_amount,
            tax_total=cn.tax_total,
            grand_total=cn.grand_total,
            currency_code=cn.currency_code,
            reason=cn.reason,
            notes=cn.notes,
            status=cn.status,
            issued_at=cn.issued_at,
            created_by=cn.created_by,
            created_at=cn.created_at,
            updated_at=cn.updated_at,
            items=item_responses,
        )
