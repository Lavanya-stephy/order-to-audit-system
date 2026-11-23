import csv
from datetime import datetime, date, time
from decimal import Decimal
from typing import Dict, Any, List, Optional, Tuple
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.db.models import Sum, Q, Count

from masters.models import Customer, Supplier, Product, RawMaterial, PackagingItem
from orders.models import SalesOrder
from invoices.models import Invoice, InvoiceLine, InvoiceStatus, Payment
from inventory.models import StockMovement, MovementType
from inventory.services import get_stock_summary, get_all_inventory_items
from purchases.models import PurchaseOrder, PurchaseOrderLine
from production.models import ProductionRun, ProductionRunItem


# ---------------------------------------------------------------------------
# GST UQC (Unit Quantity Code) Mapper — GST Portal standard codes
# ---------------------------------------------------------------------------

# Maps common unit symbols / names (lower-case) to GST portal UQC codes.
# Reference: CBIC HSN/UQC notification. Extend as needed.
UQC_MAP = {
    # Packet / Pack
    'packet': 'PAC',
    'packets': 'PAC',
    'pkt': 'PAC',
    'pkts': 'PAC',
    'pac': 'PAC',
    'pack': 'PAC',
    # Kilogram
    'kg': 'KGS',
    'kgs': 'KGS',
    'kilogram': 'KGS',
    'kilograms': 'KGS',
    # Gram
    'g': 'GMS',
    'gm': 'GMS',
    'gms': 'GMS',
    'gram': 'GMS',
    'grams': 'GMS',
    # Litre
    'l': 'LTR',
    'ltr': 'LTR',
    'litre': 'LTR',
    'litres': 'LTR',
    'liter': 'LTR',
    'liters': 'LTR',
    # Millilitre
    'ml': 'MLT',
    'mlt': 'MLT',
    'millilitre': 'MLT',
    'milliliter': 'MLT',
    # Piece
    'piece': 'PCS',
    'pieces': 'PCS',
    'pcs': 'PCS',
    'pc': 'PCS',
    'nos': 'NOS',
    'no': 'NOS',
    'number': 'NOS',
    # Carton / Box
    'carton': 'BOX',
    'cartons': 'BOX',
    'ctn': 'BOX',
    'box': 'BOX',
    'boxes': 'BOX',
    # Metric Tonne
    'mt': 'MTS',
    'mts': 'MTS',
    'tonne': 'MTS',
    'ton': 'MTS',
}


def get_gst_uqc(symbol_or_name: str) -> str:
    """Return the GST portal UQC code for a given unit symbol or name.
    Falls back to 'OTH' (Others) when no mapping is found.
    """
    if not symbol_or_name:
        return 'OTH'
    key = str(symbol_or_name).strip().lower()
    return UQC_MAP.get(key, 'OTH')


def parse_report_dates(request) -> Tuple[Optional[date], Optional[date], str, str, str]:
    """
    Parses start_date, end_date, and preset from GET parameters.
    Returns (start_date, end_date, start_str, end_str, preset).
    """
    preset = request.GET.get('preset', '').strip().lower()
    start_str = request.GET.get('start_date', '').strip()
    end_str = request.GET.get('end_date', '').strip()

    today = timezone.localdate()

    if preset == 'this_month':
        start_date = today.replace(day=1)
        # End date is today
        end_date = today
        start_str = start_date.strftime('%Y-%m-%d')
        end_str = end_date.strftime('%Y-%m-%d')
    elif preset == 'last_month':
        first_of_this_month = today.replace(day=1)
        # Last day of previous month
        from datetime import timedelta
        last_day_prev = first_of_this_month - timedelta(days=1)
        start_date = last_day_prev.replace(day=1)
        end_date = last_day_prev
        start_str = start_date.strftime('%Y-%m-%d')
        end_str = end_date.strftime('%Y-%m-%d')
    elif preset == 'today':
        start_date = today
        end_date = today
        start_str = start_date.strftime('%Y-%m-%d')
        end_str = end_date.strftime('%Y-%m-%d')
    else:
        start_date = parse_date(start_str) if start_str else None
        end_date = parse_date(end_str) if end_str else None

    return start_date, end_date, start_str, end_str, preset


# ---------------------------------------------------------------------------
# 1. Sales Register, Customer-wise & Product-wise Sales
# ---------------------------------------------------------------------------

