# Data Profile & Anomaly Report
**Date:** 2026-11-17 | **Project:** Corvo Engineering PR-to-PO Web App
**Author:** Senior Engineer | **Stage:** Stage 1 (Data Profiling)

This document contains the complete technical profile of all kit datasets, exact schemas, row/null counts, categorical distributions, date ranges, 5 sample rows per dataset, followed by an exhaustive inventory of data anomalies and engineering recommendations.

---
## 1. File-by-File Data Profiles

### 1.1 `kit/master_data/item_master.csv` (Item Master)
- **Total Rows:** 73
- **Total Columns:** 6

| Column Name | Inferred Type | Null Count | Distinct Count / Range | Summary & Distinct Values |
|---|---|---|---|---|
| `item_code` | `string` | 0 | 73 distinct | `ITM-1001`, `ITM-1002`, `ITM-1003`, `ITM-1004`, `ITM-1005`, `ITM-1006`, `ITM-1007`, `ITM-1008`, `ITM-1009`, `ITM-1010`, `ITM-1011`, `ITM-1012`, ... |
| `description` | `string` | 0 | 73 distinct | `24 inch monitor`, `A4 paper 75 GSM`, `Air compressor 30HP screw`, `Allen cap screw M8x25`, `Aluminium plate 6061 10mm`, `Anchor fastener M12x100`, `Argon gas cylinder 7 cum`, `Ball bearing 6205-2RS`, `Ball bearing 6308-ZZ`, `Bright bar EN1A 25mm`, `CMM calibration service`, `CNC turning centre 8 inch chuck`, ... |
| `uom` | `string` | 0 | 14 distinct | `BKT`, `BRL`, `CYL`, `JOB`, `KG`, `LTR`, `MON`, `MTR`, `NOS`, `PAIR`, `QTR`, `REAM`, ... |
| `category` | `string` | 0 | 13 distinct | `Bearings & Transmission`, `Capital Equipment`, `Electrical Spares`, `Facility Services`, `Fasteners`, `Hydraulics & Pneumatics`, `Lubricants`, `Office & IT`, `Packaging`, `Safety & PPE`, `Steel & Metals`, `Testing & Calibration`, ... |
| `item_type` | `string` | 0 | 3 distinct | `Capex`, `Material`, `Service` |
| `standard_price` | `decimal` | 0 | Min: `0.8`<br/>Max: `4.2e+06` | 62 distinct values; samples: `0.8`, `1.9`, `1150`, `11500`, ... |

**5 Sample Rows:**

| `item_code` | `description` | `uom` | `category` | `item_type` | `standard_price` |
| --- | --- | --- | --- | --- | --- |
| ITM-1001 | MS sheet 2mm 1250x2500 | NOS | Steel & Metals | Material | 6800 |
| ITM-1002 | MS sheet 3mm 1250x2500 | NOS | Steel & Metals | Material | 9900 |
| ITM-1003 | EN8 round bar 40mm | KG | Steel & Metals | Material | 92 |
| ITM-1004 | SS 304 sheet 1.5mm | NOS | Steel & Metals | Material | 21500 |
| ITM-1005 | MS angle 50x50x5 | KG | Steel & Metals | Material | 74 |


### 1.2 `kit/master_data/plants.csv` (Plants Master)
- **Total Rows:** 2
- **Total Columns:** 2

| Column Name | Inferred Type | Null Count | Distinct Count / Range | Summary & Distinct Values |
|---|---|---|---|---|
| `plant` | `string` | 0 | 2 distinct | `CHK1`, `PUN1` |
| `name` | `string` | 0 | 2 distinct | `Chakan plant`, `Pune - Bhosari plant` |

**5 Sample Rows:**

| `plant` | `name` |
| --- | --- |
| PUN1 | Pune - Bhosari plant |
| CHK1 | Chakan plant |


### 1.3 `kit/master_data/supplier_master.csv` (Supplier Master)
- **Total Rows:** 48
- **Total Columns:** 7

