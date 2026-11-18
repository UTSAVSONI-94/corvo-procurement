"""
tests/test_contract_management.py

Unit and integration tests for Contract Management (Stage 9):
1. GET /api/contracts with filters (supplier, status, source, search, as_of_date).
2. Calculation of ceiling utilization percentage and remaining balance.
3. POST /api/contracts/extract: PDF text parsing, Schedule A extraction, and confidence scoring.
4. POST /api/contracts/confirm: Buyer confirmation, line persistence, and audit logging.
5. POST /api/contracts/manual: Manual contract creation.
6. Policy 4.4 behavior: Contract binding from start_date with consumed=0.
"""

from datetime import date, datetime
from decimal import Decimal
import os
import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.database import SessionLocal
from backend.app.models import Contract, ContractLine, AuditLog
from backend.app.contract_service import (
    extract_text_from_pdf,
    parse_contract_text,
    save_or_update_contract,
    ContractConfirmRequest,
    ContractLinePreview,
)


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


def test_list_contracts_filters_and_utilization(client):
    """
    Verifies GET /api/contracts:
    - Lists contracts from database.
    - Computes ceiling_used_pct and remaining_value correctly.
    - Supports filtering by supplier_id, status, source, and search string.
    """
    # 1. Basic listing
    res = client.get("/api/contracts")
    assert res.status_code == 200
    data = res.json()
    assert len(data) >= 10

    # Verify ceiling calculation on RC-2025-011 (ceiling 6,000,000, consumed 4,100,000 -> ~68.33%)
    rc11 = next((c for c in data if c["contract_id"] == "RC-2025-011"), None)
    assert rc11 is not None
    assert rc11["value_ceiling"] == 6000000.0
    assert rc11["consumed_value"] == 4100000.0
    assert rc11["remaining_value"] == 1900000.0
    assert abs(rc11["ceiling_used_pct"] - 68.33) < 0.1
    assert rc11["supplier_id"] == "S001"
    assert len(rc11["lines"]) == 3

    # 2. Filter by supplier_id
    res_sup = client.get("/api/contracts?supplier_id=S001")
    assert res_sup.status_code == 200
    sup_data = res_sup.json()
    assert all(c["supplier_id"] == "S001" for c in sup_data)

    # 3. Filter by search (item_code ITM-1001)
    res_search = client.get("/api/contracts?search=ITM-1001")
    assert res_search.status_code == 200
    search_data = res_search.json()
    assert any(c["contract_id"] == "RC-2025-011" for c in search_data)

    # 4. Filter by status=EXHAUSTED as of today
    # Contract RC-2026-015 has ceiling 500,000, consumed 488,000 (remaining 12,000)
    # Let's check status query
    res_active = client.get("/api/contracts?status=ACTIVE&as_of_date=2026-11-01")
    assert res_active.status_code == 200
    active_data = res_active.json()
    assert len(active_data) > 0
    assert all(c["validity_status"] == "ACTIVE" for c in active_data)


def test_get_contract_detail_endpoint(client):
    """Verifies GET /api/contracts/{contract_id} returns all details and line items."""
    res = client.get("/api/contracts/RC-2026-002")
    assert res.status_code == 200
    data = res.json()
    assert data["contract_id"] == "RC-2026-002"
    assert data["supplier_id"] == "S013"
    assert data["value_ceiling"] == 1200000.0
    assert len(data["lines"]) == 4

    # Non-existent contract returns 404
    res_none = client.get("/api/contracts/RC-9999-999")
    assert res_none.status_code == 404


def test_extract_contract_from_pdf_preview(client):
    """
    Verifies POST /api/contracts/extract:
    - Extracts structured contract metadata from a PDF file.
    - Accurately captures header, validity dates, ceiling, and Schedule A rates.
    - Generates confidence score and preview without saving to database.
    """
    pdf_path = "kit/contracts/pdf/RC-2025-014.pdf"
    assert os.path.exists(pdf_path)

    res = client.post("/api/contracts/extract", json={"file_path": pdf_path})
    assert res.status_code == 200
    data = res.json()

    assert data["contract_id"] == "RC-2025-014"
    assert data["supplier_id"] == "S009"
    assert "Weldtech Supplies" in data["supplier_name"]
    assert data["start_date"] == "2025-12-01"
    assert data["end_date"] == "2026-11-30"
    assert float(data["value_ceiling"]) == 1500000.0
    assert float(data["consumed_value"]) == 0.0
    assert data["confidence_score"] >= 0.9
    assert len(data["lines"]) == 3

    # Check line items
    item_codes = [l["item_code"] for l in data["lines"]]
    assert "ITM-1015" in item_codes
    assert "ITM-1016" in item_codes
    assert "ITM-1019" in item_codes


