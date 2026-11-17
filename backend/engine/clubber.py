from datetime import date, datetime
from decimal import Decimal
from typing import Dict, List, Optional

from .types import PRLineInput, RequirementGroup


def club_pr_lines(
    lines: List[PRLineInput],
    resolved_item_codes: Dict[str, str],  # (pr_no, pr_line) -> resolved_item_code
    club_window_days: int = 14,
    need_by_window_days: int = 7,
) -> List[RequirementGroup]:
    """
    Implements Procurement Policy Section 2:
    - Sorts PR lines strictly by (created_at, pr_no, pr_line).
    - A line joins an existing requirement when:
        1. Same resolved item code
        2. Same plant
        3. Created within `club_window_days` (14 days) of the requirement's first line
        4. Need-by date is within `need_by_window_days` (7 days, either side) of the first line's need-by date
    - If it could join more than one requirement, it joins the earliest.
    - Policy 1.2: NEW items are NEVER clubbed.
    - Requirement date = first line's creation date.
    - Emergency = True if ANY line in the requirement is marked Emergency.
    """
    # Sort lines deterministically
    sorted_lines = sorted(
        lines,
        key=lambda l: (l.created_at, l.pr_no, l.pr_line),
    )

    requirements: List[RequirementGroup] = []
    req_counter = 1

    for line in sorted_lines:
        item_code = resolved_item_codes.get((line.pr_no, line.pr_line), line.item_code or "NEW")
        is_new_item = (item_code == "NEW")

        joined = False
        if not is_new_item:
            # Check existing requirements in order of creation (earliest first)
            for req in requirements:
                if req.resolved_item_code != item_code:
                    continue
                if req.plant != line.plant:
                    continue

                # Creation date window relative to first line's creation date
                created_delta = (line.created_at.date() - req.requirement_date).days
                if created_delta < 0 or created_delta > club_window_days:
                    continue

                # Need-by tolerance window relative to first line's need-by date
                need_by_delta = abs((line.need_by_date - req.first_need_by_date).days)
                if need_by_delta > need_by_window_days:
                    continue

                # Qualifies for earliest open requirement
                req.pr_lines.append(line)
                req.total_quantity += line.quantity
                if line.urgency.strip().lower() == "emergency":
                    req.is_emergency = True
                joined = True
                break

        if not joined:
            # Starts a new requirement
            is_emergency = (line.urgency.strip().lower() == "emergency")
            new_req = RequirementGroup(
                id=f"REQ-{req_counter:04d}",
                resolved_item_code=item_code,
                plant=line.plant,
                requirement_date=line.created_at.date(),
                first_need_by_date=line.need_by_date,
                total_quantity=line.quantity,
                uom=line.uom,
                is_emergency=is_emergency,
                pr_lines=[line],
            )
            requirements.append(new_req)
            req_counter += 1

    return requirements

