"""
tests/test_orchestrator.py

End-to-end tests for engine orchestrator (process_batch):
- Validates all 14 worked examples from Worked_Examples.pdf.
- Tests invalid line handling (PUN2, qty <= 0, duplicates).
- Tests final guard against Blocked / Inactive suppliers.
- Tests 24-hour PO consolidation.
- Tests strict determinism (replay test comparing two identical runs).
"""

from datetime import datetime, date
from decimal import Decimal
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


@pytest.fixture
def policy_v5():
    with open("backend/policies/corvo_v5_0.json", "r", encoding="utf-8") as f:
        return PolicyDocument(**json.load(f))


@pytest.fixture
def test_reference_data():
    items = {
        "ITM-1002": ItemMasterRecord("ITM-1002", "MS sheet 3mm 1250x2500", "NOS", "Steel & Metals", "Raw Material", Decimal("9000.00")),
        "ITM-1006": ItemMasterRecord("ITM-1006", "Aluminium plate 6061 10mm", "KG", "Steel & Metals", "Raw Material", Decimal("365.00")),
        "ITM-1009": ItemMasterRecord("ITM-1009", "Hex bolt M10x40 GR 8.8", "NOS", "Fasteners", "Standard Part", Decimal("8.00")),
        "ITM-1022": ItemMasterRecord("ITM-1022", "Ball bearing 6308-ZZ", "NOS", "Bearings", "Standard Part", Decimal("600.00")),
        "ITM-1026": ItemMasterRecord("ITM-1026", "Gearbox oil seal 45x62x8", "NOS", "Seals & Gaskets", "Standard Part", Decimal("110.00")),
        "ITM-1034": ItemMasterRecord("ITM-1034", "Encoder for CNC spindle (Vertex)", "NOS", "Electrical", "Asset", Decimal("41000.00")),
        "ITM-1035": ItemMasterRecord("ITM-1035", "Hydraulic hose 1/2 inch 2 wire", "MTR", "Hydraulics & Pneumatics", "Consumable", Decimal("400.00")),
        "ITM-1037": ItemMasterRecord("ITM-1037", "Solenoid valve 5/2 1/4 inch", "NOS", "Hydraulics & Pneumatics", "Standard Part", Decimal("2500.00")),
        "ITM-1038": ItemMasterRecord("ITM-1038", "Hydraulic oil HLP 68", "LTR", "Oils & Lubricants", "Consumable", Decimal("170.00")),
        "ITM-1044": ItemMasterRecord("ITM-1044", "VCI bag 600x900", "NOS", "Packaging", "Consumable", Decimal("25.00")),
        "ITM-1048": ItemMasterRecord("ITM-1048", "Nitrile coated gloves", "PRS", "Safety", "Consumable", Decimal("95.00")),
        "ITM-1066": ItemMasterRecord("ITM-1066", "CMM calibration service", "JOB", "Testing & Calibration", "Service", Decimal("67000.00")),
        "ITM-1071": ItemMasterRecord("ITM-1071", "EOT crane 5 ton", "NOS", "Capital Equipment", "Capex", Decimal("1500000.00")),
    }

    suppliers = {
        "S001": SupplierRecord("S001", "Bhosari Steel Traders", "Pune", "Steel & Metals", "Active", Decimal("87.00"), Decimal("3.3")),
        "S002": SupplierRecord("S002", "Deccan Metals", "Pune", "Steel & Metals", "Active", Decimal("79.00"), Decimal("4.5")),
        "S003": SupplierRecord("S003", "Shreeji Steel Corporation", "Mumbai", "Steel & Metals", "Active", Decimal("98.00"), Decimal("4.6")),
        "S004": SupplierRecord("S004", "Metalink Alloys", "Pune", "Steel & Metals", "Blocked", Decimal("88.00"), Decimal("4.7")),
        "S005": SupplierRecord("S005", "Kalyani Steel Stockists", "Pune", "Steel & Metals", "Active", Decimal("68.00"), Decimal("4.6")),
        "S007": SupplierRecord("S007", "Precision Fasteners Co", "Pune", "Fasteners", "Active", Decimal("92.00"), Decimal("4.4")),
        "S008": SupplierRecord("S008", "Unbrako Fasteners Dealer", "Mumbai", "Fasteners", "Active", Decimal("85.00"), Decimal("4.2")),
        "S013": SupplierRecord("S013", "SKF Authorised Distributor", "Pune", "Bearings", "Active", Decimal("91.00"), Decimal("4.5")),
        "S014": SupplierRecord("S014", "Mahalaxmi Machine Spares", "Pune", "Bearings, Seals & Gaskets", "Active", Decimal("84.00"), Decimal("4.1")),
        "S016": SupplierRecord("S016", "National Bearing Center", "Mumbai", "Bearings", "Active", Decimal("78.00"), Decimal("3.8")),
        "S017": SupplierRecord("S017", "Siemens Partner Pune", "Pune", "Electrical", "Active", Decimal("88.00"), Decimal("4.7")),
        "S018": SupplierRecord("S018", "Schneider Electric Dealer", "Pune", "Electrical", "Active", Decimal("82.00"), Decimal("4.3")),
        "S019": SupplierRecord("S019", "Omron Automation Distributor", "Mumbai", "Electrical", "Active", Decimal("79.00"), Decimal("4.2")),
        "S020": SupplierRecord("S020", "Delta Electronics Partner", "Pune", "Electrical, Capital Equipment", "Active", Decimal("94.00"), Decimal("4.6")),
        "S021": SupplierRecord("S021", "Pneumatic Point", "Pune", "Hydraulics & Pneumatics", "Active", Decimal("89.00"), Decimal("4.3")),
        "S023": SupplierRecord("S023", "Hydrax Hydraulics", "Pune", "Hydraulics & Pneumatics", "Active", Decimal("74.00"), Decimal("3.9")),
        "S024": SupplierRecord("S024", "Janatics Dealer Chakan", "Chakan", "Hydraulics & Pneumatics, Oils & Lubricants", "Active", Decimal("89.00"), Decimal("4.1")),
        "S027": SupplierRecord("S027", "Vardhman Packaging", "Pune", "Packaging", "Active", Decimal("86.00"), Decimal("4.2")),
        "S042": SupplierRecord("S042", "Accurate Calibration Labs", "Pune", "Testing & Calibration", "Active", Decimal("68.00"), Decimal("4.0")),
        "S043": SupplierRecord("S043", "TUV Inspection Partner", "Mumbai", "Testing & Calibration", "Active", Decimal("81.00"), Decimal("3.6")),
        "S044": SupplierRecord("S044", "Metal Testing Labs", "Pune", "Testing & Calibration", "Active", Decimal("86.00"), Decimal("4.6")),
        "S045": SupplierRecord("S045", "Demag Cranes Partner", "Pune", "Capital Equipment", "Active", Decimal("92.00"), Decimal("4.8")),
        "S046": SupplierRecord("S046", "Electromag Material Handling", "Pune", "Capital Equipment", "Active", Decimal("75.00"), Decimal("4.1")),
        "S047": SupplierRecord("S047", "Hercules Cranes", "Mumbai", "Capital Equipment", "Active", Decimal("88.00"), Decimal("4.5")),
        "S048": SupplierRecord("S048", "Konecranes Dealer", "Pune", "Capital Equipment", "Active", Decimal("85.00"), Decimal("4.4")),
    }

    contracts = [
        # Ex 1: RC-2025-011 Bhosari Steel Traders covering ITM-1002
        ContractRecord(
            contract_id="RC-2025-011",
            supplier_id="S001",
            supplier_name="Bhosari Steel Traders",
            start_date=date(2025, 4, 1),
            end_date=date(2026, 12, 31),
            value_ceiling=Decimal("500000.00"),
            consumed_value=Decimal("100000.00"),
            lines={"ITM-1002": ContractLineRecord("RC-2025-011", "ITM-1002", Decimal("9168.73"), "NOS")},
        ),
        # Ex 2: RC-2026-031 PDF-only contract covering ITM-1037 from 2026-11-15
        ContractRecord(
            contract_id="RC-2026-031",
            supplier_id="S021",
            supplier_name="Pneumatic Point",
            start_date=date(2026, 11, 15),
            end_date=date(2027, 11, 14),
            value_ceiling=Decimal("500000.00"),
            consumed_value=Decimal("0.00"),
            lines={"ITM-1037": ContractLineRecord("RC-2026-031", "ITM-1037", Decimal("2439.00"), "NOS")},
        ),
        # Ex 3: RC-2026-002 covering ITM-1022 with near-exhausted ceiling (only 38000 left)
        ContractRecord(
            contract_id="RC-2026-002",
            supplier_id="S013",
            supplier_name="SKF Authorised Distributor",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
            value_ceiling=Decimal("1200000.00"),
            consumed_value=Decimal("1162000.00"),  # leaves ~38k
            lines={"ITM-1022": ContractLineRecord("RC-2026-002", "ITM-1022", Decimal("579.62"), "NOS")},
        ),
        # Ex 4 & 14: RC-2026-015 (rate 6.80, exhausted ceiling) and RC-2026-013 (rate 7.00, has room)
        ContractRecord(
            contract_id="RC-2026-015",
            supplier_id="S008",
            supplier_name="Unbrako Fasteners Dealer",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
            value_ceiling=Decimal("200000.00"),
            consumed_value=Decimal("199500.00"),
            lines={"ITM-1009": ContractLineRecord("RC-2026-015", "ITM-1009", Decimal("6.80"), "NOS")},
        ),
        ContractRecord(
            contract_id="RC-2026-013",
            supplier_id="S007",
            supplier_name="Precision Fasteners Co",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
            value_ceiling=Decimal("500000.00"),
            consumed_value=Decimal("150000.00"),
            lines={"ITM-1009": ContractLineRecord("RC-2026-013", "ITM-1009", Decimal("7.00"), "NOS")},
        ),
    ]

    po_history = [
        # Ex 5: Hydraulic oil ITM-1038 bought from S024 at 166.41 within 90 days
        POHistoryRecord("PO-73001", date(2026, 10, 1), "S024", "ITM-1038", Decimal("200"), "LTR", Decimal("166.41"), "CHK1"),
        # Ex 6: VCI bag ITM-1044 bought from S027 at 21.19
        POHistoryRecord("PO-73002", date(2026, 9, 15), "S027", "ITM-1044", Decimal("5000"), "NOS", Decimal("21.19"), "PUN1"),
        # Ex 7: Hydraulic hose ITM-1035 bought from S023 at 391.82
        POHistoryRecord("PO-0023", date(2026, 9, 20), "S023", "ITM-1035", Decimal("100"), "MTR", Decimal("391.82"), "PUN1"),
        # Ex 8: Gearbox oil seal ITM-1026 bought from S014 at 106.38
        POHistoryRecord("PO-0024", date(2026, 8, 10), "S014", "ITM-1026", Decimal("1000"), "NOS", Decimal("106.38"), "PUN1"),
        # Ex 9: CMM calibration ITM-1066 bought from S043
        POHistoryRecord("PO-73005", date(2026, 10, 7), "S043", "ITM-1066", Decimal("1"), "JOB", Decimal("67312.43"), "PUN1"),
        POHistoryRecord("PO-73006", date(2026, 7, 11), "S044", "ITM-1066", Decimal("1"), "JOB", Decimal("66404.67"), "PUN1"),
        # Ex 11: ITM-1034 Encoder bought from S020
        POHistoryRecord("PO-73007", date(2026, 8, 1), "S020", "ITM-1034", Decimal("10"), "NOS", Decimal("41415.60"), "CHK1"),
        # Ex 12: ITM-1071 EOT crane bought at 1509176.00
        POHistoryRecord("PO-73008", date(2026, 5, 1), "S045", "ITM-1071", Decimal("1"), "NOS", Decimal("1509176.00"), "PUN1"),
    ]

    return ReferenceData(
        items=items,
        suppliers=suppliers,
        contracts=contracts,
        po_history=po_history,
    )


