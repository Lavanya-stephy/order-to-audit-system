from decimal import Decimal
from io import BytesIO
from typing import List, Dict, Any, Optional

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable,
)
from reportlab.lib.enums import TA_RIGHT, TA_CENTER, TA_LEFT

from invoices.pdf import get_pdf_fonts, FACTORY_NAME, FACTORY_ADDRESS, FACTORY_GSTIN


def _create_report_doc(buffer: BytesIO, orientation: str = 'portrait') -> SimpleDocTemplate:
    pagesize = landscape(A4) if orientation == 'landscape' else A4
    return SimpleDocTemplate(
        buffer,
        pagesize=pagesize,
        leftMargin=10 * mm,
        rightMargin=10 * mm,
        topMargin=10 * mm,
        bottomMargin=10 * mm,
    )


def _get_styles():
    font_name, bold_font, rupee = get_pdf_fonts()
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        'RepTitle',
        parent=styles['Normal'],
        fontName=bold_font,
        fontSize=13,
        leading=16,
        textColor=colors.HexColor('#1e3a8a'),
        alignment=TA_LEFT,
    )
    subtitle_style = ParagraphStyle(
        'RepSub',
        parent=styles['Normal'],
        fontName=font_name,
        fontSize=8,
        leading=11,
        textColor=colors.HexColor('#475569'),
        alignment=TA_LEFT,
    )
    meta_style = ParagraphStyle(
        'RepMeta',
        parent=styles['Normal'],
        fontName=font_name,
        fontSize=7.5,
        leading=10,
        textColor=colors.HexColor('#64748b'),
        alignment=TA_RIGHT,
    )
    th_style = ParagraphStyle(
        'RepTH',
        parent=styles['Normal'],
        fontName=bold_font,
        fontSize=7,
        leading=9,
        textColor=colors.HexColor('#0f172a'),
        alignment=TA_CENTER,
    )
    td_left = ParagraphStyle(
        'RepTDL',
        parent=styles['Normal'],
        fontName=font_name,
        fontSize=6.5,
        leading=8.5,
        textColor=colors.HexColor('#1e293b'),
        alignment=TA_LEFT,
    )
    td_right = ParagraphStyle(
        'RepTDR',
        parent=styles['Normal'],
        fontName=font_name,
        fontSize=6.5,
        leading=8.5,
        textColor=colors.HexColor('#1e293b'),
        alignment=TA_RIGHT,
    )
    td_bold_right = ParagraphStyle(
        'RepTDBR',
        parent=styles['Normal'],
        fontName=bold_font,
        fontSize=6.5,
        leading=8.5,
        textColor=colors.HexColor('#0f172a'),
        alignment=TA_RIGHT,
    )

    return {
        'title': title_style,
        'subtitle': subtitle_style,
        'meta': meta_style,
        'th': th_style,
        'td_left': td_left,
        'td_right': td_right,
        'td_bold_right': td_bold_right,
        'font': font_name,
        'bold': bold_font,
        'rupee': rupee,
    }


def _build_header_flowable(title: str, subtitle: str, period_str: str, styles: dict):
    header_data = [
        [
            Paragraph(f"<b>{FACTORY_NAME}</b><br/>{title}", styles['title']),
            Paragraph(f"GSTIN: {FACTORY_GSTIN}<br/>Period: {period_str}<br/>Generated: Today", styles['meta']),
        ]
    ]
    t = Table(header_data, colWidths=['65%', '35%'])
    t.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    return t


# ---------------------------------------------------------------------------
# 1. Sales Register PDF
# ---------------------------------------------------------------------------

