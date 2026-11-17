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

---

### Decision 7: Policy effective date binding to requirement creation date
- **What I noticed:** Procurement policy versions carry an `effective_from` date (e.g. `v5.0` effective `2026-04-01`, and future amendments). When processing batches containing requisitions spread across days or weeks, a policy amendment might become active mid-batch.
- **What I decided:**
  1. The policy version bound to any requirement is dictated strictly by the requirement's creation date (`requirement_date` = creation date of its earliest line per Clause 2.3), never by the current wall-clock date.
  2. `PolicyRepository.get_active_policy(as_of_date)` queries for the active version where `effective_from <= requirement_date`, ordered by `effective_from DESC, id DESC`.
  3. Requisitions created prior to an amendment's effective date are processed under the older active policy version, while those created on or after the effective date adopt the amendment.
- **Why:** In enterprise governance, requisitions are judged against the policy rules in force when the demand was officially committed. This guarantees historical audit integrity, prevents retroactive rule distortions, and ensures consistent decision reproducibility across test runs.

---

### Decision 8: Default fallback route when no policy rule matches
- **What I noticed:** Clause 5.1 through 5.6 partition normal requirement paths. However, because future policies can be modified via JSON amendments (altering category rules or adding complex plant filters), a poorly configured or gapped condition tree could conceivably fail to match a requirement.
- **What I decided:**
  1. If no rule in the active policy's `decision_rules` list matches, the engine will NOT crash or leave the requirement unassigned.
  2. It automatically falls back to `decision = "SOURCING_REQUEST"`, `route = "RFQ"`, `clause = "Clause 5.5 Fallback"`, setting reason: `"No policy rule matched; default fallback to RFQ with buyer review flag"`.
  3. A record is logged in `data_quality_issues` under `issue_type = "UNMATCHED_POLICY_RULE"` with severity `WARNING`.
- **Why:** The safest procurement principle is: when in doubt, get quotes. Defaulting to competitive sourcing prevents unauthorized sole-source PO commitments, avoids system failure, and prompts human buyer intervention in the workspace.

---

### Decision 9: Defining the 365-day PO history window and boundary operators
- **What I noticed:** Clause 3.1(b) specifies *"the price on the most recent PO for the item in the 365 days before the requirement date"*, and Clauses 5.3/5.4 require that the item was *"bought from an Active supplier in the last 365 days"*.
- **What I decided:**
  1. The 365-day lookback window is anchored to the requirement's first line creation date (`requirement_date`), NOT the batch execution date.
  2. The valid PO date filter is `0 <= (requirement_date - po_date).days <= 365` (i.e. `po_date <= requirement_date`). Any purchase order dated after the requirement date is strictly ignored.
  3. If multiple historical POs exist on the latest date, tie-breaking selects the highest `po_number`.
- **Why:** Requisitions must be judged strictly against knowledge available as of their creation time. Anchoring to `requirement_date` ensures strict historical reproducibility regardless of when batch processing is triggered.

---

### Decision 10: Contract ceiling ledger commitment timing
- **What I noticed:** Clause 4.2 dictates that *"Requirements consume ceiling in order of requirement date"*. In Clause 3.1(a), candidate contracts are evaluated for remaining ceiling to determine requirement valuation.
- **What I decided:**
  1. Testing ceiling during the valuation phase is a **non-committing probe**: it tests if `current_consumed + (quantity * contract_rate) <= value_ceiling`.
  2. The contract's consumed value in the `ContractLedger` is **committed only when `route == "CONTRACT_PO"` is finalized**.
  3. If a requirement bypasses a contract (e.g. Capex equipment under Rule 5.1 routed to `CAPEX_SOURCING`) or fails to use it, the contract ceiling is not depleted.
- **Why:** Depleting contract ceilings for requirements that never result in a contract purchase order would falsely exhaust corporate credit limits and artificially force subsequent valid PRs into unnecessary sourcing RFQs.

