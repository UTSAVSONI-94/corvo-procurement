"""
backend/app/policy_service.py

Policy management service implementing:
1. Ingestion of policy amendments from PDF, DOCX, TXT or natural-language instructions.
2. Structured amendment extraction via LLM or deterministic fallback parser.
3. Plain-language structural diffing between policy versions.
4. Batch impact preview simulating route transitions before activation.
5. Version lifecycle management (DRAFT -> ACTIVE) with audit logging.
"""

from datetime import date, datetime, timedelta
from decimal import Decimal
import io
import json
import os
import re
import zipfile
import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Optional, Tuple, Union

from pydantic import ValidationError
from pypdf import PdfReader
from sqlalchemy.orm import Session

from backend.app.models import PolicyVersion, PolicyDiff, AuditLog, PRLine, Item, Supplier, Contract, ContractLine, POHistory
from backend.engine.schema import PolicyDocument, DecisionRule, RuleOutcome, Condition
from backend.engine.types import (
    PRLineInput,
    ItemMasterRecord,
    SupplierRecord,
    ContractRecord,
    ContractLineRecord,
    POHistoryRecord,
    ReferenceData,
)
from backend.engine.orchestrator import process_batch


def extract_text_from_upload(content: bytes, filename: str) -> str:
    """Extracts raw text from uploaded PDF, DOCX, or text documents."""
    fname_lower = filename.lower()

    if fname_lower.endswith(".pdf"):
        reader = PdfReader(io.BytesIO(content))
        pages_text = [page.extract_text() or "" for page in reader.pages]
        return "\n".join(pages_text).strip()

    if fname_lower.endswith(".docx"):
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as z:
                xml_content = z.read("word/document.xml")
                root = ET.fromstring(xml_content)
                # Word namespace
                ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
                paragraphs = []
                for p in root.findall(".//w:p", ns):
                    texts = [t.text for t in p.findall(".//w:t", ns) if t.text]
                    if texts:
                        paragraphs.append("".join(texts))
                return "\n".join(paragraphs).strip()
        except Exception as e:
            return f"Error extracting DOCX text: {e}"

    # Default to UTF-8 plain text
    try:
        return content.decode("utf-8").strip()
    except UnicodeDecodeError:
        return content.decode("latin-1", errors="replace").strip()


def parse_lakh_amount(text: str) -> Optional[Decimal]:
    """Parses expressions like '3 lakh', '3,00,000', '300000', 'to Rs 3,00,000' into Decimal."""
    # If "to <amount>" exists (e.g. "from 2 lakh to 3 lakh" or "from Rs 2,00,000 to Rs 3,00,000"), extract target
    to_match = re.search(
        r"\bto\s+(?:rs\.?|inr|₹)?\s*([0-9.,\s]+(?:lakhs?|lakh)?)(?:\s+effective|\.|\s*$|\s+for)",
        text,
        re.IGNORECASE,
    )
    if to_match:
        eval_text = to_match.group(1).strip()
    else:
        to_broad = re.search(r"\bto\s+(.+?)(?:effective|\.|$)", text, re.IGNORECASE)
        eval_text = to_broad.group(1).strip() if to_broad else text

    # Pattern 1: e.g. "3 lakh", "2.5 lakh", "10 lakhs"
    lakh_match = re.search(r"(\d+(?:\.\d+)?)\s*lakh", eval_text, re.IGNORECASE)
    if not lakh_match and eval_text != text:
        lakh_match = re.search(r"(\d+(?:\.\d+)?)\s*lakh", text, re.IGNORECASE)
    if lakh_match:
        val = float(lakh_match.group(1)) * 100000
        return Decimal(str(int(val)))

    # Pattern 2: e.g. "3,00,000", "200000", "500,000" (support both Indian and Western comma groupings)
    num_match = re.search(r"(?:rs\.?|inr|₹)?\s*([\d,]+(?:\.\d+)?)", eval_text, re.IGNORECASE)
    if num_match:
        clean_num = num_match.group(1).replace(",", "").strip()
        if clean_num:
            try:
                return Decimal(clean_num)
            except Exception:
                pass
    return None