def build_sales_register_pdf(data: dict, period_str: str = "All Time") -> BytesIO:
    buf = BytesIO()
    doc = _create_report_doc(buf, orientation='landscape')
    styles = _get_styles()
    rupee = styles['rupee']

    elements = []
    elements.append(_build_header_flowable("Monthly Sales Register & Outward Invoices", "GST Outward Supplies", period_str, styles))
    elements.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor('#cbd5e1'), spaceAfter=6, spaceBefore=4))

    table_data = [
        [
            Paragraph("<b>Invoice No</b>", styles['th']),
            Paragraph("<b>Date</b>", styles['th']),
            Paragraph("<b>Customer Name</b>", styles['th']),
            Paragraph("<b>Place of Supply</b>", styles['th']),
            Paragraph("<b>Taxable Val</b>", styles['th']),
            Paragraph("<b>CGST</b>", styles['th']),
            Paragraph("<b>SGST</b>", styles['th']),
            Paragraph("<b>IGST</b>", styles['th']),
            Paragraph("<b>Total Tax</b>", styles['th']),
            Paragraph("<b>Invoice Total</b>", styles['th']),
            Paragraph("<b>Paid</b>", styles['th']),
            Paragraph("<b>Balance Due</b>", styles['th']),
        ]
    ]

    for inv in data['invoices']:
        table_data.append([
            Paragraph(inv.invoice_number, styles['td_left']),
            Paragraph(inv.invoice_date.strftime('%d-%b-%Y'), styles['td_left']),
            Paragraph(inv.customer.name[:25], styles['td_left']),
            Paragraph(inv.customer.state, styles['td_left']),
            Paragraph(f"{rupee}{inv.taxable_value:.2f}", styles['td_right']),
            Paragraph(f"{rupee}{inv.cgst_amount:.2f}", styles['td_right']),
            Paragraph(f"{rupee}{inv.sgst_amount:.2f}", styles['td_right']),
            Paragraph(f"{rupee}{inv.igst_amount:.2f}", styles['td_right']),
            Paragraph(f"{rupee}{(inv.cgst_amount + inv.sgst_amount + inv.igst_amount):.2f}", styles['td_right']),
            Paragraph(f"<b>{rupee}{inv.grand_total:.2f}</b>", styles['td_bold_right']),
            Paragraph(f"{rupee}{inv.amount_paid:.2f}", styles['td_right']),
            Paragraph(f"<b>{rupee}{inv.outstanding_balance:.2f}</b>", styles['td_bold_right']),
        ])

    t = data['totals']
    table_data.append([
        Paragraph("<b>TOTALS</b>", styles['td_left']),
        Paragraph(f"<b>{t['count']} Inv</b>", styles['td_left']),
        Paragraph("", styles['td_left']),
        Paragraph("", styles['td_left']),
        Paragraph(f"<b>{rupee}{t['taxable_value']:.2f}</b>", styles['td_bold_right']),
        Paragraph(f"<b>{rupee}{t['cgst']:.2f}</b>", styles['td_bold_right']),
        Paragraph(f"<b>{rupee}{t['sgst']:.2f}</b>", styles['td_bold_right']),
        Paragraph(f"<b>{rupee}{t['igst']:.2f}</b>", styles['td_bold_right']),
        Paragraph(f"<b>{rupee}{t['total_tax']:.2f}</b>", styles['td_bold_right']),
        Paragraph(f"<b>{rupee}{t['grand_total']:.2f}</b>", styles['td_bold_right']),
        Paragraph(f"<b>{rupee}{t['amount_paid']:.2f}</b>", styles['td_bold_right']),
        Paragraph(f"<b>{rupee}{t['outstanding']:.2f}</b>", styles['td_bold_right']),
    ])

    col_widths = [24*mm, 18*mm, 45*mm, 26*mm, 22*mm, 18*mm, 18*mm, 18*mm, 20*mm, 24*mm, 22*mm, 22*mm]
    reg_table = Table(table_data, colWidths=col_widths, repeatRows=1)
    reg_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#f1f5f9')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e2e8f0')),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#f8fafc')),
    ]))
    elements.append(reg_table)
    elements.append(Spacer(1, 10))
    elements.append(Paragraph("Declaration: dummy data for evaluation &bull; Demo Snacks Pvt Ltd", styles['subtitle']))

    doc.build(elements)
    buf.seek(0)
    return buf


