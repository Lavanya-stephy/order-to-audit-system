"""
invoices/pdf.py

Generates a GST-compliant A4 tax invoice PDF using ReportLab.

Features:
- Bundled Unicode DejaVu Sans font with ₹ (rupee) glyph support,
  with graceful fallback to Helvetica and "Rs." if font is unavailable.
- Precision column sizing so "CGST %" and "SGST %" do not break mid-word.
- Indian currency "Amount in words" (e.g. "Rupees Seven Thousand Eight Hundred and Seventy-Five Only").
- Mandatory evaluation footer: "Declaration: dummy data for evaluation".
"""
from decimal import Decimal
from io import BytesIO
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable,
)
from reportlab.lib.enums import TA_RIGHT, TA_CENTER, TA_LEFT
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont


FACTORY_NAME    = "Demo Snacks Pvt Ltd"
FACTORY_ADDRESS = "12 Industrial Estate, Tiruchirappalli - 620001, Tamil Nadu"
FACTORY_GSTIN   = "33AAAAA0000A1Z5"
FACTORY_STATE   = "Tamil Nadu (33)"

FONTS_DIR = Path(__file__).resolve().parent / 'fonts'
DEJAVU_PATH = FONTS_DIR / 'DejaVuSans.ttf'


def get_pdf_fonts():
    """
    Registers and returns (font_family, bold_font, rupee_symbol).
    Uses DejaVu Sans (supporting ₹) if available, falling back to Helvetica and 'Rs.'.
    """
    if 'DejaVuSans' in pdfmetrics.getRegisteredFontNames():
        return 'DejaVuSans', 'DejaVuSans-Bold', '₹'

    if DEJAVU_PATH.exists():
        try:
            font_path_str = str(DEJAVU_PATH)
            pdfmetrics.registerFont(TTFont('DejaVuSans', font_path_str))
            pdfmetrics.registerFont(TTFont('DejaVuSans-Bold', font_path_str))
            pdfmetrics.registerFontFamily('DejaVuSans', normal='DejaVuSans', bold='DejaVuSans-Bold')
            return 'DejaVuSans', 'DejaVuSans-Bold', '₹'
        except Exception:
            pass

    return 'Helvetica', 'Helvetica-Bold', 'Rs.'


