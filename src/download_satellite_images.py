"""
Download clean satellite images from Google Maps Static API for each home.

One image per home, centered by address geocoding (more accurate than lat/lon).
No markers, no bounding box overlays — just satellite imagery.

Skips homes that already have an image on disk.

Requires:
  GOOGLE_MAPS_API_KEY environment variable

Usage:
  python src/download_satellite_images.py --config boulder_co
"""

from __future__ import annotations

import argparse
import os
import time
import urllib.parse
import requests
import pandas as pd
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

# Google Static Maps settings
BASE_URL = "https://maps.googleapis.com/maps/api/staticmap"
ZOOM = 20
SIZE = "640x640"
SCALE = 2
MAPTYPE = "satellite"
REQUEST_DELAY_SECONDS = 0.1


def get_api_key() -> str:
    key = os.getenv("GOOGLE_MAPS_API_KEY")
    if not key:
        raise SystemExit("GOOGLE_MAPS_API_KEY environment variable is not set")
    return key


def build_image_url_address(address: str, api_key: str) -> str:
    """Build Static Maps URL using address string for centering."""
    params = {
        "center": address,
        "zoom": ZOOM,
        "size": SIZE,
        "scale": SCALE,
        "maptype": MAPTYPE,
        "key": api_key,
    }
    return f"{BASE_URL}?{urllib.parse.urlencode(params)}"


def build_image_url_latlon(lat: float, lon: float, api_key: str) -> str:
    """Fallback: build Static Maps URL using lat/lon."""
    params = {
        "center": f"{lat},{lon}",
        "zoom": ZOOM,
        "size": SIZE,
        "scale": SCALE,
        "maptype": MAPTYPE,
        "key": api_key,
    }
    return f"{BASE_URL}?{urllib.parse.urlencode(params)}"


def download_image(url: str, filepath: Path, session: requests.Session) -> bool:
    try:
        r = session.get(url, timeout=30)
        r.raise_for_status()
        filepath.write_bytes(r.content)
        return True
    except requests.RequestException as e:
        print(f"  Failed: {e}")
        return False


def existing_image_names(directory: Path) -> set[str]:
    names = set()
    if directory.exists():
        for f in directory.iterdir():
            if f.is_file() and f.suffix.lower() == ".png":
                names.add(f.name.lower())
    return names


def run(config, limit: int | None = None) -> None:
    """Download satellite images for all homes in filtered Regrid data.

    Uses address for centering (more accurate), falls back to lat/lon if
    address is missing.

    Args:
        config: CountyConfig object
        limit: Max NEW images to download (None = all)
    """
    regrid_path = config.regrid_filtered_path
    out_dir = config.image_dir
    prefix = config.index_prefix  # e.g. "BOULDER_CO_"

    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"Reading Regrid data: {regrid_path}")
    df = pd.read_csv(regrid_path, usecols=[
        "original_index", "address", "city", "state2", "szip5",
        config.lat_column, config.lon_column,
    ])
    print(f"  {len(df)} homes in filtered Regrid")

    # Build full address string
    df["full_address"] = (
        df["address"].fillna("").str.strip()
        + ", " + df["city"].fillna("").str.strip()
        + ", " + df["state2"].fillna("").str.strip()
        + " " + df["szip5"].fillna("").astype(str).str.strip()
    )
    has_address = df["address"].notna() & (df["address"].str.strip() != "")

    api_key = get_api_key()
    existing = existing_image_names(out_dir)
    session = requests.Session()

    saved = 0
    skipped = 0
    fallback_count = 0

    for _, row in df.iterrows():
        if limit is not None and saved >= limit:
            break

        idx = int(row["original_index"])
        fname = f"{prefix}{idx}.png"

        if fname.lower() in existing:
            skipped += 1
            continue

        if has_address.loc[row.name]:
            url = build_image_url_address(row["full_address"], api_key)
        else:
            url = build_image_url_latlon(float(row[config.lat_column]), float(row[config.lon_column]), api_key)
            fallback_count += 1

        if download_image(url, out_dir / fname, session):
            saved += 1
            existing.add(fname.lower())
            if saved <= 5 or saved % 25 == 0:
                method = "address" if has_address.loc[row.name] else "lat/lon"
                print(f"  [{saved}] {fname} ({method})")

        time.sleep(REQUEST_DELAY_SECONDS)

    print(
        f"Done. Saved {saved} new images, skipped {skipped} existing. "
        f"Lat/lon fallback used {fallback_count} times. Output: {out_dir}"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Download satellite images")
    parser.add_argument("--config", required=True, help="County config name")
    parser.add_argument("--limit", type=int, default=None, help="Max NEW images to download")
    args = parser.parse_args()

    from pipeline_config import load_config
    run(load_config(args.config), limit=args.limit)
