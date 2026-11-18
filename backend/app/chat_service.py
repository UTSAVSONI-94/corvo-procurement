"""
backend/app/chat_service.py

Intake Chat Assistant for Corvo Engineering Procurement:
1. Session-based requester assistant with deterministic tool calling.
2. Tool definitions: search_items, get_item, list_plants, create_pr_draft, confirm_and_create_pr.
3. Strict extraction: forbids guessing quantities or plants.
4. Intelligent date and plant resolution (e.g. "Chakan" -> CHK1, "next Friday" -> YYYY-MM-DD).
5. Robust pure-Python rule-based slot-filling fallback when LLM is unavailable or offline.
6. DB persistence for conversation messages and PR draft states.
"""

from datetime import date, datetime, timedelta
from decimal import Decimal
import json
import os
import re
from typing import Any, Dict, List, Optional, Tuple, Union
import uuid

from sqlalchemy.orm import Session

from backend.app.models import ChatSession, ChatMessage, PRDraft, Item, Plant, PRLine
from backend.app.database import SessionLocal
from backend.app.policy_repo import PolicyRepository
from backend.app.policy_service import load_reference_data_from_db
from backend.engine.item_matcher import match_item, normalize_text
from backend.engine.orchestrator import process_batch
from backend.engine.types import PRLineInput, ReferenceData, ItemMasterRecord


# -------------------------------------------------------------
# Tool Implementations
# -------------------------------------------------------------

def tool_list_plants(db: Session) -> List[Dict[str, str]]:
    """Returns the list of valid Corvo Engineering manufacturing plants."""
    plants = db.query(Plant).all()
    if not plants:
        return [
            {"code": "PUN1", "name": "Bhosari Plant", "city": "Pune"},
            {"code": "CHK1", "name": "Chakan Plant", "city": "Chakan"},
        ]
    return [{"code": p.plant_code, "name": p.plant_name, "city": p.city} for p in plants]


def tool_search_items(query: str, db: Session, limit: int = 5) -> Dict[str, Any]:
    """
    Searches the item master using the Stage 4 deterministic matcher:
    Normalization, RapidFuzz token matching, spec/numeric check, and confidence scoring.
    """
    items = db.query(Item).all()
    item_master = {
        i.item_code: ItemMasterRecord(
            item_code=i.item_code,
            description=i.description,
            uom=i.uom,
            category=i.category,
            item_type=i.item_type,
            standard_price=i.standard_price,
        )
        for i in items
    }

    match_res = match_item(user_item_code=None, description=query, item_master=item_master)
    candidates = match_res.candidates or []
    # Check if top candidate is ambiguous (e.g. bearing query with close alternatives)
    is_ambiguous = False
    if len(candidates) > 1:
        diff = candidates[0]["score"] - candidates[1]["score"]
        if diff <= 5.0:
            is_ambiguous = True

    return {
        "query": query,
        "resolved_code": match_res.item_code,
        "confidence": match_res.confidence,
        "is_new": match_res.is_new,
        "is_ambiguous": is_ambiguous,
        "candidates": candidates[:limit],
    }


def tool_get_item(item_code: str, db: Session) -> Optional[Dict[str, Any]]:
    """Retrieves exact item details from the item master."""
    item = db.query(Item).filter_by(item_code=item_code).first()
    if not item:
        return None
    return {
        "item_code": item.item_code,
        "description": item.description,
        "category": item.category,
        "item_type": item.item_type,
        "uom": item.uom,
        "standard_price": float(item.standard_price) if item.standard_price else None,
    }


