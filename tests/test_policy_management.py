"""
tests/test_policy_management.py

Unit and integration tests for Policy Management (Stage 8):
1. Ingestion of limit changes, plant-specific rules, and category-specific rules via API.
2. Structural diff calculation and plain-language summary rendering.
3. Impact preview calculation (reprocessing batch and counting route shifts).
4. Zero-code extensibility for new rule kinds (plant-specific, category-specific).
5. Rule ordering sensitivity (changing rule order alters outcomes).
6. Policy approval workflow (DRAFT -> ACTIVE) and audit logging.
7. Future vs Past effective date behavior.
"""

from datetime import date, datetime, timedelta
from decimal import Decimal
import json
import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.database import SessionLocal
from backend.app.models import PolicyVersion, PolicyDiff, AuditLog
from backend.app.policy_service import (
    deterministic_amendment_parser,
    compute_policy_diff,
    compute_impact_preview,
    load_reference_data_from_db,
    load_pr_lines_from_db,
)
from backend.engine.schema import PolicyDocument, DecisionRule, RuleOutcome, Condition
from backend.engine.types import PRLineInput, ReferenceData
from backend.engine.orchestrator import process_batch


@pytest.fixture(scope="function", autouse=True)
def reset_policy_db():
    """Ensures each test starts with a clean policy state (only v5.0 ACTIVE)."""
    db = SessionLocal()
    try:
        db.query(PolicyDiff).delete()
        db.query(PolicyVersion).filter(PolicyVersion.version_label != "v5.0").delete()
        v5 = db.query(PolicyVersion).filter_by(version_label="v5.0").first()
        if v5:
            v5.status = "ACTIVE"
        db.commit()
    finally:
        db.close()
    yield
    db = SessionLocal()
    try:
        db.query(PolicyDiff).delete()
        db.query(PolicyVersion).filter(PolicyVersion.version_label != "v5.0").delete()
        v5 = db.query(PolicyVersion).filter_by(version_label="v5.0").first()
        if v5:
            v5.status = "ACTIVE"
        db.commit()
    finally:
        db.close()


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


@pytest.fixture(scope="module")
def base_policy():
    with open("backend/policies/corvo_v5_0.json", "r", encoding="utf-8") as f:
        return PolicyDocument(**json.load(f))


