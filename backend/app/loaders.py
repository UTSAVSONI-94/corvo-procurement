import csv
import json
import os
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Dict, Any, List, Tuple

from sqlalchemy.orm import Session

from .models import (
    Plant,
    Item,
    Supplier,
    POHistory,
    Contract,
    ContractLine,
    PRLine,
    PolicyVersion,
    User,
    DataQualityIssue,
)


def normalize_str(val: Any) -> str:
    if val is None:
        return ""
    return str(val).strip()


def parse_decimal(val: Any, default: Decimal = Decimal("0.00")) -> Decimal:
    if val is None or str(val).strip() == "":
        return default
    try:
        return Decimal(str(val).strip())
    except InvalidOperation:
        return default


def parse_date(val: Any) -> datetime.date:
    s = normalize_str(val)
    return datetime.strptime(s, "%Y-%m-%d").date()


def parse_datetime(val: Any) -> datetime:
    s = normalize_str(val)
    if len(s) == 16:
        return datetime.strptime(s, "%Y-%m-%d %H:%M")
    return datetime.strptime(s, "%Y-%m-%d %H:%M:%S")


class DataLoader:
    def __init__(self, db: Session, base_dir: str = "kit"):
        self.db = db
        self.base_dir = base_dir
        self.summary = {}

    def log_issue(
        self,
        file_source: str,
        row_id: str,
        issue_type: str,
        description: str,
        raw_data: Any = None,
        severity: str = "WARNING",
    ):
        issue = DataQualityIssue(
            file_source=file_source,
            row_identifier=str(row_id),
            issue_type=issue_type,
            issue_description=description,
            raw_data=json.dumps(raw_data) if raw_data else None,
            severity=severity,
        )
        self.db.add(issue)

    def load_plants(self, filepath: str = None) -> int:
        path = filepath or os.path.join(self.base_dir, "master_data", "plants.csv")
        with open(path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            count = 0
            for row in reader:
                code = normalize_str(row.get("plant")).upper()
                name = normalize_str(row.get("name"))
                if not code:
                    self.log_issue("plants.csv", count, "EMPTY_PLANT_CODE", "Missing plant code", row, "ERROR")
                    continue
                plant = self.db.query(Plant).filter_by(plant_code=code).first()
                if not plant:
                    plant = Plant(plant_code=code, name=name)
                    self.db.add(plant)
                else:
                    plant.name = name
                count += 1
            self.db.commit()
            self.summary["plants"] = count
            return count

    def load_items(self, filepath: str = None) -> int:
        path = filepath or os.path.join(self.base_dir, "master_data", "item_master.csv")
        with open(path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            count = 0
            for row in reader:
                code = normalize_str(row.get("item_code"))
                desc = normalize_str(row.get("description"))
                uom = normalize_str(row.get("uom")).upper()
                category = normalize_str(row.get("category"))
                item_type = normalize_str(row.get("item_type"))
                std_price = parse_decimal(row.get("standard_price"))

                search_text = f"{code} {desc} {category}".lower()

                item = self.db.query(Item).filter_by(item_code=code).first()
                if not item:
                    item = Item(
                        item_code=code,
                        description=desc,
                        uom=uom,
                        category=category,
                        item_type=item_type,
                        standard_price=std_price,
                        search_text=search_text,
                    )
                    self.db.add(item)
                else:
                    item.description = desc
                    item.uom = uom
                    item.category = category
                    item.item_type = item_type
                    item.standard_price = std_price
                    item.search_text = search_text
                count += 1
            self.db.commit()
            self.summary["items"] = count
            return count

    def load_suppliers(self, filepath: str = None) -> int:
        path = filepath or os.path.join(self.base_dir, "master_data", "supplier_master.csv")
        self.db.query(DataQualityIssue).filter_by(file_source="supplier_master.csv").delete()
        with open(path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            count = 0
            for row in reader:
                sid = normalize_str(row.get("supplier_id"))
                name = normalize_str(row.get("name"))
                city = normalize_str(row.get("city"))
                cats = normalize_str(row.get("categories"))
                status = normalize_str(row.get("status"))
                on_time = parse_decimal(row.get("on_time_pct"))
                quality = parse_decimal(row.get("quality_rating"))

                if status in ("Blocked", "Inactive"):
                    self.log_issue(
                        "supplier_master.csv",
                        sid,
                        f"SUPPLIER_{status.upper()}",
                        f"Supplier {name} ({sid}) is marked as {status}",
                        row,
                        "WARNING",
                    )

                supplier = self.db.query(Supplier).filter_by(supplier_id=sid).first()
                if not supplier:
                    supplier = Supplier(
                        supplier_id=sid,
                        name=name,
                        city=city,
                        categories=cats,
                        status=status,
                        on_time_pct=on_time,
                        quality_rating=quality,
                    )
                    self.db.add(supplier)
                else:
                    supplier.name = name
                    supplier.city = city
                    supplier.categories = cats
                    supplier.status = status
                    supplier.on_time_pct = on_time
                    supplier.quality_rating = quality
                count += 1
            self.db.commit()
            self.summary["suppliers"] = count
            return count

    def load_po_history(self, filepath: str = None) -> int:
        path = filepath or os.path.join(self.base_dir, "master_data", "po_history.csv")
        self.db.query(DataQualityIssue).filter_by(file_source="po_history.csv").delete()
        existing_items = {i.item_code for i in self.db.query(Item.item_code).all()}
        existing_suppliers = {s.supplier_id for s in self.db.query(Supplier.supplier_id).all()}
        existing_plants = {p.plant_code for p in self.db.query(Plant.plant_code).all()}

        with open(path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            count = 0
            for row in reader:
                po_num = normalize_str(row.get("po_number"))
                po_dt = parse_date(row.get("po_date"))
                sid = normalize_str(row.get("supplier_id"))
                code = normalize_str(row.get("item_code"))
                qty = parse_decimal(row.get("quantity"))
                uom = normalize_str(row.get("uom")).upper()
                price = parse_decimal(row.get("unit_price"))
                plant = normalize_str(row.get("plant")).upper()
                delivered = normalize_str(row.get("delivered_on_time")).lower() == "true"

                # Check FK orphan references rather than crashing
                if sid not in existing_suppliers:
                    self.log_issue(
                        "po_history.csv",
                        po_num,
                        "ORPHAN_SUPPLIER_FK",
                        f"Supplier {sid} does not exist in supplier master",
                        row,
                        "ERROR",
                    )
                    continue
                if code not in existing_items:
                    self.log_issue(
                        "po_history.csv",
                        po_num,
                        "ORPHAN_ITEM_FK",
                        f"Item {code} does not exist in item master",
                        row,
                        "ERROR",
                    )
                    continue
                if plant not in existing_plants:
                    self.log_issue(
                        "po_history.csv",
                        po_num,
                        "ORPHAN_PLANT_FK",
                        f"Plant {plant} does not exist in plants master",
                        row,
                        "ERROR",
                    )
                    continue

                po_rec = self.db.query(POHistory).filter_by(po_number=po_num).first()
                if not po_rec:
                    po_rec = POHistory(
                        po_number=po_num,
                        po_date=po_dt,
                        supplier_id=sid,
                        item_code=code,
                        quantity=qty,
                        uom=uom,
                        unit_price=price,
                        plant=plant,
                        delivered_on_time=delivered,
                    )
                    self.db.add(po_rec)
                count += 1
            self.db.commit()
            self.summary["po_history"] = count
            return count

    def load_contracts(self, filepath: str = None) -> int:
        path = filepath or os.path.join(self.base_dir, "contracts", "contract_register.csv")
        self.db.query(DataQualityIssue).filter_by(file_source="contract_register.csv").delete()
        existing_suppliers = {s.supplier_id: s.status for s in self.db.query(Supplier).all()}

        with open(path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            count = 0
            for row in reader:
                cid = normalize_str(row.get("contract_id"))
                sid = normalize_str(row.get("supplier_id"))
                sname = normalize_str(row.get("supplier_name"))
                s_dt = parse_date(row.get("start_date"))
                e_dt = parse_date(row.get("end_date"))
                val_cap = parse_decimal(row.get("value_cap"))
                consumed = parse_decimal(row.get("consumed_value"))

                if sid not in existing_suppliers:
                    self.log_issue(
                        "contract_register.csv",
                        cid,
                        "ORPHAN_SUPPLIER_FK",
                        f"Contract {cid} references non-existent supplier {sid}",
                        row,
                        "ERROR",
                    )
                    continue

                if existing_suppliers.get(sid) != "Active":
                    self.log_issue(
                        "contract_register.csv",
                        cid,
                        "CONTRACT_NON_ACTIVE_SUPPLIER",
                        f"Contract {cid} has supplier {sid} with status {existing_suppliers.get(sid)}",
                        row,
                        "WARNING",
                    )

                if e_dt < s_dt:
                    self.log_issue(
                        "contract_register.csv",
                        cid,
                        "INVALID_DATE_RANGE",
                        f"Contract {cid} end date {e_dt} is before start date {s_dt}",
                        row,
                        "ERROR",
                    )

                contract = self.db.query(Contract).filter_by(contract_id=cid).first()
                if not contract:
                    contract = Contract(
                        contract_id=cid,
                        supplier_id=sid,
                        supplier_name=sname,
                        start_date=s_dt,
                        end_date=e_dt,
                        value_ceiling=val_cap,
                        consumed_value=consumed,
                        source="REGISTER",
                    )
                    self.db.add(contract)
                else:
                    contract.supplier_id = sid
                    contract.supplier_name = sname
                    contract.start_date = s_dt
                    contract.end_date = e_dt
                    contract.value_ceiling = val_cap
                    contract.consumed_value = consumed
                count += 1
            self.db.commit()
            self.summary["contracts"] = count
            return count

    def load_contract_lines(self, filepath: str = None) -> int:
        path = filepath or os.path.join(self.base_dir, "contracts", "contract_lines.csv")
        self.db.query(DataQualityIssue).filter_by(file_source="contract_lines.csv").delete()
        existing_contracts = {c.contract_id for c in self.db.query(Contract.contract_id).all()}
        existing_items = {i.item_code for i in self.db.query(Item.item_code).all()}

        with open(path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            count = 0
            for row in reader:
                cid = normalize_str(row.get("contract_id"))
                code = normalize_str(row.get("item_code"))
                desc = normalize_str(row.get("description"))
                uom = normalize_str(row.get("uom")).upper()
                rate = parse_decimal(row.get("rate"))

                if cid not in existing_contracts:
                    self.log_issue(
                        "contract_lines.csv",
                        f"{cid}_{code}",
                        "ORPHAN_CONTRACT_FK",
                        f"Contract {cid} does not exist in contracts table",
                        row,
                        "ERROR",
                    )
                    continue

                if code not in existing_items:
                    self.log_issue(
                        "contract_lines.csv",
                        f"{cid}_{code}",
                        "ORPHAN_ITEM_FK",
                        f"Item {code} does not exist in items table",
                        row,
                        "ERROR",
                    )
                    continue

                line = self.db.query(ContractLine).filter_by(contract_id=cid, item_code=code).first()
                if not line:
                    line = ContractLine(
                        contract_id=cid,
                        item_code=code,
                        description=desc,
                        uom=uom,
                        rate=rate,
                    )
                    self.db.add(line)
                else:
                    line.description = desc
                    line.uom = uom
                    line.rate = rate
                count += 1
            self.db.commit()
            self.summary["contract_lines"] = count
            return count

    def load_pr_batch(self, filepath: str = None) -> int:
        path = filepath or os.path.join(self.base_dir, "pr_batches", "sample_pr_batch.csv")
        self.db.query(DataQualityIssue).filter_by(file_source="sample_pr_batch.csv").delete()
        existing_plants = {p.plant_code for p in self.db.query(Plant.plant_code).all()}
        existing_items = {i.item_code for i in self.db.query(Item.item_code).all()}

        with open(path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            count = 0
            for row in reader:
                pr_no = normalize_str(row.get("pr_no"))
                pr_line_num = int(row.get("pr_line", 1))
                c_dt = parse_datetime(row.get("created_at"))
                req = normalize_str(row.get("requester"))
                dept = normalize_str(row.get("department"))
                plant = normalize_str(row.get("plant")).upper()
                code = normalize_str(row.get("item_code"))
                desc = normalize_str(row.get("description"))
                qty = parse_decimal(row.get("quantity"))
                uom = normalize_str(row.get("uom")).upper()
                est_price_str = row.get("estimated_unit_price")
                est_price = parse_decimal(est_price_str, None) if est_price_str else None
                need_by = parse_date(row.get("need_by_date"))
                urgency = normalize_str(row.get("urgency")) or "Normal"

                # Data quality logging without dropping rows
                row_key = f"{pr_no}/{pr_line_num}"
                if plant not in existing_plants:
                    self.log_issue(
                        "sample_pr_batch.csv",
                        row_key,
                        "INVALID_PLANT",
                        f"Plant code '{plant}' is not recognized in plants master",
                        row,
                        "WARNING",
                    )

                if qty <= Decimal("0"):
                    self.log_issue(
                        "sample_pr_batch.csv",
                        row_key,
                        "ZERO_QUANTITY",
                        f"Quantity is {qty}; requested amount must be positive",
                        row,
                        "WARNING",
                    )

                if not code:
                    self.log_issue(
                        "sample_pr_batch.csv",
                        row_key,
                        "BLANK_ITEM_CODE",
                        f"Item code is blank; description: '{desc}'",
                        row,
                        "WARNING",
                    )
                elif code not in existing_items:
                    self.log_issue(
                        "sample_pr_batch.csv",
                        row_key,
                        "UNKNOWN_ITEM_CODE",
                        f"Item code '{code}' does not exist in item master",
                        row,
                        "WARNING",
                    )

                pr_line = self.db.query(PRLine).filter_by(pr_no=pr_no, pr_line=pr_line_num).first()
                if not pr_line:
                    pr_line = PRLine(
                        pr_no=pr_no,
                        pr_line=pr_line_num,
                        created_at=c_dt,
                        requester=req,
                        department=dept,
                        plant=plant,
                        item_code=code or None,
                        description=desc,
                        quantity=qty,
                        uom=uom,
                        estimated_unit_price=est_price,
                        need_by_date=need_by,
                        urgency=urgency,
                        batch_id="sample_pr_batch_nov_2026",
                        raw_data_json=json.dumps(row),
                    )
                    self.db.add(pr_line)
                else:
                    pr_line.created_at = c_dt
                    pr_line.requester = req
                    pr_line.department = dept
                    pr_line.plant = plant
                    pr_line.item_code = code or None
                    pr_line.description = desc
                    pr_line.quantity = qty
                    pr_line.uom = uom
                    pr_line.estimated_unit_price = est_price
                    pr_line.need_by_date = need_by
                    pr_line.urgency = urgency
                count += 1
            self.db.commit()
            self.summary["pr_lines"] = count
            return count

    def seed_initial_policy_and_users(self):
        # 1. Seed initial users
        users = [
            ("buyer_priya", "Priya Sharma", "BUYER", "priya.sharma@corvo.internal"),
            ("requester_kulkarni", "A. Kulkarni", "REQUESTER", "a.kulkarni@corvo.internal"),
            ("admin_procurement", "Head of Procurement", "PROCUREMENT_ADMIN", "procurement.head@corvo.internal"),
        ]
        for username, name, role, email in users:
            if not self.db.query(User).filter_by(username=username).first():
                self.db.add(User(username=username, name=name, role=role, email=email))

        # 2. Seed active policy v5.0 from JSON file
        policy_file = os.path.join(os.path.dirname(__file__), "..", "policies", "corvo_v5_0.json")
        if os.path.exists(policy_file):
            with open(policy_file, "r", encoding="utf-8") as pf:
                policy_data = json.load(pf)
                policy_json_str = json.dumps(policy_data, indent=2)
                eff_date = datetime.strptime(policy_data["effective_from"], "%Y-%m-%d").date()
        else:
            eff_date = datetime.strptime("2026-04-01", "%Y-%m-%d").date()
            policy_json_str = "{}"

        v5 = self.db.query(PolicyVersion).filter_by(version_label="v5.0").first()
        if not v5:
            # Check if ANY active policy already exists in DB (e.g. v5.1 approved during runtime)
            any_active = self.db.query(PolicyVersion).filter_by(status="ACTIVE").first()
            status_for_v5 = "SUPERSEDED" if any_active else "ACTIVE"
            v5 = PolicyVersion(
                version_label="v5.0",
                effective_from=eff_date,
                status=status_for_v5,
                rules_json=policy_json_str,
                source_text="Corvo Engineering Procurement Policy v5.0",
                created_by="Head of Procurement",
                created_at=datetime.now(),
                approved_by="Board of Directors",
                approved_at=datetime.now(),
            )
            self.db.add(v5)
        # If v5.0 already exists, do NOT alter its status or wipe active amendment policies!

        self.db.commit()

    def load_pdf_only_contracts(self) -> int:
        pdf_dir = os.path.join(self.base_dir, "contracts", "pdf")
        if not os.path.exists(pdf_dir):
            return 0
        from backend.app.contract_service import (
            extract_text_from_pdf,
            parse_contract_text,
            save_or_update_contract,
            ContractConfirmRequest,
        )

        existing = {c.contract_id for c in self.db.query(Contract.contract_id).all()}
        count = 0
        for fname in sorted(os.listdir(pdf_dir)):
            if not fname.endswith(".pdf"):
                continue
            pdf_path = os.path.join(pdf_dir, fname)
            cid = fname.replace(".pdf", "")
            # Ingest PDF contracts that are not present in register (e.g. RC-2026-031)
            if cid not in existing:
                try:
                    text = extract_text_from_pdf(pdf_path)
                    preview = parse_contract_text(text, self.db, pdf_path=pdf_path)
                    req = ContractConfirmRequest(
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
                        confirmed_by="System Ingestion",
                    )
                    save_or_update_contract(req, self.db)
                    count += 1
                except Exception as e:
                    self.log_issue(
                        fname,
                        cid,
                        "PDF_EXTRACTION_FAILURE",
                        str(e),
                        {"filename": fname},
                        "WARNING",
                    )
        self.summary["pdf_contracts_ingested"] = count
        return count

    def run_all(self):
        print("Starting idempotent data ingestion...")
        self.load_plants()
        self.load_items()
        self.load_suppliers()
        self.load_po_history()
        self.load_contracts()
        self.load_contract_lines()
        self.load_pdf_only_contracts()
        self.load_pr_batch()
        self.seed_initial_policy_and_users()

        issue_count = self.db.query(DataQualityIssue).count()
        self.summary["data_quality_issues"] = issue_count
        return self.summary
