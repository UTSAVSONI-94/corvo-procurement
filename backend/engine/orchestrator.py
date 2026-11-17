"""
backend/engine/orchestrator.py

Pure Python decision engine orchestrator.
Executes end-to-end PR-to-PO evaluation pipeline:
1. Validates and pre-filters PR lines (identifying non-processable lines).
2. Matches free-text descriptions to the item master.
3. Clubs lines into requirement groups according to Policy Section 2.
4. Evaluates requirements against the active policy version and contract ceilings.
5. Applies final supplier status guards (never awards PO to Blocked/Inactive).
6. Consolidates PO-ending requirements into purchase orders per Policy Section 7.
7. Produces deterministic, line-level output records per the brief.
"""

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Dict, List, Optional, Tuple, Any, Set

from backend.engine.types import (
    PRLineInput,
    ItemMasterRecord,
    SupplierRecord,
    ContractRecord,
    POHistoryRecord,
    RequirementGroup,
    ValuationResult,
    ReferenceData,
    BatchLineResult,
)
from backend.engine.item_matcher import match_item
from backend.engine.clubber import club_pr_lines
from backend.engine.contracts import ContractLedger
from backend.engine.valuation import value_requirement, has_active_supplier_purchase
from backend.engine.policy_eval import evaluate_policy_rules
from backend.engine.preferred_suppliers import (
    build_preferred_supplier_list,
    suggest_sourcing_suppliers,
)
from backend.engine.schema import PolicyDocument


class OpenPurchaseOrder:
    def __init__(
        self,
        po_id: str,
        supplier_id: str,
        plant: str,
        route: str,
        first_req_created_at: datetime,
    ):
        self.po_id = po_id
        self.supplier_id = supplier_id
        self.plant = plant
        self.route = route
        self.first_req_created_at = first_req_created_at
        self.requirement_ids: List[str] = []


def _format_inr(amount: Decimal) -> str:
    """Formats decimal currency into clean human-readable Indian Rupee representation."""
    return f"₹{amount:,.2f}"


