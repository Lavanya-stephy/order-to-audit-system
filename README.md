# Order-to-Audit System for Small Food Manufacturers

**Centre for Digital Infrastructure, NIT Tiruchirappalli — Internship Technical Project**

An integrated enterprise solution designed for small-scale food manufacturing factories (such as traditional snack, sweet, and baked goods units). The system connects the entire operational lifecycle—from field salesman mobile order taking to real-time inventory ledgering, recipe Bill of Materials (BOM) production runs with variance tracking, GST-compliant invoicing, customer receivables ageing, and auditor-ready statutory reports.

---

## 1. Technology Stack & Justification

We chose **Python 3.11+ / Django 5.x** paired with **SQLite** (switchable to **PostgreSQL** via environment variables), **ReportLab**, and **Docker Compose**:

* **Python & Django 5.x:**
  * **Relational Consistency:** Django's transactional ORM (`transaction.atomic`) guarantees atomic commits across stock movements, invoice generation, and balance updates, eliminating partial writes and race conditions.
  * **Role-Based Security:** Built-in session authentication, permission decorators (`@role_required`), and CSRF protection enforce strict role isolation across Salesman, Admin, Production Supervisor, Accountant, and Owner.
  * **Rapid & Maintainable:** Django’s form validation, built-in admin tooling, and template engine eliminate heavy frontend-backend synchronization drift, keeping the codebase transparent, reproducible, and explainable in a technical review.
* **Database (SQLite for Dev/Test, PostgreSQL for Production):**
  * **SQLite:** Zero-setup local execution and ultra-fast in-memory automated test execution (runs 146 tests in ~7 seconds).
  * **PostgreSQL-Ready:** Database configuration in `config/settings.py` seamlessly maps to PostgreSQL using standard environment variables (`DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT`) without modifying application code.
* **ReportLab:**
  * Generates high-fidelity, printable PDF documents (Tax Invoices and statutory reports) server-side with precise millimeter layouts, table formatting, and embedded Unicode font support (`DejaVuSans.ttf`) for Indian Rupee (`₹`) symbol rendering.
* **Docker Compose:**
  * Delivers a single-command reproducible container environment encompassing web application, static assets, and database services.

---

## 2. Quick Start & Setup

### Prerequisites
* Python 3.11 or higher
* `pip` and virtual environment support (`venv`)
* Docker & Docker Compose (optional, for containerized run)

---

### Option A: Local Development Setup (Recommended)

1. **Clone the repository:**
   ```bash
   git clone <repo-url>
   cd order-to-audit-system
   ```

2. **Create and activate a virtual environment:**
   ```bash
   # Windows (PowerShell)
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1

   # Linux / macOS
   python3 -m venv .venv
   source .venv/bin/activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Apply database migrations:**
   ```bash
   python manage.py migrate
   ```

5. **Seed standard users and master data:**
   ```bash
   # Creates standard users for all roles
   python manage.py create_test_users

   # Loads the complete Section 5 benchmark masters & opening stock
   python manage.py seed_benchmark
   ```

6. **Run all automated tests:**
   ```bash
   python manage.py test
   ```
   *(Expected output: `Ran 146 tests in ~7s — OK`)*

7. **Start the development server:**
   ```bash
   python manage.py runserver 0.0.0.0:8000
   ```
   Access the web application at [http://127.0.0.1:8000](http://127.0.0.1:8000).

---

### Option B: Docker Compose

Run the entire system in an isolated container:

```bash
# Build and launch application container
docker compose up --build

# Run in detached mode (background)
docker compose up -d

