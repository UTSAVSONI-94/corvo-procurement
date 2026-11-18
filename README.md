# Corvo Engineering - Autonomous Policy-Driven Procurement

A full-stack, policy-driven procurement engine that translates purchase requisitions (PRs) into purchase orders (POs) or competitive sourcing requests (RFQs/RFPs) in strict adherence to corporate policy rules, active contracts, supplier transaction histories, and 24-hour purchase order consolidation.

When procurement management uploads a new policy version or describes an amendment, the system updates how it decides **without any code changes**.

---

## Quick Start (One Command Run)

### Option 1: Docker Compose (Recommended)
```bash
docker compose up --build
```
Open **`http://localhost:8000`** in your browser. Both the FastAPI API backend and the React single-page application run together on port 8000.

### Option 2: Local Development Setup

1. **Backend:**
   ```bash
   # Create and activate virtual environment
   python3 -m venv venv
   source venv/bin/activate

   # Install dependencies
   pip install fastapi uvicorn pydantic sqlalchemy rapidfuzz pypdf python-multipart pytest

   # Seed database
   python -m backend.app.seed

   # Run FastAPI backend
   uvicorn backend.app.main:app --port 8000 --reload
   ```

2. **Frontend:**
   ```bash
   cd frontend
   npm install
   npm run dev
   ```
   Open **`http://localhost:5173`** (proxies `/api` to port 8000).

---

## Running the Automated Test Suites

### 1. Backend Regression Tests (Pytest)
Runs 99 unit & integration tests, including all 14 official Worked Examples from `kit/Worked_Examples.pdf` tested against real master data:
```bash
./venv/bin/pytest tests/ -v
```

### 2. Frontend End-to-End Smoke Tests (Playwright)
Runs 3 automated user journey smoke tests (Chat-to-PR, Batch-to-Approve, Policy-to-Activate):
```bash
cd frontend
./node_modules/.bin/playwright test
```

### 3. Rehearsing Policy Amendments
Runs an automated policy amendment script verifying global limit shifts, plant-specific rules, and category-level RFQ overrides without code changes:
```bash
./venv/bin/python backend/scripts/rehearse_amendments.py
```

### 4. Standalone Batch CLI
Process any batch CSV offline directly from terminal:
```bash
python -m backend.app.cli process <input_batch.csv> <output_decisions.csv>
```

---

## Core Features & Architecture

- **Pure Decision Engine (`backend/engine/`):** 100% deterministic Python core with 0 framework imports (no FastAPI, no SQLAlchemy, no LLMs). Evaluates item matching, 14-day creation & 7-day need-by clubbing, contract ceilings, 3-tier valuation, and 5-component preferred supplier ranking.
- **Conversational Chat Intake (`/api/chat`):** Guided requester assistant with quick replies, candidate selection for ambiguous terms, refusal to guess quantities or plants, and confirmation cards before requisition creation.
- **Policy as Data (`/api/policies`):** Versioned JSON policy documents evaluated via a recursive AST condition evaluator (**banned `eval()`**). Generates plain-English structural diffs and batch rehearsal impact previews before activation.
- **Contract Management & PDF Ingestion (`/api/contracts`):** Real-time ceiling utilization tracking (`consumed / ceiling`), multi-strategy PDF Schedule A extraction with confidence scoring, and support for late-signed contracts (e.g. `RC-2026-031` signed mid-month with `consumed_value = 0.00`).
- **Buyer Workspace:** Filterable requirements ledger with "Why" rationale drawer (clause, ceiling progress bar, clubbing details, preferred ranking breakdown), single/bulk approval, and mandatory override justification.
- **Full Audit Trail (`/api/audit-log`):** Chronological log tracking actor, timestamp, action (`APPROVE`, `OVERRIDE`, `INGEST`), entity, and before/after states.

---

## Documentation
- **[APPROACH.md](APPROACH.md):** Complete technical methodology, design trade-offs, and tool rationales.
- **[DECISIONS.md](DECISIONS.md):** Engineering log of all 18 assumptions, edge cases, and policy interpretations.
