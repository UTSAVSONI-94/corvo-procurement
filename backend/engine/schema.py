from decimal import Decimal
from typing import Any, List, Optional, Union
from pydantic import BaseModel, Field


class ParameterConfig(BaseModel):
    club_window_days: int = Field(default=14, description="Days within which PR lines can be clubbed")
    need_by_window_days: int = Field(default=7, description="Need-by date tolerance window (+/- days)")
    po_history_days: int = Field(default=365, description="Lookback window for recent PO price and active purchases")
    preferred_history_days: int = Field(default=548, description="Lookback window for preferred supplier ranking")
    consolidation_window_hours: int = Field(default=24, description="Window to consolidate POs with same supplier/plant/route")
    min_rfq_suppliers: int = Field(default=3, description="Default number of suppliers to suggest for RFQ")
    min_rfp_suppliers: int = Field(default=5, description="Default number of suppliers to suggest for RFP")
    min_capex_suppliers: int = Field(default=5, description="Default number of suppliers to suggest for Capex sourcing")


class ThresholdsConfig(BaseModel):
    spot_limit: Decimal = Field(default=Decimal("200000.00"), description="Spot PO value ceiling in INR")
    emergency_limit: Decimal = Field(default=Decimal("500000.00"), description="Emergency PO value ceiling in INR")
    rfp_threshold: Decimal = Field(default=Decimal("1000000.00"), description="RFP value threshold in INR")


class ConsolidationConfig(BaseModel):
    same_fields: List[str] = Field(default=["supplier_id", "plant", "route"], description="Fields that must match to combine POs")
    window_hours: int = Field(default=24, description="Maximum hours between first and subsequent requirement")


class Condition(BaseModel):
    field: Optional[str] = None
    op: Optional[str] = None  # eq, ne, lt, lte, gt, gte, in, not_in
    value: Optional[Any] = None
    ref: Optional[str] = None  # e.g. "thresholds.spot_limit"
    all: Optional[List["Condition"]] = None
    any: Optional[List["Condition"]] = None
    not_: Optional["Condition"] = Field(default=None, alias="not")


class RuleOutcome(BaseModel):
    decision: str  # PO | SOURCING_REQUEST
    route: str  # CONTRACT_PO | EMERGENCY_PO | SPOT_PO | RFQ | RFP | CAPEX_SOURCING | NEW_ITEM_SOURCING | NOT_PROCESSED
    supplier_mode: str  # CONTRACT | PREFERRED_1 | SUGGEST_N | NONE
    suggest_count: Optional[int] = None
    price_mode: str  # CONTRACT_RATE | REFERENCE_PRICE | ESTIMATED_PRICE | NONE
    needs_approval: bool = False
    notes: Optional[str] = None


class DecisionRule(BaseModel):
    id: str  # e.g. "5.1"
    clause: str  # e.g. "Clause 5.1"
    name: str
    description: Optional[str] = None
    when: Condition
    outcome: RuleOutcome


class PolicyDocument(BaseModel):
    version: str
    effective_from: str  # YYYY-MM-DD
    title: str = "Corvo Engineering Procurement Policy"
    description: Optional[str] = None
    parameters: ParameterConfig = Field(default_factory=ParameterConfig)
    thresholds: ThresholdsConfig = Field(default_factory=ThresholdsConfig)
    consolidation: ConsolidationConfig = Field(default_factory=ConsolidationConfig)
    decision_rules: List[DecisionRule]
    guards: List[str] = Field(default_factory=lambda: [
        "BLOCKED_OR_INACTIVE_SUPPLIERS_NEVER_RECEIVE_PO",
        "BLOCKED_OR_INACTIVE_SUPPLIERS_NEVER_SUGGESTED_FOR_SOURCING"
    ])

