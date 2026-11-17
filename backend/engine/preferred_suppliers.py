"""
backend/engine/preferred_suppliers.py

Preferred supplier evaluation and ranking module adhering to Corvo Procurement Policy v5.0, Section 6.
Pure Python module with zero DB or framework dependencies.
"""

from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
import io
import csv
from typing import List, Dict, Optional, Tuple, Any

from backend.engine.types import (
    SupplierRecord,
    POHistoryRecord,
    ContractRecord,
    ContractLineRecord,
    RankedSupplier,
    ScoreBreakdown,
)


DEFAULT_WEIGHTS = {
    "frequency": Decimal("0.30"),
    "recency": Decimal("0.25"),
    "contract_held": Decimal("0.20"),
    "on_time": Decimal("0.15"),
    "quality": Decimal("0.10"),
}


def _round_score(val: Decimal) -> Decimal:
    """Helper to round score to 4 decimal places for clean display and consistency."""
    return val.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


def _round_currency(val: Decimal) -> Decimal:
    return val.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def calculate_supplier_score(
    supplier: SupplierRecord,
    po_count: int,
    max_po_count: int,
    last_po_date: Optional[date],
    has_contract: bool,
    as_of_date: date,
    weights: Dict[str, Decimal],
) -> Tuple[Decimal, Decimal, List[ScoreBreakdown]]:
    """
    Computes transparent multi-criteria score and breakdown for an eligible supplier.
    """
    # 1. Frequency (0.30): normalized against max PO count for this item in window
    if max_po_count > 0:
        freq_raw = Decimal(po_count) / Decimal(max_po_count)
    else:
        freq_raw = Decimal("0")
    freq_weight = weights.get("frequency", DEFAULT_WEIGHTS["frequency"])
    freq_points = freq_raw * freq_weight

    # 2. Recency (0.25): 1.0 if within 90 days, 0.5 within 365 days, 0.0 otherwise
    if last_po_date is not None:
        days_ago = (as_of_date - last_po_date).days
        if days_ago <= 90:
            recency_raw = Decimal("1.0")
        elif days_ago <= 365:
            recency_raw = Decimal("0.5")
        else:
            recency_raw = Decimal("0.0")
    else:
        recency_raw = Decimal("0.0")
    recency_weight = weights.get("recency", DEFAULT_WEIGHTS["recency"])
    recency_points = recency_raw * recency_weight

    # 3. Contract Held (0.20): 1.0 if ever held contract for item starting on/before as_of_date
    contract_raw = Decimal("1.0") if has_contract else Decimal("0.0")
    contract_weight = weights.get("contract_held", DEFAULT_WEIGHTS["contract_held"])
    contract_points = contract_raw * contract_weight

    # 4. On-Time Delivery (0.15): normalized / 100
    on_time_raw = (supplier.on_time_pct or Decimal("0")) / Decimal("100")
    on_time_weight = weights.get("on_time", DEFAULT_WEIGHTS["on_time"])
    on_time_points = on_time_raw * on_time_weight

    # 5. Quality Rating (0.10): normalized / 5.0
    quality_raw = (supplier.quality_rating or Decimal("0")) / Decimal("5.0")
    quality_weight = weights.get("quality", DEFAULT_WEIGHTS["quality"])
    quality_points = quality_raw * quality_weight

    total_points = freq_points + recency_points + contract_points + on_time_points + quality_points

    breakdown = [
        ScoreBreakdown("frequency", po_count, freq_weight, _round_score(freq_points)),
        ScoreBreakdown("recency", recency_raw, recency_weight, _round_score(recency_points)),
        ScoreBreakdown("contract_held", bool(has_contract), contract_weight, _round_score(contract_points)),
        ScoreBreakdown("on_time", supplier.on_time_pct or Decimal("0"), on_time_weight, _round_score(on_time_points)),
        ScoreBreakdown("quality", supplier.quality_rating or Decimal("0"), quality_weight, _round_score(quality_points)),
    ]

    return _round_score(total_points), recency_raw, breakdown