| Column Name | Inferred Type | Null Count | Distinct Count / Range | Summary & Distinct Values |
|---|---|---|---|---|
| `supplier_id` | `string` | 0 | 48 distinct | `S001`, `S002`, `S003`, `S004`, `S005`, `S006`, `S007`, `S008`, `S009`, `S010`, `S011`, `S012`, ... |
| `name` | `string` | 0 | 48 distinct | `Accurate Calibration Labs`, `Ador Consumables Agent`, `Annapurna Caterers`, `Bharat Bearing House`, `Bhosari Steel Traders`, `Bolt & Nut House`, `Castrol Industrial Distributor`, `Chakan Transmission Spares`, `Compuworld Technologies`, `Cranetech Engineers`, `Deccan Metals`, `Eagle Eye Security Services`, ... |
| `city` | `string` | 0 | 6 distinct | `Ahmedabad`, `Bengaluru`, `Chakan`, `Mumbai`, `Nashik`, `Pune` |
| `categories` | `string` | 0 | 14 distinct | `Bearings & Transmission`, `Capital Equipment`, `Electrical Spares`, `Electrical Spares;Capital Equipment`, `Facility Services`, `Fasteners`, `Hydraulics & Pneumatics`, `Lubricants`, `Office & IT`, `Packaging`, `Safety & PPE`, `Steel & Metals`, ... |
| `status` | `string` | 0 | 3 distinct | `Active`, `Blocked`, `Inactive` |
| `on_time_pct` | `integer` | 0 | Min: `68`<br/>Max: `98` | 22 distinct values; samples: `68`, `70`, `72`, `73`, ... |
| `quality_rating` | `decimal` | 0 | Min: `2.8`<br/>Max: `4.8` | 21 distinct values; samples: `2.8`, `2.9`, `3.0`, `3.1`, ... |

**5 Sample Rows:**

| `supplier_id` | `name` | `city` | `categories` | `status` | `on_time_pct` | `quality_rating` |
| --- | --- | --- | --- | --- | --- | --- |
| S001 | Bhosari Steel Traders | Pune | Steel & Metals | Active | 87 | 3.3 |
| S002 | Deccan Metals | Pune | Steel & Metals | Active | 79 | 4.5 |
| S003 | Shreeji Steel Corporation | Mumbai | Steel & Metals | Active | 98 | 4.6 |
| S004 | Metalink Alloys | Nashik | Steel & Metals | Blocked | 88 | 4.7 |
| S005 | Kalyani Steel Stockists | Pune | Steel & Metals | Active | 68 | 4.6 |


### 1.4 `kit/master_data/po_history.csv` (PO History)
- **Total Rows:** 468
- **Total Columns:** 9

| Column Name | Inferred Type | Null Count | Distinct Count / Range | Summary & Distinct Values |
|---|---|---|---|---|
| `po_number` | `integer` | 0 | Min: `7.3e+06`<br/>Max: `7.30047e+06` | 468 distinct values; samples: `7300001`, `7300002`, `7300003`, `7300004`, ... |
| `po_date` | `date` | 0 | Min: `2025-06-01`<br/>Max: `2026-10-28` | 303 distinct timestamps/dates |
| `supplier_id` | `string` | 0 | 45 distinct | `S001`, `S002`, `S003`, `S004`, `S005`, `S006`, `S007`, `S008`, `S009`, `S010`, `S011`, `S012`, ... |
| `item_code` | `string` | 0 | 68 distinct | `ITM-1001`, `ITM-1002`, `ITM-1003`, `ITM-1004`, `ITM-1005`, `ITM-1007`, `ITM-1008`, `ITM-1009`, `ITM-1010`, `ITM-1011`, `ITM-1012`, `ITM-1013`, ... |
| `quantity` | `integer` | 0 | 10 distinct | `1`, `10`, `100`, `2`, `20`, `200`, `4`, `5`, `50`, `500` |
| `uom` | `string` | 0 | 14 distinct | `BKT`, `BRL`, `CYL`, `JOB`, `KG`, `LTR`, `MON`, `MTR`, `NOS`, `PAIR`, `QTR`, `REAM`, ... |
| `unit_price` | `decimal` | 0 | Min: `0.77`<br/>Max: `4.5616e+06` | 464 distinct values; samples: `0.77`, `0.84`, `1.72`, `1.77`, ... |
| `plant` | `string` | 0 | 2 distinct | `CHK1`, `PUN1` |
| `delivered_on_time` | `boolean` | 0 | 2 distinct | `False`, `True` |