# ---------------------------------------------------------------------------
# 2. GST Summary PDF (GSTR-1 & GSTR-3B)
# ---------------------------------------------------------------------------

def build_gst_summary_pdf(data: dict, period_str: str = "All Time") -> BytesIO:
    buf = BytesIO()
    doc = _create_report_doc(buf, orientation='portrait')
    styles = _get_styles()
    rupee = styles['rupee']

    elements = []
    elements.append(_build_header_flowable("GST Summary of Outward Supplies", "GSTR-1 & GSTR-3B Compliant Summary", period_str, styles))
    elements.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor('#cbd5e1'), spaceAfter=8, spaceBefore=4))

    # GSTR-3B Table 3.1
    elements.append(Paragraph("<b>1. GSTR-3B Table 3.1: Details of Outward Supplies</b>", styles['title']))
    elements.append(Spacer(1, 4))
    g31 = data['gstr3b_3_1']
    t31_data = [
        [
            Paragraph("<b>Nature of Supply</b>", styles['th']),
            Paragraph("<b>Taxable Val</b>", styles['th']),
            Paragraph("<b>IGST</b>", styles['th']),
            Paragraph("<b>CGST</b>", styles['th']),
            Paragraph("<b>SGST</b>", styles['th']),
            Paragraph("<b>Cess</b>", styles['th']),
        ],
        [
            Paragraph("3.1(a) Outward taxable supplies (normal rate)", styles['td_left']),
            Paragraph(f"{rupee}{g31['taxable_value']:.2f}", styles['td_right']),
            Paragraph(f"{rupee}{g31['igst']:.2f}", styles['td_right']),
            Paragraph(f"{rupee}{g31['cgst']:.2f}", styles['td_right']),
            Paragraph(f"{rupee}{g31['sgst']:.2f}", styles['td_right']),
            Paragraph(f"{rupee}{g31['cess']:.2f}", styles['td_right']),
        ]
    ]
    t31 = Table(t31_data, colWidths=[70*mm, 26*mm, 24*mm, 24*mm, 24*mm, 22*mm])
    t31.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#f1f5f9')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    elements.append(t31)
    elements.append(Spacer(1, 10))

    # GSTR-1 Table 12 HSN Summary
    elements.append(Paragraph("<b>2. GSTR-1 Table 12: HSN-wise Summary of Outward Supplies</b>", styles['title']))
    elements.append(Spacer(1, 4))
    hsn_table_data = [
        [
            Paragraph("<b>HSN</b>", styles['th']),
            Paragraph("<b>Description</b>", styles['th']),
            Paragraph("<b>UQC</b>", styles['th']),
            Paragraph("<b>Total Qty</b>", styles['th']),
            Paragraph("<b>Taxable Val</b>", styles['th']),
            Paragraph("<b>IGST</b>", styles['th']),
            Paragraph("<b>CGST</b>", styles['th']),
            Paragraph("<b>SGST</b>", styles['th']),
            Paragraph("<b>Total Tax</b>", styles['th']),
        ]
    ]
    for h in data['hsn_summary']:
        hsn_table_data.append([
            Paragraph(h['hsn_code'], styles['td_left']),
            Paragraph(h['description'], styles['td_left']),
            Paragraph(h['uqc'], styles['td_left']),
            Paragraph(f"{h['total_quantity']:.0f}", styles['td_right']),
            Paragraph(f"{rupee}{h['taxable_value']:.2f}", styles['td_right']),
            Paragraph(f"{rupee}{h['igst']:.2f}", styles['td_right']),
            Paragraph(f"{rupee}{h['cgst']:.2f}", styles['td_right']),
            Paragraph(f"{rupee}{h['sgst']:.2f}", styles['td_right']),
            Paragraph(f"<b>{rupee}{h['total_tax']:.2f}</b>", styles['td_bold_right']),
        ])
    t_hsn = Table(hsn_table_data, colWidths=[20*mm, 45*mm, 15*mm, 20*mm, 25*mm, 17*mm, 17*mm, 17*mm, 20*mm])
    t_hsn.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#f1f5f9')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
    ]))
    elements.append(t_hsn)
    elements.append(Spacer(1, 10))

    # GSTR-1 Table 4: B2B Invoices
    elements.append(Paragraph("<b>3. GSTR-1 Table 4: B2B Tax Invoices</b>", styles['title']))
    elements.append(Spacer(1, 4))
    b2b_table_data = [
        [
            Paragraph("<b>GSTIN</b>", styles['th']),
            Paragraph("<b>Recipient Name</b>", styles['th']),
            Paragraph("<b>Invoice No</b>", styles['th']),
            Paragraph("<b>Place of Supply</b>", styles['th']),
            Paragraph("<b>Taxable Val</b>", styles['th']),
            Paragraph("<b>Total Tax</b>", styles['th']),
            Paragraph("<b>Invoice Val</b>", styles['th']),
        ]
    ]
    for inv in data['b2b_invoices']:
        b2b_table_data.append([
            Paragraph(inv.customer.gstin, styles['td_left']),
            Paragraph(inv.customer.name, styles['td_left']),
            Paragraph(inv.invoice_number, styles['td_left']),
            Paragraph(inv.customer.state, styles['td_left']),
            Paragraph(f"{rupee}{inv.taxable_value:.2f}", styles['td_right']),
            Paragraph(f"{rupee}{(inv.cgst_amount + inv.sgst_amount + inv.igst_amount):.2f}", styles['td_right']),
            Paragraph(f"<b>{rupee}{inv.grand_total:.2f}</b>", styles['td_bold_right']),
        ])
    t_b2b = Table(b2b_table_data, colWidths=[35*mm, 45*mm, 28*mm, 28*mm, 22*mm, 20*mm, 22*mm])
    t_b2b.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#f1f5f9')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
    ]))
    elements.append(t_b2b)
    elements.append(Spacer(1, 10))
    elements.append(Paragraph("Declaration: dummy data for evaluation &bull; Demo Snacks Pvt Ltd", styles['subtitle']))

    doc.build(elements)
    buf.seek(0)
    return buf


