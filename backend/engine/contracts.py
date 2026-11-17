from datetime import date
from decimal import Decimal
from typing import Dict, List, Optional, Tuple

from .types import ContractRecord, ContractLineRecord, SupplierRecord


class ContractLedger:
    """
    In-memory ledger tracking contract ceiling consumption during a batch run.
    Initialized from contract register consumed_value (or 0 for new PDF contracts).
    Requirements consume ceiling sequentially in requirement-date order.
    """
    def __init__(self, contracts: Dict[str, ContractRecord]):
        self.contracts = contracts
        # Initialize ledger balances from consumed_value
        self.consumed_balances: Dict[str, Decimal] = {
            cid: Decimal(str(c.consumed_value)) for cid, c in contracts.items()
        }

    def get_consumed(self, contract_id: str) -> Decimal:
        return self.consumed_balances.get(contract_id, Decimal("0.00"))

    def get_remaining_ceiling(self, contract_id: str) -> Decimal:
        contract = self.contracts.get(contract_id)
        if not contract:
            return Decimal("0.00")
        consumed = self.get_consumed(contract_id)
        return max(Decimal("0.00"), contract.value_ceiling - consumed)

    def has_room(self, contract_id: str, requirement_value: Decimal) -> bool:
        contract = self.contracts.get(contract_id)
        if not contract:
            return False
        return (self.get_consumed(contract_id) + requirement_value) <= contract.value_ceiling

    def consume(self, contract_id: str, amount: Decimal):
        if contract_id in self.consumed_balances:
            self.consumed_balances[contract_id] += amount


def find_applicable_contracts(
    item_code: str,
    requirement_date: date,
    contracts: Dict[str, ContractRecord],
    suppliers: Dict[str, SupplierRecord],
) -> List[Tuple[ContractRecord, ContractLineRecord]]:
    """
    Policy Clause 4.1:
    A rate contract applies to a requirement if:
      1. Contract covers the item (contract_lines)
      2. Requirement date falls between start_date and end_date (inclusive)
      3. Contract supplier is Active in the supplier master
    Returns list of (ContractRecord, ContractLineRecord).
    """
    applicable = []
    for cid, contract in contracts.items():
        if item_code not in contract.lines:
            continue

        # Date validity check
        if not (contract.start_date <= requirement_date <= contract.end_date):
            continue

        # Supplier active check
        supplier = suppliers.get(contract.supplier_id)
        if not supplier or supplier.status.strip().lower() != "active":
            continue

        line = contract.lines[item_code]
        applicable.append((contract, line))

    return applicable


def select_best_contract(
    item_code: str,
    requirement_date: date,
    quantity: Decimal,
    contracts: Dict[str, ContractRecord],
    suppliers: Dict[str, SupplierRecord],
    ledger: ContractLedger,
) -> Tuple[Optional[ContractRecord], Optional[Decimal], bool, Decimal]:
    """
    Evaluates contract applicability and ceiling per Policy Clauses 4.1 to 4.3:
    Returns:
      (selected_contract, unit_rate, contract_usable, lowest_applicable_rate)
    Where:
      - selected_contract: ContractRecord to be used for PO, or None
      - unit_rate: Rate of the contract to be used (or lowest applicable if all out of ceiling)
      - contract_usable: True if a contract with sufficient ceiling is available
      - lowest_applicable_rate: Lowest rate among all valid applicable contracts
    """
    applicable = find_applicable_contracts(item_code, requirement_date, contracts, suppliers)
    if not applicable:
        return None, None, False, Decimal("0.00")

    # Find lowest rate across all applicable contracts (Policy 3.1a fallback)
    lowest_rate = min(line.rate for _, line in applicable)

    # Check ceiling for each applicable contract
    # Clause 4.3: use the one with the lowest rate that still has enough ceiling
    eligible = []
    for contract, line in applicable:
        req_val_at_rate = quantity * line.rate
        if ledger.has_room(contract.contract_id, req_val_at_rate):
            eligible.append((contract, line))

    if not eligible:
        # All applicable contracts are out of ceiling
        return None, lowest_rate, False, lowest_rate

    # Sort eligible contracts by rate ascending (lowest rate first)
    eligible.sort(key=lambda item: (item[1].rate, item[0].start_date))
    best_contract, best_line = eligible[0]

    return best_contract, best_line.rate, True, lowest_rate

