import csv
from io import StringIO
from decimal import Decimal
from django.http import HttpResponse


def create_csv_response(filename: str, headers: list, rows: list) -> HttpResponse:
    """
    Creates an HTTP response with CSV content, prefixed with UTF-8 BOM
    for seamless opening in Microsoft Excel and LibreOffice without encoding glitches.
    """
    buffer = StringIO()
    # Write UTF-8 BOM
    buffer.write('\ufeff')
    writer = csv.writer(buffer, quoting=csv.QUOTE_MINIMAL)
    writer.writerow(headers)
    for row in rows:
        formatted_row = []
        for cell in row:
            if isinstance(cell, Decimal):
                formatted_row.append(f"{cell:.2f}")
            elif cell is None:
                formatted_row.append("")
            else:
                formatted_row.append(str(cell))
        writer.writerow(formatted_row)

    response = HttpResponse(buffer.getvalue(), content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="{filename}.csv"'
    return response


# ---------------------------------------------------------------------------
# Sales Register CSV
# ---------------------------------------------------------------------------

def export_sales_register_csv(data: dict) -> HttpResponse:
    headers = [
        "Invoice No", "Date", "Customer Name", "Customer GSTIN", "Place of Supply",
        "Supply Type", "Status", "Taxable Value (₹)", "CGST (₹)", "SGST (₹)",
        "IGST (₹)", "Total Tax (₹)", "Invoice Total (₹)", "Amount Paid (₹)", "Balance Due (₹)"
    ]
    rows = []
    for inv in data['invoices']:
        rows.append([
            inv.invoice_number,
            inv.invoice_date.strftime('%Y-%m-%d'),
            inv.customer.name,
            inv.customer.gstin or "Unregistered",
            inv.customer.state,
            "Inter-State" if inv.is_interstate else "Intra-State",
            inv.get_status_display(),
            inv.taxable_value,
            inv.cgst_amount,
            inv.sgst_amount,
            inv.igst_amount,
            inv.cgst_amount + inv.sgst_amount + inv.igst_amount,
            inv.grand_total,
            inv.amount_paid,
            inv.outstanding_balance,
        ])
    # Append Total row
    t = data['totals']
    rows.append([
        "TOTAL", "", f"{t['count']} Invoices", "", "", "", "",
        t['taxable_value'], t['cgst'], t['sgst'], t['igst'],
        t['total_tax'], t['grand_total'], t['amount_paid'], t['outstanding']
    ])
    return create_csv_response("sales_register", headers, rows)


def export_customer_sales_csv(data: dict) -> HttpResponse:
    headers = [
        "Customer Name", "Channel", "GSTIN", "State", "Invoices Count",
        "Taxable Value (₹)", "CGST (₹)", "SGST (₹)", "IGST (₹)", "Total Tax (₹)",
        "Grand Total (₹)", "Amount Paid (₹)", "Outstanding Balance (₹)"
    ]
    rows = []
    for r in data['customer_sales']:
        rows.append([
            r['customer'].name,
            r['customer'].get_customer_type_display(),
            r['customer'].gstin or "Unregistered",
            r['customer'].state,
            r['invoices_count'],
            r['taxable_value'],
            r['cgst'],
            r['sgst'],
            r['igst'],
            r['total_tax'],
            r['grand_total'],
            r['amount_paid'],
            r['outstanding'],
        ])
    return create_csv_response("customer_wise_sales", headers, rows)


def export_product_sales_csv(data: dict) -> HttpResponse:
    headers = [
        "Product Code", "Product Name", "HSN Code", "Quantity Sold", "Unit",
        "Average Selling Rate (₹)", "Taxable Value (₹)", "CGST (₹)", "SGST (₹)",
        "IGST (₹)", "Total Tax (₹)", "Total Sales Value (₹)"
    ]
    rows = []
    for p in data['product_sales']:
        rows.append([
            p['product'].code,
            p['product'].name,
            p['product'].hsn_code or "19059040",
            p['quantity'],
            p['unit'].symbol,
            p['avg_rate'],
            p['taxable_value'],
            p['cgst'],
            p['sgst'],
            p['igst'],
            p['total_tax'],
            p['total_value'],
        ])
    return create_csv_response("product_wise_sales", headers, rows)


# ---------------------------------------------------------------------------
# GST Summary CSV
# ---------------------------------------------------------------------------

def export_gst_summary_csv(data: dict) -> HttpResponse:
    buffer = StringIO()
    buffer.write('\ufeff')
    writer = csv.writer(buffer, quoting=csv.QUOTE_MINIMAL)

    # 1. GSTR-3B Table 3.1
    writer.writerow(["=== GSTR-3B TABLE 3.1: OUTWARD TAXABLE SUPPLIES ==="])
    writer.writerow(["Nature of Supply", "Total Taxable Value (₹)", "Integrated Tax (₹)", "Central Tax (₹)", "State/UT Tax (₹)", "Cess (₹)"])
    g31 = data['gstr3b_3_1']
    writer.writerow([
        "(a) Outward taxable supplies (other than zero rated, nil rated and exempted)",
        f"{g31['taxable_value']:.2f}",
        f"{g31['igst']:.2f}",
        f"{g31['cgst']:.2f}",
        f"{g31['sgst']:.2f}",
        f"{g31['cess']:.2f}",
    ])
    writer.writerow([])

    # 2. GSTR-3B Table 3.2
    writer.writerow(["=== GSTR-3B TABLE 3.2: INTER-STATE SUPPLIES TO UNREGISTERED PERSONS ==="])
    writer.writerow(["Place of Supply (State)", "Total Taxable Value (₹)", "Amount of Integrated Tax (₹)"])
    for r in data['gstr3b_3_2']:
        writer.writerow([r['place_of_supply'], f"{r['taxable_value']:.2f}", f"{r['igst']:.2f}"])
    if not data['gstr3b_3_2']:
        writer.writerow(["None in selected period", "0.00", "0.00"])
    writer.writerow([])

    # 3. GSTR-1 Table 4: B2B Invoices
    writer.writerow(["=== GSTR-1 TABLE 4: B2B INVOICES (REGISTERED TAXABLE PERSONS) ==="])
    writer.writerow(["Recipient GSTIN", "Recipient Name", "Invoice No", "Date", "Invoice Value (₹)", "Place of Supply", "Reverse Charge", "Rate (%)", "Taxable Value (₹)", "Integrated Tax (₹)", "Central Tax (₹)", "State/UT Tax (₹)"])
    for inv in data['b2b_invoices']:
        writer.writerow([
            inv.customer.gstin,
            inv.customer.name,
            inv.invoice_number,
            inv.invoice_date.strftime('%Y-%m-%d'),
            f"{inv.grand_total:.2f}",
            inv.customer.state,
            "N",
            "5.00",
            f"{inv.taxable_value:.2f}",
            f"{inv.igst_amount:.2f}",
            f"{inv.cgst_amount:.2f}",
            f"{inv.sgst_amount:.2f}",
        ])
    writer.writerow([])

    # 4. GSTR-1 Table 12: HSN Summary
    writer.writerow(["=== GSTR-1 TABLE 12: HSN-WISE SUMMARY OF OUTWARD SUPPLIES ==="])
    writer.writerow(["HSN Code", "Description", "UQC", "Total Quantity", "Total Value (₹)", "Taxable Value (₹)", "Integrated Tax (₹)", "Central Tax (₹)", "State/UT Tax (₹)", "Total Tax (₹)"])
    for h in data['hsn_summary']:
        writer.writerow([
            h['hsn_code'],
            h['description'],
            h['uqc'],
            f"{h['total_quantity']:.2f}",
            f"{h['total_value']:.2f}",
            f"{h['taxable_value']:.2f}",
            f"{h['igst']:.2f}",
            f"{h['cgst']:.2f}",
            f"{h['sgst']:.2f}",
            f"{h['total_tax']:.2f}",
        ])

    response = HttpResponse(buffer.getvalue(), content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = 'attachment; filename="gst_outward_summary_gstr1_gstr3b.csv"'
    return response


# ---------------------------------------------------------------------------
# Purchase Register CSV
# ---------------------------------------------------------------------------

def export_purchase_register_csv(data: dict) -> HttpResponse:
    headers = [
        "PO Number", "Date", "Supplier Name", "Supplier GSTIN", "Supplier State",
        "Item Name", "Item Category", "Quantity", "Unit", "Unit Price (₹)",
        "Line Total (₹)", "Status"
    ]
    rows = []
    for line in data['detailed_lines']:
        rows.append([
            line['po_number'],
            line['order_date'].strftime('%Y-%m-%d') if hasattr(line['order_date'], 'strftime') else line['order_date'],
            line['supplier'].name,
            line['supplier'].gstin or "Unregistered",
            line['supplier'].state,
            line['item_name'],
            line['item_type'],
            line['quantity'],
            line['unit'].symbol,
            line['unit_price'],
            line['line_total'],
            line['status'],
        ])
    t = data['totals']
    rows.append([
        "TOTAL", "", f"{t['lines_count']} Lines", "", "", "", "",
        "", "", "", t['grand_total'], ""
    ])
    return create_csv_response("purchase_register", headers, rows)


# ---------------------------------------------------------------------------
# Stock Summary & Stock Ledger CSV
# ---------------------------------------------------------------------------

def export_stock_summary_csv(summary_rows: list) -> HttpResponse:
    headers = [
        "Category", "Item Code", "Item Name", "Unit", "Opening Stock",
        "Receipts (+)", "Issues (-)", "Audit Adjustments", "Closing Stock",
        "Unit Cost (₹)", "Stock Valuation (₹)", "Reorder Level", "Low Stock Alert"
    ]
    rows = []
    for r in summary_rows:
        rows.append([
            r['type_name'],
            r['code'],
            r['name'],
            r['unit'].symbol,
            r['opening'],
            r['receipts'],
            r['issues'],
            Decimal('0.0000'),
            r['closing'],
            r['cost'],
            r['valuation'],
            r['reorder_level'],
            "⚠️ LOW STOCK" if r['is_low_stock'] else "OK",
        ])
    return create_csv_response("stock_summary", headers, rows)


def export_stock_ledger_csv(ledger_data: dict, item_name: str) -> HttpResponse:
    headers = [
        "Date & Time", "Movement Type", "Source Document", "Unit", "Unit Cost (₹)",
        "Inward (+)", "Outward (-)", "Running Balance", "Batch Number", "User", "Notes"
    ]
    rows = []
    for m in ledger_data.get('movements', []):
        in_qty = m['quantity'] if m['quantity'] > Decimal('0.0000') else Decimal('0.0000')
        out_qty = abs(m['quantity']) if m['quantity'] < Decimal('0.0000') else Decimal('0.0000')
        rows.append([
            m['movement'].created_at.strftime('%Y-%m-%d %H:%M'),
            m['movement'].get_movement_type_display(),
            m['movement'].source_document,
            m['movement'].unit.symbol if m['movement'].unit else "",
            m['movement'].unit_cost,
            in_qty,
            out_qty,
            m['running_balance'],
            m['movement'].batch_number,
            m['movement'].user.username if m['movement'].user else "System",
            m['movement'].notes,
        ])
    clean_name = item_name.lower().replace(' ', '_')[:25]
    return create_csv_response(f"stock_ledger_{clean_name}", headers, rows)


# ---------------------------------------------------------------------------
# Production Variance CSV
# ---------------------------------------------------------------------------

def export_production_variance_csv(data: dict) -> HttpResponse:
    # Run-level summary columns
    run_headers = [
        "Run Number", "Date", "Product", "Status", "Expected Yield", "Actual Yield",
        "Yield Variance (%)", "Variance Alert", "Damaged Pouches", "Cartons Used",
        "Raw Material Cost (₹)", "Packaging Cost (₹)", "Labour Cost (₹)", "Power/Overheads (₹)",
        "Total Batch Cost (₹)", "Cost / Packet (₹)", "Selling Price (₹)", "Margin / Packet (₹)", "Margin (%)"
    ]
    # Material consumption detail columns (appended after the run row)
    mc_headers = [
        "", "",  # indent columns
        "  Material / Packaging", "  Category",
        "  Planned Qty", "  Actual Qty", "  Unit",
        "  Variance Qty", "  Variance %", "  Flagged?"
    ]

    rows = []
    rows.append(run_headers)  # header row for run summary

    for rd in data['runs_data']:
        run = rd['run']
        # Run summary row
        rows.append([
            run.run_number,
            run.start_date.strftime('%Y-%m-%d') if hasattr(run.start_date, 'strftime') else run.start_date,
            run.product.name,
            run.get_status_display(),
            run.expected_yield,
            run.actual_yield or 0,
            run.yield_variance_pct,
            rd.get('flag_label', "⚠️ FLAGGED" if rd['has_variance_flag'] else "Normal"),
            run.damaged_pouches,
            run.cartons_used,
            run.total_raw_material_cost,
            run.total_packaging_cost,
            run.labour_cost,
            run.overhead_cost,
            run.total_production_cost,
            run.actual_cost_per_packet,
            run.product.selling_price,
            run.margin_per_packet,
            run.margin_pct,
        ])

        # Material Consumption header (sub-section)
        mc_list = rd.get('material_consumption', [])
        if mc_list:
            rows.append(mc_headers)
            for mc in mc_list:
                var_pct = mc['variance_pct']
                var_qty = mc['variance_quantity']
                rows.append([
                    "",  # indent
                    "",  # indent
                    f"  {mc['item_name']}",
                    f"  {mc['item_type']}",
                    mc['standard_quantity'],
                    mc['actual_quantity'],
                    f"  {mc['unit']}",
                    f"+{var_qty}" if var_qty > 0 else str(var_qty),
                    f"+{var_pct}%" if var_pct > 0 else f"{var_pct}%",
                    ("OVER" if var_qty > 0 else "UNDER") if mc['is_flagged'] else "",
                ])
            rows.append([""])  # blank spacer

    # Build the CSV manually so we can skip create_csv_response's header assumption
    from io import StringIO
    import csv as _csv
    buffer = StringIO()
    buffer.write('\ufeff')  # UTF-8 BOM for Excel
    writer = _csv.writer(buffer, quoting=_csv.QUOTE_MINIMAL)
    for row in rows:
        formatted_row = []
        for cell in row:
            if isinstance(cell, Decimal):
                formatted_row.append(f"{cell:.2f}")
            elif cell is None:
                formatted_row.append("")
            else:
                formatted_row.append(str(cell))
        writer.writerow(formatted_row)

    response = HttpResponse(buffer.getvalue(), content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = 'attachment; filename="production_variance_report.csv"'
    return response


# ---------------------------------------------------------------------------
# Receivables & Ageing CSV
# ---------------------------------------------------------------------------

def export_ageing_report_csv(report_data: dict, as_of_date) -> HttpResponse:
    headers = [
        "Customer Name", "Channel", "Total Outstanding (₹)",
        "Current (0-30 days) (₹)", "31-60 days (₹)", "61-90 days (₹)", "90+ days (₹)"
    ]
    rows = []
    for c in report_data.get('customers', []):
        rows.append([
            c['customer'].name,
            c['customer'].get_customer_type_display(),
            c['total_outstanding'],
            c['bucket_0_30'],
            c['bucket_31_60'],
            c['bucket_61_90'],
            c['bucket_90_plus'],
        ])
    s = report_data.get('summary', {})
    rows.append([
        "TOTAL", "", s.get('total_outstanding', Decimal('0.00')),
        s.get('bucket_0_30', Decimal('0.00')),
        s.get('bucket_31_60', Decimal('0.00')),
        s.get('bucket_61_90', Decimal('0.00')),
        s.get('bucket_90_plus', Decimal('0.00')),
    ])
    date_str = as_of_date.strftime('%Y%m%d') if hasattr(as_of_date, 'strftime') else str(as_of_date)
    return create_csv_response(f"accounts_receivable_ageing_{date_str}", headers, rows)


def export_payments_csv(payments: list) -> HttpResponse:
    headers = [
        "Receipt No", "Payment Date", "Customer Name", "Invoice No", "Payment Mode",
        "Reference No", "Amount Received (₹)", "Recorded By", "Notes"
    ]
    rows = []
    tot = Decimal('0.00')
    for p in payments:
        tot += p.amount
        rows.append([
            p.payment_number,
            p.payment_date.strftime('%Y-%m-%d'),
            p.customer.name,
            p.invoice.invoice_number if p.invoice else "",
            p.get_payment_mode_display(),
            p.reference_number,
            p.amount,
            p.recorded_by.username if p.recorded_by else "",
            p.notes,
        ])
    rows.append(["TOTAL", "", "", "", "", "", tot, "", ""])
    return create_csv_response("payments_collections_register", headers, rows)
