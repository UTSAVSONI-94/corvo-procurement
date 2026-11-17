from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional, Dict, Any


@dataclass
class ItemMasterRecord:
    item_code: str
    description: str
    uom: str
    category: str
    item_type: str  # Material, Service, Capex
    standard_price: Decimal


@dataclass
class SupplierRecord:
    supplier_id: str
    name: str
    city: str
    categories: str
    status: str  # Active, Blocked, Inactive
    on_time_pct: Decimal
    quality_rating: Decimal


@dataclass
class ContractLineRecord:
    contract_id: str
    item_code: str
    rate: Decimal
    uom: str
    description: str = ""


@dataclass
class ContractRecord:
    contract_id: str
    supplier_id: str
    supplier_name: str
    start_date: date
    end_date: date
    value_ceiling: Decimal
    consumed_value: Decimal = Decimal("0.00")
    lines: Dict[str, ContractLineRecord] = field(default_factory=dict)  # item_code -> line


@dataclass
class POHistoryRecord:
    po_number: str
    po_date: date
    supplier_id: str
    item_code: str
    quantity: Decimal
    uom: str
    unit_price: Decimal
    plant: str
    delivered_on_time: bool = True


@dataclass
class PRLineInput:
    pr_no: str
    pr_line: int
    created_at: datetime
    requester: str
    department: str
    plant: str
    item_code: Optional[str]
    description: str
    quantity: Decimal
    uom: str
    estimated_unit_price: Optional[Decimal]
    need_by_date: date
    urgency: str = "Normal"


@dataclass
class MatchedItemResult:
    item_code: str  # ITM-xxxx or "NEW"
    confidence: float
    is_new: bool
    candidates: List[Dict[str, Any]]
    match_reason: str


@dataclass
class RequirementGroup:
    id: str  # e.g. REQ-2026-0001
    resolved_item_code: str  # ITM-xxxx or "NEW"
    plant: str
    requirement_date: date
    first_need_by_date: date
    total_quantity: Decimal
    uom: str
    is_emergency: bool
    pr_lines: List[PRLineInput]


@dataclass
class ValuationResult:
    unit_price: Decimal
    total_value: Decimal
    source_method: str  # "CONTRACT", "RECENT_PO", "STANDARD_PRICE", "ESTIMATED_PRICE"
    reference_id: Optional[str] = None  # contract_id or po_number


@dataclass
class DecisionOutput:
    requirement_id: str
    decision: str  # "PO" or "SOURCING_REQUEST"
    route: str  # "CONTRACT_PO", "EMERGENCY_PO", "SPOT_PO", "RFQ", "RFP", "CAPEX_SOURCING", "NEW_ITEM_SOURCING", "NOT_PROCESSED"
    supplier_id: Optional[str] = None
    unit_price: Optional[Decimal] = None
    group_value_inr: Decimal = Decimal("0.00")
    suggested_supplier_ids: Optional[str] = None  # S014;S013;S016
    contract_id: Optional[str] = None
    po_id_ref: Optional[str] = None
    clause: str = ""
    reason: str = ""
