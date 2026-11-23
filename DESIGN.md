# System Architecture & Design Note

**Order-to-Audit System for Small Food Manufacturers**  
*Centre for Digital Infrastructure, NIT Tiruchirappalli — Internship Technical Project*

---

## 1. Data Model

```mermaid
erDiagram
    USER {
        int id PK
        string username
        string role
    }
    CUSTOMER {
        int id PK
        string name
        string state_code
        string gstin
    }
    UNIT {
        int id PK
        string name
        string symbol
    }
    RAW_MATERIAL {
        int id PK
        string code
        string name
        decimal standard_cost
    }
    PACKAGING_ITEM {
        int id PK
        string code
        string name
        decimal standard_cost
    }
    PRODUCT {
        int id PK
        string code
        string name
        decimal selling_price
    }
    BILL_OF_MATERIAL {
        int id PK
        int product_id FK
        decimal batch_size
        int expected_yield_packets
    }
    BOM_LINE {
        int id PK
        int bom_id FK
        int raw_material_id FK
        int packaging_item_id FK
        decimal quantity
    }
    PRODUCTION_RUN {
        int id PK
        string run_number
        int product_id FK
        decimal batch_multiplier
        int actual_yield
        decimal total_cost
    }
    PRODUCTION_RUN_ITEM {
        int id PK
        int run_id FK
        int raw_material_id FK
        int packaging_item_id FK
        decimal standard_quantity
        decimal actual_quantity
    }
    STOCK_MOVEMENT {
        int id PK
        string movement_type
        int raw_material_id FK
        int packaging_item_id FK
        int product_id FK
        decimal quantity
        string reference_doc
    }
    SALES_ORDER {
        int id PK
        string order_number
        int customer_id FK
        int salesman_id FK
        string status
    }
    SALES_ORDER_LINE {
        int id PK
        int order_id FK
        int product_id FK
        decimal quantity
        decimal unit_price
    }
    INVOICE {
        int id PK
        string invoice_number
        int order_id FK
        int customer_id FK
        decimal taxable_value
        decimal grand_total
        string status
    }
    PAYMENT {
        int id PK
        int invoice_id FK
        int customer_id FK
        decimal amount
        date payment_date
    }

    CUSTOMER ||--o{ SALES_ORDER : "places"
    USER ||--o{ SALES_ORDER : "salesman"
    SALES_ORDER ||--|{ SALES_ORDER_LINE : "contains"
    PRODUCT ||--o{ SALES_ORDER_LINE : "ordered"

    SALES_ORDER ||--o| INVOICE : "billed as"
    CUSTOMER ||--o{ INVOICE : "billed to"
    INVOICE ||--o{ PAYMENT : "settled by"
    CUSTOMER ||--o{ PAYMENT : "paid by"

    PRODUCT ||--o{ BILL_OF_MATERIAL : "standard recipe"
    BILL_OF_MATERIAL ||--|{ BOM_LINE : "specifies"
    RAW_MATERIAL ||--o{ BOM_LINE : "input material"
    PACKAGING_ITEM ||--o{ BOM_LINE : "input packaging"

    PRODUCT ||--o{ PRODUCTION_RUN : "produces"
    BILL_OF_MATERIAL ||--o{ PRODUCTION_RUN : "uses BOM"
    PRODUCTION_RUN ||--|{ PRODUCTION_RUN_ITEM : "tracks usage"
    RAW_MATERIAL ||--o{ PRODUCTION_RUN_ITEM : "consumed"
    PACKAGING_ITEM ||--o{ PRODUCTION_RUN_ITEM : "consumed"

    RAW_MATERIAL ||--o{ STOCK_MOVEMENT : "adjusts"
    PACKAGING_ITEM ||--o{ STOCK_MOVEMENT : "adjusts"
    PRODUCT ||--o{ STOCK_MOVEMENT : "adjusts"
```

Master items (`RAW_MATERIAL`, `PACKAGING_ITEM`, `PRODUCT`) define item attributes and anchor the append-only `STOCK_MOVEMENT` ledger where all physical quantity adjustments are recorded. Finished products link to recipe `BILL_OF_MATERIAL` formulas containing `BOM_LINE` specifications; these recipes are instantiated during manufacturing into `PRODUCTION_RUN` and itemized `PRODUCTION_RUN_ITEM` rows. Field orders booked by salesmen (`USER`) for a `CUSTOMER` create `SALES_ORDER` records with `SALES_ORDER_LINE`s, which on admin approval generate a posted `INVOICE`, deduct inventory upon dispatch, and track collections through linked `PAYMENT` receipts.

