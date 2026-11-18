"""
backend/app/contract_service.py

Contract Management and PDF Extraction Service for Corvo Engineering:
1. Multi-strategy PDF text extraction (pdfplumber, pypdf, OCR fallback).
2. Deterministic & structured extraction of contract header, supplier, dates, ceiling, and line items.
3. Supplier and Item Master matching and normalization.
4. Preview generation with confidence scoring and ambiguity detection.
5. Ingestion & Confirmation workflow (PDF_EXTRACTED / PDF_MANUAL).
"""

from datetime import date, datetime
from decimal import Decimal
import io
import os
import re
from typing import Any, Dict, List, Optional, Tuple, Union

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.app.models import Contract, ContractLine, Supplier, Item, AuditLog


class ContractLinePreview(BaseModel):
    item_code: str
    description: str
    uom: str
    rate: Decimal


class ContractPreviewResponse(BaseModel):
    contract_id: str
    supplier_id: str
    supplier_name: str
    start_date: str
    end_date: str
    value_ceiling: Decimal
    consumed_value: Decimal = Decimal("0.00")
    source: str = "PDF_EXTRACTED"
    pdf_path: Optional[str] = None
    lines: List[ContractLinePreview]
    confidence_score: float = 1.0
    confidence_note: str = ""
    ambiguities: List[str] = []


class ContractConfirmRequest(BaseModel):
    contract_id: str
    supplier_id: str
    supplier_name: str
    start_date: date
    end_date: date
    value_ceiling: Decimal
    consumed_value: Decimal = Decimal("0.00")
    source: str = "PDF_EXTRACTED"  # PDF_EXTRACTED or PDF_MANUAL
    pdf_path: Optional[str] = None
    lines: List[ContractLinePreview]
    confirmed_by: str = "Buyer"


class ContractDetailResponse(BaseModel):
    contract_id: str
    supplier_id: str
    supplier_name: str
    start_date: str
    end_date: str
    value_ceiling: float
    consumed_value: float
    remaining_value: float
    ceiling_used_pct: float
    is_valid: bool
    validity_status: str
    source: str
    pdf_path: Optional[str]
    lines_count: int
    lines: List[Dict[str, Any]] = []


def extract_text_from_pdf(file_source: Union[bytes, str]) -> str:
    """
    Extracts text from a PDF given file bytes or a file path.
    Tries pdfplumber if installed, then pypdf.
    Falls back to simple regex scan or OCR notice if scanned.
    """
    # 1. Try pdfplumber
    try:
        import pdfplumber

        if isinstance(file_source, bytes):
            with pdfplumber.open(io.BytesIO(file_source)) as pdf:
                text = "\n".join(page.extract_text() or "" for page in pdf.pages)
        else:
            with pdfplumber.open(file_source) as pdf:
                text = "\n".join(page.extract_text() or "" for page in pdf.pages)
        if len(text.strip()) > 30:
            return text
    except Exception:
        pass

    # 2. Try pypdf
    try:
        import pypdf

        if isinstance(file_source, bytes):
            reader = pypdf.PdfReader(io.BytesIO(file_source))
        else:
            reader = pypdf.PdfReader(file_source)
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
        if len(text.strip()) > 30:
            return text
    except Exception:
        pass

    # 3. Fallback: inspect raw bytes for ASCII text streams if scanned/uncompressed
    raw_bytes = file_source if isinstance(file_source, bytes) else open(file_source, "rb").read()
    ascii_matches = re.findall(rb"\((.*?)\)\s*['Tj]", raw_bytes)
    if ascii_matches:
        recovered = "\n".join(m.decode("latin1", errors="ignore") for m in ascii_matches)
        if len(recovered.strip()) > 30:
            return recovered

    raise ValueError("Unable to extract text from PDF. The document may be a scanned image requiring OCR.")