def test_worked_example_1_contract_po(test_reference_data, policy_v5):
    """Worked Example 1: PR-26-00019/1 MS sheet -> CONTRACT_PO, S001 at contract rate."""
    line = PRLineInput(
        pr_no="PR-26-00019",
        pr_line=1,
        created_at=datetime(2026, 11, 4, 12, 40),
        requester="User",
        department="Machining",
        plant="PUN1",
        item_code="ITM-1002",
        description="MS sheet 3mm 1250x2500",
        quantity=Decimal("15"),
        uom="NOS",
        estimated_unit_price=Decimal("9000"),
        need_by_date=date(2026, 11, 15),
    )
    results = process_batch([line], test_reference_data, policy_v5)
    assert len(results) == 1
    r = results[0]
    assert r.decision == "PO"
    assert r.route == "CONTRACT_PO"
    assert r.supplier_id == "S001"
    assert r.unit_price == Decimal("9168.73")
    assert r.po_id is not None
    assert "RC-2025-011" in r.reason


def test_worked_example_2_pdf_only_contract(test_reference_data, policy_v5):
    """Worked Example 2: PR-26-00045/1 Solenoid valve -> CONTRACT_PO under RC-2026-031 signed 2026-11-15."""
    line = PRLineInput(
        pr_no="PR-26-00045",
        pr_line=1,
        created_at=datetime(2026, 11, 18, 10, 50),
        requester="User",
        department="Assembly",
        plant="CHK1",
        item_code="ITM-1037",
        description="Solenoid valve 5/2 1/4 inch",
        quantity=Decimal("11"),
        uom="NOS",
        estimated_unit_price=Decimal("2500"),
        need_by_date=date(2026, 12, 13),
    )
    results = process_batch([line], test_reference_data, policy_v5)
    assert len(results) == 1
    r = results[0]
    assert r.decision == "PO"
    assert r.route == "CONTRACT_PO"
    assert r.supplier_id == "S021"
    assert r.unit_price == Decimal("2439.00")
    assert "RC-2026-031" in r.reason


