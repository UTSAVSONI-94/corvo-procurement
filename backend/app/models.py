from datetime import datetime, date
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    Column,
    String,
    Integer,
    Numeric,
    Date,
    DateTime,
    Boolean,
    Text,
    ForeignKey,
    UniqueConstraint,
    Index,
)
from sqlalchemy.orm import relationship

from .database import Base


class Plant(Base):
    __tablename__ = "plants"

    plant_code = Column(String(10), primary_key=True)  # CHK1, PUN1
    name = Column(String(100), nullable=False)

    def __repr__(self):
        return f"<Plant {self.plant_code} - {self.name}>"


class Item(Base):
    __tablename__ = "items"

    item_code = Column(String(20), primary_key=True)  # ITM-1001
    description = Column(String(255), nullable=False)
    category = Column(String(100), nullable=False)
    item_type = Column(String(50), nullable=False)  # Material, Service, Capex
    uom = Column(String(20), nullable=False)
    standard_price = Column(Numeric(14, 2), nullable=False)
    aliases = Column(Text, nullable=True)  # JSON list or comma-separated aliases
    search_text = Column(String(500), nullable=False, index=True)

    contract_lines = relationship("ContractLine", back_populates="item")
    po_records = relationship("POHistory", back_populates="item")

    def __repr__(self):
        return f"<Item {self.item_code} - {self.description}>"


class Supplier(Base):
    __tablename__ = "suppliers"

    supplier_id = Column(String(20), primary_key=True)  # S001
    name = Column(String(150), nullable=False)
    city = Column(String(100), nullable=False)
    categories = Column(String(255), nullable=False)
    status = Column(String(20), nullable=False)  # Active, Blocked, Inactive
    on_time_pct = Column(Numeric(5, 2), nullable=False)
    quality_rating = Column(Numeric(3, 1), nullable=False)

    contracts = relationship("Contract", back_populates="supplier")
    po_records = relationship("POHistory", back_populates="supplier")

    def __repr__(self):
        return f"<Supplier {self.supplier_id} - {self.name} ({self.status})>"


class POHistory(Base):
    __tablename__ = "po_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    po_number = Column(String(30), nullable=False, index=True)
    po_date = Column(Date, nullable=False, index=True)
    supplier_id = Column(String(20), ForeignKey("suppliers.supplier_id"), nullable=False)
    item_code = Column(String(20), ForeignKey("items.item_code"), nullable=False)
    quantity = Column(Numeric(12, 2), nullable=False)
    uom = Column(String(20), nullable=False)
    unit_price = Column(Numeric(14, 2), nullable=False)
    plant = Column(String(10), ForeignKey("plants.plant_code"), nullable=False)
    delivered_on_time = Column(Boolean, nullable=False, default=True)

    supplier = relationship("Supplier", back_populates="po_records")
    item = relationship("Item", back_populates="po_records")

    __table_args__ = (
        Index("ix_po_history_item_date", "item_code", "po_date"),
        Index("ix_po_history_supplier_item", "supplier_id", "item_code"),
    )


class Contract(Base):
    __tablename__ = "contracts"

    contract_id = Column(String(30), primary_key=True)  # RC-2025-011
    supplier_id = Column(String(20), ForeignKey("suppliers.supplier_id"), nullable=False)
    supplier_name = Column(String(150), nullable=False)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    value_ceiling = Column(Numeric(14, 2), nullable=False)  # mapped from value_cap
    consumed_value = Column(Numeric(14, 2), nullable=False, default=Decimal("0.00"))
    source = Column(String(30), nullable=False, default="REGISTER")  # REGISTER, PDF_MANUAL, PDF_EXTRACTED
    pdf_path = Column(String(255), nullable=True)

    supplier = relationship("Supplier", back_populates="contracts")
    lines = relationship("ContractLine", back_populates="contract", cascade="all, delete-orphan")


class ContractLine(Base):
    __tablename__ = "contract_lines"

    id = Column(Integer, primary_key=True, autoincrement=True)
    contract_id = Column(String(30), ForeignKey("contracts.contract_id"), nullable=False)
    item_code = Column(String(20), ForeignKey("items.item_code"), nullable=False)
    description = Column(String(255), nullable=False)
    uom = Column(String(20), nullable=False)
    rate = Column(Numeric(14, 2), nullable=False)

    contract = relationship("Contract", back_populates="lines")
    item = relationship("Item", back_populates="contract_lines")

    __table_args__ = (
        UniqueConstraint("contract_id", "item_code", name="uq_contract_item"),
    )


