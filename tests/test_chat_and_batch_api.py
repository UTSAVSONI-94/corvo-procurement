"""
tests/test_chat_and_batch_api.py

Unit and integration tests for Stage 10:
1. POST /api/chat with 5 scripted conversations:
   - Convo 1: Complete request ("need 200 nitrile gloves for Chakan by next Friday")
   - Convo 2: Missing fields ("need MS sheet 3mm" -> prompt for qty & plant -> confirm)
   - Convo 3: Ambiguous item ("bearing" -> multiple candidates -> select code -> confirm)
   - Convo 4: Unknown / NEW item ("drone camera" -> offer NEW item with est. price -> confirm)
   - Convo 5: Emergency urgency ("urgent 50 grinding wheels for Bhosari tomorrow")
2. GET /api/chat/{session_id} state persistence on refresh.
3. POST /api/pr/upload validation summary (accepted vs rejected with reasons).
4. GET /api/export/decisions with EXACT column ordering.
5. GET /api/export/preferred-suppliers with EXACT column ordering (top 3 per item).
6. CLI processing fallback execution.
"""

import csv
from datetime import date
import io
import os
import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.database import SessionLocal
from backend.app.models import ChatSession, ChatMessage, PRDraft, PRLine
from backend.app.cli import run_process_cli


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


# -------------------------------------------------------------
# 1. Five Scripted Chat Conversations
# -------------------------------------------------------------

def test_chat_convo_1_complete_prompt_flow(client):
    """
    Conversation 1: Complete prompt.
    User: 'need 200 nitrile gloves for Chakan by next Friday'
    - Matches item ITM-1048
    - Resolves plant CHK1
    - Resolves relative date
    - Asks for confirmation
    - User confirms ('Yes') -> Creates PR and returns status line.
    """
    # Turn 1: Initial complete request
    res1 = client.post(
        "/api/chat",
        json={"message": "need 200 nitrile gloves for Chakan by next Friday", "ref_date": "2026-11-18"},
    )
    assert res1.status_code == 200
    data1 = res1.json()
    session_id = data1["session_id"]
    draft1 = data1["draft"]

    assert draft1 is not None
    assert draft1["item_code"] == "ITM-1048"
    assert draft1["quantity"] == 200.0
    assert draft1["plant"] == "CHK1"
    assert draft1["need_by_date"] == "2026-11-27"
    assert "Please confirm" in data1["reply"]

    # Turn 2: User confirms
    res2 = client.post(
        "/api/chat",
        json={"session_id": session_id, "message": "Yes, please proceed"},
    )
    assert res2.status_code == 200
    data2 = res2.json()
    assert "Purchase Requisition Created" in data2["reply"]
    assert "PR Number" in data2["reply"]
    assert data2["draft"]["status"] == "CONFIRMED"
    assert data2["draft"]["created_pr_no"] is not None


def test_chat_convo_2_missing_fields_flow(client):
    """
    Conversation 2: Missing plant and quantity.
    User: 'need MS sheet 3mm' -> Assistant asks for missing qty and plant.
    User replies: '15 sheets for Bhosari by next Friday' -> Slot fills and asks confirmation.
    User replies: 'Confirm' -> Creates PR.
    """
    # Turn 1: Incomplete request
    res1 = client.post(
        "/api/chat",
        json={"message": "need MS sheet 3mm", "ref_date": "2026-11-18"},
    )
    data1 = res1.json()
    session_id = data1["session_id"]
    assert "quantity" in data1["reply"].lower()
    assert "plant" in data1["reply"].lower()

    # Turn 2: Provide missing quantity and plant
    res2 = client.post(
        "/api/chat",
        json={"session_id": session_id, "message": "15 sheets for Bhosari by next Friday", "ref_date": "2026-11-18"},
    )
    data2 = res2.json()
    draft2 = data2["draft"]
    assert draft2["item_code"] == "ITM-1002"
    assert draft2["quantity"] == 15.0
    assert draft2["plant"] == "PUN1"
    assert "Please confirm" in data2["reply"]

    # Turn 3: User confirms
    res3 = client.post(
        "/api/chat",
        json={"session_id": session_id, "message": "Confirm and create"},
    )
    data3 = res3.json()
    assert "Purchase Requisition Created" in data3["reply"]
    assert data3["draft"]["status"] == "CONFIRMED"