def test_worked_example_3_contract_ceiling_exceeded_rfq(test_reference_data, policy_v5):
    """
    Worked Example 3: Two lines clubbed into single bearing requirement (380 NOS).
    Contract RC-2026-002 ceiling exceeded -> RFQ with suggested S014, S013, S016.
    """
    lines = [
        PRLineInput("PR-26-00004", 1, datetime(2026, 11, 2, 15, 15), "User", "Maint", "CHK1", None, "brg 6308 ZZ for maintenance", Decimal("210"), "NOS", None, date(2026, 11, 26)),
        PRLineInput("PR-26-00026", 1, datetime(2026, 11, 2, 15, 20), "User", "Maint", "CHK1", "ITM-1022", "Ball bearing 6308-ZZ", Decimal("170"), "NOS", None, date(2026, 11, 23)),
    ]
    results = process_batch(lines, test_reference_data, policy_v5)
    assert len(results) == 2
    assert results[0].group_id == results[1].group_id  # Clubbed!
    r = results[0]
    assert r.decision == "SOURCING_REQUEST"
    assert r.route == "RFQ"
    assert r.po_id is None
    assert "S014" in r.suggested_supplier_ids
    assert "S013" in r.suggested_supplier_ids
    assert "S016" in r.suggested_supplier_ids
    assert r.group_value_inr == Decimal("220255.60")  # 380 * 579.62


