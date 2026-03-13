#!/usr/bin/env python3
"""
Validate permit classification results.

Reads parsed_permits.csv and regrid_filtered.csv, filters to matched homes,
and produces a diagnostic report covering category coverage, permit_type
distribution, "other" analysis, cross-strap duplicates, and valuation stats.

Usage:
    python scripts/validate_permits.py --config boulder_co
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from pathlib import Path

import pandas as pd
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from parse_permits_features import CATEGORY_MATCHES, get_feature_names


def _list_available_configs() -> list[str]:
    configs_dir = PROJECT_ROOT / "configs"
    if not configs_dir.exists():
        return []
    return sorted(p.stem for p in configs_dir.glob("*.py") if not p.name.startswith("_"))


def load_data(config) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Load parsed_permits.csv and regrid_filtered.csv, filter permits to matched straps."""
    permits_path = config.parsed_permits_path
    regrid_path = config.regrid_filtered_path

    if not permits_path.exists():
        print(f"ERROR: {permits_path} not found. Run parse_permits.py first.")
        sys.exit(1)
    if not regrid_path.exists():
        print(f"ERROR: {regrid_path} not found. Run the pipeline first.")
        sys.exit(1)

    permits = pd.read_csv(permits_path, low_memory=False)
    regrid = pd.read_csv(regrid_path, low_memory=False, usecols=["strap"])

    permits["strap"] = permits["strap"].astype(str)
    regrid["strap"] = regrid["strap"].astype(str)
    regrid_straps = set(regrid["strap"].unique())

    matched = permits[permits["strap"].isin(regrid_straps)].copy()
    print(f"Permits: {len(permits):,} total, {len(matched):,} matched to {len(regrid_straps):,} regrid homes")
    print(f"  ({len(permits) - len(matched):,} permits dropped — straps not in regrid)")
    print()

    return matched, regrid


def section_category_coverage(df: pd.DataFrame):
    """Section 1: Which permit_category values are being matched by CATEGORY_MATCHES."""
    print("=" * 70)
    print("1. CATEGORY COVERAGE")
    print("=" * 70)

    if "permit_category" not in df.columns:
        print("  No permit_category column — skipping")
        return

    cat_counts = df["permit_category"].fillna("(empty)").value_counts()

    # For each category value, check which CATEGORY_MATCHES it triggers
    matched_cats = {}
    for cat_val in cat_counts.index:
        cat_lower = str(cat_val).lower()
        triggers = []
        for feature, keywords in CATEGORY_MATCHES.items():
            for kw in keywords:
                if kw in cat_lower:
                    triggers.append(feature)
                    break
        matched_cats[cat_val] = triggers

    unmatched = [(cat, count) for cat, count in cat_counts.items()
                 if not matched_cats.get(cat)]
    matched = [(cat, count) for cat, count in cat_counts.items()
               if matched_cats.get(cat)]

    n_matched_permits = sum(c for _, c in matched)
    n_total = len(df)
    print(f"\n  {len(matched)} category values matched patterns ({n_matched_permits:,} permits, {n_matched_permits/n_total*100:.1f}%)")
    print(f"  {len(unmatched)} category values unmatched")

    if matched:
        print(f"\n  Matched categories:")
        for cat, count in sorted(matched, key=lambda x: -x[1]):
            features = ", ".join(matched_cats[cat])
            print(f"    {count:>8,}  {cat} -> {features}")

    # Flag unmatched categories with significant counts
    significant_unmatched = [(cat, count) for cat, count in unmatched if count > 50]
    if significant_unmatched:
        print(f"\n  ** Unmatched categories with >50 permits (candidates for new rules):")
        for cat, count in sorted(significant_unmatched, key=lambda x: -x[1]):
            print(f"    {count:>8,}  {cat}")

    # Show remaining unmatched
    small_unmatched = [(cat, count) for cat, count in unmatched if count <= 50]
    if small_unmatched:
        total_small = sum(c for _, c in small_unmatched)
        print(f"\n  {len(small_unmatched)} other unmatched categories ({total_small:,} permits total, all <=50 each)")

    print()


def _explode_types(df: pd.DataFrame) -> pd.Series:
    """Explode comma-separated permit_type into individual values."""
    return df["permit_type"].str.split(",").explode().str.strip()