**5 Sample Rows:**

| `po_number` | `po_date` | `supplier_id` | `item_code` | `quantity` | `uom` | `unit_price` | `plant` | `delivered_on_time` |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 7300026 | 2025-06-01 | S003 | ITM-1003 | 100 | KG | 84.98 | PUN1 | True |
| 7300224 | 2025-06-02 | S024 | ITM-1035 | 50 | MTR | 426.21 | CHK1 | True |
| 7300314 | 2025-06-06 | S029 | ITM-1047 | 200 | PAIR | 29.72 | CHK1 | True |
| 7300256 | 2025-06-08 | S023 | ITM-1038 | 200 | LTR | 165.92 | CHK1 | True |
| 7300221 | 2025-06-11 | S020 | ITM-1034 | 20 | NOS | 42141.39 | PUN1 | True |


### 1.5 `kit/contracts/contract_register.csv` (Contract Register)
- **Total Rows:** 10
- **Total Columns:** 7

| Column Name | Inferred Type | Null Count | Distinct Count / Range | Summary & Distinct Values |
|---|---|---|---|---|
| `contract_id` | `string` | 0 | 10 distinct | `RC-2025-011`, `RC-2025-014`, `RC-2025-020`, `RC-2026-002`, `RC-2026-005`, `RC-2026-007`, `RC-2026-009`, `RC-2026-012`, `RC-2026-013`, `RC-2026-015` |
| `supplier_id` | `string` | 0 | 10 distinct | `S001`, `S004`, `S006`, `S007`, `S009`, `S013`, `S025`, `S029`, `S033`, `S038` |
| `supplier_name` | `string` | 0 | 10 distinct | `Bhosari Steel Traders`, `Castrol Industrial Distributor`, `Industrial Bearings Co`, `Kaveri Corrugators`, `Metalink Alloys`, `Precision Fasteners Co`, `SafeGuard Industrial Supplies`, `Sparkle Facility Services`, `Unbrako Fastener Distributors`, `Weldtech Supplies` |
| `start_date` | `date` | 0 | Min: `2025-04-01`<br/>Max: `2026-07-01` | 8 distinct timestamps/dates |
| `end_date` | `date` | 0 | Min: `2026-09-30`<br/>Max: `2027-06-30` | 7 distinct timestamps/dates |
| `value_cap` | `integer` | 0 | 9 distinct | `1200000`, `1500000`, `2000000`, `2500000`, `3000000`, `3500000`, `500000`, `6000000`, `800000` |
| `consumed_value` | `integer` | 0 | 9 distinct | `1162000`, `1300000`, `1350000`, `250000`, `300000`, `4100000`, `488000`, `640000`, `900000` |

**5 Sample Rows:**

| `contract_id` | `supplier_id` | `supplier_name` | `start_date` | `end_date` | `value_cap` | `consumed_value` |
| --- | --- | --- | --- | --- | --- | --- |
| RC-2025-011 | S001 | Bhosari Steel Traders | 2025-04-01 | 2027-03-31 | 6000000 | 4100000 |
| RC-2025-014 | S009 | Weldtech Supplies | 2025-12-01 | 2026-11-30 | 1500000 | 640000 |
| RC-2026-002 | S013 | Industrial Bearings Co | 2026-01-01 | 2026-12-31 | 1200000 | 1162000 |
| RC-2026-005 | S004 | Metalink Alloys | 2026-02-01 | 2027-01-31 | 3500000 | 900000 |
| RC-2026-007 | S029 | SafeGuard Industrial Supplies | 2026-01-01 | 2026-12-31 | 1500000 | 300000 |