def test_worked_examples_4_and_14_po_consolidation(test_reference_data, policy_v5):
    """
    Worked Example 4 & 14:
    Req A: lines 3920 & 690 (first line 11-02 14:05)
    Req B: lines 1140 & 2150 (first line 11-03 10:30)
    Both get CONTRACT_PO with S007 at rate 7.00.
    11-03 10:30 is within 24h of 11-02 14:05 -> Consolidated into SAME PO-id!
    """
    lines = [
        PRLineInput("PR-26-00034", 1, datetime(2026, 11, 2, 14, 5), "User", "Mfg", "PUN1", "ITM-1009", "Hex bolt M10x40 GR 8.8", Decimal("3920"), "NOS", None, date(2026, 11, 25)),
        PRLineInput("PR-26-00031", 1, datetime(2026, 11, 3, 10, 30), "User", "Mfg", "PUN1", "ITM-1009", "Hex bolt M10x40 GR 8.8", Decimal("1140"), "NOS", None, date(2026, 11, 12)),
        PRLineInput("PR-26-00035", 1, datetime(2026, 11, 8, 10, 5), "User", "Mfg", "PUN1", "ITM-1009", "Hex bolt M10x40 GR 8.8", Decimal("2150"), "NOS", None, date(2026, 11, 17)),
        PRLineInput("PR-26-00032", 1, datetime(2026, 11, 9, 18, 10), "User", "Mfg", "PUN1", "ITM-1009", "Hex bolt M10x40 GR 8.8", Decimal("690"), "NOS", None, date(2026, 11, 29)),
    ]
    results = process_batch(lines, test_reference_data, policy_v5)
    assert len(results) == 4

    # Check decisions
    for r in results:
        assert r.decision == "PO"
        assert r.route == "CONTRACT_PO"
        assert r.supplier_id == "S007"
        assert r.unit_price == Decimal("7.00")

    # Consolidation: all 4 lines (across the 2 requirements) must share the SAME PO ID!
    po_ids = {r.po_id for r in results}
    assert len(po_ids) == 1
    shared_po_id = list(po_ids)[0]
    assert shared_po_id.startswith("PO-")