def process_batch(
    pr_lines: List[PRLineInput],
    reference_data: ReferenceData,
    policy_repo: Any,
) -> List[BatchLineResult]:
    """
    Main entry point for batch PR processing.
    Pure Python: takes dataclasses in, returns dataclasses out.
    Guarantees 100% determinism.
    """
    # -------------------------------------------------------------
    # Step 1: Pre-validation & Non-processed Line Detection
    # -------------------------------------------------------------
    seen_pr_keys: Set[Tuple[str, int]] = set()
    valid_lines: List[PRLineInput] = []
    invalid_results: Dict[int, BatchLineResult] = {}

    for idx, line in enumerate(pr_lines):
        line_key = (line.pr_no, line.pr_line)

        # A. Duplicate PR Line Check
        if line_key in seen_pr_keys:
            invalid_results[idx] = BatchLineResult(
                pr_no=line.pr_no,
                pr_line=line.pr_line,
                resolved_item_code=line.item_code or "UNKNOWN",
                group_id="NONE",
                po_id=None,
                decision="NOT_PROCESSED",
                route="NOT_PROCESSED",
                supplier_id=None,
                unit_price=None,
                group_value_inr=Decimal("0.00"),
                suggested_supplier_ids="",
                policy_version="v5.0",
                reason=f"Duplicate PR line: {line.pr_no}/{line.pr_line} already processed in this batch.",
            )
            continue
        seen_pr_keys.add(line_key)

        # B. Plant Code Validation (Policy Section 1: only PUN1 and CHK1)
        norm_plant = (line.plant or "").strip().upper()
        if norm_plant not in ("PUN1", "CHK1"):
            invalid_results[idx] = BatchLineResult(
                pr_no=line.pr_no,
                pr_line=line.pr_line,
                resolved_item_code=line.item_code or "UNKNOWN",
                group_id="NONE",
                po_id=None,
                decision="NOT_PROCESSED",
                route="NOT_PROCESSED",
                supplier_id=None,
                unit_price=None,
                group_value_inr=Decimal("0.00"),
                suggested_supplier_ids="",
                policy_version="v5.0",
                reason=f"Invalid plant {line.plant}: Policy only applies to PUN1 and CHK1.",
            )
            continue

        # C. Quantity Validation (> 0)
        if line.quantity is None or line.quantity <= Decimal("0"):
            invalid_results[idx] = BatchLineResult(
                pr_no=line.pr_no,
                pr_line=line.pr_line,
                resolved_item_code=line.item_code or "UNKNOWN",
                group_id="NONE",
                po_id=None,
                decision="NOT_PROCESSED",
                route="NOT_PROCESSED",
                supplier_id=None,
                unit_price=None,
                group_value_inr=Decimal("0.00"),
                suggested_supplier_ids="",
                policy_version="v5.0",
                reason=f"Line rejected: quantity <= 0 (qty={line.quantity}). Quantity must be greater than zero.",
            )
            continue

        valid_lines.append(line)

    # -------------------------------------------------------------
    # Step 2: Item Matching (Policy 1.1 & 1.2)
    # -------------------------------------------------------------
    resolved_codes: Dict[Tuple[str, int], str] = {}
    for line in valid_lines:
        line_key = (line.pr_no, line.pr_line)
        match_res = match_item(
            user_item_code=line.item_code or "",
            description=line.description or "",
            item_master=reference_data.items,
        )
        resolved_codes[line_key] = match_res.item_code

    # -------------------------------------------------------------
    # Step 3: Club PR Lines into Requirements (Policy Section 2)
    # -------------------------------------------------------------
    # Clubbing uses standard 14-day creation window and 7-day need-by tolerance
    raw_requirements = club_pr_lines(
        lines=valid_lines,
        resolved_item_codes=resolved_codes,
        club_window_days=14,
        need_by_window_days=7,
    )

    # Sort requirements strictly by (requirement_date, first line created_at, id)
    raw_requirements.sort(
        key=lambda r: (r.requirement_date, r.pr_lines[0].created_at, r.id)
    )

    # Deterministic sequential requirement numbering: REQ-0001, REQ-0002...
    requirements: List[RequirementGroup] = []
    line_to_requirement: Dict[Tuple[str, int], RequirementGroup] = {}

    for idx, req in enumerate(raw_requirements, start=1):
        req.id = f"REQ-{idx:04d}"
        requirements.append(req)
        for line in req.pr_lines:
            line_to_requirement[(line.pr_no, line.pr_line)] = req

    # -------------------------------------------------------------
    # Step 4: Requirement Evaluation & Policy Application
    # -------------------------------------------------------------
    contracts_list = (
        list(reference_data.contracts.values())
        if isinstance(reference_data.contracts, dict)
        else reference_data.contracts
    )
    contracts_map = {c.contract_id: c for c in contracts_list}

    # Initialize batch contract ledger to track ceiling consumption sequentially
    ledger = ContractLedger(contracts_map)

    req_evaluations: Dict[str, Dict[str, Any]] = {}

    for req in requirements:
        # Retrieve policy active as of the requirement date
        if hasattr(policy_repo, "get_active_policy"):
            policy: PolicyDocument = policy_repo.get_active_policy(req.requirement_date)
        elif hasattr(policy_repo, "get_policy"):
            policy = policy_repo.get_policy(req.requirement_date)
        elif callable(policy_repo):
            policy = policy_repo(req.requirement_date)
        else:
            policy = policy_repo

        val_res, best_contract, contract_usable = value_requirement(
            req=req,
            item_master=reference_data.items,
            contracts=contracts_map,
            suppliers=reference_data.suppliers,
            po_history=reference_data.po_history,
            ledger=ledger,
            lookback_days=policy.parameters.po_history_days,
        )

        # Check purchase history from active supplier in last 365 days
        has_hist_365 = has_active_supplier_purchase(
            item_code=req.resolved_item_code,
            requirement_date=req.requirement_date,
            po_history=reference_data.po_history,
            suppliers=reference_data.suppliers,
            lookback_days=policy.parameters.po_history_days,
        )

        is_new_item = (req.resolved_item_code == "NEW")

        # Determine item type and category
        if is_new_item:
            item_type = "CONSUMABLE"
            category = "Unknown"
        else:
            item_rec = reference_data.items.get(req.resolved_item_code)
            item_type = item_rec.item_type if item_rec else "CONSUMABLE"
            category = item_rec.category if item_rec else "Unknown"

        # Build facts for condition engine
        facts = {
            "item_type": item_type,
            "category": category,
            "plant": req.plant,
            "value": val_res.total_value,
            "is_emergency": req.is_emergency,
            "urgency": "Emergency" if req.is_emergency else "Normal",
            "contract_usable": contract_usable,
            "has_active_supplier_purchase_365d": has_hist_365,
            "is_new_item": is_new_item,
            "quantity": req.total_quantity,
        }

        # Evaluate policy rules in order
        policy_context = (
            policy.model_dump()
            if hasattr(policy, "model_dump")
            else (policy.dict() if hasattr(policy, "dict") else dict(policy))
        )
        matched_rule, match_msg = evaluate_policy_rules(
            rules=policy.decision_rules,
            facts=facts,
            policy_context=policy_context,
        )

        outcome = matched_rule.get("outcome", {}) if matched_rule else {}
        clause = matched_rule.get("clause", "") if matched_rule else ""
        decision = outcome.get("decision", "SOURCING_REQUEST")
        route = outcome.get("route", "RFQ")
        suggest_count = outcome.get("suggest_count") or (3 if route == "RFQ" else 5)
        supplier_id: Optional[str] = None
        unit_price: Optional[Decimal] = val_res.unit_price
        suggested_ids_list: List[str] = []
        reason = ""

        # --- Route: Rate Contract PO (Clause 5.2) ---
        if route == "CONTRACT_PO" and best_contract is not None:
            supp = reference_data.suppliers.get(best_contract.supplier_id)
            if supp and supp.status.strip().lower() == "active":
                supplier_id = best_contract.supplier_id
                decision = "PO"
                unit_price = val_res.unit_price
                # Commit consumed value to ledger
                ledger.consume(best_contract.contract_id, val_res.total_value)
                consumed_so_far = ledger.get_consumed(best_contract.contract_id)
                ceiling_val = best_contract.value_ceiling
                reason = (
                    f"Policy {policy.version} {clause}: Covered by active rate contract "
                    f"{best_contract.contract_id} with supplier {supplier_id} at rate {_format_inr(unit_price)}. "
                    f"Ceiling has room (consumed {_format_inr(consumed_so_far)} <= {_format_inr(ceiling_val)})."
                )
            else:
                # Final Guard: Contract supplier is not active! Fall back to RFQ/RFP
                route = "RFQ" if val_res.total_value < Decimal(str(policy.thresholds.rfp_threshold)) else "RFP"
                decision = "SOURCING_REQUEST"
                supplier_id = None

        # --- Route: Spot PO or Emergency PO (Clauses 5.3 & 5.4) ---
        if route in ("SPOT_PO", "EMERGENCY_PO"):
            ranked_suppliers = build_preferred_supplier_list(
                item_code=req.resolved_item_code,
                as_of_date=req.requirement_date,
                po_history=reference_data.po_history,
                contracts=contracts_list,
                suppliers=reference_data.suppliers,
                weights=getattr(policy.parameters, "ranking_weights", None),
            )
            # Final Guard: find 1st ACTIVE preferred supplier
            active_preferred = [
                s for s in ranked_suppliers
                if reference_data.suppliers.get(s.supplier_id)
                and reference_data.suppliers[s.supplier_id].status.strip().lower() == "active"
            ]

            if active_preferred:
                chosen = active_preferred[0]
                supplier_id = chosen.supplier_id
                unit_price = chosen.reference_price or val_res.unit_price
                decision = "PO"
                ref_id = val_res.reference_id or "PO history"
                if route == "EMERGENCY_PO":
                    limit_amt = Decimal(str(policy.thresholds.emergency_limit))
                    reason = (
                        f"Policy {policy.version} {clause}: Marked Emergency, requirement value "
                        f"{_format_inr(val_res.total_value)} <= emergency limit {_format_inr(limit_amt)}, "
                        f"and active purchase history within {policy.parameters.po_history_days} days (relied on {ref_id}). "
                        f"Routed to 1st preferred supplier {supplier_id} at {_format_inr(unit_price)}."
                    )
                else:
                    limit_amt = Decimal(str(policy.thresholds.spot_limit))
                    reason = (
                        f"Policy {policy.version} {clause}: Requirement value {_format_inr(val_res.total_value)} "
                        f"< spot limit {_format_inr(limit_amt)} and active purchase history within "
                        f"{policy.parameters.po_history_days} days (relied on {ref_id}). "
                        f"Routed to 1st preferred supplier {supplier_id} at {_format_inr(unit_price)}."
                    )
            else:
                # No active preferred suppliers exist -> Fall through to sourcing!
                route = "RFQ" if val_res.total_value < Decimal(str(policy.thresholds.rfp_threshold)) else "RFP"
                decision = "SOURCING_REQUEST"
                supplier_id = None
                reason = (
                    f"Policy {policy.version} {clause}: Fallback to sourcing: no active preferred supplier "
                    f"found for {req.resolved_item_code}. Never issue PO to blocked or inactive supplier."
                )

        # --- Route: Sourcing Requests (RFQ, RFP, Capex, New Item) ---
        if decision == "SOURCING_REQUEST":
            supplier_id = None
            if route == "NEW_ITEM_SOURCING":
                suggested_ids_list = []
                reason = (
                    f"Policy {policy.version} {clause}: Item not found in item master (classified as NEW). "
                    f"Sourcing request valued at requester estimate {_format_inr(val_res.total_value)} with zero supplier suggestions."
                )
            else:
                target_count = suggest_count
                ranked_pref = build_preferred_supplier_list(
                    item_code=req.resolved_item_code,
                    as_of_date=req.requirement_date,
                    po_history=reference_data.po_history,
                    contracts=contracts_list,
                    suppliers=reference_data.suppliers,
                )
                suggested_ids_list = suggest_sourcing_suppliers(
                    item_code=req.resolved_item_code,
                    category=category,
                    as_of_date=req.requirement_date,
                    target_count=target_count,
                    preferred_suppliers=ranked_pref,
                    suppliers=reference_data.suppliers,
                    is_new_item=is_new_item,
                )
                sugg_str = ";".join(suggested_ids_list)

                if route == "CAPEX_SOURCING":
                    reason = (
                        f"Policy {policy.version} {clause}: Item type is Capex. Requirement value "
                        f"{_format_inr(val_res.total_value)}. Routed to Capex sourcing with {len(suggested_ids_list)} "
                        f"suggested suppliers ({sugg_str}) requiring Capex approval."
                    )
                elif route == "RFP":
                    rfp_limit = Decimal(str(policy.thresholds.rfp_threshold))
                    reason = (
                        f"Policy {policy.version} {clause}: Requirement value {_format_inr(val_res.total_value)} "
                        f">= RFP threshold {_format_inr(rfp_limit)}. Formal RFP required with {len(suggested_ids_list)} "
                        f"suggested suppliers ({sugg_str})."
                    )
                elif route == "RFQ":
                    spot_limit = Decimal(str(policy.thresholds.spot_limit))
                    rfp_limit = Decimal(str(policy.thresholds.rfp_threshold))
                    if val_res.source_method == "CONTRACT_RATE" and not contract_usable:
                        reason = (
                            f"Policy {policy.version} {clause}: Rate contract ceiling exceeded; requirement value "
                            f"{_format_inr(val_res.total_value)} < RFP threshold {_format_inr(rfp_limit)}. "
                            f"Routed to RFQ with {len(suggested_ids_list)} suggested suppliers ({sugg_str})."
                        )
                    elif not has_hist_365:
                        reason = (
                            f"Policy {policy.version} {clause}: Requirement value {_format_inr(val_res.total_value)} "
                            f"< spot limit {_format_inr(spot_limit)} but no active purchase history within "
                            f"{policy.parameters.po_history_days} days. Routed to RFQ with {len(suggested_ids_list)} "
                            f"suggested suppliers ({sugg_str})."
                        )
                    else:
                        reason = (
                            f"Policy {policy.version} {clause}: Requirement value {_format_inr(val_res.total_value)} "
                            f">= spot limit {_format_inr(spot_limit)} and < RFP threshold {_format_inr(rfp_limit)}. "
                            f"Routed to RFQ with {len(suggested_ids_list)} suggested suppliers ({sugg_str})."
                        )

        req_evaluations[req.id] = {
            "decision": decision,
            "route": route,
            "supplier_id": supplier_id,
            "unit_price": unit_price,
            "group_value_inr": val_res.total_value,
            "suggested_supplier_ids": ";".join(suggested_ids_list),
            "policy_version": policy.version,
            "reason": reason,
        }

    # -------------------------------------------------------------
    # Step 5: PO Consolidation (Policy Section 7)
    # -------------------------------------------------------------
    # Ordered by the creation timestamp of the requirement's first line
    po_ending_requirements = [
        req for req in requirements
        if req_evaluations[req.id]["decision"] == "PO"
    ]
    po_ending_requirements.sort(
        key=lambda r: (r.pr_lines[0].created_at, r.id)
    )

    open_pos: List[OpenPurchaseOrder] = []
    req_to_po_id: Dict[str, str] = {}
    po_seq_counter = 1

    for req in po_ending_requirements:
        req_eval = req_evaluations[req.id]
        supplier_id = req_eval["supplier_id"]
        plant = req.plant
        route = req_eval["route"]
        req_created_at = req.pr_lines[0].created_at

        # Search for an open PO with matching (supplier, plant, route) within 24h of its first requirement
        matched_po: Optional[OpenPurchaseOrder] = None
        for po in open_pos:
            if (
                po.supplier_id == supplier_id
                and po.plant == plant
                and po.route == route
            ):
                elapsed = req_created_at - po.first_req_created_at
                # Must be raised within 24 hours of that PO's first requirement
                if timedelta(0) <= elapsed <= timedelta(hours=24):
                    matched_po = po
                    break

        if matched_po is not None:
            matched_po.requirement_ids.append(req.id)
            req_to_po_id[req.id] = matched_po.po_id
        else:
            new_po_id = f"PO-{po_seq_counter:04d}"
            po_seq_counter += 1
            new_open_po = OpenPurchaseOrder(
                po_id=new_po_id,
                supplier_id=supplier_id,
                plant=plant,
                route=route,
                first_req_created_at=req_created_at,
            )
            new_open_po.requirement_ids.append(req.id)
            open_pos.append(new_open_po)
            req_to_po_id[req.id] = new_po_id

    # -------------------------------------------------------------
    # Step 6: Assemble Output Results per Input Line
    # -------------------------------------------------------------
    results: List[BatchLineResult] = []

    for idx, line in enumerate(pr_lines):
        if idx in invalid_results:
            results.append(invalid_results[idx])
            continue

        line_key = (line.pr_no, line.pr_line)
        req = line_to_requirement[line_key]
        eval_data = req_evaluations[req.id]
        assigned_po_id = req_to_po_id.get(req.id, None)

        results.append(
            BatchLineResult(
                pr_no=line.pr_no,
                pr_line=line.pr_line,
                resolved_item_code=req.resolved_item_code,
                group_id=req.id,
                po_id=assigned_po_id,
                decision=eval_data["decision"],
                route=eval_data["route"],
                supplier_id=eval_data["supplier_id"],
                unit_price=eval_data["unit_price"],
                group_value_inr=eval_data["group_value_inr"],
                suggested_supplier_ids=eval_data["suggested_supplier_ids"],
                policy_version=eval_data["policy_version"],
                reason=eval_data["reason"],
            )
        )

    return results
