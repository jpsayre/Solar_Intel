"""
Step 0: Filter Regrid data and call Google Sunroof API.

Reads the raw Regrid export, applies property filters, then calls the
Google Solar API for each property to get roof segment data.

NOTE - the API output appends to the existing CSV. Delete the output
file to recreate from scratch.
"""

import pandas as pd
from datetime import datetime
import SunroofBatchAPI


def apply_regrid_filters(df, filters):
    """Apply configurable filters to the Regrid dataframe.

    Args:
        df: Raw Regrid DataFrame
        filters: Dict of filter rules from county config
    """
    if not filters:
        return df

    if "usedesc" in filters:
        df = df[df["usedesc"].isin(filters["usedesc"])]

    if "zoning_description_contains" in filters:
        pattern = filters["zoning_description_contains"]
        df = df[df["zoning_description"].str.contains(pattern, case=False, na=False)]

    if "designcodedscr" in filters:
        df = df[df["designcodedscr"].isin(filters["designcodedscr"])]

    if "sales_cd" in filters:
        df = df[df["sales_cd"].isin(filters["sales_cd"])]

    if "mainfloorsf_min" in filters:
        df = df[df["mainfloorsf"] >= filters["mainfloorsf_min"]]

    if "saleprice_min" in filters:
        df = df[df["saleprice"] >= filters["saleprice_min"]]

    if filters.get("owner_occupied"):
        df['OwnerOccupied'] = (
            df['mailadd'].astype(str).str[:6] == df['address'].astype(str).str[:6]
        )
        df = df[df["OwnerOccupied"] == True]

    if "calculated_build_year_min" in filters:
        df['calculated_build_year'] = (
            df[['yearbuilt', 'year_built_effective_date']]
            .apply(pd.to_numeric, errors='coerce')
            .max(axis=1)
        )
        df = df[df["calculated_build_year"] >= filters["calculated_build_year_min"]]

    return df


def run(config, limit=None):
    """Filter Regrid data and call Sunroof API.

    Args:
        config: CountyConfig object
        limit: Max NEW API calls to make (None = all). Existing rows are
               skipped and don't count toward the limit.
    """
    config.ensure_dirs()

    print(f"Reading Regrid data from {config.regrid_csv}")
    df = pd.read_csv(config.regrid_csv)
    print(f"Raw records: {len(df)}")

    df = apply_regrid_filters(df, config.regrid_filters)
    print(f"After filters: {len(df)}")

    before = len(df)
    # Keep the most complete row when deduplicating by address
    completeness_cols = ["area_building", "num_bedrooms", "num_bath", "numrooms"]
    df["_completeness"] = df[completeness_cols].notna().sum(axis=1)
    df = df.sort_values("_completeness", ascending=False).drop_duplicates(subset=["address"], keep="first")
    df = df.drop(columns=["_completeness"])
    print(f"After address dedup: {len(df)} (removed {before - len(df)} duplicates)")

    # Ensure we have original_index
    if "original_index" not in df.columns:
        df = df.reset_index(names="original_index")

    # Save the filtered Regrid data (used later by create_data_science_input)
    df.to_csv(str(config.regrid_filtered_path), index=False)
    print(f"Saved filtered Regrid to {config.regrid_filtered_path}")

    csv_output = str(config.sunroof_api_output_path)

    print(f"Starting Sunroof API calls: {len(df)} rows, limit={limit or 'none'}")

    new_calls = SunroofBatchAPI.run(
        df,
        csv_output,
        resume=True,
        max_new_calls=limit,
    )

    print(f"Sunroof API complete. {new_calls} new calls made. Output: {csv_output}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True, help="County config name or path")
    parser.add_argument("--limit", type=int, default=None,
                        help="Max NEW API calls (skipped rows don't count)")
    args = parser.parse_args()

    from pipeline_config import load_config
    run(load_config(args.config), limit=args.limit)
