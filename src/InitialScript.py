"""
Step 0: Filter Regrid data and call Google Sunroof API.

Reads the raw Regrid export, applies property filters, then calls the
Google Solar API for each property to get roof segment data.

NOTE - the API output appends to the existing CSV. Delete the output
file to recreate from scratch.
"""

import pandas as pd
from datetime import datetime
import SunroofBatchAPI_test


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


def run(config, max_calls=None, chunk_size=50, start_row=0):
    """Filter Regrid data and call Sunroof API.

    Args:
        config: CountyConfig object
        max_calls: Max API calls to make (None = all rows)
        chunk_size: Rows per API batch
        start_row: Row to start from (for resuming)
    """
    config.ensure_dirs()

    print(f"Reading Regrid data from {config.regrid_csv}")
    df = pd.read_csv(config.regrid_csv)
    print(f"Raw records: {len(df)}")

    df = apply_regrid_filters(df, config.regrid_filters)
    print(f"After filters: {len(df)}")

    # Ensure we have original_index
    if "original_index" not in df.columns:
        df = df.reset_index(names="original_index")

    # Save the filtered Regrid data (used later by create_parsed_permits_by_year)
    df.to_csv(str(config.regrid_filtered_path), index=False)
    print(f"Saved filtered Regrid to {config.regrid_filtered_path}")

    csv_output = str(config.sunroof_api_output_path)

    if max_calls is None:
        max_calls = len(df)

    call_counter = 0
    current_row = start_row

    print(f"Starting Sunroof API calls: start_row={start_row}, max_calls={max_calls}")

    while call_counter < max_calls:
        remaining = max_calls - call_counter
        current_chunk = min(chunk_size, remaining)

        subset = df.iloc[current_row : current_row + current_chunk]

        if subset.empty:
            break

        SunroofBatchAPI_test.run(
            subset,
            csv_output,
            resume=True
        )

        current_row += current_chunk
        call_counter += len(subset)

    print(f"Sunroof API complete. Output: {csv_output}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True, help="County config name or path")
    parser.add_argument("--max-calls", type=int, default=None, help="Max API calls")
    parser.add_argument("--start-row", type=int, default=0, help="Start row for resuming")
    args = parser.parse_args()

    from pipeline_config import load_config
    run(load_config(args.config), max_calls=args.max_calls, start_row=args.start_row)
