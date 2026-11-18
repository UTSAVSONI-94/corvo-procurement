import os
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.database import Base
from backend.app.models import (
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
from backend.app.loaders import DataLoader


@pytest.fixture(scope="module")
def db_session():
    # Use in-memory SQLite database for isolated test execution
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = TestingSessionLocal()
    
    loader = DataLoader(db, base_dir="kit")
    loader.run_all()
    
    yield db
    db.close()


def test_row_counts_match_csvs(db_session):
    assert db_session.query(Plant).count() == 2
    assert db_session.query(Item).count() == 73
    assert db_session.query(Supplier).count() == 48
    assert db_session.query(POHistory).count() == 468
    assert db_session.query(Contract).filter_by(source="REGISTER").count() == 10
    assert db_session.query(Contract).count() in (10, 11)
    assert db_session.query(ContractLine).join(Contract).filter(Contract.source == "REGISTER").count() == 26
    assert db_session.query(ContractLine).count() in (26, 27)
    assert db_session.query(PRLine).count() == 186


def test_contract_lines_fk_integrity(db_session):
    contract_ids = {c.contract_id for c in db_session.query(Contract.contract_id).all()}
    item_codes = {i.item_code for i in db_session.query(Item.item_code).all()}

    lines = db_session.query(ContractLine).all()
    assert len(lines) in (26, 27)
    for line in lines:
        assert line.contract_id in contract_ids, f"Orphan contract_id {line.contract_id}"
        assert line.item_code in item_codes, f"Orphan item_code {line.item_code}"
        assert line.rate > 0


def test_po_history_fk_integrity(db_session):
    supplier_ids = {s.supplier_id for s in db_session.query(Supplier.supplier_id).all()}
    item_codes = {i.item_code for i in db_session.query(Item.item_code).all()}
    plant_codes = {p.plant_code for p in db_session.query(Plant.plant_code).all()}

    pos = db_session.query(POHistory).all()
    assert len(pos) == 468
    for po in pos:
        assert po.supplier_id in supplier_ids
        assert po.item_code in item_codes
        assert po.plant in plant_codes
        assert po.quantity > 0
        assert po.unit_price > 0


def test_orphan_handling_resilience(db_session):
    # Verify that data quality logger records issues instead of crashing
    loader = DataLoader(db_session, base_dir="kit")
    initial_issues = db_session.query(DataQualityIssue).count()

    # Log a simulated orphan FK
    loader.log_issue(
        file_source="test_feed.csv",
        row_id="TEST-001",
        issue_type="ORPHAN_SUPPLIER_FK",
        description="Supplier S999 does not exist",
        raw_data={"supplier_id": "S999"},
        severity="ERROR",
    )
    db_session.commit()

    new_issues = db_session.query(DataQualityIssue).count()
    assert new_issues == initial_issues + 1

    logged = db_session.query(DataQualityIssue).filter_by(row_identifier="TEST-001").first()
    assert logged is not None
    assert logged.issue_type == "ORPHAN_SUPPLIER_FK"
    assert logged.severity == "ERROR"


def test_data_quality_issues_logged(db_session):
    # Verify expected anomalies are tracked in data_quality_issues table
    issues = db_session.query(DataQualityIssue).all()
    issue_types = {i.issue_type for i in issues}

    assert "INVALID_PLANT" in issue_types  # PUN2
    assert "ZERO_QUANTITY" in issue_types  # PR-26-00172
    assert "BLANK_ITEM_CODE" in issue_types  # 39 lines
    assert "SUPPLIER_BLOCKED" in issue_types  # S004, S008, S011
    assert "SUPPLIER_INACTIVE" in issue_types  # S031, S034

    # Verify PUN2 row was not dropped from pr_lines table
    pun2_pr = db_session.query(PRLine).filter_by(plant="PUN2").first()
    assert pun2_pr is not None
    assert pun2_pr.pr_no == "PR-26-00173"


def test_policy_and_users_seeded(db_session):
    v5 = db_session.query(PolicyVersion).filter_by(version_label="v5.0").first()
    assert v5 is not None
    assert v5.status == "ACTIVE"

    users = db_session.query(User).all()
    assert len(users) >= 3
    usernames = {u.username for u in users}
    assert "buyer_priya" in usernames
    assert "admin_procurement" in usernames