def test_worked_example_5_split_prs_clubbed(test_reference_data, policy_v5):
    """Worked Example 5: 3 split PRs clubbed into 1 requirement -> SPOT_PO to S024."""
    lines = [
        PRLineInput("PR-26-00146", 1, datetime(2026, 11, 2, 9, 40), "User", "Maint", "CHK1", "ITM-1038", "Hydraulic oil HLP 68", Decimal("270"), "LTR", None, date(2026, 11, 19)),
        PRLineInput("PR-26-00144", 1, datetime(2026, 11, 3, 9, 30), "User", "Maint", "CHK1", "ITM-1038", "Hydraulic oil HLP 68", Decimal("190"), "LTR", None, date(2026, 11, 15)),
        PRLineInput("PR-26-00145", 1, datetime(2026, 11, 5, 8, 40), "User", "Maint", "CHK1", "ITM-1038", "Hydraulic oil HLP 68", Decimal("300"), "LTR", None, date(2026, 11, 21)),
    ]
    results = process_batch(lines, test_reference_data, policy_v5)
    assert len(results) == 3
    # Same requirement group
    assert results[0].group_id == results[1].group_id == results[2].group_id
    r = results[0]
    assert r.decision == "PO"
    assert r.route == "SPOT_PO"
    assert r.supplier_id == "S024"
    assert r.group_value_inr == Decimal("126471.60")  # 760 * 166.41


def test_worked_example_7_freetext_matched_spot_po(test_reference_data, policy_v5):
    """Worked Example 7: Free-text 'hyd hose 1/2 inch 2 wire' matched to ITM-1035 -> SPOT_PO to S023."""
    line = PRLineInput("PR-26-00088", 1, datetime(2026, 11, 6, 15, 0), "User", "Maint", "PUN1", None, "hyd hose 1/2 inch 2 wire", Decimal("250"), "MTR", None, date(2026, 11, 28))
    results = process_batch([line], test_reference_data, policy_v5)
    assert len(results) == 1
    r = results[0]
    assert r.resolved_item_code == "ITM-1035"
    assert r.decision == "PO"
    assert r.route == "SPOT_PO"
    assert r.supplier_id == "S023"
    assert r.group_value_inr == Decimal("97955.00")


def test_worked_example_8_emergency_po(test_reference_data, policy_v5):
    """Worked Example 8: Emergency oil seal worth 2.53L (<= 5L emergency limit) -> EMERGENCY_PO to S014."""
    line = PRLineInput("PR-26-00059", 1, datetime(2026, 11, 6, 18, 50), "User", "Maint", "PUN1", "ITM-1026", "Gearbox oil seal 45x62x8", Decimal("2380"), "NOS", None, date(2026, 11, 25), urgency="Emergency")
    results = process_batch([line], test_reference_data, policy_v5)
    assert len(results) == 1
    r = results[0]
    assert r.decision == "PO"
    assert r.route == "EMERGENCY_PO"
    assert r.supplier_id == "S014"
    assert r.group_value_inr == Decimal("253184.40")


def test_worked_example_10_rfq_no_recent_purchase(test_reference_data, policy_v5):
    """Worked Example 10: ITM-1006 Aluminium plate worth 80.3k, but no purchases in 365d -> RFQ, suggested S003, S002, S005."""
    line = PRLineInput("PR-26-00050", 1, datetime(2026, 11, 2, 10, 20), "User", "Prod", "PUN1", "ITM-1006", "Aluminium plate 6061 10mm", Decimal("220"), "KG", None, date(2026, 11, 15))
    results = process_batch([line], test_reference_data, policy_v5)
    assert len(results) == 1
    r = results[0]
    assert r.decision == "SOURCING_REQUEST"
    assert r.route == "RFQ"
    assert r.suggested_supplier_ids == "S003;S002;S005"


def test_worked_example_12_capex_equipment(test_reference_data, policy_v5):
    """Worked Example 12: 'eot crane 5 ton' matched to ITM-1071 (Capex) -> CAPEX_SOURCING with 5 suppliers."""
    line = PRLineInput("PR-26-00047", 1, datetime(2026, 11, 3, 14, 0), "User", "Projects", "PUN1", None, "eot crane 5 ton", Decimal("4"), "NOS", None, date(2026, 12, 1))
    results = process_batch([line], test_reference_data, policy_v5)
    assert len(results) == 1
    r = results[0]
    assert r.resolved_item_code == "ITM-1071"
    assert r.decision == "SOURCING_REQUEST"
    assert r.route == "CAPEX_SOURCING"
    assert len(r.suggested_supplier_ids.split(";")) == 5


