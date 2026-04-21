"""
seed.py — Populate the database with 2026 profiles from profiles.json

Usage:
    python seed.py                        # looks for profiles.json in same folder
    python seed.py path/to/profiles.json  # custom path

Rules:
    - Re-running this script will NOT create duplicates
    - Duplicate check is done by name (unique column)
    - Each record gets a UUID v7 id and UTC created_at generated here
    - Skipped records are reported at the end
"""

import sys
import json
from datetime import datetime, timezone
from uuid6 import uuid7
from database import Profile, SessionLocal


def load_json(filepath: str) -> list[dict]:
    """Read the JSON file and return the list under the 'profiles' key."""
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)

    # The JSON is shaped as {"profiles": [...]} — not a top-level array
    if isinstance(data, dict) and "profiles" in data:
        return data["profiles"]

    # Fallback — if someone passes a plain array
    if isinstance(data, list):
        return data

    raise ValueError(
        "Unexpected JSON structure. "
        "Expected {'profiles': [...]} or a top-level array."
    )


def seed(filepath: str = "seed_profiles.json"):
    print(f"\n📂 Loading profiles from: {filepath}")
    records = load_json(filepath)
    print(f"📊 Total records in file: {len(records)}")

    db = SessionLocal()

    inserted = 0
    skipped  = 0
    errors   = 0

    try:
        for i, record in enumerate(records, start=1):

            name = record.get("name", "").strip()

            # ── Skip if name is empty ─────────────────────────────────────────
            if not name:
                print(f"  [!] Row {i}: missing name — skipped")
                errors += 1
                continue

            # ── Idempotency check — skip if name already exists ───────────────
            exists = db.query(Profile).filter(Profile.name == name).first()
            if exists:
                skipped += 1
                continue

            # ── Build the Profile object ──────────────────────────────────────
            profile = Profile(
                id                  = str(uuid7()),
                name                = name,
                gender              = record.get("gender"),
                gender_probability  = record.get("gender_probability"),
                age                 = record.get("age"),
                age_group           = record.get("age_group"),
                country_id          = record.get("country_id"),
                country_name        = record.get("country_name"),
                country_probability = record.get("country_probability"),
                created_at          = datetime.now(timezone.utc),

                # sample_size is not in the seed file — default to 0
                # it only comes from the Genderize API (Stage 1 POST endpoint)
                sample_size         = record.get("sample_size", 0),
            )

            db.add(profile)
            inserted += 1

            # ── Commit in batches of 100 for performance ──────────────────────
            # Committing every single row is slow (100 round trips per 100 rows)
            # One giant commit at the end risks losing everything on error
            # Batching of 100 balances speed and safety
            if inserted % 100 == 0:
                db.commit()
                print(f"  ✓ {inserted} records committed so far...")

        # Final commit for any remaining records not yet committed
        db.commit()

    except Exception as e:
        db.rollback()
        print(f"\n❌ Error during seeding: {e}")
        raise

    finally:
        db.close()

    # ── Summary ───────────────────────────────────────────────────────────────
    print(f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ Seeding complete
   Inserted : {inserted}
   Skipped  : {skipped}  (already existed)
   Errors   : {errors}   (bad records)
   Total    : {inserted + skipped + errors}
━━━━━━━━━━━━━━━━━━━━━━━━━━━
""")


if __name__ == "__main__":
    # Accept optional filepath argument from command line
    # Default is profiles.json in the same directory as this script
    filepath = sys.argv[1] if len(sys.argv) > 1 else "seed_profiles.json"
    seed(filepath)