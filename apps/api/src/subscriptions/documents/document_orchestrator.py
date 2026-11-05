"""Phase 21E.4D — Platform Billing Document Workflow Orchestrator.

Glues PDF rendering, secure object storage, and reliable email delivery:
- Asserts strict immutability (DRAFT documents rejected).
- Enforces multi-tenant authorization and PostgreSQL RLS.
- Retrieves or generates documents with SHA-256 verification.
- Manages transactional email delivery outbox and attempt history.
"""

import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from apps.api.src.database.models.platform_billing import (
    PlatformBillingDocument,
    PlatformCreditNote,
    PlatformDocumentDelivery,
    PlatformInvoice,
    PlatformSubscriptionAuditLog,
)
from apps.api.src.subscriptions.documents.email_service import (
    BillingEmailDeliveryService,
)
from apps.api.src.subscriptions.documents.exceptions import (
    DocumentNotFoundException,
    DocumentPermissionDeniedException,
    DraftDocumentAccessDeniedException,
)
from apps.api.src.subscriptions.documents.pdf_service import BillingPDFService
from apps.api.src.subscriptions.documents.schemas import (
    PlatformDeliveryAttemptResponse,
    PlatformDocumentDeliveryResponse,
    PlatformDocumentDownloadUrlResponse,
    PlatformDocumentEmailRequest,
)
from apps.api.src.subscriptions.documents.storage_service import (
    BillingDocumentStorageService,
)
from apps.api.src.subscriptions.tax.snapshot import TaxSnapshot, TaxSnapshotService

logger = logging.getLogger("societysphere.subscriptions.documents.orchestrator")


