# Engineering Approach & System Architecture

## 1. Executive Summary & Core Philosophy
The Corvo Engineering Autonomous Procurement System is a production-grade, policy-driven requisition-to-order engine. It automates the operational triage of Purchase Requisitions (PRs), evaluating incoming industrial demands against corporate policy constraints, active contracts, supplier transaction histories, and operational pricing rules to generate either approved Purchase Orders (POs) or structured Sourcing Requests (RFQs/RFPs).

Our engineering design is built on three foundational principles:
1. **Zero AI In The Critical Decision Path:** All procurement rules, eligibility checks, line clubbing, contract ceiling allocations, and supplier scoring are executed by a pure, deterministic Python engine (`backend/engine/`). Business logic never relies on non-deterministic LLM prompting, probabilistic weights, or unsafe expression evaluation (`eval()`).
2. **Transparent, Reversible Policy Governance:** Policies are declarative versioned JSON structures stored with effective dates. Corporate rule changes—such as raising spot limits, creating plant-specific thresholds, or inserting mandatory RFQ rules—take effect without modifying a single line of application source code.
3. **Enterprise Auditability & Data Hygiene:** No raw requisition is ever silently dropped. Every state transition (policy ingestion, buyer override, contract extraction confirmation, and order creation) is immutably logged with actor identities, timestamps, and before/after states.

---

## 2. System Architecture & Monorepo Structure

The repository is structured as a modular, decoupled monorepo:

```
├── backend/
│   ├── engine/               # Pure Python Decision Engine (Zero external dependencies)
│   │   ├── item_matcher.py       # Catalog matching, normalisation, spec conflict guards
│   │   ├── clubber.py            # Temporal line clubbing (14d creation, 7d need-by tolerance)
│   │   ├── contracts.py          # Sequential contract ledger & ceiling tracking
│   │   ├── valuation.py          # 3-tier valuation hierarchy & emergency bypass
│   │   ├── preferred_suppliers.py# 5-factor scoring model & category top-up ranking
│   │   ├── orchestrator.py       # Deterministic pipeline & 24h PO consolidation
│   │   ├── condition_evaluator.py# Recursive AST condition evaluator (no eval)
│   │   ├── schema.py             # Pydantic v2 schemas for policy documents
│   │   └── types.py              # Pure typed dataclasses for engine I/O
│   ├── app/                  # FastAPI Application Layer
│   │   ├── models.py             # SQLAlchemy 2.0 ORM models
│   │   ├── database.py           # Engine setup & session lifecycle
│   │   ├── loaders.py            # Master CSV loaders with anomaly isolation
│   │   ├── seed.py               # Idempotent DB seeder
│   │   ├── policy_service.py     # Structural diffing, plain-English summary, batch rehearsal
│   │   ├── contract_service.py   # Multi-strategy PDF extraction & reconciliation
│   │   ├── chat_service.py       # Deterministic slot-filling assistant & state manager
│   │   ├── cli.py                # Standalone offline batch processor CLI
│   │   └── main.py               # REST API endpoints & route controllers
│   ├── policies/             # Active and baseline declarative policy JSON documents
│   └── scripts/              # Automated rehearsal and migration utilities
├── frontend/                 # React 18 + Vite + Tailwind CSS Single-Page Application
│   ├── src/
│   │   ├── api.js                # Clean API client talking exclusively to FastAPI backend
│   │   ├── components/           # Universal Header, role switchers, policy badge
│   │   └── views/                # 7 specialized role-based views
│   └── e2e/                  # Playwright End-to-End smoke test suite
├── docs/                     # Data profile, field mappings, and schema specifications
├── tests/                    # 10 comprehensive pytest test suites (99 tests)
├── kit/                      # Original corporate test master CSVs, PDFs, and worked examples
└── corvo_procurement.db      # SQLite database seeded with master data
```

---

## 3. What Was Used (Technologies, Libraries, and Rationale)

Every technology in the stack was selected for reliability, speed, and strict adherence to enterprise software standards:

### Backend & Decision Engine
- **Python 3.14 (Virtual Environment):** Clean runtime utilizing modern type hinting and standard library speed improvements.
- **Pydantic v2:** Used strictly for policy document schema validation, parameter constraints, and API contract enforcement.
- **RapidFuzz:** Utilized in `item_matcher.py` for token-set and partial ratio scoring to match colloquial plant descriptions against canonical item master records, coupled with strict alphanumeric specification extraction (e.g., ensuring bearing `6205` never matches `6305`).
- **FastAPI & Uvicorn:** High-performance asynchronous API framework providing automatic OpenAPI schema generation, structured request validation, and clean dependency injection.
- **SQLAlchemy 2.0:** Declarative database ORM supporting SQLite for local operation and seamless migration to enterprise PostgreSQL.
- **pypdf & pdfplumber:** Multi-strategy PDF text parsing for signed rate contracts and policy amendment documents, paired with regular expressions for deterministic metadata extraction.

### Frontend
- **React 18 + Vite:** Fast, modern SPA framework providing instant HMR and lightweight bundle production.
- **Tailwind CSS:** Utility-first styling delivering clean, accessible, and responsive user interfaces with high visual contrast.
- **Lucide React:** Consistent iconography for procurement entities, state badges, and system actions.
- **Playwright:** End-to-end browser automation framework running against live backend and frontend instances.

---

## 4. Engineering Workflow by Stage

The project was implemented in 12 disciplined stages:

### Stage 1: Data Profiling & Hygiene Analysis
- Extensively profiled 6 CSV datasets (73 items, 48 suppliers, 468 POs, 10 contracts, 186 PR lines, 2 plants).
- Discovered and isolated edge cases: colloquial item descriptions missing item codes, invalid plant `PUN2`, zero-quantity requests, semicolon-delimited multi-category suppliers, and blocked vendors holding contracts.