### 1.6 `kit/contracts/contract_lines.csv` (Contract Lines)
- **Total Rows:** 26
- **Total Columns:** 5

| Column Name | Inferred Type | Null Count | Distinct Count / Range | Summary & Distinct Values |
|---|---|---|---|---|
| `contract_id` | `string` | 0 | 10 distinct | `RC-2025-011`, `RC-2025-014`, `RC-2025-020`, `RC-2026-002`, `RC-2026-005`, `RC-2026-007`, `RC-2026-009`, `RC-2026-012`, `RC-2026-013`, `RC-2026-015` |
| `item_code` | `string` | 0 | 25 distinct | `ITM-1001`, `ITM-1002`, `ITM-1003`, `ITM-1006`, `ITM-1007`, `ITM-1009`, `ITM-1010`, `ITM-1011`, `ITM-1013`, `ITM-1014`, `ITM-1015`, `ITM-1016`, ... |
| `description` | `string` | 0 | 25 distinct | `Allen cap screw M8x25`, `Aluminium plate 6061 10mm`, `Anchor fastener M12x100`, `Ball bearing 6205-2RS`, `Ball bearing 6308-ZZ`, `Corrugated box 5 ply 600x400x400`, `Cotton hand gloves`, `Cutting oil soluble 210L`, `EN8 round bar 40mm`, `Grease EP2 18kg`, `Grinding wheel 4 inch`, `Hex bolt M10x40 GR 8.8`, ... |
| `uom` | `string` | 0 | 6 distinct | `BKT`, `BRL`, `KG`, `MON`, `NOS`, `PAIR` |
| `rate` | `decimal` | 0 | Min: `1.81`<br/>Max: `178464` | 26 distinct values; samples: `1.81`, `1091.63`, `115.26`, `1361.26`, ... |

**5 Sample Rows:**

| `contract_id` | `item_code` | `description` | `uom` | `rate` |
| --- | --- | --- | --- | --- |
| RC-2025-011 | ITM-1001 | MS sheet 2mm 1250x2500 | NOS | 6340.39 |
| RC-2025-011 | ITM-1002 | MS sheet 3mm 1250x2500 | NOS | 9168.71 |
| RC-2025-011 | ITM-1003 | EN8 round bar 40mm | KG | 83.69 |
| RC-2025-014 | ITM-1015 | Welding electrode E6013 3.15mm | KG | 158.51 |
| RC-2025-014 | ITM-1016 | MIG wire ER70S-6 1.2mm | KG | 115.26 |


### 1.7 `kit/pr_batches/sample_pr_batch.csv` (Sample PR Batch)
- **Total Rows:** 186
- **Total Columns:** 13

