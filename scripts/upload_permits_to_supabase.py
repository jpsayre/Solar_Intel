#!/usr/bin/env python3
"""
Upload parsed permit data to the Supabase `permits` table.

Reads parsed_permits_test.csv, maps strap → home_index via the Regrid joined file,
classifies permit types from binary flags, and upserts into Supabase.

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
        "permits_csv": PROJECT_ROOT / "data" / "working" / "parsed_permits_test.csv",
        "regrid_csv": PROJECT_ROOT / "data" / "working" / "Boulder_CO_Regrid_joined_with_API.csv",
        "index_prefix": "BOULDER_CO_",
        "county_name": "Boulder",
    },
    # Add more counties here as needed:
    # "san_diego_ca": {
    #     "permits_csv": PROJECT_ROOT / "data" / "SanDiego_CA" / "working" / "parsed_permits.csv",
    #     "regrid_csv": PROJECT_ROOT / "data" / "SanDiego_CA" / "working" / "...",
    #     "index_prefix": "SANDIEGO_CA_",
    #     "county_name": "San Diego",
    # },
}

# Binary flag columns → permit type mapping
# Each permit row can have multiple flags; we emit one record per type.
PERMIT_TYPE_MAP = {
    "solar_pv": "solar",
    "battery": "battery",
    "ev_charger": "ev_charger",
    "roof_new_or_replace": "roof",
    "electrical_service_upgrade": "electrical",
    "heat_pump": "heat_pump",
    "ac": "hvac",
    "furnace": "hvac",
    "water_heater": "water_heater",
    "water_heater_electric": "water_heater",
    "water_heater_gas": "water_heater",
    "water_heater_solar_thermal": "water_heater",
    "windows_doors": "other",
    "insulation_airseal": "other",
    "generator": "generator",
    "addition_new_build": "construction",
    "kitchen_bath_remodel": "remodel",
    "pool_hot_tub": "other",
    "evaporative_cooler": "hvac",
}

# Human-readable descriptions for each type
PERMIT_DESCRIPTIONS = {
    "solar": "Solar PV installation",
    "battery": "Battery storage installation",
    "ev_charger": "EV charger installation",
    "roof": "Roof replacement or repair",
    "electrical": "Electrical service upgrade",
    "heat_pump": "Heat pump installation",
    "hvac": "HVAC system work",
    "water_heater": "Water heater installation",
    "generator": "Generator installation",
    "construction": "Addition or new construction",
    "remodel": "Kitchen/bath remodel",
    "other": "General permit",
}


def build_strap_lookup(regrid_csv: Path, index_prefix: str) -> dict[str, str]:
    """Build strap → home_index lookup from Regrid joined data."""
    df = pd.read_csv(regrid_csv, usecols=["strap", "original_index"], low_memory=False)
    df["home_index"] = index_prefix + df["original_index"].astype(str)
    return dict(zip(df["strap"], df["home_index"]))


def parse_permits(permits_csv: Path, strap_to_home: dict[str, str],
                  county_name: str, since_year: int | None = None) -> list[dict]:
    """Parse permit CSV into normalized records for Supabase."""
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
    type_cols = [c for c in PERMIT_TYPE_MAP if c in df.columns]

    for _, row in df.iterrows():
        # Find which permit types this row represents
        active_types = set()
        for col in type_cols:
            if row.get(col, 0) == 1:
                active_types.add(PERMIT_TYPE_MAP[col])

        if not active_types:
            active_types = {"other"}

        for ptype in active_types:
            records.append({
                "home_index": row["home_index"],
                "permit_number": str(row["permit_num"]) if pd.notna(row.get("permit_num")) else None,
                "permit_type": ptype,
                "description": PERMIT_DESCRIPTIONS.get(ptype, "Permit"),
                "filed_date": row["issue_dt"].strftime("%Y-%m-%d"),
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
        result = client.table("permits").upsert(
            batch,
            on_conflict="home_index,permit_number",
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
        # Show a few sample records
        for r in records[:3]:
            print(f"  Sample: {r}")
        return

    if not os.environ.get("SUPABASE_URL") or not os.environ.get("SUPABASE_SERVICE_ROLE_KEY"):
        print("\nERROR: Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY environment variables")
        sys.exit(1)

    print("\nUploading to Supabase...")
    upload_to_supabase(records)


if __name__ == "__main__":
    main()
