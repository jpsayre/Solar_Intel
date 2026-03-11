#!/usr/bin/env python3
"""
Temporary script: backfill solar_panels in CSV from image folders.
If a row has no solar_panels value but an image exists in data/images/no_solar
or data/images/yes_solar (BOULDER_CO_<original_index>.png), set solar_panels
to "No" or "Yes" accordingly, set image_name to the filename found, and save the CSV.
"""

import os
import re
from typing import Optional

import pandas as pd

# Paths (relative to project root)
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
CSV_PATH = os.path.join(PROJECT_ROOT, "data", "working", "Boulder_CO_Regrid_joined_with_API.csv")
NO_SOLAR_DIR = os.path.join(PROJECT_ROOT, "data", "images", "no_solar")
YES_SOLAR_DIR = os.path.join(PROJECT_ROOT, "data", "images", "yes_solar")

# Filename pattern: BOULDER_CO_<original_index>.png (case-insensitive)
IMAGE_PATTERN = re.compile(r"^BOULDER_CO_(\d+)\.(?:png|PNG)$", re.IGNORECASE)


def get_index_from_filename(name: str) -> Optional[int]:
    m = IMAGE_PATTERN.match(name)
    return int(m.group(1)) if m else None


def index_to_filename_from_folder(folder: str) -> dict[int, str]:
    """Return mapping original_index -> image filename for folder."""
    if not os.path.isdir(folder):
        return {}
    result = {}
    for name in os.listdir(folder):
        idx = get_index_from_filename(name)
        if idx is not None:
            result[idx] = name
    return result


def main():
    no_solar_names = index_to_filename_from_folder(NO_SOLAR_DIR)
    yes_solar_names = index_to_filename_from_folder(YES_SOLAR_DIR)
    print(f"no_solar images: {len(no_solar_names)}, yes_solar images: {len(yes_solar_names)}")

    df = pd.read_csv(CSV_PATH, low_memory=False)
    if "original_index" not in df.columns:
        raise SystemExit("CSV has no column 'original_index'")
    if "solar_panels" not in df.columns:
        raise SystemExit("CSV has no column 'solar_panels'")
    if "image_name" not in df.columns:
        df["image_name"] = ""

    # Rows where solar_panels is missing/empty (NaN or blank string)
    missing = df["solar_panels"].isna() | (df["solar_panels"].astype(str).str.strip() == "")
    rows_with_missing = missing.sum()
    print(f"Rows with missing solar_panels: {rows_with_missing}")

    updated_no = 0
    updated_yes = 0
    for i in df.index[missing]:
        idx = df.at[i, "original_index"]
        if pd.isna(idx):
            continue
        try:
            orig = int(idx)
        except (TypeError, ValueError):
            continue
        if orig in no_solar_names:
            df.at[i, "solar_panels"] = "No"
            df.at[i, "image_name"] = no_solar_names[orig]
            updated_no += 1
        elif orig in yes_solar_names:
            df.at[i, "solar_panels"] = "Yes"
            df.at[i, "image_name"] = yes_solar_names[orig]
            updated_yes += 1

    print(f"Updated to No: {updated_no}, Updated to Yes: {updated_yes}")
    df.to_csv(CSV_PATH, index=False)
    print(f"Saved to {CSV_PATH}")


if __name__ == "__main__":
    main()
