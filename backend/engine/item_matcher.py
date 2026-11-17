import re
from typing import Dict, List, Optional, Set, Tuple
from rapidfuzz import fuzz

from .types import ItemMasterRecord, MatchedItemResult

# Common industrial abbreviations and synonyms in manufacturing procurement
ABBREVIATIONS = {
    r"\bbrg\b": "bearing",
    r"\bhyd\b": "hydraulic",
    r"\bpneu\b": "pneumatic",
    r"\bcyl\b": "cylinder",
    r"\bgr\b": "grade",
    r"\bwelding rod\b": "welding electrode",
    r"\bmnt\b": "maintenance",
    r"\bfor maintenance\b": "",
    r"\bas per sample\b": "",
    r"\brepeat\b": "",
    r"\burgent\b": "",
    r"\"": " inch ",
}


def normalize_text(text: str) -> str:
    """Normalize free text by expanding abbreviations and standardizing delimiters."""
    if not text:
        return ""
    s = text.lower().strip()

    # Expand common abbreviations
    for pattern, replacement in ABBREVIATIONS.items():
        s = re.sub(pattern, replacement, s)

    # Standardize spaces and punctuation (keep hyphens and forward slashes for specs like 6205-2RS, 1/2 inch)
    s = re.sub(r"[^\w\s\-\/\.]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def extract_spec_tokens(text: str) -> Set[str]:
    """
    Extract critical numerical/specification tokens that must match exactly.
    Examples: '6205', '6308', '32210', 'm10', 'm16', '50x100', '600x900'.
    """
    raw = text.lower()
    tokens = set()
    
    # 1. Bearing & part numbers (4 to 5 digits, e.g. 6205, 6308, 32210, 6061)
    for m in re.findall(r"\b\d{4,5}\b", raw):
        tokens.add(m)

    # 2. Metric bolt/screw sizes (e.g. m8, m10, m12, m16, m18)
    for m in re.findall(r"\bm\d{1,2}\b", raw):
        tokens.add(m)

    # 3. Dimensions (e.g. 50x100, 600x900, 1250x2500, 45x62x8)
    for m in re.findall(r"\b\d+x\d+(?:x\d+)?\b", raw):
        tokens.add(m)

    # 4. Critical suffix codes (e.g. 2rs, zz, pnp, er70s, e6013)
    for m in re.findall(r"\b(2rs|zz|pnp|er70s|e6013)\b", raw):
        tokens.add(m)

    return tokens


def match_item(
    user_item_code: Optional[str],
    description: str,
    item_master: Dict[str, ItemMasterRecord],
    confidence_threshold: float = 70.0,
    ambiguity_margin: float = 5.0,
) -> MatchedItemResult:
    """
    Matches item based on Policy 1.1 / 1.2:
    - If user gave an item_code that exists in item_master, use it directly (confidence = 100.0).
    - Else match free text with token normalization and strict spec conflict rejection.
    - If confidence < confidence_threshold -> returns item_code = "NEW".
    """
    # 1. Exact Item Code match
    if user_item_code and user_item_code.strip():
        code = user_item_code.strip().upper()
        if code in item_master:
            return MatchedItemResult(
                item_code=code,
                confidence=100.0,
                is_new=False,
                candidates=[{"item_code": code, "description": item_master[code].description, "score": 100.0}],
                match_reason=f"Matched exact item code {code} provided by requester",
            )

    # 2. Free-text fuzzy matching
    norm_query = normalize_text(description)
    query_specs = extract_spec_tokens(description)

    candidates = []
    for code, item in item_master.items():
        norm_item_desc = normalize_text(item.description)
        item_specs = extract_spec_tokens(item.description)

        # Check for hard spec conflicts (e.g. bearing 6205 must never match 6308)
        if query_specs and item_specs:
            # If both have bearing numbers or bolt sizes and they don't overlap, reject!
            query_nums = {t for t in query_specs if t.isdigit() and len(t) >= 4}
            item_nums = {t for t in item_specs if t.isdigit() and len(t) >= 4}
            if query_nums and item_nums and not (query_nums & item_nums):
                continue

            query_bolts = {t for t in query_specs if t.startswith("m") and t[1:].isdigit()}
            item_bolts = {t for t in item_specs if t.startswith("m") and t[1:].isdigit()}
            if query_bolts and item_bolts and not (query_bolts & item_bolts):
                continue

            query_dims = {t for t in query_specs if "x" in t}
            item_dims = {t for t in item_specs if "x" in t}
            if query_dims and item_dims and not (query_dims & item_dims):
                continue

        # Compute fuzzy token similarity
        token_set_score = fuzz.token_set_ratio(norm_query, norm_item_desc)
        token_sort_score = fuzz.token_sort_ratio(norm_query, norm_item_desc)
        partial_score = fuzz.partial_ratio(norm_query, norm_item_desc)

        # Weighted score emphasizing token overlap
        final_score = (token_set_score * 0.5) + (token_sort_score * 0.3) + (partial_score * 0.2)

        # Boost score if specs match exactly
        if query_specs and item_specs and query_specs.issubset(item_specs):
            final_score = min(100.0, final_score + 10.0)

        candidates.append({
            "item_code": code,
            "description": item.description,
            "score": round(final_score, 1),
        })

    # Sort descending by score
    candidates.sort(key=lambda c: c["score"], reverse=True)
    top_candidates = candidates[:5]

    if not top_candidates or top_candidates[0]["score"] < confidence_threshold:
        return MatchedItemResult(
            item_code="NEW",
            confidence=top_candidates[0]["score"] if top_candidates else 0.0,
            is_new=True,
            candidates=top_candidates,
            match_reason=f"No master item matched above {confidence_threshold}% threshold; treated as NEW item",
        )

    best = top_candidates[0]
    reason = f"Fuzzy matched to '{best['description']}' with {best['score']}% confidence"

    # Check for ambiguity with second candidate
    if len(top_candidates) > 1:
        second = top_candidates[1]
        if (best["score"] - second["score"]) <= ambiguity_margin:
            reason += f" (Note: Close candidate '{second['item_code']}' scored {second['score']}%)"

    return MatchedItemResult(
        item_code=best["item_code"],
        confidence=best["score"],
        is_new=False,
        candidates=top_candidates,
        match_reason=reason,
    )