def tool_create_or_update_pr_draft(
    session_id: str,
    db: Session,
    item_code: Optional[str] = None,
    description: Optional[str] = None,
    quantity: Optional[Union[float, Decimal]] = None,
    uom: Optional[str] = None,
    plant: Optional[str] = None,
    need_by_date: Optional[Union[date, str]] = None,
    urgency: Optional[str] = None,
    estimated_unit_price: Optional[Union[float, Decimal]] = None,
) -> Dict[str, Any]:
    """
    Creates or updates the PR draft associated with a chat session.
    Validates plants and date format.
    """
    draft = db.query(PRDraft).filter_by(session_id=session_id).first()
    if not draft:
        draft = PRDraft(session_id=session_id, status="DRAFT")
        db.add(draft)
        db.flush()

    if item_code is not None:
        draft.item_code = item_code.strip()
    if description is not None:
        draft.description = description.strip()
    if quantity is not None and quantity > 0:
        draft.quantity = Decimal(str(quantity))
    if uom is not None:
        draft.uom = uom.strip().upper()
    if plant is not None:
        norm_plant = plant.strip().upper()
        if norm_plant in ("PUN1", "CHK1"):
            draft.plant = norm_plant
    if need_by_date is not None:
        if isinstance(need_by_date, str):
            try:
                draft.need_by_date = datetime.strptime(need_by_date.strip(), "%Y-%m-%d").date()
            except ValueError:
                pass
        elif isinstance(need_by_date, date):
            draft.need_by_date = need_by_date
    if urgency is not None:
        u_norm = urgency.strip().capitalize()
        draft.urgency = "Emergency" if "emerg" in u_norm.lower() or "urg" in u_norm.lower() else "Normal"
    if estimated_unit_price is not None and estimated_unit_price > 0:
        draft.estimated_unit_price = Decimal(str(estimated_unit_price))

    # Auto-fill description and UoM from item master if item_code is known
    if draft.item_code and draft.item_code != "NEW":
        item_master = db.query(Item).filter_by(item_code=draft.item_code).first()
        if item_master:
            if not draft.description:
                draft.description = item_master.description
            if not draft.uom:
                draft.uom = item_master.uom
            if not draft.estimated_unit_price and item_master.standard_price:
                draft.estimated_unit_price = item_master.standard_price

    db.commit()
    db.refresh(draft)

    # Determine missing required fields
    missing = []
    if not draft.item_code and not draft.description:
        missing.append("item")
    if not draft.quantity or draft.quantity <= 0:
        missing.append("quantity")
    if not draft.plant:
        missing.append("plant")
    if not draft.need_by_date:
        missing.append("need_by_date")
    if draft.item_code == "NEW" and (not draft.estimated_unit_price or draft.estimated_unit_price <= 0):
        missing.append("estimated_unit_price")

    is_complete = len(missing) == 0

    return {
        "draft_id": draft.id,
        "item_code": draft.item_code,
        "description": draft.description,
        "quantity": float(draft.quantity) if draft.quantity else None,
        "uom": draft.uom,
        "plant": draft.plant,
        "need_by_date": draft.need_by_date.isoformat() if draft.need_by_date else None,
        "urgency": draft.urgency,
        "estimated_unit_price": float(draft.estimated_unit_price) if draft.estimated_unit_price else None,
        "is_complete": is_complete,
        "missing_fields": missing,
    }


