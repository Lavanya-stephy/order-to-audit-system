# Order-to-Audit System for Small Food Manufacturers

**Centre for Digital Infrastructure, NIT Tiruchirappalli — Internship Technical Project**

An integrated enterprise prototype that connects the entire operational lifecycle of a small-scale food manufacturing factory—from field salesman orders to real-time inventory ledgering, recipe-based production tracking, GST-compliant invoicing, and auditor-ready monthly reporting.

---

## 1. Technology Stack & Justification

We chose **Python and Django** paired with **SQLite** (switchable to **PostgreSQL** via environment variables) and **Docker Compose**:
- **Python & Django:** Django’s transactional ORM (`transaction.atomic`) guarantees data consistency across inventory movements and billing, while its built-in role-based authentication, form validation, and admin tooling eliminate boilerplate and keep the codebase concise, readable, and explainable in an interview setting.
- **SQLite / PostgreSQL:** SQLite provides zero-configuration local development and rapid automated testing, with a database adapter configuration that switches immediately to PostgreSQL in production environments with no code changes.
- **Docker Compose:** Ensures a reproducible, single-command development and evaluation environment matching production expectations.

---

## 2. Core Architectural Principles

1. **Precision Arithmetic:** All monetary amounts, tax computations, and fractional quantities use `Decimal` (never floating-point) to prevent rounding drift.
2. **Ledger-Derived Inventory:** Stock balances are never overwritten directly; inventory levels are strictly derived from an append-only `StockMovement` ledger ($\text{Opening} + \text{Inward} - \text{Outward} \pm \text{Adjustments} = \text{Closing}$).
3. **End-to-End Traceability:** Every stock movement links to a verifiable source document (Purchase Receipt, Production Run, Dispatch Invoice, or Audit Adjustment).
4. **Audit Trail & Integrity:** Invoices are never deleted; cancellations are recorded via credit notes, and sensitive operations record timestamps and user IDs.

---

## 3. Quick Start & Setup

### Prerequisites
- Python 3.11+
- Pip
- Docker & Docker Compose (optional for containerized execution)

### Option A: Local Development (SQLite)

1. **Clone the repository:**
   ```bash
   git clone <repo-url>
   cd NIT-PROJRCT
   ```

2. **Create and activate a virtual environment:**
   ```bash
   # Windows
   python -m venv .venv
   .\.venv\Scripts\activate

   # Linux / macOS
   python3 -m venv .venv
   source .venv/bin/activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Run migrations:**
   ```bash
   python manage.py migrate
   ```

5. **Start development server:**
   ```bash
   python manage.py runserver
   ```
   Open [http://127.0.0.1:8000](http://127.0.0.1:8000) in your browser.

---

### Option B: Docker Compose

To run the application using Docker Compose:

```bash
# Build and start the container
docker compose up --build

# Run in background
docker compose up -d
```

To switch from SQLite to PostgreSQL in Docker:
1. Uncomment the PostgreSQL environment variables and `db` service definition in `docker-compose.yml`.
2. Run `docker compose up --build`.

---

## 4. Scope & Feature Roadmap (Section 6 Tiers)

| Tier | Module / Feature | Status |
| :--- | :--- | :--- |
| **Must Have** | Role-Based Access Control (Salesman, Admin, Production, Auditor, Owner) | Pending |
| **Must Have** | Master Data (Items, BOM, Customers, Suppliers, UOMs) | Pending |
| **Must Have** | Mobile-responsive Field Order Taking & Admin Approval | Pending |
| **Must Have** | GST Tax Invoicing (CGST/SGST/IGST) with PDF Download | Pending |
| **Must Have** | Recipe-based Production Run (Auto-stock updates for RM and FG) | Pending |
| **Must Have** | Planned vs Actual Consumption & Yield with Variance Analysis | Pending |
| **Must Have** | Append-only Stock Summary & Itemized Stock Ledger | Pending |
| **Must Have** | Sales Register and Stock Reports exportable to CSV/Excel | Pending |
| **Should Have** | Purchase Orders & Supplier Records | Pending |
| **Should Have** | Customer Payments, Outstanding Balances & Ageing | Pending |
| **Should Have** | Cost per Packet Calculation with Overheads Allocation | Pending |
| **Should Have** | GST Summary of Outward Supplies (GSTR-1 / GSTR-3B) | Pending |
| **Should Have** | Owner Dashboard | Pending |
| **Stretch** | Batch & Expiry Tracking (FEFO Dispatch) | Planned |
| **Stretch** | Offline Order Capture with Sync | Planned |
| **Stretch** | Tamil Language Interface Toggle | Planned |

---

## 5. Benchmark Scenario Checklist (Section 5)

| Step | Checkpoint | Expected Benchmark Output | Status |
| :--- | :--- | :--- | :--- |
| 1 | Flour Purchase (60 kg @ ₹45/kg) | Flour Closing: **120 kg** | Pending |
| 2-3 | Murukku 200g Production Run (188 pkts output) | Oil Closing: **19.5 L**; Pouches: **306**; FG: **238 pkts** | Pending |
| 2-3 | Variance Analysis | Yield Variance: **-6%**; Oil Variance: **+5%** | Pending |
| 4-5 | Retailer A Order (150 pkts), Invoice & Dispatch | FG Closing: **88 pkts**; Invoice: **₹7,875** (₹7500 + ₹375 GST) | Pending |
| 6 | Distributor B Order (120 pkts) | Shortage of **32 pkts** flagged; Inter-state IGST | Pending |
| 7 | Retailer A Payment (₹4,000) | Outstanding Balance: **₹3,875** | Pending |
| 8 | Overhead Allocation (Labour ₹1200 + Power ₹600) | Cost per Packet computed & documented | Pending |
| 9 | Auditor Reports Export | Monthly reports match all audit totals | Pending |

---

## 6. Assumptions & Known Gaps

- **Place of Supply:** Intra-state transactions within Tamil Nadu apply 2.5% CGST + 2.5% SGST (5% total). Inter-state supplies (e.g., Karnataka) apply 5% IGST.
- **Overhead Allocation Rule:** Production overheads (labour, power) are directly allocated to individual batches proportionally based on run duration or batch count.
- **Stock Valuation:** Raw material valuation uses the weighted average cost method based on purchase ledger entries.

---

## 7. Project Documentation

Detailed system architecture, design decisions, and build plan are documented in:
- [NOTES.md](file:///d:/NIT-PROJRCT/NOTES.md) — Comprehensive technical notes, data model design, and step-by-step build order.
- [PROBLEM.md](file:///d:/NIT-PROJRCT/PROBLEM.md) — Original internship problem statement specification.
