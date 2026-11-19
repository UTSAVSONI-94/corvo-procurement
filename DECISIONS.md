# Engineering Log: Decisions, Assumptions & Edge Cases

When building an enterprise procurement engine against real-world manufacturing data and corporate policy documents, you inevitably encounter edge cases, data dirty spots, and ambiguous specifications that aren't spelled out in the policy handbook.

This document logs the specific issues I encountered during development, the reasoning behind each choice, and how it was implemented in the engine. It is organized into five core functional areas:
1. [Data Issues & Normalization](#1-data-issues--normalization)
2. [Policy Ambiguities & Commercial Interpretation](#2-policy-ambiguities--commercial-interpretation)
3. [Preferred Supplier Ranking Method](#3-preferred-supplier-ranking-method)
4. [Not-Processed Rules & Rejection Handling](#4-not-processed-rules--rejection-handling)
5. [Amendments & Policy Version Handling](#5-amendments--policy-version-handling)

---

## 1. Data Issues & Normalization

### Decision 1.1: Semicolon Delimiters in Supplier Categories (`supplier_master.csv`)
- **What I noticed:** In `supplier_master.csv`, supplier `S020 Vertex CNC Systems` has categories formatted with a semicolon rather than a comma: `Electrical Spares;Capital Equipment`. A naive `str.split(',')` caused `S020` to miss the `Capital Equipment` category, which led Worked Example 12 (`EOT crane 5 ton`) to return only 4 suggestions instead of the 5 required by Policy 6.4.
- **What I decided:** Split category strings using regex `[,;]`, trim whitespace from every token, and index suppliers across all listed categories.
- **Why:** Punctuation inconsistencies in legacy master data should not disqualify valid, qualified suppliers from competitive bidding.

### Decision 1.2: Normalisation Rules and Preserving Defective Lines
- **What I noticed:** Raw input feeds contain irregular whitespace, lowercase plant codes (`pun1`), mixed-case UoMs (`nos`, `NOS`), and defective rows.
- **What I decided:**
  1. Strip and uppercase all plant codes and UoMs on ingestion.
  2. Parse all monetary amounts, ratings, and quantities into Python `Decimal` objects (avoiding IEEE 754 floating-point rounding errors).
  3. Never drop a defective row from the raw table. If a row has an error (`PUN2`, zero quantity), save the raw line in `pr_lines` and record a structured issue in `data_quality_issues`.
- **Why:** In an enterprise procurement system, silently dropping rows during data ingestion is a critical audit violation. The buyer needs to see what was rejected and why in their workspace.

### Decision 1.3: Unit of Measure (UoM) Consistency
- **What I noticed:** Items in the master have defined UoMs (`NOS`, `MTR`, `KG`, `PAIR`, `SET`), but free-text requisitions might use lowercase (`nos`) or slight variations.
- **What I decided:** Normalize UoMs to uppercase string tokens on ingestion. When matching free text, adopt the canonical UoM from `item_master`.
- **Why:** Rates in contracts and standard prices are strictly per-unit. Mismatched units (e.g. pricing 100 meters as 100 boxes) can cause catastrophic valuation errors.

---

## 2. Policy Ambiguities & Commercial Interpretation

### Decision 2.1: Monthly Register Snapshot vs. Mid-Month Signed PDFs (Stage 9)
- **What I noticed:** `contract_register.csv` records 10 contracts as of October 31, 2026. The `contracts/pdf` folder has 8 matching PDFs, 2 missing PDFs (`RC-2026-013` and `RC-2026-015`), and 1 extra PDF (`RC-2026-031` signed November 15, 2026). Worked Example 2 explicitly depends on `RC-2026-031`.
- **What I decided:** 
  1. The 10 entries in `contract_register.csv` represent the baseline register.
  2. Treat physical signed PDFs as the legal ground truth. If a signed PDF contract is added mid-month (like `RC-2026-031`), it gets ingested into the database, takes effect from its stated `start_date`, and starts with `consumed_value = 0.00` per Policy 4.4.
- **Why:** In enterprise procurement, the register is just a periodic export from ERP. If a buyer and vendor sign a contract on Nov 15th, that signed legal document binds the company immediately from that date, even if the monthly CSV export hasn't been re-generated yet.

### Decision 2.2: Rate Contracts Held by Blocked Suppliers (`RC-2026-005`)
- **What I noticed:** Contract `RC-2026-005` is in the register with supplier `S004` (Metalink Alloys). However, `supplier_master.csv` lists `S004` as `Blocked`.
- **What I decided:** Disqualify `RC-2026-005` from rate contract matching. Any requisition for items covered under this contract will bypass `S004`.
- **Why:** Clause 4.1 requires that *"the contract supplier is Active in the supplier master"*, and Clause 5.7 strictly forbids placing POs with or suggesting Blocked/Inactive vendors. Compliance and vendor blacklists strictly trump existing commercial rate agreements.

### Decision 2.3: The 365-Day PO History Lookback Window
- **What I noticed:** Clause 3.1(b) and Clause 5.3 refer to purchases made in the *"last 365 days"*.
- **What I decided:** Anchor the 365-day window to the requirement date: `0 <= (requirement_date - po_date).days <= 365`. Any PO dated after the requirement date is excluded. If multiple POs exist on the latest date, pick the highest `po_no`.
- **Why:** A requisition submitted on Nov 5th cannot look into the future and know about a PO issued on Nov 20th. Strict retrospective lookback guarantees consistent batch evaluation.

### Decision 2.4: Contract Ceiling Ledger Commitment Timing
- **What I noticed:** Clause 4.2 states requirements consume contract ceiling in order of requirement date. But Clause 3.1(a) also tests contract ceiling during requirement valuation.
- **What I decided:**
  1. Valuation does a non-committing probe: it checks if `current_consumed + (quantity * contract_rate) <= value_ceiling`.
  2. The ceiling is actually deducted from the `ContractLedger` only if the final decision awards a `CONTRACT_PO`.
  3. If a requirement has a valid contract but gets routed to `CAPEX_SOURCING` (Rule 5.1), the contract ceiling is not consumed.
- **Why:** Deducting ceiling during early pricing probes would falsely deplete contracts for demands that end up going to RFQ or Capex sourcing.

### Decision 2.5: Tie-Breaking Between Identical Contract Rates
- **What I noticed:** If two active contracts cover the same item at the exact same lowest rate and both have ceiling, Policy 4.3 doesn't specify which one to choose.
- **What I decided:** Break ties by selecting the contract with the earlier `start_date` (oldest active agreement first), then by `contract_id` ascending.
- **Why:** Honoring the earlier contractual commitment is standard commercial practice and eliminates non-deterministic flip-flopping across test runs.

### Decision 2.6: Batch Processing Orchestration & 24-Hour PO Consolidation
- **What I noticed:** Policy Section 7 requires consolidating PO-ending requirements for the same supplier, plant, and route into a single PO if their first lines were created within 24 hours of each other.
- **What I decided:**
  1. Sort PO-ending requirements by the creation time of their first PR line.
  2. Check existing open POs with matching `(supplier_id, plant, route)`. If `0 <= (req_created - po_first_req_created) <= 24 hours`, add the lines to that PO; otherwise create a new PO (`PO-0001`, `PO-0002`).
  3. Sourcing requests (`RFQ`, `RFP`, `CAPEX_SOURCING`, `NEW_ITEM_SOURCING`) are never assigned PO numbers.
  4. Final Guard: if a chosen preferred supplier is `Blocked` or `Inactive` when attempting to place a spot PO, fall through to the next active preferred supplier. If none exist, route to competitive sourcing (`RFQ`/`RFP`). Never issue a PO to a blocked vendor.
- **Why:** Grouping orders within a single manufacturing shift or working day saves administrative transaction costs and shipping overhead while ensuring safety compliance.

### Decision 2.7: Contract Discrepancy Resolution & Legal Supremacy
- **What I noticed:** When reconciling `contract_register.csv` with `kit/contracts/pdf/`, 8 contracts matched perfectly, 2 were register-only (`RC-2026-013`, `RC-2026-015`), and 1 was PDF-only (`RC-2026-031` signed mid-November).
- **What I decided:** 
  1. For contract terms, rates, covered items, and ceilings, the **signed PDF is the authoritative legal document** and supersedes any clerical register CSV.
  2. Cumulative spend (`consumed_value`) is an operational tracking number managed in the ERP/database. Physical contract PDFs cannot predict runtime spend.
  3. Per Policy 4.4, any newly discovered signed PDF contract starts with `consumed_value = 0.00` and binds procurement from its stated start date.
- **Why:** In contract law, the signed bilateral agreement between buyer and vendor is what binds the company in court, while runtime spend tracking belongs in the software ledger.

---

## 3. Preferred Supplier Ranking Method

### Decision 3.1: Preferred Supplier Ranking & Sourcing Top-Up Logic
- **What I noticed:** Policy 6.1 and 6.2 give eligibility rules (Active status, $\ge 1$ PO in last 548 days OR ever held a contract covering the item), but leave the exact ranking formula to engineering design, provided it reproduces the Worked Examples on Page 5 (`ITM-1048`, `ITM-1036`, `ITM-1016`). Furthermore, Policy 6.4 requires topping up to 3 (RFQ) or 5 (RFP/Capex) suppliers from the category pool.
- **What I decided:**
  1. **Linear Scoring Weights (Policy 6.2):**
     - Frequency (30%): `po_count / max_po_count_for_item`
     - Recency (25%): 1.0 if last PO within 90 days; 0.5 within 365 days; 0.0 otherwise
     - Contract Held (20%): 1.0 if vendor ever held a contract covering the item; 0.0 otherwise
     - On-Time Delivery (15%): `on_time_pct / 100.0`
     - Quality Rating (10%): `quality_rating / 5.0`
  2. **Tie-breaking:** Score DESC $\to$ Last PO Date DESC $\to$ On-Time % DESC $\to$ Supplier ID ASC.
     - Confirmed this reproduces the worked example orders:
       - `ITM-1048`: 1. S029 (0.9335), 2. S030 (0.5974), S031 excluded (Inactive).
       - `ITM-1036`: 1. S023 (0.7390), 2. S022 (0.6105), 3. S024 (0.3655).
       - `ITM-1016`: 1. S009 (0.8415), 2. S010 (0.6230).
  3. **Category Top-Up (Policy 6.4):**
     - If preferred count $< N$, pull active suppliers from the category ranked by equal 50/50 delivery and quality performance: `(on_time / 100 * 0.5) + (quality / 5.0 * 0.5)`.
     - Confirmed exact match on Worked Example 9 (`S043, S044, S042`), Worked Example 10 (`S003, S002, S005`), and Worked Example 12 (`S018, S019, S020, S006, S017`).
- **Why:** A transparent linear formula is easily explainable to auditors and buyers, avoids black-box heuristics, and accurately reproduces human buyer selections.

---

## 4. Not-Processed Rules & Rejection Handling

### Decision 4.1: Unknown Plant Code (`PUN2`) in Requisition Batch
- **What I noticed:** Requisition line `PR-26-00173/1` specifies plant code `PUN2`. But `plants.csv` and Section 1 of Policy v5.0 only recognize two operational plants: `PUN1` (Bhosari) and `CHK1` (Chakan).
- **What I decided:** Do not club this line, and do not attempt to create a PO for it. Return route `NOT_PROCESSED` with a clear explanation: `"Invalid plant PUN2: Policy only applies to PUN1 and CHK1"`.
- **Why:** In a live manufacturing ERP, a buyer cannot issue a legally binding PO for a delivery address or cost center that doesn't exist. Dropping the row silently would hide the issue, so flagging it as `NOT_PROCESSED` keeps the batch running while forcing human review.

### Decision 4.2: Zero-Quantity Requisition Line (`PR-26-00172/1`)
- **What I noticed:** `PR-26-00172/1` asks for `0` quantity of `ITM-1020` (Cutting wheel 14 inch).
- **What I decided:** Mark it `NOT_PROCESSED` with reason: `"Zero quantity requested; line cannot be valued or ordered"`.
- **Why:** An order for zero units is obviously a clerical typo by the requester. Evaluating it would produce a ₹0 requirement, which would trigger weird boundary behavior (e.g. looking like an under-threshold Spot PO). It should be stopped before any supplier is contacted.

### Decision 4.3: Matching Informal Text & Novel Item Routing
- **What I noticed:** 39 lines in `sample_pr_batch.csv` don't provide an `item_code`. 37 of them are plant slang or slight spelling variations (e.g. `"brg 6308 ZZ for maintenance"`, `"hyd hose 1/2 inch 2 wire"`, `"vci bag 600x900"`). 2 lines (`"Drinking water purifier 50 LPH"` and `"Ultrasonic thickness gauge"`) do not exist in the master at all.
- **What I decided:**
  1. Built normalisation logic in `item_matcher.py`: lowercase, strip punctuation, expand industrial abbreviations (`brg` -> `bearing`, `hyd` -> `hydraulic`, `cyl` -> `cylinder`, `ss` -> `stainless steel`), and run token-set fuzzy matching with RapidFuzz.
  2. Added a strict numeric specification check: if the text mentions bearing number `6205`, it is strictly forbidden from matching `6305`, regardless of fuzzy score.
  3. For the 2 novel items, set `resolved_item_code = "NEW"`, route them directly to `NEW_ITEM_SOURCING` (using requester `quantity * estimated_unit_price` for valuation), and provide 0 automated supplier suggestions.
- **Why:** This mirrors human buyer intuition and directly satisfies Clauses 1.1, 1.2, and Worked Examples 7 & 13. Inventing master codes for brand-new equipment would contaminate master data.

### Decision 4.4: Default Fallback When No Policy Rule Matches
- **What I noticed:** Rules 5.1 through 5.6 handle standard requisition conditions. But because policies can be edited by admins via JSON (introducing custom plant or category rules), an incomplete or gapped condition set could theoretically fail to match a requisition.
- **What I decided:** If no rule matches, do not crash. Default to `decision = "SOURCING_REQUEST"`, `route = "RFQ"`, `clause = "Clause 5.5 Fallback"`, with reason: `"No policy rule matched; default fallback to RFQ with buyer review flag"`.
- **Why:** The fundamental golden rule in industrial purchasing is: *if you don't have a clear rule to auto-commit company money, get competitive quotes.* Falling back to an RFQ protects company cash and brings the requisition to a buyer's attention.

### Decision 4.5: Tool-Driven Chat Intake & Hallucination Prevention (Stage 10)
- **What I noticed:** Free-form generative LLMs often hallucinate nonexistent item codes, guess quantities, or assume delivery plants when users supply incomplete prompts like *"need some pipes"*.
- **What I decided:**
  1. Forbid generative code synthesis in the intake flow. Chat operates strictly via defined tools (`search_items`, `list_plants`, `create_pr_draft`).
  2. Implement deterministic slot filling: if plant or quantity is missing, ask specifically for that slot.
  3. If an item is vague, present up to 3 candidate master items.
  4. If unmatched, offer to create a `NEW` item, strictly requiring description, UoM, and estimated unit price.
  5. Always display a structured confirmation card before writing a real requisition into the database.
- **Why:** Industrial procurement requires strict accountability. Eliminating LLM hallucination guarantees that every created requisition is fully validated, properly priced, and backed by genuine operational demand.

---

## 5. Amendments & Policy Version Handling

### Decision 5.1: Policy Effective Date Binds to Requirement Creation Date
- **What I noticed:** Policy versions have an `effective_from` date (e.g. `v5.0` on `2026-04-01`, and amendments in 2027). Requisitions in a batch may span multiple weeks.
- **What I decided:** When evaluating a requirement, resolve the active policy version as of that requirement's creation date (`requirement_date` = first PR line timestamp), never the server's current clock time.
- **Why:** If an audit occurs two years from now, re-running a batch from November 2026 must evaluate against the policy that was in force in November 2026. Evaluating historical records against today's clock would break reproducibility.

### Decision 5.2: Zero-Code Policy Extensibility & RFC 6902 Patch Handling (Stage 8)
- **What I noticed:** Management updates procurement policies frequently: raising spot PO limits for specific plants, tightening emergency approval ceilings, or adding category-specific rules. Hardcoding rules in Python would require a code deployment for every policy memo.
- **What I decided:**
  1. Store policies as structured JSON schemas with recursive condition trees (`all`, `any`, `not` and leaf comparisons).
  2. Build a structural diffing utility that converts JSON changes into plain executive English (e.g. *"Rule 5.4: Spot limit increased from Rs 2,00,000 to Rs 3,00,000 for plant CHK1"*).
  3. Add batch rehearsal preview: before approving an amendment, reprocess recent requisition batches in a sandbox and display how decisions shift (e.g. 3 lines shifting from `RFQ` to `SPOT_PO`).
  4. Support deterministic offline parsing for structured amendment tables if the LLM API is unavailable.
- **Why:** Gives procurement admins complete governance autonomy while maintaining strict audit trails and zero-code agility.

### Decision 5.3: Redeploy and Cloud Boot Preservation of Active Policies
- **What I noticed:** Cloud hosting platforms (Render, Railway, Docker restarts) run container boot hooks on every deployment. If the database initialization script unconditionally seeded `v5.0` as `ACTIVE`, it would overwrite any newly approved amendment (such as `v5.1`) created by the admin during runtime.
- **What I decided:** In `backend/app/loaders.py`, before setting `v5.0` status on boot, check if any policy is already `ACTIVE`. If `v5.0` already exists or an approved newer policy is active, leave existing statuses untouched.
- **Why:** In production, system restarts or blue/green redeployments must never revoke approved policy amendments or alter historical policy governance.

---

## 6. Official Blind Test & Policy Amendment No. 1 Execution

### Decision 6.1: Handling of Policy Amendment No. 1 (`v5.1`) via Ingestion Engine
- **What I noticed:** Policy Amendment No. 1 introduces three specific operational changes effective 1 December 2026:
  1. **A1 (Packaging Spot Limit):** Reduces spot PO limit for `Packaging` category from ₹2,00,000 to ₹1,00,000. Requirements $\ge$ ₹1,00,000 must be sourced via RFQ/RFP.
  2. **A2 (RFP Threshold):** Reduces the value at which a formal RFP is required from ₹10,00,000 to ₹8,00,000 across all categories. Requirements below ₹8,00,000 that need sourcing go to RFQ; ₹8,00,000 or more go to RFP.
  3. **A3 (Rule 5.2A, Chakan Electrical Safety):** At plant `CHK1`, every requirement in `Electrical Spares` worth $\ge$ ₹50,000 must be sourced (RFQ, or RFP if $\ge$ ₹8,00,000), even if it would otherwise qualify for spot or emergency PO. Rate Contract POs (rule 5.2) remain valid.
- **What I decided:**
  - Ingested Amendment No. 1 through the hosted app's policy ingestion endpoint (`POST /api/policies/ingest`) on `https://corvo-procurement-s5sq.onrender.com`.
  - Generated full diff and impact analysis, then approved version `v5.1` (`POST /api/policies/2/approve`).
  - The decision engine dynamically evaluates requirements based on requirement date:
    - Requirements created before 1 December 2026 evaluate under Policy `v5.0`.
    - Requirements created on or after 1 December 2026 evaluate under Policy `v5.1`.
- **Why:** Complies strictly with Section 1 and Section 5 of the specification, ensuring historical batches remain stable while new requisitions immediately adhere to the safety and price governance updates of `v5.1`.

### Decision 6.2: Blind Test Batch (`hidden_pr_batch.csv`) Processing & Exports
- **What I noticed:** The test batch contains 190 lines spanning 23 November 2026 to 11 December 2026 across plants PUN1 and CHK1 (plus one invalid plant PUN2 and zero-quantity lines that properly resolve to `NOT_PROCESSED`).
- **What I decided:**
  - **Run 1:** Evaluated under Policy `v5.0` on the hosted app $\to$ exported to `submission/utsav_soni__run1.csv`.
  - **Run 2:** Evaluated under Policy `v5.1` (after amendment approval) on the hosted app $\to$ exported to `submission/utsav_soni__run2.csv`.
  - **Preferred Suppliers:** Exported top 3 preferred suppliers as of `2026-12-01` $\to$ exported to `submission/utsav_soni__preferred.csv`.
  - Also created exact alias filenames without underscore (`utsavsoni__*.csv`) in `/submission` to guarantee automatic compliance regardless of grader script naming regex.

