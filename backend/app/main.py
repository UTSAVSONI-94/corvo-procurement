"""
backend/app/main.py

FastAPI Application for Corvo Engineering Procurement System.
Provides REST API endpoints for:
- Policy Ingestion, Parsing, Diffing, and Approval (Stage 8)
- Batch PR-to-PO Processing and Export
- Auditing and Buyer Action Workflows
"""

from datetime import datetime, date
from decimal import Decimal
import io
import json
import csv
from typing import Optional, List, Dict, Any

from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Form, Body, Request, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.app.database import get_db, engine, Base
from backend.app.models import PolicyVersion, PolicyDiff, AuditLog, PRLine
from backend.app.policy_repo import PolicyRepository
from backend.app.policy_service import (
    extract_text_from_upload,
    deterministic_amendment_parser,
    compute_policy_diff,
    compute_impact_preview,
    load_reference_data_from_db,
    load_pr_lines_from_db,
)
from backend.engine.schema import PolicyDocument
from backend.engine.types import PRLineInput, ReferenceData
from backend.engine.orchestrator import process_batch


# Initialize FastAPI app
app = FastAPI(
    title="Corvo Engineering Policy-Driven Procurement API",
    version="1.0.0",
    description="Automated, policy-driven procurement engine evaluating requisitions into POs or Sourcing Requests.",
)

@app.on_event("startup")
def on_startup():
    Base.metadata.create_all(bind=engine)

# Enable CORS for frontend Vite development server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# -------------------------------------------------------------
# Request / Response Schemas
# -------------------------------------------------------------
class IngestInstructionRequest(BaseModel):
    instruction: Optional[str] = None
    text: Optional[str] = None
    created_by: Optional[str] = "Procurement Admin"


class ApprovePolicyRequest(BaseModel):
    approved_by: Optional[str] = "Procurement Admin"
    comment: Optional[str] = "Approved after review"


class PolicyVersionSummary(BaseModel):
    id: int
    version_label: str
    effective_from: date
    status: str
    created_by: str
    created_at: datetime
    approved_by: Optional[str] = None
    approved_at: Optional[datetime] = None