def get_sales_register_data(
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    customer_id: Optional[int] = None,
    status_filter: str = 'all',
) -> Dict[str, Any]:
    qs = (
        Invoice.objects
        .select_related('customer', 'order', 'created_by')
        .prefetch_related('lines', 'lines__product', 'lines__unit')
        .order_by('-invoice_date', '-invoice_number')
    )

    if start_date:
        qs = qs.filter(invoice_date__gte=start_date)
    if end_date:
        qs = qs.filter(invoice_date__lte=end_date)
    if customer_id:
        qs = qs.filter(customer_id=customer_id)
    if status_filter and status_filter != 'all':
        qs = qs.filter(status=status_filter)

    invoices = list(qs)

    # Detailed Invoices Summary
    total_taxable = sum((inv.taxable_value for inv in invoices), Decimal('0.00'))
    total_cgst = sum((inv.cgst_amount for inv in invoices), Decimal('0.00'))
    total_sgst = sum((inv.sgst_amount for inv in invoices), Decimal('0.00'))
    total_igst = sum((inv.igst_amount for inv in invoices), Decimal('0.00'))
    total_tax = total_cgst + total_sgst + total_igst
    total_grand = sum((inv.grand_total for inv in invoices), Decimal('0.00'))
    total_paid = sum((inv.amount_paid for inv in invoices), Decimal('0.00'))
    total_outstanding = sum((inv.outstanding_balance for inv in invoices), Decimal('0.00'))

    # Customer-wise Aggregation
    customers_map: Dict[int, Dict[str, Any]] = {}
    for inv in invoices:
        cid = inv.customer_id
        if cid not in customers_map:
            customers_map[cid] = {
                'customer': inv.customer,
                'invoices_count': 0,
                'taxable_value': Decimal('0.00'),
                'cgst': Decimal('0.00'),
                'sgst': Decimal('0.00'),
                'igst': Decimal('0.00'),
                'total_tax': Decimal('0.00'),
                'grand_total': Decimal('0.00'),
                'amount_paid': Decimal('0.00'),
                'outstanding': Decimal('0.00'),
            }
        rec = customers_map[cid]
        rec['invoices_count'] += 1
        rec['taxable_value'] += inv.taxable_value
        rec['cgst'] += inv.cgst_amount
        rec['sgst'] += inv.sgst_amount
        rec['igst'] += inv.igst_amount
        rec['total_tax'] += (inv.cgst_amount + inv.sgst_amount + inv.igst_amount)
        rec['grand_total'] += inv.grand_total
        rec['amount_paid'] += inv.amount_paid
        rec['outstanding'] += inv.outstanding_balance

    customer_sales = sorted(customers_map.values(), key=lambda x: x['grand_total'], reverse=True)

    # Product-wise Aggregation
    products_map: Dict[int, Dict[str, Any]] = {}
    for inv in invoices:
        # Include lines from valid invoices
        if inv.status == InvoiceStatus.CANCELLED:
            continue
        for line in inv.lines.all():
            pid = line.product_id
            if pid not in products_map:
                products_map[pid] = {
                    'product': line.product,
                    'quantity': Decimal('0.00'),
                    'unit': line.unit,
                    'taxable_value': Decimal('0.00'),
                    'cgst': Decimal('0.00'),
                    'sgst': Decimal('0.00'),
                    'igst': Decimal('0.00'),
                    'total_tax': Decimal('0.00'),
                    'total_value': Decimal('0.00'),
                }
            prec = products_map[pid]
            prec['quantity'] += line.quantity
            prec['taxable_value'] += line.taxable_value
            prec['cgst'] += line.cgst_amount
            prec['sgst'] += line.sgst_amount
            prec['igst'] += line.igst_amount
            prec['total_tax'] += (line.cgst_amount + line.sgst_amount + line.igst_amount)
            prec['total_value'] += line.line_total

    for p in products_map.values():
        if p['quantity'] > Decimal('0.00'):
            p['avg_rate'] = (p['taxable_value'] / p['quantity']).quantize(Decimal('0.01'))
        else:
            p['avg_rate'] = Decimal('0.00')

    product_sales = sorted(products_map.values(), key=lambda x: x['total_value'], reverse=True)

    return {
        'invoices': invoices,
        'customer_sales': customer_sales,
        'product_sales': product_sales,
        'totals': {
            'count': len(invoices),
            'taxable_value': total_taxable,
            'cgst': total_cgst,
            'sgst': total_sgst,
            'igst': total_igst,
            'total_tax': total_tax,
            'grand_total': total_grand,
            'amount_paid': total_paid,
            'outstanding': total_outstanding,
        }
    }


# ---------------------------------------------------------------------------
# 2. GST Summary (GSTR-1 & GSTR-3B)
# ---------------------------------------------------------------------------