def num_to_words_below_1000(n: int) -> str:
    ones = ['', 'One', 'Two', 'Three', 'Four', 'Five', 'Six', 'Seven', 'Eight', 'Nine',
            'Ten', 'Eleven', 'Twelve', 'Thirteen', 'Fourteen', 'Fifteen', 'Sixteen',
            'Seventeen', 'Eighteen', 'Nineteen']
    tens = ['', '', 'Twenty', 'Thirty', 'Forty', 'Fifty', 'Sixty', 'Seventy', 'Eighty', 'Ninety']
    res = []
    if n >= 100:
        res.append(ones[n // 100] + ' Hundred')
        n %= 100
    if n >= 20:
        ten_str = tens[n // 10]
        unit = n % 10
        if unit > 0:
            res.append(f'{ten_str}-{ones[unit]}')
        else:
            res.append(ten_str)
    elif n > 0:
        res.append(ones[n])
    if len(res) == 2 and 'Hundred' in res[0]:
        return ' and '.join(res)
    return ' '.join(res)


def integer_to_words_indian(n: int) -> str:
    if n == 0:
        return 'Zero'
    crores = n // 10000000
    n %= 10000000
    lakhs = n // 100000
    n %= 100000
    thousands = n // 1000
    n %= 1000
    remainder = n
    parts = []
    if crores > 0:
        parts.append(integer_to_words_indian(crores) + ' Crore')
    if lakhs > 0:
        parts.append(integer_to_words_indian(lakhs) + ' Lakh')
    if thousands > 0:
        parts.append(integer_to_words_indian(thousands) + ' Thousand')
    if remainder > 0:
        parts.append(num_to_words_below_1000(remainder))
    return ' '.join(parts)


def amount_to_words(amount) -> str:
    """
    Converts amount to Indian currency words,
    e.g. 7875 -> 'Rupees Seven Thousand Eight Hundred and Seventy-Five Only'.
    """
    d = Decimal(str(amount)).quantize(Decimal('0.01'))
    rupees = int(d)
    paise = int((d - Decimal(rupees)) * 100)
    words = integer_to_words_indian(rupees)
    if paise > 0:
        paise_words = integer_to_words_indian(paise)
        return f"Rupees {words} and {paise_words} Paise Only"
    return f"Rupees {words} Only"


def _format_curr(val, symbol: str) -> str:
    return f"{symbol} {val:,.2f}"


def build_invoice_pdf(invoice) -> BytesIO:
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        rightMargin=12 * mm,
        leftMargin=12 * mm,
        topMargin=12 * mm,
        bottomMargin=12 * mm,
    )

    font_family, bold_font, curr = get_pdf_fonts()

    styles = getSampleStyleSheet()
    bold   = ParagraphStyle('Bold',   parent=styles['Normal'], fontName=bold_font, fontSize=9, leading=12)
    small  = ParagraphStyle('Small',  parent=styles['Normal'], fontName=font_family, fontSize=8, leading=10)
    right  = ParagraphStyle('Right',  parent=styles['Normal'], fontName=font_family, alignment=TA_RIGHT)
    center = ParagraphStyle('Center', parent=styles['Normal'], fontName=font_family, alignment=TA_CENTER)
    h1     = ParagraphStyle('H1', parent=styles['Normal'], fontSize=14, fontName=bold_font, alignment=TA_CENTER)
    bold_r = ParagraphStyle('BoldR', parent=styles['Normal'], fontName=bold_font, fontSize=9, leading=12, alignment=TA_RIGHT)

    story = []
    W = doc.width  # 186 mm

    # ── Header ───────────────────────────────────────────────────────────────
    story.append(Paragraph("TAX INVOICE", h1))
    story.append(Spacer(1, 3 * mm))

    status_label = ""
    if invoice.status == 'cancelled':
        status_label = " [CANCELLED]"

    # Two-column header: Supplier left, Invoice details right
    supplier_col = [
        Paragraph(f"<b>{FACTORY_NAME}</b>", bold),
        Paragraph(FACTORY_ADDRESS, small),
        Paragraph(f"GSTIN: {FACTORY_GSTIN}", small),
        Paragraph(f"State: {FACTORY_STATE}", small),
    ]
    inv_details_col = [
        Paragraph(f"<b>Invoice No:</b> {invoice.invoice_number}{status_label}", bold),
        Paragraph(f"<b>Invoice Date:</b> {invoice.invoice_date.strftime('%d %b %Y')}", small),
    ]
    if invoice.credit_note_number:
        inv_details_col.append(
            Paragraph(f"<b>Credit Note:</b> {invoice.credit_note_number}", small)
        )

    hdr_data = [[supplier_col, inv_details_col]]
    hdr_table = Table(hdr_data, colWidths=[W * 0.6, W * 0.4])
    hdr_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING',  (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
    ]))
    story.append(hdr_table)
    story.append(Spacer(1, 3 * mm))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor('#1e3a8a')))
    story.append(Spacer(1, 3 * mm))

    # ── Bill To & Order Reference ─────────────────────────────────────────────
    customer = invoice.customer
    bill_to = [
        Paragraph("<b>BILL TO</b>", bold),
        Paragraph(f"<b>{customer.name}</b>", bold),
        Paragraph(customer.get_customer_type_display(), small),
    ]
    if customer.address:
        bill_to.append(Paragraph(customer.address, small))
    bill_to.append(Paragraph(f"{customer.city + ', ' if customer.city else ''}{customer.state} - {customer.state_code}", small))
    if invoice.customer_gstin:
        bill_to.append(Paragraph(f"GSTIN: {invoice.customer_gstin}", small))

    tax_type_str = "Inter-state Supply (IGST)" if invoice.is_interstate else "Intra-state Supply - Tamil Nadu (CGST + SGST)"
    order_col = [
        Paragraph("<b>ORDER REFERENCE</b>", bold),
        Paragraph(f"<b>SO No:</b> {invoice.order.order_number}", small),
        Paragraph(f"<b>Order Date:</b> {invoice.order.order_date.strftime('%d %b %Y')}", small),
        Spacer(1, 1.5 * mm),
        Paragraph(f"<b>Tax Type:</b> {tax_type_str}", small),
        Paragraph(f"<b>Place of Supply:</b> {customer.state} ({customer.state_code})", small),
    ]

    bill_data = [[bill_to, order_col]]
    bill_table = Table(bill_data, colWidths=[W * 0.5, W * 0.5])
    bill_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING',  (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 2 * mm),
        ('LINEAFTER', (0, 0), (0, -1), 0.5, colors.lightgrey),
    ]))
    story.append(bill_table)
    story.append(Spacer(1, 3.5 * mm))

    # ── Line Items Table ──────────────────────────────────────────────────────
    # Column widths and styles crafted so headers never wrap mid-word
    th_style = ParagraphStyle(
        'TH',
        parent=styles['Normal'],
        fontName=bold_font,
        fontSize=7,
        leading=8.5,
        alignment=TA_CENTER,
        textColor=colors.white,
    )

    if invoice.is_interstate:
        col_headers = [
            '#', 'Description / HSN', 'Qty', 'Unit',
            f'Rate ({curr})', f'Taxable ({curr})',
            'IGST %', f'IGST ({curr})', f'Total ({curr})',
        ]
        col_w = [7*mm, 52*mm, 13*mm, 12*mm, 18*mm, 22*mm, 18*mm, 21*mm, 23*mm]
    else:
        col_headers = [
            '#', 'Description / HSN', 'Qty', 'Unit',
            f'Rate ({curr})', f'Taxable ({curr})',
            'CGST %', f'CGST ({curr})',
            'SGST %', f'SGST ({curr})',
            f'Total ({curr})',
        ]
        col_w = [6*mm, 40*mm, 10*mm, 10*mm, 15*mm, 18*mm, 16*mm, 17*mm, 16*mm, 17*mm, 21*mm]

    header_row = [Paragraph(h, th_style) for h in col_headers]
    rows = [header_row]

    cell_style = ParagraphStyle('Cell', parent=styles['Normal'], fontName=font_family, fontSize=7.5, leading=9.5)
    cell_desc = ParagraphStyle('CellDesc', parent=styles['Normal'], fontName=font_family, fontSize=7.5, leading=9.5)

    for idx, line in enumerate(invoice.lines.all(), 1):
        desc = Paragraph(
            f"<b>{line.product.name}</b><br/><font size='6.5' color='grey'>HSN: {line.hsn_code}</font>",
            cell_desc,
        )
        if invoice.is_interstate:
            row = [
                str(idx), desc,
                f"{line.quantity:.0f}", line.unit.symbol,
                f"{line.unit_price:.2f}", f"{line.taxable_value:.2f}",
                f"{line.igst_rate:.2f}%", f"{line.igst_amount:.2f}",
                f"{line.line_total:.2f}",
            ]
        else:
            row = [
                str(idx), desc,
                f"{line.quantity:.0f}", line.unit.symbol,
                f"{line.unit_price:.2f}", f"{line.taxable_value:.2f}",
                f"{line.cgst_rate:.2f}%", f"{line.cgst_amount:.2f}",
                f"{line.sgst_rate:.2f}%", f"{line.sgst_amount:.2f}",
                f"{line.line_total:.2f}",
            ]
        rows.append(row)

    items_table = Table(rows, colWidths=col_w, repeatRows=1)
    items_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1e3a8a')),
        ('TEXTCOLOR',  (0, 0), (-1, 0), colors.white),
        ('FONTNAME',   (0, 0), (-1, -1), font_family),
        ('FONTSIZE',   (0, 0), (-1, -1), 7.5),
        ('ALIGN',      (0, 0), (-1, -1), 'CENTER'),
        ('ALIGN',      (1, 1), (1, -1), 'LEFT'),
        ('VALIGN',     (0, 0), (-1, -1), 'MIDDLE'),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8fafc')]),
        ('GRID',       (0, 0), (-1, -1), 0.4, colors.lightgrey),
        ('TOPPADDING', (0, 0), (-1, -1), 2.5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2.5),
        ('LEFTPADDING',  (0, 0), (-1, -1), 2),
        ('RIGHTPADDING', (0, 0), (-1, -1), 2),
    ]))
    story.append(items_table)
    story.append(Spacer(1, 3 * mm))

    # ── Totals ────────────────────────────────────────────────────────────────
    totals = [
        ['Taxable Value', _format_curr(invoice.taxable_value, curr)],
    ]
    if invoice.is_interstate:
        totals.append(['IGST', _format_curr(invoice.igst_amount, curr)])
    else:
        totals.append(['CGST', _format_curr(invoice.cgst_amount, curr)])
        totals.append(['SGST', _format_curr(invoice.sgst_amount, curr)])
    totals.append(['', ''])
    totals.append([Paragraph('<b>GRAND TOTAL</b>', bold), Paragraph(f'<b>{_format_curr(invoice.grand_total, curr)}</b>', bold_r)])

    totals_table = Table(totals, colWidths=[W * 0.70, W * 0.30])
    totals_table.setStyle(TableStyle([
        ('ALIGN',      (1, 0), (1, -1), 'RIGHT'),
        ('FONTNAME',   (0, 0), (-1, -1), font_family),
        ('FONTSIZE',   (0, 0), (-1, -1), 8.5),
        ('LINEABOVE',  (0, -1), (-1, -1), 1, colors.HexColor('#1e3a8a')),
        ('LINEBELOW',  (0, -1), (-1, -1), 1, colors.HexColor('#1e3a8a')),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ('LEFTPADDING',  (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
    ]))
    story.append(totals_table)
    story.append(Spacer(1, 2.5 * mm))

    # ── Amount in Words ───────────────────────────────────────────────────────
    words = amount_to_words(invoice.grand_total)
    words_style = ParagraphStyle(
        'Words',
        parent=styles['Normal'],
        fontName=font_family,
        fontSize=8,
        leading=10.5,
        textColor=colors.HexColor('#1e293b'),
    )
    story.append(Paragraph(f"<b>Amount in words:</b> {words}", words_style))
    story.append(Spacer(1, 3.5 * mm))

    # ── Dispatch / Cancellation Status ────────────────────────────────────────
    if invoice.is_dispatched:
        story.append(Paragraph(
            f"<font color='green'><b>Dispatched:</b> {invoice.dispatch_ledger_note}</font>",
            small,
        ))
    if invoice.status == 'cancelled':
        story.append(Paragraph(
            f"<font color='red'><b>CANCELLED</b> - Credit Note: {invoice.credit_note_number} | "
            f"Reason: {invoice.cancellation_reason}</font>",
            small,
        ))

    # ── Footer ────────────────────────────────────────────────────────────────
    story.append(Spacer(1, 4 * mm))
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.lightgrey))
    story.append(Spacer(1, 1.5 * mm))

    decl_style = ParagraphStyle(
        'Decl',
        parent=styles['Normal'],
        fontName=font_family,
        fontSize=7.5,
        leading=9.5,
        textColor=colors.HexColor('#334155'),
    )
    story.append(Paragraph("<b>Declaration: dummy data for evaluation</b>", decl_style))
    story.append(Spacer(1, 0.5 * mm))
    story.append(Paragraph(
        "All data in this system is dummy data for evaluation.",
        ParagraphStyle('EvalNote', parent=styles['Normal'], fontName=font_family, fontSize=7, leading=8.5, textColor=colors.HexColor('#64748b')),
    ))
    story.append(Spacer(1, 0.5 * mm))
    story.append(Paragraph(
        f"This is a computer-generated invoice from {FACTORY_NAME}. No signature required. Subject to Tiruchirappalli jurisdiction.",
        ParagraphStyle('Muted', parent=styles['Normal'], fontName=font_family, fontSize=7, leading=8.5, textColor=colors.grey),
    ))

    doc.build(story)
    buf.seek(0)
    return buf
