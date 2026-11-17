"""
backend/scripts/rehearse_amendments.py

Rehearsal script for live policy amendment workflows during the blind test.
Applies amendments strictly through the real HTTP API (POST /api/policies/ingest and POST /api/policies/{id}/approve),
never by manually modifying JSON policy files.

Run via:
    python -m backend.scripts.rehearse_amendments
or with a target API base URL:
    python -m backend.scripts.rehearse_amendments http://127.0.0.1:8000
"""

import sys
import json
import httpx


def rehearse_amendments(base_url: str = "http://test"):
    print("\n" + "=" * 65)
    print("      CORVO PROCUREMENT - POLICY AMENDMENT REHEARSAL")
    print("=" * 65)

    # Use TestClient if testing in-process, or standard HTTP client if against live server
    if base_url == "http://test":
        from fastapi.testclient import TestClient
        from backend.app.main import app
        from backend.app.database import SessionLocal
        from backend.app.models import PolicyVersion, PolicyDiff

        # Reset to base v5.0 for clean repeatable rehearsal demonstration
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

        client = TestClient(app)
    else:
        client = httpx.Client(base_url=base_url)

    # -------------------------------------------------------------
    # Step 1: Rehearse Amendment A - Spot PO Limit Increase
    # -------------------------------------------------------------
    print("\n[Step 1] Ingesting Amendment A: Raise Spot PO Limit to 3 Lakh...")
    payload_a = {
        "instruction": "Raise the spot PO limit from Rs 2,00,000 to Rs 3,00,000 effective from 2026-11-01.",
        "created_by": "Rehearsal Agent",
    }
    res_a = client.post("/api/policies/ingest", json=payload_a)
    assert res_a.status_code == 200, f"Failed: {res_a.text}"
    data_a = res_a.json()

    print(f"  -> Generated Draft Version : {data_a['version_label']}")
    print(f"  -> Effective From          : {data_a['effective_from']}")
    print(f"  -> Plain-Language Diff     :\n     {data_a['diff_summary'].replace(chr(10), chr(10) + '     ')}")
    print(f"  -> Impact Preview          : {data_a['impact_preview']['changed_lines_count']} lines affected")
    for trans, count in data_a['impact_preview']['transitions'].items():
        print(f"     * {trans}: {count} lines")

    draft_id_a = data_a["draft_id"]
    app_res_a = client.post(f"/api/policies/{draft_id_a}/approve", json={"approved_by": "VP Procurement"})
    assert app_res_a.status_code == 200
    print(f"  -> APPROVED & ACTIVATED    : Version {app_res_a.json()['version']}")

    # -------------------------------------------------------------
    # Step 2: Rehearse Amendment B - Plant-Specific Override
    # -------------------------------------------------------------
    print("\n[Step 2] Ingesting Amendment B: Plant-Specific Override (PUN1 only)...")
    payload_b = {
        "instruction": "For plant PUN1 only: raise spot PO limit to 3.5 lakh effective 2026-11-01.",
        "created_by": "Rehearsal Agent",
    }
    res_b = client.post("/api/policies/ingest", json=payload_b)
    assert res_b.status_code == 200, f"Failed: {res_b.text}"
    data_b = res_b.json()

    print(f"  -> Generated Draft Version : {data_b['version_label']}")
    print(f"  -> Plain-Language Diff     :\n     {data_b['diff_summary'].replace(chr(10), chr(10) + '     ')}")
    print(f"  -> Impact Preview          : {data_b['impact_preview']['changed_lines_count']} lines affected")

    draft_id_b = data_b["draft_id"]
    app_res_b = client.post(f"/api/policies/{draft_id_b}/approve", json={"approved_by": "VP Procurement"})
    assert app_res_b.status_code == 200
    print(f"  -> APPROVED & ACTIVATED    : Version {app_res_b.json()['version']}")

    # -------------------------------------------------------------
    # Step 3: Rehearse Amendment C - Category Rule Injected Before 5.4
    # -------------------------------------------------------------
    print("\n[Step 3] Ingesting Amendment C: Category Override (Packaging mandatory RFQ)...")
    payload_c = {
        "instruction": "For category Packaging: mandatory RFQ before 5.4 effective 2026-11-01.",
        "created_by": "Rehearsal Agent",
    }
    res_c = client.post("/api/policies/ingest", json=payload_c)
    assert res_c.status_code == 200, f"Failed: {res_c.text}"
    data_c = res_c.json()

    print(f"  -> Generated Draft Version : {data_c['version_label']}")
    print(f"  -> Plain-Language Diff     :\n     {data_c['diff_summary'].replace(chr(10), chr(10) + '     ')}")
    print(f"  -> Impact Preview          : {data_c['impact_preview']['changed_lines_count']} lines affected")
    for trans, count in data_c['impact_preview']['transitions'].items():
        print(f"     * {trans}: {count} lines")

    draft_id_c = data_c["draft_id"]
    app_res_c = client.post(f"/api/policies/{draft_id_c}/approve", json={"approved_by": "VP Procurement"})
    assert app_res_c.status_code == 200
    print(f"  -> APPROVED & ACTIVATED    : Version {app_res_c.json()['version']}")

    # -------------------------------------------------------------
    # Step 4: Verify Live Batch Processing Under Latest Policy
    # -------------------------------------------------------------
    print("\n[Step 4] Running Batch Reprocessing Under Latest Active Policy...")
    batch_res = client.post("/api/process-batch")
    assert batch_res.status_code == 200
    batch_data = batch_res.json()
    print(f"  -> Reprocessed {batch_data['total_lines']} requisition lines successfully!")

    print("\n" + "=" * 65)
    print("      ALL AMENDMENT REHEARSAL STEPS PASSED SUCCESSFULLY!")
    print("=" * 65 + "\n")


if __name__ == "__main__":
    target_url = sys.argv[1] if len(sys.argv) > 1 else "http://test"
    rehearse_amendments(target_url)
