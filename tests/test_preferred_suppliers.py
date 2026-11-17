"""
tests/test_preferred_suppliers.py

Unit and integration tests for preferred supplier ranking and sourcing suggestions
per Corvo Procurement Policy v5.0 Section 6 and Worked Examples.
"""

from datetime import date, timedelta
from decimal import Decimal
import csv
import io
import pytest

from backend.engine.types import (
    SupplierRecord,
    POHistoryRecord,
    ContractRecord,
    ContractLineRecord,
    ItemMasterRecord,
)
from backend.engine.preferred_suppliers import (
    build_preferred_supplier_list,
    suggest_sourcing_suppliers,
    export_preferred_suppliers_csv,
    calculate_supplier_score,
)


@pytest.fixture
def mock_suppliers():
    return {
        "S001": SupplierRecord("S001", "Bhosari Steel Traders", "Pune", "Steel & Metals", "Active", Decimal("87.00"), Decimal("3.3")),
        "S002": SupplierRecord("S002", "Deccan Metals", "Pune", "Steel & Metals", "Active", Decimal("79.00"), Decimal("4.5")),
        "S003": SupplierRecord("S003", "Shreeji Steel Corporation", "Mumbai", "Steel & Metals", "Active", Decimal("98.00"), Decimal("4.6")),
        "S004": SupplierRecord("S004", "Metalink Alloys", "Pune", "Steel & Metals", "Blocked", Decimal("88.00"), Decimal("4.7")),
        "S005": SupplierRecord("S005", "Kalyani Steel Stockists", "Pune", "Steel & Metals", "Active", Decimal("68.00"), Decimal("4.6")),
        "S009": SupplierRecord("S009", "Weldtech Supplies", "Pune", "Welding Consumables", "Active", Decimal("83.00"), Decimal("4.6")),
        "S010": SupplierRecord("S010", "Inox Gases Dealer Pune", "Pune", "Welding Consumables", "Active", Decimal("80.00"), Decimal("3.9")),
        "S022": SupplierRecord("S022", "Fluidline Hydraulics", "Pune", "Hydraulics & Pneumatics", "Active", Decimal("77.00"), Decimal("3.5")),
        "S023": SupplierRecord("S023", "Hydrax Hydraulics", "Pune", "Hydraulics & Pneumatics", "Active", Decimal("74.00"), Decimal("3.9")),
        "S024": SupplierRecord("S024", "Janatics Dealer Chakan", "Chakan", "Hydraulics & Pneumatics", "Active", Decimal("89.00"), Decimal("4.1")),
        "S029": SupplierRecord("S029", "SafeGuard Industrial Supplies", "Pune", "Safety, PPE", "Active", Decimal("81.00"), Decimal("3.1")),
        "S030": SupplierRecord("S030", "Karam Safety Distributor", "Mumbai", "Safety, PPE", "Active", Decimal("72.00"), Decimal("3.4")),
        "S031": SupplierRecord("S031", "Udyogi Safety Dealer", "Pune", "Safety, PPE", "Inactive", Decimal("78.00"), Decimal("3.4")),
        "S042": SupplierRecord("S042", "Accurate Calibration Labs", "Pune", "Testing & Calibration", "Active", Decimal("68.00"), Decimal("4.0")),
        "S043": SupplierRecord("S043", "TUV Inspection Partner", "Mumbai", "Testing & Calibration", "Active", Decimal("81.00"), Decimal("3.6")),
        "S044": SupplierRecord("S044", "Metal Testing Labs", "Pune", "Testing & Calibration", "Active", Decimal("86.00"), Decimal("4.6")),
    }


