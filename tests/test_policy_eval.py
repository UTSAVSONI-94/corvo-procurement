import json
import pytest
from datetime import date
from decimal import Decimal
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.database import Base
from backend.app.policy_repo import PolicyRepository
from backend.engine.schema import PolicyDocument
from backend.engine.policy_eval import (
    evaluate_condition,
    evaluate_policy_rules,
    resolve_ref,
)


@pytest.fixture
def policy_doc():
    with open("backend/policies/corvo_v5_0.json", "r", encoding="utf-8") as f:
        data = json.load(f)
    return PolicyDocument(**data)


@pytest.fixture
def policy_dict(policy_doc):
    return policy_doc.model_dump() if hasattr(policy_doc, "model_dump") else policy_doc.dict()


# -------------------------------------------------------------
# 1. Tests for Reference Resolution
# -------------------------------------------------------------
def test_resolve_ref(policy_dict):
    assert resolve_ref("thresholds.spot_limit", policy_dict) == Decimal("200000.00")
    assert resolve_ref("thresholds.emergency_limit", policy_dict) == Decimal("500000.00")
    assert resolve_ref("parameters.club_window_days", policy_dict) == 14
    assert resolve_ref("parameters.consolidation_window_hours", policy_dict) == 24

    with pytest.raises(KeyError):
        resolve_ref("non_existent.field", policy_dict)


# -------------------------------------------------------------
# 2. Tests for Operators
# -------------------------------------------------------------
def test_operator_eq(policy_dict):
    assert evaluate_condition({"field": "plant", "op": "eq", "value": "PUN1"}, {"plant": "PUN1"}, policy_dict)
    assert not evaluate_condition({"field": "plant", "op": "eq", "value": "PUN1"}, {"plant": "CHK1"}, policy_dict)


def test_operator_ne(policy_dict):
    assert evaluate_condition({"field": "item_type", "op": "ne", "value": "Capex"}, {"item_type": "Material"}, policy_dict)
    assert not evaluate_condition({"field": "item_type", "op": "ne", "value": "Capex"}, {"item_type": "Capex"}, policy_dict)


def test_operator_lt(policy_dict):
    # Literal
    assert evaluate_condition({"field": "value", "op": "lt", "value": 200000}, {"value": Decimal("199999.00")}, policy_dict)
    assert not evaluate_condition({"field": "value", "op": "lt", "value": 200000}, {"value": Decimal("200000.00")}, policy_dict)
    # Ref
    assert evaluate_condition({"field": "value", "op": "lt", "ref": "thresholds.spot_limit"}, {"value": Decimal("150000.00")}, policy_dict)
    assert not evaluate_condition({"field": "value", "op": "lt", "ref": "thresholds.spot_limit"}, {"value": Decimal("250000.00")}, policy_dict)


def test_operator_lte(policy_dict):
    assert evaluate_condition({"field": "value", "op": "lte", "ref": "thresholds.emergency_limit"}, {"value": Decimal("500000.00")}, policy_dict)
    assert evaluate_condition({"field": "value", "op": "lte", "ref": "thresholds.emergency_limit"}, {"value": Decimal("499999.00")}, policy_dict)
    assert not evaluate_condition({"field": "value", "op": "lte", "ref": "thresholds.emergency_limit"}, {"value": Decimal("500001.00")}, policy_dict)


def test_operator_gt(policy_dict):
    assert evaluate_condition({"field": "value", "op": "gt", "value": 1000000}, {"value": Decimal("1000001.00")}, policy_dict)
    assert not evaluate_condition({"field": "value", "op": "gt", "value": 1000000}, {"value": Decimal("1000000.00")}, policy_dict)


def test_operator_gte(policy_dict):
    assert evaluate_condition({"field": "value", "op": "gte", "ref": "thresholds.rfp_threshold"}, {"value": Decimal("1000000.00")}, policy_dict)
    assert not evaluate_condition({"field": "value", "op": "gte", "ref": "thresholds.rfp_threshold"}, {"value": Decimal("999999.00")}, policy_dict)


def test_operator_in(policy_dict):
    cond = {"field": "plant", "op": "in", "value": ["PUN1", "CHK1"]}
    assert evaluate_condition(cond, {"plant": "PUN1"}, policy_dict)
    assert evaluate_condition(cond, {"plant": "CHK1"}, policy_dict)
    assert not evaluate_condition(cond, {"plant": "PUN2"}, policy_dict)