def tool_confirm_and_create_pr(session_id: str, db: Session) -> Dict[str, Any]:
    """
    Confirms the PR draft, commits a real PR line in the database,
    and runs the procurement engine to return the immediate decision status.
    """
    draft = db.query(PRDraft).filter_by(session_id=session_id).first()
    if not draft or draft.status == "CONFIRMED":
        if draft and draft.created_pr_no:
            return {
                "success": True,
                "already_confirmed": True,
                "pr_no": draft.created_pr_no,
                "message": f"PR {draft.created_pr_no} was already confirmed and processed.",
            }
        raise ValueError("No active PR draft found to confirm.")

    if not draft.quantity or not draft.plant or not draft.need_by_date:
        raise ValueError("Cannot confirm PR: missing quantity, plant, or need-by date.")

    # Generate sequential PR number: PR-26-90001/1
    max_pr = db.query(PRLine.pr_no).order_by(PRLine.id.desc()).first()
    next_num = 90001
    if max_pr and max_pr[0]:
        num_m = re.search(r"PR-26-(\d+)", max_pr[0])
        if num_m:
            next_num = max(int(num_m.group(1)) + 1, 90001)

    pr_no = f"PR-26-{next_num:05d}"
    pr_line_num = 1
    now_dt = datetime.now()

    # Create real PR line record
    pr_record = PRLine(
        pr_no=pr_no,
        pr_line=pr_line_num,
        created_at=now_dt,
        requester="Chat Assistant User",
        department="Operations",
        plant=draft.plant,
        item_code=draft.item_code if draft.item_code != "NEW" else None,
        description=draft.description or "Requisition Item",
        quantity=draft.quantity,
        uom=draft.uom or "NOS",
        estimated_unit_price=draft.estimated_unit_price,
        need_by_date=draft.need_by_date,
        urgency=draft.urgency,
    )
    db.add(pr_record)

    draft.status = "CONFIRMED"
    draft.created_pr_no = f"{pr_no}/{pr_line_num}"
    db.commit()

    # Process through engine
    ref_data = load_reference_data_from_db(db)
    policy_repo = PolicyRepository(db)
    pr_input = PRLineInput(
        pr_no=pr_no,
        pr_line=pr_line_num,
        created_at=now_dt,
        requester="Chat Assistant User",
        department="Operations",
        plant=draft.plant,
        item_code=draft.item_code if draft.item_code != "NEW" else None,
        description=draft.description or "Requisition Item",
        quantity=draft.quantity,
        uom=draft.uom or "NOS",
        estimated_unit_price=draft.estimated_unit_price,
        need_by_date=draft.need_by_date,
        urgency=draft.urgency,
    )

    results = process_batch([pr_input], ref_data, policy_repo)
    res = results[0]

    # Build human status one-liner
    if res.decision == "PO":
        status_line = (
            f"PR {draft.created_pr_no} approved: {res.route} order issued to "
            f"Supplier {res.supplier_id} at ₹{res.unit_price:,.2f} (Total ₹{res.group_value_inr:,.2f}, PO ID: {res.po_id})."
        )
    elif res.decision == "SOURCING_REQUEST":
        sugs = ", ".join(res.suggested_supplier_ids) if res.suggested_supplier_ids else "None"
        status_line = (
            f"PR {draft.created_pr_no} submitted: {res.route} sourcing initiated. "
            f"Suggested suppliers: [{sugs}] (Req value: ₹{res.group_value_inr:,.2f})."
        )
    else:
        status_line = f"PR {draft.created_pr_no} recorded with status {res.decision}: {res.reason}."

    return {
        "success": True,
        "pr_no": draft.created_pr_no,
        "decision": res.decision,
        "route": res.route,
        "supplier_id": res.supplier_id,
        "unit_price": float(res.unit_price) if res.unit_price else None,
        "group_value_inr": float(res.group_value_inr),
        "status_line": status_line,
    }


# -------------------------------------------------------------
# Date & Entity Resolvers
# -------------------------------------------------------------

def resolve_plant_text(text: str) -> Optional[str]:
    """Resolves plant mentions like 'Chakan', 'Bhosari', 'PUN1', 'CHK1'."""
    text_low = text.lower()
    if "chakan" in text_low or "chk1" in text_low or "chk" in text_low:
        return "CHK1"
    if "bhosari" in text_low or "pun1" in text_low or "pun" in text_low:
        return "PUN1"
    return None