def test_worked_example_itm_1048(mock_suppliers):
    """
    Worked Examples page 5: ITM-1048 (as of 2026-11-01)
    1. S029 (Active, 7 POs, recency 1.0, contract yes, 81% on-time, 3.1 quality) -> total score 0.9335
    2. S030 (Active, 4 POs, recency 1.0, contract no, 72% on-time, 3.4 quality) -> total score 0.5974
    Excluded: S031 (Inactive)
    """
    as_of = date(2026, 11, 1)

    # 7 POs for S029 within 90 days of as_of
    pos = [
        POHistoryRecord(f"PO-029-{i}", as_of - timedelta(days=10 + i * 5), "S029", "ITM-1048", Decimal("100"), "PRS", Decimal("94.00"), "PUN1")
        for i in range(7)
    ]
    # 4 POs for S030 within 90 days of as_of
    pos += [
        POHistoryRecord(f"PO-030-{i}", as_of - timedelta(days=15 + i * 10), "S030", "ITM-1048", Decimal("50"), "PRS", Decimal("89.62"), "PUN1")
        for i in range(4)
    ]
    # 2 POs for S031 (Inactive)
    pos += [
        POHistoryRecord(f"PO-031-{i}", as_of - timedelta(days=20 + i * 10), "S031", "ITM-1048", Decimal("30"), "PRS", Decimal("91.00"), "PUN1")
        for i in range(2)
    ]

    # Contract for S029 covering ITM-1048
    contracts = [
        ContractRecord(
            contract_id="RC-2026-011",
            supplier_id="S029",
            supplier_name="SafeGuard Industrial Supplies",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
            value_ceiling=Decimal("500000"),
            consumed_value=Decimal("100000"),
            lines={"ITM-1048": ContractLineRecord("RC-2026-011", "ITM-1048", Decimal("94.00"), "PRS")},
        )
    ]

    ranked = build_preferred_supplier_list("ITM-1048", as_of, pos, contracts, mock_suppliers)

    assert len(ranked) == 2
    assert ranked[0].supplier_id == "S029"
    assert ranked[0].rank == 1
    assert ranked[0].total_score == Decimal("0.9335")
    assert ranked[0].has_contract is True
    assert ranked[0].po_count == 7
    assert ranked[0].recency_score == Decimal("1.0")
    assert ranked[0].reference_price == Decimal("94.00")

    assert ranked[1].supplier_id == "S030"
    assert ranked[1].rank == 2
    assert ranked[1].total_score == Decimal("0.5974")
    assert ranked[1].has_contract is False
    assert ranked[1].po_count == 4
    assert ranked[1].recency_score == Decimal("1.0")

    # Inactive S031 must not appear
    supplier_ids = [r.supplier_id for r in ranked]
    assert "S031" not in supplier_ids


def test_worked_example_itm_1036(mock_suppliers):
    """
    Worked Examples page 5: ITM-1036 (as of 2026-11-01)
    1. S023: 2 POs, recency 1.0, contract no, 74% on-time, 3.9 quality -> 0.7390
    2. S022: 2 POs, recency 0.5, contract no, 77% on-time, 3.5 quality -> 0.6105
    3. S024: 1 PO, recency 0.0, contract no, 89% on-time, 4.1 quality -> 0.3655
    """
    as_of = date(2026, 11, 1)

    # S023: last PO within 90 days (days=30)
    # S022: last PO within 365 days (days=180)
    # S024: last PO older than 365 days but <= 548 days (days=400)
    pos = [
        POHistoryRecord("PO-23-1", as_of - timedelta(days=30), "S023", "ITM-1036", Decimal("2"), "NOS", Decimal("4360.80"), "PUN1"),
        POHistoryRecord("PO-23-2", as_of - timedelta(days=60), "S023", "ITM-1036", Decimal("1"), "NOS", Decimal("4350.00"), "PUN1"),
        POHistoryRecord("PO-22-1", as_of - timedelta(days=180), "S022", "ITM-1036", Decimal("2"), "NOS", Decimal("4232.09"), "PUN1"),
        POHistoryRecord("PO-22-2", as_of - timedelta(days=210), "S022", "ITM-1036", Decimal("1"), "NOS", Decimal("4200.00"), "PUN1"),
        POHistoryRecord("PO-24-1", as_of - timedelta(days=400), "S024", "ITM-1036", Decimal("1"), "NOS", Decimal("3700.35"), "PUN1"),
    ]

    ranked = build_preferred_supplier_list("ITM-1036", as_of, pos, [], mock_suppliers)

    assert len(ranked) == 3
    assert ranked[0].supplier_id == "S023"
    assert ranked[0].rank == 1
    assert ranked[0].total_score == Decimal("0.7390")

    assert ranked[1].supplier_id == "S022"
    assert ranked[1].rank == 2
    assert ranked[1].total_score == Decimal("0.6105")

    assert ranked[2].supplier_id == "S024"
    assert ranked[2].rank == 3
    assert ranked[2].total_score == Decimal("0.3655")


def test_worked_example_itm_1016(mock_suppliers):
    """
    Worked Examples page 5: ITM-1016 (as of 2026-11-01)
    1. S009: 1 PO, recency 0.5, contract yes, 83% on-time, 4.6 quality -> 0.8415
    2. S010: 1 PO, recency 0.5, contract no, 80% on-time, 3.9 quality -> 0.6230
    """
    as_of = date(2026, 11, 1)

    pos = [
        POHistoryRecord("PO-09-1", as_of - timedelta(days=200), "S009", "ITM-1016", Decimal("50"), "ROL", Decimal("135.05"), "PUN1"),
        POHistoryRecord("PO-10-1", as_of - timedelta(days=150), "S010", "ITM-1016", Decimal("25"), "ROL", Decimal("123.74"), "PUN1"),
    ]

    contracts = [
        ContractRecord(
            contract_id="RC-2025-014",
            supplier_id="S009",
            supplier_name="Weldtech Supplies",
            start_date=date(2025, 4, 1),
            end_date=date(2026, 3, 31),
            value_ceiling=Decimal("300000"),
            consumed_value=Decimal("150000"),
            lines={"ITM-1016": ContractLineRecord("RC-2025-014", "ITM-1016", Decimal("135.00"), "ROL")},
        )
    ]

    ranked = build_preferred_supplier_list("ITM-1016", as_of, pos, contracts, mock_suppliers)

    assert len(ranked) == 2
    assert ranked[0].supplier_id == "S009"
    assert ranked[0].rank == 1
    assert ranked[0].total_score == Decimal("0.8415")
    assert ranked[0].has_contract is True

    assert ranked[1].supplier_id == "S010"
    assert ranked[1].rank == 2
    assert ranked[1].total_score == Decimal("0.6230")
    assert ranked[1].has_contract is False