def get_gst_summary_data(
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
) -> Dict[str, Any]:
    """
    Prepares outward supplies summary mapped directly to GSTR-1 & GSTR-3B reporting.
    Excludes cancelled invoices.
    """
    qs = (
        Invoice.objects
        .filter(status=InvoiceStatus.POSTED)
        .select_related('customer', 'order')
        .prefetch_related('lines', 'lines__product', 'lines__unit')
        .order_by('invoice_date', 'invoice_number')
    )

    if start_date:
        qs = qs.filter(invoice_date__gte=start_date)
    if end_date:
        qs = qs.filter(invoice_date__lte=end_date)

    invoices = list(qs)

    # GSTR-1: Table 4 - B2B Supplies (Customer has GSTIN)
    b2b_invoices = [inv for inv in invoices if inv.customer and inv.customer.gstin and inv.customer.gstin.strip()]
    b2b_taxable = sum((inv.taxable_value for inv in b2b_invoices), Decimal('0.00'))
    b2b_cgst = sum((inv.cgst_amount for inv in b2b_invoices), Decimal('0.00'))
    b2b_sgst = sum((inv.sgst_amount for inv in b2b_invoices), Decimal('0.00'))
    b2b_igst = sum((inv.igst_amount for inv in b2b_invoices), Decimal('0.00'))
    b2b_total = sum((inv.grand_total for inv in b2b_invoices), Decimal('0.00'))

    # GSTR-1: Table 5 / 7 - B2C Supplies (Customer has NO GSTIN)
    b2c_invoices = [inv for inv in invoices if not (inv.customer and inv.customer.gstin and inv.customer.gstin.strip())]
    # Group B2C by State / Place of supply
    b2c_map: Dict[str, Dict[str, Any]] = {}
    for inv in b2c_invoices:
        state_key = inv.customer.state if inv.customer else 'Tamil Nadu'
        state_code = inv.customer.state_code if inv.customer else '33'
        pos = f"{state_key} ({state_code})"
        supply_type = "Inter-State" if inv.is_interstate else "Intra-State"
        key = (pos, supply_type)
        if key not in b2c_map:
            b2c_map[key] = {
                'place_of_supply': pos,
                'supply_type': supply_type,
                'rate': Decimal('5.00'),
                'count': 0,
                'taxable_value': Decimal('0.00'),
                'cgst': Decimal('0.00'),
                'sgst': Decimal('0.00'),
                'igst': Decimal('0.00'),
                'total_tax': Decimal('0.00'),
                'invoice_value': Decimal('0.00'),
            }
        rec = b2c_map[key]
        rec['count'] += 1
        rec['taxable_value'] += inv.taxable_value
        rec['cgst'] += inv.cgst_amount
        rec['sgst'] += inv.sgst_amount
        rec['igst'] += inv.igst_amount
        rec['total_tax'] += (inv.cgst_amount + inv.sgst_amount + inv.igst_amount)
        rec['invoice_value'] += inv.grand_total

    b2c_summary = sorted(b2c_map.values(), key=lambda x: x['place_of_supply'])
    b2c_taxable = sum((r['taxable_value'] for r in b2c_summary), Decimal('0.00'))
    b2c_cgst = sum((r['cgst'] for r in b2c_summary), Decimal('0.00'))
    b2c_sgst = sum((r['sgst'] for r in b2c_summary), Decimal('0.00'))
    b2c_igst = sum((r['igst'] for r in b2c_summary), Decimal('0.00'))
    b2c_total = sum((r['invoice_value'] for r in b2c_summary), Decimal('0.00'))

    # GSTR-1: Table 12 - HSN-wise Summary of Outward Supplies
    hsn_map: Dict[str, Dict[str, Any]] = {}
    for inv in invoices:
        for line in inv.lines.all():
            prod = line.product
            hsn = prod.hsn_code or '19059040'
            key = (hsn, prod.name)
            if key not in hsn_map:
                hsn_map[key] = {
                    'hsn_code': hsn,
                    'description': prod.name,
                    'uqc': get_gst_uqc(prod.unit.symbol),
                    'total_quantity': Decimal('0.00'),
                    'total_value': Decimal('0.00'),
                    'taxable_value': Decimal('0.00'),
                    'igst': Decimal('0.00'),
                    'cgst': Decimal('0.00'),
                    'sgst': Decimal('0.00'),
                    'cess': Decimal('0.00'),
                    'total_tax': Decimal('0.00'),
                }
            hrec = hsn_map[key]
            hrec['total_quantity'] += line.quantity
            hrec['total_value'] += line.line_total
            hrec['taxable_value'] += line.taxable_value
            hrec['igst'] += line.igst_amount
            hrec['cgst'] += line.cgst_amount
            hrec['sgst'] += line.sgst_amount
            hrec['total_tax'] += (line.igst_amount + line.cgst_amount + line.sgst_amount)

    hsn_summary = sorted(hsn_map.values(), key=lambda x: x['hsn_code'])

    # GSTR-3B Table 3.1 & 3.2
    total_taxable = sum((inv.taxable_value for inv in invoices), Decimal('0.00'))
    total_cgst = sum((inv.cgst_amount for inv in invoices), Decimal('0.00'))
    total_sgst = sum((inv.sgst_amount for inv in invoices), Decimal('0.00'))
    total_igst = sum((inv.igst_amount for inv in invoices), Decimal('0.00'))
    total_cess = Decimal('0.00')

    # Table 3.2: Inter-state supplies made to unregistered persons
    interstate_unreg = [
        inv for inv in b2c_invoices if inv.is_interstate
    ]
    interstate_unreg_map: Dict[str, Dict[str, Any]] = {}
    for inv in interstate_unreg:
        state_key = inv.customer.state if inv.customer else 'Other'
        if state_key not in interstate_unreg_map:
            interstate_unreg_map[state_key] = {
                'place_of_supply': state_key,
                'taxable_value': Decimal('0.00'),
                'igst': Decimal('0.00'),
            }
        irec = interstate_unreg_map[state_key]
        irec['taxable_value'] += inv.taxable_value
        irec['igst'] += inv.igst_amount

    return {
        'invoices_count': len(invoices),
        # GSTR-1
        'b2b_invoices': b2b_invoices,
        'b2b_totals': {
            'count': len(b2b_invoices),
            'taxable_value': b2b_taxable,
            'cgst': b2b_cgst,
            'sgst': b2b_sgst,
            'igst': b2b_igst,
            'grand_total': b2b_total,
        },
        'b2c_summary': b2c_summary,
        'b2c_totals': {
            'count': len(b2c_invoices),
            'taxable_value': b2c_taxable,
            'cgst': b2c_cgst,
            'sgst': b2c_sgst,
            'igst': b2c_igst,
            'grand_total': b2c_total,
        },
        'hsn_summary': hsn_summary,
        # GSTR-3B Table 3.1
        'gstr3b_3_1': {
            'taxable_value': total_taxable,
            'igst': total_igst,
            'cgst': total_cgst,
            'sgst': total_sgst,
            'cess': total_cess,
            'total_tax': total_cgst + total_sgst + total_igst,
        },
        # GSTR-3B Table 3.2
        'gstr3b_3_2': list(interstate_unreg_map.values()),
    }