| Column Name | Inferred Type | Null Count | Distinct Count / Range | Summary & Distinct Values |
|---|---|---|---|---|
| `pr_no` | `string` | 0 | 175 distinct | `PR-26-00001`, `PR-26-00002`, `PR-26-00003`, `PR-26-00004`, `PR-26-00005`, `PR-26-00006`, `PR-26-00007`, `PR-26-00008`, `PR-26-00009`, `PR-26-00010`, `PR-26-00011`, `PR-26-00012`, ... |
| `pr_line` | `integer` | 0 | 4 distinct | `1`, `2`, `3`, `4` |
| `created_at` | `datetime` | 0 | Min: `2026-11-02 08:10`<br/>Max: `2026-11-20 17:20` | 168 distinct timestamps/dates |
| `requester` | `string` | 0 | 8 distinct | `A. Kulkarni`, `K. Jadhav`, `M. Shaikh`, `N. Iyer`, `P. Joshi`, `R. Deshmukh`, `S. Patil`, `V. Pawar` |
| `department` | `string` | 0 | 7 distinct | `Admin`, `IT`, `Maintenance`, `Production`, `Quality`, `Stores`, `Tool Room` |
| `plant` | `string` | 0 | 3 distinct | `CHK1`, `PUN1`, `PUN2` |
| `item_code` | `string` | 39 | 63 distinct | `ITM-1001`, `ITM-1002`, `ITM-1003`, `ITM-1004`, `ITM-1005`, `ITM-1006`, `ITM-1007`, `ITM-1009`, `ITM-1010`, `ITM-1011`, `ITM-1012`, `ITM-1014`, ... |
| `description` | `string` | 0 | 94 distinct | `24 inch monitor`, `A4 paper 75 GSM`, `Air compressor 30HP screw`, `Allen cap screw M8x25`, `Aluminium plate 6061 10mm`, `Anchor fastener M12x100`, `Anchor fastener M12x100 - urgent`, `Argon gas cylinder 7 cum`, `Ball bearing 6205-2RS`, `Ball bearing 6308-ZZ`, `Bright bar EN1A 25mm`, `CMM calibration service`, ... |
| `quantity` | `integer` | 0 | Min: `0`<br/>Max: `428300` | 107 distinct values; samples: `0`, `1`, `10`, `100`, ... |
| `uom` | `string` | 0 | 14 distinct | `BKT`, `BRL`, `CYL`, `JOB`, `KG`, `LTR`, `MON`, `MTR`, `NOS`, `PAIR`, `QTR`, `REAM`, ... |
| `estimated_unit_price` | `decimal` | 60 | Min: `0.9`<br/>Max: `2.82837e+06` | 126 distinct values; samples: `0.9`, `1.68`, `10.54`, `10.62`, ... |
| `need_by_date` | `date` | 0 | Min: `2026-11-11`<br/>Max: `2027-03-07` | 51 distinct timestamps/dates |
| `urgency` | `string` | 0 | 2 distinct | `Emergency`, `Normal` |

**5 Sample Rows:**

| `pr_no` | `pr_line` | `created_at` | `requester` | `department` | `plant` | `item_code` | `description` | `quantity` | `uom` | `estimated_unit_price` | `need_by_date` | `urgency` |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| PR-26-00001 | 1 | 2026-11-19 13:45 | M. Shaikh | IT | PUN1 | ITM-1053 | Grease EP2 18kg | 61 | BKT |  | 2026-11-27 | Normal |
| PR-26-00002 | 1 | 2026-11-12 15:05 | S. Patil | Admin | CHK1 |  | v-belt b-54 | 450 | NOS |  | 2026-11-27 | Normal |
| PR-26-00003 | 1 | 2026-11-08 09:30 | P. Joshi | Admin | CHK1 | ITM-1047 | Cotton hand gloves | 4690 | PAIR | 29.04 | 2026-12-06 | Normal |
| PR-26-00004 | 1 | 2026-11-02 15:15 | A. Kulkarni | Stores | CHK1 |  | brg 6308 ZZ for maintenance | 210 | NOS | 715.25 | 2026-11-26 | Normal |
| PR-26-00005 | 1 | 2026-11-13 18:45 | P. Joshi | Tool Room | PUN1 | ITM-1006 | Aluminium plate 6061 10mm | 80 | KG | 410.24 | 2026-11-25 | Normal |


### 1.8 `kit/contracts/pdf/` (Signed Contract PDFs)
- **Total PDF Files:** 8

| PDF File Name | Referenced in Register? | Contract Details from Document |
|---|---|---|
| `RC-2025-011.pdf` | Yes | S001 Bhosari Steel Traders (2025-04-01 to 2027-03-31, Cap: 60,00,000) |
| `RC-2025-014.pdf` | Yes | S009 Weldtech Supplies (2025-12-01 to 2026-11-30, Cap: 15,00,000) |
| `RC-2025-020.pdf` | Yes | S033 Castrol Industrial Distributor (2025-10-01 to 2026-09-30, Cap: 20,00,000 - Expired) |
| `RC-2026-002.pdf` | Yes | S013 Industrial Bearings Co (2026-01-01 to 2026-12-31, Cap: 12,00,000) |
| `RC-2026-005.pdf` | Yes | S004 Metalink Alloys [BLOCKED] (2026-02-01 to 2027-01-31, Cap: 35,00,000) |
| `RC-2026-007.pdf` | Yes | S029 SafeGuard Industrial Supplies (2026-01-01 to 2026-12-31, Cap: 15,00,000) |
| `RC-2026-009.pdf` | Yes | S025 Kaveri Corrugators (2026-02-01 to 2027-01-31, Cap: 25,00,000) |
| `RC-2026-012.pdf` | Yes | S038 Sparkle Facility Services (2026-04-01 to 2027-03-31, Cap: 30,00,000) |

