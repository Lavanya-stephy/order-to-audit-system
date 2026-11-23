# Order-to-Audit System: Project Blueprint & Technical Notes
**Hypothetical Client:** Small-scale packaged South Indian food manufacturer (e.g., Murukku, Mixture, Chips, Sweets) based in Tamil Nadu, India.  
**Objective:** Replace fragmented operations (WhatsApp orders, notebooks, spreadsheets, manual billing) with an integrated prototype where every transaction is entered once at its source and flows automatically into stock, production, costing, and auditor-ready reports.

---

## 1. Non-Negotiable Project Rules

These architectural rules apply to all modules and must be preserved across every iteration:

1. **Money Uses Decimal (Never Float):**
   - Financial arithmetic (prices, line totals, tax calculations, invoices, payments, receivables) must never use floating-point types to prevent rounding drift.
   - All monetary fields in models use Django's `DecimalField(max_digits=12, decimal_places=2)`.
   - Tax rates, quantities, and conversion rates also use `DecimalField` with required precision (e.g., 3 decimal places for weights in kg and volumes in litres).

2. **Stock Balances Are Always Derived from a StockMovement Ledger (Never Overwritten):**
   - No table or model will maintain an arbitrarily editable `current_stock` column where someone can execute `stock = 150` or `stock -= 10`.
   - Current inventory is always computed by aggregating movements:
     $$\text{Closing Balance} = \text{Opening Balance} + \text{Receipts} - \text{Issues/Dispatches} \pm \text{Adjustments}$$
   - The ledger (`StockMovement`) is append-only and provides an immutable audit trail.

3. **Every Movement Links to Its Source Document:**
   - Every entry in `StockMovement` must have a valid reference to the document that created it:
     - Purchase receipt / GRN (Goods Received Note)
     - Production Run (raw material consumption or finished goods yield)
     - Sales Invoice / Dispatch note
     - Physical inventory audit adjustment (with documented reason)
   - Orphan stock records are forbidden.

4. **Code Simplicity & Interview Explainability:**
   - The codebase must prioritize clarity, readability, and clean architecture over clever metaprogramming or unnecessary third-party abstractions.
   - Any shortlisted candidate must be able to clearly walk through the database schema, query patterns, and calculation logic in a 30-minute interview and make live modifications with confidence.

---

## 2. Core Business Loops

The architecture joins two operational loops that intersect at **Finished-Goods Stock**:

```
[PRODUCTION LOOP]
Raw Materials Purchased ──> Inward Stock Movement (Raw/Packaging)
       │
       ▼ (Issued against BOM)
Production Run (Actual vs Planned) ──> Outward Stock Movement (Raw/Packaging)
       │
       ▼ (Output & Yield)
Finished Packets Produced ──> Inward Stock Movement (Finished Goods)
                                     │
                                     ▼
                          [FINISHED GOODS STOCK]
                                     ▲
                                     │
[SALES LOOP]                         │
Salesman Field Order (Mobile)        │
       │                             │
       ▼                             │
Factory Admin Verification & Stock Check
       │
       ▼
GST Tax Invoice Generated (CGST/SGST or IGST)
       │
       ▼
Dispatch ────────────────────────────┴─ Outward Stock Movement (Finished Goods)
       │
       ▼
Receivables Ledger & Payment Collections (Outstanding / Ageing)
```

Both loops converge to generate the **Auditor's Monthly Pack**:
- Sales & Outward GST Register (GSTR-1 / GSTR-3B compliant)
- Stock Summary & Itemized Stock Ledger
- Production Variance & Yield Report
- Cost per Packet & Margin Analysis
- Customer Receivables Ageing Report

---

## 3. Systematic Build Order

Following Section 6 of `PROBLEM.md`, development will be executed in staged phases:

### Phase 1: Foundation & Master Data
- [x] User authentication with Role-Based Access Control (RBAC):
  - `Salesman`: Mobile order placement, status tracking, customer-specific sales.
  - `Factory Admin`: Order review, stock verification, GST invoicing, dispatch, payments.
  - `Production Supervisor`: Raw material inward, daily production logging, planned vs actual output.
  - `Accountant / Auditor`: Read-only access to monthly audit packs and export registers.
  - `Owner`: High-level operational dashboard (orders, stock alerts, variances, dues).
  - Role-based login redirection (`ROLE_DASHBOARD_URLS`) and strict permission decorator (`@role_required`).
