"""
backend/app/cli.py

Command-line interface for Corvo Engineering Procurement System.
Usage:
  python -m backend.app.cli process <input_csv> <output_csv> [--as-of YYYY-MM-DD] [--policy-version v5.0]
"""

import argparse
import csv
from datetime import datetime, date
from decimal import Decimal
import os
import sys

from backend.app.database import SessionLocal
from backend.app.policy_repo import PolicyRepository
from backend.app.policy_service import load_reference_data_from_db
from backend.engine.orchestrator import process_batch
from backend.engine.types import PRLineInput


def run_process_cli(
    input_path: str,
    output_path: str,
    as_of_str: str = None,
    policy_ver: str = None,
):
    print("=" * 65)
    print("Corvo Engineering - Procurement Engine Batch CLI")
    print("=" * 65)

    if not os.path.exists(input_path):
        print(f"[ERROR] Input file not found: {input_path}", file=sys.stderr)
        sys.exit(1)

    print(f"Reading input requisition batch: {input_path}")
    pr_inputs = []
    accepted_rows = 0
    rejected_rows = 0
    rejection_reasons = []

    with open(input_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for idx, r in enumerate(reader, start=1):
            pr_no = r.get("pr_no", "").strip()
            pr_line_str = r.get("pr_line", "1").strip()
            plant = r.get("plant", "").strip().upper()
            qty_str = r.get("quantity", "0").strip()

            # Pre-validation check
            try:
                qty = Decimal(qty_str)
            except Exception:
                qty = Decimal("0")

            if plant not in ("PUN1", "CHK1"):
                rejected_rows += 1
                rejection_reasons.append(f"Row {idx} ({pr_no}/{pr_line_str}): Invalid manufacturing plant '{plant}'")
            elif qty <= 0:
                rejected_rows += 1
                rejection_reasons.append(f"Row {idx} ({pr_no}/{pr_line_str}): Non-positive quantity ({qty})")
            else:
                accepted_rows += 1

            # Still include in pr_inputs so engine can record NOT_PROCESSED with zero silent drops
            c_dt = datetime.strptime(r["created_at"], "%Y-%m-%d %H:%M") if "created_at" in r and r["created_at"] else datetime.now()
            n_dt = datetime.strptime(r["need_by_date"], "%Y-%m-%d").date() if "need_by_date" in r and r["need_by_date"] else date.today()
            est_p_str = r.get("estimated_unit_price")
            est_p = Decimal(est_p_str) if est_p_str else None

            pr_inputs.append(
                PRLineInput(
                    pr_no=pr_no,
                    pr_line=int(pr_line_str),
                    created_at=c_dt,
                    requester=r.get("requester", ""),
                    department=r.get("department", ""),
                    plant=plant,
                    item_code=r.get("item_code") if r.get("item_code") else None,
                    description=r.get("description", ""),
                    quantity=qty,
                    uom=r.get("uom", "NOS"),
                    estimated_unit_price=est_p,
                    need_by_date=n_dt,
                    urgency=r.get("urgency", "Normal"),
                )
            )

    print(f"\nValidation Summary:")
    print(f"  * Total Requisition Lines : {len(pr_inputs)}")
    print(f"  * Lines Accepted          : {accepted_rows}")
    print(f"  * Lines Flagged/Rejected  : {rejected_rows}")
    if rejection_reasons:
        for reason in rejection_reasons[:5]:
            print(f"      - {reason}")
        if len(rejection_reasons) > 5:
            print(f"      - ... and {len(rejection_reasons) - 5} more")

    # Load database reference data & policy
    db = SessionLocal()
    try:
        ref_data = load_reference_data_from_db(db)
        policy_repo = PolicyRepository(db)

        # Process through pure Python orchestrator
        results = process_batch(pr_inputs, ref_data, policy_repo)

        # Output CSV with EXACT column order required by specification:
        # pr_no, pr_line, resolved_item_code, group_id, po_id, decision, route, supplier_id, unit_price, group_value_inr, suggested_supplier_ids, policy_version, reason
        fieldnames = [
            "pr_no",
            "pr_line",
            "resolved_item_code",
            "group_id",
            "po_id",
            "decision",
            "route",
            "supplier_id",
            "unit_price",
            "group_value_inr",
            "suggested_supplier_ids",
            "policy_version",
            "reason",
        ]

        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        with open(output_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for r in results:
                sugs = (
                    ";".join(r.suggested_supplier_ids)
                    if isinstance(r.suggested_supplier_ids, list)
                    else (r.suggested_supplier_ids or "")
                )
                writer.writerow({
                    "pr_no": r.pr_no,
                    "pr_line": r.pr_line,
                    "resolved_item_code": r.resolved_item_code or "",
                    "group_id": r.group_id or "",
                    "po_id": r.po_id or "",
                    "decision": r.decision,
                    "route": r.route,
                    "supplier_id": r.supplier_id or "",
                    "unit_price": f"{r.unit_price:.2f}" if r.unit_price is not None else "",
                    "group_value_inr": f"{r.group_value_inr:.2f}",
                    "suggested_supplier_ids": sugs,
                    "policy_version": r.policy_version,
                    "reason": r.reason,
                })

        # Summary of results
        po_count = sum(1 for r in results if r.decision == "PO")
        src_count = sum(1 for r in results if r.decision == "SOURCING_REQUEST")
        not_proc = sum(1 for r in results if r.decision == "NOT_PROCESSED")
        unique_pos = {r.po_id for r in results if r.po_id}

        print("\nProcessing Results Summary:")
        print(f"  * Purchase Orders Issued  : {po_count} lines across {len(unique_pos)} POs")
        print(f"  * Sourcing Requests       : {src_count} lines")
        print(f"  * Not Processed           : {not_proc} lines")
        print(f"\nSaved results to: {output_path}")
        print("=" * 65 + "\n")

    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(description="Corvo Procurement Engine CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    proc_parser = subparsers.add_parser("process", help="Process a PR batch CSV into decisions CSV")
    proc_parser.add_argument("input_csv", help="Path to input PR batch CSV")
    proc_parser.add_argument("output_csv", help="Path to output decisions CSV")
    proc_parser.add_argument("--as-of", dest="as_of", default=None, help="Evaluation as-of date (YYYY-MM-DD)")
    proc_parser.add_argument("--policy-version", dest="policy_version", default=None, help="Policy version label")

    args = parser.parse_args()

    if args.command == "process":
        run_process_cli(
            input_path=args.input_csv,
            output_path=args.output_csv,
            as_of_str=args.as_of,
            policy_ver=args.policy_version,
        )


if __name__ == "__main__":
    main()