# ---------------------------------------------------------------------------
# 3. Purchase Register
# ---------------------------------------------------------------------------

def get_purchase_register_data(
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    supplier_id: Optional[int] = None,
    status_filter: str = 'all',
) -> Dict[str, Any]:
    qs = (
        PurchaseOrder.objects
        .select_related('supplier', 'created_by')
        .prefetch_related('lines', 'lines__raw_material', 'lines__packaging_item', 'lines__unit')
        .order_by('-order_date', '-po_number')
    )

    if start_date:
        qs = qs.filter(order_date__gte=start_date)
    if end_date:
        qs = qs.filter(order_date__lte=end_date)
    if supplier_id:
        qs = qs.filter(supplier_id=supplier_id)
    if status_filter and status_filter != 'all':
        qs = qs.filter(status=status_filter)

    pos = list(qs)

    detailed_lines = []
    total_rm_val = Decimal('0.00')
    total_pm_val = Decimal('0.00')

    for po in pos:
        for line in po.lines.all():
            item_name = line.item_name
            is_rm = line.raw_material is not None
            line_tot = line.line_total
            if is_rm:
                total_rm_val += line_tot
            else:
                total_pm_val += line_tot

            detailed_lines.append({
                'po_number': po.po_number,
                'order_date': po.order_date,
                'supplier': po.supplier,
                'item_name': item_name,
                'item_type': 'Raw Material' if is_rm else 'Packaging Item',
                'quantity': line.quantity,
                'unit': line.unit,
                'unit_price': line.unit_price,
                'line_total': line_tot,
                'status': po.get_status_display(),
            })

    total_val = total_rm_val + total_pm_val

    # Supplier-wise aggregation
    suppliers_map: Dict[int, Dict[str, Any]] = {}
    for line in detailed_lines:
        sid = line['supplier'].id
        if sid not in suppliers_map:
            suppliers_map[sid] = {
                'supplier': line['supplier'],
                'lines_count': 0,
                'total_value': Decimal('0.00'),
            }
        srec = suppliers_map[sid]
        srec['lines_count'] += 1
        srec['total_value'] += line['line_total']

    supplier_summary = sorted(suppliers_map.values(), key=lambda x: x['total_value'], reverse=True)

    return {
        'purchase_orders': pos,
        'detailed_lines': detailed_lines,
        'supplier_summary': supplier_summary,
        'totals': {
            'pos_count': len(pos),
            'lines_count': len(detailed_lines),
            'rm_total': total_rm_val,
            'pm_total': total_pm_val,
            'grand_total': total_val,
        }
    }


