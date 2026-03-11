#!/usr/bin/env python3
"""
Upload permit data to the Supabase `permits` table.

Reads raw Permits.csv (with descriptions and valuations), maps strap → home_index
via the Regrid joined file, classifies permit types from permit_category, and
upserts into Supabase.

Environment variables (set in .env or os env):
  SUPABASE_URL             - Supabase project URL
  SUPABASE_SERVICE_ROLE_KEY - Service role key (bypasses RLS for writes)

Usage:
  python scripts/upload_permits_to_supabase.py                # upload all matched permits
  python scripts/upload_permits_to_supabase.py --since 2024   # only permits from 2024+
  python scripts/upload_permits_to_supabase.py --dry-run      # preview without uploading
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]

try:
    from dotenv import load_dotenv
    load_dotenv(PROJECT_ROOT / ".env")
except ImportError:
    pass

# ---------------------------------------------------------------------------
# Config per county: paths and index prefix
# ---------------------------------------------------------------------------
COUNTY_CONFIGS = {
    "boulder_co": {
        "permits_csv": PROJECT_ROOT / "data" / "raw" / "Boulder_CO_Permits_3_11_26.csv",
        "regrid_csv": PROJECT_ROOT / "data" / "working" / "Boulder_CO_Regrid_joined_with_API.csv",
        "index_prefix": "BOULDER_CO_",
        "county_name": "Boulder",
    },
    # Add more counties here as needed:
    # "san_diego_ca": {
    #     "permits_csv": PROJECT_ROOT / "data" / "raw" / "SanDiegoCA" / "permits.csv",
    #     "regrid_csv": PROJECT_ROOT / "data" / "SanDiego_CA" / "working" / "...",
    #     "index_prefix": "SANDIEGO_CA_",
    #     "county_name": "San Diego",
    # },
}

# permit_category → standardized permit_type
# Categories not listed here default to "other"
CATEGORY_TO_TYPE = {
    "RESIDENTIAL RE-ROOF": "roof",
    "COMMERCIAL RE-ROOF": "roof",
    "AIR CONDITIONER": "hvac",
    "HEATING SYSTEM": "hvac",
    "EVAPORATIVE COOLER": "hvac",
    "ENERGY EFFICIENT SYSTEM": "solar",  # majority are solar in Boulder data
    "ELECTRICAL/MECHANICAL": "electrical",
    "WATER HEATER": "water_heater",
    "REMODEL": "remodel",
    "BATHROOM": "remodel",
    "BASEMENT FINISH": "remodel",
    "ADDITION": "construction",
    "NEW CONSTRUCTION": "construction",
    "GARAGE": "construction",
    "DECK": "construction",
    "PORCH": "construction",
    "ENCLOSED PORCH": "construction",
    "OUTBUILDING OR SHED": "construction",
    "BARN": "construction",
    "WINDOWS OR DOORS": "other",
    "FENCE": "other",
    "SIDING": "other",
    "DEMOLITION": "other",
    "SEWER REPAIR": "other",
    "REPAIRS GENERAL": "other",
    "REPAIRS FIRE": "other",
    "REPAIRS STRUCTURAL": "other",
    "POOL": "other",
    "HOT TUB/SPA": "other",
    "RETAINING WALL": "other",
    "GAS FIREPLACE": "other",
    "WOOD FIREPLACE": "other",
    "FIRE SPRINKLER": "other",
    "OTHER": "other",
}

# Keywords in description to refine classification beyond category
DESCRIPTION_OVERRIDES = [
    # EV charger — check BEFORE solar (category "ENERGY EFFICIENT SYSTEM" is often solar,
    # but description may say "level 2 charger for EV")
    ("ev charger", "ev_charger"),
    ("ev charging", "ev_charger"),
    ("electric vehicle", "ev_charger"),
    ("chargepoint", "ev_charger"),
    ("wallbox", "ev_charger"),
    ("level 2 charg", "ev_charger"),
    ("level 2 ev", "ev_charger"),
    ("evse", "ev_charger"),
    ("charger for ev", "ev_charger"),
    # Battery — check BEFORE solar
    ("battery", "battery"),
    ("powerwall", "battery"),
    ("energy storage", "battery"),
    # Solar
    ("solar", "solar"),
    ("photovoltaic", "solar"),
    (" pv ", "solar"),
    # Other
    ("heat pump", "heat_pump"),
    ("mini-split", "heat_pump"),
    ("mini split", "heat_pump"),
    ("generator", "generator"),
]


def build_strap_lookup(regrid_csv: Path, index_prefix: str) -> dict[str, str]:
    """Build strap → home_index lookup from Regrid joined data."""
    df = pd.read_csv(regrid_csv, usecols=["strap", "original_index"], low_memory=False)
    df["home_index"] = index_prefix + df["original_index"].astype(str)
    return dict(zip(df["strap"], df["home_index"]))


def classify_permit(category: str, description: str) -> str:
    """Classify permit type from category and description text."""
    desc_lower = description.lower() if isinstance(description, str) else ""

    # Description keywords override category (more specific)
    for keyword, ptype in DESCRIPTION_OVERRIDES:
        if keyword in desc_lower:
            return ptype

    # Fall back to category mapping
    cat = str(category).strip().upper()
    return CATEGORY_TO_TYPE.get(cat, "other")


def parse_permits(permits_csv: Path, strap_to_home: dict[str, str],
                  county_name: str, since_year: int | None = None) -> list[dict]:
    """Parse raw permit CSV into normalized records for Supabase."""
    df = pd.read_csv(permits_csv, low_memory=False)
    df["issue_dt"] = pd.to_datetime(df["issue_dt"], format="mixed", dayfirst=False, errors="coerce")
    bad_dates = df["issue_dt"].isna().sum()
    if bad_dates:
        print(f"  Warning: {bad_dates} rows with unparseable dates dropped")
    df = df.dropna(subset=["issue_dt"])

    if since_year:
        df = df[df["issue_dt"].dt.year >= since_year]

    # Only keep permits that map to homes in our system
    df["home_index"] = df["strap"].map(strap_to_home)
    df = df.dropna(subset=["home_index"])

    records = []
    for _, row in df.iterrows():
        category = row.get("permit_category", "OTHER")
        description = row.get("description", None)
        ptype = classify_permit(category, description)

        # Clean up description
        desc_text = str(description).strip() if pd.notna(description) else None

        # Valuation
        val = row.get("estimated_value", None)
        valuation = float(val) if pd.notna(val) else None

        records.append({
            "home_index": row["home_index"],
            "permit_number": str(row["permit_num"]).strip() if pd.notna(row.get("permit_num")) else None,
            "permit_type": ptype,
            "description": desc_text,
            "filed_date": row["issue_dt"].strftime("%Y-%m-%d"),
            "valuation": valuation,
            "county": county_name,
        })

    return records


def upload_to_supabase(records: list[dict], batch_size: int = 500) -> None:
    """Upsert records to Supabase permits table."""
    from supabase import create_client

    url = os.environ["SUPABASE_URL"]
    key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    client = create_client(url, key)

    total = len(records)
    uploaded = 0

    for i in range(0, total, batch_size):
        batch = records[i : i + batch_size]
        client.table("permits").upsert(
            batch,
            on_conflict="home_index,permit_number,permit_type",
        ).execute()
        uploaded += len(batch)
        print(f"  Upserted {uploaded}/{total} records...")

    print(f"Done. {uploaded} permit records upserted.")


def main():
    parser = argparse.ArgumentParser(description="Upload permits to Supabase")
    parser.add_argument("--county", default="boulder_co", choices=list(COUNTY_CONFIGS.keys()),
                        help="County config to use (default: boulder_co)")
    parser.add_argument("--since", type=int, default=None,
                        help="Only upload permits from this year onward")
    parser.add_argument("--dry-run", action="store_true",
                        help="Parse and show stats without uploading")
    args = parser.parse_args()

    config = COUNTY_CONFIGS[args.county]
    print(f"County: {config['county_name']}")
    print(f"Permits CSV: {config['permits_csv']}")
    print(f"Regrid CSV: {config['regrid_csv']}")

    if not config["permits_csv"].exists():
        print(f"ERROR: Permits file not found: {config['permits_csv']}")
        sys.exit(1)
    if not config["regrid_csv"].exists():
        print(f"ERROR: Regrid file not found: {config['regrid_csv']}")
        sys.exit(1)

    print("Building strap → home_index lookup...")
    strap_to_home = build_strap_lookup(config["regrid_csv"], config["index_prefix"])
    print(f"  {len(strap_to_home)} straps mapped")

    print("Parsing permits...")
    records = parse_permits(config["permits_csv"], strap_to_home,
                           config["county_name"], args.since)

    # Stats
    from collections import Counter
    type_counts = Counter(r["permit_type"] for r in records)
    print(f"\n  Total records: {len(records)}")
    for ptype, count in sorted(type_counts.items(), key=lambda x: -x[1]):
        print(f"    {ptype}: {count}")

    if args.dry_run:
        print("\n--dry-run: skipping upload")
        for r in records[:5]:
            print(f"  Sample: {r}")
        return

    if not os.environ.get("SUPABASE_URL") or not os.environ.get("SUPABASE_SERVICE_ROLE_KEY"):
        print("\nERROR: Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY environment variables")
        sys.exit(1)

    print("\nUploading to Supabase...")
    upload_to_supabase(records)


if __name__ == "__main__":
    main()