class PolicyVersion(Base):
    __tablename__ = "policy_versions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    version_label = Column(String(20), nullable=False, unique=True)  # v5.0
    effective_from = Column(Date, nullable=False)
    status = Column(String(20), nullable=False, default="DRAFT")  # DRAFT, ACTIVE, SUPERSEDED
    rules_json = Column(Text, nullable=False)  # Configurable limits, rules order, windows
    source_text = Column(Text, nullable=True)  # Full policy markdown or raw text
    created_by = Column(String(100), nullable=False, default="System")
    created_at = Column(DateTime, nullable=False, default=datetime.now)
    approved_by = Column(String(100), nullable=True)
    approved_at = Column(DateTime, nullable=True)

    decisions = relationship("Decision", back_populates="policy_version")


class PolicyDiff(Base):
    __tablename__ = "policy_diffs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    old_version_id = Column(Integer, ForeignKey("policy_versions.id"), nullable=True)
    new_version_id = Column(Integer, ForeignKey("policy_versions.id"), nullable=False)
    diff_summary = Column(Text, nullable=False)
    changes_json = Column(Text, nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.now)


class PRLine(Base):
    __tablename__ = "pr_lines"

    id = Column(Integer, primary_key=True, autoincrement=True)
    pr_no = Column(String(30), nullable=False)
    pr_line = Column(Integer, nullable=False)
    created_at = Column(DateTime, nullable=False)
    requester = Column(String(100), nullable=False)
    department = Column(String(100), nullable=False)
    plant = Column(String(10), nullable=False)
    item_code = Column(String(20), nullable=True)
    description = Column(String(255), nullable=False)
    quantity = Column(Numeric(12, 2), nullable=False)
    uom = Column(String(20), nullable=False)
    estimated_unit_price = Column(Numeric(14, 2), nullable=True)
    need_by_date = Column(Date, nullable=False)
    urgency = Column(String(20), nullable=False, default="Normal")  # Normal, Emergency
    batch_id = Column(String(50), nullable=True)
    raw_data_json = Column(Text, nullable=True)

    __table_args__ = (
        UniqueConstraint("pr_no", "pr_line", name="uq_pr_no_line"),
        Index("ix_pr_lines_created", "created_at"),
    )


class Requirement(Base):
    __tablename__ = "requirements"

    id = Column(String(40), primary_key=True)  # REQ-xxxx group ID
    resolved_item_code = Column(String(20), nullable=False)
    plant = Column(String(10), nullable=False)
    requirement_date = Column(Date, nullable=False)
    need_by_date = Column(Date, nullable=False)
    total_quantity = Column(Numeric(12, 2), nullable=False)
    uom = Column(String(20), nullable=False)
    estimated_value = Column(Numeric(14, 2), nullable=False)
    is_emergency = Column(Boolean, nullable=False, default=False)
    status = Column(String(30), nullable=False, default="PENDING")
    created_at = Column(DateTime, nullable=False, default=datetime.now)

    lines = relationship("RequirementLine", back_populates="requirement")
    decision = relationship("Decision", back_populates="requirement", uselist=False)


class RequirementLine(Base):
    __tablename__ = "requirement_lines"

    id = Column(Integer, primary_key=True, autoincrement=True)
    requirement_id = Column(String(40), ForeignKey("requirements.id"), nullable=False)
    pr_line_id = Column(Integer, ForeignKey("pr_lines.id"), nullable=False)

    requirement = relationship("Requirement", back_populates="lines")
    pr_line = relationship("PRLine")