# ---------------------------------------------------------------------------
# 4. Production Report (Variance & Wastage)
# ---------------------------------------------------------------------------

def get_production_variance_report_data(
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    product_id: Optional[int] = None,
    status_filter: str = 'all',
) -> Dict[str, Any]:
    qs = (
        ProductionRun.objects
        .select_related('product', 'bom', 'created_by')
        .prefetch_related('items', 'items__raw_material', 'items__packaging_item', 'items__unit')
        .order_by('-start_date', '-run_number')
    )

    if start_date:
        qs = qs.filter(start_date__gte=start_date)
    if end_date:
        qs = qs.filter(start_date__lte=end_date)
    if product_id:
        qs = qs.filter(product_id=product_id)
    if status_filter and status_filter != 'all':
        qs = qs.filter(status=status_filter)

    runs = list(qs)

    total_expected_pkts = 0
    total_actual_pkts = 0
    total_damaged_pouches = 0
    total_cartons_used = 0
    total_production_cost = Decimal('0.00')
    flagged_runs_count = 0

    runs_data = []
    for run in runs:
        if run.expected_yield:
            total_expected_pkts += run.expected_yield
        if run.actual_yield:
            total_actual_pkts += run.actual_yield
        total_damaged_pouches += run.damaged_pouches
        total_cartons_used += run.cartons_used
        total_production_cost += run.total_production_cost

        # Build flagged_reasons and material_consumption list
        flagged_reasons = []
        if run.is_yield_variance_flagged:
            flagged_reasons.append('Yield')

        # All items (raw materials + packaging) in insertion order
        all_items = list(run.items.select_related('raw_material', 'packaging_item', 'unit').all())

        material_consumption = []
        for item in all_items:
            is_rm = item.raw_material is not None
            var_pct = item.consumption_variance_pct
            if item.is_variance_flagged:
                flagged_reasons.append(item.item_name)

            material_consumption.append({
                'item_name': item.item_name,
                'item_type': 'Raw Material' if is_rm else 'Packaging',
                'standard_quantity': item.standard_quantity,
                'actual_quantity': item.actual_quantity,
                'unit': item.unit.symbol if item.unit else '',
                'variance_quantity': item.consumption_variance_quantity,
                'variance_pct': var_pct,
                'is_flagged': item.is_variance_flagged,
            })

        has_variance_flag = bool(flagged_reasons)
        if has_variance_flag:
            flagged_runs_count += 1
            flag_label = f"FLAGGED ({', '.join(flagged_reasons)})"
        else:
            flag_label = 'Normal'

        runs_data.append({
            'run': run,
            'rm_items': [i for i in all_items if i.raw_material is not None],
            'pkg_items': [i for i in all_items if i.packaging_item is not None],
            'material_consumption': material_consumption,
            'has_variance_flag': has_variance_flag,
            'flagged_reasons': flagged_reasons,
            'flag_label': flag_label,
        })

    avg_cost_per_pkt = (
        (total_production_cost / Decimal(str(total_actual_pkts))).quantize(Decimal('0.01'))
        if total_actual_pkts > 0 else Decimal('0.00')
    )
    overall_yield_pct = (
        (Decimal(str(total_actual_pkts)) / Decimal(str(total_expected_pkts)) * Decimal('100')).quantize(Decimal('0.01'))
        if total_expected_pkts > 0 else Decimal('0.00')
    )

    return {
        'runs_data': runs_data,
        'totals': {
            'runs_count': len(runs),
            'total_expected_pkts': total_expected_pkts,
            'total_actual_pkts': total_actual_pkts,
            'overall_yield_pct': overall_yield_pct,
            'total_damaged_pouches': total_damaged_pouches,
            'total_cartons_used': total_cartons_used,
            'total_production_cost': total_production_cost,
            'avg_cost_per_pkt': avg_cost_per_pkt,
            'flagged_runs_count': flagged_runs_count,
        }
    }