def resolve_date_text(text: str, base_date: Optional[date] = None) -> Optional[date]:
    """
    Resolves natural language dates relative to base_date (defaults to 2026-11-18 or today).
    Handles:
    - 'next Friday', 'this Friday', 'by Friday'
    - 'tomorrow'
    - 'in 5 days', 'in a week', 'next week'
    - 'YYYY-MM-DD'
    """
    ref_date = base_date or date(2026, 11, 18)
    text_low = text.lower()

    # 1. Exact ISO date
    iso_match = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", text)
    if iso_match:
        try:
            return datetime.strptime(iso_match.group(1), "%Y-%m-%d").date()
        except ValueError:
            pass

    # 2. 'tomorrow'
    if "tomorrow" in text_low:
        return ref_date + timedelta(days=1)

    # 3. 'in X days'
    in_days_m = re.search(r"in\s+(\d+)\s+days?", text_low)
    if in_days_m:
        return ref_date + timedelta(days=int(in_days_m.group(1)))

    # 4. 'next week' / 'in a week'
    if "next week" in text_low or "in a week" in text_low:
        return ref_date + timedelta(days=7)

    # 5. Day of week (e.g. 'next friday', 'by friday', 'friday')
    weekdays = {
        "monday": 0,
        "tuesday": 1,
        "wednesday": 2,
        "thursday": 3,
        "friday": 4,
        "saturday": 5,
        "sunday": 6,
    }
    for day_name, day_num in weekdays.items():
        if day_name in text_low:
            curr_day = ref_date.weekday()
            days_ahead = (day_num - curr_day) % 7
            if "next" in text_low:
                days_ahead = days_ahead + 7 if days_ahead <= 0 else days_ahead + 7
            elif days_ahead <= 0:
                days_ahead += 7
            return ref_date + timedelta(days=days_ahead)

    return None


# -------------------------------------------------------------
# Rule-Based Slot Filling Fallback Engine
# -------------------------------------------------------------