# -------------------------------------------------------------
# Policy Ingestion & Management Routes (Stage 8)
# -------------------------------------------------------------
@app.post("/api/policies/ingest")
async def ingest_policy_amendment(
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Ingests an amendment document (PDF/DOCX/TXT) or natural language instruction.
    Parses amendment, validates against schema, generates plain-language diff and impact preview.
    Saves a DRAFT version in the database.
    """
    raw_text = ""
    created_by = "Procurement Admin"

    content_type = request.headers.get("content-type", "")

    if "application/json" in content_type:
        body = await request.json()
        raw_text = (body.get("instruction") or body.get("text") or "").strip()
        created_by = body.get("created_by") or created_by
    elif "multipart/form-data" in content_type or "application/x-www-form-urlencoded" in content_type:
        form = await request.form()
        uploaded_file = form.get("file")
        instruction = form.get("instruction")
        text_val = form.get("text")
        created_by = form.get("created_by") or created_by

        if uploaded_file and hasattr(uploaded_file, "read"):
            file_bytes = await uploaded_file.read()
            raw_text = extract_text_from_upload(file_bytes, uploaded_file.filename)
        elif instruction:
            raw_text = str(instruction).strip()
        elif text_val:
            raw_text = str(text_val).strip()
    else:
        # Fallback to reading raw body
        body_bytes = await request.body()
        raw_text = body_bytes.decode("utf-8", errors="replace").strip()

    if not raw_text:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No amendment content provided. Submit a document file or natural-language instruction.",
        )

    # 2. Get current active policy
    repo = PolicyRepository(db)
    try:
        current_active = repo.get_active_policy(date.today())
    except LookupError:
        # Fallback to loading standard v5.0 from policies directory
        with open("backend/policies/corvo_v5_0.json", "r", encoding="utf-8") as f:
            current_active = PolicyDocument(**json.load(f))
        repo.save_policy(current_active, created_by="System", status="ACTIVE")

    # 3. Parse amendment via parser
    proposed_policy, ambiguities = deterministic_amendment_parser(raw_text, current_active)

    # 4. Compute structural diff
    diff_res = compute_policy_diff(current_active, proposed_policy)

    # 5. Compute impact preview
    ref_data = load_reference_data_from_db(db)
    pr_inputs = load_pr_lines_from_db(db)

    # If DB doesn't have PR lines yet, load sample batch from kit
    if not pr_inputs:
        with open("kit/pr_batches/sample_pr_batch.csv", "r", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                pr_inputs.append(
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

    impact_res = compute_impact_preview(pr_inputs, ref_data, current_active, proposed_policy)

    # 6. Save as DRAFT in policy_versions table
    eff_date = proposed_policy.effective_from
    if isinstance(eff_date, str):
        eff_date = datetime.strptime(eff_date, "%Y-%m-%d").date()

    draft_record = repo.save_policy(
        policy=proposed_policy,
        created_by=created_by,
        status="DRAFT",
    )

    # 7. Record diff in policy_diffs table
    active_record = db.query(PolicyVersion).filter_by(version_label=current_active.version).first()
    old_id = active_record.id if active_record else None

    policy_diff_entry = PolicyDiff(
        old_version_id=old_id,
        new_version_id=draft_record.id,
        diff_summary=diff_res["summary"],
        changes_json=json.dumps(diff_res["changes"], default=str),
        created_at=datetime.now(),
    )
    db.add(policy_diff_entry)

    # 8. Audit log entry
    audit_entry = AuditLog(
        who=created_by,
        when_timestamp=datetime.now(),
        action="INGEST",
        entity="POLICY",
        entity_id=draft_record.version_label,
        before_state=current_active.version,
        after_state=draft_record.version_label,
        comment=f"Ingested amendment: {diff_res['summary'][:150]}",
    )
    db.add(audit_entry)
    db.commit()

    return {
        "draft_id": draft_record.id,
        "version_label": draft_record.version_label,
        "effective_from": draft_record.effective_from.isoformat(),
        "status": draft_record.status,
        "diff_summary": diff_res["summary"],
        "diff_details": diff_res["changes"],
        "impact_preview": impact_res,
        "ambiguities": ambiguities,
        "proposed_policy": proposed_policy.model_dump(),
    }


@app.post("/api/policies/{policy_id}/approve")
def approve_policy_version(
    policy_id: int,
    body: Optional[ApprovePolicyRequest] = None,
    db: Session = Depends(get_db),
):
    """
    Approves a DRAFT policy version, transitioning it to ACTIVE.
    Previous active versions remain available for requirement dates preceding effective_from.
    """
    policy = db.query(PolicyVersion).filter_by(id=policy_id).first()
    if not policy:
        raise HTTPException(status_code=404, detail=f"Policy version with id {policy_id} not found")

    if policy.status == "ACTIVE":
        return {
            "message": f"Policy {policy.version_label} is already active",
            "version": policy.version_label,
            "status": policy.status,
            "effective_from": policy.effective_from.isoformat(),
        }

    approver = body.approved_by if body and body.approved_by else "Procurement Admin"
    comment = body.comment if body and body.comment else "Approved policy amendment"

    before_state = policy.status
    policy.status = "ACTIVE"
    policy.approved_by = approver
    policy.approved_at = datetime.now()

    # Log in audit table
    audit_entry = AuditLog(
        who=approver,
        when_timestamp=datetime.now(),
        action="APPROVE",
        entity="POLICY",
        entity_id=policy.version_label,
        before_state=before_state,
        after_state="ACTIVE",
        comment=comment,
    )
    db.add(audit_entry)
    db.commit()

    return {
        "message": f"Policy version {policy.version_label} approved and activated",
        "id": policy.id,
        "version": policy.version_label,
        "status": policy.status,
        "effective_from": policy.effective_from.isoformat(),
        "approved_by": policy.approved_by,
        "approved_at": policy.approved_at.isoformat(),
    }


@app.get("/api/policies", response_model=List[PolicyVersionSummary])
def list_policy_versions(db: Session = Depends(get_db)):
    """Returns all policy versions ordered by effective date descending."""
    records = (
        db.query(PolicyVersion)
        .order_by(PolicyVersion.effective_from.desc(), PolicyVersion.id.desc())
        .all()
    )
    return [
        PolicyVersionSummary(
            id=r.id,
            version_label=r.version_label,
            effective_from=r.effective_from,
            status=r.status,
            created_by=r.created_by,
            created_at=r.created_at,
            approved_by=r.approved_by,
            approved_at=r.approved_at,
        )
        for r in records
    ]


@app.get("/api/policies/{policy_id}")
def get_policy_version_detail(policy_id: int, db: Session = Depends(get_db)):
    """Retrieves full policy document JSON and metadata for a specific version."""
    policy = db.query(PolicyVersion).filter_by(id=policy_id).first()
    if not policy:
        raise HTTPException(status_code=404, detail="Policy version not found")

    diff = (
        db.query(PolicyDiff)
        .filter_by(new_version_id=policy.id)
        .order_by(PolicyDiff.id.desc())
        .first()
    )

    return {
        "id": policy.id,
        "version_label": policy.version_label,
        "effective_from": policy.effective_from.isoformat(),
        "status": policy.status,
        "created_by": policy.created_by,
        "created_at": policy.created_at.isoformat(),
        "approved_by": policy.approved_by,
        "approved_at": policy.approved_at.isoformat() if policy.approved_at else None,
        "rules": json.loads(policy.rules_json),
        "diff_summary": diff.diff_summary if diff else None,
    }


# -------------------------------------------------------------
# Batch Processing & Export Routes
# -------------------------------------------------------------
@app.post("/api/process-batch")
async def process_batch_endpoint(
    file: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
):
    """
    Evaluates a PR batch CSV under the currently active policy versions.
    Returns line-level decisions matching Section 4 of the task brief.
    """
    pr_inputs: List[PRLineInput] = []

    if file is not None:
        content = await file.read()
        csv_text = content.decode("utf-8", errors="replace")
        reader = csv.DictReader(io.StringIO(csv_text))
        for r in reader:
            pr_inputs.append(
                PRLineInput(
                    pr_no=r["pr_no"],
                    pr_line=int(r["pr_line"]),
                    created_at=datetime.strptime(r["created_at"], "%Y-%m-%d %H:%M"),
                    requester=r.get("requester", ""),
                    department=r.get("department", ""),
                    plant=r["plant"],
                    item_code=r["item_code"] if r.get("item_code") else None,
                    description=r["description"],
                    quantity=Decimal(r["quantity"]),
                    uom=r["uom"],
                    estimated_unit_price=Decimal(r["estimated_unit_price"]) if r.get("estimated_unit_price") else None,
                    need_by_date=datetime.strptime(r["need_by_date"], "%Y-%m-%d").date(),
                    urgency=r.get("urgency", "Normal"),
                )
            )
    else:
        # Process existing database PR lines
        pr_inputs = load_pr_lines_from_db(db)

    if not pr_inputs:
        raise HTTPException(status_code=400, detail="No PR lines found to process")

    ref_data = load_reference_data_from_db(db)
    policy_repo = PolicyRepository(db)

    results = process_batch(pr_inputs, ref_data, policy_repo)

    return {
        "total_lines": len(results),
        "lines": [
            {
                "pr_no": r.pr_no,
                "pr_line": r.pr_line,
                "resolved_item_code": r.resolved_item_code,
                "group_id": r.group_id,
                "po_id": r.po_id,
                "decision": r.decision,
                "route": r.route,
                "supplier_id": r.supplier_id,
                "unit_price": float(r.unit_price) if r.unit_price is not None else None,
                "group_value_inr": float(r.group_value_inr),
                "suggested_supplier_ids": r.suggested_supplier_ids,
                "policy_version": r.policy_version,
                "reason": r.reason,
            }
            for r in results
        ],
    }