def build_preferred_supplier_list(
    item_code: str,
    as_of_date: date,
    po_history: List[POHistoryRecord],
    contracts: List[ContractRecord],
    suppliers: Dict[str, SupplierRecord],
    weights: Optional[Dict[str, Decimal]] = None,
    history_days: int = 548,
) -> List[RankedSupplier]:
    """
    Ranks eligible suppliers for an item as of a given date (Policy 6.1, 6.2).

    Eligibility criteria:
    - Supplier is ACTIVE in supplier master (case-insensitive).
    - AND has at least 1 PO in the 548 days before as_of_date,
      OR has a contract covering the item starting on or before as_of_date (even if expired).
    - Blocked or Inactive suppliers are strictly excluded.
    """
    if weights is None:
        weights = DEFAULT_WEIGHTS

    window_start = as_of_date - timedelta(days=history_days)

    # 1. Filter PO history for this item within the window
    item_pos_in_window = [
        po for po in po_history
        if po.item_code == item_code
        and window_start <= po.po_date <= as_of_date
    ]

    # Group POs by supplier
    supplier_pos: Dict[str, List[POHistoryRecord]] = {}
    for po in item_pos_in_window:
        supplier_pos.setdefault(po.supplier_id, []).append(po)

    # 2. Check contracts covering this item starting on or before as_of_date
    supplier_contracts: Dict[str, List[Tuple[ContractRecord, ContractLineRecord]]] = {}
    for contract in contracts:
        if contract.start_date <= as_of_date:
            if isinstance(contract.lines, dict):
                if item_code in contract.lines:
                    line = contract.lines[item_code]
                    supplier_contracts.setdefault(contract.supplier_id, []).append((contract, line))
            else:
                for line in contract.lines:
                    if line.item_code == item_code:
                        supplier_contracts.setdefault(contract.supplier_id, []).append((contract, line))

    # Identify candidate supplier IDs
    candidate_supplier_ids = set(supplier_pos.keys()) | set(supplier_contracts.keys())

    # Filter by ACTIVE status
    eligible_supplier_ids = set()
    for s_id in candidate_supplier_ids:
        supp = suppliers.get(s_id)
        if supp and supp.status.strip().lower() == "active":
            eligible_supplier_ids.add(s_id)

    if not eligible_supplier_ids:
        return []

    # Calculate max PO count across eligible active suppliers for frequency normalization
    po_counts = {
        s_id: len(supplier_pos.get(s_id, []))
        for s_id in eligible_supplier_ids
    }
    max_po_count = max(po_counts.values()) if po_counts else 0

    evaluated: List[Dict[str, Any]] = []

    for s_id in eligible_supplier_ids:
        supp = suppliers[s_id]
        pos = supplier_pos.get(s_id, [])
        po_cnt = len(pos)

        # Most recent PO in window
        if pos:
            sorted_pos = sorted(pos, key=lambda p: (p.po_date, p.po_number), reverse=True)
            last_po = sorted_pos[0]
            last_po_date = last_po.po_date
            ref_price = last_po.unit_price
        else:
            last_po_date = None
            # Fall back to rate on most recent contract for the item
            c_lines = supplier_contracts.get(s_id, [])
            if c_lines:
                sorted_contracts = sorted(c_lines, key=lambda c: (c[0].start_date, c[0].contract_id), reverse=True)
                ref_price = sorted_contracts[0][1].rate
            else:
                ref_price = None

        has_contract = s_id in supplier_contracts

        total_score, recency_raw, breakdown = calculate_supplier_score(
            supplier=supp,
            po_count=po_cnt,
            max_po_count=max_po_count,
            last_po_date=last_po_date,
            has_contract=has_contract,
            as_of_date=as_of_date,
            weights=weights,
        )

        evaluated.append({
            "supplier_id": s_id,
            "supplier_name": supp.name,
            "total_score": total_score,
            "reference_price": ref_price,
            "po_count": po_cnt,
            "recency_score": recency_raw,
            "has_contract": has_contract,
            "on_time_pct": supp.on_time_pct or Decimal("0"),
            "quality_rating": supp.quality_rating or Decimal("0"),
            "last_po_date": last_po_date,
            "breakdown": breakdown,
        })

    # Sort deterministically:
    # 1. Total score descending
    # 2. Last PO date descending (suppliers with recent purchase beat those with None)
    # 3. On-time delivery pct descending
    # 4. Supplier ID ascending
    evaluated.sort(
        key=lambda x: (
            x["total_score"],
            x["last_po_date"] or date.min,
            x["on_time_pct"],
            # Python sorts ascending on ties, so for supplier_id we negate by custom compare or secondary sort
        ),
        reverse=True,
    )

    # Secondary tie-break for supplier_id ascending when other fields are equal
    # Python's timsort is stable, so we can achieve multi-key mixed direction cleanly:
    def sort_key(item):
        return (
            -item["total_score"],
            -(item["last_po_date"] or date.min).toordinal(),
            -item["on_time_pct"],
            item["supplier_id"],
        )

    evaluated.sort(key=sort_key)

    ranked_suppliers: List[RankedSupplier] = []
    for rank, entry in enumerate(evaluated, start=1):
        ranked_suppliers.append(
            RankedSupplier(
                supplier_id=entry["supplier_id"],
                supplier_name=entry["supplier_name"],
                rank=rank,
                total_score=entry["total_score"],
                reference_price=entry["reference_price"],
                po_count=entry["po_count"],
                recency_score=entry["recency_score"],
                has_contract=entry["has_contract"],
                on_time_pct=entry["on_time_pct"],
                quality_rating=entry["quality_rating"],
                breakdown=entry["breakdown"],
            )
        )

    return ranked_suppliers


