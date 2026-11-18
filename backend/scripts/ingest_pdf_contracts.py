"""
backend/scripts/ingest_pdf_contracts.py

Automated script to:
1. Scan all PDF contracts in kit/contracts/pdf/.
2. Extract text and parse structured data via the contract service.
3. Compare PDF contract values against the contract register (detecting any mismatches).
4. Ingest PDF-only contracts (such as RC-2026-031) with source='PDF_EXTRACTED' and consumed_value=0.
5. Report any items requiring visual verification.
"""

from decimal import Decimal
import glob
import os
import sys

from backend.app.database import SessionLocal
from backend.app.models import Contract, ContractLine
from backend.app.contract_service import (
    extract_text_from_pdf,
    parse_contract_text,
    save_or_update_contract,
    ContractConfirmRequest,
)


def run_contract_ingestion():
    print("\n" + "=" * 70)
    print("      CORVO PROCUREMENT - CONTRACT RECONCILIATION & PDF INGESTION")
    print("=" * 70)

    db = SessionLocal()
    pdf_dir = "kit/contracts/pdf"
    pdf_files = sorted(glob.glob(os.path.join(pdf_dir, "*.pdf")))

    if not pdf_files:
        print(f"No PDF contracts found in {pdf_dir}")
        db.close()
        return

    print(f"\nDiscovered {len(pdf_files)} PDF contract file(s) in {pdf_dir}:")
    for p in pdf_files:
        print(f"  - {os.path.basename(p)}")

    # Load register contracts from DB
    register_contracts = {
        c.contract_id: c for c in db.query(Contract).filter_by(source="REGISTER").all()
    }

    in_both_count = 0
    pdf_only_count = 0
    mismatches = []
    verify_by_eye = []

    print("\n" + "-" * 70)
    print("Step 1: Extracting & Comparing Contracts")
    print("-" * 70)

    for pdf_path in pdf_files:
        filename = os.path.basename(pdf_path)
        try:
            text = extract_text_from_pdf(pdf_path)
            preview = parse_contract_text(text, db, pdf_path=pdf_path)
        except Exception as e:
            print(f"  [ERROR] Failed to extract {filename}: {e}")
            verify_by_eye.append(f"{filename}: Extraction failed ({e})")
            continue

        cid = preview.contract_id

        if cid in register_contracts:
            in_both_count += 1
            reg_c = register_contracts[cid]
            # Compare fields
            diffs = []
            if preview.supplier_id != reg_c.supplier_id:
                diffs.append(f"supplier_id: PDF={preview.supplier_id} vs REG={reg_c.supplier_id}")
            if preview.start_date != reg_c.start_date.isoformat():
                diffs.append(f"start_date: PDF={preview.start_date} vs REG={reg_c.start_date}")
            if preview.end_date != reg_c.end_date.isoformat():
                diffs.append(f"end_date: PDF={preview.end_date} vs REG={reg_c.end_date}")
            if preview.value_ceiling != reg_c.value_ceiling:
                diffs.append(f"ceiling: PDF=₹{preview.value_ceiling:,.2f} vs REG=₹{reg_c.value_ceiling:,.2f}")

            # Check lines
            reg_lines = {l.item_code: l for l in reg_c.lines}
            if len(preview.lines) != len(reg_lines):
                diffs.append(f"line items count: PDF={len(preview.lines)} vs REG={len(reg_lines)}")
            else:
                for pl in preview.lines:
                    if pl.item_code not in reg_lines:
                        diffs.append(f"item {pl.item_code} in PDF but not in REG")
                    else:
                        rl = reg_lines[pl.item_code]
                        if pl.rate != rl.rate:
                            diffs.append(f"rate for {pl.item_code}: PDF=₹{pl.rate} vs REG=₹{rl.rate}")

            if diffs:
                print(f"  * {cid:<12} (Both) -> MISMATCH DETECTED:")
                for d in diffs:
                    print(f"      - {d}")
                mismatches.append((cid, diffs))
                verify_by_eye.append(f"{cid} ({filename}): {', '.join(diffs)}")
            else:
                print(f"  * {cid:<12} (Both) -> 100% MATCH ({len(preview.lines)} lines, ceiling ₹{preview.value_ceiling:,.2f})")
                # Update pdf_path on register contract if not set
                if not reg_c.pdf_path:
                    reg_c.pdf_path = pdf_path
                    db.commit()

        else:
            # Contract is PDF-ONLY (e.g. RC-2026-031)
            pdf_only_count += 1
            print(f"  * {cid:<12} (PDF-ONLY) -> Extracting & Ingesting as active contract:")
            print(f"      Supplier : {preview.supplier_id} ({preview.supplier_name})")
            print(f"      Validity : {preview.start_date} to {preview.end_date}")
            print(f"      Ceiling  : ₹{preview.value_ceiling:,.2f} (Consumed: ₹0.00)")
            print(f"      Items    : {len(preview.lines)} line item(s)")
            for l in preview.lines:
                print(f"        - {l.item_code} | {l.description} | {l.uom} | ₹{l.rate}")

            # Ingest into database
            confirm_req = ContractConfirmRequest(
                contract_id=preview.contract_id,
                supplier_id=preview.supplier_id,
                supplier_name=preview.supplier_name,
                start_date=preview.start_date,
                end_date=preview.end_date,
                value_ceiling=preview.value_ceiling,
                consumed_value=Decimal("0.00"),
                source="PDF_EXTRACTED",
                pdf_path=pdf_path,
                lines=preview.lines,
                confirmed_by="Ingestion Script",
            )
            saved = save_or_update_contract(confirm_req, db)
            print(f"      Status   : Successfully saved to DB with source='{saved.source}'.")

            if preview.confidence_score < 0.9 or preview.ambiguities:
                verify_by_eye.append(f"{cid} ({filename}): Confidence={preview.confidence_score}, ambiguities={preview.ambiguities}")

    print("\n" + "-" * 70)
    print("Summary:")
    print(f"  * Total PDFs Processed   : {len(pdf_files)}")
    print(f"  * Matched Register & PDF : {in_both_count}")
    print(f"  * PDF-Only Ingested      : {pdf_only_count}")
    print(f"  * Register-Only (No PDF) : {len(register_contracts) - in_both_count}")
    print(f"  * Discrepancies / Mismatches: {len(mismatches)}")

    if verify_by_eye:
        print("\n[!] Recommended Visual Verification (By Eye):")
        for v in verify_by_eye:
            print(f"  - {v}")
    else:
        print("\nAll contracts matched register records with 100% data integrity.")

    print("=" * 70 + "\n")
    db.close()


if __name__ == "__main__":
    run_contract_ingestion()
