"""
Parse raw permit CSVs into classified permit records.

Reads raw permit files from any county/city (via config permit_sources),
normalizes columns, classifies each permit using category + description + valuation,
and outputs a single row-level file with 19 binary features and a permit_type label.

Usage:
    python src/parse_permits.py --config boulder_co

Output: parsed_permits.csv (one row per permit)
    strap, permit_num, issue_dt, permit_category, description, estimated_value,
    _source, [19 binary features], permit_type
"""

import pandas as pd
from pathlib import Path

from parse_permits_features import compute_features, classify_permit_type, get_feature_names


def _load_permit_source(source):
    """Load a single PermitSource and normalize column names.

    Returns a DataFrame with standardized columns: strap, permit_num, issue_dt,
    permit_category, description, estimated_value, _source.
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
    if source.permit_num_column != "permit_num":
        rename_map[source.permit_num_column] = "permit_num"
    if source.valuation_column != "estimated_value":
        rename_map[source.valuation_column] = "estimated_value"
    if rename_map:
        df = df.rename(columns=rename_map)

    # Keep all columns we need for output
    keep = [c for c in ["strap", "permit_num", "issue_dt", "permit_category",
                         "description", "estimated_value"] if c in df.columns]
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
    """Parse permit records into classified rows with binary features and permit_type.

    Loads all permit sources from config, normalizes columns, concatenates,
    then classifies each permit row.

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

    # Classify: compute 19 binary features (with valuation sanity checks)
    valuation = df["estimated_value"] if "estimated_value" in df.columns else None
    flags_df = compute_features(df, estimated_value=valuation)

    # Add permit_type from binary flags
    feature_names = get_feature_names()
    permit_types = flags_df[feature_names].apply(
        lambda row: classify_permit_type(row.to_dict()), axis=1
    )

    # Build output: original columns + binary features + permit_type
    output = df.copy()
    for feat in feature_names:
        output[feat] = flags_df[feat].values
    output["permit_type"] = permit_types.values

    # Clean dates: parse, clamp to valid range, null out junk
    if "issue_dt" in output.columns:
        output["issue_dt"] = pd.to_datetime(output["issue_dt"], format="mixed", errors="coerce")
        # 1899-12-30 is Excel's epoch for zero/null — treat as missing
        excel_epoch = output["issue_dt"] == pd.Timestamp("1899-12-30")
        # Future dates beyond current year are likely typos (e.g. 2098 → 1998)
        too_far_future = output["issue_dt"].dt.year > pd.Timestamp.now().year
        n_bad = (excel_epoch | too_far_future).sum()
        if n_bad:
            print(f"  Nulled {n_bad:,} bad dates (Excel epoch or future year)")
        output.loc[excel_epoch | too_far_future, "issue_dt"] = pd.NaT
        # Format as YYYY-MM-DD string for CSV output
        output["issue_dt"] = output["issue_dt"].dt.strftime("%Y-%m-%d")

    output = output.sort_values("strap")

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    output.to_csv(output_path, index=False)

    n_straps = output["strap"].nunique()
    print(f"Saved parsed permits to: {output_path}")
    print(f"Total permits: {len(output):,} across {n_straps:,} properties")
    print(f"Columns: {list(output.columns)}")

    # permit_type distribution
    type_counts = output["permit_type"].value_counts()
    print(f"\npermit_type distribution:")
    for ptype, count in type_counts.items():
        print(f"  {ptype}: {count:,}")

    return output


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
