#!/usr/bin/env python3
"""
Combine model scores and roof_score with Regrid data.

Merges on strap (model scores) and on (strap, lat, lon) via regrid_filtered (roof_score).
Adds gb_score, gb_decile, ensemble_score, ensemble_decile, hybrid_score, hybrid_decile,
and roof_score to each Regrid row.
"""

from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Default paths (used when no config provided)
STRAPS_PATH = PROJECT_ROOT / "data_science" / "output" / "walk_forward" / "straps_no_solar_as_of_2026.csv"
REGRID_PATH = PROJECT_ROOT / "data" / "raw" / "Regrid_Reduced.csv"
REGRID_FILTERED_PATH = PROJECT_ROOT / "data" / "final" / "regrid_filtered.csv"
ROOF_SCORE_PATH = PROJECT_ROOT / "data" / "final" / "roof_score.csv"
OUTPUT_PATH = PROJECT_ROOT / "data" / "final" / "Regrid_Model_Rank.csv"


def main(config=None) -> None:
    if config:
        straps_path = config.straps_no_solar_path
        regrid_path = Path(config.regrid_csv)
        regrid_filtered_path = config.regrid_filtered_path
        roof_score_path = config.roof_score_path
        output_path = config.regrid_model_rank_path
        strap_col = config.strap_column
        config.ensure_dirs()
    else:
        straps_path = STRAPS_PATH
        regrid_path = REGRID_PATH
        regrid_filtered_path = REGRID_FILTERED_PATH
        roof_score_path = ROOF_SCORE_PATH
        output_path = OUTPUT_PATH
        strap_col = "alt_parcelnumb1"

    print(f"Loading model scores from {straps_path}...")
    straps = pd.read_csv(straps_path)
    print(f"  Loaded {len(straps):,} straps with model scores")

    print(f"Loading roof_score from {roof_score_path}...")
    roof_score = pd.read_csv(roof_score_path)
    print(f"  Loaded {len(roof_score):,} roof scores")

    print(f"Loading regrid_filtered (bridge for roof_score)...")
    regrid_filtered = pd.read_csv(regrid_filtered_path)
    lat_col = "lat" if "lat" in regrid_filtered.columns else "latitude"
    lon_col = "lon" if "lon" in regrid_filtered.columns else "longitude"
    roof_by_location = regrid_filtered[["original_index", "strap", lat_col, lon_col]].merge(
        roof_score, on="original_index", how="inner"
    )[["strap", lat_col, lon_col, "roof_score"]]

    print(f"Loading Regrid from {regrid_path}...")
    regrid = pd.read_csv(regrid_path)
    if "strap" not in regrid.columns and strap_col in regrid.columns:
        regrid["strap"] = regrid[strap_col].astype(str)
    print(f"  Loaded {len(regrid):,} Regrid rows")

    print("Merging model scores on strap (left join)...")
    merged = regrid.merge(straps, on="strap", how="left")

    print("Merging roof_score on strap+lat+lon (left join)...")
    merged = merged.merge(
        roof_by_location[["strap", lat_col, lon_col, "roof_score"]],
        on=["strap", lat_col, lon_col],
        how="left",
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    merged.to_csv(output_path, index=False)
    print(f"Saved {len(merged):,} rows to {output_path}")

    n_with_scores = merged["gb_score"].notna().sum() if "gb_score" in merged.columns else 0
    n_with_roof = merged["roof_score"].notna().sum() if "roof_score" in merged.columns else 0
    print(f"  Rows with model scores: {n_with_scores:,} ({100 * n_with_scores / len(merged):.1f}%)")
    print(f"  Rows with roof_score: {n_with_roof:,} ({100 * n_with_roof / len(merged):.1f}%)")


def run(config):
    """Pipeline entry point."""
    main(config=config)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", help="County config name or path")
    args = parser.parse_args()

    if args.config:
        import sys
        sys.path.insert(0, str(PROJECT_ROOT / "src"))
        from pipeline_config import load_config
        main(config=load_config(args.config))
    else:
        main()