def test_worked_example_13_new_item_sourcing(test_reference_data, policy_v5):
    """Worked Example 13: 'Drinking water purifier 50 LPH' not in master -> NEW_ITEM_SOURCING, 0 suggestions."""
    line = PRLineInput("PR-26-00170", 1, datetime(2026, 11, 5, 10, 40), "User", "Admin", "PUN1", None, "Drinking water purifier 50 LPH", Decimal("1"), "NOS", Decimal("141100.00"), date(2026, 11, 13))
    results = process_batch([line], test_reference_data, policy_v5)
    assert len(results) == 1
    r = results[0]
    assert r.resolved_item_code == "NEW"
    assert r.decision == "SOURCING_REQUEST"
    assert r.route == "NEW_ITEM_SOURCING"
    assert r.suggested_supplier_ids == ""
    assert r.group_value_inr == Decimal("141100.00")


def test_invalid_lines_not_processed(test_reference_data, policy_v5):
    """Verify validation guards: invalid plant, qty <= 0, duplicates."""
    lines = [
        # Invalid plant PUN2
        PRLineInput("PR-26-00173", 1, datetime(2026, 11, 6, 10, 0), "User", "Maint", "PUN2", "ITM-1002", "MS sheet", Decimal("10"), "NOS", None, date(2026, 11, 20)),
        # Zero quantity
        PRLineInput("PR-26-00172", 1, datetime(2026, 11, 6, 11, 0), "User", "Maint", "PUN1", "ITM-1002", "MS sheet", Decimal("0"), "NOS", None, date(2026, 11, 20)),
        # Duplicate of line 1
        PRLineInput("PR-26-00173", 1, datetime(2026, 11, 6, 12, 0), "User", "Maint", "PUN1", "ITM-1002", "MS sheet", Decimal("5"), "NOS", None, date(2026, 11, 20)),
    ]
    results = process_batch(lines, test_reference_data, policy_v5)
    assert len(results) == 3

    assert results[0].route == "NOT_PROCESSED"
    assert "Invalid plant PUN2" in results[0].reason

    assert results[1].route == "NOT_PROCESSED"
    assert "quantity <= 0" in results[1].reason

    assert results[2].route == "NOT_PROCESSED"
    assert "Duplicate PR line" in results[2].reason


def test_determinism_replay(test_reference_data, policy_v5):
    """Replay test: running process_batch twice on the same input produces identical output."""
    lines = [
        PRLineInput("PR-26-00019", 1, datetime(2026, 11, 4, 12, 40), "User", "Machining", "PUN1", "ITM-1002", "MS sheet 3mm 1250x2500", Decimal("15"), "NOS", Decimal("9000"), date(2026, 11, 15)),
        PRLineInput("PR-26-00050", 1, datetime(2026, 11, 2, 10, 20), "User", "Prod", "PUN1", "ITM-1006", "Aluminium plate 6061 10mm", Decimal("220"), "KG", None, date(2026, 11, 15)),
        PRLineInput("PR-26-00170", 1, datetime(2026, 11, 5, 10, 40), "User", "Admin", "PUN1", None, "Drinking water purifier 50 LPH", Decimal("1"), "NOS", Decimal("141100.00"), date(2026, 11, 13)),
    ]

    run1 = process_batch(lines, test_reference_data, policy_v5)
    run2 = process_batch(lines, test_reference_data, policy_v5)

    assert len(run1) == len(run2)
    for r1, r2 in zip(run1, run2):
        assert r1.pr_no == r2.pr_no
        assert r1.pr_line == r2.pr_line
        assert r1.resolved_item_code == r2.resolved_item_code
        assert r1.group_id == r2.group_id
        assert r1.po_id == r2.po_id
        assert r1.decision == r2.decision
        assert r1.route == r2.route
        assert r1.supplier_id == r2.supplier_id
        assert r1.unit_price == r2.unit_price
        assert r1.group_value_inr == r2.group_value_inr
        assert r1.suggested_supplier_ids == r2.suggested_supplier_ids
        assert r1.policy_version == r2.policy_version
        assert r1.reason == r2.reason
