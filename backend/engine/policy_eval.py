from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional, Tuple, Union


def resolve_ref(ref_path: str, context: Dict[str, Any]) -> Any:
    """
    Resolve a dot-notated path against a nested policy context dictionary.
    Example: 'thresholds.spot_limit' -> context['thresholds']['spot_limit']
    """
    parts = ref_path.strip().split(".")
    curr = context
    for part in parts:
        if isinstance(curr, dict) and part in curr:
            curr = curr[part]
        elif hasattr(curr, part):
            curr = getattr(curr, part)
        else:
            raise KeyError(f"Reference '{ref_path}' could not be resolved at '{part}'")
    return curr


def _to_comparable(val: Any) -> Any:
    """Normalize numerical and string values for safe, consistent comparison."""
    if val is None:
        return None
    if isinstance(val, bool):
        return val
    if isinstance(val, (int, float, Decimal)):
        return Decimal(str(val))
    if isinstance(val, str):
        # Try to parse string numbers if comparison is numeric
        try:
            return Decimal(val)
        except InvalidOperation:
            return val
    return val


def _compare_leaf(field: str, op: str, expected: Any, facts: Dict[str, Any]) -> bool:
    actual = facts.get(field)
    
    # Clean and normalize comparable numbers
    norm_actual = _to_comparable(actual)
    norm_expected = _to_comparable(expected)

    if op == "eq":
        return norm_actual == norm_expected
    elif op == "ne":
        return norm_actual != norm_expected
    elif op == "lt":
        if norm_actual is None or norm_expected is None:
            return False
        return norm_actual < norm_expected
    elif op == "lte":
        if norm_actual is None or norm_expected is None:
            return False
        return norm_actual <= norm_expected
    elif op == "gt":
        if norm_actual is None or norm_expected is None:
            return False
        return norm_actual > norm_expected
    elif op == "gte":
        if norm_actual is None or norm_expected is None:
            return False
        return norm_actual >= norm_expected
    elif op == "in":
        if isinstance(expected, (list, tuple, set)):
            expected_set = {_to_comparable(x) for x in expected}
            return norm_actual in expected_set
        return False
    elif op == "not_in":
        if isinstance(expected, (list, tuple, set)):
            expected_set = {_to_comparable(x) for x in expected}
            return norm_actual not in expected_set
        return True
    else:
        raise ValueError(f"Unsupported comparison operator: '{op}'")


def evaluate_condition(
    condition: Union[Dict[str, Any], Any],
    facts: Dict[str, Any],
    policy_context: Dict[str, Any],
) -> bool:
    """
    Pure, safe condition evaluator. Zero eval() or exec().
    Supports:
      - all: [list of sub-conditions] (logical AND)
      - any: [list of sub-conditions] (logical OR)
      - not: sub-condition (logical NOT)
      - leaf: {field, op, value | ref}
    """
    if condition is None:
        return True

    # Support both pydantic models and raw dicts
    if hasattr(condition, "model_dump"):
        cond = condition.model_dump(by_alias=True)
    elif hasattr(condition, "dict"):
        cond = condition.dict(by_alias=True)
    else:
        cond = condition

    # 1. Combinator: all (AND)
    if "all" in cond and cond["all"] is not None:
        sub_conds = cond["all"]
        return all(evaluate_condition(sub, facts, policy_context) for sub in sub_conds)

    # 2. Combinator: any (OR)
    if "any" in cond and cond["any"] is not None:
        sub_conds = cond["any"]
        return any(evaluate_condition(sub, facts, policy_context) for sub in sub_conds)

    # 3. Combinator: not (NOT)
    if "not" in cond and cond["not"] is not None:
        return not evaluate_condition(cond["not"], facts, policy_context)

    # 4. Leaf condition
    field = cond.get("field")
    op = cond.get("op")
    if not field or not op:
        # Empty condition evaluates to True
        return True

    if "ref" in cond and cond["ref"]:
        expected = resolve_ref(cond["ref"], policy_context)
    else:
        expected = cond.get("value")

    return _compare_leaf(field, op, expected, facts)


def evaluate_policy_rules(
    rules: List[Union[Dict[str, Any], Any]],
    facts: Dict[str, Any],
    policy_context: Dict[str, Any],
) -> Tuple[Optional[Dict[str, Any]], str]:
    """
    Applies an ordered list of decision rules to the supplied facts dictionary.
    Returns the first matching rule and a reason string.
    If no rule matches, returns (None, 'NO_RULE_MATCHED').
    """
    for rule in rules:
        if hasattr(rule, "model_dump"):
            r_dict = rule.model_dump()
        elif hasattr(rule, "dict"):
            r_dict = rule.dict()
        else:
            r_dict = rule
        when_cond = r_dict.get("when", {})
        if evaluate_condition(when_cond, facts, policy_context):
            clause = r_dict.get("clause", "Policy Rule")
            name = r_dict.get("name", "")
            return r_dict, f"Applied {clause}: {name}"

    return None, "NO_RULE_MATCHED"