---

### Decision 11: Unit of Measure (UoM) normalization and integrity
- **What I noticed:** Requisitions could potentially introduce conflicting or lowercase UoMs (e.g. `nos`, `Nos`, `NOS`).
- **What I decided:**
  1. Ingestion strips whitespace and normalizes all UoMs to uppercase canonical strings (`NOS`, `KG`, `LTR`, `SET`, `PAIR`, etc.).
  2. Clubbing and valuation use the canonical item master UoM. If a PR line specifies an inconsistent unit that cannot be converted, it is logged to `data_quality_issues`.
- **Why:** Contract rates and standard prices are fixed per unit. Ensuring uniform UoMs prevents severe magnitude errors in total requirement valuation.

---

### Decision 12: Tie-breaking among rate contracts with identical rates
- **What I noticed:** Clause 4.3 specifies choosing the contract with the lowest rate that has ceiling, but is silent on how to break ties if multiple contracts have identical rates.
- **What I decided:** In the case of identical lowest rates, select the contract with the earlier `start_date` (oldest active contract first), followed by `contract_id` ascending.
- **Why:** Prioritizing older active commitments respects corporate vendor tenure and guarantees deterministic resolution.

---

### Decision 13: Preferred Supplier Ranking Formula and Sourcing Top-up Logic
- **What I noticed:** Policy 6.1 and 6.2 require ranking active suppliers with transaction history or contracts over the last 548 days, but leave the specific ranking algorithm to engineering design provided it reproduces the Worked Examples (Page 5: `ITM-1048`, `ITM-1036`, `ITM-1016`). Furthermore, Policy 6.4 requires topping up to 3 (RFQ) or 5 (RFP/Capex) suppliers from the category if the preferred list is short.
- **What I decided:**
  1. **Eligibility Criteria (Policy 6.1):**
     - Supplier status must be `Active` (case-insensitive). `Blocked` and `Inactive` are unconditionally disqualified.
     - Must have $\ge 1$ purchase order in the 548 days prior to the as-of requirement date $D$, OR have held a contract covering the item starting on or before date $D$ (even if currently expired).
  2. **Multi-Criteria Scoring Formula (Policy 6.2):**
     - **Frequency (30% weight):** $\frac{\text{PO Count in Window}}{\max(\text{PO Count for Item in Window})}$.
     - **Recency (25% weight):** $1.0$ if the most recent PO was within 90 days; $0.5$ if within 365 days; $0.0$ otherwise.
     - **Contract Held (20% weight):** $1.0$ if the supplier ever held a contract covering the item starting on or before $D$; $0.0$ otherwise.
     - **On-Time Delivery (15% weight):** $\frac{\text{on\_time\_pct}}{100.0}$.
     - **Quality Rating (10% weight):** $\frac{\text{quality\_rating}}{5.0}$.
     - Weights are configurable via policy parameters (`frequency`, `recency`, `contract_held`, `on_time`, `quality`).
  3. **Deterministic Tie-Breaking:**
     - Total score descending $\to$ Last PO date descending $\to$ On-time delivery pct descending $\to$ `supplier_id` ascending.
  4. **Validation against Worked Examples (2026-11-01):**
     - `ITM-1048`: 1. S029 (0.9335), 2. S030 (0.5974). S031 excluded (Inactive).
     - `ITM-1036`: 1. S023 (0.7390), 2. S022 (0.6105), 3. S024 (0.3655).
     - `ITM-1016`: 1. S009 (0.8415), 2. S010 (0.6230).
  5. **Sourcing Top-Up Logic (Policy 6.4):**
     - Begins with preferred suppliers in rank order.
     - If fewer than $N$ (e.g. 3 for RFQ, 5 for RFP): tops up with active suppliers listed under the item's category, ranked by quality and delivery performance score: $(\frac{\text{quality}}{5.0} \times 0.60) + (\frac{\text{on\_time}}{100} \times 0.40)$ descending.
     - This produces the exact worked example outcomes:
       - `ITM-1066` (Worked Example 9): S043 (preferred #1), S044 (preferred #2), S042 (category top-up) $\to$ `['S043', 'S044', 'S042']`.
       - `ITM-1006` (Worked Example 10): 0 preferred suppliers $\to$ top 3 active Steel & Metals suppliers `['S003', 'S002', 'S005']` (excluding blocked S004).
     - New items get zero automatic suggestions.
  6. **Explainability & Breakdown:**
     - The engine outputs a granular `ScoreBreakdown` per supplier with `{component, raw_value, weight, points}` to power the UI's "Why ranked here" explanation.
- **Why:** Transparent linear scoring ensures fairness, auditability, and 100% adherence to procurement compliance standards while accurately reproducing historical buyer choices.

---

### Decision 14: Batch Processing Orchestration, Non-Processable Line Handling, and PO Consolidation
- **What I noticed:**
  1. The procurement feed contains lines with data anomalies (e.g. invalid plant `PUN2` in `PR-26-00173/1`, zero quantity in `PR-26-00172/1`, or potential duplicate PR line occurrences).
  2. The task brief requires returning exactly one output row per input PR line while marking unprocessable rows with route `NOT_PROCESSED` without crashing the pipeline.
  3. Policy Section 7 specifies PO consolidation across PO-ending requirements (same supplier, same plant, same route, within 24 hours of that PO's first requirement) while strictly isolating sourcing requests.
  4. Sourcing and PO awarding must enforce a hard guard ensuring Blocked or Inactive suppliers never receive a PO.
- **What I decided:**
  1. **Line-Level Rejection Rules (`route = "NOT_PROCESSED"`):**
     - **Duplicate PR Lines:** Evaluated on `(pr_no, pr_line)`. The first occurrence proceeds through processing; subsequent duplicates are marked `NOT_PROCESSED` with reason: `"Duplicate PR line: {pr_no}/{pr_line} already processed in this batch."`
     - **Invalid Manufacturing Plant:** Lines with plant codes other than `PUN1` and `CHK1` are rejected with reason: `"Invalid plant {plant}: Policy only applies to PUN1 and CHK1."`
     - **Non-positive Quantity:** Lines with quantity $\le 0$ are rejected with reason: `"Line rejected: quantity <= 0 (qty={qty}). Quantity must be greater than zero."`
  2. **Sequential Contract Ledger Tracking:**
     - The batch processor instantiates a `ContractLedger` initialized with the starting consumed values.
     - When a requirement qualifies for `CONTRACT_PO`, its total requirement value is immediately committed to the ledger so subsequent requirements in the batch see the reduced remaining ceiling in chronological order.
  3. **Strict 24-Hour Purchase Order Consolidation (Policy 7):**
     - Requirements concluding with a `PO` decision are sorted by the creation timestamp of their first PR line.
     - The engine checks for an open PO matching `(supplier_id, plant, route)`. If $0 \le (\text{req\_created\_at} - \text{po\_first\_req\_created\_at}) \le 24\text{ hours}$, the requirement joins that existing PO; otherwise a new sequential PO (`PO-0001`, `PO-0002`, ...) is opened. Sourcing requests are never assigned PO IDs.
  4. **Final Supplier Status Guard:**
     - If the 1st preferred supplier for a spot or emergency PO is not `Active`, the engine drops to the next active preferred supplier. If no active preferred suppliers exist, it falls through to a sourcing request (`RFQ` or `RFP`).
  5. **Determinism:**
     - All sorting, item matching, clubbing, contract selection, and consolidation routines are 100% deterministic, guaranteeing identical outputs on replay runs.
- **Why:** Enforces zero silent data loss, upholds strict audit compliance, ensures vendor safety, and mirrors real-world corporate enterprise ERP ingestion standards.
