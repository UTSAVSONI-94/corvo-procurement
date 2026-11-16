# Technical Decisions & Assumptions (DECISIONS.md)

This document tracks edge cases, policy ambiguities, and data inconsistencies discovered during development, along with the reasoning behind how they are handled.

---

### Decision 1: Handling unknown plant `PUN2` in sample PR batch
- **What I noticed:** Requisition line `PR-26-00173/1` specifies plant code `PUN2`. According to `plants.csv` and Section 1 of Procurement Policy v5.0, Corvo Engineering operates exactly two manufacturing plants: `PUN1` (Bhosari) and `CHK1` (Chakan).
- **What I decided:** Route this line as `NOT_PROCESSED` with reason: `"Invalid plant PUN2: Policy only applies to PUN1 and CHK1"`. Do not club it with any other line or create a PO.
- **Why:** Requisitions cannot be committed against a factory location that does not exist in master data or company operations. Halting the line for manual review prevents invalid commitments while maintaining audit transparency.

---

### Decision 2: Handling zero-quantity PR lines (`PR-26-00172/1`)
- **What I noticed:** `PR-26-00172/1` requests `0` quantity of `ITM-1020` (Cutting wheel 14 inch).
- **What I decided:** Mark this line as `NOT_PROCESSED` with reason: `"Zero quantity requested; line cannot be valued or ordered"`.
- **Why:** Placing a purchase order or sending an RFQ for zero units is a clerical input error. It should not create empty PO lines or trigger supplier outreach.

---

### Decision 3: Contract register vs. PDF contract copies
- **What I noticed:** `contract_register.csv` records 10 contracts, but only 8 PDF copies were provided in `contracts/pdf` (signed PDFs for `RC-2026-013` and `RC-2026-015` are absent from the folder). Meanwhile, Worked Example 2 references contract `RC-2026-031`, which was signed mid-November and exists only as a signed PDF.
- **What I decided:** 
  1. The 10 entries in `contract_register.csv` represent the agreed corporate rate contracts as of October 31, 2026.
  2. The application will support loading from the register as well as dynamically parsing/adding new signed PDF contracts that take effect post-register.
- **Why:** In real procurement systems, the monthly contract register is the system of record, while newly signed contracts coming in mid-month must be ingested and bound from their stated start date.

---

### Decision 4: Rate contract disqualification for blocked suppliers (`RC-2026-005`)
- **What I noticed:** Contract `RC-2026-005` exists in the register with supplier `S004` (Metalink Alloys). However, `supplier_master.csv` lists `S004` as `Blocked`.
- **What I decided:** Disqualify `RC-2026-005` from rate contract matching. Requirements for items under this contract will not be awarded to `S004`.
- **Why:** Clause 4.1 explicitly requires that *"the contract supplier is Active in the supplier master"*, and Clause 5.7 strictly prohibits placing POs with or suggesting Blocked/Inactive suppliers.

---

### Decision 5: Matching informal descriptions to item master
- **What I noticed:** 39 rows in `sample_pr_batch.csv` omit the `item_code`. 37 of them are colloquial plant shorthand or slight variations of existing master items (e.g., `"brg 6308 ZZ for maintenance"`, `"hyd hose 1/2 inch 2 wire"`, `"monitor 24\""`). 2 rows (`"Drinking water purifier 50 LPH"` and `"Ultrasonic thickness gauge"`) are completely new items not found anywhere in `item_master.csv`.
- **What I decided:** 
  1. Map the 37 informal descriptions to their canonical `ITM-xxxx` codes via a resilient normalization and keyword matching layer.
  2. For the 2 novel items, set `resolved_item_code = "NEW"`, route them to `NEW_ITEM_SOURCING` valued at `quantity * estimated_unit_price`, do not club them, and do not provide supplier suggestions.
- **Why:** This directly follows Clause 1.1 and 1.2, matching the exact outcomes demonstrated in Worked Example 7 and Worked Example 13.

---

### Decision 6: Normalisation choices and non-dropping data quality logging
- **What I noticed:** CSV feeds contain small data anomalies: casing differences, blank item codes, an invalid plant code (`PUN2`), a zero-quantity line, and blocked suppliers holding active rate contracts.
- **What I decided:**
  1. Standardize all textual inputs on ingestion: strip whitespace, uppercase plant codes (`PUN1`, `CHK1`) and UoMs (`NOS`, `KG`, `LTR`).
  2. Parse all monetary amounts, ratings, and quantities strictly into `Decimal` (never floating-point numbers) to avoid precision drift.
  3. **No silent drops:** Every row from `sample_pr_batch.csv` is preserved in `pr_lines`. Rows with data defects (e.g. `PUN2`, zero quantity, blank item codes) are logged into a queryable `data_quality_issues` table with structured metadata (`file_source`, `row_identifier`, `issue_type`, `severity`, `raw_data`).
  4. **Resilient foreign key validation:** Ingestion loaders verify foreign key integrity (e.g. `po_history -> suppliers/items`, `contract_lines -> contracts/items`) and record orphan references into `data_quality_issues` rather than failing the transaction or crashing the seed process.
- **Why:** Production procurement systems must never discard requisitions without an audit trail. Storing the raw lines while raising actionable data quality alerts ensures full traceability and allows buyers to inspect flagged items in their workspace.
