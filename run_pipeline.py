#!/usr/bin/env python3
"""
End-to-end solar pipeline runner.

Usage:
    python run_pipeline.py boulder_co
    python run_pipeline.py boulder_co --limit 50          # only process 50 homes
    python run_pipeline.py boulder_co --start-from 5
    python run_pipeline.py boulder_co --step 3
    python run_pipeline.py boulder_co --skip-api
    python run_pipeline.py boulder_co --dry-run
"""

import argparse
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "data_science"))

from pipeline_config import load_config, validate_inputs


STAGES = [
    # (number, name, description)
    (1, "validate",            "Validate input files and create directories"),
    (2, "interest_rates",      "Compute average yearly mortgage interest rates"),
    (3, "filter_regrid_api",   "Filter Regrid data + call Google Sunroof API"),
    (4, "filter_solar",        "Filter API output by solar potential / roof score"),
    (5, "merge_regrid_api",    "Merge Regrid with filtered API output"),
    (6, "roof_score",          "Compute roof scores from Sunroof data"),
    (7, "parse_permits",       "Parse permit records into binary features"),
    (8, "census_enrichment",   "Census ACS demographic enrichment"),
    (9, "permits_by_year",     "Aggregate permits by strap-year with all features"),
    (10, "walk_forward_model", "Walk-forward ML modeling"),
    (11, "combine_ranks",      "Combine model scores with Regrid for final output"),
]


def log(msg):
    ts = time.strftime("%H:%M:%S")
    print(f"[{ts}] {msg}")


def run_stage(stage_num, config, skip_api=False, limit=None):
    """Run a single pipeline stage.

    Args:
        limit: Max number of homes to process. Applied at stage 3 (API calls)
               and stage 3 skip-api (Regrid filter). Downstream stages
               automatically process only what's in the data.
    """

    if stage_num == 1:
        log("Validating inputs...")
        errors = validate_inputs(config)
        if errors:
            for e in errors:
                log(f"  ERROR: {e}")
            raise RuntimeError("Input validation failed")
        config.ensure_dirs()
        log("Inputs validated. Directories created.")

    elif stage_num == 2:
        import interest_rates
        interest_rates.run(config)

    elif stage_num == 3:
        if skip_api:
            log("Skipping Sunroof API calls (--skip-api). Ensuring regrid_filtered exists...")
            import InitialScript
            import pandas as pd
            df = pd.read_csv(config.regrid_csv)
            df = InitialScript.apply_regrid_filters(df, config.regrid_filters)
            if "original_index" not in df.columns:
                df = df.reset_index(names="original_index")
            if limit:
                df = df.head(limit)
                log(f"Limited to {limit} homes (--limit)")
            df.to_csv(str(config.regrid_filtered_path), index=False)
            log(f"Saved filtered Regrid ({len(df)} rows) to {config.regrid_filtered_path}")
        else:
            import InitialScript
            InitialScript.run(config, limit=limit)

    elif stage_num == 4:
        import Analyze_ProjectSunroof_Data
        Analyze_ProjectSunroof_Data.run(config)

    elif stage_num == 5:
        import Combine_Regrid_ProjectSunroof_Data
        Combine_Regrid_ProjectSunroof_Data.run(config)

    elif stage_num == 6:
        import roof_score
        roof_score.run(config=config)

    elif stage_num == 7:
        import parse_permits
        parse_permits.run(config)

    elif stage_num == 8:
        import enrich_census
        enrich_census.run(config)

    elif stage_num == 9:
        import create_data_science_input
        create_data_science_input.run(config)

    elif stage_num == 10:
        import walk_forward_modeling
        walk_forward_modeling.run(config)

    elif stage_num == 11:
        import combine_regrid_model_rank
        combine_regrid_model_rank.run(config)


def main():
    parser = argparse.ArgumentParser(
        description="Run the solar pipeline end-to-end for a county.",
        epilog="Example: python run_pipeline.py boulder_co"
    )
    parser.add_argument("config", help="County config name (e.g. boulder_co) or path to config .py file")
    parser.add_argument("--start-from", type=int, default=1,
                        help="Start from stage N (default: 1)")
    parser.add_argument("--step", type=int, default=None,
                        help="Run only stage N")
    parser.add_argument("--limit", type=int, default=None,
                        help="Max homes to process (limits API calls and Regrid rows)")
    parser.add_argument("--skip-api", action="store_true",
                        help="Skip Sunroof API calls (use existing data)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print what would run without executing")

    args = parser.parse_args()

    log(f"Loading config: {args.config}")
    config = load_config(args.config)
    log(f"County: {config.county_id} ({config.state_abbrev})")
    log(f"Data dir: {config.data_dir}")
    if args.limit:
        log(f"Limit: {args.limit} homes")

    # Determine which stages to run
    if args.step is not None:
        stages_to_run = [(n, name, desc) for n, name, desc in STAGES if n == args.step]
    else:
        stages_to_run = [(n, name, desc) for n, name, desc in STAGES if n >= args.start_from]

    if not stages_to_run:
        log("No stages to run.")
        return

    log(f"\nPipeline stages to run:")
    for n, name, desc in stages_to_run:
        log(f"  {n:2d}. {name:25s} - {desc}")
    print()

    if args.dry_run:
        log("Dry run complete. No stages executed.")
        return

    start_time = time.time()
    for n, name, desc in stages_to_run:
        log(f"{'='*60}")
        log(f"Stage {n}: {desc}")
        log(f"{'='*60}")
        stage_start = time.time()

        try:
            run_stage(n, config, skip_api=args.skip_api, limit=args.limit)
        except Exception as e:
            log(f"FAILED at stage {n} ({name}): {e}")
            log(f"Resume with: python run_pipeline.py {args.config} --start-from {n}")
            raise

        elapsed = time.time() - stage_start
        log(f"Stage {n} complete ({elapsed:.1f}s)\n")

    total = time.time() - start_time
    log(f"Pipeline complete! Total time: {total:.1f}s")
    log(f"Final output: {config.regrid_model_rank_path}")


if __name__ == "__main__":
    main()