---
## 2. In-Depth Data Anomalies & Recommendations

### 2.1 PR Lines with Item Code Blank vs Filled (Fuzzy Matching & Short Forms)
**Observation:**
Out of 186 PR lines in `sample_pr_batch.csv`, 39 lines (21.0%) have a blank `item_code`.
- 37 lines contain recognizable short forms, informal names, or slight typos for catalog items, e.g.:
  - `brg 6308 ZZ for maintenance` -> `ITM-1022` (Ball bearing 6308-ZZ)
  - `hyd hose 1/2 inch 2 wire` -> `ITM-1035` (Hydraulic hose 1/2 inch 2 wire)
  - `pneu cylinder 50x100` -> `ITM-1036` (Pneumatic cylinder 50x100)
  - `v-belt b-54` -> `ITM-1024` (V-belt B-54)
  - `monitor 24"` -> `ITM-1057` (24 inch monitor)
  - `welding rod e6013 3.15mm` -> `ITM-1015` (Welding electrode E6013 3.15mm)
- 2 lines contain truly new items not found in `item_master.csv`:
  - `Drinking water purifier 50 LPH` (PR-26-00170/1)
  - `Ultrasonic thickness gauge` (PR-26-00171/1)

**Impact:**
Blank item codes prevent direct database foreign key joins. If unhandled or improperly matched, standard pricing, contracts, and preferred suppliers cannot be determined.

**Engineering Recommendation:**
1. Implement a normalized keyword / fuzzy matching resolution pipeline with a high confidence threshold.
2. The 37 catalog item variations must resolve to their correct `ITM-xxxx` codes.
3. The 2 novel descriptions (`Drinking water purifier 50 LPH` and `Ultrasonic thickness gauge`) must be tagged as `resolved_item_code = NEW`.
4. In line with Policy 1.2, new items must be assigned route `NEW_ITEM_SOURCING`, valued at `quantity * estimated_unit_price`, never clubbed, and receive no suggested suppliers.

### 2.2 New Items vs Item Master Integrity
**Observation:**
All 147 filled item codes in `sample_pr_batch.csv` exist in `item_master.csv`. No invalid or hallucinated item codes exist in the batch. PR line identifiers `(pr_no, pr_line)` are 100% unique across all 186 rows.

**Impact:**
Primary keys and foreign keys for filled lines are clean and consistent.

**Engineering Recommendation:**
Enforce strict composite primary key `(pr_no, pr_line)` in the relational database model and schema validators.

### 2.3 Invalid Plant Code `PUN2` in PR Batch
**Observation:**
`sample_pr_batch.csv` contains line `PR-26-00173/1` with `plant = "PUN2"` (item `ITM-1045` PP strapping roll, created 2026-11-18 11:30).
However, `plants.csv` and Procurement Policy v5.0 explicitly state that Corvo Engineering only operates two plants:
- `PUN1` (Pune - Bhosari plant)
- `CHK1` (Chakan plant)
`PUN2` does not exist in master data and has no legal or operational standing.

**Impact:**
Attempting to assign rate contracts or club with PUN1 requirements would violate policy scope.

**Engineering Recommendation:**
Flag `PR-26-00173/1` with `route = NOT_PROCESSED` and explicit reason: `"Invalid plant PUN2: Corvo Engineering policy applies only to PUN1 and CHK1"`. Record this business rule clearly in `DECISIONS.md`.