def extract_effective_date(text: str, default_date: Optional[date] = None) -> date:
    """Extracts effective date from text (e.g. 'effective from 2026-11-15'), defaulting to tomorrow."""
    date_match = re.search(r"effective\s+(?:from|date|as of)?[:\s]*(\d{4}-\d{2}-\d{2})", text, re.IGNORECASE)
    if date_match:
        try:
            return datetime.strptime(date_match.group(1), "%Y-%m-%d").date()
        except ValueError:
            pass

    # Generic YYYY-MM-DD
    generic_match = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", text)
    if generic_match:
        try:
            return datetime.strptime(generic_match.group(1), "%Y-%m-%d").date()
        except ValueError:
            pass

    return default_date or (date.today() + timedelta(days=1))


def deterministic_amendment_parser(
    text: str,
    current_policy: PolicyDocument,
) -> Tuple[PolicyDocument, List[str]]:
    """
    Robust deterministic parser for amendments when LLM is unavailable or for local testing.
    Handles:
    - JSON Patch or full JSON embeddings
    - Spot PO limit changes (global or plant-specific)
    - Emergency limit changes
    - RFP threshold changes
    - Category-specific rules inserted before 5.4
    - Plant-specific overrides (e.g. for CHK1 only)
    """
    ambiguities: List[str] = []
    text_clean = text.strip()

    # 1. Direct JSON check
    if text_clean.startswith("{") and text_clean.endswith("}"):
        try:
            data = json.loads(text_clean)
            if "version" in data and "decision_rules" in data:
                return PolicyDocument(**data), []
        except Exception:
            pass

    # Clone current policy dict for mutation
    p_dict = current_policy.model_dump()
    eff_date = extract_effective_date(text_clean)
    p_dict["effective_from"] = eff_date.isoformat()

    # Increment minor version label: e.g. v5.0 -> v5.1
    curr_ver = str(p_dict.get("version", "5.0")).lstrip("v")
    parts = curr_ver.split(".")
    if len(parts) >= 2:
        try:
            next_minor = int(parts[1]) + 1
            p_dict["version"] = f"v{parts[0]}.{next_minor}"
        except ValueError:
            p_dict["version"] = f"v{curr_ver}.1"
    else:
        p_dict["version"] = f"v{curr_ver}.1"

    # 2. Check for plant-specific rule (e.g. "for CHK1 only", "for plant PUN1")
    plant_match = re.search(r"\b(?:for\s+plant|for)\s+(PUN1|CHK1)\b", text_clean, re.IGNORECASE)
    is_plant_specific = plant_match is not None
    target_plant = plant_match.group(1).upper() if is_plant_specific else None

    # 3. Check for category-specific rule (e.g. "category Packaging", "for category Steel & Metals")
    cat_match = re.search(r"\bcategory\s+([A-Za-z0-9 &]+?)(?:\s+before|\s+only|\s+goes|\s*:|$)", text_clean, re.IGNORECASE)

    # 4. Spot PO Limit Modifications
    if "spot" in text_clean.lower() and ("limit" in text_clean.lower() or "raise" in text_clean.lower() or "change" in text_clean.lower()):
        new_limit = parse_lakh_amount(text_clean)
        if new_limit is not None:
            if is_plant_specific and target_plant:
                # Add a plant-specific spot PO override rule inserted BEFORE Rule 5.4
                rule_id = f"5.4_{target_plant.lower()}"
                new_rule = {
                    "id": rule_id,
                    "clause": f"Clause 5.4 ({target_plant} Override)",
                    "name": f"Spot Purchase Order ({target_plant})",
                    "description": f"Spot PO limit for plant {target_plant} raised to INR {new_limit:,.2f}.",
                    "when": {
                        "all": [
                          {"field": "plant", "op": "eq", "value": target_plant},
                          {"field": "value", "op": "lt", "value": float(new_limit)},
                          {"field": "has_active_supplier_purchase_365d", "op": "eq", "value": True}
                        ]
                    },
                    "outcome": {
                        "decision": "PO",
                        "route": "SPOT_PO",
                        "supplier_mode": "PREFERRED_1",
                        "suggest_count": None,
                        "price_mode": "REFERENCE_PRICE",
                        "needs_approval": False,
                        "notes": f"Plant {target_plant} spot limit override at INR {new_limit:,.2f}"
                    }
                }
                # Insert right before rule 5.4 (or spot PO rule)
                rules = p_dict.get("decision_rules", [])
                insert_idx = len(rules)
                for idx, r in enumerate(rules):
                    if r.get("id") == "5.4" or r.get("route") == "SPOT_PO":
                        insert_idx = idx
                        break
                rules.insert(insert_idx, new_rule)
                p_dict["decision_rules"] = rules
            else:
                # Global spot limit change
                p_dict["thresholds"]["spot_limit"] = float(new_limit)

    # 5. Emergency Limit Modifications
    if "emergency" in text_clean.lower() and ("limit" in text_clean.lower() or "raise" in text_clean.lower() or "change" in text_clean.lower()):
        new_limit = parse_lakh_amount(text_clean)
        if new_limit is not None:
            p_dict["thresholds"]["emergency_limit"] = float(new_limit)

    # 6. RFP Threshold Modifications
    if "rfp" in text_clean.lower() and ("threshold" in text_clean.lower() or "limit" in text_clean.lower() or "raise" in text_clean.lower()):
        new_limit = parse_lakh_amount(text_clean)
        if new_limit is not None:
            p_dict["thresholds"]["rfp_threshold"] = float(new_limit)

    # 7. Category Rule insertion
    if cat_match:
        category_name = cat_match.group(1).strip()
        rule_id = f"cat_{category_name.lower().replace(' ', '_')}"
        new_cat_rule = {
            "id": rule_id,
            "clause": f"Clause Category Override ({category_name})",
            "name": f"Category Rule ({category_name})",
            "description": f"Mandatory RFQ for category {category_name}.",
            "when": {
                "all": [
                  {"field": "category", "op": "eq", "value": category_name},
                  {"field": "value", "op": "lt", "value": 1000000.00}
                ]
            },
            "outcome": {
                "decision": "SOURCING_REQUEST",
                "route": "RFQ",
                "supplier_mode": "SUGGEST_N",
                "suggest_count": 3,
                "price_mode": "REFERENCE_PRICE",
                "needs_approval": False,
                "notes": f"Mandatory quotes for {category_name}"
            }
        }
        # Insert before rule 5.4
        rules = p_dict.get("decision_rules", [])
        insert_idx = len(rules)
        for idx, r in enumerate(rules):
            if r.get("id") == "5.4" or "spot" in r.get("name", "").lower():
                insert_idx = idx
                break
        rules.insert(insert_idx, new_cat_rule)
        p_dict["decision_rules"] = rules

    # Parse and validate with Pydantic
    try:
        new_policy = PolicyDocument(**p_dict)
        return new_policy, ambiguities
    except ValidationError as e:
        ambiguities.append(f"Validation error in parsed policy: {e}")
        return current_policy, ambiguities


