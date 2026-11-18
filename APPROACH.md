# My Engineering Approach: Building Corvo Procurement

## How I Built This & Architectural Choices

I wanted to build Corvo's procurement engine the way real production-grade industrial software is built: **rock-solid determinism in the financial/decision path, clean architectural seams, and zero black-box magic where real company money is on the line.**

The biggest trap in "AI-powered procurement" is letting an LLM decide who gets a Purchase Order or what price gets paid. If an LLM hallucinates an item rate, or invents a vendor, or misinterprets an emergency threshold, that’s an audit violation or a commercial loss. 

So my core architectural boundary is simple:
- **`backend/engine/` is pure, deterministic Python.** It has 0 framework imports (no FastAPI, no SQLAlchemy, no OpenAI/Gemini SDKs, no network calls). It takes plain Python dataclasses and outputs decision dataclasses. This made it fast, 100% testable in pytest, and guaranteed to produce identical results on every replay.
- **The LLM is kept strictly at the edges:** parsing unstructured user text in the chat assistant (slot-filling quantities, plants, and dates) and extracting proposed clauses from uploaded policy amendment PDFs into structured JSON for buyer review.
- **FastAPI (`backend/app/`)** serves purely as the operational persistence and API orchestration layer.
- **React + Tailwind (`frontend/`)** gives buyers and requesters a clean UI where every screen has one obvious primary action, backed by Playwright end-to-end smoke tests.

---

## What I Used & Why

I chose tools for reliability, standard compliance, and developer ergonomics:

1. **Python 3.14 & Standard Library:**
   - Kept currency handling in Python's `Decimal` module everywhere (valuation, line values, contract ceilings, and unit rates) to prevent floating-point rounding errors.
   - Used standard `dataclasses` for all internal engine objects.

2. **Pydantic v2:**
   - Used solely to validate policy JSON schemas and enforce parameter boundaries (windows, limits, rule orders).

3. **RapidFuzz:**
   - Used for token-set fuzzy matching when requesters provide informal slang (`"brg 6308 ZZ for maintenance"`). But I paired this with a strict alphanumeric spec guard so that bearing `6205` can never match bearing `6305`, regardless of fuzzy score.

4. **SQLAlchemy 2.0 & SQLite:**
   - Built declarative models with strict foreign keys, unique constraints, and indexes. Kept an idempotent `python -m app.seed` command that re-runs cleanly without duplicating data.

5. **pypdf & pdfplumber:**
   - Multi-strategy text extraction for signed PDF rate contracts and policy memos, extracting Schedule A tables and metadata with confidence scoring.

6. **React 18, Vite & Tailwind CSS:**
   - Fast, minimal frontend with custom role switching (`Requester`, `Buyer`, `Procurement Admin`), live active policy badge, expandable requirement drawers, and visual contract ceiling bars.

7. **Playwright:**
   - End-to-end browser automation testing real user flows (Chat to PR, Batch upload to PO approval, Policy amendment ingestion to activation).

---

## How I Tackled the Implementation (Step by Step)

Here is how the system came together chronologically across the project:

### 1. Data Profiling & Finding the Real Quirks (Stage 1)
Before writing code, I inspected all 6 CSV files in `kit/` and wrote `docs/data_profile.md`. 
I discovered several real-world quirks:
- Requisition `PR-26-00173/1` asks for delivery to `PUN2` (which doesn't exist; Corvo only has `PUN1` and `CHK1`).
- Line `PR-26-00172/1` has quantity `0`.
- 39 lines don't have item codes (37 are colloquial names of master items; 2 are brand-new items).
- Supplier `S004` (Metalink Alloys) is marked `Blocked` in the supplier master, yet holds an active contract `RC-2026-005`.
- Supplier `S020` has categories delimited by semicolons (`Electrical Spares;Capital Equipment`) rather than commas.

### 2. Database Schema & Idempotent Ingestion (Stage 2)
I modeled the database in SQLAlchemy 2 with tables for `plants`, `items`, `suppliers`, `po_history`, `contracts`, `contract_lines`, `policy_versions`, `policy_diffs`, `pr_lines`, `requirements`, `decisions`, `purchase_orders`, `po_lines`, `sourcing_requests`, `audit_log`, and `users`.
I built `app.seed` to ingest all kit data cleanly and idempotently.

### 3. Declarative Policy Schema & AST Condition Evaluator (Stage 3)
Management policies change frequently. To avoid code deployments whenever a limit is raised, I designed a versioned JSON policy schema. 
To evaluate condition trees (`all`, `any`, `not` and leaf comparisons like `eq`, `lt`, `in`), I built a recursive AST evaluator (`condition_evaluator.py`). **I explicitly banned `eval()`** to avoid security holes.

### 4. Core Engine Modules (Stage 4)
I built out the pure Python engine:
- **`item_matcher.py`:** Normalizes text, expands industrial acronyms (`brg`, `hyd`, `ss`, `ms`), computes fuzzy token scores, and enforces spec token guards.
- **`clubber.py`:** Groups demands by `(item_code, plant)` within a 14-day creation window and ±7-day need-by window.
- **`contracts.py`:** Tracks contract ceilings dynamically via a sequential `ContractLedger`.
- **`valuation.py`:** Implements the 3-tier valuation hierarchy (Contract rate $\to$ Last 365-day PO price $\to$ Standard price) and emergency bypass logic.

### 5. Multi-Criteria Preferred Supplier Ranking (Stage 5)
For Policy Section 6, I built `preferred_suppliers.py`:
- 548-day lookback window for active vendors with transaction history or contracts.
- Weighted scoring: Frequency (0.30), Recency (0.25), Contract Held (0.20), On-Time % (0.15), Quality Rating (0.10).
- Deterministic tie-breaking on last PO date, on-time delivery, and supplier ID.
- Category top-up logic (topping up to 3 for RFQs or 5 for RFPs) using a balanced 50/50 quality and delivery score.

### 6. Batch Orchestrator & PO Consolidation (Stage 6)
I wired the complete batch pipeline together: match items $\to$ club lines $\to$ select policy version active on the requirement date $\to$ evaluate rules in order $\to$ resolve pricing and suppliers $\to$ enforce the active supplier guard.
Finally, requirements resulting in a PO are consolidated into sequential POs (`PO-0001`, `PO-0002`) if they share the same supplier, plant, and route, and their first lines were created within 24 hours of each other.

### 7. Verifying Against the 14 Worked Examples (Stage 7)
I encoded all 14 official worked examples from `Worked_Examples.pdf` into automated pytest tests (`tests/test_worked_examples.py`). 
Then I processed the entire 186-line sample batch:
- All 14 worked examples match with 100% precision.
- 0 blocked suppliers were awarded orders or suggested.
- Defective rows (`PUN2`, zero quantity) were routed to `NOT_PROCESSED` without crashing the batch.

### 8. Policy Management, Diffing & Rehearsal (Stage 8)
I created API endpoints for policy ingestion and approval:
- Extracts amendment text, runs deterministic or LLM schema validation, and generates plain-language executive diffs (e.g. *"Rule 5.4: Spot limit increased from Rs 2,00,000 to Rs 3,00,000 for plant CHK1"*).
- Generates impact previews by rehearsing how recent PR batches migrate across routes.
- Wrote `rehearse_amendments.py` testing limit adjustments, plant overrides, and category-level RFQ rules without touching engine code.

### 9. Contract Reconciliation & PDF Ingestion (Stage 9)
I reconciled `contract_register.csv` against `kit/contracts/pdf/`:
- Discovered that `RC-2026-031` (Pneumatic Point S021) only existed as a signed PDF entered after the register snapshot date.
- Established the legal authority rule: signed PDFs represent legal truth and supersede register CSVs.
- Created PDF extraction with confidence scoring, and ensured newly ingested contracts start with `consumed_value = 0.00` per Policy 4.4.

### 10. Chat Intake & Batch API (Stage 10)
I implemented `POST /api/chat` with tool definitions (`search_items`, `get_item`, `list_plants`, `create_pr_draft`):
- Refuses to hallucinate or guess quantities or plant locations.
- Presents up to 3 candidate chips when a search is ambiguous (e.g. `'bearing'`).
- Handles `NEW` items with mandatory description, UoM, and estimated price.
- Added session hydration for page refreshes and built the offline CLI processor (`python -m backend.app.cli process <in.csv> <out.csv>`).

### 11. React UI & Playwright Testing (Stage 11)
I built the React + Tailwind frontend:
- Requester Chat with quick-reply chips and a confirmation card.
- Batches view for drag-and-drop CSV uploads.
- Buyer Workspace with filters, expandable PR line sub-tables, "Why" rationale drawer, and bulk approve / override modals.
- Preferred Suppliers explorer with CSV export.
- Policy Management with version timelines, diffing, and raw JSON inspection.
- Contracts register with ceiling progress bars and PDF upload extraction preview.
- Audit Log tracking every state change.
- Wrote 3 Playwright end-to-end smoke tests covering the core user flows.

---

## Technical Assumptions & Edge Cases
All 18 specific edge cases, data quirks, and policy ambiguities encountered during development are documented in detail in **`DECISIONS.md`**.