def test_chat_convo_3_ambiguous_item_candidates(client):
    """
    Conversation 3: Ambiguous item query ('bearing').
    Assistant presents top candidate bearing codes.
    User selects 'ITM-1021', provides plant & date -> confirms -> PR created.
    """
    # Turn 1: Generic 'bearing' query
    res1 = client.post("/api/chat", json={"message": "I need bearing for our machines"})
    data1 = res1.json()
    session_id = data1["session_id"]
    assert "multiple matching items" in data1["reply"]
    assert "ITM-1021" in data1["reply"]
    assert "ITM-1022" in data1["reply"]

    # Turn 2: User specifies ITM-1021 with quantity, plant, and date
    res2 = client.post(
        "/api/chat",
        json={
            "session_id": session_id,
            "message": "ITM-1021, 50 units for Chakan tomorrow",
            "ref_date": "2026-11-18",
        },
    )
    data2 = res2.json()
    assert data2["draft"]["item_code"] == "ITM-1021"
    assert data2["draft"]["quantity"] == 50.0
    assert data2["draft"]["plant"] == "CHK1"
    assert "Please confirm" in data2["reply"]

    # Turn 3: Confirm
    res3 = client.post("/api/chat", json={"session_id": session_id, "message": "Yes, create it"})
    assert "Purchase Requisition Created" in res3.json()["reply"]


def test_chat_convo_4_unknown_item_creation(client):
    """
    Conversation 4: Unknown / New item ('drone camera').
    Assistant offers to create as NEW item, requesting estimated unit price.
    User provides price and details -> PR created as NEW item.
    """
    # Turn 1: Unknown item
    res1 = client.post(
        "/api/chat",
        json={"message": "special drone camera for perimeter security"},
    )
    data1 = res1.json()
    session_id = data1["session_id"]
    assert "NEW" in data1["reply"]
    assert "estimated unit price" in data1["reply"].lower()

    # Turn 2: Provide price, quantity, and plant
    res2 = client.post(
        "/api/chat",
        json={
            "session_id": session_id,
            "message": "Price ₹45000, need 2 units for Chakan by 2026-12-01",
        },
    )
    data2 = res2.json()
    assert data2["draft"]["item_code"] == "NEW"
    assert data2["draft"]["estimated_unit_price"] == 45000.0
    assert data2["draft"]["quantity"] == 2.0
    assert data2["draft"]["plant"] == "CHK1"
    assert "Please confirm" in data2["reply"]

    # Turn 3: Confirm
    res3 = client.post("/api/chat", json={"session_id": session_id, "message": "Proceed"})
    assert "Purchase Requisition Created" in res3.json()["reply"]


def test_chat_convo_5_emergency_urgency_flow(client):
    """
    Conversation 5: Emergency urgency.
    User: 'urgent 50 grinding wheels for Bhosari tomorrow'
    Assistant extracts urgency=Emergency, matches ITM-1019, asks confirmation.
    User confirms -> PR created with Emergency urgency.
    """
    res1 = client.post(
        "/api/chat",
        json={"message": "urgent 50 grinding wheels for Bhosari tomorrow", "ref_date": "2026-11-18"},
    )
    data1 = res1.json()
    session_id = data1["session_id"]
    assert data1["draft"]["item_code"] == "ITM-1019"
    assert data1["draft"]["quantity"] == 50.0
    assert data1["draft"]["plant"] == "PUN1"
    assert data1["draft"]["urgency"] == "Emergency"
    assert "Please confirm" in data1["reply"]

    res2 = client.post("/api/chat", json={"session_id": session_id, "message": "Yes, submit"})
    data2 = res2.json()
    assert "Purchase Requisition Created" in data2["reply"]


def test_chat_session_state_persistence_on_refresh(client):
    """
    Verifies GET /api/chat/{session_id}:
    - Preserves messages and current draft slots across page refreshes.
    """
    # Start a turn
    res = client.post("/api/chat", json={"message": "need 100 cotton gloves for PUN1"})
    session_id = res.json()["session_id"]

    # Simulate page refresh
    get_res = client.get(f"/api/chat/{session_id}")
    assert get_res.status_code == 200
    state = get_res.json()
    assert state["session_id"] == session_id
    assert len(state["messages"]) >= 2
    assert state["draft"]["quantity"] == 100.0
    assert state["draft"]["plant"] == "PUN1"