def section_permit_type_distribution(df: pd.DataFrame, config, validation_dir: Path):
    """Section 2: permit_type distribution with baseline comparison."""
    print("=" * 70)
    print("2. PERMIT_TYPE DISTRIBUTION")
    print("=" * 70)

    if "permit_type" not in df.columns:
        print("  No permit_type column — skipping")
        return

    # Explode comma-separated multi-type values for counting
    exploded = _explode_types(df)
    type_counts = exploded.value_counts()
    total = len(df)
    multi_type = (df["permit_type"].str.contains(",", na=False)).sum()
    if multi_type:
        print(f"\n  ({multi_type:,} permits have multiple types — counts below sum to more than total)")

    # Load baseline if exists
    baseline_path = validation_dir / "baseline_distribution.json"
    baseline = None
    if baseline_path.exists():
        with open(baseline_path) as f:
            baseline = json.load(f)

    print(f"\n  {'Type':<20} {'Count':>10} {'Pct':>8}", end="")
    if baseline:
        print(f"  {'Baseline':>10} {'Delta':>8}", end="")
    print()
    print(f"  {'-'*20} {'-'*10} {'-'*8}", end="")
    if baseline:
        print(f"  {'-'*10} {'-'*8}", end="")
    print()

    for ptype in sorted(type_counts.index):
        count = type_counts[ptype]
        pct = count / total * 100
        line = f"  {ptype:<20} {count:>10,} {pct:>7.1f}%"
        if baseline and ptype in baseline:
            b_pct = baseline[ptype]["pct"]
            delta = pct - b_pct
            line += f"  {b_pct:>9.1f}% {delta:>+7.1f}%"
        print(line)

    # Flags (use exploded counts)
    other_pct = type_counts.get("other", 0) / total * 100
    solar_pct = type_counts.get("solar", 0) / total * 100

    print()
    if other_pct > 50:
        print(f"  ** WARNING: 'other' is {other_pct:.1f}% — patterns likely need work for this county")
    if solar_pct > 5:
        print(f"  ** WARNING: solar is {solar_pct:.1f}% — unusually high, check for false positives")
    if solar_pct < 0.1 and total > 1000:
        print(f"  ** WARNING: solar is {solar_pct:.1f}% — unusually low, check for missed patterns")

    # Save current as baseline
    validation_dir.mkdir(parents=True, exist_ok=True)
    current = {}
    for ptype, count in type_counts.items():
        current[ptype] = {"count": int(count), "pct": round(count / total * 100, 2)}
    current["_total"] = int(total)
    current["_county"] = config.county_id

    with open(baseline_path, "w") as f:
        json.dump(current, f, indent=2)
    print(f"\n  Saved baseline to {baseline_path}")
    print()


def section_other_analysis(df: pd.DataFrame):
    """Section 3: Top 'other' permits by category+description."""
    print("=" * 70)
    print("3. 'OTHER' ANALYSIS (missed classifications)")
    print("=" * 70)

    others = df[df["permit_type"].str.strip() == "other"].copy()
    if len(others) == 0:
        print("  No 'other' permits — all classified!")
        print()
        return

    print(f"\n  {len(others):,} permits classified as 'other'")

    # Group by permit_category
    if "permit_category" in others.columns:
        cat_counts = others["permit_category"].fillna("(empty)").value_counts()
        print(f"\n  'Other' by permit_category:")
        for cat, count in cat_counts.head(20).items():
            print(f"    {count:>8,}  {cat}")

    # Top category+description pairs
    if "description" in others.columns and "permit_category" in others.columns:
        others["_desc_clean"] = others["description"].fillna("(no description)")
        others["_cat_clean"] = others["permit_category"].fillna("(no category)")
        pair_counts = others.groupby(["_cat_clean", "_desc_clean"]).size().sort_values(ascending=False)

        print(f"\n  Top 30 'other' (category | description) pairs:")
        for (cat, desc), count in pair_counts.head(30).items():
            # Truncate for console display only
            desc_display = desc[:80] + "..." if len(str(desc)) > 80 else desc
            print(f"    {count:>6,}  {cat} | {desc_display}")

    print()