- [x] Master Data Models:
  - Unit of Measure (`Unit`): kg, g, litre, ml, piece, packet, carton with category ratios and conversion rules (`UnitConversion`).
  - Raw Materials (`RawMaterial`): Flour, cooking oil, spices with standard costs and reorder thresholds.
  - Packaging Items (`PackagingItem`): Pouches, cartons, capacity mappings, and purchase rates.
  - Finished Goods (`Product`): Pack size, HSN codes (e.g. 19059040), pre-tax selling price (₹50.00), GST rate (5.00%), carton packet capacities.
  - Customer & Supplier masters (`Customer`, `Supplier`): Retailer vs Distributor channel, GSTIN, State code (`is_interstate()` logic).
  - Web CRUD interfaces and Django Admin registrations with role permissions.
- [x] Bill of Materials (`BillOfMaterial` & `BOMLine`):
  - Standard recipe formulas per finished product with expected yield in packets per batch.
  - Line items supporting either Raw Materials (flour, oil, spices) or Packaging Items (pouches, cartons).
  - Dynamic standard costing (`total_standard_cost`, `standard_cost_per_packet`, gross margins).
  - Web screens to create, edit, view, and delete BOMs with multi-line formsets.
  - Benchmark Murukku 200g BOM (40 kg flour, 10 L oil, 1.2 kg spices, 200 pouches, 10 cartons; 200 pkts yield; ₹19.85/pkt cost).

### Phase 2: Inventory Ledger & Production Loop (Highest Evaluation Weight)
- [x] `StockMovement` append-only ledger model with document linkage:
  - Signed quantities (+ for inward receipts/yield, - for outward issues/dispatch).
  - Movement types: `opening`, `purchase`, `production_issue`, `production_output`, `dispatch`, `adjustment`, `return`.
  - Non-negotiable formula enforced: $\text{Opening Balance} + \text{Inward Receipts} - \text{Outward Issues} = \text{Closing Balance}$.
  - Real-time stock summary dashboard (`/inventory/summary/`) filterable by category and date range.
  - Traceable stock ledger audit trail (`/inventory/ledger/`) with running balances and source document references.
  - Physical audit adjustment recording interface (`/inventory/adjust/`).
- [ ] Production Run (`ProductionRun` & `ProductionRunItem`):
  - Select finished product and batch quantity.
  - Calculate standard BOM recipe requirements.
  - Record actual raw/packaging materials issued and actual output yield (good packets, damaged, scrap).
  - Automatically create ledger movements:
    - Reduce raw & packaging stock.
    - Increase finished goods stock.
  - Compute consumption variance % and yield variance %, flagging variances exceeding tolerance (e.g., >3%).

### Phase 3: Sales Loop, GST Billing & Dispatch
- [ ] Sales Order module:
  - Mobile-responsive order entry for salesmen.
  - Customer selection, line items with price list rates.
  - Offline-ready / draft submission capability.
- [ ] Order Approval & Stock Reservation:
  - Admin view showing real-time finished goods stock coverage before approval.
  - Rejection / quantity adjustment workflow.
- [ ] GST Tax Invoice:
  - Automatic invoice numbering per Financial Year (e.g., `INV/2026-27/0001`).
  - Place of Supply rules: Intra-state (Tamil Nadu to Tamil Nadu) $\rightarrow$ CGST + SGST; Inter-state $\rightarrow$ IGST.
  - Clean PDF invoice generation with downloadable/shareable link.
- [ ] Dispatch Confirmation:
  - Triggers finished goods stock reduction in the ledger.
- [ ] Payments & Collections:
  - Recording customer payment entries against open invoices.
  - Customer outstanding balance and receivables tracking.

### Phase 4: Costing & Overheads
- [ ] Material costing: Valuation based on purchase rates (weighted average or latest purchase rate).
- [ ] Overhead allocation: Recording labour, power, fuel, and packaging costs per run.
- [ ] Cost per packet computation:
  $$\text{Cost per Packet} = \frac{\text{Total Material Cost} + \text{Allocated Overheads}}{\text{Actual Good Packets Produced}}$$
- [ ] Gross margin analysis against selling price.

### Phase 5: Reporting, Auditor Exports & Management Dashboard
- [ ] Sales Register (customer-wise and product-wise).
- [ ] GST Summary of outward supplies (taxable value, CGST, SGST, IGST).
- [ ] Stock Summary & Stock Ledger (opening, inward, outward, closing balance).
- [ ] Production variance and wastage report.
- [ ] Receivables report with ageing buckets (0-30 days, 31-60 days, 60+ days).
- [ ] Export to CSV/Excel and printable formats.
- [ ] Owner dashboard showing daily snapshot.