# -------------------------------------------------------------
# 2. PR Batch CSV Upload & Validation Summary
# -------------------------------------------------------------

def test_pr_batch_upload_validation_summary(client):
    """
    Verifies POST /api/pr/upload:
    - Accepts CSV format.
    - Validates lines and flags rows with non-positive qty or invalid plant (e.g. PUN2).
    - Returns summary table of accepted vs rejected rows with reasons.
    """
    csv_sample = """pr_no,pr_line,created_at,requester,department,plant,item_code,description,quantity,uom,need_by_date,urgency
PR-26-TEST01,1,2026-11-02 09:30,John,Eng,PUN1,ITM-1001,MS sheet 2mm,10,NOS,2026-11-20,Normal
PR-26-TEST02,1,2026-11-02 09:35,Jane,Ops,PUN2,ITM-1002,MS sheet 3mm,5,NOS,2026-11-20,Normal
PR-26-TEST03,1,2026-11-02 09:40,Bob,Maint,CHK1,ITM-1021,Bearing,0,NOS,2026-11-20,Normal
"""
    res = client.post(
        "/api/pr/upload",
        json={"csv_content": csv_sample},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["total_rows"] == 3
    assert data["accepted_count"] == 1
    assert data["rejected_count"] == 2

    # Check rejection reasons
    rejections = {r["pr_no"]: r["rejection_reasons"] for r in data["rejected_rows"]}
    assert any("PUN2" in reason for reason in rejections["PR-26-TEST02"])
    assert any("greater than zero" in reason for reason in rejections["PR-26-TEST03"])


# -------------------------------------------------------------
# 3. Export Endpoints (Exact Header and Columns)
# -------------------------------------------------------------

def test_export_decisions_csv_exact_headers(client):
    """
    Verifies GET /api/export/decisions:
    - Returns CSV with exact column order:
      pr_no, pr_line, resolved_item_code, group_id, po_id, decision, route, supplier_id, unit_price, group_value_inr, suggested_supplier_ids, policy_version, reason
    """
    res = client.get("/api/export/decisions")
    assert res.status_code == 200
    assert "text/csv" in res.headers["content-type"]

    csv_reader = csv.reader(io.StringIO(res.text))
    header = next(csv_reader)
    expected_header = [
        "pr_no",
        "pr_line",
        "resolved_item_code",
        "group_id",
        "po_id",
        "decision",
        "route",
        "supplier_id",
        "unit_price",
        "group_value_inr",
        "suggested_supplier_ids",
        "policy_version",
        "reason",
    ]
    assert header == expected_header
    rows = list(csv_reader)
    assert len(rows) >= 180


def test_export_preferred_suppliers_csv_exact_headers(client):
    """
    Verifies GET /api/export/preferred-suppliers?as_of=2026-11-01:
    - Returns CSV with exact column order:
      item_code, rank, supplier_id, reference_price
    - Lists top 3 preferred suppliers per item.
    """
    res = client.get("/api/export/preferred-suppliers?as_of=2026-11-01")
    assert res.status_code == 200
    assert "text/csv" in res.headers["content-type"]

    csv_reader = csv.reader(io.StringIO(res.text))
    header = next(csv_reader)
    assert header == ["item_code", "rank", "supplier_id", "reference_price"]
    rows = list(csv_reader)
    assert len(rows) > 0
    # Every row must have rank in ('1', '2', '3')
    assert all(r[1] in ("1", "2", "3") for r in rows)


def test_cli_process_execution(tmp_path):
    """Verifies that the CLI process subcommand produces the expected output CSV."""
    out_csv = tmp_path / "cli_decisions_out.csv"
    run_process_cli(
        input_path="kit/pr_batches/sample_pr_batch.csv",
        output_path=str(out_csv),
    )
    assert os.path.exists(out_csv)
    with open(out_csv, "r", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader)
        assert header[0] == "pr_no"
        rows = list(reader)
        assert len(rows) == 186
