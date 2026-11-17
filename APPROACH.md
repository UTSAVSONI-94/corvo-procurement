# Engineering Approach (APPROACH.md)

## Overview & Architecture
This project implements a policy-driven procurement engine that translates purchase requisitions (PRs) into purchase orders (POs) or sourcing requests (RFQs/RFPs). The application is built with a monorepo setup:
- `backend/`: FastAPI backend with SQLAlchemy 2, Alembic migrations, and SQLite/PostgreSQL.
- `backend/engine/`: A pure Python decision engine package. It has no external framework dependencies (no FastAPI, no database session, no LLM SDKs). It accepts plain Python dataclasses and outputs decision dataclasses. This ensures the business logic can be tested deterministically in isolation and guarantees clean separation of concerns.
- `frontend/`: React + Vite + Tailwind application with a chat intake assistant, policy editor, and buyer workspace.
- `docs/`: Technical documentation, data profiling, and evaluation reports.

---

## AI Usage & LLM Integration
Per task guidelines, AI tooling was used for development assistance and is integrated into runtime features:

1. **Development Assistance:**
   - Used for rapid data profiling, regex patterns for shorthand item descriptions, and drafting test scenarios covering the 14 worked examples.
   - Code architecture, decision engine design, data modeling, and business logic decisions were authored by me.
   - Designed SQLAlchemy 2 models and resilient loaders in Stage 2 with data quality isolation.
   - Designed the declarative JSON policy schema, safe AST condition evaluator (no eval), and historical policy repository in Stage 3.

2. **Runtime Chat & Policy Extraction:**
   - **Chat Requisition Intake:** An LLM-backed chat assistant parses conversational user inputs (e.g., *"need 200 nitrile gloves for Chakan next Friday"*), validates missing fields against `item_master` and plant constraints, and prompts for clarification before creating a draft PR.
   - **Policy Amendment Parser:** Reads uploaded policy PDFs or text amendments, extracts modified clauses/thresholds into structured JSON, and shows buyers a plain-English diff before activating the new version.
   - **Pure Engine Boundary:** The core decision engine remains 100% deterministic code. The LLM extracts parameters, but the decision engine applies the rules.