def compute_policy_diff(old_policy: PolicyDocument, new_policy: PolicyDocument) -> Dict[str, Any]:
    """
    Computes a structural diff and renders plain-language summaries of changes.
    """
    diff_lines: List[str] = []
    changes: Dict[str, Any] = {
        "version": {"old": old_policy.version, "new": new_policy.version},
        "effective_from": {"old": str(old_policy.effective_from), "new": str(new_policy.effective_from)},
        "thresholds": {},
        "parameters": {},
        "rules_added": [],
        "rules_modified": [],
        "rules_removed": [],
        "rule_order_changed": False,
    }

    # 1. Version and Effective Date
    if old_policy.version != new_policy.version:
        diff_lines.append(f"Version updated from {old_policy.version} to {new_policy.version}.")
    if old_policy.effective_from != new_policy.effective_from:
        diff_lines.append(f"Effective date set to {new_policy.effective_from} (previously {old_policy.effective_from}).")

    # 2. Thresholds
    old_th = old_policy.thresholds.model_dump()
    new_th = new_policy.thresholds.model_dump()
    for k, v in new_th.items():
        if k in old_th and old_th[k] != v:
            changes["thresholds"][k] = {"old": old_th[k], "new": v}
            diff_lines.append(f"Threshold '{k}' changed from ₹{old_th[k]:,.2f} to ₹{v:,.2f}.")
        elif k not in old_th:
            changes["thresholds"][k] = {"old": None, "new": v}
            diff_lines.append(f"New threshold '{k}' added: ₹{v:,.2f}.")

    # 3. Parameters
    old_params = old_policy.parameters.model_dump()
    new_params = new_policy.parameters.model_dump()
    for k, v in new_params.items():
        if k in old_params and old_params[k] != v:
            changes["parameters"][k] = {"old": old_params[k], "new": v}
            diff_lines.append(f"Parameter '{k}' changed from {old_params[k]} to {v}.")

    # 4. Decision Rules
    old_rules_by_id = {r.id: r for r in old_policy.decision_rules}
    new_rules_by_id = {r.id: r for r in new_policy.decision_rules}

    # Added rules
    for r in new_policy.decision_rules:
        if r.id not in old_rules_by_id:
            changes["rules_added"].append(r.model_dump())
            diff_lines.append(f"New rule added: '{r.name}' ({r.clause}) - {r.description}")

    # Removed rules
    for r in old_policy.decision_rules:
        if r.id not in new_rules_by_id:
            changes["rules_removed"].append(r.model_dump())
            diff_lines.append(f"Rule removed: '{r.name}' ({r.clause})")

    # Modified rules
    for r in new_policy.decision_rules:
        if r.id in old_rules_by_id:
            old_r = old_rules_by_id[r.id]
            if old_r.model_dump() != r.model_dump():
                changes["rules_modified"].append({"id": r.id, "old": old_r.model_dump(), "new": r.model_dump()})
                diff_lines.append(f"Rule '{r.name}' ({r.clause}) conditions/outcomes modified.")

    # Check rule order changes
    old_ids = [r.id for r in old_policy.decision_rules if r.id in new_rules_by_id]
    new_ids = [r.id for r in new_policy.decision_rules if r.id in old_rules_by_id]
    if old_ids != new_ids:
        changes["rule_order_changed"] = True
        diff_lines.append("Decision rule evaluation order was reordered.")

    summary_text = "\n".join(diff_lines) if diff_lines else "No functional changes detected."

    return {
        "summary": summary_text,
        "changes": changes,
        "diff_lines": diff_lines,
    }