### Phase 6: Benchmark Scenario Automated Seed & Test Harness
- [ ] Management command (`python manage.py seed_benchmark`) loading the exact Section 5 master data.
- [ ] Automated end-to-end integration test verifying the 9 demonstration steps.

---

## 4. Benchmark Scenario Reference Data (Section 5)

| Item | Type | Qty per Batch | Unit | Benchmark Rate | Opening Stock |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Flour** | Raw Material | 40 | kg | ₹42 (opening), ₹45 (new purchase) | 100 kg |
| **Cooking Oil** | Raw Material | 10 | litre | ₹140 | 30 L |
| **Salt & Spice Mix**| Raw Material | 1.2 | kg | ₹200 | 5 kg |
| **200 g Pouch** | Packaging | 200 | piece | ₹2.50 | 500 pcs |
| **Carton** (20 pkts)| Packaging | 10 | piece | ₹15.00 | 30 pcs |
| **Murukku 200 g**| Finished Good | 200 (expected) | packet | ₹50.00 (selling price, 5% GST) | 50 pkts |

### Expected Verification Checklist

| Step | Action | Expected Audit Result |
| :--- | :--- | :--- |
| 1 | Purchase 60 kg flour @ ₹45/kg | Flour closing balance: **120 kg** ($100 + 60 - 40$) |
| 2-3| Issue 40 kg flour, 10.5 L oil (+0.5 L), 1.2 kg spices; Produce 188 pkts, 6 damaged pouches, 9 cartons used | - Oil closing balance: **19.5 L**<br>- Pouches closing balance: **306** ($500 - 188 - 6$)<br>- Finished Goods after run: **238 pkts** ($50 + 188$)<br>- Yield variance: **-6%** (188 vs 200, flagged)<br>- Oil consumption variance: **+5%** (10.5 vs 10 L, flagged) |
| 4-5| Salesman A orders 150 pkts for Retailer A (TN); Admin approves, invoices, dispatches | - Finished Goods after dispatch: **88 pkts** ($238 - 150$)<br>- Retailer A Invoice: ₹7,500 taxable + ₹187.50 CGST + ₹187.50 SGST = **₹7,875** |
| 6 | Salesman B orders 120 pkts for Distributor B (Karnataka) | Insufficient stock flagged (Shortage of **32 pkts** against 88 on hand); IGST applicable if invoiced |
| 7 | Payment of ₹4,000 recorded from Retailer A | Retailer A outstanding balance: **₹3,875** ($7,875 - 4,000$) |
| 8 | Add Labour ₹1,200 + Gas/Power ₹600 to the run | Cost per packet calculated with clear overhead allocation formula |
| 9 | Generate monthly reports | Auditor reports exported matching above figures |

---

## 5. Technology Stack Rationale

- **Backend:** Python 3.12+ / Django 5+
  - Django provides an enterprise-grade ORM, atomic transactions (`transaction.atomic()`), built-in role/permission handling, and admin interfaces that accelerate development while ensuring relational integrity.
- **Database:** SQLite for rapid zero-dependency local development and testing; instantly switchable to PostgreSQL via environment variables (`POSTGRES_DB` or `DATABASE_URL`) without modifying code.
- **Containerization:** Multi-stage `Dockerfile` and `docker-compose.yml` for unified one-command local and evaluation setup.

---

## 6. Production Costing & Valuation (Weighted Average Method)

### 1. Costing Method: Moving Weighted Average Cost (WAC)
- **Calculation:** The unit cost of each raw material and packaging item is the moving weighted average cost of stock on hand at the time of issue:
  $$\text{Weighted Average Unit Cost} = \frac{\text{Current Stock Value} + \text{Inward Receipt Value}}{\text{Current Stock Quantity} + \text{Inward Receipt Quantity}}$$
- **Snapshot Rule:** When a production run is completed, a permanent cost snapshot (`unit_cost` and `total_cost`) is frozen on each `ProductionRunItem`. Future material purchases at higher or lower rates never retroactively alter the cost of an already completed production run.
- **Absorbed Packaging Loss:** Packaging cost includes all pouches consumed—both good packets produced and damaged pouches (e.g., $188 + 6 = 194$ pouches). Damaged pouches are treated as an absorbed manufacturing loss reflected in the cost of good packets.