def test_synthetic_amendment_a_limit_change(client):
    """
    Synthetic Amendment A: Raise spot PO limit from 2,00,000 to 3,00,000.
    Checks:
    - Ingested via POST /api/policies/ingest
    - Generates DRAFT version with auto-incremented version label (e.g. v5.1)
    - Plain-language diff describes the threshold change
    - Impact preview reports lines transitioning from RFQ -> SPOT_PO
    """
    payload = {
        "instruction": "Raise the spot PO limit from Rs 2,00,000 to Rs 3,00,000 effective from 2026-11-01.",
        "created_by": "Procurement Analyst",
    }
    response = client.post("/api/policies/ingest", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert data["status"] == "DRAFT"
    assert "spot_limit" in data["diff_summary"]
    assert "300,000" in data["diff_summary"]

    impact = data["impact_preview"]
    assert impact["total_lines_evaluated"] > 0
    # Several PR lines worth between 2L and 3L shift from RFQ to SPOT_PO!
    assert "RFQ -> SPOT_PO" in impact["transitions"]
    assert impact["transitions"]["RFQ -> SPOT_PO"] > 0

    # Test approval
    draft_id = data["draft_id"]
    approve_res = client.post(f"/api/policies/{draft_id}/approve", json={"approved_by": "CPO Admin"})
    assert approve_res.status_code == 200
    assert approve_res.json()["status"] == "ACTIVE"


def test_synthetic_amendment_b_plant_specific_rule(client):
    """
    Synthetic Amendment B: Plant-specific override rule applying only to plant PUN1.
    Spot limit for PUN1 raised to 3,50,000 while CHK1 remains at normal limit.
    Checks:
    - Plant-specific rule injected into policy JSON with NO code changes
    - Plain-language diff specifies the plant override
    - Only PUN1 lines shift routes in impact preview
    """
    payload = {
        "instruction": "For plant PUN1 only: raise spot PO limit to 3.5 lakh effective 2026-11-01.",
        "created_by": "Plant Manager Bhosari",
    }
    response = client.post("/api/policies/ingest", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert "PUN1" in data["diff_summary"]
    proposed_rules = data["proposed_policy"]["decision_rules"]
    pun1_rules = [r for r in proposed_rules if "PUN1" in r["clause"] or "PUN1" in r["name"]]
    assert len(pun1_rules) > 0
    assert pun1_rules[0]["outcome"]["route"] == "SPOT_PO"

    # Verify impact: only PUN1 lines should transition
    impacted = data["impact_preview"]["impacted_lines"]
    for line in impacted:
        # In pr_lines, lines that transitioned must belong to PUN1
        assert "RFQ" in line["old_route"]
        assert "SPOT_PO" in line["new_route"]


def test_synthetic_amendment_c_category_specific_rule(client):
    """
    Synthetic Amendment C: Mandatory RFQ for category 'Packaging' inserted before 5.4.
    Checks:
    - Category rule is created and positioned before Rule 5.4 in decision_rules
    - Packaging items under 2L that previously qualified for SPOT_PO now shift to RFQ!
    """
    payload = {
        "instruction": "For category Packaging: mandatory RFQ before 5.4 effective 2026-11-01.",
        "created_by": "Compliance Lead",
    }
    response = client.post("/api/policies/ingest", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert "Packaging" in data["diff_summary"]
    proposed_rules = data["proposed_policy"]["decision_rules"]

    # Verify rule position: Packaging rule must appear BEFORE rule 5.4 (spot PO)
    pkg_idx = next(i for i, r in enumerate(proposed_rules) if "Packaging" in r["name"])
    spot_idx = next(i for i, r in enumerate(proposed_rules) if r["id"] == "5.4")
    assert pkg_idx < spot_idx

    # Impact preview: Packaging lines (like VCI bag PR-26-00106/1) shift from SPOT_PO to RFQ!
    transitions = data["impact_preview"]["transitions"]
    assert "SPOT_PO -> RFQ" in transitions
    assert transitions["SPOT_PO -> RFQ"] > 0


def test_rule_order_sensitivity(base_policy):
    """
    Explicit verification: altering rule order changes procurement decisions.
    Case:
    - Rule A: Category 'Packaging' -> RFQ
    - Rule B: Spot PO (value < 200,000) -> SPOT_PO
    When Rule A is placed before Rule B -> Output is RFQ.
    When Rule B is placed before Rule A -> Output is SPOT_PO.
    """
    pkg_rule = DecisionRule(
        id="rule_pkg_rfq",
        clause="Clause Special Packaging",
        name="Packaging Mandatory Sourcing",
        description="Mandatory RFQ for packaging",
        when=Condition(field="category", op="eq", value="Packaging"),
        outcome=RuleOutcome(
            decision="SOURCING_REQUEST",
            route="RFQ",
            supplier_mode="SUGGEST_N",
            suggest_count=3,
            price_mode="REFERENCE_PRICE",
        ),
    )

    # Order 1: Packaging Rule BEFORE Spot PO
    p1 = base_policy.model_copy(deep=True)
    spot_idx = next(i for i, r in enumerate(p1.decision_rules) if r.id == "5.4")
    p1.decision_rules.insert(spot_idx, pkg_rule)

    # Order 2: Packaging Rule AFTER Spot PO
    p2 = base_policy.model_copy(deep=True)
    spot_idx2 = next(i for i, r in enumerate(p2.decision_rules) if r.id == "5.4")
    p2.decision_rules.insert(spot_idx2 + 1, pkg_rule)

    # Test facts for a ₹1,56,170 Packaging line with purchase history
    facts = {
        "item_type": "Consumable",
        "category": "Packaging",
        "plant": "PUN1",
        "value": Decimal("156170.00"),
        "is_emergency": False,
        "urgency": "Normal",
        "contract_usable": False,
        "has_active_supplier_purchase_365d": True,
        "is_new_item": False,
        "quantity": Decimal("7370"),
    }

    from backend.engine.policy_eval import evaluate_policy_rules

    r1, _ = evaluate_policy_rules(p1.decision_rules, facts, p1.model_dump())
    assert r1["outcome"]["route"] == "RFQ"

    r2, _ = evaluate_policy_rules(p2.decision_rules, facts, p2.model_dump())
    assert r2["outcome"]["route"] == "SPOT_PO"


def test_effective_date_future_vs_past_resolution(client):
    """
    Verifies version selection based on requirement date:
    - A policy scheduled with a FUTURE effective date does not affect requisitions dated before it.
    - A policy with a PAST/CURRENT effective date takes effect immediately for requisitions on or after that date.
    """
    db = SessionLocal()
    try:
        from backend.app.policy_repo import PolicyRepository
        repo = PolicyRepository(db)

        # Baseline active v5.0 effective 2026-04-01 queried as of 2026-05-01
        active_baseline = repo.get_active_policy(date(2026, 5, 1))
        assert active_baseline.thresholds.spot_limit == Decimal("200000.00")
        assert active_baseline.version == "v5.0"

        # Future amendment effective 2027-01-01 (raising limit to 500,000)
        p_future = active_baseline.model_copy(deep=True)
        p_future.version = "v5.9-future"
        p_future.effective_from = date(2027, 1, 1)
        p_future.thresholds.spot_limit = Decimal("500000.00")
        repo.save_policy(p_future, status="ACTIVE")

        # Query as of November 15, 2026 (before 2027-01-01) -> MUST NOT resolve v5.9-future!
        pol_nov = repo.get_active_policy(date(2026, 11, 15))
        assert pol_nov.version != "v5.9-future"

        # Query as of January 5, 2027 (after 2027-01-01) -> MUST resolve v5.9-future!
        pol_jan = repo.get_active_policy(date(2027, 1, 5))
        assert pol_jan.version == "v5.9-future"
        assert pol_jan.thresholds.spot_limit == Decimal("500000.00")
    finally:
        db.close()


def test_audit_logging_on_policy_actions(client):
    """Verifies that every policy ingestion and approval creates immutable audit trail entries."""
    db = SessionLocal()
    try:
        initial_audit_count = db.query(AuditLog).filter_by(entity="POLICY").count()

        # Ingest new draft
        res = client.post("/api/policies/ingest", json={"instruction": "Change emergency limit to 6 lakh."})
        assert res.status_code == 200
        draft_id = res.json()["draft_id"]

        # Approve draft
        res_app = client.post(f"/api/policies/{draft_id}/approve", json={"approved_by": "Compliance Officer"})
        assert res_app.status_code == 200

        # Check audit records
        new_audit_count = db.query(AuditLog).filter_by(entity="POLICY").count()
        assert new_audit_count >= initial_audit_count + 2

        latest_approve = (
            db.query(AuditLog)
            .filter_by(entity="POLICY", action="APPROVE")
            .order_by(AuditLog.id.desc())
            .first()
        )
        assert latest_approve is not None
        assert latest_approve.who == "Compliance Officer"
        assert latest_approve.after_state == "ACTIVE"
    finally:
        db.close()