def compute_impact_preview(
    pr_lines: List[PRLineInput],
    reference_data: ReferenceData,
    current_policy: PolicyDocument,
    proposed_policy: PolicyDocument,
) -> Dict[str, Any]:
    """
    Simulates reprocessing the batch under both current and proposed policies,
    reporting lines that shift routes, suppliers, or decisions.
    """
    old_results = process_batch(pr_lines, reference_data, current_policy)
    new_results = process_batch(pr_lines, reference_data, proposed_policy)

    transitions: Dict[str, int] = {}
    impacted_lines: List[Dict[str, Any]] = []

    for old_r, new_r in zip(old_results, new_results):
        if old_r.route != new_r.route or old_r.decision != new_r.decision or old_r.supplier_id != new_r.supplier_id:
            trans_key = f"{old_r.route} -> {new_r.route}"
            transitions[trans_key] = transitions.get(trans_key, 0) + 1
            impacted_lines.append({
                "pr_no": old_r.pr_no,
                "pr_line": old_r.pr_line,
                "item_code": old_r.resolved_item_code,
                "old_route": old_r.route,
                "new_route": new_r.route,
                "old_decision": old_r.decision,
                "new_decision": new_r.decision,
                "old_supplier": old_r.supplier_id,
                "new_supplier": new_r.supplier_id,
                "group_value_inr": float(new_r.group_value_inr),
            })

    return {
        "total_lines_evaluated": len(pr_lines),
        "changed_lines_count": len(impacted_lines),
        "transitions": transitions,
        "impacted_lines": impacted_lines,
    }