def test_operator_not_in(policy_dict):
    cond = {"field": "category", "op": "not_in", "value": ["Capital Equipment", "Facility Services"]}
    assert evaluate_condition(cond, {"category": "Fasteners"}, policy_dict)
    assert not evaluate_condition(cond, {"category": "Capital Equipment"}, policy_dict)


# -------------------------------------------------------------
# 3. Tests for Combinators (all, any, not, nested)
# -------------------------------------------------------------
def test_combinator_all(policy_dict):
    cond = {
        "all": [
            {"field": "is_emergency", "op": "eq", "value": True},
            {"field": "value", "op": "lte", "ref": "thresholds.emergency_limit"},
            {"field": "has_active_supplier_purchase_365d", "op": "eq", "value": True},
        ]
    }
    facts_match = {"is_emergency": True, "value": Decimal("253184.00"), "has_active_supplier_purchase_365d": True}
    assert evaluate_condition(cond, facts_match, policy_dict)

    facts_no_history = {"is_emergency": True, "value": Decimal("253184.00"), "has_active_supplier_purchase_365d": False}
    assert not evaluate_condition(cond, facts_no_history, policy_dict)

    facts_over_limit = {"is_emergency": True, "value": Decimal("550000.00"), "has_active_supplier_purchase_365d": True}
    assert not evaluate_condition(cond, facts_over_limit, policy_dict)


def test_combinator_any(policy_dict):
    cond = {
        "any": [
            {"field": "item_type", "op": "eq", "value": "Capex"},
            {"field": "category", "op": "eq", "value": "Capital Equipment"},
        ]
    }
    assert evaluate_condition(cond, {"item_type": "Capex", "category": "General"}, policy_dict)
    assert evaluate_condition(cond, {"item_type": "Material", "category": "Capital Equipment"}, policy_dict)
    assert not evaluate_condition(cond, {"item_type": "Material", "category": "Fasteners"}, policy_dict)


def test_combinator_not(policy_dict):
    cond = {
        "not": {"field": "contract_usable", "op": "eq", "value": True}
    }
    assert evaluate_condition(cond, {"contract_usable": False}, policy_dict)
    assert not evaluate_condition(cond, {"contract_usable": True}, policy_dict)


def test_nested_conditions(policy_dict):
    # Plant-specific condition override example: PUN1 gets spot up to 300000, others 200000
    cond = {
        "any": [
            {
                "all": [
                    {"field": "plant", "op": "eq", "value": "PUN1"},
                    {"field": "value", "op": "lt", "value": Decimal("300000.00")}
                ]
            },
            {
                "all": [
                    {"field": "plant", "op": "ne", "value": "PUN1"},
                    {"field": "value", "op": "lt", "value": Decimal("200000.00")}
                ]
            }
        ]
    }
    assert evaluate_condition(cond, {"plant": "PUN1", "value": Decimal("250000.00")}, policy_dict)
    assert not evaluate_condition(cond, {"plant": "CHK1", "value": Decimal("250000.00")}, policy_dict)
    assert evaluate_condition(cond, {"plant": "CHK1", "value": Decimal("150000.00")}, policy_dict)


# -------------------------------------------------------------
# 4. Tests for Policy Rule Order & Outcomes
# -------------------------------------------------------------
def test_rule_order_capex(policy_doc, policy_dict):
    # Rule 5.1 Capex must precede contract and value rules
    facts = {
        "item_type": "Capex",
        "contract_usable": True,  # even if contract exists, Capex goes to sourcing
        "value": Decimal("6036704.00"),
        "has_active_supplier_purchase_365d": True,
    }
    rule, reason = evaluate_policy_rules(policy_doc.decision_rules, facts, policy_dict)
    assert rule is not None
    assert rule["id"] == "5.1"
    assert rule["outcome"]["route"] == "CAPEX_SOURCING"


def test_rule_order_contract(policy_doc, policy_dict):
    # Rule 5.2 Contract applies before spot or emergency
    facts = {
        "item_type": "Material",
        "contract_usable": True,
        "is_emergency": True,
        "value": Decimal("137531.00"),
        "has_active_supplier_purchase_365d": True,
    }
    rule, reason = evaluate_policy_rules(policy_doc.decision_rules, facts, policy_dict)
    assert rule is not None
    assert rule["id"] == "5.2"
    assert rule["outcome"]["route"] == "CONTRACT_PO"


