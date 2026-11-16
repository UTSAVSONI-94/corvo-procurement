# Architecture & Business Decisions Log (DECISIONS.md)

This log records every decision made where the Corvo Engineering Procurement Policy v5.0 is silent, ambiguous, or where real-world data requires sensible business interpretation.

Format per entry:
- **What I noticed:** The observation, ambiguity, or missing rule.
- **What I decided:** The concrete engineering and business rule implemented.
- **Why:** The justification based on sound procurement and software practices.

---

## Decision 1: Handling Invalid Plant Code `PUN2` in PR Batch
- **What I noticed:** In `sample_pr_batch.csv`, line `PR-26-00173/1` specifies `plant = "PUN2"`. However, Corvo Engineering master data (`plants.csv`) and Procurement Policy v5.0 explicitly state that the company operates only two plants: `PUN1` (Bhosari) and `CHK1` (Chakan).
- **What I decided:** The engine will assign route `NOT_PROCESSED` with `decision = "SOURCING_REQUEST"` (or rejected), setting reason to: `"Invalid plant PUN2: Corvo Engineering policy applies only to PUN1 and CHK1"`. It will not be clubbed with `PUN1` or `CHK1` lines.
- **Why:** Placing orders or sending RFQs for an unknown/unregistered plant violates procurement jurisdiction and ERP master data integrity. The brief explicitly instructs: *"For lines you decide not to process (see DECISIONS.md), use route NOT_PROCESSED and give the reason."*

---

## Decision 2: Handling Zero Quantity PR Line (`PR-26-00172/1`)
- **What I noticed:** Line `PR-26-00172/1` (`ITM-1020` Cutting wheel 14 inch) has `quantity = 0`.
- **What I decided:** Assign route `NOT_PROCESSED` with reason: `"Zero quantity requested; cannot value or process PR line"`.
- **Why:** An order or quote request for 0 quantity is invalid and represents a clerical or intake error. Creating a PO for 0 units would result in a zero-value financial document.

---

## Decision 3: Contract Register Precedence and Missing PDF Copies
- **What I noticed:** `contract_register.csv` and `contract_lines.csv` define 10 rate contracts. However, `kit/contracts/pdf/` only contains 8 PDF files (missing signed PDFs for `RC-2026-013` and `RC-2026-015`). Conversely, Worked Example 2 cites a contract `RC-2026-031` that exists only as a signed PDF valid from 2026-11-15.
- **What I decided:** 
  1. The 10 contracts in `contract_register.csv` and `contract_lines.csv` are considered valid, active corporate rate contracts.
  2. The contracts subsystem will support loading from the register as well as dynamically ingesting standalone PDF contracts (such as `RC-2026-031.pdf`) into the database.
- **Why:** In enterprise ERPs, the contract register is the system of record as of the register date (31 Oct 2026), while post-update contracts signed in November must be ingested as supplemental contracts.

---

## Decision 4: Contract Disqualification for Blocked Suppliers (`RC-2026-005` / `S004`)
- **What I noticed:** Supplier `S004` (Metalink Alloys) is marked `Blocked` in `supplier_master.csv`. However, `RC-2026-005` in `contract_register.csv` covers items `ITM-1006` and `ITM-1007` with `S004`.
- **What I decided:** Contract `RC-2026-005` is disqualified from rate contract application under Policy 4.1. Requirements for `ITM-1006` will not receive a contract PO from `S004`.
- **Why:** Policy clause 4.1 specifically stipulates: *"A rate contract applies to a requirement if... the contract supplier is Active in the supplier master"*. Furthermore, clause 5.7 mandates: *"Blocked or Inactive suppliers must never receive a PO or be suggested for a sourcing event."*

---

## Decision 5: Item Resolution for Free-Text Descriptions
- **What I noticed:** 39 PR lines in the sample batch have blank `item_code`. 37 of them represent slight misspellings, short forms, or colloquial descriptions of items existing in `item_master.csv` (e.g. `"brg 6308 ZZ for maintenance"` for `ITM-1022`). 2 lines (`Drinking water purifier 50 LPH` and `Ultrasonic thickness gauge`) do not match any item in the catalog.
- **What I decided:** 
  1. Implement a rule-based and fuzzy item matcher mapping known variations to canonical `ITM-xxxx` codes.
  2. For descriptions that cannot be matched to the catalog with high confidence, set `resolved_item_code = "NEW"`, route as `NEW_ITEM_SOURCING`, do not club, do not suggest suppliers, and value at `quantity * estimated_unit_price`.
- **Why:** This strictly adheres to Policy Clause 1.1 and 1.2, matching Worked Example 7 (free-text item matching) and Worked Example 13 (new item sourcing).
