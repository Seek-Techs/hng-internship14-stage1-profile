"""
seed.py — Seed the database with 2026 profiles from the JSON file.

Usage:
    python seed.py                         # seeds from profiles.json in same folder
    python seed.py --file /path/to/file.json

Design:
    - Re-running this script is SAFE — it uses INSERT OR IGNORE (SQLite)
      or INSERT ... ON CONFLICT DO NOTHING (PostgreSQL) via SQLAlchemy upsert.
    - Duplicate names are skipped silently.
    - Prints a summary at the end.
"""

import json
import sys
import os
import argparse
from datetime import datetime, timezone

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy import text

from database import SessionLocal, Profile, engine, DATABASE_URL


def get_age_group(age: int) -> str:
    if age <= 12:
        return "child"
    elif age <= 19:
        return "teenager"
    elif age <= 59:
        return "adult"
    return "senior"


def load_json(filepath: str) -> list:
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)
    # Handle both a bare list and {"profiles": [...]} wrapper
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("profiles", "data", "results"):
            if key in data:
                return data[key]
    raise ValueError(f"Unrecognised JSON structure in {filepath}")


def seed(filepath: str):
    records = load_json(filepath)
    print(f"📂 Loaded {len(records)} records from {filepath}")

    db = SessionLocal()
    inserted = 0
    skipped  = 0

    try:
        for raw in records:
            # Normalise field names — JSON may use different casing
            name = str(raw.get("name", "")).strip().lower()
            if not name:
                skipped += 1
                continue

            # Check for existing record — skip if already present
            exists = db.query(Profile.id).filter(Profile.name == name).first()
            if exists:
                skipped += 1
                continue

            age = int(raw.get("age", 25))

            profile = Profile(
                name=name,
                gender=str(raw.get("gender", "male")).lower(),
                gender_probability=float(raw.get("gender_probability", 0.9)),
                age=age,
                age_group=get_age_group(age),
                country_id=str(raw.get("country_id", "NG")).upper(),
                country_name=str(raw.get("country_name", "Nigeria")),
                country_probability=float(raw.get("country_probability", 0.8)),
                created_at=datetime.now(timezone.utc),
            )

            db.add(profile)
            inserted += 1

            # Commit in batches of 200 to avoid memory issues with large datasets
            if inserted % 200 == 0:
                db.commit()
                print(f"  ✅ {inserted} inserted so far...")

        db.commit()

    except Exception as e:
        db.rollback()
        print(f"❌ Error during seeding: {e}")
        raise
    finally:
        db.close()

    print(f"\n✅ Seeding complete.")
    print(f"   Inserted : {inserted}")
    print(f"   Skipped  : {skipped} (already existed or empty name)")
    print(f"   Total    : {inserted + skipped}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed profiles into the database.")
    parser.add_argument(
        "--file",
        default="profiles.json",
        help="Path to the JSON file containing profiles (default: profiles.json)",
    )
    args = parser.parse_args()

    if not os.path.exists(args.file):
        print(f"❌ File not found: {args.file}")
        print("   Download the 2026 profiles JSON from the task Airtable link")
        print("   and place it in the same folder as seed.py, then run:")
        print("   python seed.py")
        sys.exit(1)

    seed(args.file)
