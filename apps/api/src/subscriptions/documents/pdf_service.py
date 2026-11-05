"""Phase 21E.4D — Statutory Billing PDF Generation Service.

Renders official B2B SaaS Tax Invoices and Credit Notes via ReportLab:
- Strictly binds to finalized database entities and verified immutable TaxSnapshots.
- Never recalculates or modifies financial amounts in the presentation layer.
- Enforces statutory GST rules (SAC 998313, CGST/SGST/IGST breakdown, Place of Supply, GSTINs).
- Computes canonical SHA-256 digest on output bytes for tamper detection.
"""

import hashlib
import io
from decimal import Decimal
from typing import Final

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    HRFlowable,
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from apps.api.src.database.models.platform_billing import (
    PlatformCreditNote,
    PlatformCreditNoteItem,
    PlatformInvoice,
    PlatformInvoiceItem,
)
from apps.api.src.database.models.society import Society
from apps.api.src.subscriptions.documents.exceptions import DraftDocumentAccessDeniedException
from apps.api.src.subscriptions.documents.issuer import BillingIssuerConfig, get_issuer_config
from apps.api.src.subscriptions.tax.snapshot import TaxSnapshot

PAGE_WIDTH, PAGE_HEIGHT = A4

PRIMARY_COLOR: Final = colors.HexColor("#1A365D")  # Deep Navy
SECONDARY_COLOR: Final = colors.HexColor("#2B6CB0")  # Slate Blue
ACCENT_COLOR: Final = colors.HexColor("#2C5282")
TEXT_DARK: Final = colors.HexColor("#2D3748")  # Charcoal
BG_LIGHT: Final = colors.HexColor("#F7FAFC")
BORDER_COLOR: Final = colors.HexColor("#E2E8F0")


def _format_currency(val: Decimal | float | None) -> str:
    """Format Decimal into Indian Rupee string format."""
    if val is None:
        return "₹0.00"
    dec_val = Decimal(str(val))
    return f"₹{dec_val:,.2f}"


def _format_date(dt) -> str:
    if not dt:
        return "N/A"
    return dt.strftime("%d-%b-%Y")


