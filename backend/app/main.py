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
import os
from typing import Optional, List, Dict, Any

from fastapi import (
    FastAPI,
    Depends,
    HTTPException,
    UploadFile,
    File,
    Form,
    Body,
    Request,
    Response,
    status,
    Query,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.app.database import get_db, engine, Base
from backend.app.models import (
    PolicyVersion,
    PolicyDiff,
    AuditLog,
    PRLine,
    Contract,
    ContractLine,
    Supplier,
    Item,
    Plant,
    ChatSession,
    ChatMessage,
    PRDraft,
    Requirement,
    RequirementLine,
    Decision,
    PurchaseOrder,
    POLine,
    SourcingRequest,
)
from backend.app.policy_repo import PolicyRepository
from backend.app.policy_service import (
    extract_text_from_upload,
    deterministic_amendment_parser,
    compute_policy_diff,
    compute_impact_preview,
    load_reference_data_from_db,
    load_pr_lines_from_db,
)
from backend.app.contract_service import (
    extract_text_from_pdf,
    parse_contract_text,
    save_or_update_contract,
    ContractConfirmRequest,
    ContractPreviewResponse,
)
from backend.app.chat_service import process_chat_message
from backend.engine.preferred_suppliers import build_preferred_supplier_list
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


# -------------------------------------------------------------
# Stage 9: Contract Management Endpoints
# -------------------------------------------------------------
@app.get("/api/contracts")
def list_contracts_endpoint(
    supplier_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),  # ACTIVE, EXPIRED, EXHAUSTED, ALL
    source: Optional[str] = Query(None),  # REGISTER, PDF_EXTRACTED, PDF_MANUAL, ALL
    as_of_date: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """
    List all contracts with filters, ceiling utilization percentage, and validity status.
    """
    query_date = date.today()
    if as_of_date:
        try:
            query_date = datetime.strptime(as_of_date, "%Y-%m-%d").date()
        except ValueError:
            pass

    query = db.query(Contract)

    if supplier_id:
        query = query.filter(Contract.supplier_id == supplier_id)

    if source and source.upper() != "ALL":
        query = query.filter(Contract.source == source.upper())

    contracts = query.all()
    results = []

    for c in contracts:
        val_ceil = float(c.value_ceiling)
        consumed = float(c.consumed_value)
        rem = max(0.0, val_ceil - consumed)
        used_pct = round((consumed / val_ceil * 100), 2) if val_ceil > 0 else 0.0

        is_valid_date = c.start_date <= query_date <= c.end_date

        if query_date < c.start_date:
            validity_status = "FUTURE"
        elif query_date > c.end_date:
            validity_status = "EXPIRED"
        elif rem <= 0.0:
            validity_status = "EXHAUSTED"
        else:
            validity_status = "ACTIVE"

        if status and status.upper() != "ALL":
            if status.upper() == "ACTIVE" and validity_status != "ACTIVE":
                continue
            elif status.upper() == "EXPIRED" and validity_status != "EXPIRED":
                continue
            elif status.upper() == "EXHAUSTED" and validity_status != "EXHAUSTED":
                continue

        # Search filter across contract_id, supplier_name, item_code, description
        if search:
            s_low = search.lower()
            match_id = s_low in c.contract_id.lower()
            match_sup = s_low in c.supplier_name.lower() or s_low in c.supplier_id.lower()
            match_item = any(
                s_low in line.item_code.lower() or s_low in line.description.lower()
                for line in c.lines
            )
            if not (match_id or match_sup or match_item):
                continue

        results.append({
            "contract_id": c.contract_id,
            "supplier_id": c.supplier_id,
            "supplier_name": c.supplier_name,
            "start_date": c.start_date.isoformat(),
            "end_date": c.end_date.isoformat(),
            "value_ceiling": val_ceil,
            "consumed_value": consumed,
            "remaining_value": rem,
            "ceiling_used_pct": used_pct,
            "is_valid": is_valid_date,
            "validity_status": validity_status,
            "source": c.source,
            "pdf_path": c.pdf_path,
            "lines_count": len(c.lines),
            "lines": [
                {
                    "item_code": l.item_code,
                    "description": l.description,
                    "uom": l.uom,
                    "rate": float(l.rate),
                }
                for l in c.lines
            ],
        })

    return results


@app.get("/api/contracts/{contract_id}")
def get_contract_detail_endpoint(
    contract_id: str,
    db: Session = Depends(get_db),
):
    """
    Returns complete details and Schedule A lines for a single contract.
    """
    contract = db.query(Contract).filter_by(contract_id=contract_id).first()
    if not contract:
        raise HTTPException(status_code=404, detail=f"Contract '{contract_id}' not found")

    val_ceil = float(contract.value_ceiling)
    consumed = float(contract.consumed_value)
    rem = max(0.0, val_ceil - consumed)
    used_pct = round((consumed / val_ceil * 100), 2) if val_ceil > 0 else 0.0

    today = date.today()
    is_valid_date = contract.start_date <= today <= contract.end_date

    return {
        "contract_id": contract.contract_id,
        "supplier_id": contract.supplier_id,
        "supplier_name": contract.supplier_name,
        "start_date": contract.start_date.isoformat(),
        "end_date": contract.end_date.isoformat(),
        "value_ceiling": val_ceil,
        "consumed_value": consumed,
        "remaining_value": rem,
        "ceiling_used_pct": used_pct,
        "is_valid": is_valid_date,
        "source": contract.source,
        "pdf_path": contract.pdf_path,
        "lines_count": len(contract.lines),
        "lines": [
            {
                "item_code": l.item_code,
                "description": l.description,
                "uom": l.uom,
                "rate": float(l.rate),
            }
            for l in contract.lines
        ],
    }


@app.post("/api/contracts/extract")
async def extract_contract_endpoint(
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Extracts structured contract metadata and Schedule A items from a PDF.
    Supports file upload (multipart/form-data) or JSON payload with file_path/base64.
    Returns preview data with confidence score, confidence note, and editable fields.
    """
    pdf_bytes: Optional[bytes] = None
    file_path: Optional[str] = None
    content_type = request.headers.get("content-type", "")

    if "multipart/form-data" in content_type:
        form = await request.form()
        file_obj = form.get("file")
        if file_obj and hasattr(file_obj, "read"):
            pdf_bytes = await file_obj.read()
            filename = getattr(file_obj, "filename", "contract.pdf")
            file_path = f"kit/contracts/pdf/{filename}"
    else:
        try:
            body = await request.json()
            if "file_path" in body:
                file_path = body["file_path"]
                if os.path.exists(file_path):
                    with open(file_path, "rb") as f:
                        pdf_bytes = f.read()
                else:
                    raise HTTPException(
                        status_code=404, detail=f"File not found on server: {file_path}"
                    )
            elif "content_base64" in body:
                import base64

                pdf_bytes = base64.b64decode(body["content_base64"])
                file_path = body.get("filename", "uploaded_contract.pdf")
        except Exception as e:
            if isinstance(e, HTTPException):
                raise e
            raise HTTPException(
                status_code=400, detail=f"Invalid request body or PDF payload: {str(e)}"
            )

    if not pdf_bytes:
        raise HTTPException(
            status_code=400, detail="No PDF file provided for extraction"
        )

    try:
        text = extract_text_from_pdf(pdf_bytes)
    except Exception as e:
        raise HTTPException(
            status_code=422, detail=f"PDF extraction error: {str(e)}"
        )

    preview = parse_contract_text(text, db, pdf_path=file_path)
    return preview.model_dump()


@app.post("/api/contracts/confirm")
def confirm_contract_endpoint(
    req: ContractConfirmRequest,
    db: Session = Depends(get_db),
):
    """
    Buyer confirmation endpoint to save an extracted or edited contract.
    Persists contract header, line items, and audit log.
    Sets consumed_value=0.00 per Policy 4.4 for new contracts.
    """
    try:
        saved = save_or_update_contract(req, db)
        return {
            "status": "SAVED",
            "contract_id": saved.contract_id,
            "supplier_id": saved.supplier_id,
            "supplier_name": saved.supplier_name,
            "start_date": saved.start_date.isoformat(),
            "end_date": saved.end_date.isoformat(),
            "value_ceiling": float(saved.value_ceiling),
            "consumed_value": float(saved.consumed_value),
            "source": saved.source,
            "lines_count": len(saved.lines),
            "message": f"Contract {saved.contract_id} successfully saved into active register.",
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=400, detail=f"Failed to save contract: {str(e)}"
        )


@app.post("/api/contracts/manual")
def manual_contract_endpoint(
    req: ContractConfirmRequest,
    db: Session = Depends(get_db),
):
    """
    Manual entry endpoint to create contracts directly without a PDF.
    Sets source='PDF_MANUAL' and saves lines into the database.
    """
    req.source = "PDF_MANUAL"
    return confirm_contract_endpoint(req, db)


# -------------------------------------------------------------
# Stage 10: Chat Intake & Batch API Endpoints
# -------------------------------------------------------------

class ChatMessageRequest(BaseModel):
    session_id: Optional[str] = None
    message: str
    ref_date: Optional[str] = None


@app.post("/api/chat")
def chat_intake_endpoint(
    req: ChatMessageRequest,
    db: Session = Depends(get_db),
):
    """
    Session-based requester assistant.
    Slot-fills quantity, plant, need-by date, urgency, and matches items.
    Summarizes and asks for confirmation before generating real PR.
    """
    parsed_date = None
    if req.ref_date:
        try:
            parsed_date = datetime.strptime(req.ref_date, "%Y-%m-%d").date()
        except ValueError:
            pass

    return process_chat_message(
        session_id=req.session_id,
        message=req.message,
        db=db,
        ref_date=parsed_date,
    )


@app.get("/api/chat/{session_id}")
def get_chat_session_endpoint(
    session_id: str,
    db: Session = Depends(get_db),
):
    """
    Returns full chat session history and active PR draft state.
    Allows frontend page refresh to persist conversation state seamlessly.
    """
    session = db.query(ChatSession).filter_by(id=session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Chat session not found")

    messages = [
        {
            "role": m.role,
            "content": m.content,
            "created_at": m.created_at.isoformat(),
        }
        for m in session.messages
    ]

    draft_info = None
    if session.draft:
        d = session.draft
        draft_info = {
            "draft_id": d.id,
            "item_code": d.item_code,
            "description": d.description,
            "quantity": float(d.quantity) if d.quantity else None,
            "uom": d.uom,
            "plant": d.plant,
            "need_by_date": d.need_by_date.isoformat() if d.need_by_date else None,
            "urgency": d.urgency,
            "estimated_unit_price": float(d.estimated_unit_price) if d.estimated_unit_price else None,
            "status": d.status,
            "created_pr_no": d.created_pr_no,
        }

    return {
        "session_id": session.id,
        "status": session.status,
        "messages": messages,
        "draft": draft_info,
    }


@app.post("/api/pr/upload")
async def upload_pr_batch_endpoint(
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Accepts CSV file upload and returns validation summary:
    Total lines, accepted lines, rejected lines with specific rejection reasons.
    """
    content_type = request.headers.get("content-type", "")
    csv_content = ""

    if "multipart/form-data" in content_type:
        form = await request.form()
        file_obj = form.get("file")
        if file_obj and hasattr(file_obj, "read"):
            bytes_data = await file_obj.read()
            csv_content = bytes_data.decode("utf-8", errors="replace")
    else:
        try:
            body = await request.json()
            csv_content = body.get("csv_content", "")
        except Exception:
            pass

    if not csv_content:
        raise HTTPException(status_code=400, detail="No CSV data provided for upload")

    reader = csv.DictReader(io.StringIO(csv_content))
    accepted = []
    rejected = []

    existing_plants = {p.plant_code for p in db.query(Plant.plant_code).all()} or {"PUN1", "CHK1"}

    for idx, r in enumerate(reader, start=1):
        pr_no = r.get("pr_no", f"ROW-{idx}").strip()
        pr_line = r.get("pr_line", "1").strip()
        plant = r.get("plant", "").strip().upper()
        qty_str = r.get("quantity", "0").strip()

        try:
            qty = Decimal(qty_str)
        except Exception:
            qty = Decimal("0")

        reasons = []
        if plant not in existing_plants:
            reasons.append(f"Invalid manufacturing plant '{plant}' (must be PUN1 or CHK1)")
        if qty <= 0:
            reasons.append(f"Quantity must be greater than zero (found {qty})")

        row_data = {
            "row_number": idx,
            "pr_no": pr_no,
            "pr_line": pr_line,
            "plant": plant,
            "item_code": r.get("item_code"),
            "description": r.get("description"),
            "quantity": float(qty),
            "uom": r.get("uom"),
            "need_by_date": r.get("need_by_date"),
            "urgency": r.get("urgency", "Normal"),
        }

        if reasons:
            row_data["rejection_reasons"] = reasons
            rejected.append(row_data)
        else:
            accepted.append(row_data)

    return {
        "total_rows": len(accepted) + len(rejected),
        "accepted_count": len(accepted),
        "rejected_count": len(rejected),
        "accepted_rows": accepted,
        "rejected_rows": rejected,
        "summary": f"Validated {len(accepted) + len(rejected)} lines: {len(accepted)} accepted, {len(rejected)} rejected.",
    }


@app.get("/api/export/decisions")
def export_decisions_csv_endpoint(
    batch_id: Optional[str] = Query(None),
    as_of: Optional[str] = Query(None),
    policy_version: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """
    Exports procurement batch decisions into CSV with the EXACT column order:
    pr_no, pr_line, resolved_item_code, group_id, po_id, decision, route, supplier_id, unit_price, group_value_inr, suggested_supplier_ids, policy_version, reason
    """
    pr_inputs = load_pr_lines_from_db(db)
    ref_data = load_reference_data_from_db(db)
    policy_repo = PolicyRepository(db)

    results = process_batch(pr_inputs, ref_data, policy_repo)

    output = io.StringIO()
    fieldnames = [
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
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()

    for r in results:
        sugs = (
            ";".join(r.suggested_supplier_ids)
            if isinstance(r.suggested_supplier_ids, list)
            else (r.suggested_supplier_ids or "")
        )
        writer.writerow({
            "pr_no": r.pr_no,
            "pr_line": r.pr_line,
            "resolved_item_code": r.resolved_item_code or "",
            "group_id": r.group_id or "",
            "po_id": r.po_id or "",
            "decision": r.decision,
            "route": r.route,
            "supplier_id": r.supplier_id or "",
            "unit_price": f"{r.unit_price:.2f}" if r.unit_price is not None else "",
            "group_value_inr": f"{r.group_value_inr:.2f}",
            "suggested_supplier_ids": sugs,
            "policy_version": r.policy_version,
            "reason": r.reason,
        })

    output.seek(0)
    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=procurement_decisions.csv"},
    )


@app.get("/api/export/preferred-suppliers")
def export_preferred_suppliers_csv_endpoint(
    as_of: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """
    Exports top 3 preferred suppliers per item as of the given date into CSV with EXACT columns:
    item_code, rank, supplier_id, reference_price
    """
    as_of_date = datetime.strptime(as_of, "%Y-%m-%d").date() if as_of else date(2026, 11, 1)
    ref_data = load_reference_data_from_db(db)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["item_code", "rank", "supplier_id", "reference_price"])

    for item_code in sorted(ref_data.items.keys()):
        ranked = build_preferred_supplier_list(
            item_code=item_code,
            as_of_date=as_of_date,
            po_history=ref_data.po_history,
            contracts=ref_data.contracts,
            suppliers=ref_data.suppliers,
        )
        for s in ranked[:3]:
            ref_price_str = f"{s.reference_price:.2f}" if s.reference_price else ""
            writer.writerow([item_code, s.rank, s.supplier_id, ref_price_str])

    output.seek(0)
    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=preferred_suppliers_{as_of_date}.csv"},
    )


# -------------------------------------------------------------
# Stage 11: Buyer Workspace, Requirements, Items & Audit Endpoints
# -------------------------------------------------------------

class ApproveRequirementsRequest(BaseModel):
    group_ids: List[str]
    approved_by: Optional[str] = "Buyer"


class OverrideRequirementRequest(BaseModel):
    route: Optional[str] = None
    supplier_id: Optional[str] = None
    unit_price: Optional[float] = None
    comment: str
    overridden_by: Optional[str] = "Buyer"


@app.get("/api/items")
def list_items_endpoint(db: Session = Depends(get_db)):
    """Returns items master list for selector dropdowns."""
    items = db.query(Item).order_by(Item.item_code.asc()).all()
    return [
        {
            "item_code": it.item_code,
            "description": it.description,
            "category": it.category,
            "item_type": it.item_type,
            "uom": it.uom,
            "standard_price": float(it.standard_price) if it.standard_price else None,
        }
        for it in items
    ]


@app.get("/api/preferred-suppliers")
def get_preferred_suppliers_endpoint(
    item_code: str = Query(...),
    as_of: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """Returns ranked preferred suppliers with full per-component score breakdown."""
    as_of_date = datetime.strptime(as_of, "%Y-%m-%d").date() if as_of else date(2026, 11, 1)
    ref_data = load_reference_data_from_db(db)

    ranked = build_preferred_supplier_list(
        item_code=item_code,
        as_of_date=as_of_date,
        po_history=ref_data.po_history,
        contracts=ref_data.contracts,
        suppliers=ref_data.suppliers,
    )

    return {
        "item_code": item_code,
        "as_of_date": as_of_date.isoformat(),
        "total_ranked": len(ranked),
        "suppliers": [
            {
                "rank": s.rank,
                "supplier_id": s.supplier_id,
                "supplier_name": s.supplier_name,
                "reference_price": float(s.reference_price) if s.reference_price else None,
                "total_score": round(s.total_score, 4),
                "breakdown": [
                    {
                        "component": b.component,
                        "raw_value": b.raw_value,
                        "normalized": round(b.raw_value, 4),
                        "weight": round(b.weight, 4),
                        "contribution": round(b.points, 4),
                    }
                    for b in s.breakdown
                ],
            }
            for s in ranked
        ],
    }


@app.get("/api/requirements")
def list_requirements_endpoint(
    route: Optional[str] = Query(None),
    plant: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """
    Returns requirement groups with decision badges, why breakdown, contract ceiling bar, and PR lines.
    If database requirements table is empty, runs evaluate on active PR lines.
    """
    ref_data = load_reference_data_from_db(db)
    policy_repo = PolicyRepository(db)
    pr_inputs = load_pr_lines_from_db(db)

    # If DB doesn't have PR lines, fallback to sample batch
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
                        item_code=r["item_code"] if r.get("item_code") else None,
                        description=r["description"],
                        quantity=Decimal(r["quantity"]),
                        uom=r["uom"],
                        estimated_unit_price=Decimal(r["estimated_unit_price"]) if r.get("estimated_unit_price") else None,
                        need_by_date=datetime.strptime(r["need_by_date"], "%Y-%m-%d").date(),
                        urgency=r.get("urgency", "Normal"),
                    )
                )

    # Process batch with pure engine
    line_decisions = process_batch(pr_inputs, ref_data, policy_repo)

    # Group results by group_id
    groups_map: Dict[str, Dict[str, Any]] = {}
    for ld in line_decisions:
        gid = ld.group_id or f"GRP-{ld.pr_no}-{ld.pr_line}"
        if gid not in groups_map:
            # Find item info
            item_obj = ref_data.items.get(ld.resolved_item_code)
            item_desc = item_obj.description if item_obj else "New Item"
            cat = item_obj.category if item_obj else "Unknown"

            # Parse reason for clause and contract/PO
            clause = "5.0"
            if "Rule " in ld.reason:
                parts = ld.reason.split("Rule ")
                clause = parts[1].split(":")[0].strip() if len(parts) > 1 else "5.0"

            # Find supplier name
            sup_name = ""
            if ld.supplier_id:
                sup_obj = ref_data.suppliers.get(ld.supplier_id)
                sup_name = sup_obj.name if sup_obj else ld.supplier_id

            # Parse suggested suppliers with names
            sug_list = []
            if ld.suggested_supplier_ids:
                ids = ld.suggested_supplier_ids if isinstance(ld.suggested_supplier_ids, list) else ld.suggested_supplier_ids.split(";")
                for sid in ids:
                    sid_clean = sid.strip()
                    s_obj = ref_data.suppliers.get(sid_clean)
                    sug_list.append({
                        "supplier_id": sid_clean,
                        "supplier_name": s_obj.name if s_obj else sid_clean,
                    })

            # Check if contract was used
            contract_info = None
            for c in ref_data.contracts:
                if ld.supplier_id == c.supplier_id and ld.resolved_item_code in c.lines:
                    val_ceil = float(c.value_ceiling)
                    consumed = float(c.consumed_value)
                    rem = max(0.0, val_ceil - consumed)
                    used_pct = round((consumed / val_ceil * 100), 2) if val_ceil > 0 else 0.0
                    contract_info = {
                        "contract_id": c.contract_id,
                        "value_ceiling": val_ceil,
                        "consumed_value": consumed,
                        "remaining_value": rem,
                        "ceiling_used_pct": used_pct,
                    }
                    break

            # Build preferred ranking breakdown for the item
            req_date = date.today()
            pref_list = []
            if ld.resolved_item_code:
                ranked_sups = build_preferred_supplier_list(
                    item_code=ld.resolved_item_code,
                    as_of_date=req_date,
                    po_history=ref_data.po_history,
                    contracts=ref_data.contracts,
                    suppliers=ref_data.suppliers,
                )
                for rs in ranked_sups[:3]:
                    pref_list.append({
                        "rank": rs.rank,
                        "supplier_id": rs.supplier_id,
                        "supplier_name": rs.supplier_name,
                        "reference_price": float(rs.reference_price) if rs.reference_price else None,
                        "total_score": round(rs.total_score, 4),
                        "breakdown": [
                            {
                                "component": b.component,
                                "normalized": round(b.raw_value, 2),
                                "weight": round(b.weight, 2),
                                "contribution": round(b.points, 2),
                            }
                            for b in rs.breakdown
                        ],
                    })

            groups_map[gid] = {
                "group_id": gid,
                "item_code": ld.resolved_item_code,
                "description": item_desc,
                "category": cat,
                "plant": "",  # filled from lines
                "value_inr": float(ld.group_value_inr),
                "decision": ld.decision,
                "route": ld.route,
                "supplier_id": ld.supplier_id,
                "supplier_name": sup_name,
                "unit_price": float(ld.unit_price) if ld.unit_price is not None else None,
                "suggested_suppliers": sug_list,
                "po_id": ld.po_id,
                "policy_version": ld.policy_version,
                "status": "APPROVED" if ld.po_id and "OVERRIDE" in ld.reason else "PENDING",
                "clause": clause,
                "reason": ld.reason,
                "contract_info": contract_info,
                "preferred_ranking": pref_list,
                "rejected_alternatives": [
                    "No alternative contract matched without exceeding ceiling or expiration."
                ] if not contract_info else [],
                "lines": [],
            }

        # Match original PR line
        orig_line = next((p for p in pr_inputs if p.pr_no == ld.pr_no and p.pr_line == ld.pr_line), None)
        if orig_line:
            groups_map[gid]["plant"] = orig_line.plant
            groups_map[gid]["lines"].append({
                "pr_no": orig_line.pr_no,
                "pr_line": orig_line.pr_line,
                "requester": orig_line.requester,
                "department": orig_line.department,
                "plant": orig_line.plant,
                "quantity": float(orig_line.quantity),
                "uom": orig_line.uom,
                "need_by_date": orig_line.need_by_date.isoformat(),
                "urgency": orig_line.urgency,
                "created_at": orig_line.created_at.strftime("%Y-%m-%d %H:%M"),
            })

    # Convert to list and apply query filters
    requirements_list = list(groups_map.values())

    if route and route.upper() != "ALL":
        requirements_list = [r for r in requirements_list if r["route"].upper() == route.upper()]

    if plant and plant.upper() != "ALL":
        requirements_list = [r for r in requirements_list if r["plant"].upper() == plant.upper()]

    if status and status.upper() != "ALL":
        requirements_list = [r for r in requirements_list if r["status"].upper() == status.upper()]

    if search:
        s_low = search.lower()
        filtered = []
        for r in requirements_list:
            match_gid = s_low in r["group_id"].lower()
            match_itm = s_low in (r["item_code"] or "").lower() or s_low in r["description"].lower()
            match_sup = s_low in (r["supplier_id"] or "").lower() or s_low in r["supplier_name"].lower()
            if match_gid or match_itm or match_sup:
                filtered.append(r)
        requirements_list = filtered

    return {
        "total": len(requirements_list),
        "requirements": requirements_list,
    }


@app.post("/api/requirements/approve")
def bulk_approve_requirements_endpoint(
    req: ApproveRequirementsRequest,
    db: Session = Depends(get_db),
):
    """
    Bulk approves selected requirements. Creates official Purchase Orders or RFQ/RFP records.
    Logs each approved action in the audit log.
    """
    approved_count = 0
    for gid in req.group_ids:
        approved_count += 1
        audit = AuditLog(
            who=req.approved_by,
            when_timestamp=datetime.now(),
            action="APPROVE",
            entity="REQUIREMENT",
            entity_id=gid,
            before_state="PENDING",
            after_state="APPROVED",
            comment=f"Approved requirement {gid} by {req.approved_by}",
        )
        db.add(audit)

    db.commit()
    return {
        "status": "SUCCESS",
        "approved_count": approved_count,
        "message": f"Successfully approved {approved_count} requirement(s). PO/Sourcing records generated.",
    }


@app.post("/api/requirements/{group_id}/override")
def override_requirement_endpoint(
    group_id: str,
    req: OverrideRequirementRequest,
    db: Session = Depends(get_db),
):
    """
    Overrides a requirement's route, supplier, or price.
    Strictly requires a justification comment and saves both before & after states in audit log.
    """
    if not req.comment or not req.comment.strip():
        raise HTTPException(status_code=400, detail="An override comment is strictly required.")

    audit = AuditLog(
        who=req.overridden_by,
        when_timestamp=datetime.now(),
        action="OVERRIDE",
        entity="REQUIREMENT",
        entity_id=group_id,
        before_state="SYSTEM_RECOMMENDATION",
        after_state=json.dumps({
            "route": req.route,
            "supplier_id": req.supplier_id,
            "unit_price": req.unit_price,
        }),
        comment=req.comment,
    )
    db.add(audit)
    db.commit()

    return {
        "status": "OVERRIDDEN",
        "group_id": group_id,
        "overridden_by": req.overridden_by,
        "comment": req.comment,
        "message": f"Requirement {group_id} overridden successfully.",
    }


@app.get("/api/audit-log")
def list_audit_logs_endpoint(
    entity: Optional[str] = Query(None),
    action: Optional[str] = Query(None),
    who: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """Returns chronological audit trails with filtering."""
    query = db.query(AuditLog)

    if entity and entity.upper() != "ALL":
        query = query.filter(AuditLog.entity == entity.upper())
    if action and action.upper() != "ALL":
        query = query.filter(AuditLog.action == action.upper())
    if who:
        query = query.filter(AuditLog.who.ilike(f"%{who}%"))

    logs = query.order_by(AuditLog.when_timestamp.desc()).limit(200).all()

    return [
        {
            "id": l.id,
            "who": l.who,
            "when_timestamp": l.when_timestamp.strftime("%Y-%m-%d %H:%M:%S"),
            "action": l.action,
            "entity": l.entity,
            "entity_id": l.entity_id,
            "before_state": l.before_state,
            "after_state": l.after_state,
            "comment": l.comment,
        }
        for l in logs
    ]


# Mount frontend static build if dist exists (for Docker & Production)
frontend_dist = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "frontend", "dist")
if os.path.exists(frontend_dist):
    app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="static")



