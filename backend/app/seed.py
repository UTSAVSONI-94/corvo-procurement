import sys
import os

from .database import engine, Base, SessionLocal
from .loaders import DataLoader
from .models import DataQualityIssue


def run_seed():
    print("=" * 60)
    print("Corvo Engineering Procurement System - Database Seeder")
    print("=" * 60)

    # Ensure tables are created
    Base.metadata.create_all(bind=engine)
    print("[1/3] Database schema verified and initialized.")

    db = SessionLocal()
    try:
        loader = DataLoader(db, base_dir="kit")
        summary = loader.run_all()
        print("\n[2/3] Data Ingestion Summary:")
        print("-" * 45)
        for entity, count in summary.items():
            print(f"  * {entity:<24}: {count:>6} rows")
        print("-" * 45)

        # Print Data Quality Issues summary
        issues = db.query(DataQualityIssue).all()
        print(f"\n[3/3] Data Quality Issues Detected: {len(issues)}")
        if issues:
            print("-" * 60)
            issue_groups = {}
            for iss in issues:
                key = (iss.file_source, iss.issue_type, iss.severity)
                issue_groups[key] = issue_groups.get(key, 0) + 1

            for (src, itype, sev), cnt in issue_groups.items():
                print(f"  [{sev}] {src} -> {itype}: {cnt} occurrences")
            print("-" * 60)
            print("Note: No rows were silently dropped. Flagged records are logged in 'data_quality_issues'.")
        print("\nDatabase seeding completed successfully.")

    except Exception as e:
        db.rollback()
        print(f"\n[ERROR] Seeding failed: {e}", file=sys.stderr)
        raise
    finally:
        db.close()


if __name__ == "__main__":
    run_seed()

