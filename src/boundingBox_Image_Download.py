"""
Download satellite map images from Google Maps Static API for each record in a CSV.

Features:
- Optional per-row bounding box support (SW/NE) to improve centering
- Optional bbox buffer (meters)
- Optional rectangle overlay via Static Maps `path=`
- Uses scale=2 for higher effective resolution

Requires:
  GOOGLE_MAPS_API_KEY environment variable

Install:
  pip install requests pandas

Notes:
- Static Maps does NOT accept a bbox to auto-crop.
  We compute the bbox center and optionally draw the rectangle.
"""

from __future__ import annotations

import os
import time
import json
import math
import urllib.parse
import requests
import pandas as pd
from pathlib import Path
from typing import Optional, Tuple, Dict, Any


# --------------------
# Configuration
# --------------------

LOCATION = "Boulder_CO"

CSV_PATH = f"data/working/test_images_dataset.csv"
OUTPUT_DIR = "data/images/test"
NO_SOLAR_DIR = "data/images/no_solar"
YES_SOLAR_DIR = "data/images/yes_solar"

MAX_API_CALLS = 20  # int to limit calls for testing; None = no limit

# Expected CSV columns
LAT_COLUMN = "latitude"
LON_COLUMN = "longitude"
ID_COLUMN = "original_index"

# --- Bounding box settings ---
# CSV column containing JSON like:
# {"sw": {"lat": .., "lon": ..}, "ne": {"lat": .., "lon": ..}}
USE_BBOX = True
BBOX_JSON_COLUMN = "houseBox"  # <-- set to your actual column name

# If bbox is split across two columns instead, set:
# BBOX_JSON_COLUMN = None
# SW_JSON_COLUMN = "sw"
# NE_JSON_COLUMN = "ne"
SW_JSON_COLUMN: Optional[str] = None
NE_JSON_COLUMN: Optional[str] = None

# Buffer to expand bbox (meters). ~6m ≈ 20ft
BBOX_BUFFER_M = 5.0

# Draw rectangle overlay
DRAW_BBOX_RECTANGLE = True
POLY_STROKE_COLOR = "0xff0000ff"
POLY_STROKE_WEIGHT = 3
POLY_FILL_COLOR = None

# Google Static Maps settings
BASE_URL = "https://maps.googleapis.com/maps/api/staticmap"
ZOOM = 20
SIZE = "640x640"
SCALE = 2
MAPTYPE = "satellite"
REQUEST_DELAY_SECONDS = 0.1


# --------------------
# Helpers
# --------------------

def get_api_key() -> str:
    key = os.getenv("GOOGLE_MAPS_API_KEY")
    if not key:
        raise SystemExit("GOOGLE_MAPS_API_KEY environment variable is not set")
    return key


def safe_json_loads(val: Any) -> Optional[Dict[str, Any]]:
    if val is None or (isinstance(val, float) and math.isnan(val)):
        return None
    if isinstance(val, dict):
        return val
    if isinstance(val, str):
        try:
            return json.loads(val)
        except json.JSONDecodeError:
            return None
    return None


def bbox_from_row(row: pd.Series) -> Optional[Tuple[Tuple[float, float], Tuple[float, float]]]:
    if BBOX_JSON_COLUMN:
        obj = safe_json_loads(row.get(BBOX_JSON_COLUMN))
        if obj and "sw" in obj and "ne" in obj:
            sw = obj["sw"]
            ne = obj["ne"]
            return (sw["lat"], sw["lon"]), (ne["lat"], ne["lon"])

    if SW_JSON_COLUMN and NE_JSON_COLUMN:
        sw = safe_json_loads(row.get(SW_JSON_COLUMN))
        ne = safe_json_loads(row.get(NE_JSON_COLUMN))
        if sw and ne:
            return (sw["lat"], sw["lon"]), (ne["lat"], ne["lon"])

    return None


def expand_sw_ne_by_meters(
    sw: Tuple[float, float],
    ne: Tuple[float, float],
    buffer_m: float,
) -> Tuple[Tuple[float, float], Tuple[float, float]]:
    mid_lat = (sw[0] + ne[0]) / 2.0
    meters_per_deg_lat = 111_320.0
    meters_per_deg_lon = 111_320.0 * math.cos(math.radians(mid_lat))

    dlat = buffer_m / meters_per_deg_lat
    dlon = buffer_m / meters_per_deg_lon

    return (
        (sw[0] - dlat, sw[1] - dlon),
        (ne[0] + dlat, ne[1] + dlon),
    )


