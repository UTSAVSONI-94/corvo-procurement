# Pure decision engine package (no database, FastAPI, or LLM dependencies)
from .types import (
    ItemMasterRecord,
    SupplierRecord,
    ContractLineRecord,
    ContractRecord,
    POHistoryRecord,
    PRLineInput,
    MatchedItemResult,
    RequirementGroup,
    ValuationResult,
    DecisionOutput,
    RankedSupplier,
    ScoreBreakdown,
)
from .item_matcher import match_item, normalize_text
from .clubber import club_pr_lines
from .contracts import (
    ContractLedger,
    find_applicable_contracts,
    select_best_contract,
)
from .valuation import (
    value_requirement,
    get_most_recent_po,
    has_active_supplier_purchase,
)
from .preferred_suppliers import (
    build_preferred_supplier_list,
    suggest_sourcing_suppliers,
    export_preferred_suppliers_csv,
    calculate_supplier_score,
)
from .policy_eval import evaluate_condition, evaluate_policy_rules, resolve_ref
from .schema import (
    PolicyDocument,
    DecisionRule,
    RuleOutcome,
    Condition,
    ParameterConfig,
    ThresholdsConfig,
    ConsolidationConfig,
)

__all__ = [
    "ItemMasterRecord",
    "SupplierRecord",
    "ContractLineRecord",
    "ContractRecord",
    "POHistoryRecord",
    "PRLineInput",
    "MatchedItemResult",
    "RequirementGroup",
    "ValuationResult",
    "DecisionOutput",
    "RankedSupplier",
    "ScoreBreakdown",
    "match_item",
    "normalize_text",
    "club_pr_lines",
    "ContractLedger",
    "find_applicable_contracts",
    "select_best_contract",
    "value_requirement",
    "get_most_recent_po",
    "has_active_supplier_purchase",
    "build_preferred_supplier_list",
    "suggest_sourcing_suppliers",
    "export_preferred_suppliers_csv",
    "calculate_supplier_score",
    "evaluate_condition",
    "evaluate_policy_rules",
    "resolve_ref",
    "PolicyDocument",
    "DecisionRule",
    "RuleOutcome",
    "Condition",
    "ParameterConfig",
    "ThresholdsConfig",
    "ConsolidationConfig",
]
