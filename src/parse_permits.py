import pandas as pd

from parse_permits_features import compute_features, get_feature_names

# ============================================================
# USER SETTINGS — EDIT THESE TWO PATHS ONLY
# ============================================================

INPUT_CSV_PATH = "/Users/jeffs/Projects/SolarProject/data/raw/Permits.csv"
OUTPUT_CSV_PATH = "/Users/jeffs/Projects/SolarProject/data/final/parsed_permits.csv"

# ============================================================
# SCRIPT
# ============================================================

def main():

    df = pd.read_csv(INPUT_CSV_PATH)

    required_cols = {"strap", "permit_category", "description"}
    missing = required_cols - set(df.columns)
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    flags_df = compute_features(df)

    # Aggregate to strap-level (ANY match → 1)
    X = flags_df.groupby("strap", as_index=False).max()

    # Production dataset: strap + binary feature columns only
    feature_cols = get_feature_names()
    production = X[["strap"] + feature_cols].sort_values("strap")

    production.to_csv(OUTPUT_CSV_PATH, index=False)

    print(f"Saved production dataset to: {OUTPUT_CSV_PATH}")
    print(f"Total properties: {len(production):,}")
    print(f"Columns: strap + {len(feature_cols)} binary features")


if __name__ == "__main__":
    main()