# ---------------------------------------------------------------------------
# 3. Purchase Register PDF
# ---------------------------------------------------------------------------

def build_purchase_register_pdf(data: dict, period_str: str = "All Time") -> BytesIO:
    buf = BytesIO()
    doc = _create_report_doc(buf, orientation='landscape')
    styles = _get_styles()
    rupee = styles['rupee']

    elements = []
    elements.append(_build_header_flowable("Raw Material & Packaging Purchase Register", "Goods Inward Register", period_str, styles))
    elements.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor('#cbd5e1'), spaceAfter=6, spaceBefore=4))

    table_data = [
        [
            Paragraph("<b>PO Number</b>", styles['th']),
            Paragraph("<b>Date</b>", styles['th']),
            Paragraph("<b>Supplier Name</b>", styles['th']),
            Paragraph("<b>Item Name</b>", styles['th']),
            Paragraph("<b>Category</b>", styles['th']),
            Paragraph("<b>Quantity</b>", styles['th']),
            Paragraph("<b>Unit Price</b>", styles['th']),
            Paragraph("<b>Line Total</b>", styles['th']),
            Paragraph("<b>Status</b>", styles['th']),
        ]
    ]

    for line in data['detailed_lines']:
        table_data.append([
            Paragraph(line['po_number'], styles['td_left']),
            Paragraph(str(line['order_date']), styles['td_left']),
            Paragraph(line['supplier'].name, styles['td_left']),
            Paragraph(line['item_name'], styles['td_left']),
            Paragraph(line['item_type'], styles['td_left']),
            Paragraph(f"{line['quantity']} {line['unit'].symbol}", styles['td_right']),
            Paragraph(f"{rupee}{line['unit_price']:.2f}", styles['td_right']),
            Paragraph(f"<b>{rupee}{line['line_total']:.2f}</b>", styles['td_bold_right']),
            Paragraph(line['status'], styles['td_left']),
        ])

    tot = data['totals']
    table_data.append([
        Paragraph("<b>TOTALS</b>", styles['td_left']),
        Paragraph("", styles['td_left']),
        Paragraph(f"<b>{tot['lines_count']} lines</b>", styles['td_left']),
        Paragraph("", styles['td_left']),
        Paragraph("", styles['td_left']),
        Paragraph("", styles['td_left']),
        Paragraph("", styles['td_left']),
        Paragraph(f"<b>{rupee}{tot['grand_total']:.2f}</b>", styles['td_bold_right']),
        Paragraph("", styles['td_left']),
    ])

    col_widths = [28*mm, 22*mm, 55*mm, 45*mm, 30*mm, 26*mm, 24*mm, 28*mm, 20*mm]
    t = Table(table_data, colWidths=col_widths, repeatRows=1)
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#f1f5f9')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#f8fafc')),
    ]))
    elements.append(t)
    elements.append(Spacer(1, 10))
    elements.append(Paragraph("Declaration: dummy data for evaluation &bull; Demo Snacks Pvt Ltd", styles['subtitle']))

    doc.build(elements)
    buf.seek(0)
    return buf