def section_cross_strap_duplicates(df: pd.DataFrame):
    """Section 4: Descriptions appearing on too many different straps."""
    print("=" * 70)
    print("4. CROSS-STRAP DUPLICATE CHECK")
    print("=" * 70)

    if "description" not in df.columns:
        print("  No description column — skipping")
        print()
        return

    # Only check non-empty descriptions with enough specificity (>30 chars)
    # Short generic descriptions like "Re-Roof" naturally appear on many straps
    has_desc = df[df["description"].notna() & (df["description"].str.strip() != "")]
    specific_desc = has_desc[has_desc["description"].str.len() > 30]
    desc_strap_counts = specific_desc.groupby("description")["strap"].nunique()
    suspicious = desc_strap_counts[desc_strap_counts > 2].sort_values(ascending=False)

    if len(suspicious) == 0:
        print("  No specific descriptions (>30 chars) appearing on >2 different straps")
    else:
        print(f"\n  ** {len(suspicious):,} specific descriptions (>30 chars) appear on >2 different straps")
        print(f"  (Short generic descriptions like 'Re-Roof' are excluded)")
        print(f"\n  Top 10:")
        for desc, n_straps in suspicious.head(10).items():
            n_permits = len(specific_desc[specific_desc["description"] == desc])
            desc_display = desc[:100] + "..." if len(str(desc)) > 100 else desc
            print(f"    {n_straps:>5} straps, {n_permits:>6} permits: {desc_display}")

    print()


def section_valuation_stats(df: pd.DataFrame):
    """Section 5: Valuation statistics per permit_type."""
    print("=" * 70)
    print("5. VALUATION STATS")
    print("=" * 70)

    if "estimated_value" not in df.columns or "permit_type" not in df.columns:
        print("  Missing estimated_value or permit_type column — skipping")
        print()
        return

    df["_val"] = pd.to_numeric(df["estimated_value"], errors="coerce")

    # Explode multi-type permits so each type gets the valuation stats
    exploded = df.assign(permit_type=df["permit_type"].str.split(",")).explode("permit_type")
    exploded["permit_type"] = exploded["permit_type"].str.strip()

    print(f"\n  {'Type':<20} {'Median':>10} {'Mean':>10} {'Min':>10} {'Max':>12} {'%Null':>8}")
    print(f"  {'-'*20} {'-'*10} {'-'*10} {'-'*10} {'-'*12} {'-'*8}")

    for ptype in sorted(exploded["permit_type"].unique()):
        subset = exploded[exploded["permit_type"] == ptype]["_val"]
        n_null = subset.isna().sum()
        pct_null = n_null / len(subset) * 100 if len(subset) > 0 else 0
        valid = subset.dropna()
        if len(valid) > 0:
            print(f"  {ptype:<20} {valid.median():>10,.0f} {valid.mean():>10,.0f} "
                  f"{valid.min():>10,.0f} {valid.max():>12,.0f} {pct_null:>7.1f}%")
        else:
            print(f"  {ptype:<20} {'n/a':>10} {'n/a':>10} {'n/a':>10} {'n/a':>12} {pct_null:>7.1f}%")

    # Check solar permits with low valuation
    # The sanity check removes solar_pv when value < $3k AND no strong keywords.
    # Solar permits that remain with low value have strong keywords ("solar", "photovoltaic", etc.)
    solar = exploded[exploded["permit_type"] == "solar"]
    low_val_solar = solar[solar["_val"].notna() & (solar["_val"] < 3000)]
    if len(low_val_solar) > 0:
        print(f"\n  Solar permits with valuation < $3k: {len(low_val_solar)} (kept because they have strong solar keywords)")
        if "description" in df.columns:
            sample = low_val_solar.head(5)
            for _, row in sample.iterrows():
                desc = str(row.get("description", ""))[:80]
                val = row["_val"]
                print(f"    ${val:,.0f}: {desc}")
    else:
        print(f"\n  No solar permits with valuation < $3k")

    print()


def main():
    available = _list_available_configs()
    epilog = f"Available configs: {', '.join(available)}" if available else ""

    parser = argparse.ArgumentParser(
        description="Validate permit classification results",
        epilog=epilog,
    )
    parser.add_argument("--config", required=True,
                        help=f"County config name ({', '.join(available)}) or path to config .py file")
    args = parser.parse_args()

    from pipeline_config import load_config
    config = load_config(args.config)

    validation_dir = config.data_dir / "validation"

    print(f"Permit Classification Validation Report")
    print(f"County: {config.county_id}")
    print(f"Permits: {config.parsed_permits_path}")
    print(f"Regrid:  {config.regrid_filtered_path}")
    print()

    df, regrid = load_data(config)

    section_category_coverage(df)
    section_permit_type_distribution(df, config, validation_dir)
    section_other_analysis(df)
    section_cross_strap_duplicates(df)
    section_valuation_stats(df)

    print("=" * 70)
    print("DONE")
    print("=" * 70)


if __name__ == "__main__":
    main()
