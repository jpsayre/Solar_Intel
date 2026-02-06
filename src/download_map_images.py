"""
Download satellite map images from Google Maps Static API for each latitude/longitude
in a CSV file. Images are saved to data/images.

Requires: GOOGLE_MAPS_API_KEY environment variable.
"""

import os
import time
import requests
import pandas as pd
from pathlib import Path

location = 'BOULDER_CO'
location = location.upper()

# --- Configuration ---
CSV_PATH = "data/working/"+location+"_Lat_Long_For_Solar_Classification.csv"  # Path to CSV with latitude/longitude columns
OUTPUT_DIR = "data/images/unprocessed"
NO_SOLAR_DIR = "data/images/no_solar"
YES_SOLAR_DIR = "data/images/yes_solar"
MAX_API_CALLS = None  # Set to an integer (e.g. 5) to limit calls for testing; None = no limit

# Expected CSV column names (adjust if your CSV uses different names)
LAT_COLUMN = "lat"
LON_COLUMN = "lon"
ID_COLUMN = "original_index"

# API settings
BASE_URL = "https://maps.googleapis.com/maps/api/staticmap"
ZOOM = 20
SIZE = "400x400"
MAPTYPE = "satellite"
REQUEST_DELAY_SECONDS = 0.1  # Small delay between requests to avoid rate limits


def get_api_key() -> str:
    key = os.getenv("GOOGLE_MAPS_API_KEY")
    if not key:
        raise SystemExit(
            "GOOGLE_MAPS_API_KEY environment variable is not set. "
            "Set it before running this script."
        )
    return key


def build_image_url(lat: float, lon: float, api_key: str) -> str:
    center = f"{lat},{lon}"
    params = {
        "center": center,
        "zoom": ZOOM,
        "size": SIZE,
        "maptype": MAPTYPE,
        "key": api_key,
    }
    # Build URL with query string
    qs = "&".join(f"{k}={v}" for k, v in params.items())
    return f"{BASE_URL}?{qs}"


def download_image(url: str, filepath: Path, session: requests.Session) -> bool:
    try:
        resp = session.get(url, timeout=30)
        resp.raise_for_status()
        filepath.write_bytes(resp.content)
        return True
    except requests.RequestException as e:
        print(f"  Failed to download: {e}")
        return False


def existing_image_names(unprocessed_dir: Path, no_solar_dir: Path, yes_solar_dir: Path) -> set[str]:
    """Collect image filenames from unprocessed, no_solar, and yes_solar (case-insensitive set)."""
    existing = set()
    for folder in (unprocessed_dir, no_solar_dir, yes_solar_dir):
        if folder.exists():
            for f in folder.iterdir():
                if f.suffix.lower() == ".png":
                    existing.add(f.name.lower())
    return existing


def main() -> None:
    project_root = Path(__file__).resolve().parent.parent
    csv_path = project_root / CSV_PATH
    output_dir = project_root / OUTPUT_DIR
    no_solar_dir = project_root / NO_SOLAR_DIR
    yes_solar_dir = project_root / YES_SOLAR_DIR

    if not csv_path.exists():
        raise SystemExit(f"CSV file not found: {csv_path}")

    output_dir.mkdir(parents=True, exist_ok=True)

    api_key = get_api_key()
    df = pd.read_csv(csv_path)

    for col in (LAT_COLUMN, LON_COLUMN, ID_COLUMN):
        if col not in df.columns:
            raise SystemExit(
                f"CSV must contain columns '{LAT_COLUMN}', '{LON_COLUMN}', and '{ID_COLUMN}'. "
                f"Found: {list(df.columns)}"
            )

    already_present = existing_image_names(output_dir, no_solar_dir, yes_solar_dir)
    print(f"Found {len(already_present)} images already in unprocessed/no_solar/yes_solar.")

    limit = MAX_API_CALLS
    total = len(df) if limit is None else min(len(df), limit)
    print(f"Processing up to {total} locations (limit={MAX_API_CALLS})...")

    session = requests.Session()
    success_count = 0
    skipped_present = 0
    processed = 0

    for i, row in df.iterrows():
        if limit is not None and success_count >= limit:
            print(f"Reached limit of {limit} API calls. Stopping.")
            break

        processed += 1
        lat = row[LAT_COLUMN]
        lon = row[LON_COLUMN]
        id = int(row[ID_COLUMN])
        filename = f"{location}_{id}.png"
        if filename.lower() in already_present:
            skipped_present += 1
            print(f"[{processed}/{total}] {filename}... already in unprocessed/no_solar/yes_solar, skip")
            continue

        url = build_image_url(lat, lon, api_key)
        filepath = output_dir / filename

        print(f"[{processed}/{total}] {filename}...", end=" ")
        if download_image(url, filepath, session):
            success_count += 1
            print("OK")
        else:
            print("SKIP")

        time.sleep(REQUEST_DELAY_SECONDS)

    print(f"Done. Skipped {skipped_present} (already present). Saved {success_count} images to {output_dir}")


if __name__ == "__main__":
    main()
