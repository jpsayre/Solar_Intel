"""
Test copy of parse_permits.py that outputs ROW-LEVEL (permit-level) data
with permit_category, estimated_value, description, and feature flags
so you can inspect how each permit is classified before aggregation by strap.
"""

import pandas as pd

from parse_permits_features import compute_features, get_feature_names

# ============================================================
# USER SETTINGS — EDIT THESE TWO PATHS ONLY
# ============================================================

INPUT_CSV_PATH = "/Users/jeffs/Projects/SolarProject/data/raw/Permits.csv"
OUTPUT_CSV_PATH = "/Users/jeffs/Projects/SolarProject/data/working/parsed_permits_test.csv"

# ============================================================
# SCRIPT
# ============================================================

def main():

    df = pd.read_csv(INPUT_CSV_PATH)

    required_cols = {"strap", "permit_category", "description", "permit_num", "issue_dt"}
    missing = required_cols - set(df.columns)
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    df["strap"] = df["strap"].astype(str)
    df["permit_category"] = df["permit_category"].fillna("").astype(str)
    df["description"] = df["description"].fillna("").astype(str)

    flags_df = compute_features(df)

    # Row-level output: strap, permit_num, issue_dt, then all binary feature columns
    feature_names = get_feature_names()
    out_columns = ["strap", "permit_num", "issue_dt"] + feature_names

    result = pd.DataFrame()
    result["strap"] = df["strap"].values
    result["permit_num"] = df["permit_num"].values
    result["issue_dt"] = df["issue_dt"].values

    for f in feature_names:
        result[f] = flags_df[f].values

    # Save (row-level, one row per permit)
    result[out_columns].to_csv(OUTPUT_CSV_PATH, index=False)

    print(f"Saved row-level permit data to: {OUTPUT_CSV_PATH}")
    print(f"Total permit rows: {len(result):,}")
    print(f"Columns: {out_columns}")


if __name__ == "__main__":
    main()