# ---------------------------------------------------------------------------
# 4. Stock Summary PDF
# ---------------------------------------------------------------------------

def build_stock_summary_pdf(summary_rows: list, period_str: str = "All Time") -> BytesIO:
    buf = BytesIO()
    doc = _create_report_doc(buf, orientation='landscape')
    styles = _get_styles()
    rupee = styles['rupee']

    elements = []
    elements.append(_build_header_flowable("Inventory Stock Summary Report", "Raw, Packaging & Finished Goods", period_str, styles))
    elements.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor('#cbd5e1'), spaceAfter=6, spaceBefore=4))

    table_data = [
        [
            Paragraph("<b>Category</b>", styles['th']),
            Paragraph("<b>Item Name</b>", styles['th']),
            Paragraph("<b>Unit</b>", styles['th']),
            Paragraph("<b>Opening</b>", styles['th']),
            Paragraph("<b>Receipts (+)</b>", styles['th']),
            Paragraph("<b>Issues (-)</b>", styles['th']),
            Paragraph("<b>Adj (±)</b>", styles['th']),
            Paragraph("<b>Closing Stock</b>", styles['th']),
            Paragraph("<b>Unit Rate</b>", styles['th']),
            Paragraph("<b>Stock Valuation</b>", styles['th']),
            Paragraph("<b>Status</b>", styles['th']),
        ]
    ]

    total_val = Decimal('0.00')
    for r in summary_rows:
        total_val += r['valuation']
        status_text = "⚠️ LOW" if r['is_low_stock'] else "OK"
        table_data.append([
            Paragraph(r['type_name'], styles['td_left']),
            Paragraph(f"<b>{r['name']}</b> ({r['code']})", styles['td_left']),
            Paragraph(r['unit'].symbol, styles['td_left']),
            Paragraph(f"{r['opening']:.2f}", styles['td_right']),
            Paragraph(f"{r['receipts']:.2f}", styles['td_right']),
            Paragraph(f"{r['issues']:.2f}", styles['td_right']),
            Paragraph("0.00", styles['td_right']),
            Paragraph(f"<b>{r['closing']:.2f}</b>", styles['td_bold_right']),
            Paragraph(f"{rupee}{r['cost']:.2f}", styles['td_right']),
            Paragraph(f"<b>{rupee}{r['valuation']:.2f}</b>", styles['td_bold_right']),
            Paragraph(status_text, styles['td_left']),
        ])

    table_data.append([
        Paragraph("<b>TOTAL VALUATION</b>", styles['td_left']),
        Paragraph("", styles['td_left']),
        Paragraph("", styles['td_left']),
        Paragraph("", styles['td_left']),
        Paragraph("", styles['td_left']),
        Paragraph("", styles['td_left']),
        Paragraph("", styles['td_left']),
        Paragraph("", styles['td_left']),
        Paragraph("", styles['td_left']),
        Paragraph(f"<b>{rupee}{total_val:.2f}</b>", styles['td_bold_right']),
        Paragraph("", styles['td_left']),
    ])

    col_widths = [26*mm, 60*mm, 15*mm, 20*mm, 22*mm, 22*mm, 18*mm, 26*mm, 24*mm, 30*mm, 15*mm]
    t = Table(table_data, colWidths=col_widths, repeatRows=1)
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#f1f5f9')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#f8fafc')),
    ]))
    elements.append(t)
    elements.append(Spacer(1, 10))
    elements.append(Paragraph("Declaration: dummy data for evaluation &bull; Demo Snacks Pvt Ltd", styles['subtitle']))

    doc.build(elements)
    buf.seek(0)
    return buf


