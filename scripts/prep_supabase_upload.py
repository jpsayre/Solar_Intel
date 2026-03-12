#!/usr/bin/env python3
"""
Prepare home data for Supabase upload.

Reads regrid_filtered.csv (all qualified properties), optionally joins
Sunroof API data, and outputs JSON ready for upsert into the homes table.

Usage:
  python scripts/prep_supabase_upload.py --config boulder_co
  python scripts/prep_supabase_upload.py --config boulder_co --dry-run
  python scripts/prep_supabase_upload.py --config boulder_co --upload
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import pandas as pd
import numpy as np
from FinalFilters import parse_owner, format_subdivision

try:
    from dotenv import load_dotenv
    load_dotenv(PROJECT_ROOT / ".env")
except ImportError:
    pass


def prep(config) -> list[dict]:
    """Prepare home records from pipeline output."""
    regrid_path = config.regrid_filtered_path
    sunroof_path = config.sunroof_api_output_path

    print(f"Reading regrid_filtered: {regrid_path}")
    df = pd.read_csv(regrid_path, low_memory=False)
    print(f"  {len(df)} rows")

    # Derived: calculated_build_year = max(yearbuilt, year_built_effective_date)
    df["calculated_build_year"] = (
        df[["yearbuilt", "year_built_effective_date"]]
        .apply(pd.to_numeric, errors="coerce")
        .max(axis=1)
    )

    # Join Sunroof API data if available
    if sunroof_path.exists():
        print(f"Reading sunroof API output: {sunroof_path}")
        api = pd.read_csv(sunroof_path, low_memory=False)
        api_ok = api[api.get("ok", pd.Series(dtype=bool)).astype(str).str.lower() == "true"] if "ok" in api.columns else api
        print(f"  {len(api_ok)} ok rows out of {len(api)}")

        # Keep only columns we need, join on strap
        api_cols = [c for c in ["strap", "roof_orientation", "solar_score"] if c in api_ok.columns]
        if "strap" in api_cols:
            df = df.merge(api_ok[api_cols], on="strap", how="left", suffixes=("", "_api"))
    else:
        print(f"  No sunroof output at {sunroof_path}, skipping API join")

    # Lat/lon: use regrid values
    df["latitude"] = pd.to_numeric(df["lat"], errors="coerce")
    df["longitude"] = pd.to_numeric(df["lon"], errors="coerce")

    # Uppercase city/county
    for col in ["city", "county"]:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip().str.upper()

    # Extract numeric part from original_index
    df["original_index_num"] = df["original_index"].astype(str).str.extract(r"(\d+)$")[0]

    # Build index: COUNTY_STATE_num
    df["home_index"] = (
        df["county"].astype(str) + "_" + df["state2"].astype(str) + "_" + df["original_index_num"]
    )

    # Parse owner names
    parsed = df["owner"].apply(lambda x: pd.Series(parse_owner(x)))
    df["owner_1"] = parsed[0]
    df["owner_2"] = parsed[1]

    # Format subdivision
    df["subdivision_formatted"] = df["subdivision"].apply(format_subdivision)

    # Build output DataFrame
    output = pd.DataFrame({
        "index": df["home_index"],
        "strap": df["strap"],
        "qualified_orientations": df.get("roof_orientation"),
        "saleprice": df["saleprice"],
        "saledate": df["saledate"],
        "owner_unaltered": df["owner"],
        "owner_1": df["owner_1"],
        "owner_2": df["owner_2"],
        "address": df["mailadd"],
        "city": df["city"],
        "county": df["county"],
        "state": df["state2"],
        "zip_code": df["szip5"].astype(str).str.replace(r"\.0$", "", regex=True),
        "subdivision_formatted": df["subdivision_formatted"],
        "building_sqft": df["area_building"],
        "roof_type": df.get("roof_coverdscr"),
        "calculated_build_year": df["calculated_build_year"],
        "latitude": df["latitude"],
        "longitude": df["longitude"],
        "count_stories": df["numstories"],
        "count_rooms": df["numrooms"],
        "count_bath": df["num_bath"],
        "count_bath_partial": df["num_bath_partial"],
        "count_bedrooms": df["num_bedrooms"],
        "original_index": df["original_index_num"],
    })

    # Convert numeric fields to strings (Supabase text columns)
    numeric_as_str = ["saleprice", "building_sqft", "calculated_build_year",
                      "count_stories", "count_rooms", "count_bath",
                      "count_bath_partial", "count_bedrooms"]
    for col in numeric_as_str:
        output[col] = output[col].apply(
            lambda x: str(int(x)) if pd.notna(x) and x == x else None
        )

    # Clean NaN/nan to None
    for col in output.columns:
        output[col] = output[col].where(output[col].notna(), None)
        output[col] = output[col].apply(lambda x: None if x == "nan" or x == "NAN" else x)

    # Ensure original_index is string
    output["original_index"] = output["original_index"].apply(
        lambda x: str(int(x)) if x is not None else None
    )

    records = output.to_dict(orient="records")

    print(f"\nPrepared: {len(records)} records")
    has_strap = sum(1 for r in records if r["strap"] is not None)
    has_orientation = sum(1 for r in records if r["qualified_orientations"] is not None)
    has_lat = sum(1 for r in records if r["latitude"] is not None)
    print(f"  With strap: {has_strap}/{len(records)}")
    print(f"  With roof orientation: {has_orientation}/{len(records)}")
    print(f"  With lat/lon: {has_lat}/{len(records)}")
    print(f"\nSample:")
    print(json.dumps(records[0], indent=2))

    return records


def upload_to_supabase(records: list[dict], batch_size: int = 500) -> None:
    """Upsert records to Supabase homes table."""
    from supabase import create_client

    url = os.environ["SUPABASE_URL"]
    key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    client = create_client(url, key)

    total = len(records)
    uploaded = 0

    for i in range(0, total, batch_size):
        batch = records[i : i + batch_size]
        client.table("homes").upsert(batch, on_conflict="index").execute()
        uploaded += len(batch)
        if uploaded <= batch_size or uploaded % 2000 == 0 or uploaded == total:
            print(f"  Upserted {uploaded}/{total}...")

    print(f"Done. {uploaded} home records upserted.")


def main():
    parser = argparse.ArgumentParser(description="Prepare and upload homes to Supabase")
    parser.add_argument("--config", required=True, help="County config name (e.g. boulder_co)")
    parser.add_argument("--upload", action="store_true", help="Upload to Supabase after prep")
    parser.add_argument("--dry-run", action="store_true", help="Prep only, no file output or upload")
    args = parser.parse_args()

    from pipeline_config import load_config
    config = load_config(args.config)

    records = prep(config)

    if args.dry_run:
        print("\n--dry-run: no output written")
        return

    # Save JSON
    output_path = config.final_dir / f"{config.county_id}_supabase_upload.json"
    with open(output_path, "w") as f:
        json.dump(records, f, indent=2)
    print(f"\nSaved to {output_path}")

    if args.upload:
        if not os.environ.get("SUPABASE_URL") or not os.environ.get("SUPABASE_SERVICE_ROLE_KEY"):
            print("\nERROR: Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY")
            sys.exit(1)
        print("\nUploading to Supabase...")
        upload_to_supabase(records)


if __name__ == "__main__":
    main()
