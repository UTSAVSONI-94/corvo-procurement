import json
from datetime import date, datetime
from typing import Optional, Union

from sqlalchemy import desc
from sqlalchemy.orm import Session

from backend.app.models import PolicyVersion
from backend.engine.schema import PolicyDocument


class PolicyRepository:
    def __init__(self, db: Session):
        self.db = db

    def _normalize_date(self, dt: Union[date, datetime, str]) -> date:
        if isinstance(dt, datetime):
            return dt.date()
        if isinstance(dt, date):
            return dt
        if isinstance(dt, str):
            clean_str = dt.strip().split(" ")[0]
            return datetime.strptime(clean_str, "%Y-%m-%d").date()
        raise ValueError(f"Unsupported date format: {dt}")

    def get_active_policy(self, as_of_date: Union[date, datetime, str]) -> PolicyDocument:
        """
        Retrieves the active policy version effective as of the given date.
        Picks the ACTIVE version with the latest effective_from <= as_of_date.
        Per requirement, the requirement date, NOT today's date, decides the version.
        """
        req_date = self._normalize_date(as_of_date)

        record = (
            self.db.query(PolicyVersion)
            .filter(
                PolicyVersion.status == "ACTIVE",
                PolicyVersion.effective_from <= req_date,
            )
            .order_by(
                desc(PolicyVersion.effective_from),
                desc(PolicyVersion.id),
            )
            .first()
        )

        if not record:
            raise LookupError(f"No active procurement policy found effective on or before {req_date}")

        data = json.loads(record.rules_json)
        return PolicyDocument(**data)

    def get_by_version(self, version_label: str) -> Optional[PolicyDocument]:
        record = self.db.query(PolicyVersion).filter_by(version_label=version_label).first()
        if not record:
            return None
        data = json.loads(record.rules_json)
        return PolicyDocument(**data)

    def save_policy(
        self,
        policy: PolicyDocument,
        created_by: str = "Procurement User",
        status: str = "DRAFT",
    ) -> PolicyVersion:
        eff_date = self._normalize_date(policy.effective_from)
        record = self.db.query(PolicyVersion).filter_by(version_label=policy.version).first()
        json_content = policy.model_dump_json(indent=2) if hasattr(policy, "model_dump_json") else json.dumps(policy.dict(), indent=2)

        if not record:
            record = PolicyVersion(
                version_label=policy.version,
                effective_from=eff_date,
                status=status,
                rules_json=json_content,
                source_text=policy.description,
                created_by=created_by,
                created_at=datetime.now(),
            )
            self.db.add(record)
        else:
            record.effective_from = eff_date
            record.status = status
            record.rules_json = json_content
            record.source_text = policy.description

        self.db.commit()
        self.db.refresh(record)
        return record

    def activate_version(self, version_label: str, approved_by: str) -> PolicyVersion:
        record = self.db.query(PolicyVersion).filter_by(version_label=version_label).first()
        if not record:
            raise LookupError(f"Policy version {version_label} not found")

        record.status = "ACTIVE"
        record.approved_by = approved_by
        record.approved_at = datetime.now()
        self.db.commit()
        self.db.refresh(record)
        return record