class PlatformBillingDocumentService:
    """High-level service coordinating document generation, persistence, and dispatch."""

    def __init__(
        self,
        pdf_service: BillingPDFService | None = None,
        storage_service: BillingDocumentStorageService | None = None,
        email_service: BillingEmailDeliveryService | None = None,
    ) -> None:
        self.pdf_service = pdf_service or BillingPDFService()
        self.storage_service = storage_service or BillingDocumentStorageService()
        self.email_service = email_service or BillingEmailDeliveryService()

    async def _fetch_tax_snapshot(
        self,
        session: AsyncSession,
        entity_id: UUID,
        entity_type: str,
        society_id: UUID,
    ) -> TaxSnapshot:
        """Fetch and cryptographically verify immutable TaxSnapshot from audit log."""
        stmt = (
            select(PlatformSubscriptionAuditLog)
            .where(
                PlatformSubscriptionAuditLog.society_id == society_id,
                PlatformSubscriptionAuditLog.entity_id == entity_id,
                PlatformSubscriptionAuditLog.entity_type == entity_type,
            )
            .order_by(PlatformSubscriptionAuditLog.created_at.desc())
        )
        res = await session.execute(stmt)
        audit_log = res.scalar_one_or_none()
        if not audit_log or not audit_log.after_state:
            raise DocumentNotFoundException(
                f"Immutable tax snapshot not found for {entity_type} '{entity_id}'"
            )

        snapshot = TaxSnapshot.model_validate(audit_log.after_state)
        # Verify cryptographic tamper digest
        TaxSnapshotService.assert_valid_snapshot(snapshot)
        return snapshot

    async def get_or_generate_invoice_document(
        self,
        session: AsyncSession,
        invoice_id: UUID,
        caller_society_id: UUID | None = None,
    ) -> tuple[PlatformBillingDocument, bytes]:
        """Retrieve existing invoice PDF or generate, store, and record metadata."""
        stmt = (
            select(PlatformInvoice)
            .options(
                selectinload(PlatformInvoice.items),
                selectinload(PlatformInvoice.society),
            )
            .where(PlatformInvoice.id == invoice_id)
        )
        if caller_society_id:
            stmt = stmt.where(PlatformInvoice.society_id == caller_society_id)

        res = await session.execute(stmt)
        invoice = res.scalar_one_or_none()
        if not invoice:
            raise DocumentNotFoundException(f"Invoice '{invoice_id}' not found.")

        if caller_society_id and invoice.society_id != caller_society_id:
            raise DocumentPermissionDeniedException(invoice_id, caller_society_id)

        if invoice.status == "DRAFT":
            raise DraftDocumentAccessDeniedException("INVOICE", invoice.id, invoice.status)

        # 1. Check if already generated
        doc_stmt = (
            select(PlatformBillingDocument)
            .where(
                PlatformBillingDocument.society_id == invoice.society_id,
                PlatformBillingDocument.document_type == "INVOICE",
                PlatformBillingDocument.document_id == invoice.id,
            )
        )
        doc_res = await session.execute(doc_stmt)
        existing_doc = doc_res.scalar_one_or_none()

        if existing_doc:
            pdf_bytes = await self.storage_service.get_document_bytes(
                session=session,
                document_id=existing_doc.id,
                caller_society_id=invoice.society_id,
            )
            return existing_doc, pdf_bytes

        # 2. Generate new PDF
        snapshot = await self._fetch_tax_snapshot(
            session=session,
            entity_id=invoice.id,
            entity_type="INVOICE_TAX_SNAPSHOT",
            society_id=invoice.society_id,
        )

        pdf_bytes, checksum = self.pdf_service.generate_invoice_pdf(
            invoice=invoice,
            items=invoice.items,
            snapshot=snapshot,
            society=invoice.society,
        )

        doc = await self.storage_service.store_billing_document(
            session=session,
            society_id=invoice.society_id,
            document_type="INVOICE",
            document_id=invoice.id,
            document_number=invoice.invoice_number or f"INV-{invoice.id.hex[:8]}",
            fiscal_year=invoice.fiscal_year or "2627",
            pdf_bytes=pdf_bytes,
            checksum=checksum,
        )
        return doc, pdf_bytes

    async def get_or_generate_credit_note_document(
        self,
        session: AsyncSession,
        credit_note_id: UUID,
        caller_society_id: UUID | None = None,
    ) -> tuple[PlatformBillingDocument, bytes]:
        """Retrieve existing credit note PDF or generate, store, and record metadata."""
        stmt = (
            select(PlatformCreditNote)
            .options(
                selectinload(PlatformCreditNote.items),
                selectinload(PlatformCreditNote.invoice),
                selectinload(PlatformCreditNote.society),
            )
            .where(PlatformCreditNote.id == credit_note_id)
        )
        if caller_society_id:
            stmt = stmt.where(PlatformCreditNote.society_id == caller_society_id)

        res = await session.execute(stmt)
        cn = res.scalar_one_or_none()
        if not cn:
            raise DocumentNotFoundException(f"Credit note '{credit_note_id}' not found.")

        if caller_society_id and cn.society_id != caller_society_id:
            raise DocumentPermissionDeniedException(credit_note_id, caller_society_id)

        if cn.status == "DRAFT":
            raise DraftDocumentAccessDeniedException("CREDIT_NOTE", cn.id, cn.status)

        # 1. Check if already generated
        doc_stmt = (
            select(PlatformBillingDocument)
            .where(
                PlatformBillingDocument.society_id == cn.society_id,
                PlatformBillingDocument.document_type == "CREDIT_NOTE",
                PlatformBillingDocument.document_id == cn.id,
            )
        )
        doc_res = await session.execute(doc_stmt)
        existing_doc = doc_res.scalar_one_or_none()

        if existing_doc:
            pdf_bytes = await self.storage_service.get_document_bytes(
                session=session,
                document_id=existing_doc.id,
                caller_society_id=cn.society_id,
            )
            return existing_doc, pdf_bytes

        # 2. Generate new PDF
        snapshot = await self._fetch_tax_snapshot(
            session=session,
            entity_id=cn.id,
            entity_type="CREDIT_NOTE_TAX_SNAPSHOT",
            society_id=cn.society_id,
        )

        pdf_bytes, checksum = self.pdf_service.generate_credit_note_pdf(
            credit_note=cn,
            items=cn.items,
            invoice=cn.invoice,
            snapshot=snapshot,
            society=cn.society,
        )

        doc = await self.storage_service.store_billing_document(
            session=session,
            society_id=cn.society_id,
            document_type="CREDIT_NOTE",
            document_id=cn.id,
            document_number=cn.credit_note_number or f"CN-{cn.id.hex[:8]}",
            fiscal_year=cn.fiscal_year or "2627",
            pdf_bytes=pdf_bytes,
            checksum=checksum,
        )
        return doc, pdf_bytes

    async def get_invoice_download_url(
        self,
        session: AsyncSession,
        invoice_id: UUID,
        caller_society_id: UUID | None = None,
        expires_in_seconds: int = 300,
    ) -> PlatformDocumentDownloadUrlResponse:
        """Generate short-lived signed download URL for invoice PDF."""
        doc, _ = await self.get_or_generate_invoice_document(session, invoice_id, caller_society_id)
        url = await self.storage_service.generate_presigned_download_url(
            session=session,
            document_id=doc.id,
            caller_society_id=doc.society_id,
            expires_in_seconds=expires_in_seconds,
        )
        return PlatformDocumentDownloadUrlResponse(
            document_id=doc.id,
            document_number=doc.document_number,
            download_url=url,
            expires_in_seconds=min(expires_in_seconds, 300),
            sha256_checksum=doc.sha256_checksum,
        )

    async def get_credit_note_download_url(
        self,
        session: AsyncSession,
        credit_note_id: UUID,
        caller_society_id: UUID | None = None,
        expires_in_seconds: int = 300,
    ) -> PlatformDocumentDownloadUrlResponse:
        """Generate short-lived signed download URL for credit note PDF."""
        doc, _ = await self.get_or_generate_credit_note_document(session, credit_note_id, caller_society_id)
        url = await self.storage_service.generate_presigned_download_url(
            session=session,
            document_id=doc.id,
            caller_society_id=doc.society_id,
            expires_in_seconds=expires_in_seconds,
        )
        return PlatformDocumentDownloadUrlResponse(
            document_id=doc.id,
            document_number=doc.document_number,
            download_url=url,
            expires_in_seconds=min(expires_in_seconds, 300),
            sha256_checksum=doc.sha256_checksum,
        )

    async def send_invoice_email(
        self,
        session: AsyncSession,
        invoice_id: UUID,
        caller_society_id: UUID | None = None,
        payload: PlatformDocumentEmailRequest | None = None,
    ) -> PlatformDocumentDeliveryResponse:
        """Enqueue and execute reliable invoice email dispatch."""
        doc, pdf_bytes = await self.get_or_generate_invoice_document(session, invoice_id, caller_society_id)

        invoice_stmt = (
            select(PlatformInvoice)
            .options(selectinload(PlatformInvoice.society))
            .where(PlatformInvoice.id == invoice_id)
        )
        inv = (await session.execute(invoice_stmt)).scalar_one()

        download_url = await self.storage_service.generate_presigned_download_url(
            session=session,
            document_id=doc.id,
            caller_society_id=doc.society_id,
            expires_in_seconds=300,
        )
        subject, html, text = self.email_service.render_invoice_email(inv, inv.society, download_url)

        delivery = await self.email_service.queue_delivery(
            session=session,
            document=doc,
            recipient_email=payload.recipient_email if payload else None,
            idempotency_key=payload.idempotency_key if payload else None,
        )

        completed_delivery = await self.email_service.execute_delivery(
            session=session,
            delivery_id=delivery.id,
            subject=subject,
            html_body=html,
            text_body=text,
            pdf_bytes=pdf_bytes,
            filename=f"{doc.document_number}.pdf",
        )

        return self._to_delivery_response(completed_delivery)

    async def send_credit_note_email(
        self,
        session: AsyncSession,
        credit_note_id: UUID,
        caller_society_id: UUID | None = None,
        payload: PlatformDocumentEmailRequest | None = None,
    ) -> PlatformDocumentDeliveryResponse:
        """Enqueue and execute reliable credit note email dispatch."""
        doc, pdf_bytes = await self.get_or_generate_credit_note_document(session, credit_note_id, caller_society_id)

        cn_stmt = (
            select(PlatformCreditNote)
            .options(
                selectinload(PlatformCreditNote.invoice),
                selectinload(PlatformCreditNote.society),
            )
            .where(PlatformCreditNote.id == credit_note_id)
        )
        cn = (await session.execute(cn_stmt)).scalar_one()

        download_url = await self.storage_service.generate_presigned_download_url(
            session=session,
            document_id=doc.id,
            caller_society_id=doc.society_id,
            expires_in_seconds=300,
        )
        subject, html, text = self.email_service.render_credit_note_email(cn, cn.invoice, cn.society, download_url)

        delivery = await self.email_service.queue_delivery(
            session=session,
            document=doc,
            recipient_email=payload.recipient_email if payload else None,
            idempotency_key=payload.idempotency_key if payload else None,
        )

        completed_delivery = await self.email_service.execute_delivery(
            session=session,
            delivery_id=delivery.id,
            subject=subject,
            html_body=html,
            text_body=text,
            pdf_bytes=pdf_bytes,
            filename=f"{doc.document_number}.pdf",
        )

        return self._to_delivery_response(completed_delivery)

    async def list_document_deliveries(
        self,
        session: AsyncSession,
        document_id: UUID,
        caller_society_id: UUID | None = None,
    ) -> list[PlatformDocumentDeliveryResponse]:
        """Fetch delivery audit history and provider attempts for a document."""
        stmt = (
            select(PlatformDocumentDelivery)
            .options(selectinload(PlatformDocumentDelivery.attempts))
            .where(PlatformDocumentDelivery.document_id == document_id)
        )
        if caller_society_id:
            stmt = stmt.where(PlatformDocumentDelivery.society_id == caller_society_id)

        stmt = stmt.order_by(PlatformDocumentDelivery.created_at.desc())
        res = await session.execute(stmt)
        deliveries = res.scalars().all()
        return [self._to_delivery_response(d) for d in deliveries]

    def _to_delivery_response(self, d: PlatformDocumentDelivery) -> PlatformDocumentDeliveryResponse:
        return PlatformDocumentDeliveryResponse(
            id=d.id,
            society_id=d.society_id,
            document_id=d.document_id,
            channel=d.channel,
            recipient_email=d.recipient_email,
            status=d.status,
            attempt_count=d.attempt_count,
            max_attempts=d.max_attempts,
            next_retry_at=d.next_retry_at,
            sent_at=d.sent_at,
            error_message=d.error_message,
            idempotency_key=d.idempotency_key,
            attempts=[
                PlatformDeliveryAttemptResponse(
                    id=a.id,
                    attempt_number=a.attempt_number,
                    status=a.status,
                    provider_name=a.provider_name,
                    provider_response_code=a.provider_response_code,
                    provider_request_id=a.provider_request_id,
                    error_message=a.error_message,
                    latency_ms=a.latency_ms,
                    created_at=a.created_at,
                )
                for a in getattr(d, "attempts", [])
            ],
        )
