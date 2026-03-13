"""
Enrich property records with Census ACS block-group demographics.

Two-step process:
  1. Map each property's lat/lon to a Census block group FIPS code
     using the FCC Census Block API (free, no key needed).
  2. Pull ACS 5-year demographic data for all Colorado block groups
     from the Census API (free, requires API key from census.gov).

Usage:
    # Full enrichment (geocode + ACS pull + merge)
    python src/enrich_census.py

    # Just geocode lat/lon to block groups (step 1 only)
    python src/enrich_census.py --geocode-only

    # Just pull ACS data and merge (if geocoding already done)
    python src/enrich_census.py --acs-only

    # Limit to top N records for testing
    python src/enrich_census.py --top 100

    # Export strap-level census lookup for walk-forward model (~19K straps)
    python src/enrich_census.py --export-strap-lookup

Environment:
    CENSUS_API_KEY: Census API key (get free at https://api.census.gov/data/key_signup.html)
                    Set in .env or as environment variable.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pandas as pd
import requests
from dotenv import load_dotenv

load_dotenv()

# Default paths (used when no config provided)
_DATA_DIR = Path(__file__).parent.parent / "data" / "final"
_DEFAULT_PATHS = {
    "INPUT_CSV": _DATA_DIR / "Regrid_Model_Rank.csv",
    "GEOCODED_CSV": _DATA_DIR / "block_group_geocoded.csv",
    "ACS_CSV": _DATA_DIR / "acs_block_group_data.csv",
    "OUTPUT_CSV": _DATA_DIR / "Regrid_Model_Rank_Census.csv",
    "STRAP_CENSUS_LOOKUP_CSV": _DATA_DIR / "strap_census_lookup.csv",
    "PERMITS_CSV": Path(__file__).parent.parent / "data" / "working" / "data_science_input.csv",
    "REGRID_CSV": _DATA_DIR / "Regrid_Model_Rank.csv",
    "STRAP_GEOCODED_CSV": _DATA_DIR / "strap_block_group_geocoded.csv",
    "STATE_FIPS": "08",
}


def _get_paths(config=None):
    """Return a dict of resolved paths from config or defaults."""
    if config:
        return {
            "INPUT_CSV": config.regrid_model_rank_path,
            "GEOCODED_CSV": config.block_group_geocoded_path,
            "ACS_CSV": config.acs_csv_path,
            "OUTPUT_CSV": config.regrid_model_rank_census_path,
            "STRAP_CENSUS_LOOKUP_CSV": config.strap_census_lookup_path,
            "PERMITS_CSV": config.data_science_input_path,
            "REGRID_CSV": config.regrid_filtered_path,
            "STRAP_GEOCODED_CSV": config.strap_block_group_geocoded_path,
            "STATE_FIPS": config.state_fips,
        }
    return _DEFAULT_PATHS

# ACS variables to pull (avoiding race, religion, national origin)
ACS_VARIABLES = {
    # Income
    "B19013_001E": "median_household_income",
    "B19001_001E": "total_households_income",
    # Home value
    "B25077_001E": "median_home_value",
    # Education (population 25+)
    "B15003_001E": "pop_25_plus",
    "B15003_022E": "pop_bachelors",
    "B15003_023E": "pop_masters",
    "B15003_024E": "pop_professional",
    "B15003_025E": "pop_doctorate",
    # Age
    "B01002_001E": "median_age",
    # Housing tenure
    "B25003_001E": "total_occupied_units",
    "B25003_002E": "owner_occupied_units",
    # Year householder moved in
    "B25039_001E": "median_year_moved_in",
    # Vehicles available
    "B25044_001E": "total_vehicles_tenure",
    "B25044_003E": "owner_1_vehicle",
    "B25044_004E": "owner_2_vehicles",
    "B25044_005E": "owner_3_plus_vehicles",
    # Year structure built (median not available; use aggregate)
    "B25035_001E": "median_year_built",
    # Household type
    "B11001_001E": "total_households",
    "B11001_002E": "family_households",
}

FCC_BLOCK_API = "https://geo.fcc.gov/api/census/block/find"


def get_census_api_key() -> str:
    key = os.environ.get("CENSUS_API_KEY", "")
    if not key:
        print("Warning: CENSUS_API_KEY not set. Will use Census API without key (rate-limited).")
        print("Get a free key at: https://api.census.gov/data/key_signup.html")
    return key


def load_input_data(top_n: int | None = None, paths: dict | None = None) -> pd.DataFrame:
    p = paths or _DEFAULT_PATHS
    df = pd.read_csv(p["INPUT_CSV"])
    # Only keep rows with valid lat/lon
    df = df[df["lat"].notna() & df["lon"].notna()]
    if top_n:
        df = df.head(top_n)
    return df


# ---------------------------------------------------------------------------
# Step 1: Geocode lat/lon -> Census block group FIPS via FCC API
# ---------------------------------------------------------------------------

def fcc_lookup_block_group(lat: float, lon: float) -> str | None:
    """Query FCC API to get the Census block FIPS code for a lat/lon.
    Returns the 12-digit block group FIPS (state+county+tract+block_group)."""
    try:
        resp = requests.get(FCC_BLOCK_API, params={
            "latitude": lat,
            "longitude": lon,
            "censusYear": "2020",
            "format": "json",
        }, timeout=10)

        if resp.status_code == 200:
            data = resp.json()
            block_fips = data.get("Block", {}).get("FIPS")
            if block_fips and len(block_fips) >= 12:
                # Block group is first 12 digits of the 15-digit block FIPS
                return block_fips[:12]
        return None
    except requests.RequestException:
        return None


def geocode_properties(df: pd.DataFrame, paths: dict | None = None) -> pd.DataFrame:
    """Add block_group_fips column to the dataframe using FCC API."""
    p = paths or _DEFAULT_PATHS
    geocoded_csv = Path(p["GEOCODED_CSV"])
    # Load any existing geocoded results to resume
    if geocoded_csv.exists():
        existing = pd.read_csv(geocoded_csv, dtype={"block_group_fips": str})
        existing_indices = set(existing["original_index"].tolist())
        print(f"Found {len(existing)} existing geocoded records")
    else:
        existing = pd.DataFrame()
        existing_indices = set()

    to_geocode = df[~df["original_index"].isin(existing_indices)]
    total = len(to_geocode)

    if total == 0:
        print("All records already geocoded")
        return existing

    MAX_WORKERS = 20
    print(f"Geocoding {total} properties via FCC API ({MAX_WORKERS} threads)...")
    new_rows = []
    errors = 0
    rows_list = list(to_geocode.itertuples(index=False))

    def _geocode_one(row):
        fips = fcc_lookup_block_group(row.lat, row.lon)
        return {"original_index": row.original_index, "block_group_fips": fips or ""}

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(_geocode_one, row): row for row in rows_list}
        for i, future in enumerate(as_completed(futures)):
            result = future.result()
            new_rows.append(result)
            if not result["block_group_fips"]:
                errors += 1
                if errors <= 5:
                    row = futures[future]
                    print(f"  Warning: no FIPS for index {row.original_index} "
                          f"({row.lat}, {row.lon})")
            if (i + 1) % 500 == 0:
                print(f"  Progress: {i + 1}/{total} ({errors} errors)")

    new_df = pd.DataFrame(new_rows)

    if not existing.empty:
        combined = pd.concat([existing, new_df], ignore_index=True)
    else:
        combined = new_df

    combined.to_csv(geocoded_csv, index=False)
    print(f"Geocoded {total} properties ({errors} errors). Saved to {geocoded_csv}")
    return combined


# ---------------------------------------------------------------------------
# Step 2: Pull ACS data for all Colorado block groups
# ---------------------------------------------------------------------------

def pull_acs_data(api_key: str, paths: dict | None = None) -> pd.DataFrame:
    """Pull ACS 5-year data for all block groups in the configured state."""
    p = paths or _DEFAULT_PATHS
    acs_csv = Path(p["ACS_CSV"])
    state_fips = p["STATE_FIPS"]
    if acs_csv.exists():
        print(f"Loading cached ACS data from {acs_csv}")
        return pd.read_csv(acs_csv, dtype={"block_group_fips": str})

    variables = list(ACS_VARIABLES.keys())
    var_str = ",".join(variables)

    # Query all block groups in Colorado (state FIPS 08)
    # Format: get=VARS&for=block group:*&in=state:08
    url = "https://api.census.gov/data/2023/acs/acs5"
    params = {
        "get": f"NAME,{var_str}",
        "for": "block group:*",
        "in": f"state:{state_fips} county:*",
    }
    if api_key:
        params["key"] = api_key

    print(f"Pulling ACS 5-year data for all block groups in state FIPS {state_fips}...")
    resp = requests.get(url, params=params, timeout=60)

    if resp.status_code != 200:
        # Fall back to 2022 if 2023 not available yet
        print(f"  2023 data returned {resp.status_code}, trying 2022...")
        url = "https://api.census.gov/data/2022/acs/acs5"
        resp = requests.get(url, params=params, timeout=60)

    if resp.status_code != 200:
        print(f"Error: Census API returned {resp.status_code}")
        print(resp.text[:500])
        sys.exit(1)

    try:
        data = resp.json()
    except requests.exceptions.JSONDecodeError:
        print(f"Error: Census API returned invalid JSON")
        print(resp.text[:500])
        sys.exit(1)
    header = data[0]
    rows = data[1:]

    acs_df = pd.DataFrame(rows, columns=header)

    # Build the 12-digit block group FIPS code
    acs_df["block_group_fips"] = (
        acs_df["state"] + acs_df["county"] + acs_df["tract"] + acs_df["block group"]
    )

    # Rename ACS variable codes to readable names
    acs_df = acs_df.rename(columns=ACS_VARIABLES)

    # Convert numeric columns and replace Census "no data" sentinel values
    for col in ACS_VARIABLES.values():
        acs_df[col] = pd.to_numeric(acs_df[col], errors="coerce")
    # Census uses negative values like -666666666 to indicate missing data
    acs_df[list(ACS_VARIABLES.values())] = acs_df[list(ACS_VARIABLES.values())].where(
        acs_df[list(ACS_VARIABLES.values())] >= 0
    )

    # Compute derived features
    acs_df["pct_college_educated"] = (
        (acs_df["pop_bachelors"] + acs_df["pop_masters"] +
         acs_df["pop_professional"] + acs_df["pop_doctorate"])
        / acs_df["pop_25_plus"].replace(0, float("nan"))
        * 100
    ).round(1)

    acs_df["pct_owner_occupied"] = (
        acs_df["owner_occupied_units"]
        / acs_df["total_occupied_units"].replace(0, float("nan"))
        * 100
    ).round(1)

    acs_df["pct_family_households"] = (
        acs_df["family_households"]
        / acs_df["total_households"].replace(0, float("nan"))
        * 100
    ).round(1)

    total_owner_vehicles = (
        acs_df["owner_1_vehicle"] + acs_df["owner_2_vehicles"] +
        acs_df["owner_3_plus_vehicles"]
    )
    acs_df["pct_multi_vehicle"] = (
        (acs_df["owner_2_vehicles"] + acs_df["owner_3_plus_vehicles"])
        / total_owner_vehicles.replace(0, float("nan"))
        * 100
    ).round(1)

    # Keep only useful columns
    keep_cols = [
        "block_group_fips",
        "median_household_income",
        "median_home_value",
        "median_age",
        "median_year_moved_in",
        "median_year_built",
        "pct_college_educated",
        "pct_owner_occupied",
        "pct_family_households",
        "pct_multi_vehicle",
    ]
    acs_df = acs_df[keep_cols]

    acs_csv.parent.mkdir(parents=True, exist_ok=True)
    acs_df.to_csv(acs_csv, index=False)
    print(f"Saved ACS data for {len(acs_df)} block groups to {acs_csv}")
    return acs_df


# ---------------------------------------------------------------------------
# Step 3: Merge everything
# ---------------------------------------------------------------------------

def merge_and_save(input_df: pd.DataFrame, geocoded: pd.DataFrame,
                   acs: pd.DataFrame, paths: dict | None = None) -> pd.DataFrame:
    """Merge geocoded FIPS + ACS data back onto the property records."""
    p = paths or _DEFAULT_PATHS
    output_csv = Path(p["OUTPUT_CSV"])
    # Merge geocoded block group FIPS onto properties
    merged = input_df.merge(
        geocoded[["original_index", "block_group_fips"]],
        on="original_index",
        how="left",
    )

    # Merge ACS data by block group FIPS
    merged = merged.merge(acs, on="block_group_fips", how="left")

    output_csv.parent.mkdir(parents=True, exist_ok=True)
    merged.to_csv(output_csv, index=False)

    matched = merged["median_household_income"].notna().sum()
    total = len(merged)
    print(f"\nMerged {matched}/{total} records with Census demographics")
    print(f"Output saved to {output_csv}")

    # Summary stats
    print("\n--- Census Feature Summary ---")
    census_cols = [c for c in acs.columns if c != "block_group_fips"]
    for col in census_cols:
        if col in merged.columns:
            valid = merged[col].notna().sum()
            print(f"  {col:30s}  median={merged[col].median():>10.1f}  "
                  f"non-null={valid}")

    return merged


def export_strap_lookup(top_n: int | None = None, paths: dict | None = None, config=None):
    """Export a strap-level census lookup CSV for the walk-forward model.

    Joins unique straps from data_science_input.csv to Regrid (for lat/lon),
    geocodes via FCC API, merges ACS data, and writes strap_census_lookup.csv.
    """
    p = paths or _DEFAULT_PATHS
    strap_geocoded_csv = Path(p["STRAP_GEOCODED_CSV"])
    strap_census_lookup_csv = Path(p["STRAP_CENSUS_LOOKUP_CSV"])
    strap_col = config.strap_column if config else "alt_parcelnumb1"

    # Load unique straps from Regrid filtered (authoritative strap list with lat/lon)
    regrid = pd.read_csv(p["REGRID_CSV"])
    regrid["strap"] = regrid[strap_col].astype(str)
    regrid = regrid.drop_duplicates(subset=["strap"], keep="first")
    strap_df = regrid[["strap", "lat", "lon"]].copy()
    strap_df = strap_df[strap_df["lat"].notna() & strap_df["lon"].notna()]
    if top_n:
        strap_df = strap_df.head(top_n)
    print(f"Found {len(strap_df)} unique straps with lat/lon from {Path(p['REGRID_CSV']).name}")

    # Geocode to block group FIPS via FCC API (with resume support)
    if strap_geocoded_csv.exists():
        existing = pd.read_csv(strap_geocoded_csv, dtype={"block_group_fips": str})
        existing_straps = set(existing["strap"].tolist())
        print(f"Found {len(existing)} existing geocoded straps")
    else:
        existing = pd.DataFrame()
        existing_straps = set()

    to_geocode = strap_df[~strap_df["strap"].isin(existing_straps)]
    total = len(to_geocode)
    MAX_WORKERS = 20

    if total > 0:
        print(f"Geocoding {total} straps via FCC API ({MAX_WORKERS} threads)...")
        new_rows = []
        errors = 0
        rows_list = list(to_geocode.itertuples(index=False))

        def _geocode_one(row):
            fips = fcc_lookup_block_group(row.lat, row.lon)
            return {"strap": row.strap, "block_group_fips": fips or ""}

        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = {executor.submit(_geocode_one, row): row for row in rows_list}
            for i, future in enumerate(as_completed(futures)):
                result = future.result()
                new_rows.append(result)
                if not result["block_group_fips"]:
                    errors += 1
                    if errors <= 5:
                        row = futures[future]
                        print(f"  Warning: no FIPS for strap {row.strap} "
                              f"({row.lat}, {row.lon})")
                if (i + 1) % 500 == 0:
                    print(f"  Progress: {i + 1}/{total} ({errors} errors)")
                    # Checkpoint
                    checkpoint = pd.DataFrame(new_rows)
                    if not existing.empty:
                        checkpoint = pd.concat([existing, checkpoint], ignore_index=True)
                    checkpoint.to_csv(strap_geocoded_csv, index=False)

        new_df = pd.DataFrame(new_rows)
        geocoded = pd.concat([existing, new_df], ignore_index=True) if not existing.empty else new_df
        geocoded.to_csv(strap_geocoded_csv, index=False)
        print(f"Geocoded {total} straps ({errors} errors). Saved to {strap_geocoded_csv}")
    else:
        geocoded = existing
        print("All straps already geocoded")

    # Pull ACS data and merge
    api_key = get_census_api_key()
    acs = pull_acs_data(api_key, paths=p)

    lookup = geocoded.merge(acs, on="block_group_fips", how="left")
    # Drop the block_group_fips column (not needed downstream)
    lookup = lookup.drop(columns=["block_group_fips"])

    strap_census_lookup_csv.parent.mkdir(parents=True, exist_ok=True)
    lookup.to_csv(strap_census_lookup_csv, index=False)
    matched = lookup["median_household_income"].notna().sum()
    print(f"\nWrote {len(lookup)} rows to {strap_census_lookup_csv} "
          f"({matched} with census data)")
    return lookup


def main():
    parser = argparse.ArgumentParser(
        description="Enrich property records with Census ACS demographics"
    )
    parser.add_argument("--config", help="County config name or path")
    parser.add_argument("--top", type=int, help="Limit to first N records")
    parser.add_argument("--geocode-only", action="store_true",
                        help="Only run the FCC geocoding step")
    parser.add_argument("--acs-only", action="store_true",
                        help="Only pull ACS data and merge (skip geocoding)")
    parser.add_argument("--export-strap-lookup", action="store_true",
                        help="Export strap-level census lookup for walk-forward model")
    args = parser.parse_args()

    config = None
    if args.config:
        from pipeline_config import load_config
        config = load_config(args.config)
        config.ensure_dirs()

    paths = _get_paths(config)

    if args.export_strap_lookup:
        export_strap_lookup(top_n=args.top, paths=paths, config=config)
        return

    df = load_input_data(top_n=args.top, paths=paths)
    print(f"Loaded {len(df)} property records with lat/lon")

    geocoded_csv = Path(paths["GEOCODED_CSV"])

    if not args.acs_only:
        geocoded = geocode_properties(df, paths=paths)
    else:
        if not geocoded_csv.exists():
            print("Error: no geocoded data found. Run without --acs-only first.")
            sys.exit(1)
        geocoded = pd.read_csv(geocoded_csv, dtype={"block_group_fips": str})

    if args.geocode_only:
        print("Geocoding complete. Run again with --acs-only to pull ACS data.")
        return

    api_key = get_census_api_key()
    acs = pull_acs_data(api_key, paths=paths)
    merge_and_save(df, geocoded, acs, paths=paths)


def run(config):
    """Run the full strap-level census enrichment for the pipeline."""
    config.ensure_dirs()
    paths = _get_paths(config)
    export_strap_lookup(paths=paths, config=config)


if __name__ == "__main__":
    main()
