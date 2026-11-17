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
class ScoreBreakdown:
    component: str  # "frequency", "recency", "contract_held", "on_time", "quality"
    raw_value: Any
    weight: Decimal
    points: Decimal


@dataclass
class RankedSupplier:
    supplier_id: str
    supplier_name: str
    rank: int
    total_score: Decimal
    reference_price: Optional[Decimal]
    po_count: int
    recency_score: Decimal
    has_contract: bool
    on_time_pct: Decimal
    quality_rating: Decimal
    breakdown: List[ScoreBreakdown] = field(default_factory=list)


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


@dataclass
class ReferenceData:
    items: Dict[str, ItemMasterRecord]
    suppliers: Dict[str, SupplierRecord]
    contracts: List[ContractRecord]
    po_history: List[POHistoryRecord]


@dataclass
class BatchLineResult:
    pr_no: str
    pr_line: int
    resolved_item_code: str
    group_id: str
    po_id: Optional[str]
    decision: str
    route: str
    supplier_id: Optional[str]
    unit_price: Optional[Decimal]
    group_value_inr: Decimal
    suggested_supplier_ids: str  # ";"-separated e.g. "S043;S044;S042" or ""
    policy_version: str
    reason: str