def suggest_sourcing_suppliers(
    item_code: str,
    category: str,
    as_of_date: date,
    target_count: int,
    preferred_suppliers: List[RankedSupplier],
    suppliers: Dict[str, SupplierRecord],
    is_new_item: bool = False,
) -> List[str]:
    """
    Returns list of supplier IDs for RFQ/RFP sourcing requests (Policy 6.4).

    Order of selection:
    1. Preferred supplier list in rank order.
    2. If fewer than target_count (e.g. 3 for RFQ, 5 for RFP):
       Top up with other ACTIVE suppliers listing the item's category,
       ranked by delivery and quality performance:
         (on_time_pct / 100 * 0.60) + (quality_rating / 5.0 * 0.40).
    3. New items get NO automatic suggestions (empty list).
    4. Blocked / Inactive suppliers are NEVER included.
    5. If category pool is exhausted, returns available suppliers without padding.
    """
    if is_new_item:
        return []

    suggested: List[str] = [s.supplier_id for s in preferred_suppliers]

    if len(suggested) >= target_count:
        return suggested[:target_count]

    needed = target_count - len(suggested)
    already_selected = set(suggested)

    # Find candidate category suppliers
    category_candidates: List[Tuple[Decimal, Decimal, str]] = []
    norm_cat = category.strip().lower()

    for s_id, supp in suppliers.items():
        if s_id in already_selected:
            continue
        if supp.status.strip().lower() != "active":
            continue

        # Check if supplier lists this category (split comma-separated or list)
        raw_cats = supp.categories
        if isinstance(raw_cats, str):
            supp_cats = [c.strip().lower() for c in raw_cats.split(",")]
        else:
            supp_cats = [c.strip().lower() for c in (raw_cats or [])]

        if norm_cat in supp_cats:
            on_time = supp.on_time_pct or Decimal("0")
            quality = supp.quality_rating or Decimal("0")
            perf_score = (quality / Decimal("5.0") * Decimal("0.60")) + (on_time / Decimal("100") * Decimal("0.40"))
            category_candidates.append((perf_score, quality, on_time, s_id))

    # Sort category candidates by perf_score DESC, quality DESC, on_time DESC, s_id ASC
    category_candidates.sort(
        key=lambda x: (-x[0], -x[1], -x[2], x[3])
    )

    for _, _, _, s_id in category_candidates[:needed]:
        suggested.append(s_id)

    return suggested


def export_preferred_suppliers_csv(
    as_of_date: date,
    items: List[Any],
    po_history: List[POHistoryRecord],
    contracts: List[ContractRecord],
    suppliers: Dict[str, SupplierRecord],
    top_n: int = 3,
    weights: Optional[Dict[str, Decimal]] = None,
) -> str:
    """
    Generates CSV export of top-N preferred suppliers per item.
    Columns: item_code, rank, supplier_id, supplier_name, reference_price, total_score
    """
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["item_code", "rank", "supplier_id", "supplier_name", "reference_price", "total_score"])

    # Sort items by item_code for deterministic export
    sorted_items = sorted(items, key=lambda it: getattr(it, "code", getattr(it, "item_code", str(it))))

    for it in sorted_items:
        code = getattr(it, "code", getattr(it, "item_code", str(it)))
        ranked = build_preferred_supplier_list(
            item_code=code,
            as_of_date=as_of_date,
            po_history=po_history,
            contracts=contracts,
            suppliers=suppliers,
            weights=weights,
        )
        for supp in ranked[:top_n]:
            ref_price_str = f"{supp.reference_price:.2f}" if supp.reference_price is not None else ""
            writer.writerow([
                code,
                supp.rank,
                supp.supplier_id,
                supp.supplier_name,
                ref_price_str,
                f"{supp.total_score:.4f}",
            ])

    return output.getvalue()