### 2. Overhead Allocation Rule
- Direct labour (e.g., ₹1,200.00) and power/gas (e.g., ₹600.00) entered for a run are charged **entirely** to the batch of product produced in that run.
- **Total Run Cost Formula:**
  $$\text{Total Run Cost} = \text{Raw Material Cost} + \text{Packaging Cost} + \text{Direct Labour} + \text{Power / Gas Overheads}$$
- **Cost per Good Packet:**
  $$\text{Cost per Packet} = \frac{\text{Total Run Cost}}{\text{Actual Good Packets Produced}}$$
- **Margin:**
  $$\text{Margin per Packet} = \text{Selling Price} - \text{Cost per Packet}$$
  $$\text{Margin \%} = \frac{\text{Selling Price} - \text{Cost per Packet}}{\text{Selling Price}} \times 100$$

### 3. Why Weighted Average Cost?
- **Fungible Bulk Ingredients:** In snack food manufacturing, bulk staples like flour, oil, and spices are stored in shared bins and tanks. Tracking individual bags or lots (FIFO/LIFO lot tracking) is practically impossible on a small factory floor where raw materials mix seamlessly.
- **Price Smoothing:** Commodity ingredient prices fluctuate constantly. Moving weighted average naturally blends opening inventory and recent purchase prices, preventing artificial margin spikes between consecutive batches.
- **Accounting & Audit Standards:** Weighted average cost (WAC) is recognized under Indian Accounting Standards (Ind AS 2 / AS 2) and tax guidelines as an accurate, compliant method for inventory valuation and Cost of Goods Sold (COGS).

---

## 7. Section 4.6 Reports for Accounts & Audit

The reporting suite provides complete monthly auditor packs, filterable by date range and exportable to CSV/Excel and PDF:

1. **Sales Register & Outward Invoices (`/reports/sales-register/`):**
   - Detailed invoice register with Place of Supply, Taxable Value, CGST, SGST, IGST, Invoice Total, and Outstanding Balances.
   - Customer-wise aggregated sales breakdown.
   - Product-wise sales volume, average selling rate, and revenue breakdown.
   - Export to CSV/Excel and PDF.

2. **GST Summary of Outward Supplies (`/reports/gst-summary/`):**
   - **GSTR-3B Table 3.1 & 3.2:** Outward taxable supplies by tax category (Central, State, Integrated, Cess).
   - **GSTR-1 Table 4:** Registered B2B supplies with recipient GSTIN, invoice details, and tax breakdowns.
   - **GSTR-1 Table 12:** HSN-wise summary of outward supplies (HSN 19059040, UQC, quantities, values, taxes).
   - Export to CSV/Excel and PDF.

3. **Purchase Register (`/reports/purchases/`):**
   - Goods received notes (GRN) and purchase orders for raw materials and packaging.
   - Supplier breakdown with item codes, received quantities, unit rates, and line totals.
   - Export to CSV/Excel and PDF.

4. **Stock Summary & Stock Ledger (`/reports/stock/`, `/inventory/summary/`, `/inventory/ledger/`):**
   - Derived balance formula: $\text{Opening} + \text{Inward} - \text{Outward} \pm \text{Adjustments} = \text{Closing}$.
   - Category filtering (Raw Materials, Packaging, Finished Goods) with standard valuation.
   - Traceable item ledger with running balance and source document links.
   - Export to CSV/Excel and PDF.

5. **Production Variance & Wastage Report (`/reports/production/`):**
   - Standard recipe requirements vs actual material consumption (variance % and flags).
   - Output yields, damaged packaging absorbed losses, and run-level batch costing.
   - Export to CSV/Excel and PDF.

6. **Customer Receivables, Ageing & Payments (`/reports/receivables/`, `/invoices/ageing/`):**
   - Accounts receivable ageing categorized across 0-30, 31-60, 61-90, and 90+ day buckets.
   - Payment collections register linked to invoices and customer receipts.
   - Export to CSV/Excel and PDF.

7. **Accountant Role Permissions:**
   - The `Accountant / Auditor` role (`Role.ACCOUNTANT`) has full read-only access to view and export all Section 4.6 reports.
   - Accountants cannot create, update, delete, approve, cancel, or dispatch operational transactions (orders, invoices, production runs, purchases, adjustments).