# ---------------------------------------------------------------------------
# 5. Production Variance PDF
# ---------------------------------------------------------------------------

def build_production_variance_pdf(data: dict, period_str: str = "All Time") -> BytesIO:
    buf = BytesIO()
    doc = _create_report_doc(buf, orientation='landscape')
    styles = _get_styles()
    rupee = styles['rupee']

    elements = []
    elements.append(_build_header_flowable("Production Variance & Wastage Report", "Yield, Material Consumption & Batch Costing", period_str, styles))
    elements.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor('#cbd5e1'), spaceAfter=6, spaceBefore=4))

    # ---- Run Summary Table ----
    run_table_data = [
        [
            Paragraph("<b>Run No</b>", styles['th']),
            Paragraph("<b>Date</b>", styles['th']),
            Paragraph("<b>Product</b>", styles['th']),
            Paragraph("<b>Expected</b>", styles['th']),
            Paragraph("<b>Actual</b>", styles['th']),
            Paragraph("<b>Yield Var %</b>", styles['th']),
            Paragraph("<b>Damaged</b>", styles['th']),
            Paragraph("<b>Cartons</b>", styles['th']),
            Paragraph("<b>Total Cost</b>", styles['th']),
            Paragraph("<b>Cost/Pkt</b>", styles['th']),
            Paragraph("<b>Margin %</b>", styles['th']),
            Paragraph("<b>Variance Alert</b>", styles['th']),
        ]
    ]

    for rd in data['runs_data']:
        run = rd['run']
        flag_label = rd.get('flag_label', "⚠️ FLAG" if rd['has_variance_flag'] else "Normal")
        flag_color = '#b91c1c' if rd['has_variance_flag'] else '#15803d'
        flag_style = ParagraphStyle('flag', parent=styles['td_left'], textColor=colors.HexColor(flag_color), fontName='Helvetica-Bold' if rd['has_variance_flag'] else 'Helvetica')
        run_table_data.append([
            Paragraph(run.run_number, styles['td_left']),
            Paragraph(str(run.start_date), styles['td_left']),
            Paragraph(run.product.name, styles['td_left']),
            Paragraph(str(run.expected_yield), styles['td_right']),
            Paragraph(str(run.actual_yield or 0), styles['td_right']),
            Paragraph(f"{run.yield_variance_pct:.2f}%", styles['td_right']),
            Paragraph(str(run.damaged_pouches), styles['td_right']),
            Paragraph(str(run.cartons_used), styles['td_right']),
            Paragraph(f"{rupee}{run.total_production_cost:.2f}", styles['td_right']),
            Paragraph(f"{rupee}{run.actual_cost_per_packet:.2f}", styles['td_right']),
            Paragraph(f"{run.margin_pct:.2f}%", styles['td_right']),
            Paragraph(flag_label, flag_style),
        ])

    tot = data['totals']
    run_table_data.append([
        Paragraph("<b>TOTALS</b>", styles['td_left']),
        Paragraph("", styles['td_left']),
        Paragraph(f"<b>{tot['runs_count']} runs</b>", styles['td_left']),
        Paragraph(str(tot['total_expected_pkts']), styles['td_right']),
        Paragraph(str(tot['total_actual_pkts']), styles['td_right']),
        Paragraph(f"<b>{tot['overall_yield_pct']:.2f}%</b>", styles['td_bold_right']),
        Paragraph(str(tot['total_damaged_pouches']), styles['td_right']),
        Paragraph(str(tot['total_cartons_used']), styles['td_right']),
        Paragraph(f"<b>{rupee}{tot['total_production_cost']:.2f}</b>", styles['td_bold_right']),
        Paragraph(f"<b>{rupee}{tot['avg_cost_per_pkt']:.2f}</b>", styles['td_bold_right']),
        Paragraph("", styles['td_left']),
        Paragraph(f"<b>{tot['flagged_runs_count']} flags</b>", styles['td_left']),
    ])

    col_widths = [26*mm, 20*mm, 44*mm, 18*mm, 18*mm, 20*mm, 18*mm, 16*mm, 26*mm, 20*mm, 18*mm, 36*mm]
    t = Table(run_table_data, colWidths=col_widths, repeatRows=1)
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#f1f5f9')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#f8fafc')),
    ]))
    elements.append(t)
    elements.append(Spacer(1, 8))

    # ---- Material Consumption Sub-Tables (one per run) ----
    for rd in data['runs_data']:
        run = rd['run']
        mc_list = rd.get('material_consumption', [])
        if not mc_list:
            continue

        elements.append(Paragraph(
            f"<b>Material Consumption — {run.run_number} ({run.product.name})</b>",
            ParagraphStyle('mc_title', parent=styles['subtitle'],
                           textColor=colors.HexColor('#0369a1'), spaceBefore=6, spaceAfter=3)
        ))

        mc_table_data = [[
            Paragraph("<b>Material / Packaging</b>", styles['th']),
            Paragraph("<b>Category</b>", styles['th']),
            Paragraph("<b>Planned Qty</b>", styles['th']),
            Paragraph("<b>Actual Qty</b>", styles['th']),
            Paragraph("<b>Unit</b>", styles['th']),
            Paragraph("<b>Variance Qty</b>", styles['th']),
            Paragraph("<b>Variance %</b>", styles['th']),
            Paragraph("<b>Alert</b>", styles['th']),
        ]]

        for mc in mc_list:
            var_qty = mc['variance_quantity']
            var_pct = mc['variance_pct']
            var_qty_str = f"+{var_qty}" if var_qty > 0 else str(var_qty)
            var_pct_str = f"+{var_pct:.2f}%" if var_pct > 0 else f"{var_pct:.2f}%"
            if mc['is_flagged']:
                if var_qty > 0:
                    alert_str = "⚠️ OVER"
                    alert_color = colors.HexColor('#b91c1c')   # red
                else:
                    alert_str = "⚠️ UNDER"
                    alert_color = colors.HexColor('#92400e')   # amber
            else:
                alert_str = "—"
                alert_color = colors.HexColor('#64748b')
            alert_style = ParagraphStyle(
                'alert_cell',
                parent=styles['td_left'],
                textColor=alert_color,
                fontName='Helvetica-Bold' if mc['is_flagged'] else 'Helvetica',
            )
            mc_table_data.append([
                Paragraph(mc['item_name'], styles['td_left']),
                Paragraph(mc['item_type'], styles['td_left']),
                Paragraph(str(mc['standard_quantity']), styles['td_right']),
                Paragraph(str(mc['actual_quantity']), styles['td_right']),
                Paragraph(mc['unit'], styles['td_left']),
                Paragraph(var_qty_str, styles['td_right']),
                Paragraph(var_pct_str, styles['td_right']),
                Paragraph(alert_str, alert_style),
            ])

        mc_col_widths = [60*mm, 30*mm, 25*mm, 25*mm, 20*mm, 25*mm, 25*mm, 30*mm]
        mc_t = Table(mc_table_data, colWidths=mc_col_widths, repeatRows=1)
        mc_style = [
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#e0f2fe')),
            ('GRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#bae6fd')),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ]
        for i, mc in enumerate(mc_list, start=1):
            if mc['is_flagged']:
                # OVER = light red bg, UNDER = light amber bg
                if mc['variance_quantity'] > 0:
                    row_bg = colors.HexColor('#fee2e2')   # red-50 for over-consumption
                else:
                    row_bg = colors.HexColor('#fef3c7')   # amber-50 for under-consumption
                mc_style.append(('BACKGROUND', (0, i), (-1, i), row_bg))
        mc_t.setStyle(TableStyle(mc_style))
        elements.append(mc_t)
        elements.append(Spacer(1, 6))

    elements.append(Paragraph("Declaration: dummy data for evaluation &bull; Demo Snacks Pvt Ltd", styles['subtitle']))

    doc.build(elements)
    buf.seek(0)
    return buf