class Decision(Base):
    __tablename__ = "decisions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    requirement_id = Column(String(40), ForeignKey("requirements.id"), nullable=False, unique=True)
    policy_version_id = Column(Integer, ForeignKey("policy_versions.id"), nullable=False)
    decision = Column(String(30), nullable=False)  # PO or SOURCING_REQUEST
    route = Column(String(40), nullable=False)  # CONTRACT_PO, SPOT_PO, RFQ, RFP, etc.
    supplier_id = Column(String(20), nullable=True)
    unit_price = Column(Numeric(14, 2), nullable=True)
    group_value_inr = Column(Numeric(14, 2), nullable=False)
    suggested_supplier_ids = Column(String(255), nullable=True)  # S014;S013;S016
    contract_id = Column(String(30), nullable=True)
    po_id_ref = Column(String(30), nullable=True)
    clause = Column(String(50), nullable=False)
    reason = Column(Text, nullable=False)
    override_comment = Column(Text, nullable=True)
    overridden_by = Column(String(100), nullable=True)
    overridden_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.now)

    requirement = relationship("Requirement", back_populates="decision")
    policy_version = relationship("PolicyVersion", back_populates="decisions")


class PurchaseOrder(Base):
    __tablename__ = "purchase_orders"

    id = Column(String(30), primary_key=True)  # PO-0001
    supplier_id = Column(String(20), ForeignKey("suppliers.supplier_id"), nullable=False)
    plant = Column(String(10), nullable=False)
    route = Column(String(40), nullable=False)
    po_date = Column(Date, nullable=False)
    total_value = Column(Numeric(14, 2), nullable=False)
    status = Column(String(30), nullable=False, default="DRAFT")  # DRAFT, APPROVED, SENT
    created_at = Column(DateTime, nullable=False, default=datetime.now)

    lines = relationship("POLine", back_populates="purchase_order")


class POLine(Base):
    __tablename__ = "po_lines"

    id = Column(Integer, primary_key=True, autoincrement=True)
    po_id = Column(String(30), ForeignKey("purchase_orders.id"), nullable=False)
    requirement_id = Column(String(40), nullable=False)
    item_code = Column(String(20), nullable=False)
    quantity = Column(Numeric(12, 2), nullable=False)
    unit_price = Column(Numeric(14, 2), nullable=False)
    line_value = Column(Numeric(14, 2), nullable=False)

    purchase_order = relationship("PurchaseOrder", back_populates="lines")


class SourcingRequest(Base):
    __tablename__ = "sourcing_requests"

    id = Column(String(30), primary_key=True)  # SR-0001
    requirement_id = Column(String(40), nullable=False)
    route = Column(String(40), nullable=False)  # RFQ, RFP, CAPEX_SOURCING, NEW_ITEM_SOURCING
    item_code = Column(String(20), nullable=False)
    quantity = Column(Numeric(12, 2), nullable=False)
    estimated_value = Column(Numeric(14, 2), nullable=False)
    suggested_suppliers = Column(String(255), nullable=True)
    status = Column(String(30), nullable=False, default="OPEN")
    created_at = Column(DateTime, nullable=False, default=datetime.now)


class AuditLog(Base):
    __tablename__ = "audit_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    who = Column(String(100), nullable=False)
    when_timestamp = Column(DateTime, nullable=False, default=datetime.now)
    action = Column(String(50), nullable=False)  # APPROVE, OVERRIDE, CREATE, UPDATE
    entity = Column(String(50), nullable=False)  # DECISION, CONTRACT, POLICY, PO
    entity_id = Column(String(50), nullable=True)
    before_state = Column(Text, nullable=True)
    after_state = Column(Text, nullable=True)
    comment = Column(Text, nullable=True)


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(50), unique=True, nullable=False)
    name = Column(String(100), nullable=False)
    role = Column(String(30), nullable=False)  # REQUESTER, BUYER, PROCUREMENT_ADMIN
    email = Column(String(120), unique=True, nullable=False)


class DataQualityIssue(Base):
    __tablename__ = "data_quality_issues"

    id = Column(Integer, primary_key=True, autoincrement=True)
    file_source = Column(String(100), nullable=False)
    row_identifier = Column(String(100), nullable=False)
    issue_type = Column(String(50), nullable=False)  # INVALID_PLANT, ZERO_QTY, MISSING_PRICE, etc.
    issue_description = Column(Text, nullable=False)
    raw_data = Column(Text, nullable=True)
    severity = Column(String(20), nullable=False, default="WARNING")  # WARNING, ERROR
    created_at = Column(DateTime, nullable=False, default=datetime.now)

    def __repr__(self):
        return f"<DataQualityIssue {self.issue_type} in {self.file_source}: {self.row_identifier}>"