def parse_contract_text(
    text: str,
    db: Session,
    pdf_path: Optional[str] = None,
) -> ContractPreviewResponse:
    """
    Parses contract text into structured contract header and line items.
    Cross-checks suppliers and items against the database master records.
    Computes confidence score and ambiguity warnings.
    """
    ambiguities: List[str] = []
    confidence = 1.0

    # 1. Extract Contract ID (e.g. RC-2026-031, Contract No. RC-2025-011)
    cid_match = re.search(r"\b(RC-\d{4}-\d{3})\b", text)
    if not cid_match:
        cid_match = re.search(r"Contract\s+(?:No\.?|Number)?\s*[:\s]*([A-Z0-9-]+)", text, re.IGNORECASE)
    contract_id = cid_match.group(1).strip() if cid_match else "UNKNOWN-CONTRACT"
    if contract_id == "UNKNOWN-CONTRACT":
        confidence -= 0.3
        ambiguities.append("Could not locate standard Rate Contract ID (e.g. RC-YYYY-NNN).")

    # 2. Extract Supplier Name & Supplier ID
    # Pattern 1: and <Supplier Name>, <City> (Supplier ID <ID>)
    sup_match = re.search(r"and\s+(.*?)(?:,\s*[A-Za-z\s]+)?\s*\(Supplier\s+ID\s+([A-Z0-9]+)\)", text, re.IGNORECASE)
    supplier_id = None
    supplier_name = None

    if sup_match:
        supplier_name = sup_match.group(1).strip().strip('"').strip("'")
        supplier_id = sup_match.group(2).strip()
    else:
        # Pattern 2: Supplier ID S021
        id_match = re.search(r"Supplier\s+ID[:\s]*([A-Z0-9]+)", text, re.IGNORECASE)
        if id_match:
            supplier_id = id_match.group(1).strip()

    # Validate or lookup supplier in DB
    all_suppliers = db.query(Supplier).all()
    sup_by_id = {s.supplier_id: s for s in all_suppliers}
    sup_by_name = {s.name.lower(): s for s in all_suppliers}

    if supplier_id and supplier_id in sup_by_id:
        supplier_name = sup_by_id[supplier_id].name
    elif supplier_name:
        matched_sup = sup_by_name.get(supplier_name.lower())
        if matched_sup:
            supplier_id = matched_sup.supplier_id
            supplier_name = matched_sup.name
        else:
            # Fuzzy match supplier name
            for s in all_suppliers:
                if s.name.lower() in supplier_name.lower() or supplier_name.lower() in s.name.lower():
                    supplier_id = s.supplier_id
                    supplier_name = s.name
                    break

    if not supplier_id:
        supplier_id = "UNKNOWN"
        supplier_name = supplier_name or "Unknown Supplier"
        confidence -= 0.3
        ambiguities.append("Supplier could not be resolved to an active supplier master record.")

    # 3. Extract Validity Dates
    # e.g. "valid from 2026-11-15 to 2027-11-14"
    term_match = re.search(
        r"valid\s+from\s+(\d{4}-\d{2}-\d{2})\s+to\s+(\d{4}-\d{2}-\d{2})",
        text,
        re.IGNORECASE,
    )
    if term_match:
        start_date = term_match.group(1)
        end_date = term_match.group(2)
    else:
        # Fallback date search
        dates = re.findall(r"\b(\d{4}-\d{2}-\d{2})\b", text)
        if len(dates) >= 2:
            start_date = dates[0]
            end_date = dates[1]
            ambiguities.append(f"Inferred contract dates {start_date} to {end_date} from document body.")
            confidence -= 0.1
        else:
            start_date = date.today().isoformat()
            end_date = (date.today().replace(year=date.today().year + 1)).isoformat()
            confidence -= 0.3
            ambiguities.append("Missing validity dates; defaulted to 1 year from today.")

    # 4. Extract Value Ceiling
    # e.g. "shall not exceed INR 10,00,000" or "INR 35,00,000" or "1000000"
    ceil_match = re.search(r"(?:not\s+exceed|ceiling\s+of)?\s*INR\s+([\d,]+(?:\.\d+)?)", text, re.IGNORECASE)
    if not ceil_match:
        ceil_match = re.search(r"Value\s+ceiling.*?INR\s*([\d,]+)", text, re.IGNORECASE | re.DOTALL)

    if ceil_match:
        clean_ceil = ceil_match.group(1).replace(",", "").strip()
        try:
            value_ceiling = Decimal(clean_ceil)
        except Exception:
            value_ceiling = Decimal("1000000.00")
            confidence -= 0.2
            ambiguities.append("Error parsing ceiling value; default applied.")
    else:
        value_ceiling = Decimal("1000000.00")
        confidence -= 0.25
        ambiguities.append("Value ceiling not found; default ₹10,00,000.00 applied.")

    # 5. Extract Schedule A Items and Rates
    lines: List[ContractLinePreview] = []
    sched_part = text
    if "Schedule A" in text:
        sched_part = text.split("Schedule A")[-1]

    # Pre-index item master for code/description resolution
    items_by_code = {item.item_code: item for item in db.query(Item).all()}

    # Match rows like: "1 ITM-1037 Solenoid valve 5/2 1/4 inch NOS 2,439.00"
    # or "1 ITM-1006 Aluminium plate 6061 10mm KG 329.54"
    row_pattern = re.compile(
        r"^\s*(?:\d+\s+)?(ITM-\d+)\s+(.*?)\s+([A-Z]{2,5})\s+([\d,]+\.?\d*)",
        re.MULTILINE,
    )

    for m in row_pattern.finditer(sched_part):
        item_code = m.group(1).strip()
        desc = m.group(2).strip()
        uom = m.group(3).strip()
        rate_val = Decimal(m.group(4).replace(",", "").strip())

        # If description is empty or short, take from item master
        if item_code in items_by_code:
            master_item = items_by_code[item_code]
            if not desc or len(desc) < 3:
                desc = master_item.description
            if not uom:
                uom = master_item.uom

        lines.append(
            ContractLinePreview(
                item_code=item_code,
                description=desc,
                uom=uom,
                rate=rate_val,
            )
        )

    # If no lines found with standard pattern, attempt line-by-line fallback
    if not lines:
        for raw_line in sched_part.split("\n"):
            line_clean = raw_line.strip()
            item_code_m = re.search(r"\b(ITM-\d+)\b", line_clean)
            rate_m = re.search(r"([\d,]+\.\d{2})", line_clean)
            if item_code_m and rate_m:
                item_code = item_code_m.group(1)
                rate_val = Decimal(rate_m.group(1).replace(",", ""))
                item_rec = items_by_code.get(item_code)
                desc = item_rec.description if item_rec else "Contract Line Item"
                uom = item_rec.uom if item_rec else "NOS"
                lines.append(
                    ContractLinePreview(
                        item_code=item_code,
                        description=desc,
                        uom=uom,
                        rate=rate_val,
                    )
                )

    if not lines:
        confidence -= 0.4
        ambiguities.append("No line items or rates could be parsed from Schedule A.")

    confidence = max(0.1, min(1.0, round(confidence, 2)))
    note = (
        f"Extracted contract {contract_id} with {len(lines)} line item(s) from supplier "
        f"{supplier_id} ({supplier_name}). Confidence: {int(confidence * 100)}%."
    )

    return ContractPreviewResponse(
        contract_id=contract_id,
        supplier_id=supplier_id,
        supplier_name=supplier_name,
        start_date=start_date,
        end_date=end_date,
        value_ceiling=value_ceiling,
        consumed_value=Decimal("0.00"),
        source="PDF_EXTRACTED",
        pdf_path=pdf_path,
        lines=lines,
        confidence_score=confidence,
        confidence_note=note,
        ambiguities=ambiguities,
    )