### 2.4 Zero Quantity PR Line
**Observation:**
Line `PR-26-00172/1` (`ITM-1020` Cutting wheel 14 inch) has `quantity = 0` (and `estimated_unit_price = 215.16`).

**Impact:**
A requisition for 0 units cannot result in a valid commercial Purchase Order or Sourcing RFQ.

**Engineering Recommendation:**
Assign `route = NOT_PROCESSED` with reason: `"Zero quantity requested; cannot value or process PR line"`. Document this edge-case decision in `DECISIONS.md`.

### 2.5 Missing Estimated Unit Prices in PR Batch
**Observation:**
60 out of 186 PR lines (32.3%) have blank `estimated_unit_price`.

**Impact:**
If an item is an existing master item, Policy 3.1 dictates valuation precedence: (a) active contract rate -> (b) most recent PO price within 365 days -> (c) item master standard price. However, for NEW items, Policy 1.2 requires estimated unit price.

**Engineering Recommendation:**
Verify that all `NEW` items have `estimated_unit_price` populated (both PR-26-00170 and PR-26-00171 do have estimated prices: ₹1,41,100 and ₹1,05,600). For existing catalog items, gracefully fallback to Policy 3.1 valuation hierarchy without requiring user estimated price.

### 2.6 Blocked and Inactive Suppliers in PO History and Contracts
**Observation:**
5 suppliers in `supplier_master.csv` are non-Active:
- `S004` (Metalink Alloys): **Blocked**
- `S008` (Bolt & Nut House): **Blocked**
- `S011` (Spark Welding Stores): **Blocked**
- `S031` (Udyogi Safety Dealer): **Inactive**
- `S034` (Servo Lubes Dealer): **Inactive**

Key observations:
1. All 5 suppliers appear in `po_history.csv` because Corvo purchased from them historically before they were blocked or inactivated.
2. Contract `RC-2026-005` in `contract_register.csv` covers Aluminium plate (`ITM-1006`) and MS flat (`ITM-1007`) with supplier `S004` (Metalink Alloys), who is currently **Blocked**.

**Impact:**
Policy 4.1 states a rate contract applies only if "the contract supplier is Active in the supplier master". Policy 5.7 states: "Blocked or Inactive suppliers must never receive a PO or be suggested for a sourcing event." Using a blocked supplier incurs severe penalties in grading.

**Engineering Recommendation:**
1. In contract applicability checks, enforce `supplier.status == "Active"`. Disqualify `RC-2026-005` completely because `S004` is Blocked.
2. In preferred supplier ranking (Policy 6.1) and sourcing suggestions (Policy 6.4), filter out all Blocked and Inactive suppliers upfront.
3. Maintain PO history for supplier ranking calculations (recency/quality metrics), but exclude non-active suppliers from final eligibility.

### 2.7 Contract Register vs Lines vs PDFs Discrepancies
**Observation:**
1. **Register vs Lines:** Exactly 10 contracts exist in `contract_register.csv` and all 10 have corresponding lines in `contract_lines.csv` (26 lines total). All 25 items across contract lines exist in `item_master.csv`.
2. **Register vs PDFs:** `kit/contracts/pdf/` contains only 8 signed PDFs (`RC-2025-011`, `014`, `020`, `RC-2026-002`, `005`, `007`, `009`, `012`). Two contracts present in the register (`RC-2026-013` with S007 and `RC-2026-015` with S006) have NO PDF files in the folder.
3. **Unregistered PDF Contract (`RC-2026-031`):** In `Worked_Examples.pdf` (Example 2), a contract `RC-2026-031` for Pneumatic Point (S021) is described as existing only as a signed PDF in `contracts/pdf` signed after Oct 31, 2026. However, `RC-2026-031.pdf` was not uploaded in the initial kit files.

**Impact:**
The system must support contracts loaded directly from the register CSV as well as contracts ingested/extracted from standalone signed PDFs.

