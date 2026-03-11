"""
Step 2: Merge Regrid property data with filtered Sunroof API output.

Inner join on original_index. Supports incremental appends to
preserve downstream-filled columns from previous runs.
"""

import os
import pandas as pd
import numpy as np


def run(config=None):
    """Merge Regrid data with filtered API output.

    Args:
        config: CountyConfig object. If None, uses legacy hardcoded paths.
    """
    if config:
        regrid_path = str(config.regrid_filtered_path)
        api_path = str(config.filtered_api_output_path)
        output_path = str(config.regrid_joined_path)
        config.ensure_dirs()
    else:
        location = 'Boulder_CO'
        regrid_path = f'/Users/jeffs/Projects/SolarProject/data/working/{location}_Primary_Regrid_Filter_Output.csv'
        api_path = f"/Users/jeffs/Projects/SolarProject/data/working/{location}_Filtered_API_Output.csv"
        output_path = f"/Users/jeffs/Projects/SolarProject/data/working/{location}_Regrid_joined_with_API.csv"

    A = pd.read_csv(regrid_path)
    B = pd.read_csv(api_path)

    # Inner join (only matched rows kept)
    merged = A.merge(B, how="inner", on="original_index")

    # Incremental append: preserve downstream-filled columns
    if os.path.exists(output_path):
        existing = pd.read_csv(output_path)
        existing_ids = set(existing["original_index"].astype(str))
        new_rows = merged[~merged["original_index"].astype(str).isin(existing_ids)]
        to_write = pd.concat([existing, new_rows], ignore_index=True)
    else:
        to_write = merged

    to_write.to_csv(output_path, index=False)
    print(f"Merged {len(merged)} rows. Output: {output_path}")
    return to_write


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", help="County config name or path")
    args = parser.parse_args()

    if args.config:
        from pipeline_config import load_config
        run(load_config(args.config))
    else:
        run()