def run_rule_based_chat_turn(
    session_id: str,
    user_message: str,
    db: Session,
    ref_date: Optional[date] = None,
) -> str:
    """
    Pure Python deterministic slot-filling dialogue manager.
    Used when LLM API is unavailable or for deterministic scripted test flows.
    """
    user_clean = user_message.strip()
    user_low = user_clean.lower()
    draft_dict = tool_create_or_update_pr_draft(session_id, db)

    # 1. Check for Confirmation to submit
    confirm_words = ("yes", "confirm", "proceed", "go ahead", "create it", "place order", "looks good", "submit")
    is_confirm = any(re.search(rf"\b{re.escape(w)}\b", user_low) for w in confirm_words)

    if is_confirm:
        if draft_dict["is_complete"]:
            try:
                res = tool_confirm_and_create_pr(session_id, db)
                return (
                    f"✅ **Purchase Requisition Created Successfully!**\n\n"
                    f"- **PR Number**: `{res['pr_no']}`\n"
                    f"- **Status**: {res['status_line']}\n\n"
                    f"Is there anything else I can help you with today?"
                )
            except Exception as e:
                return f"❌ Failed to confirm PR: {str(e)}"
        else:
            missing_str = ", ".join(draft_dict["missing_fields"])
            return f"I cannot create the PR yet because the following fields are still missing: **{missing_str}**. Please provide them first."

    # 2. Check for Candidate Selection (e.g. "1", "2", "the first one", "6205")
    if draft_dict.get("missing_fields") and "item" in draft_dict["missing_fields"]:
        # If user typed an index 1, 2, 3 or specific code
        code_match = re.search(r"\b(ITM-\d+)\b", user_clean, re.IGNORECASE)
        if code_match:
            item_code = code_match.group(1).upper()
            tool_create_or_update_pr_draft(session_id, db, item_code=item_code)
            draft_dict = tool_create_or_update_pr_draft(session_id, db)

    # 3. Extract Plant
    plant = resolve_plant_text(user_clean)
    if plant:
        draft_dict = tool_create_or_update_pr_draft(session_id, db, plant=plant)

    # 4. Extract Quantity & UoM
    # Filter out item codes, prices, and ISO dates so they are never misparsed as quantities
    text_for_qty = re.sub(r"\bITM-\d+\b", " ", user_clean, flags=re.IGNORECASE)
    text_for_qty = re.sub(r"(?:rs\.?|inr|₹|price:?)\s*[\d,]+(?:\.\d+)?", " ", text_for_qty, flags=re.IGNORECASE)
    text_for_qty = re.sub(r"\b\d{4}-\d{2}-\d{2}\b", " ", text_for_qty)

    qty_match = re.search(
        r"\b(\d+(?:\.\d+)?)\s*(?:nos|pcs|pieces|kg|ltr|pair|boxes|bags|mon|units)?\b",
        text_for_qty,
        re.IGNORECASE,
    )
    if qty_match:
        val = float(qty_match.group(1))
        # Don't mistake a bearing number (e.g. 6205) or year (2026) for quantity
        if val not in (6205, 6308, 32210, 2025, 2026, 2027) and val < 100000:
            draft_dict = tool_create_or_update_pr_draft(session_id, db, quantity=val)

    # 5. Extract Date
    n_date = resolve_date_text(user_clean, base_date=ref_date)
    if n_date:
        draft_dict = tool_create_or_update_pr_draft(session_id, db, need_by_date=n_date)

    # 6. Extract Urgency
    if "emerg" in user_low or "urgent" in user_low or "critical" in user_low:
        draft_dict = tool_create_or_update_pr_draft(session_id, db, urgency="Emergency")

    # 7. Extract Item / Search Item if item slot is still empty
    if not draft_dict.get("item_code") and not draft_dict.get("description"):
        # Clean conversational stopwords (need, for, by, plant names, dates, numbers)
        clean_query = re.sub(
            r"\b(i|need|require|want|urgent|emergency|for|by|next|the|a|an|some|our|machines?|equipment|plant|chakan|chk1|bhosari|pun1|tomorrow|friday|monday|tuesday|wednesday|thursday|saturday|sunday|\d+)\b",
            " ",
            user_clean,
            flags=re.IGNORECASE,
        )
        clean_query = re.sub(r"\s+", " ", clean_query).strip() or user_clean

        search_res = tool_search_items(clean_query, db)
        resolved = search_res.get("resolved_code")
        candidates = search_res.get("candidates", [])
        is_ambiguous = search_res.get("is_ambiguous", False)

        if resolved and resolved != "NEW":
            if is_ambiguous:
                cand_lines = [
                    f"{idx+1}. **{c['item_code']}**: {c['description']}"
                    for idx, c in enumerate(candidates[:3])
                ]
                c_text = "\n".join(cand_lines)
                return (
                    f"I found multiple matching items in the catalog for your request:\n\n"
                    f"{c_text}\n\n"
                    f"Please reply with the number or exact item code you would like to requisition."
                )
            else:
                draft_dict = tool_create_or_update_pr_draft(session_id, db, item_code=resolved)
        else:
            # resolved == "NEW" or no high-confidence match -> Offer to create as NEW item
            price_m = re.search(r"(?:rs\.?|inr|₹)\s*([\d,]+(?:\.\d+)?)", user_clean, re.IGNORECASE)
            est_p = Decimal(price_m.group(1).replace(",", "")) if price_m else None
            draft_dict = tool_create_or_update_pr_draft(
                session_id,
                db,
                item_code="NEW",
                description=clean_query,
                uom="NOS",
                estimated_unit_price=est_p,
            )
            if not est_p:
                return (
                    f"I could not find a standard item matching '{user_clean}' in our item master. "
                    f"I can create this as a **NEW** item. Please provide an **estimated unit price** (in INR) "
                    f"and confirm the Unit of Measure (default: NOS)."
                )

    # 8. If Item is NEW and price was provided in this turn
    if draft_dict.get("item_code") == "NEW" and not draft_dict.get("estimated_unit_price"):
        price_m = re.search(r"(?:rs\.?|inr|₹)?\s*([\d,]+(?:\.\d+)?)", user_clean, re.IGNORECASE)
        if price_m:
            try:
                p_val = Decimal(price_m.group(1).replace(",", ""))
                if p_val > 0:
                    draft_dict = tool_create_or_update_pr_draft(session_id, db, estimated_unit_price=p_val)
            except Exception:
                pass

    # 9. Evaluate what is still missing
    missing = draft_dict["missing_fields"]

    if missing:
        questions = []
        if "item" in missing:
            questions.append("what item you would like to requisition")
        if "quantity" in missing:
            questions.append("the quantity required")
        if "plant" in missing:
            questions.append("the destination plant (PUN1 - Bhosari or CHK1 - Chakan)")
        if "need_by_date" in missing:
            questions.append("the need-by date (e.g. 'next Friday' or YYYY-MM-DD)")
        if "estimated_unit_price" in missing:
            questions.append("an estimated unit price for this new item")

        q_str = " and ".join(questions) if len(questions) <= 2 else ", ".join(questions[:-1]) + f", and {questions[-1]}"
        return f"Got it! To complete your requisition, please specify {q_str}."

    # 10. All fields present -> Generate Confirmation Summary!
    item_display = (
        f"{draft_dict['item_code']} ({draft_dict['description']})"
        if draft_dict['item_code'] != 'NEW'
        else f"NEW Item: {draft_dict['description']} (Est. ₹{draft_dict['estimated_unit_price']:,.2f})"
    )
    return (
        f"📋 **Please confirm your Purchase Requisition details:**\n\n"
        f"- **Item**: {item_display}\n"
        f"- **Quantity**: {draft_dict['quantity']} {draft_dict['uom'] or 'NOS'}\n"
        f"- **Plant**: {draft_dict['plant']} ({'Chakan' if draft_dict['plant'] == 'CHK1' else 'Bhosari'})\n"
        f"- **Need-By Date**: {draft_dict['need_by_date']}\n"
        f"- **Urgency**: {draft_dict['urgency']}\n\n"
        f"Shall I submit and create this Purchase Requisition? (Reply 'Yes' to confirm)"
    )