def save_or_update_contract(
    req: ContractConfirmRequest,
    db: Session,
) -> Contract:
    """
    Saves or updates a contract and its line items in the database.
    Per Policy 4.4, new PDF contracts start with consumed_value=0.
    """
    contract = db.query(Contract).filter_by(contract_id=req.contract_id).first()
    is_new = contract is None

    if is_new:
        contract = Contract(
            contract_id=req.contract_id,
            supplier_id=req.supplier_id,
            supplier_name=req.supplier_name,
            start_date=req.start_date,
            end_date=req.end_date,
            value_ceiling=req.value_ceiling,
            consumed_value=req.consumed_value,
            source=req.source,
            pdf_path=req.pdf_path,
        )
        db.add(contract)
    else:
        contract.supplier_id = req.supplier_id
        contract.supplier_name = req.supplier_name
        contract.start_date = req.start_date
        contract.end_date = req.end_date
        contract.value_ceiling = req.value_ceiling
        contract.consumed_value = req.consumed_value
        contract.source = req.source
        if req.pdf_path:
            contract.pdf_path = req.pdf_path

        # Delete existing lines to replace cleanly
        db.query(ContractLine).filter_by(contract_id=req.contract_id).delete()

    db.flush()

    for line in req.lines:
        c_line = ContractLine(
            contract_id=req.contract_id,
            item_code=line.item_code,
            description=line.description,
            uom=line.uom,
            rate=line.rate,
        )
        db.add(c_line)

    # Log audit entry
    action_type = "CONTRACT_EXTRACTED_INGEST" if req.source == "PDF_EXTRACTED" else "CONTRACT_MANUAL_CREATE"
    audit = AuditLog(
        who=req.confirmed_by,
        action=action_type,
        entity="CONTRACT",
        entity_id=req.contract_id,
        before_state=None if is_new else f"Existing contract {req.contract_id}",
        after_state=f"Saved contract {req.contract_id} with {len(req.lines)} lines, ceiling ₹{req.value_ceiling:,.2f}",
        comment=f"Source: {req.source}, Validity: {req.start_date} to {req.end_date}",
    )
    db.add(audit)
    db.commit()
    db.refresh(contract)
    return contract