def load_reference_data_from_db(db: Session) -> ReferenceData:
    """Helper to assemble engine ReferenceData from database models."""
    db_items = db.query(Item).all()
    db_supps = db.query(Supplier).all()
    db_contracts = db.query(Contract).all()
    db_pos = db.query(POHistory).all()

    items = {
        it.item_code: ItemMasterRecord(
            item_code=it.item_code,
            description=it.description,
            uom=it.uom,
            category=it.category,
            item_type=it.item_type,
            standard_price=Decimal(str(it.standard_price)),
        )
        for it in db_items
    }

    suppliers = {
        s.supplier_id: SupplierRecord(
            supplier_id=s.supplier_id,
            name=s.name,
            city=s.city or "",
            categories=s.categories or "",
            status=s.status,
            on_time_pct=Decimal(str(s.on_time_pct)) if s.on_time_pct is not None else Decimal("0"),
            quality_rating=Decimal(str(s.quality_rating)) if s.quality_rating is not None else Decimal("0"),
        )
        for s in db_supps
    }

    contracts = []
    for c in db_contracts:
        lines = {
            cl.item_code: ContractLineRecord(
                contract_id=cl.contract_id,
                item_code=cl.item_code,
                rate=Decimal(str(cl.rate)),
                uom=cl.uom or "",
                description=cl.description or "",
            )
            for cl in c.lines
        }
        contracts.append(
            ContractRecord(
                contract_id=c.contract_id,
                supplier_id=c.supplier_id,
                supplier_name=c.supplier.name if c.supplier else c.supplier_name,
                start_date=c.start_date,
                end_date=c.end_date,
                value_ceiling=Decimal(str(c.value_ceiling)) if c.value_ceiling is not None else Decimal("0"),
                consumed_value=Decimal(str(c.consumed_value)) if c.consumed_value is not None else Decimal("0"),
                lines=lines,
            )
        )

    po_history = [
        POHistoryRecord(
            po_number=p.po_number,
            po_date=p.po_date,
            supplier_id=p.supplier_id,
            item_code=p.item_code,
            quantity=Decimal(str(p.quantity)),
            uom=p.uom or "",
            unit_price=Decimal(str(p.unit_price)),
            plant=p.plant or "",
        )
        for p in db_pos
    ]

    return ReferenceData(
        items=items,
        suppliers=suppliers,
        contracts=contracts,
        po_history=po_history,
    )


def load_pr_lines_from_db(db: Session) -> List[PRLineInput]:
    """Helper to assemble engine PRLineInputs from database models."""
    db_lines = db.query(PRLine).order_by(PRLine.id).all()
    pr_inputs = []
    for l in db_lines:
        pr_inputs.append(
            PRLineInput(
                pr_no=l.pr_no,
                pr_line=l.pr_line,
                created_at=l.created_at,
                requester=l.requester or "",
                department=l.department or "",
                plant=l.plant,
                item_code=l.item_code,
                description=l.description,
                quantity=Decimal(str(l.quantity)),
                uom=l.uom or "",
                estimated_unit_price=Decimal(str(l.estimated_unit_price)) if l.estimated_unit_price is not None else None,
                need_by_date=l.need_by_date,
                urgency=l.urgency or "Normal",
            )
        )
    return pr_inputs
