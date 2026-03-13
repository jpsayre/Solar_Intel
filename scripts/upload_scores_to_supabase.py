#!/usr/bin/env python3
"""
Build home_scores_upload.csv and optionally upsert to Supabase.

Joins model scores (gb_score → percentile rank 1–100) and roof scores
(already 0–100 from roof_score.py v2) to home indexes.

Usage:
  python scripts/upload_scores_to_supabase.py --config boulder_co
  python scripts/upload_scores_to_supabase.py --config boulder_co --upload
"""

from __future__ import annotations

import argparse
import os
import sys
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


def build_home_scores(config) -> pd.DataFrame:
    """Build a DataFrame of home_index, county, model_score, roof_score."""
    regrid_filtered_path = config.regrid_filtered_path
    roof_score_path = config.roof_score_path
    straps_path = config.straps_no_solar_path
    county_id = config.county_id

    # Load regrid_filtered for the strap → home_index bridge
    print(f"Loading regrid_filtered: {regrid_filtered_path}")
    rf = pd.read_csv(regrid_filtered_path, low_memory=False)
    rf["county_upper"] = rf["county"].astype(str).str.strip().str.upper()
    rf["home_index"] = (
        rf["county_upper"] + "_" + rf["state2"].astype(str) + "_"
        + rf["original_index"].astype(str)
    )
    bridge = rf[["home_index", "strap", "original_index"]].copy()
    bridge["original_index"] = bridge["original_index"].astype(str)
    print(f"  {len(bridge):,} homes")

    # Load roof scores and join via original_index
    print(f"Loading roof scores: {roof_score_path}")
    roof = pd.read_csv(roof_score_path)
    roof["original_index"] = roof["original_index"].astype(str)
    print(f"  {roof['roof_score'].notna().sum():,} non-null roof scores")

    merged = bridge.merge(roof, on="original_index", how="left")

    # Load model scores and join via strap
    print(f"Loading model scores: {straps_path}")
    if straps_path.exists():
        straps = pd.read_csv(straps_path)
        print(f"  {len(straps):,} straps with model scores")

        # Convert gb_score to percentile rank (1–100)
        straps = straps[straps["gb_score"].notna()].copy()
        straps["model_score"] = straps["gb_score"].rank(pct=True).mul(100).round().astype(int)
        straps["model_score"] = straps["model_score"].clip(lower=1)

        merged = merged.merge(
            straps[["strap", "model_score"]],
            on="strap",
            how="left",
        )
    else:
        print(f"  WARNING: {straps_path} not found, skipping model scores")
        merged["model_score"] = np.nan

    # Round roof_score to integer for display
    merged["roof_score"] = merged["roof_score"].round().astype("Int64")
    merged["model_score"] = merged["model_score"].astype("Int64")

    result = pd.DataFrame({
        "home_index": merged["home_index"],
        "model_score": merged["model_score"],
        "roof_score": merged["roof_score"],
        "model_version": "walk_forward_ensemble_2026",
    })

    # Deduplicate: keep first row per home_index (join can produce dupes)
    result = result.drop_duplicates(subset="home_index", keep="first")

    # model_score is NOT NULL in Supabase — drop rows without one
    n_before = len(result)
    result = result[result["model_score"].notna()].copy()

    n_model = len(result)
    n_roof = result["roof_score"].notna().sum()
    print(f"\nPrepared {n_model:,} rows ({n_before - n_model:,} dropped — no model score):")
    print(f"  With model_score: {n_model:,}")
    print(f"  With roof_score:  {n_roof:,}")

    return result


def upload_to_supabase(df: pd.DataFrame, batch_size: int = 500) -> None:
    """Upsert records to Supabase home_scores table."""
    from supabase import create_client

    url = os.environ["SUPABASE_URL"]
    key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    client = create_client(url, key)

    records = df.to_dict(orient="records")
    # Convert pandas NA to None for JSON
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

    print(f"Done. {uploaded} score records upserted.")


def main():
    parser = argparse.ArgumentParser(description="Build and upload home scores")
    parser.add_argument("--config", required=True, help="County config name")
    parser.add_argument("--upload", action="store_true", help="Upload to Supabase")
    args = parser.parse_args()

    from pipeline_config import load_config
    config = load_config(args.config)

    df = build_home_scores(config)

    output_path = PROJECT_ROOT / "data" / "final" / "home_scores_upload.csv"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False)
    print(f"\nSaved to {output_path}")

    if args.upload:
        if not os.environ.get("SUPABASE_URL") or not os.environ.get("SUPABASE_SERVICE_ROLE_KEY"):
            print("\nERROR: Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY")
            sys.exit(1)
        print("\nUploading to Supabase...")
        upload_to_supabase(df)


if __name__ == "__main__":
    main()