### Stage 2: Database Schema & Idempotent Ingestion
- Authored SQLAlchemy 2 models with primary keys, indexes, foreign keys, and unique constraints.
- Developed `python -m app.seed` (and `python -m backend.app.seed`) verifying idempotency: runs repeatedly with zero duplicate records and zero data loss.

### Stage 3: Declarative Policy Schema & Safe Condition Evaluator
- Designed a versioned JSON policy schema separating parameters (windows, lookback periods), named thresholds, and an ordered sequence of rules.
- Created a recursive AST evaluator (`condition_evaluator.py`) supporting leaf operators (`eq`, `ne`, `lt`, `lte`, `gt`, `gte`, `in`, `not_in`) and combinators (`all`, `any`, `not`). **Prohibited `eval()`** to eliminate remote code execution vulnerabilities.

### Stage 4: Pure Engine Core (Matching, Clubbing, Contracts, Valuation)
- **`item_matcher.py`:** Standardizes text, expands industrial abbreviations (`brg`, `hyd`, `cyl`, `ss`, `ms`), computes fuzzy token similarity, and enforces a mandatory spec-token check. Novel items drop to `NEW`.
- **`clubber.py`:** Sorts PR lines by `(created_at, pr_no, line_no)` and clubs identical items at the same plant within a 14-day creation window and ±7-day need-by tolerance.
- **`contracts.py`:** Sequential `ContractLedger` providing non-committing probes during valuation and binding commitments when `CONTRACT_PO` is awarded.
- **`valuation.py`:** Implements the 3-tier valuation hierarchy (Contract rate $\to$ Last 365d PO price $\to$ Standard master price) and emergency PO bypass rules.

### Stage 5: Multi-Criteria Preferred Supplier Ranking
- Implemented Section 6 ranking over a 548-day window with policy-weighted parameters:
  - Frequency (0.30), Recency (0.25), Contract Held (0.20), On-Time % (0.15), Quality Rating (0.10).
  - Deterministic tie-breaking on last PO date, on-time percentage, and supplier ID.
  - Sourcing top-up logic expanding supplier pools up to 3 (RFQ) or 5 (RFP/Capex) using balanced 50/50 quality and delivery scores.

### Stage 6: Batch Orchestrator & Purchase Order Consolidation
- Assembled the end-to-end pipeline: Item Match $\to$ Clubbing $\to$ Policy Version Selection $\to$ Fact Generation $\to$ First-Match Rule Execution $\to$ Active Supplier Guard $\to$ 24-Hour PO Consolidation.
- PO-ending requirements for the same supplier, plant, and route within 24 hours of that PO's first requirement share a single consolidated PO number (`PO-0001`, `PO-0002`).

### Stage 7: Regression Verification Across All 14 Worked Examples
- Encoded all 14 official worked examples as automated pytest cases against real master data.
- Ran all 186 sample PR lines: 0 unhandled exceptions, 0 blocked suppliers awarded, and 100% agreement on routes, pricing, and supplier selections.

### Stage 8: Policy Ingestion, Diffing, and Batch Rehearsal
- Built endpoints for natural-language amendment parsing, RFC 6902 JSON patch generation, structural diff generation, and batch rehearsal previews.
- Verified zero-code extensibility via `rehearse_amendments.py`, testing global threshold updates, plant-specific rules, and category-level RFQ overrides.

### Stage 9: Contract Management & PDF Reconciliation
- Reconciled physical PDFs with the CSV register: discovered signed contract `RC-2026-031` (Pneumatic Point S021) signed mid-November 2026.
- Established legal authority rule: signed PDF terms supersede CSV registers; new contracts start with consumed value ₹0.00.
- Implemented PDF upload, text extraction, preview editing, and confirmation APIs.

### Stage 10: Conversational Chat Intake & Offline Batch CLI
- Developed `POST /api/chat` with tool calling and a deterministic rule-based slot filler.
- Refused to guess quantities or plants, showed top-3 candidate chips when ambiguous, and supported `NEW` item intake with mandatory estimated pricing.
- Added `/api/pr/upload` CSV pre-validation and `/api/export/decisions` adhering strictly to required 13-column schemas. Built standalone CLI `python -m backend.app.cli process <in.csv> <out.csv>`.

### Stage 11: Responsive React Frontend & Playwright Smoke Suite
- Developed clean, minimal Tailwind UI with 7 specialized views: Requester Chat, Batches, Buyer Workspace, Preferred Suppliers, Contracts, Policy Management, and Audit Log.
- Enforced **one obvious primary action** per screen.
- Automated 3 end-to-end browser smoke tests in Playwright verifying complete user journeys.

---

## 5. Summary of Key Decisions & Governance

Detailed decision logs, edge-case evaluations, and policy interpretations are documented in **`DECISIONS.md`**. Key highlights:
- **Decision 1 & 2:** Lines with invalid plants (`PUN2`) or zero quantities are marked `NOT_PROCESSED` with clear audit explanations, preserving data integrity without halting the batch.
- **Decision 4:** Blocked suppliers (e.g. `S004`) holding rate contracts are disqualified under Policy 4.1/5.7.
- **Decision 7:** Policy versions bind to the requisition creation date, guaranteeing retroactive reproducibility.
- **Decision 14:** Hard safety guards drop unviable preferred suppliers to the next active candidate or fall through to competitive sourcing, guaranteeing no PO is ever issued to a blocked vendor.
- **Decision 17:** Signed rate contracts represent legal truth; newly ingested contracts take effect from their start date with `consumed_value = 0.00`.
- **Decision 18:** Requisition slot-filling requires explicit user confirmation before generating database PR lines.
