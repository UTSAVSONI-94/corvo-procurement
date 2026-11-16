# Engineering Approach & AI Usage Log (APPROACH.md)

This document tracks the technical architecture, engineering methodologies, and AI tooling utilized during the development of the Corvo Engineering PR-to-PO Web App.

---

## 1. AI Tooling & Usage Log

| Stage | Feature / Task | AI Tool / Model | Description of AI Usage |
|---|---|---|---|
| Stage 0 | Project Architecture Setup | Antigravity (Senior Engineer Agent) | Established monorepo guidelines, pure engine boundaries, and coding standards. |
| Stage 1 | Data Profiling & Anomaly Analysis | Antigravity | Automated deep schema inspection, null profiling, value distribution, and edge-case detection across all kit CSVs and PDFs. |

---

## 2. Architectural Pillars

1. **Separation of Concerns:** Pure Python decision engine (`backend/engine`) isolated from web frameworks, ORMs, and external APIs.
2. **Policy as Configuration:** Zero hardcoded thresholds or business parameters in engine logic; dynamically injected from active policy models.
3. **Resilient Data Ingestion:** Header-mapped CSV loaders and OCR/regex extraction for PDF contract ingestion.
4. **Audit Traceability:** Every decision records policy version, exact clause, underlying reference document (contract/PO), and a human-readable justification.