def test_rule_order_emergency(policy_doc, policy_dict):
    # Rule 5.3 Emergency under 5L with history takes precedence over Spot
    facts = {
        "item_type": "Material",
        "contract_usable": False,
        "is_emergency": True,
        "value": Decimal("253184.00"),
        "has_active_supplier_purchase_365d": True,
    }
    rule, reason = evaluate_policy_rules(policy_doc.decision_rules, facts, policy_dict)
    assert rule is not None
    assert rule["id"] == "5.3"
    assert rule["outcome"]["route"] == "EMERGENCY_PO"


def test_rule_order_spot(policy_doc, policy_dict):
    facts = {
        "item_type": "Material",
        "contract_usable": False,
        "is_emergency": False,
        "value": Decimal("126472.00"),
        "has_active_supplier_purchase_365d": True,
    }
    rule, reason = evaluate_policy_rules(policy_doc.decision_rules, facts, policy_dict)
    assert rule is not None
    assert rule["id"] == "5.4"
    assert rule["outcome"]["route"] == "SPOT_PO"


def test_rule_order_rfq_small_no_history(policy_doc, policy_dict):
    # Worked Example 10: under 2L but no active purchase in 365d -> RFQ
    facts = {
        "item_type": "Material",
        "contract_usable": False,
        "is_emergency": False,
        "value": Decimal("80300.00"),
        "has_active_supplier_purchase_365d": False,
    }
    rule, reason = evaluate_policy_rules(policy_doc.decision_rules, facts, policy_dict)
    assert rule is not None
    assert rule["id"] == "5.5"
    assert rule["outcome"]["route"] == "RFQ"


def test_rule_order_rfp_large_value(policy_doc, policy_dict):
    # Worked Example 11: value >= 10L -> RFP
    facts = {
        "item_type": "Material",
        "contract_usable": False,
        "is_emergency": False,
        "value": Decimal("2070780.00"),
        "has_active_supplier_purchase_365d": True,
    }
    rule, reason = evaluate_policy_rules(policy_doc.decision_rules, facts, policy_dict)
    assert rule is not None
    assert rule["id"] == "5.6"
    assert rule["outcome"]["route"] == "RFP"


# -------------------------------------------------------------
# 5. Tests for PolicyRepository (effective_from handling)
# -------------------------------------------------------------
def test_policy_repository_effective_date_lookup():
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = TestingSessionLocal()

    with open("backend/policies/corvo_v5_0.json", "r") as f:
        v5_data = json.load(f)
    v5_doc = PolicyDocument(**v5_data)

    repo = PolicyRepository(db)
    # Save v5.0
    repo.save_policy(v5_doc, created_by="Procurement Head", status="ACTIVE")

    # 1. As of date before 2026-04-01 -> raises LookupError
    with pytest.raises(LookupError):
        repo.get_active_policy(date(2026, 3, 31))

    # 2. As of date on or after 2026-04-01 (e.g. sample batch in Nov 2026) -> gets v5.0
    active = repo.get_active_policy(date(2026, 11, 4))
    assert active.version == "v5.0"
    assert active.thresholds.spot_limit == Decimal("200000.00")

    # 3. Add an amendment (v5.1) effective from 2026-11-15 with a spot limit of 250,000
    v5_1_data = json.loads(json.dumps(v5_data))
    v5_1_data["version"] = "v5.1"
    v5_1_data["effective_from"] = "2026-11-15"
    v5_1_data["thresholds"]["spot_limit"] = 250000.00
    v5_1_doc = PolicyDocument(**v5_1_data)
    repo.save_policy(v5_1_doc, created_by="Procurement Admin", status="ACTIVE")

    # PRs created on 2026-11-10 (before Nov 15) MUST still use v5.0
    policy_nov_10 = repo.get_active_policy(date(2026, 11, 10))
    assert policy_nov_10.version == "v5.0"
    assert policy_nov_10.thresholds.spot_limit == Decimal("200000.00")

    # PRs created on 2026-11-16 (after Nov 15) MUST use v5.1
    policy_nov_16 = repo.get_active_policy(date(2026, 11, 16))
    assert policy_nov_16.version == "v5.1"
    assert policy_nov_16.thresholds.spot_limit == Decimal("250000.00")

    db.close()