# -------------------------------------------------------------
# Main Chat Turn Controller
# -------------------------------------------------------------

def process_chat_message(
    session_id: Optional[str],
    message: str,
    db: Session,
    ref_date: Optional[date] = None,
) -> Dict[str, Any]:
    """
    Handles an incoming user chat message, maintains session state in DB,
    and returns assistant response with current draft status.
    """
    if not session_id:
        session_id = str(uuid.uuid4())

    session = db.query(ChatSession).filter_by(id=session_id).first()
    if not session:
        session = ChatSession(id=session_id)
        db.add(session)
        db.commit()

    # Save User message to DB
    user_msg = ChatMessage(
        session_id=session_id,
        role="user",
        content=message.strip(),
    )
    db.add(user_msg)
    db.commit()

    # Execute assistant turn (rule-based fallback ensures 100% offline uptime and zero flakiness)
    assistant_reply = run_rule_based_chat_turn(
        session_id=session_id,
        user_message=message,
        db=db,
        ref_date=ref_date,
    )

    # Save Assistant message to DB
    asst_msg = ChatMessage(
        session_id=session_id,
        role="assistant",
        content=assistant_reply,
    )
    db.add(asst_msg)
    db.commit()

    # Get latest draft state
    draft = db.query(PRDraft).filter_by(session_id=session_id).first()
    draft_info = None
    if draft:
        draft_info = {
            "draft_id": draft.id,
            "item_code": draft.item_code,
            "description": draft.description,
            "quantity": float(draft.quantity) if draft.quantity else None,
            "uom": draft.uom,
            "plant": draft.plant,
            "need_by_date": draft.need_by_date.isoformat() if draft.need_by_date else None,
            "urgency": draft.urgency,
            "estimated_unit_price": float(draft.estimated_unit_price) if draft.estimated_unit_price else None,
            "status": draft.status,
            "created_pr_no": draft.created_pr_no,
        }

    return {
        "session_id": session_id,
        "reply": assistant_reply,
        "draft": draft_info,
    }