def test_score_breakdown_transparency(mock_suppliers):
    """Verify that score breakdown contains all components matching total score."""
    as_of = date(2026, 11, 1)
    pos = [
        POHistoryRecord("PO-1", as_of - timedelta(days=20), "S029", "ITM-1048", Decimal("10"), "PRS", Decimal("94.00"), "PUN1")
    ]
    ranked = build_preferred_supplier_list("ITM-1048", as_of, pos, [], mock_suppliers)
    assert len(ranked) == 1
    s29 = ranked[0]

    breakdown_map = {b.component: b for b in s29.breakdown}
    assert "frequency" in breakdown_map
    assert "recency" in breakdown_map
    assert "contract_held" in breakdown_map
    assert "on_time" in breakdown_map
    assert "quality" in breakdown_map

    sum_points = sum(b.points for b in s29.breakdown)
    assert sum_points == s29.total_score


def test_reference_price_fallback_to_contract_rate(mock_suppliers):
    """
    If an eligible supplier has a contract covering the item but no POs in 548 days,
    its reference price is the rate from its contract.
    """
    as_of = date(2026, 11, 1)
    contracts = [
        ContractRecord(
            contract_id="RC-TEST-001",
            supplier_id="S001",
            supplier_name="Bhosari Steel Traders",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
            value_ceiling=Decimal("100000"),
            consumed_value=Decimal("0"),
            lines={"ITM-9999": ContractLineRecord("RC-TEST-001", "ITM-9999", Decimal("250.50"), "NOS")},
        )
    ]
    ranked = build_preferred_supplier_list("ITM-9999", as_of, [], contracts, mock_suppliers)
    assert len(ranked) == 1
    assert ranked[0].supplier_id == "S001"
    assert ranked[0].reference_price == Decimal("250.50")
    assert ranked[0].has_contract is True
    assert ranked[0].po_count == 0


def test_sourcing_suggestions_rfq_top_up(mock_suppliers):
    """
    Policy 6.4: If preferred suppliers < target_count, top up with active category suppliers.
    Worked Example 10: ITM-1006 with 0 preferred suppliers gets ['S003', 'S002', 'S005'].
    """
    as_of = date(2026, 11, 2)
    suggested = suggest_sourcing_suppliers(
        item_code="ITM-1006",
        category="Steel & Metals",
        as_of_date=as_of,
        target_count=3,
        preferred_suppliers=[],
        suppliers=mock_suppliers,
        is_new_item=False,
    )
    # S004 is Blocked so must be excluded. Top 3 by quality and delivery: S003, S002, S005
    assert suggested == ["S003", "S002", "S005"]


def test_sourcing_suggestions_new_item_empty(mock_suppliers):
    """Policy 6.4: New items get NO automatic sourcing suggestions."""
    suggested = suggest_sourcing_suppliers(
        item_code="NEW-001",
        category="Machinery",
        as_of_date=date(2026, 11, 1),
        target_count=5,
        preferred_suppliers=[],
        suppliers=mock_suppliers,
        is_new_item=True,
    )
    assert suggested == []


def test_export_preferred_suppliers_csv(mock_suppliers):
    """Verify CSV export format and columns."""
    as_of = date(2026, 11, 1)
    pos = [
        POHistoryRecord("PO-1", as_of - timedelta(days=20), "S029", "ITM-1048", Decimal("10"), "PRS", Decimal("94.00"), "PUN1")
    ]
    csv_text = export_preferred_suppliers_csv(
        as_of_date=as_of,
        items=[ItemMasterRecord("ITM-1048", "Gloves", "Safety", "CONSUMABLE", "PRS", Decimal("100"))],
        po_history=pos,
        contracts=[],
        suppliers=mock_suppliers,
        top_n=3,
    )

    reader = csv.DictReader(io.StringIO(csv_text))
    rows = list(reader)
    assert len(rows) == 1
    assert rows[0]["item_code"] == "ITM-1048"
    assert rows[0]["rank"] == "1"
    assert rows[0]["supplier_id"] == "S029"
    assert rows[0]["reference_price"] == "94.00"
    assert "total_score" in rows[0]