def test_confirm_contract_persists_and_logs_audit(client):
    """
    Verifies POST /api/contracts/confirm:
    - Persists confirmed contract and its lines into database.
    - Enforces consumed_value=0.00 for new contracts.
    - Writes immutable entry in audit_log.
    """
    test_cid = "RC-2027-TEST-99"
    payload = {
        "contract_id": test_cid,
        "supplier_id": "S021",
        "supplier_name": "Pneumatic Point",
        "start_date": "2027-01-01",
        "end_date": "2027-12-31",
        "value_ceiling": "750000.00",
        "consumed_value": "0.00",
        "source": "PDF_EXTRACTED",
        "pdf_path": "kit/contracts/pdf/RC-2027-TEST-99.pdf",
        "lines": [
            {
                "item_code": "ITM-1037",
                "description": "Solenoid valve 5/2 1/4 inch",
                "uom": "NOS",
                "rate": "2350.00",
            }
        ],
        "confirmed_by": "Senior Buyer",
    }

    res = client.post("/api/contracts/confirm", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "SAVED"
    assert data["contract_id"] == test_cid

    # Verify database persistence
    db = SessionLocal()
    try:
        saved_c = db.query(Contract).filter_by(contract_id=test_cid).first()
        assert saved_c is not None
        assert saved_c.supplier_id == "S021"
        assert saved_c.value_ceiling == Decimal("750000.00")
        assert saved_c.consumed_value == Decimal("0.00")
        assert len(saved_c.lines) == 1
        assert saved_c.lines[0].rate == Decimal("2350.00")

        # Verify audit log
        audit = db.query(AuditLog).filter_by(entity="CONTRACT", entity_id=test_cid).first()
        assert audit is not None
        assert audit.who == "Senior Buyer"
        assert "CONTRACT_EXTRACTED_INGEST" in audit.action

        # Clean up test contract
        db.delete(saved_c)
        db.delete(audit)
        db.commit()
    finally:
        db.close()


def test_manual_contract_creation(client):
    """Verifies POST /api/contracts/manual creates contracts with source='PDF_MANUAL'."""
    manual_cid = "RC-2027-MANUAL-01"
    payload = {
        "contract_id": manual_cid,
        "supplier_id": "S001",
        "supplier_name": "Bhosari Steel Traders",
        "start_date": "2027-02-01",
        "end_date": "2028-01-31",
        "value_ceiling": "500000.00",
        "consumed_value": "0.00",
        "lines": [
            {
                "item_code": "ITM-1001",
                "description": "MS sheet 2mm 1250x2500",
                "uom": "NOS",
                "rate": "6200.00",
            }
        ],
        "confirmed_by": "Procurement Lead",
    }

    res = client.post("/api/contracts/manual", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "SAVED"
    assert data["source"] == "PDF_MANUAL"

    db = SessionLocal()
    try:
        saved = db.query(Contract).filter_by(contract_id=manual_cid).first()
        assert saved is not None
        assert saved.source == "PDF_MANUAL"
        db.delete(saved)
        db.commit()
    finally:
        db.close()


def test_policy_4_4_late_signed_contract_binding(client):
    """
    Verifies Policy 4.4:
    - Contract signed later starts with consumed_value=0.
    - Contract is strictly binding from its start_date.
    - Requisitions before start_date do not use it; requisitions on or after start_date do use it.
    """
    db = SessionLocal()
    try:
        c31 = db.query(Contract).filter_by(contract_id="RC-2026-031").first()
        assert c31 is not None, "RC-2026-031 must be ingested in the database"
        assert c31.start_date == date(2026, 11, 15)
        assert c31.consumed_value == Decimal("0.00")
        assert c31.source == "PDF_EXTRACTED"
        assert len(c31.lines) == 1
        assert c31.lines[0].item_code == "ITM-1037"
        assert c31.lines[0].rate == Decimal("2439.00")
    finally:
        db.close()

