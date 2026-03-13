#!/usr/bin/env python3
"""
Upload permit data to the Supabase `permits` table.

Reads parsed_permits.csv (already classified by parse_permits.py), maps
strap → home_index via Supabase homes table, and upserts into Supabase.

Environment variables (set in .env or os env):
  SUPABASE_URL             - Supabase project URL
  SUPABASE_SERVICE_ROLE_KEY - Service role key (bypasses RLS for writes)

Usage:
  python scripts/upload_permits_to_supabase.py --config boulder_co
  python scripts/upload_permits_to_supabase.py --config san_diego_ca --since 2024
  python scripts/upload_permits_to_supabase.py --config boulder_co --dry-run

Available configs: see configs/*.py (e.g. boulder_co, san_diego_ca)
Or pass a path: --config path/to/my_config.py
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


def _list_available_configs() -> list[str]:
    """List config names from configs/ directory."""
    configs_dir = PROJECT_ROOT / "configs"
    if not configs_dir.exists():
        return []
    return sorted(p.stem for p in configs_dir.glob("*.py") if not p.name.startswith("_"))


def build_strap_lookup(location: str) -> dict[str, str]:
    """Build strap → home_index lookup from Supabase homes table."""
    from supabase import create_client

    url = os.environ["SUPABASE_URL"]
    key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    client = create_client(url, key)

    lookup = {}
    page_size = 1000
    offset = 0
    while True:
        result = client.table("homes").select("strap, index").eq("location", location).range(offset, offset + page_size - 1).execute()
        rows = result.data or []
        for row in rows:
            if row.get("strap"):
                lookup[row["strap"]] = row["index"]
        if len(rows) < page_size:
            break
        offset += page_size

    return lookup


def load_permits(permits_csv: Path, strap_to_home: dict[str, str],
                 location: str, since_year: int | None = None) -> list[dict]:
    """Load parsed permits and prepare records for Supabase upsert."""
    df = pd.read_csv(permits_csv, low_memory=False)

    # Parse dates
    df["issue_dt"] = pd.to_datetime(df["issue_dt"], format="mixed", dayfirst=False, errors="coerce")
    bad_dates = df["issue_dt"].isna().sum()
    if bad_dates:
        print(f"  Warning: {bad_dates} rows with unparseable dates (filed_date will be null)")

    if since_year:
        df = df[df["issue_dt"].isna() | (df["issue_dt"].dt.year >= since_year)]

    # Filter to straps that exist in Supabase homes table
    df["strap"] = df["strap"].astype(str)
    df["home_index"] = df["strap"].map(strap_to_home)
    matched = df["home_index"].notna().sum()
    df = df.dropna(subset=["home_index"])
    print(f"  {matched:,} permits matched to {df['home_index'].nunique():,} homes")

    records = []
    for _, row in df.iterrows():
        valuation = row.get("estimated_value")
        valuation_num = float(valuation) if pd.notna(valuation) else None
        desc = str(row.get("description", "")).strip() if pd.notna(row.get("description")) else None
        permit_num = str(row.get("permit_num", "")).strip() if pd.notna(row.get("permit_num")) else None

        # A permit can have multiple types (comma-separated, e.g. "solar,battery").
        # Expand into one row per type for the Supabase upsert conflict key.
        permit_types = str(row.get("permit_type", "other")).split(",")
        filed_date = row["issue_dt"].strftime("%Y-%m-%d") if pd.notna(row["issue_dt"]) else None
        for ptype in permit_types:
            records.append({
                "home_index": row["home_index"],
                "permit_number": permit_num,
                "permit_type": ptype.strip(),
                "description": desc,
                "filed_date": filed_date,
                "valuation": valuation_num,
                "location": location,
            })

    # Deduplicate by conflict key (keep last occurrence)
    seen = {}
    for r in records:
        key = (r["home_index"], r["permit_number"], r["permit_type"])
        seen[key] = r
    deduped = list(seen.values())
    if len(deduped) < len(records):
        print(f"  Deduplicated: {len(records):,} → {len(deduped):,} ({len(records) - len(deduped):,} duplicates removed)")
    return deduped


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
    available = _list_available_configs()
    epilog = f"Available configs: {', '.join(available)}" if available else ""

    parser = argparse.ArgumentParser(
        description="Upload permits to Supabase",
        epilog=epilog,
    )
    parser.add_argument("--config", required=True,
                        help=f"County config name ({', '.join(available)}) or path to config .py file")
    parser.add_argument("--since", type=int, default=None,
                        help="Only upload permits from this year onward")
    parser.add_argument("--dry-run", action="store_true",
                        help="Parse and show stats without uploading")
    args = parser.parse_args()

    # Load pipeline config to get paths
    sys.path.insert(0, str(PROJECT_ROOT / "src"))
    from pipeline_config import load_config
    config = load_config(args.config)

    permits_csv = Path(config.parsed_permits_path)
    location = config.county_id

    print(f"Location: {location}")
    print(f"Permits CSV: {permits_csv}")

    if not permits_csv.exists():
        print(f"ERROR: Permits file not found: {permits_csv}")
        print(f"Run first: python src/parse_permits.py --config {args.config}")
        sys.exit(1)

    if not os.environ.get("SUPABASE_URL") or not os.environ.get("SUPABASE_SERVICE_ROLE_KEY"):
        print("\nERROR: Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY environment variables")
        sys.exit(1)

    print("Building strap → home_index lookup from Supabase...")
    strap_to_home = build_strap_lookup(location)
    print(f"  {len(strap_to_home):,} straps mapped")

    print("Loading parsed permits...")
    records = load_permits(permits_csv, strap_to_home, location, args.since)

    # Stats
    from collections import Counter
    type_counts = Counter(r["permit_type"] for r in records)
    print(f"\n  Total records: {len(records):,}")
    for ptype, count in sorted(type_counts.items(), key=lambda x: -x[1]):
        print(f"    {ptype}: {count:,}")

    if args.dry_run:
        print("\n--dry-run: skipping upload")
        for r in records[:5]:
            print(f"  Sample: {r}")
        return

    print("\nUploading to Supabase...")
    upload_to_supabase(records)


if __name__ == "__main__":
    main()