---

## 2. Stock and BOM Consumption Computation

* **Append-only stock ledger:** Inventory balances are never stored as mutable counters or directly overwritten; stock on hand is dynamically calculated as the sum of all signed ledger movements:
  $$\text{Stock Balance} = \sum (\text{Opening} + \text{Purchases} + \text{Production Outputs} - \text{Production Issues} - \text{Dispatches} \pm \text{Adjustments})$$
* **Document linkage:** Every `StockMovement` row is strictly linked to an identifiable source document (`reference_doc`), such as a Purchase Receipt, Production Run number, Dispatch Invoice, or physical Audit Adjustment, ensuring complete traceability.
* **Planned BOM consumption:** Standard consumption is derived by scaling recipe lines by the production batch multiplier:
  $$\text{Planned Quantity} = \text{BOM Standard Quantity} \times \text{Batch Multiplier}$$
* **Actual consumption & scrap:** Floor operators record actual quantities issued and scrap (e.g., damaged pouches); raw materials and packaging are deducted from stock upon issue, and good finished packets are credited to inventory when production output is logged.
* **Variance calculation & tolerance flags:** Percentage variance is computed for each material and overall yield:
  $$\text{Variance \%} = \left(\frac{\text{Actual Quantity} - \text{Planned Quantity}}{\text{Planned Quantity}}\right) \times 100$$
  Variances exceeding the configured run tolerance (default $\pm 3.00\%$) trigger directional alerts (`OVER` in red for excess usage, `UNDER` in amber for lower usage) and are summarized in run headers.
* **Unit conversion:** All quantity calculations evaluate through a base-unit conversion engine using explicit decimal ratios (e.g., $1\text{ carton} = 20\text{ packets}$, $1\text{ kg} = 1000\text{ g}$, $1\text{ litre} = 1000\text{ ml}$) to prevent fractional rounding drift across different operational units.

---

## 3. Costing and Valuation

* **Weighted average method:** Raw material and packaging inventories are valued using the perpetual moving Weighted Average Cost (WAC) method, recalculated on every inward receipt:
  $$\text{WAC}_{\text{new}} = \frac{(\text{Current Qty} \times \text{Current Cost}) + (\text{Receipt Qty} \times \text{Purchase Rate})}{\text{Current Qty} + \text{Receipt Qty}}$$
* **Flour example:** An opening balance of $100\text{ kg} @ \text{₹}42.00/\text{kg} = \text{₹}4,200.00$ combined with a new purchase of $60\text{ kg} @ \text{₹}45.00/\text{kg} = \text{₹}2,700.00$ yields a weighted average unit rate of:
  $$\text{WAC} = \frac{\text{₹}4,200.00 + \text{₹}2,700.00}{100\text{ kg} + 60\text{ kg}} = \frac{\text{₹}6,900.00}{160\text{ kg}} = \mathbf{\text{₹}43.125/\text{kg}}$$
  When 40 kg is issued to production, it is costed at ₹43.125/kg, resulting in an exact raw material cost of ₹1,725.00.
* **Overhead allocation rule:** Direct labour (₹1,200.00) and power/gas utilities (₹600.00) recorded for a production run are charged fully and directly to that specific run's product batch rather than being diluted across arbitrary monthly estimates.
* **Cost per packet calculation:** Total batch production cost absorbs raw materials, packaging (including damaged pouches), labour, and utilities, divided strictly by actual good packets produced:
  $$\text{Cost per Packet} = \frac{\text{Total Run Cost (Materials + Packaging + Labour + Power)}}{\text{Actual Good Packets Produced}}$$
  In the benchmark run:
  $$\text{Cost per Packet} = \frac{\text{₹}3,435.00 (\text{RM}) + \text{₹}620.00 (\text{PKG}) + \text{₹}1,800.00 (\text{Overheads})}{188\text{ good packets}} = \frac{\text{₹}5,855.00}{188} = \mathbf{\text{₹}31.14/\text{packet}}$$
* **Reason for choosing weighted average:** In food manufacturing, bulk staples (flour, oil, spices) are fungible and stored in common bins or tanks where separate batch/lot tracking (FIFO/LIFO) is physically impossible on the factory floor. Weighted average naturally blends price fluctuations across procurement cycles and complies with Indian Accounting Standards (Ind AS 2 / AS 2) for inventory valuation and Cost of Goods Sold (COGS).