def center_from_sw_ne(sw: Tuple[float, float], ne: Tuple[float, float]) -> Tuple[float, float]:
    return ((sw[0] + ne[0]) / 2.0, (sw[1] + ne[1]) / 2.0)


def rectangle_polygon_from_sw_ne(sw: Tuple[float, float], ne: Tuple[float, float]):
    return [
        (sw[0], sw[1]),
        (ne[0], sw[1]),
        (ne[0], ne[1]),
        (sw[0], ne[1]),
        (sw[0], sw[1]),
    ]


def build_path_param(points, stroke_color, weight, fill_color=None) -> str:
    parts = [f"weight:{weight}", f"color:{stroke_color}"]
    if fill_color:
        parts.append(f"fillcolor:{fill_color}")
    for lat, lon in points:
        parts.append(f"{lat},{lon}")
    return "|".join(parts)


def build_image_url(center: str, api_key: str, path_param: Optional[str]) -> str:
    params = {
        "center": center,
        "zoom": ZOOM,
        "size": SIZE,
        "scale": SCALE,
        "maptype": MAPTYPE,
        "key": api_key,
    }

    qs = urllib.parse.urlencode(params)

    if path_param:
        return f"{BASE_URL}?{qs}&path={urllib.parse.quote(path_param, safe='|:,')}"

    return f"{BASE_URL}?{qs}"


def download_image(url: str, filepath: Path, session: requests.Session) -> bool:
    try:
        r = session.get(url, timeout=30)
        r.raise_for_status()
        filepath.write_bytes(r.content)
        return True
    except requests.RequestException as e:
        print(f"  Failed: {e}")
        return False


def existing_image_names(*dirs: Path) -> set[str]:
    names = set()
    for d in dirs:
        if d.exists():
            for f in d.iterdir():
                if f.suffix.lower() == ".png":
                    names.add(f.name.lower())
    return names


# --------------------
# Main
# --------------------

def main() -> None:
    root = Path(__file__).resolve().parent.parent
    csv_path = root / CSV_PATH
    out_dir = root / OUTPUT_DIR
    no_solar_dir = root / NO_SOLAR_DIR
    yes_solar_dir = root / YES_SOLAR_DIR

    out_dir.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(csv_path)
    df = df[df['ok'] == True]
    api_key = get_api_key()

    existing = existing_image_names(out_dir, no_solar_dir, yes_solar_dir)
    session = requests.Session()

    processed = 0
    saved = 0
    bbox_used = 0

    for _, row in df.iterrows():
        if MAX_API_CALLS is not None and saved >= MAX_API_CALLS:
            break

        processed += 1
        idx = int(row[ID_COLUMN])
        fname = f"{LOCATION}_{idx}.png"

        if fname.lower() in existing:
            continue

        center_lat = row[LAT_COLUMN]
        center_lon = row[LON_COLUMN]
        path_param = None

        if USE_BBOX:
            bbox = bbox_from_row(row)
            if bbox:
                sw, ne = bbox
                sw, ne = expand_sw_ne_by_meters(sw, ne, BBOX_BUFFER_M)
                center_lat, center_lon = center_from_sw_ne(sw, ne)
                bbox_used += 1

                if DRAW_BBOX_RECTANGLE:
                    path_param = build_path_param(
                        rectangle_polygon_from_sw_ne(sw, ne),
                        POLY_STROKE_COLOR,
                        POLY_STROKE_WEIGHT,
                        POLY_FILL_COLOR,
                    )

        center = f"{center_lat},{center_lon}"
        url = build_image_url(center, api_key, path_param)

        if download_image(url, out_dir / fname, session):
            saved += 1
            print(f"[{saved}] saved {fname}")

        time.sleep(REQUEST_DELAY_SECONDS)

    print(f"Done. Saved {saved} images. Used bbox on {bbox_used} rows.")


if __name__ == "__main__":
    main()
