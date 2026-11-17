from datetime import date
from decimal import Decimal
from typing import Dict, List, Optional, Tuple

from .types import (
    ItemMasterRecord,
    ContractRecord,
    SupplierRecord,
    POHistoryRecord,
    RequirementGroup,
    ValuationResult,
)
from .contracts import ContractLedger, select_best_contract


def get_most_recent_po(
    item_code: str,
    requirement_date: date,
    po_history: List[POHistoryRecord],
    lookback_days: int = 365,
) -> Optional[POHistoryRecord]:
    """
    Policy Clause 3.1(b):
    Returns the most recent PO for the item within `lookback_days` (365 days)
    before the requirement date.
    """
    matching_pos = []
    for po in po_history:
        if po.item_code != item_code:
            continue
        # Must be strictly before or on requirement date
        delta_days = (requirement_date - po.po_date).days
        if 0 <= delta_days <= lookback_days:
            matching_pos.append(po)

    if not matching_pos:
        return None

    # Sort by po_date descending, then po_number descending
    matching_pos.sort(key=lambda p: (p.po_date, p.po_number), reverse=True)
    return matching_pos[0]


def has_active_supplier_purchase(
    item_code: str,
    requirement_date: date,
    po_history: List[POHistoryRecord],
    suppliers: Dict[str, SupplierRecord],
    lookback_days: int = 365,
) -> bool:
    """
    Policy Clause 5.3 & 5.4:
    Checks if the item was bought from an Active supplier in the last 365 days.
    """
    for po in po_history:
        if po.item_code != item_code:
            continue
        delta_days = (requirement_date - po.po_date).days
        if 0 <= delta_days <= lookback_days:
            supplier = suppliers.get(po.supplier_id)
            if supplier and supplier.status.strip().lower() == "active":
                return True
    return False


def value_requirement(
    req: RequirementGroup,
    item_master: Dict[str, ItemMasterRecord],
    contracts: Dict[str, ContractRecord],
    suppliers: Dict[str, SupplierRecord],
    po_history: List[POHistoryRecord],
    ledger: ContractLedger,
    lookback_days: int = 365,
) -> Tuple[ValuationResult, Optional[ContractRecord], bool]:
    """
    Calculates requirement unit price and total value following Policy 3.1 & 1.2:
    Order of precedence:
      (a) Rate of the contract to be used (4.3), or, if all applicable contracts are out of ceiling,
          the lowest applicable contract rate.
      (b) Most recent PO price for the item in the 365 days before requirement date.
      (c) Item master standard price.
    NEW items:
      Valued at quantity * requester's estimated unit price.

    Returns:
      (ValuationResult, selected_contract, contract_usable)
    """
    qty = req.total_quantity

    # 1. NEW item valuation (Policy 1.2)
    if req.resolved_item_code == "NEW":
        first_line = req.pr_lines[0] if req.pr_lines else None
        est_price = first_line.estimated_unit_price if first_line and first_line.estimated_unit_price else Decimal("0.00")
        total_val = qty * est_price
        return (
            ValuationResult(
                unit_price=est_price,
                total_value=total_val,
                source_method="ESTIMATED_PRICE",
                reference_id=first_line.pr_no if first_line else None,
            ),
            None,
            False,
        )

    # 2. Contract Rate Valuation (Policy 3.1a)
    best_contract, contract_rate, contract_usable, lowest_rate = select_best_contract(
        item_code=req.resolved_item_code,
        requirement_date=req.requirement_date,
        quantity=qty,
        contracts=contracts,
        suppliers=suppliers,
        ledger=ledger,
    )

    if contract_rate is not None and contract_rate > Decimal("0.00"):
        total_val = qty * contract_rate
        ref_id = best_contract.contract_id if best_contract else "ALL_CONTRACTS_EXHAUSTED"
        return (
            ValuationResult(
                unit_price=contract_rate,
                total_value=total_val,
                source_method="CONTRACT_RATE",
                reference_id=ref_id,
            ),
            best_contract,
            contract_usable,
        )

    # 3. Recent PO Price Valuation (Policy 3.1b)
    recent_po = get_most_recent_po(
        item_code=req.resolved_item_code,
        requirement_date=req.requirement_date,
        po_history=po_history,
        lookback_days=lookback_days,
    )
    if recent_po is not None:
        unit_price = recent_po.unit_price
        total_val = qty * unit_price
        return (
            ValuationResult(
                unit_price=unit_price,
                total_value=total_val,
                source_method="RECENT_PO",
                reference_id=recent_po.po_number,
            ),
            None,
            False,
        )

    # 4. Item Master Standard Price Valuation (Policy 3.1c)
    item = item_master.get(req.resolved_item_code)
    if item is not None:
        std_price = item.standard_price
        total_val = qty * std_price
        return (
            ValuationResult(
                unit_price=std_price,
                total_value=total_val,
                source_method="STANDARD_PRICE",
                reference_id=req.resolved_item_code,
            ),
            None,
            False,
        )

    # Fallback if item is missing from master
    zero = Decimal("0.00")
    return (
        ValuationResult(
            unit_price=zero,
            total_value=zero,
            source_method="UNKNOWN",
            reference_id=None,
        ),
        None,
        False,
    )