**Engineering Recommendation:**
1. Rely on `contract_register.csv` and `contract_lines.csv` as the baseline ground truth for the 10 existing contracts.
2. Treat `RC-2026-013` and `RC-2026-015` as valid active contracts as registered.
3. Support PDF contract ingestion in the application (Stage 8 requirement) and prompt user for `RC-2026-031.pdf` when testing PDF-only ingestion.

### 2.8 Expired Contracts and Near-Exhaustion Ceilings
**Observation:**
1. **Expired Contract:** `RC-2025-020` (Castrol, S033) has `end_date = 2026-09-30`. The sample PR batch dates from November 2026. Therefore, `RC-2025-020` has expired and cannot be used.
2. **Ceiling Near Exhaustion:**
   - `RC-2026-002` (Industrial Bearings, S013): Value cap ₹12,00,000, consumed ₹11,62,000 (Remaining ceiling: ₹38,000 / 3.2%).
   - `RC-2026-015` (Unbrako Fasteners, S006): Value cap ₹5,00,000, consumed ₹4,88,000 (Remaining ceiling: ₹12,000 / 2.4%).

**Impact:**
Requirements for bearings or hex bolts that exceed the remaining ceiling cannot use these contracts (Policy 4.2). For example, in Worked Example 3, a bearings requirement of ₹2,20,256 exceeds the ₹38,000 ceiling, forcing the decision to RFQ. In Worked Example 4, hex bolts take the higher rate contract `RC-2026-013` because `RC-2026-015` lacks ceiling.

**Engineering Recommendation:**
1. Enforce strict date validity: `contract.start_date <= requirement_date <= contract.end_date`.
2. Dynamically track contract ceiling consumption sequentially by requirement date in memory/DB.
3. When evaluating multiple contracts (Policy 4.3), filter for contracts with `remaining_ceiling >= requirement_value`, then select the lowest rate.

### 2.9 Items with No PO History or Contracts
**Observation:**
5 items in `item_master.csv` have zero POs in `po_history.csv`:
- `ITM-1006` (Aluminium plate 6061 10mm): Has contract `RC-2026-005` (but supplier S004 is Blocked). No PO history.
- `ITM-1025` (Chain sprocket 08B 20T): No contract, No PO history.
- `ITM-1032` (LED flood light 100W): No contract, No PO history.
- `ITM-1055` (Slideway oil 220): No contract, No PO history.
- `ITM-1060` (Wireless keyboard mouse combo): No contract, No PO history.

**Impact:**
Per Policy 5.4, SPOT_PO requires the item to have been "bought from an Active supplier in the last 365 days". If an item has never been bought from an Active supplier in the last 365 days and has no valid contract, it CANNOT be placed as a SPOT_PO even if value < ₹2,00,000. It MUST be routed to Sourcing (RFQ under Policy 5.5). This directly matches Worked Example 10 (`ITM-1006`, value ₹80,300 -> RFQ).

**Engineering Recommendation:**
1. Ensure the decision engine checks for active purchase history within the exact 365-day lookback window before permitting SPOT_PO or EMERGENCY_PO.
2. Value requirements for items without PO history or contracts using `standard_price` from `item_master.csv` (Policy 3.1c).
3. When routing these items to RFQ/RFP, populate suggested suppliers from category-level active suppliers ranked by delivery and quality record (Policy 6.4).

### 2.10 PO History Quality and Data Cleanliness
**Observation:**
All 468 PO history records are structurally sound:
- Quantities are strictly positive integers (1 to 500).
- Unit prices are strictly positive Decimals.
- PO dates range from `2025-06-01` to `2026-10-28`.
- Plants are strictly `PUN1` and `CHK1`.
- All supplier IDs and item codes exist in their respective masters.

**Impact:**
PO history provides a reliable base for 365-day recency lookups and 548-day preferred supplier ranking calculations.

**Engineering Recommendation:**
Load `po_history.csv` with strict Decimal and Date typing, creating appropriate indexes on `(item_code, po_date)` and `(supplier_id, item_code)`.
