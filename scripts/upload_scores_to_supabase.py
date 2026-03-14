#!/usr/bin/env python3
"""
Upload roof scores and/or model rank scores to Supabase home_scores table.

Each score type can be uploaded independently — upserts on home_index so
running --roof now and --rank later just fills in the other column.

Usage:
  python scripts/upload_scores_to_supabase.py --config boulder_co --roof
  python scripts/upload_scores_to_supabase.py --config boulder_co --rank
  python scripts/upload_scores_to_supabase.py --config boulder_co --roof --rank
  python scripts/upload_scores_to_supabase.py --config boulder_co --roof --upload
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import numpy as np
import pandas as pd

try:
    from dotenv import load_dotenv
    load_dotenv(PROJECT_ROOT / ".env")
except ImportError:
    pass


def build_home_index_bridge(config) -> pd.DataFrame:
    """Load regrid_filtered and build home_index ↔ original_index ↔ strap bridge."""
    print(f"Loading regrid_filtered: {config.regrid_filtered_path}")
    rf = pd.read_csv(config.regrid_filtered_path, low_memory=False)
    rf["county_upper"] = rf["county"].astype(str).str.strip().str.upper()
    rf["home_index"] = (
        rf["county_upper"] + "_" + rf["state2"].astype(str) + "_"
        + rf["original_index"].astype(str)
    )
    bridge = rf[["home_index", "strap", "original_index"]].copy()
    bridge["original_index"] = bridge["original_index"].astype(str)
    print(f"  {len(bridge):,} homes")
    return bridge


def build_roof_scores(config, bridge: pd.DataFrame) -> pd.DataFrame:
    """Join roof scores to home_index. Returns DataFrame with home_index + roof_score."""
    print(f"Loading roof scores: {config.roof_score_path}")
    roof = pd.read_csv(config.roof_score_path)
    roof["original_index"] = roof["original_index"].astype(str)
    print(f"  {roof['roof_score'].notna().sum():,} non-null roof scores")

    merged = bridge[["home_index", "original_index"]].merge(roof, on="original_index", how="inner")
    merged["roof_score"] = merged["roof_score"].round().astype("Int64")
    result = merged[["home_index", "roof_score"]].drop_duplicates(subset="home_index", keep="first")
    result = result[result["roof_score"].notna()].copy()
    result["roof_updated_at"] = datetime.now(timezone.utc).isoformat()
    print(f"  {len(result):,} homes with roof scores")
    return result


def build_rank_scores(config, bridge: pd.DataFrame) -> pd.DataFrame:
    """Join model rank scores to home_index. Returns DataFrame with home_index + model_score."""
    straps_path = config.straps_no_solar_path
    print(f"Loading model scores: {straps_path}")

    if not straps_path.exists():
        print(f"  ERROR: {straps_path} not found")
        sys.exit(1)

    straps = pd.read_csv(straps_path)
    print(f"  {len(straps):,} straps")

    straps = straps[straps["gb_score"].notna()].copy()
    straps["model_score"] = straps["gb_score"].rank(pct=True).mul(100).round().astype(int)
    straps["model_score"] = straps["model_score"].clip(lower=1)

    merged = bridge[["home_index", "strap"]].merge(
        straps[["strap", "model_score"]], on="strap", how="inner"
    )
    merged["model_score"] = merged["model_score"].astype("Int64")
    result = merged[["home_index", "model_score"]].drop_duplicates(subset="home_index", keep="first")
    result["ranking_updated_at"] = datetime.now(timezone.utc).isoformat()
    print(f"  {len(result):,} homes with model scores")
    return result


def upload_to_supabase(df: pd.DataFrame, batch_size: int = 500) -> None:
    """Upsert records to Supabase home_scores table."""
    from supabase import create_client

    url = os.environ["SUPABASE_URL"]
    key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    client = create_client(url, key)

    records = df.to_dict(orient="records")
    for r in records:
        for k, v in r.items():
            if pd.isna(v):
                r[k] = None

    total = len(records)
    uploaded = 0

    for i in range(0, total, batch_size):
        batch = records[i : i + batch_size]
        client.table("home_scores").upsert(batch, on_conflict="home_index").execute()
        uploaded += len(batch)
        if uploaded <= batch_size or uploaded % 2000 == 0 or uploaded == total:
            print(f"  Upserted {uploaded}/{total}...")

    print(f"Done. {uploaded} records upserted.")


def main():
    parser = argparse.ArgumentParser(description="Upload scores to Supabase")
    parser.add_argument("--config", required=True, help="County config name")
    parser.add_argument("--roof", action="store_true", help="Include roof scores")
    parser.add_argument("--rank", action="store_true", help="Include model rank scores")
    parser.add_argument("--upload", action="store_true", help="Upload to Supabase (otherwise dry run)")
    args = parser.parse_args()

    if not args.roof and not args.rank:
        parser.error("Specify at least one of --roof or --rank")

    from pipeline_config import load_config
    config = load_config(args.config)

    bridge = build_home_index_bridge(config)

    frames = []
    if args.roof:
        frames.append(build_roof_scores(config, bridge))
    if args.rank:
        frames.append(build_rank_scores(config, bridge))

    # Merge score frames on home_index
    if len(frames) == 1:
        df = frames[0]
    else:
        df = frames[0].merge(frames[1], on="home_index", how="outer")

    # Add model_version for rank scores
    if args.rank:
        df["model_version"] = "walk_forward_ensemble_2026"

    print(f"\n{len(df):,} rows to upload")

    output_path = PROJECT_ROOT / "data" / "final" / "home_scores_upload.csv"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False)
    print(f"Saved to {output_path}")

    if args.upload:
        if not os.environ.get("SUPABASE_URL") or not os.environ.get("SUPABASE_SERVICE_ROLE_KEY"):
            print("\nERROR: Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY")
            sys.exit(1)
        print("\nUploading to Supabase...")
        upload_to_supabase(df)


if __name__ == "__main__":
    main()
