"""
tests/test_worked_examples.py

Encodes all 14 worked examples from Worked_Examples.pdf as pytest cases
evaluated against the real sample PR batch (sample_pr_batch.csv) and master data.
Finds PR lines by pr_no and pr_line without the engine hardcoding any identifiers.
"""

from datetime import datetime, date
from decimal import Decimal
import csv
import json
import pytest

from backend.engine.types import (
    PRLineInput,
    ItemMasterRecord,
    SupplierRecord,
    ContractRecord,
    ContractLineRecord,
    POHistoryRecord,
    ReferenceData,
    BatchLineResult,
)
from backend.engine.orchestrator import process_batch
from backend.engine.schema import PolicyDocument


@pytest.fixture(scope="module")
def reference_data():
    """Loads all real CSV files from kit/master_data and kit/contracts."""
    items = {}
    with open("kit/master_data/item_master.csv", "r", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            items[r["item_code"]] = ItemMasterRecord(
                item_code=r["item_code"],
                description=r["description"],
                uom=r["uom"],
                category=r["category"],
                item_type=r["item_type"],
                standard_price=Decimal(r["standard_price"]),
            )

    suppliers = {}
    with open("kit/master_data/supplier_master.csv", "r", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            suppliers[r["supplier_id"]] = SupplierRecord(
                supplier_id=r["supplier_id"],
                name=r["name"],
                city=r["city"],
                categories=r["categories"],
                status=r["status"],
                on_time_pct=Decimal(r["on_time_pct"]) if r["on_time_pct"] else Decimal("0"),
                quality_rating=Decimal(r["quality_rating"]) if r["quality_rating"] else Decimal("0"),
            )

    po_history = []
    with open("kit/master_data/po_history.csv", "r", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            po_history.append(
                POHistoryRecord(
                    po_number=r["po_number"],
                    po_date=datetime.strptime(r["po_date"], "%Y-%m-%d").date(),
                    supplier_id=r["supplier_id"],
                    item_code=r["item_code"],
                    quantity=Decimal(r["quantity"]),
                    uom=r.get("uom", ""),
                    unit_price=Decimal(r["unit_price"]),
                    plant=r["plant"],
                )
            )

    contract_lines_map = {}
    with open("kit/contracts/contract_lines.csv", "r", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            c_id = r["contract_id"]
            line = ContractLineRecord(
                contract_id=c_id,
                item_code=r["item_code"],
                rate=Decimal(r["rate"]),
                uom=r.get("uom", ""),
                description=r.get("description", ""),
            )
            contract_lines_map.setdefault(c_id, {})[r["item_code"]] = line

    contracts = []
    with open("kit/contracts/contract_register.csv", "r", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            c_id = r["contract_id"]
            supp_name = suppliers[r["supplier_id"]].name if r["supplier_id"] in suppliers else ""
            cap_val = r.get("value_cap") or r.get("value_ceiling") or "0"
            contracts.append(
                ContractRecord(
                    contract_id=c_id,
                    supplier_id=r["supplier_id"],
                    supplier_name=supp_name,
                    start_date=datetime.strptime(r["start_date"], "%Y-%m-%d").date(),
                    end_date=datetime.strptime(r["end_date"], "%Y-%m-%d").date(),
                    value_ceiling=Decimal(cap_val),
                    consumed_value=Decimal(r.get("consumed_value", "0.00")),
                    lines=contract_lines_map.get(c_id, {}),
                )
            )

    # Contract RC-2026-031 exists as a signed PDF valid from 2026-11-15 (Worked Example 2)
    contracts.append(
        ContractRecord(
            contract_id="RC-2026-031",
            supplier_id="S021",
            supplier_name="Pneumatic Point",
            start_date=date(2026, 11, 15),
            end_date=date(2027, 11, 14),
            value_ceiling=Decimal("500000.00"),
            consumed_value=Decimal("0.00"),
            lines={"ITM-1037": ContractLineRecord("RC-2026-031", "ITM-1037", Decimal("2439.00"), "NOS")},
        )
    )

    return ReferenceData(
        items=items,
        suppliers=suppliers,
        contracts=contracts,
        po_history=po_history,
    )


@pytest.fixture(scope="module")
def sample_pr_lines():
    """Loads all 186 PR lines from sample_pr_batch.csv."""
    lines = []
    with open("kit/pr_batches/sample_pr_batch.csv", "r", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            lines.append(
                PRLineInput(
                    pr_no=r["pr_no"],
                    pr_line=int(r["pr_line"]),
                    created_at=datetime.strptime(r["created_at"], "%Y-%m-%d %H:%M"),
                    requester=r.get("requester", ""),
                    department=r.get("department", ""),
                    plant=r["plant"],
                    item_code=r["item_code"] if r["item_code"] else None,
                    description=r["description"],
                    quantity=Decimal(r["quantity"]),
                    uom=r["uom"],
                    estimated_unit_price=Decimal(r["estimated_unit_price"]) if r.get("estimated_unit_price") else None,
                    need_by_date=datetime.strptime(r["need_by_date"], "%Y-%m-%d").date(),
                    urgency=r.get("urgency", "Normal"),
                )
            )
    return lines


@pytest.fixture(scope="module")
def batch_results(sample_pr_lines, reference_data):
    """Processes the full 186-line batch under Corvo Policy v5.0."""
    with open("backend/policies/corvo_v5_0.json", "r", encoding="utf-8") as f:
        policy = PolicyDocument(**json.load(f))
    return process_batch(sample_pr_lines, reference_data, policy)


@pytest.fixture(scope="module")
def results_index(batch_results):
    """Index of batch results by (pr_no, pr_line)."""
    return {(r.pr_no, r.pr_line): r for r in batch_results}


def test_example_1_contract_po(results_index):
    """Worked Example 1: PR-26-00019/1 MS sheet -> CONTRACT_PO, S001 at ₹9,169."""
    res = results_index[("PR-26-00019", 1)]
    assert res.decision == "PO"
    assert res.route == "CONTRACT_PO"
    assert res.supplier_id == "S001"
    assert round(res.unit_price) == 9169
    assert round(res.group_value_inr) == 137531
    assert res.po_id is not None
    assert "RC-2025-011" in res.reason


def test_example_2_pdf_only_contract(results_index):
    """Worked Example 2: PR-26-00045/1 Solenoid valve -> CONTRACT_PO, S021 under RC-2026-031."""
    res = results_index[("PR-26-00045", 1)]
    assert res.decision == "PO"
    assert res.route == "CONTRACT_PO"
    assert res.supplier_id == "S021"
    assert round(res.unit_price) == 2439
    assert round(res.group_value_inr) == 26829
    assert "RC-2026-031" in res.reason


def test_example_3_contract_ceiling_exhausted_rfq(results_index):
    """
    Worked Example 3: PR-26-00004/1 and PR-26-00026/1 clubbed.
    Contract ceiling exceeded -> RFQ with suggested S014, S013, S016.
    """
    r1 = results_index[("PR-26-00004", 1)]
    r2 = results_index[("PR-26-00026", 1)]
    assert r1.group_id == r2.group_id
    assert r1.route == "RFQ"
    assert r1.decision == "SOURCING_REQUEST"
    assert round(r1.group_value_inr) == 220256
    sugg = r1.suggested_supplier_ids.split(";")
    assert sugg == ["S014", "S013", "S016"]
    assert set(sugg) == {"S014", "S013", "S016"}


def test_example_4_and_14_two_contracts_and_po_consolidation(results_index):
    """
    Worked Example 4 & 14:
    PR-26-00034/1 & 32/1 (Req A) and PR-26-00031/1 & 35/1 (Req B).
    Both get CONTRACT_PO with S007 at rate 7.
    Within 24 hours of first line -> consolidated onto the SAME PO ID!
    """
    r34 = results_index[("PR-26-00034", 1)]
    r32 = results_index[("PR-26-00032", 1)]
    r31 = results_index[("PR-26-00031", 1)]
    r35 = results_index[("PR-26-00035", 1)]

    # Check clubbing pairs
    assert r34.group_id == r32.group_id
    assert r31.group_id == r35.group_id
    assert r34.group_id != r31.group_id  # 2 separate requirements

    for r in [r34, r32, r31, r35]:
        assert r.route == "CONTRACT_PO"
        assert r.supplier_id == "S007"
        assert round(r.unit_price) == 7

    assert round(r34.group_value_inr) == 32547
    assert round(r31.group_value_inr) == 23227

    # Consolidation into one PO
    assert r34.po_id == r31.po_id
    assert r34.po_id is not None


def test_example_5_split_prs_clubbed(results_index):
    """Worked Example 5: PR-26-00146/1, 144/1, 145/1 clubbed -> SPOT_PO to S024."""
    r146 = results_index[("PR-26-00146", 1)]
    r144 = results_index[("PR-26-00144", 1)]
    r145 = results_index[("PR-26-00145", 1)]

    assert r146.group_id == r144.group_id == r145.group_id
    assert r146.route == "SPOT_PO"
    assert r146.supplier_id == "S024"
    assert round(r146.unit_price) == 166
    assert round(r146.group_value_inr) == 126472
    assert r146.po_id is not None


def test_example_6_same_item_different_plants_not_clubbed(results_index):
    """
    Worked Example 6: Same item VCI bag 600x900 raised for PUN1 and CHK1.
    Different plants -> 2 separate requirements, each evaluated individually.
    """
    r_pun = results_index[("PR-26-00106", 1)]
    r_chk = results_index[("PR-26-00103", 1)]

    assert r_pun.group_id != r_chk.group_id
    assert r_pun.route == "SPOT_PO"
    assert r_pun.supplier_id == "S027"
    assert round(r_pun.unit_price) == 22
    assert round(r_pun.group_value_inr) == 156170


def test_example_7_freetext_matched_spot_po(results_index):
    """Worked Example 7: Free-text 'hyd hose 1/2 inch 2 wire' matched to ITM-1035 -> SPOT_PO to S023."""
    res = results_index[("PR-26-00088", 1)]
    assert res.resolved_item_code == "ITM-1035"
    assert res.route == "SPOT_PO"
    assert res.supplier_id == "S023"
    assert round(res.unit_price) == 392
    assert round(res.group_value_inr) == 97955


def test_example_8_emergency_po(results_index):
    """Worked Example 8: Emergency gearbox oil seal worth 2.53L (<= 5L) -> EMERGENCY_PO to S014."""
    res = results_index[("PR-26-00059", 1)]
    assert res.resolved_item_code == "ITM-1026"
    assert res.route == "EMERGENCY_PO"
    assert res.supplier_id == "S014"
    assert round(res.unit_price) == 106
    assert round(res.group_value_inr) == 253184


def test_example_9_rfq_above_spot_limit(results_index):
    """Worked Example 9: CMM calibration worth 3.36L (> 2L spot limit) -> RFQ, suggested S043, S044, S042."""
    res = results_index[("PR-26-00089", 1)]
    assert res.resolved_item_code == "ITM-1066"
    assert res.route == "RFQ"
    assert round(res.group_value_inr) == 336562
    sugg = res.suggested_supplier_ids.split(";")
    assert sugg == ["S043", "S044", "S042"]
    assert set(sugg) == {"S043", "S044", "S042"}


def test_example_10_rfq_never_bought(results_index):
    """Worked Example 10: Aluminium plate ITM-1006 worth 80.3k, no purchases in 365d -> RFQ, suggested S003, S002, S005."""
    res = results_index[("PR-26-00050", 1)]
    assert res.resolved_item_code == "ITM-1006"
    assert res.route == "RFQ"
    assert round(res.group_value_inr) == 80300
    sugg = res.suggested_supplier_ids.split(";")
    assert sugg == ["S003", "S002", "S005"]
    assert set(sugg) == {"S003", "S002", "S005"}


def test_example_11_rfp(results_index):
    """Worked Example 11: Encoder CNC spindle worth 20.7L (>= 10L) -> RFP with suggested suppliers."""
    res = results_index[("PR-26-00100", 1)]
    assert res.resolved_item_code == "ITM-1034"
    assert res.route == "RFP"
    assert round(res.group_value_inr) == 2070780
    sugg = res.suggested_supplier_ids.split(";")
    assert sugg == ["S020", "S017", "S019", "S018"]


def test_example_12_capex_sourcing(results_index):
    """Worked Example 12: 'eot crane 5 ton' (Capex) -> CAPEX_SOURCING with 5 suggested suppliers."""
    res = results_index[("PR-26-00047", 1)]
    assert res.resolved_item_code == "ITM-1071"
    assert res.route == "CAPEX_SOURCING"
    assert round(res.group_value_inr) == 6036704
    sugg = res.suggested_supplier_ids.split(";")
    assert sugg == ["S045", "S047", "S020", "S048", "S046"]
    assert set(sugg) == {"S045", "S047", "S020", "S048", "S046"}


def test_example_13_new_item_sourcing(results_index):
    """Worked Example 13: 'Drinking water purifier 50 LPH' not in item master -> NEW_ITEM_SOURCING, 0 suggestions."""
    res = results_index[("PR-26-00170", 1)]
    assert res.resolved_item_code == "NEW"
    assert res.route == "NEW_ITEM_SOURCING"
    assert round(res.group_value_inr) == 141100
    assert res.suggested_supplier_ids == ""


def test_full_batch_summary_metrics(batch_results, reference_data):
    """
    Runs the entire 186-line batch and verifies enterprise compliance metrics:
    - Counts per route and per decision.
    - Zero Blocked or Inactive suppliers awarded purchase orders.
    - Prints human-readable summary table.
    """
    from collections import Counter
    assert len(batch_results) == 186

    decision_counts = Counter(r.decision for r in batch_results)
    route_counts = Counter(r.route for r in batch_results)
    unique_pos = {r.po_id for r in batch_results if r.po_id}

    # Verify zero blocked/inactive suppliers awarded PO
    blocked_awarded = [
        r for r in batch_results
        if r.supplier_id
        and reference_data.suppliers.get(r.supplier_id)
        and reference_data.suppliers[r.supplier_id].status.strip().lower() != "active"
    ]
    assert len(blocked_awarded) == 0, f"Blocked/Inactive suppliers awarded PO: {blocked_awarded}"

    # Print summary table for inspection
    print("\n" + "=" * 50)
    print("      SAMPLE PR BATCH (186 LINES) SUMMARY TABLE")
    print("=" * 50)
    print(f"{'Decision':<25} {'Count':>10}")
    print("-" * 50)
    for dec, count in sorted(decision_counts.items()):
        print(f"{dec:<25} {count:>10}")

    print("\n" + "-" * 50)
    print(f"{'Route':<25} {'Count':>10}")
    print("-" * 50)
    for rt, count in sorted(route_counts.items()):
        print(f"{rt:<25} {count:>10}")

    print("\n" + "-" * 50)
    print(f"Total Requirements Consolidated Into POs : {len(unique_pos)} POs")
    print(f"Blocked / Inactive Suppliers Awarded PO  : {len(blocked_awarded)}")
    print("=" * 50 + "\n")
