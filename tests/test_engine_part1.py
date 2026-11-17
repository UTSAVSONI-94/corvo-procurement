import csv
from datetime import date, datetime
from decimal import Decimal
import pytest

from backend.engine.types import (
    ItemMasterRecord,
    SupplierRecord,
    ContractRecord,
    ContractLineRecord,
    POHistoryRecord,
    PRLineInput,
    RequirementGroup,
)
from backend.engine.item_matcher import match_item
from backend.engine.clubber import club_pr_lines
from backend.engine.contracts import (
    ContractLedger,
    find_applicable_contracts,
    select_best_contract,
)
from backend.engine.valuation import (
    value_requirement,
    get_most_recent_po,
    has_active_supplier_purchase,
)


@pytest.fixture
def master_data():
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
                on_time_pct=Decimal(r["on_time_pct"]),
                quality_rating=Decimal(r["quality_rating"]),
            )

    contracts = {}
    with open("kit/contracts/contract_register.csv", "r", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            contracts[r["contract_id"]] = ContractRecord(
                contract_id=r["contract_id"],
                supplier_id=r["supplier_id"],
                supplier_name=r["supplier_name"],
                start_date=datetime.strptime(r["start_date"], "%Y-%m-%d").date(),
                end_date=datetime.strptime(r["end_date"], "%Y-%m-%d").date(),
                value_ceiling=Decimal(r["value_cap"]),
                consumed_value=Decimal(r["consumed_value"]),
                lines={},
            )

    with open("kit/contracts/contract_lines.csv", "r", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            cid = r["contract_id"]
            if cid in contracts:
                contracts[cid].lines[r["item_code"]] = ContractLineRecord(
                    contract_id=cid,
                    item_code=r["item_code"],
                    rate=Decimal(r["rate"]),
                    uom=r["uom"],
                    description=r["description"],
                )

    po_history = []
    with open("kit/master_data/po_history.csv", "r", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            po_history.append(POHistoryRecord(
                po_number=r["po_number"],
                po_date=datetime.strptime(r["po_date"], "%Y-%m-%d").date(),
                supplier_id=r["supplier_id"],
                item_code=r["item_code"],
                quantity=Decimal(r["quantity"]),
                uom=r["uom"],
                unit_price=Decimal(r["unit_price"]),
                plant=r["plant"],
                delivered_on_time=(r["delivered_on_time"].strip().lower() == "true"),
            ))

    return {
        "items": items,
        "suppliers": suppliers,
        "contracts": contracts,
        "po_history": po_history,
    }


# =============================================================
# A) Tests for Item Matcher (Policy 1.1 / 1.2)
# =============================================================
def test_item_matcher_exact_code(master_data):
    items = master_data["items"]
    res = match_item("ITM-1002", "some random text", items)
    assert res.item_code == "ITM-1002"
    assert res.confidence == 100.0
    assert not res.is_new


def test_item_matcher_free_text_examples(master_data):
    items = master_data["items"]

    # 1. "brg 6205 2rs" -> ITM-1021 (Ball bearing 6205-2RS)
    r1 = match_item(None, "brg 6205 2rs", items)
    assert r1.item_code == "ITM-1021"
    assert not r1.is_new
    assert r1.confidence >= 70.0

    # 2. "brg 6308 ZZ for maintenance" -> ITM-1022 (Ball bearing 6308-ZZ)
    r2 = match_item(None, "brg 6308 ZZ for maintenance", items)
    assert r2.item_code == "ITM-1022"
    assert not r2.is_new
    assert r2.confidence >= 70.0

    # 3. "hyd hose 1/2 inch 2 wire" -> ITM-1035 (Hydraulic hose 1/2 inch 2 wire)
    r3 = match_item(None, "hyd hose 1/2 inch 2 wire", items)
    assert r3.item_code == "ITM-1035"
    assert not r3.is_new
    assert r3.confidence >= 70.0

    # 4. "vci bag 600x900" -> ITM-1044 (VCI bag 600x900)
    r4 = match_item(None, "vci bag 600x900", items)
    assert r4.item_code == "ITM-1044"
    assert not r4.is_new
    assert r4.confidence >= 70.0

    # 5. "eot crane 5 ton" -> ITM-1071 (EOT crane 5 ton)
    r5 = match_item(None, "eot crane 5 ton", items)
    assert r5.item_code == "ITM-1071"
    assert not r5.is_new
    assert r5.confidence >= 70.0

    # 6. "Drinking water purifier 50 LPH" -> NEW (not in master)
    r6 = match_item(None, "Drinking water purifier 50 LPH", items)
    assert r6.item_code == "NEW"
    assert r6.is_new


def test_item_matcher_spec_conflict_prevention(master_data):
    items = master_data["items"]
    # Requesting "bearing 6205" should NOT match Ball bearing 6308 (ITM-1022)
    res = match_item(None, "bearing 6205", items)
    assert res.item_code == "ITM-1021"  # 6205-2RS
    assert res.item_code != "ITM-1022"


# =============================================================
# B) Tests for Clubber (Policy 2 & Worked Examples 5, 6, 14)
# =============================================================
def test_clubber_worked_example_5():
    # Worked Example 5: 3 PR lines for Hydraulic oil HLP 68 CHK1 clubbed into one requirement
    lines = [
        PRLineInput(
            pr_no="PR-26-00146",
            pr_line=1,
            created_at=datetime(2026, 11, 2, 9, 40),
            requester="V. Pawar",
            department="Stores",
            plant="CHK1",
            item_code="ITM-1038",
            description="Hydraulic oil HLP 68",
            quantity=Decimal("270"),
            uom="LTR",
            estimated_unit_price=None,
            need_by_date=date(2026, 11, 19),
            urgency="Normal",
        ),
        PRLineInput(
            pr_no="PR-26-00144",
            pr_line=1,
            created_at=datetime(2026, 11, 3, 9, 30),
            requester="K. Jadhav",
            department="Tool Room",
            plant="CHK1",
            item_code="ITM-1038",
            description="Hydraulic oil HLP 68",
            quantity=Decimal("190"),
            uom="LTR",
            estimated_unit_price=Decimal("151.18"),
            need_by_date=date(2026, 11, 15),
            urgency="Normal",
        ),
        PRLineInput(
            pr_no="PR-26-00145",
            pr_line=1,
            created_at=datetime(2026, 11, 5, 8, 40),
            requester="N. Iyer",
            department="Production",
            plant="CHK1",
            item_code="ITM-1038",
            description="Hydraulic oil HLP 68",
            quantity=Decimal("300"),
            uom="LTR",
            estimated_unit_price=Decimal("164.14"),
            need_by_date=date(2026, 11, 21),
            urgency="Normal",
        ),
    ]

    reqs = club_pr_lines(lines, resolved_item_codes={})
    assert len(reqs) == 1
    req = reqs[0]
    assert req.resolved_item_code == "ITM-1038"
    assert req.plant == "CHK1"
    assert req.total_quantity == Decimal("760")
    assert req.requirement_date == date(2026, 11, 2)
    assert len(req.pr_lines) == 3


def test_clubber_worked_example_6():
    # Worked Example 6: Same item (VCI bag 600x900) but different plants -> NOT clubbed
    lines = [
        PRLineInput(
            pr_no="PR-26-00106",
            pr_line=1,
            created_at=datetime(2026, 11, 2, 12, 0),
            requester="M. Shaikh",
            department="Tool Room",
            plant="PUN1",
            item_code="ITM-1044",
            description="VCI bag 600x900",
            quantity=Decimal("7370"),
            uom="NOS",
            estimated_unit_price=None,
            need_by_date=date(2027, 2, 19),
            urgency="Normal",
        ),
        PRLineInput(
            pr_no="PR-26-00103",
            pr_line=1,
            created_at=datetime(2026, 11, 5, 8, 50),
            requester="N. Iyer",
            department="Maintenance",
            plant="CHK1",
            item_code=None,
            description="vci bag 600x900",
            quantity=Decimal("6480"),
            uom="NOS",
            estimated_unit_price=Decimal("18.74"),
            need_by_date=date(2027, 3, 4),
            urgency="Normal",
        ),
    ]

    resolved_codes = {("PR-26-00103", 1): "ITM-1044"}
    reqs = club_pr_lines(lines, resolved_item_codes=resolved_codes)
    assert len(reqs) == 2
    assert reqs[0].plant == "PUN1"
    assert reqs[0].total_quantity == Decimal("7370")
    assert reqs[1].plant == "CHK1"
    assert reqs[1].total_quantity == Decimal("6480")


def test_clubber_worked_example_14():
    # Worked Example 14: Hex bolt M10x40 GR 8.8 (ITM-1009) at PUN1
    # PR-26-00034/1 created 2026-11-02 14:05, need-by 2026-11-25 (3920)
    # PR-26-00031/1 created 2026-11-03 10:30, need-by 2026-11-12 (1140)
    # PR-26-00035/1 created 2026-11-08 10:05, need-by 2026-11-17 (2150)
    # PR-26-00032/1 created 2026-11-09 18:10, need-by 2026-11-29 (690)
    lines = [
        PRLineInput(
            pr_no="PR-26-00034",
            pr_line=1,
            created_at=datetime(2026, 11, 2, 14, 5),
            requester="R. Deshmukh",
            department="Stores",
            plant="PUN1",
            item_code="ITM-1009",
            description="Hex bolt M10x40 GR 8.8",
            quantity=Decimal("3920"),
            uom="NOS",
            estimated_unit_price=Decimal("9.12"),
            need_by_date=date(2026, 11, 25),
            urgency="Normal",
        ),
        PRLineInput(
            pr_no="PR-26-00031",
            pr_line=1,
            created_at=datetime(2026, 11, 3, 10, 30),
            requester="R. Deshmukh",
            department="Quality",
            plant="PUN1",
            item_code="ITM-1009",
            description="Hex bolt M10x40 GR 8.8",
            quantity=Decimal("1140"),
            uom="NOS",
            estimated_unit_price=Decimal("7.65"),
            need_by_date=date(2026, 11, 12),
            urgency="Normal",
        ),
        PRLineInput(
            pr_no="PR-26-00035",
            pr_line=1,
            created_at=datetime(2026, 11, 8, 10, 5),
            requester="N. Iyer",
            department="Tool Room",
            plant="PUN1",
            item_code="ITM-1009",
            description="Hex bolt M10x40 GR 8.8",
            quantity=Decimal("2150"),
            uom="NOS",
            estimated_unit_price=None,
            need_by_date=date(2026, 11, 17),
            urgency="Normal",
        ),
        PRLineInput(
            pr_no="PR-26-00032",
            pr_line=1,
            created_at=datetime(2026, 11, 9, 18, 10),
            requester="M. Shaikh",
            department="Stores",
            plant="PUN1",
            item_code="ITM-1009",
            description="Hex bolt M10x40 GR 8.8",
            quantity=Decimal("690"),
            uom="NOS",
            estimated_unit_price=Decimal("6.84"),
            need_by_date=date(2026, 11, 29),
            urgency="Normal",
        ),
    ]

    reqs = club_pr_lines(lines, resolved_item_codes={})
    assert len(reqs) == 2

    # Req 1: PR 34 (3920) + PR 32 (690) = 4610 NOS (first need-by Nov 25)
    # Req 2: PR 31 (1140) + PR 35 (2150) = 3290 NOS (first need-by Nov 12)
    req1 = reqs[0]
    req2 = reqs[1]

    assert req1.total_quantity == Decimal("4610")
    assert {l.pr_no for l in req1.pr_lines} == {"PR-26-00034", "PR-26-00032"}

    assert req2.total_quantity == Decimal("3290")
    assert {l.pr_no for l in req2.pr_lines} == {"PR-26-00031", "PR-26-00035"}


# =============================================================
# C) Tests for Contracts & Ceilings (Worked Examples 2, 3, 4)
# =============================================================
def test_contract_worked_example_2(master_data):
    # Worked Example 2: Contract signed after register (RC-2026-031 with S021 Pneumatic Point, starts 2026-11-15)
    contracts = master_data["contracts"]
    suppliers = master_data["suppliers"]

    # Add the PDF-only contract
    pdf_contract = ContractRecord(
        contract_id="RC-2026-031",
        supplier_id="S021",
        supplier_name="Pneumatic Point",
        start_date=date(2026, 11, 15),
        end_date=date(2027, 11, 14),
        value_ceiling=Decimal("1000000.00"),
        consumed_value=Decimal("0.00"),
        lines={
            "ITM-1037": ContractLineRecord(
                contract_id="RC-2026-031",
                item_code="ITM-1037",
                rate=Decimal("2439.00"),
                uom="NOS",
            )
        },
    )
    contracts["RC-2026-031"] = pdf_contract
    ledger = ContractLedger(contracts)

    req_date = date(2026, 11, 18)  # After Nov 15
    qty = Decimal("11")

    best_c, rate, usable, lowest_rate = select_best_contract(
        "ITM-1037", req_date, qty, contracts, suppliers, ledger
    )
    assert best_c is not None
    assert best_c.contract_id == "RC-2026-031"
    assert rate == Decimal("2439.00")
    assert usable is True


def test_contract_worked_example_3(master_data):
    # Worked Example 3: Bearings contract RC-2026-002 only has ~₹38,000 ceiling left
    contracts = master_data["contracts"]
    suppliers = master_data["suppliers"]
    ledger = ContractLedger(contracts)

    req_date = date(2026, 11, 2)
    qty = Decimal("380")  # 210 + 170

    # Remaining room check
    rem = ledger.get_remaining_ceiling("RC-2026-002")
    assert rem == Decimal("38000.00")

    best_c, rate, usable, lowest_rate = select_best_contract(
        "ITM-1022", req_date, qty, contracts, suppliers, ledger
    )
    # Contract cannot be used because value exceeds 38000
    assert usable is False
    assert best_c is None
    # But lowest applicable rate is returned for valuation fallback (Policy 3.1a)
    assert rate == Decimal("579.62")


def test_contract_worked_example_4(master_data):
    # Worked Example 4: Two contracts for Hex bolt M10x40 (ITM-1009)
    # RC-2026-015 rate 6.45 (cap 500000, consumed 488000 -> room 12000)
    # RC-2026-013 rate 7.06 (cap 800000, consumed 250000 -> room 550000)
    contracts = master_data["contracts"]
    suppliers = master_data["suppliers"]
    ledger = ContractLedger(contracts)

    req_date = date(2026, 11, 2)
    qty = Decimal("4610")  # Total requirement value at ~7 is ~32,547

    best_c, rate, usable, lowest_rate = select_best_contract(
        "ITM-1009", req_date, qty, contracts, suppliers, ledger
    )
    assert usable is True
    assert best_c.contract_id == "RC-2026-013"
    assert rate == Decimal("7.06")


# =============================================================
# D) Tests for Valuation (Policy 3.1 & 1.2)
# =============================================================
def test_valuation_contract_used(master_data):
    # Worked Example 1: Contract PO for ITM-1002 (MS sheet 3mm)
    # RC-2025-011 with Bhosari Steel Traders at rate 9168.71
    contracts = master_data["contracts"]
    suppliers = master_data["suppliers"]
    items = master_data["items"]
    po_history = master_data["po_history"]
    ledger = ContractLedger(contracts)

    req = RequirementGroup(
        id="REQ-0001",
        resolved_item_code="ITM-1002",
        plant="PUN1",
        requirement_date=date(2026, 11, 4),
        first_need_by_date=date(2026, 11, 15),
        total_quantity=Decimal("15"),
        uom="NOS",
        is_emergency=False,
        pr_lines=[],
    )

    val_res, selected_c, usable = value_requirement(
        req, items, contracts, suppliers, po_history, ledger
    )
    assert usable is True
    assert selected_c.contract_id == "RC-2025-011"
    assert val_res.unit_price == Decimal("9168.71")
    assert val_res.total_value == Decimal("15") * Decimal("9168.71")
    assert val_res.source_method == "CONTRACT_RATE"


def test_valuation_new_item():
    # Worked Example 13: NEW item valued at quantity * requester estimated unit price
    line = PRLineInput(
        pr_no="PR-26-00170",
        pr_line=1,
        created_at=datetime(2026, 11, 5, 10, 40),
        requester="R. Deshmukh",
        department="Maintenance",
        plant="PUN1",
        item_code=None,
        description="Drinking water purifier 50 LPH",
        quantity=Decimal("1"),
        uom="NOS",
        estimated_unit_price=Decimal("141100.00"),
        need_by_date=date(2026, 11, 13),
        urgency="Normal",
    )
    req = RequirementGroup(
        id="REQ-0013",
        resolved_item_code="NEW",
        plant="PUN1",
        requirement_date=date(2026, 11, 5),
        first_need_by_date=date(2026, 11, 13),
        total_quantity=Decimal("1"),
        uom="NOS",
        is_emergency=False,
        pr_lines=[line],
    )

    val_res, selected_c, usable = value_requirement(
        req, {}, {}, {}, [], ContractLedger({})
    )
    assert not usable
    assert selected_c is None
    assert val_res.unit_price == Decimal("141100.00")
    assert val_res.total_value == Decimal("141100.00")
    assert val_res.source_method == "ESTIMATED_PRICE"
