import pandas as pd
from pathlib import Path

from parse_permits_features import compute_features, get_feature_names


def _load_permit_source(source):
    """Load a single PermitSource and normalize column names.

    Returns a DataFrame with standardized columns: strap, permit_category,
    description, and the original date column renamed to issue_dt.
    """
    df = pd.read_csv(source.csv)

    rename_map = {}
    if source.strap_column != "strap":
        rename_map[source.strap_column] = "strap"
    if source.category_column != "permit_category":
        rename_map[source.category_column] = "permit_category"
    if source.description_column != "description":
        rename_map[source.description_column] = "description"
    if source.date_column != "issue_dt":
        rename_map[source.date_column] = "issue_dt"
    if rename_map:
        df = df.rename(columns=rename_map)

    # Keep only the columns we need (source may have extras)
    keep = [c for c in ["strap", "permit_category", "description", "issue_dt"] if c in df.columns]
    df = df[keep].copy()

    # Clean strap: drop nulls, convert float->int->str for consistent matching
    df = df.dropna(subset=["strap"])
    df["strap"] = df["strap"].apply(
        lambda x: str(int(float(x))) if not isinstance(x, str) else x.strip()
    )
    df = df[df["strap"] != "0"]

    df["_source"] = source.label
    return df


def run(config=None):
    """Parse permit records into binary feature columns.

    Loads all permit sources from config, normalizes columns, concatenates,
    then extracts binary features per strap.

    Args:
        config: CountyConfig object. If None, uses legacy hardcoded paths.
    """
    if config:
        output_path = str(config.parsed_permits_path)
        config.ensure_dirs()

        if config.permit_sources:
            frames = []
            for src in config.permit_sources:
                src_df = _load_permit_source(src)
                print(f"  Loaded {len(src_df):,} permits from '{src.label}' ({src.csv})")
                frames.append(src_df)
            df = pd.concat(frames, ignore_index=True)
            print(f"  Total permits after combining: {len(df):,}")
        else:
            raise ValueError("No permit sources configured")
    else:
        input_path = "/Users/jeffs/Projects/SolarProject/data/raw/Permits.csv"
        output_path = "/Users/jeffs/Projects/SolarProject/data/final/parsed_permits.csv"
        df = pd.read_csv(input_path)

    required_cols = {"strap", "permit_category", "description"}
    missing = required_cols - set(df.columns)
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    flags_df = compute_features(df)

    # Preserve issue_dt for downstream year-based aggregation
    feature_cols = get_feature_names()
    if "issue_dt" in df.columns:
        flags_df["issue_dt"] = df["issue_dt"].values
        output_cols = ["strap", "issue_dt"] + feature_cols
    else:
        output_cols = ["strap"] + feature_cols

    production = flags_df[output_cols].sort_values("strap")

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    production.to_csv(output_path, index=False)

    n_straps = production["strap"].nunique()
    print(f"Saved parsed permits to: {output_path}")
    print(f"Total permits: {len(production):,} across {n_straps:,} properties")
    print(f"Columns: strap + issue_dt + {len(feature_cols)} binary features")
    return production


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
