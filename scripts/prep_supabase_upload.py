"""Prepare full Boulder CO dataset for Supabase homes table upload."""

import sys
sys.path.insert(0, "/Users/jeffs/Projects/SolarProject/src")

import pandas as pd
import numpy as np
import json
from FinalFilters import parse_owner, format_subdivision

REGRID_PATH = "/Users/jeffs/Projects/SolarProject/data/final/regrid_filtered.csv"
API_JOINED_PATH = "/Users/jeffs/Projects/SolarProject/data/working/Boulder_CO_Regrid_joined_with_API.csv"
OUTPUT_PATH = "/Users/jeffs/Projects/SolarProject/data/final/boulder_co_supabase_upload.json"


def main():
    # Load base dataset (all qualified properties)
    df = pd.read_csv(REGRID_PATH)
    print(f"Loaded regrid_filtered: {len(df)} rows")

    # Load API data for roof_orientation and solar_score (join on strap)
    api_cols = ["strap", "roof_orientation", "solar_score", "latitude", "longitude"]
    api = pd.read_csv(API_JOINED_PATH, usecols=api_cols)
    print(f"Loaded API joined: {len(api)} rows")

    # Merge API data on strap
    df = df.merge(api, on="strap", how="left", suffixes=("", "_api"))

    # Use API lat/lon where available, else regrid lat/lon
    df["latitude"] = df["latitude"].fillna(df["lat"])
    df["longitude"] = df["longitude"].fillna(df["lon"])

    # Normalize solar_score to 0-100
    if "solar_score" in df.columns:
        score_max = df["solar_score"].max()
        if score_max > 0:
            df["solar_score"] = (df["solar_score"] / score_max) * 100

    # Uppercase city/county
    for col in ["city", "county"]:
        if col in df.columns:
            df[col] = df[col].astype(str).str.upper()

    # Extract numeric part from original_index (e.g. "Boulder_75056" -> "75056")
    df["original_index_num"] = df["original_index"].astype(str).str.extract(r"(\d+)$")[0]

    # Build index in BOULDER_CO_{num} format
    df["index"] = (
        df["county"].astype(str) + "_" + df["state2"].astype(str) + "_" + df["original_index_num"]
    )

    # Parse owner names
    parsed = df["owner"].apply(lambda x: pd.Series(parse_owner(x)))
    df["owner_1"] = parsed[0]
    df["owner_2"] = parsed[1]

    # Format subdivision
    df["subdivision_formatted"] = df["subdivision"].apply(format_subdivision)

    # Select and rename columns
    output = pd.DataFrame({
        "index": df["index"],
        "qualified_orientations": df.get("roof_orientation"),
        "saleprice": df["saleprice"],
        "saledate": df["saledate"],
        "owner_unaltered": df["owner"],
        "owner_1": df["owner_1"],
        "owner_2": df["owner_2"],
        "address": df["mailadd"],
        "city": df["city"],
        "county": df["county"],
        "state": df["state2"],
        "zip_code": df["szip5"].astype(str).str.replace(r"\.0$", "", regex=True),
        "subdivision_formatted": df["subdivision_formatted"],
        "building_sqft": df["area_building"],
        "roof_type": df.get("roof_coverdscr"),
        "calculated_build_year": df["calculated_build_year"],
        "calculated_roof_age": df["calculated_roof_age"],
        "latitude": df["latitude"],
        "longitude": df["longitude"],
        "count_stories": df["numstories"],
        "count_rooms": df["numrooms"],
        "count_bath": df["num_bath"],
        "count_bath_partial": df["num_bath_partial"],
        "count_bedrooms": df["num_bedrooms"],
        "original_index": df["original_index_num"],
    })

    # Convert numeric fields to proper types, replacing NaN with None for JSON
    numeric_as_str = ["saleprice", "building_sqft", "calculated_build_year",
                      "calculated_roof_age", "count_stories", "count_rooms",
                      "count_bath", "count_bath_partial", "count_bedrooms"]
    for col in numeric_as_str:
        output[col] = output[col].apply(
            lambda x: str(int(x)) if pd.notna(x) and x == x else
                       (str(x) if pd.notna(x) else None)
        )

    # Convert string columns: replace NaN/nan with None
    for col in output.columns:
        output[col] = output[col].where(output[col].notna(), None)
        # Also catch string "nan"
        output[col] = output[col].apply(lambda x: None if x == "nan" or x == "NAN" else x)

    # Convert original_index to string
    output["original_index"] = output["original_index"].apply(
        lambda x: str(int(x)) if x is not None else None
    )

    records = output.to_dict(orient="records")
    with open(OUTPUT_PATH, "w") as f:
        json.dump(records, f, indent=2)

    print(f"\nOutput: {len(records)} rows")
    print(f"Saved to {OUTPUT_PATH}")

    # Quick validation
    sample = records[0]
    print(f"\nSample record:")
    print(json.dumps(sample, indent=2))

    # Stats
    has_orientation = sum(1 for r in records if r["qualified_orientations"] is not None)
    has_roof_age = sum(1 for r in records if r["calculated_roof_age"] is not None)
    print(f"\nWith roof orientation: {has_orientation}/{len(records)}")
    print(f"With calculated_roof_age: {has_roof_age}/{len(records)}")


if __name__ == "__main__":
    main()