class BillingPDFService:
    """Enterprise PDF generation engine for SocietySphere SaaS billing."""

    def __init__(self, issuer_config: BillingIssuerConfig | None = None) -> None:
        self.issuer = issuer_config or get_issuer_config()
        self._setup_styles()

    def _setup_styles(self) -> None:
        self.styles = getSampleStyleSheet()
        self.title_style = ParagraphStyle(
            "DocTitle",
            parent=self.styles["Heading1"],
            fontSize=18,
            leading=22,
            textColor=PRIMARY_COLOR,
            fontName="Helvetica-Bold",
        )
        self.subtitle_style = ParagraphStyle(
            "DocSubtitle",
            parent=self.styles["Normal"],
            fontSize=9,
            leading=12,
            textColor=TEXT_DARK,
            fontName="Helvetica",
        )
        self.header_label_style = ParagraphStyle(
            "HeaderLabel",
            parent=self.styles["Normal"],
            fontSize=8,
            leading=10,
            textColor=colors.HexColor("#718096"),
            fontName="Helvetica-Bold",
        )
        self.body_style = ParagraphStyle(
            "DocBody",
            parent=self.styles["Normal"],
            fontSize=8,
            leading=11,
            textColor=TEXT_DARK,
            fontName="Helvetica",
        )
        self.body_bold_style = ParagraphStyle(
            "DocBodyBold",
            parent=self.styles["Normal"],
            fontSize=8,
            leading=11,
            textColor=TEXT_DARK,
            fontName="Helvetica-Bold",
        )
        self.table_header_style = ParagraphStyle(
            "TableHeader",
            parent=self.styles["Normal"],
            fontSize=8,
            leading=10,
            textColor=colors.white,
            fontName="Helvetica-Bold",
            alignment=1,  # Center
        )
        self.table_cell_style = ParagraphStyle(
            "TableCell",
            parent=self.styles["Normal"],
            fontSize=7.5,
            leading=10,
            textColor=TEXT_DARK,
            fontName="Helvetica",
        )
        self.table_cell_right_style = ParagraphStyle(
            "TableCellRight",
            parent=self.styles["Normal"],
            fontSize=7.5,
            leading=10,
            textColor=TEXT_DARK,
            fontName="Helvetica",
            alignment=2,  # Right
        )
        self.table_cell_bold_right_style = ParagraphStyle(
            "TableCellBoldRight",
            parent=self.styles["Normal"],
            fontSize=8,
            leading=11,
            textColor=PRIMARY_COLOR,
            fontName="Helvetica-Bold",
            alignment=2,  # Right
        )

    def generate_invoice_pdf(
        self,
        invoice: PlatformInvoice,
        items: list[PlatformInvoiceItem],
        snapshot: TaxSnapshot,
        society: Society,
    ) -> tuple[bytes, str]:
        """Render a finalized PlatformInvoice into PDF bytes and calculate its SHA-256 digest."""
        if invoice.status == "DRAFT":
            raise DraftDocumentAccessDeniedException(
                document_type="INVOICE",
                document_id=invoice.id,
                status=invoice.status,
            )

        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            leftMargin=12 * mm,
            rightMargin=12 * mm,
            topMargin=12 * mm,
            bottomMargin=12 * mm,
        )

        story = []

        # 1. Header: Issuer & Document Metadata
        issuer_text = (
            f"<b>{self.issuer.legal_name}</b><br/>"
            f"CIN: {self.issuer.cin} | PAN: {self.issuer.pan}<br/>"
            f"GSTIN: <b>{self.issuer.gstin}</b><br/>"
            f"{self.issuer.registered_address}<br/>"
            f"Email: {self.issuer.billing_email} | State: {self.issuer.state_name} ({self.issuer.state_code})"
        )
        invoice_meta_text = (
            f"<font size=14 color='#1A365D'><b>TAX INVOICE</b></font><br/><br/>"
            f"<b>Invoice No:</b> {invoice.invoice_number}<br/>"
            f"<b>Issue Date:</b> {_format_date(invoice.issued_at)}<br/>"
            f"<b>Financial Year:</b> {invoice.fiscal_year or 'N/A'}<br/>"
            f"<b>Due Date:</b> {_format_date(invoice.due_date)}<br/>"
            f"<b>Status:</b> <b><font color='{'#276749' if invoice.status == 'PAID' else '#C53030'}'>{invoice.status}</font></b>"
        )
        header_table = Table(
            [
                [Paragraph(issuer_text, self.body_style), Paragraph(invoice_meta_text, self.body_style)],
            ],
            colWidths=[105 * mm, 81 * mm],
        )
        header_table.setStyle(
            TableStyle([
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("PADDING", (0, 0), (-1, -1), 0),
            ])
        )
        story.append(header_table)
        story.append(Spacer(1, 4 * mm))
        story.append(HRFlowable(width="100%", thickness=1, color=SECONDARY_COLOR))
        story.append(Spacer(1, 4 * mm))

        # 2. Customer / Society Details
        soc_addr = f"{society.address_line1}, {society.city}, {society.state} - {society.postal_code}"
        customer_text = (
            f"<b>BILLED TO (CUSTOMER):</b><br/>"
            f"<b>{society.legal_name}</b> (Reg: {society.registration_number or 'N/A'})<br/>"
            f"Address: {soc_addr}<br/>"
            f"GSTIN: <b>{invoice.customer_gstin or 'Unregistered Consumer'}</b><br/>"
            f"Place of Supply: <b>{invoice.place_of_supply}</b>"
        )
        billing_period_text = (
            f"<b>SUBSCRIPTION DETAILS:</b><br/>"
            f"Billing Cycle: <b>{invoice.billing_cycle}</b><br/>"
            f"Period: {_format_date(invoice.period_start)} to {_format_date(invoice.period_end)}<br/>"
            f"SAC Code: <b>{invoice.sac_code}</b> (Cloud Software SaaS Services)<br/>"
            f"Tax Regime: <b>{snapshot.supply_type.value if hasattr(snapshot.supply_type, 'value') else snapshot.supply_type}</b> ({snapshot.place_of_supply})"
        )
        client_table = Table(
            [
                [Paragraph(customer_text, self.body_style), Paragraph(billing_period_text, self.body_style)],
            ],
            colWidths=[105 * mm, 81 * mm],
        )
        client_table.setStyle(
            TableStyle([
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("BACKGROUND", (0, 0), (-1, -1), BG_LIGHT),
                ("BOX", (0, 0), (-1, -1), 0.5, BORDER_COLOR),
                ("PADDING", (0, 0), (-1, -1), 6),
            ])
        )
        story.append(client_table)
        story.append(Spacer(1, 5 * mm))

        # 3. Line Items Table
        item_rows = [
            [
                Paragraph("#", self.table_header_style),
                Paragraph("Description", self.table_header_style),
                Paragraph("SAC", self.table_header_style),
                Paragraph("Qty", self.table_header_style),
                Paragraph("Unit Price", self.table_header_style),
                Paragraph("Taxable", self.table_header_style),
                Paragraph("Rate", self.table_header_style),
                Paragraph("Tax", self.table_header_style),
                Paragraph("Total", self.table_header_style),
            ]
        ]

        for itm in sorted(items, key=lambda x: x.item_index):
            item_rows.append([
                Paragraph(str(itm.item_index), self.table_cell_style),
                Paragraph(itm.description, self.table_cell_style),
                Paragraph(itm.sac_code, self.table_cell_style),
                Paragraph(f"{itm.quantity:.2f}", self.table_cell_right_style),
                Paragraph(_format_currency(itm.unit_price), self.table_cell_right_style),
                Paragraph(_format_currency(itm.taxable_amount), self.table_cell_right_style),
                Paragraph(f"{itm.tax_rate:.1f}%", self.table_cell_right_style),
                Paragraph(_format_currency(itm.tax_amount), self.table_cell_right_style),
                Paragraph(_format_currency(itm.total_amount), self.table_cell_bold_right_style),
            ])

        items_table = Table(
            item_rows,
            colWidths=[8 * mm, 50 * mm, 16 * mm, 14 * mm, 22 * mm, 24 * mm, 14 * mm, 18 * mm, 20 * mm],
        )
        items_table.setStyle(
            TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), PRIMARY_COLOR),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("GRID", (0, 0), (-1, -1), 0.5, BORDER_COLOR),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, BG_LIGHT]),
                ("PADDING", (0, 0), (-1, -1), 4),
            ])
        )
        story.append(items_table)
        story.append(Spacer(1, 4 * mm))

        # 4. Financial Summary Breakdown (Strictly matching entity amounts)
        summary_data = [
            [Paragraph("Subtotal (Base Plan / Charges):", self.body_style), Paragraph(_format_currency(invoice.subtotal), self.table_cell_right_style)],
        ]
        if invoice.discount_total > 0:
            summary_data.append([
                Paragraph("Commercial Discount:", self.body_style),
                Paragraph(f"-{_format_currency(invoice.discount_total)}", self.table_cell_right_style),
            ])
        if invoice.prorated_credit > 0:
            summary_data.append([
                Paragraph("Prorated Subscription Credit:", self.body_style),
                Paragraph(f"-{_format_currency(invoice.prorated_credit)}", self.table_cell_right_style),
            ])
        summary_data.extend([
            [Paragraph("<b>Net Taxable Amount:</b>", self.body_bold_style), Paragraph(f"<b>{_format_currency(invoice.taxable_amount)}</b>", self.table_cell_bold_right_style)],
            [Paragraph(f"CGST ({snapshot.cgst_rate}%):", self.body_style), Paragraph(_format_currency(invoice.cgst_amount), self.table_cell_right_style)],
            [Paragraph(f"SGST ({snapshot.sgst_rate}%):", self.body_style), Paragraph(_format_currency(invoice.sgst_amount), self.table_cell_right_style)],
            [Paragraph(f"IGST ({snapshot.igst_rate}%):", self.body_style), Paragraph(_format_currency(invoice.igst_amount), self.table_cell_right_style)],
            [Paragraph("Total GST:", self.body_style), Paragraph(_format_currency(invoice.tax_total), self.table_cell_right_style)],
            [Paragraph("<b>GRAND TOTAL:</b>", self.title_style), Paragraph(f"<b>{_format_currency(invoice.grand_total)}</b>", self.title_style)],
        ])
        if invoice.credits_applied > 0:
            summary_data.append([
                Paragraph("Credit Notes Applied:", self.body_style),
                Paragraph(f"-{_format_currency(invoice.credits_applied)}", self.table_cell_right_style),
            ])
        if invoice.amount_paid > 0:
            summary_data.append([
                Paragraph("Total Amount Paid:", self.body_style),
                Paragraph(_format_currency(invoice.amount_paid), self.table_cell_right_style),
            ])
        summary_data.append([
            Paragraph("<b>BALANCE DUE:</b>", self.body_bold_style),
            Paragraph(f"<b>{_format_currency(invoice.amount_due)}</b>", self.table_cell_bold_right_style),
        ])

        summary_table = Table(
            summary_data,
            colWidths=[110 * mm, 76 * mm],
        )
        summary_table.setStyle(
            TableStyle([
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LINEBELOW", (0, -1), (-1, -1), 1, PRIMARY_COLOR),
                ("PADDING", (0, 0), (-1, -1), 3),
            ])
        )
        story.append(KeepTogether(summary_table))
        story.append(Spacer(1, 6 * mm))

        # 5. Footer and Statutory Declaration
        footer_text = (
            "<b>STATUTORY DECLARATION & AUDIT NOTICE:</b><br/>"
            "1. This is a computer-generated tax invoice issued in accordance with Section 31 of the Central Goods and Services Tax Act, 2017.<br/>"
            "2. Supply of software SaaS services is classified under SAC 998313.<br/>"
            f"3. Immutable Tax Snapshot Reference: {snapshot.snapshot_id} (Signed Digest: {snapshot.integrity_hash[:16]}...).<br/>"
            "4. For billing inquiries, contact billing@societysphere.com."
        )
        story.append(Paragraph(footer_text, self.subtitle_style))

        doc.build(story)
        pdf_bytes = buffer.getvalue()
        buffer.close()

        sha256_hash = hashlib.sha256(pdf_bytes).hexdigest()
        return pdf_bytes, sha256_hash

    def generate_credit_note_pdf(
        self,
        credit_note: PlatformCreditNote,
        items: list[PlatformCreditNoteItem],
        invoice: PlatformInvoice,
        snapshot: TaxSnapshot,
        society: Society,
    ) -> tuple[bytes, str]:
        """Render an issued PlatformCreditNote into PDF bytes and calculate its SHA-256 digest."""
        if credit_note.status == "DRAFT":
            raise DraftDocumentAccessDeniedException(
                document_type="CREDIT_NOTE",
                document_id=credit_note.id,
                status=credit_note.status,
            )

        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            leftMargin=12 * mm,
            rightMargin=12 * mm,
            topMargin=12 * mm,
            bottomMargin=12 * mm,
        )

        story = []

        # 1. Header
        issuer_text = (
            f"<b>{self.issuer.legal_name}</b><br/>"
            f"CIN: {self.issuer.cin} | PAN: {self.issuer.pan}<br/>"
            f"GSTIN: <b>{self.issuer.gstin}</b><br/>"
            f"{self.issuer.registered_address}<br/>"
            f"Email: {self.issuer.billing_email} | State: {self.issuer.state_name} ({self.issuer.state_code})"
        )
        cn_meta_text = (
            f"<font size=14 color='#C53030'><b>TAX CREDIT NOTE</b></font><br/><br/>"
            f"<b>Credit Note No:</b> {credit_note.credit_note_number}<br/>"
            f"<b>Issue Date:</b> {_format_date(credit_note.issued_at)}<br/>"
            f"<b>Financial Year:</b> {credit_note.fiscal_year}<br/>"
            f"<b>Original Invoice No:</b> <b>{invoice.invoice_number}</b><br/>"
            f"<b>Invoice Date:</b> {_format_date(invoice.issued_at)}<br/>"
            f"<b>Status:</b> <b><font color='{'#276749' if credit_note.status == 'ISSUED' else '#718096'}'>{credit_note.status}</font></b>"
        )
        header_table = Table(
            [
                [Paragraph(issuer_text, self.body_style), Paragraph(cn_meta_text, self.body_style)],
            ],
            colWidths=[105 * mm, 81 * mm],
        )
        header_table.setStyle(
            TableStyle([
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("PADDING", (0, 0), (-1, -1), 0),
            ])
        )
        story.append(header_table)
        story.append(Spacer(1, 4 * mm))
        story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#E53E3E")))
        story.append(Spacer(1, 4 * mm))

        # 2. Customer & Reason
        soc_addr = f"{society.address_line1}, {society.city}, {society.state} - {society.postal_code}"
        customer_text = (
            f"<b>ISSUED TO (CUSTOMER):</b><br/>"
            f"<b>{society.legal_name}</b> (Reg: {society.registration_number or 'N/A'})<br/>"
            f"Address: {soc_addr}<br/>"
            f"GSTIN: <b>{invoice.customer_gstin or 'Unregistered Consumer'}</b><br/>"
            f"Place of Supply: <b>{invoice.place_of_supply}</b>"
        )
        reason_text = (
            f"<b>CREDIT ADJUSTMENT DETAILS:</b><br/>"
            f"Statutory Reason: <b>{credit_note.reason}</b><br/>"
            f"Notes: {credit_note.notes or 'Standard credit adjustment against original invoice.'}<br/>"
            f"Original Invoice Total: <b>{_format_currency(invoice.grand_total)}</b><br/>"
            f"Tax Regime: <b>{snapshot.supply_type.value if hasattr(snapshot.supply_type, 'value') else snapshot.supply_type}</b> (Reversal based on original snapshot)"
        )
        client_table = Table(
            [
                [Paragraph(customer_text, self.body_style), Paragraph(reason_text, self.body_style)],
            ],
            colWidths=[105 * mm, 81 * mm],
        )
        client_table.setStyle(
            TableStyle([
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("BACKGROUND", (0, 0), (-1, -1), BG_LIGHT),
                ("BOX", (0, 0), (-1, -1), 0.5, BORDER_COLOR),
                ("PADDING", (0, 0), (-1, -1), 6),
            ])
        )
        story.append(client_table)
        story.append(Spacer(1, 5 * mm))

        # 3. Credit Note Items Table
        item_rows = [
            [
                Paragraph("#", self.table_header_style),
                Paragraph("Description", self.table_header_style),
                Paragraph("SAC", self.table_header_style),
                Paragraph("Qty", self.table_header_style),
                Paragraph("Unit Price", self.table_header_style),
                Paragraph("Taxable", self.table_header_style),
                Paragraph("Rate", self.table_header_style),
                Paragraph("Tax Reversal", self.table_header_style),
                Paragraph("Total Credit", self.table_header_style),
            ]
        ]

        for itm in sorted(items, key=lambda x: x.item_index):
            item_rows.append([
                Paragraph(str(itm.item_index), self.table_cell_style),
                Paragraph(itm.description, self.table_cell_style),
                Paragraph(itm.sac_code, self.table_cell_style),
                Paragraph(f"{itm.quantity:.2f}", self.table_cell_right_style),
                Paragraph(_format_currency(itm.unit_price), self.table_cell_right_style),
                Paragraph(_format_currency(itm.taxable_amount), self.table_cell_right_style),
                Paragraph(f"{itm.tax_rate:.1f}%", self.table_cell_right_style),
                Paragraph(_format_currency(itm.tax_amount), self.table_cell_right_style),
                Paragraph(_format_currency(itm.total_amount), self.table_cell_bold_right_style),
            ])

        items_table = Table(
            item_rows,
            colWidths=[8 * mm, 50 * mm, 16 * mm, 14 * mm, 22 * mm, 24 * mm, 14 * mm, 18 * mm, 20 * mm],
        )
        items_table.setStyle(
            TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#742A2A")),  # Dark Red Header
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("GRID", (0, 0), (-1, -1), 0.5, BORDER_COLOR),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, BG_LIGHT]),
                ("PADDING", (0, 0), (-1, -1), 4),
            ])
        )
        story.append(items_table)
        story.append(Spacer(1, 4 * mm))

        # 4. Financial Summary Breakdown
        summary_data = [
            [Paragraph("Taxable Credit Amount:", self.body_bold_style), Paragraph(_format_currency(credit_note.taxable_amount), self.table_cell_bold_right_style)],
            [Paragraph(f"CGST Reversal ({snapshot.cgst_rate}%):", self.body_style), Paragraph(_format_currency(credit_note.cgst_amount), self.table_cell_right_style)],
            [Paragraph(f"SGST Reversal ({snapshot.sgst_rate}%):", self.body_style), Paragraph(_format_currency(credit_note.sgst_amount), self.table_cell_right_style)],
            [Paragraph(f"IGST Reversal ({snapshot.igst_rate}%):", self.body_style), Paragraph(_format_currency(credit_note.igst_amount), self.table_cell_right_style)],
            [Paragraph("Total GST Reversal:", self.body_style), Paragraph(_format_currency(credit_note.tax_total), self.table_cell_right_style)],
            [Paragraph("<b>TOTAL CREDIT NOTE VALUE:</b>", self.title_style), Paragraph(f"<b>{_format_currency(credit_note.grand_total)}</b>", self.title_style)],
        ]
        summary_table = Table(
            summary_data,
            colWidths=[110 * mm, 76 * mm],
        )
        summary_table.setStyle(
            TableStyle([
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LINEBELOW", (0, -1), (-1, -1), 1, colors.HexColor("#742A2A")),
                ("PADDING", (0, 0), (-1, -1), 3),
            ])
        )
        story.append(KeepTogether(summary_table))
        story.append(Spacer(1, 6 * mm))

        # 5. Statutory Declaration
        footer_text = (
            "<b>STATUTORY CREDIT NOTE NOTICE:</b><br/>"
            "1. Issued in accordance with Section 34 of the Central Goods and Services Tax Act, 2017.<br/>"
            f"2. References original Tax Invoice {invoice.invoice_number} dated {_format_date(invoice.issued_at)}.<br/>"
            f"3. Original Tax Snapshot Reference: {snapshot.snapshot_id} (Integrity Digest: {snapshot.integrity_hash[:16]}...).<br/>"
            "4. The customer agrees to reverse proportionate Input Tax Credit (ITC) if previously claimed."
        )
        story.append(Paragraph(footer_text, self.subtitle_style))

        doc.build(story)
        pdf_bytes = buffer.getvalue()
        buffer.close()

        sha256_hash = hashlib.sha256(pdf_bytes).hexdigest()
        return pdf_bytes, sha256_hash