# Run migrations and seed benchmark inside container
docker compose exec web python manage.py migrate
docker compose exec web python manage.py seed_benchmark
```

To switch to PostgreSQL in Docker:
1. Uncomment the PostgreSQL service and environment variables in `docker-compose.yml`.
2. Re-run `docker compose up --build`.

---

### Role-Based Test Credentials

All accounts are created with default password `pass1234` (or as specified below):

| Role | Username | Password | Default Portal Endpoint | Operational Scope |
| :--- | :--- | :--- | :--- | :--- |
| **Salesman** | `salesman` / `salesman_a` | `salesman123` / `pass1234` | `/orders/` | Mobile-optimized order booking, customer catalog, stock availability checks |
| **Factory Admin** | `admin` | `admin123` / `pass1234` | `/admin-dashboard/` | Order approvals, GST invoice generation, dispatch execution, purchase receiving, payments |
| **Production Supervisor** | `production` | `production123` / `pass1234` | `/production/` | Recipe BOM management, raw material issuing, output logging, batch cost analysis |
| **Accountant / Auditor** | `accountant` | `accountant123` / `pass1234` | `/reports/` | **Read-Only:** Monthly Reports Hub, Sales/Purchase Registers, GST summaries, Ageing, Stock Ledgers (CSV/PDF) |
| **Factory Owner** | `owner` | `owner123` / `pass1234` | `/dashboard/` | Executive Pulse: today's order value, stock valuation, variance alert badges, unit costs, outstanding dues |

---

## 3. Features Implemented Against Section 6 Tiers

### Tier 1: Must Haves (Minimum to be Considered) — 100% Completed
* [x] **Role-Based Access Control:** Strict role isolation for `salesman`, `admin`, `production`, `accountant`, and `owner` using custom Django User model and `@role_required` decorators. Accountant is strictly read-only across all transactional forms.
* [x] **Master Data Management:** Complete CRUD and relational integrity for Raw Materials, Packaging Items, Finished Goods Products, Bill of Materials (BOM) with recipe lines, Customers (with GSTIN, State Code, Channel), Suppliers, and Units with conversions.
* [x] **Mobile-Friendly Order Taking & Admin Approval:** Responsive order creation screen for field salespeople; validates credit limits and live warehouse stock; prevents submission of empty orders; Admin approval workflow.
* [x] **GST Tax Invoicing with PDF Download:** Computes taxable values, CGST (2.5%), SGST (2.5%) for intra-state sales (Tamil Nadu: 33) and IGST (5%) for inter-state sales (Karnataka: 29). Generates official Tax Invoice PDF using ReportLab with DejaVuSans font fallback.
* [x] **Recipe-Based Production Run with Auto-Stock Updates:** Multi-step production execution:
  1. *Plan Run:* Computes standard material requirements from BOM and batch multiplier.
  2. *Issue Materials:* Atomically deducts issued raw materials from `StockMovement` ledger.
  3. *Record Output:* Logs good yield packets, damaged pouches, and cartons used; automatically increments finished goods inventory in the ledger.
* [x] **Planned vs. Actual Consumption & Yield with Variance:** Full variance analysis per material (quantity variance, variance %, standard cost vs. actual cost). Flags runs where yield or material variance exceeds tolerance.
* [x] **Append-Only Stock Summary & Stock Ledger:** Balances are never manually edited; always dynamically derived as $\sum (\text{Inward} - \text{Outward} \pm \text{Adjustments})$. Detailed date-filtered stock ledger for every SKU with running balances.
* [x] **Sales Register & Stock Reports:** Date-filtered reports with summary cards, exportable to formatted CSV/Excel and printable PDF.

### Tier 2: Should Haves — 100% Completed
* [x] **Purchases & Supplier Records:** Purchase orders with item lines, supplier tracking, and warehouse receipt logging that updates stock ledger quantities and purchase costs.
* [x] **Customer Payments & Ageing Report:** Payment receipt logging against invoices; customer outstanding balances; 4-bucket ageing breakdown (0–30 days, 31–60 days, 61–90 days, 90+ days) matching Indian credit standards.
* [x] **Batch Costing with Overheads:** Real-time cost allocation adding Raw Materials + Packaging + Direct Labour + Overheads/Power to calculate exact Actual Cost per Packet and Gross Margin %.
* [x] **GST Summary Report:** Outward supplies categorized into B2B (with buyer GSTIN) and B2C, tax breakdowns (Taxable, CGST, SGST, IGST), and HSN-wise summary mapped to official GST portal UQC codes (`PAC` for packets, `KGS`, `LTR`, `BOX`).
* [x] **Configurable Variance Alerts:** Configurable tolerance threshold (default ±3.00%). Alerts distinguish `OVER` (red) vs `UNDER` (amber), with short item names listed in the alert tag (`FLAGGED (Yield, Cooking oil, Carton)`).
* [x] **Executive Owner Dashboard:** Real-time pulse showing today's orders count and value, stock valuation breakdown, variance alerts, product margins, and customer dues.

### Tier 3: Stretch Goals Implemented
* [x] **Reorder Levels & Low Stock Warnings:** Automated minimum threshold checking on raw materials and packaging items, highlighting items needing replenishment.
* [x] **Production Planning & Shortage Detection:** Field orders automatically verify available unallocated stock; flags shortages (e.g., "Shortage of 32 packets against 88 on hand") to guide batch planning.
* [x] **Compound Unit Conversions:** Multi-unit engine supporting conversions such as $1\text{ carton} = 20\text{ packets}$, $1\text{ kg} = 1000\text{ g}$, $1\text{ L} = 1000\text{ ml}$.
* [x] **Audit Trail Logs:** Every production run edit and invoice status change logs timestamp, user, previous/new values, and mandatory edit reason. Posted invoices are cancelled via Credit Notes without deleting original records.
* [x] **Automated Benchmark Seed Command:** Built-in Django command `python manage.py seed_benchmark` reloads the exact Section 5 master data, opening stocks, and transaction state.

---

## 4. Benchmark Scenario Verification (Section 5)

Every step of the Section 5 benchmark scenario is fully implemented and validated via automated end-to-end integration tests (`reports/tests_section5_benchmark_e2e.py`).

### Results Comparison Table

| Check Point | Benchmark Specification | System Result | Status | Notes & Calculation |
| :--- | :--- | :--- | :--- | :--- |
| **Flour Closing Balance** | 120 kg | **120.0000 kg** | Match | Opening $100\text{ kg} + \text{Purchase } 60\text{ kg} - \text{Production Issue } 40\text{ kg} = 120\text{ kg}$ |
| **Oil Closing Balance** | 19.5 L | **19.5000 L** | Match | Opening $30\text{ L} - \text{Issued } 10.5\text{ L} = 19.5\text{ L}$ |
| **Pouches Closing Balance** | 306 pcs | **306.0000 pcs** | Match | Opening $500 - 194\text{ consumed } (188\text{ good} + 6\text{ damaged}) = 306\text{ pcs}$ |
| **FG Stock After Run** | 238 packets | **238.0000 pkts** | Match | Opening $50\text{ pkts} + 188\text{ good pkts produced} = 238\text{ pkts}$ |
| **FG Stock After Retailer A** | 88 packets | **88.0000 pkts** | Match | Warehouse stock $238\text{ pkts} - 150\text{ dispatched} = 88\text{ pkts}$ |
| **Yield Variance** | 188 vs 200, −6%, flagged | **-6.00% [FLAGGED]** | Match | $\frac{188 - 200}{200} \times 100 = -6.00\%$; exceeds $\pm 3.00\%$ tolerance |
| **Oil Consumption Variance** | +5%, flagged | **+5.00% [OVER]** | Match | $\frac{10.5 - 10.0}{10.0} \times 100 = +5.00\%$; flagged `OVER` |
| **Retailer A Invoice** | ₹7,500 + ₹187.50 + ₹187.50 = ₹7,875 | **₹7,875.00** | Match | Intra-state Tamil Nadu: 150 pkts @ ₹50 = ₹7,500.00 taxable; CGST (2.5%) = ₹187.50; SGST (2.5%) = ₹187.50 |
| **Retailer A Outstanding** | ₹3,875 | **₹3,875.00** | Match | Invoice total ₹7,875.00 − Payment received ₹4,000.00 = ₹3,875.00 |
| **Distributor B Order** | Shortage 32 pkts flagged; IGST | **32 pkts Shortage; IGST** | Match | Requested 120 pkts vs 88 on hand $\rightarrow$ 32 pkts shortage warning; Inter-state Karnataka applies 5% IGST (₹300.00) |
| **Cost Per Packet** | Documented with method | **₹31.14 / packet** | Match | Total Cost: ₹5,855.00 / 188 good pkts. Valuation: Weighted Average Cost. Overhead: Batch run direct allocation. *(See breakdown below)* |

---

### Detailed Cost per Packet Explanation

* **Raw Materials (₹3,435.00):**
  * *Flour:* 40 kg consumed @ **₹43.125/kg** (Weighted Average Cost of 100 kg opening @ ₹42 + 60 kg purchase @ ₹45: $\frac{4200 + 2700}{160} = \text{₹}43.125$) = **₹1,725.00**
  * *Cooking Oil:* 10.5 L consumed @ **₹140.00/L** = **₹1,470.00**
  * *Salt & Spice Mix:* 1.2 kg consumed @ **₹200.00/kg** = **₹240.00**
* **Packaging Materials (₹620.00):**
  * *200 g Pouches:* 194 pcs used (188 good + 6 damaged) @ **₹2.50/pc** = **₹485.00**
  * *Cartons:* 9 pcs used @ **₹15.00/pc** = **₹135.00**
* **Direct Overheads (₹1,800.00):**
  * *Direct Labour:* **₹1,200.00**
  * *Power / Gas / Utilities:* **₹600.00**
* **Batch Total Production Cost:** $\text{₹}3,435.00 + \text{₹}620.00 + \text{₹}1,800.00 = \mathbf{\text{₹}5,855.00}$
* **Actual Cost per Packet:** $\frac{\text{₹}5,855.00}{188\text{ good packets}} = \text{₹}31.1436 \approx \mathbf{\text{₹}31.14}$
* **Gross Profit Margin:** At selling price ₹50.00/pkt, margin is $\text{₹}50.00 - \text{₹}31.14 = \mathbf{\text{₹}18.86\text{ / pkt}}$ (**37.71%** margin).

### Additional Benchmark Flag Notes

1. **Carton Usage (-10.00%):** The BOM specifies 10 cartons per batch ($10 \times 20\text{ pkts} = 200\text{ pkts}$). With an actual output of 188 packets, 9 cartons were consumed ($9 \times 20 = 180\text{ pkts}$ packed in full cartons, 8 loose). Actual usage (9) versus planned (10) represents a **-10.00% variance**, which exceeds the $\pm 3.00\%$ tolerance. The system flags this as `UNDER` usage and displays:
   $$\text{FLAGGED (Yield, Cooking oil, Carton)}$$
   This is expected behavior and accurately alerts management to packaging count variances.
2. **Pouch Usage (-3.00%):** Total pouch consumption was 194 pouches (188 good packets + 6 damaged). Compared to the standard BOM plan of 200 pouches, variance is exactly $-3.00\%$, which is within the $\pm 3.00\%$ threshold and is therefore not flagged.

---

## 5. Architectural Assumptions & Known Gaps

### Assumptions
1. **GST Regime & Jurisdiction:** The manufacturing factory is located in Tamil Nadu (State Code `33`). All customers with State Code `33` are invoiced with CGST (2.5%) and SGST (2.5%). Out-of-state buyers (e.g., Karnataka `29`) are invoiced with IGST (5.0%).
2. **UQC Portability:** Under GST regulations, finished snack packets map to Unique Quantity Code `PAC`, kilograms map to `KGS`, litres to `LTR`, and carton boxes to `BOX`.
3. **Damaged Packaging Treatment:** Damaged pouches are absorbed into batch packaging cost as normal production scrap, properly increasing the effective unit cost of finished packets.
4. **Weighted Average Costing (WAC):** Raw material inventory valuation recalculates the moving weighted average unit cost upon every purchase receipt movement.
5. **Non-destructive Invoicing:** Invoices once generated cannot be deleted from the database. Cancellations are executed strictly via an audit Credit Note workflow.

### Known Gaps & Future Roadmap
1. **Live GST Portal Integration:** The system generates GST-compliant invoices and returns internal GSTR-1 summaries; direct JSON API push to the government IRP (Invoice Registration Portal) for IRN / QR code generation is currently simulated.
2. **Hardware Barcode / QR Scanning:** Batch selection is currently done via dropdowns rather than hardware barcode scanners.
3. **Offline Sync Service Worker:** Salesman mobile ordering operates via a responsive web portal requiring active cellular connectivity; offline IndexedDB store-and-forward is identified as a Tier 3 stretch enhancement.
4. **GPS Field Check-ins:** Sales orders log user ID and timestamp; capturing background geolocation coordinates during order submission is planned for a native mobile wrapper.

---

## 6. Verification & Automated Test Suite

The system includes a comprehensive automated test suite covering unit math, ledger operations, role permissions, and full end-to-end benchmark scenarios:

```bash
# Run complete test suite
python manage.py test --verbosity=1
```

### Key Test Modules
* `reports/tests_section5_benchmark_e2e.py`: Complete 9-step Section 5 scenario end-to-end simulation.
* `reports/tests_uqc_and_variance.py`: GST UQC mapping, variance threshold detection, OVER/UNDER badges, and PDF export validation.
* `production/tests.py`: Recipe BOM scaling, material issuance, output stock recording, scrap tracking, and batch costing.
* `invoices/tests.py`: GST calculations, credit-note cancellations, payment logging, and 4-bucket ageing reports.
* `inventory/tests.py`: Append-only `StockMovement` ledger verification, moving weighted average cost computation.
* `orders/tests.py`: Sales order submission, stock shortage warnings, admin approval flow.
