#!/usr/bin/env python3
"""
Combine straps_no_solar_as_of_2026.csv (model scores) and roof_score.csv with Regrid_Reduced.csv.

Merges on strap (model scores) and on (strap, lat, lon) via regrid_filtered (roof_score).
Adds gb_score, gb_decile, ensemble_score, ensemble_decile, hybrid_score, hybrid_decile,
and roof_score to each Regrid row. Rows without matches will have NaN for those columns.
"""

from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
STRAPS_PATH = PROJECT_ROOT / "data_science" / "output" / "walk_forward" / "straps_no_solar_as_of_2026.csv"
REGRID_PATH = PROJECT_ROOT / "data" / "raw" / "Regrid_Reduced.csv"
REGRID_FILTERED_PATH = PROJECT_ROOT / "data" / "final" / "regrid_filtered.csv"
ROOF_SCORE_PATH = PROJECT_ROOT / "data" / "final" / "roof_score.csv"
OUTPUT_PATH = PROJECT_ROOT / "data" / "final" / "Regrid_Model_Rank.csv"


def main() -> None:
    print("Loading straps_no_solar_as_of_2026.csv...")
    straps = pd.read_csv(STRAPS_PATH)
    print(f"  Loaded {len(straps):,} straps with model scores")

    print("Loading roof_score.csv...")
    roof_score = pd.read_csv(ROOF_SCORE_PATH)
    print(f"  Loaded {len(roof_score):,} roof scores")

    print("Loading regrid_filtered.csv (bridge for roof_score)...")
    regrid_filtered = pd.read_csv(REGRID_FILTERED_PATH)
    roof_by_location = regrid_filtered[["original_index", "strap", "lat", "lon"]].merge(
        roof_score, on="original_index", how="inner"
    )[["strap", "lat", "lon", "roof_score"]]

    print("Loading Regrid_Reduced.csv...")
    regrid = pd.read_csv(REGRID_PATH)
    print(f"  Loaded {len(regrid):,} Regrid rows")

    print("Merging model scores on strap (left join)...")
    merged = regrid.merge(straps, on="strap", how="left")

    print("Merging roof_score on strap+lat+lon (left join)...")
    merged = merged.merge(
        roof_by_location[["strap", "lat", "lon", "roof_score"]],
        on=["strap", "lat", "lon"],
        how="left",
    )

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    merged.to_csv(OUTPUT_PATH, index=False)
    print(f"Saved {len(merged):,} rows to {OUTPUT_PATH}")

    n_with_scores = merged["gb_score"].notna().sum()
    n_with_roof = merged["roof_score"].notna().sum()
    print(f"  Rows with model scores: {n_with_scores:,} ({100 * n_with_scores / len(merged):.1f}%)")
    print(f"  Rows with roof_score: {n_with_roof:,} ({100 * n_with_roof / len(merged):.1f}%)")


if __name__ == "__main__":
    main()