# ---------------------------------------------------------------------------
# 6. Ageing & Receivables PDF
# ---------------------------------------------------------------------------

def build_ageing_report_pdf(report_data: dict, as_of_date) -> BytesIO:
    buf = BytesIO()
    doc = _create_report_doc(buf, orientation='portrait')
    styles = _get_styles()
    rupee = styles['rupee']

    elements = []
    date_str = str(as_of_date)
    elements.append(_build_header_flowable("Accounts Receivable Ageing Report", "Customer Outstanding Balances by Ageing Buckets", f"As of {date_str}", styles))
    elements.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor('#cbd5e1'), spaceAfter=8, spaceBefore=4))

    table_data = [
        [
            Paragraph("<b>Customer Name</b>", styles['th']),
            Paragraph("<b>Channel</b>", styles['th']),
            Paragraph("<b>Total Due</b>", styles['th']),
            Paragraph("<b>0-30 Days</b>", styles['th']),
            Paragraph("<b>31-60 Days</b>", styles['th']),
            Paragraph("<b>61-90 Days</b>", styles['th']),
            Paragraph("<b>90+ Days</b>", styles['th']),
        ]
    ]

    for c in report_data.get('customers', []):
        table_data.append([
            Paragraph(c['customer'].name, styles['td_left']),
            Paragraph(c['customer'].get_customer_type_display(), styles['td_left']),
            Paragraph(f"<b>{rupee}{c['total_outstanding']:.2f}</b>", styles['td_bold_right']),
            Paragraph(f"{rupee}{c['bucket_0_30']:.2f}", styles['td_right']),
            Paragraph(f"{rupee}{c['bucket_31_60']:.2f}", styles['td_right']),
            Paragraph(f"{rupee}{c['bucket_61_90']:.2f}", styles['td_right']),
            Paragraph(f"{rupee}{c['bucket_90_plus']:.2f}", styles['td_right']),
        ])

    s = report_data.get('summary', {})
    table_data.append([
        Paragraph("<b>TOTALS</b>", styles['td_left']),
        Paragraph("", styles['td_left']),
        Paragraph(f"<b>{rupee}{s.get('total_outstanding', Decimal('0.00')):.2f}</b>", styles['td_bold_right']),
        Paragraph(f"<b>{rupee}{s.get('bucket_0_30', Decimal('0.00')):.2f}</b>", styles['td_bold_right']),
        Paragraph(f"<b>{rupee}{s.get('bucket_31_60', Decimal('0.00')):.2f}</b>", styles['td_bold_right']),
        Paragraph(f"<b>{rupee}{s.get('bucket_61_90', Decimal('0.00')):.2f}</b>", styles['td_bold_right']),
        Paragraph(f"<b>{rupee}{s.get('bucket_90_plus', Decimal('0.00')):.2f}</b>", styles['td_bold_right']),
    ])

    col_widths = [55*mm, 25*mm, 28*mm, 22*mm, 20*mm, 20*mm, 20*mm]
    t = Table(table_data, colWidths=col_widths, repeatRows=1)
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#f1f5f9')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#f8fafc')),
    ]))
    elements.append(t)
    elements.append(Spacer(1, 10))
    elements.append(Paragraph("Declaration: dummy data for evaluation &bull; Demo Snacks Pvt Ltd", styles['subtitle']))

    doc.build(elements)
    buf.seek(0)
    return buf
