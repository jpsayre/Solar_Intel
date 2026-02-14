"""
Download satellite map images from Google Maps Static API for each record in a CSV.

New feature:
- Downloads TWO versions per row:
  1) A bbox-centered image with the house bounding box drawn (from column 'houseBox')
  2) A lat/lon-centered image with a red marker labeled " " (space), using columns
     'latitude' & 'longitude' (NOT input_lat/input_lon)

Filename change:
- Images are now saved as:
    original_index_bbox.png
    original_index_marker.png

Other features:
- Per-row bounding box support (SW/NE) to improve centering
- Optional bbox buffer (meters)
- Optional rectangle overlay via Static Maps `path=`
- Uses scale=2 for higher effective resolution

Requires:
  GOOGLE_MAPS_API_KEY environment variable

Install:
  pip install requests pandas
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

CSV_PATH = "data/working/Boulder_CO_Python_SunroofAPI_Output_test_box.csv"

# Outputs (two files per row)
OUTPUT_DIR_BBOX = "data/images/test/bbox"
OUTPUT_DIR_MARKER = "data/images/test/marker"

# Also check these for already-processed images to avoid re-downloading
NO_SOLAR_DIR = "data/images/no_solar"
YES_SOLAR_DIR = "data/images/yes_solar"

MAX_API_CALLS = None  # int to limit calls for testing; None = no limit

# Expected CSV columns
LAT_COLUMN = "latitude"       # explicitly use these
LON_COLUMN = "longitude"      # explicitly use these
ID_COLUMN = "original_index"

# --- Bounding box settings ---
# Column containing JSON like:
# {"sw": {"lat": .., "lon": ..}, "ne": {"lat": .., "lon": ..}}
HOUSEBOX_COLUMN = "houseBox"

# Buffer to expand bbox (meters). ~6m ≈ 20ft
BBOX_BUFFER_M = 5.0

# Draw rectangle overlay on bbox image
DRAW_BBOX_RECTANGLE = True
POLY_STROKE_COLOR = "0xff0000ff"
POLY_STROKE_WEIGHT = 3
POLY_FILL_COLOR = None

# Marker settings (marker image)
MARKER_COLOR = "red"
MARKER_LABEL = " "  # URL-encoded space

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


def bbox_from_housebox(row: pd.Series) -> Optional[Tuple[Tuple[float, float], Tuple[float, float]]]:
    obj = safe_json_loads(row.get(HOUSEBOX_COLUMN))
    if obj and "sw" in obj and "ne" in obj:
        sw = obj["sw"]
        ne = obj["ne"]
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


def build_marker_param(lat: float, lon: float, color: str, label: str) -> str:
    encoded_label = urllib.parse.quote(label, safe="")
    return f"color:{color}|label:{encoded_label}|{lat},{lon}"


def build_image_url(
    center: str,
    api_key: str,
    path_param: Optional[str] = None,
    marker_param: Optional[str] = None,
) -> str:
    params = {
        "center": center,
        "zoom": ZOOM,
        "size": SIZE,
        "scale": SCALE,
        "maptype": MAPTYPE,
        "key": api_key,
    }

    qs = urllib.parse.urlencode(params)
    url = f"{BASE_URL}?{qs}"

    if path_param:
        url += f"&path={urllib.parse.quote(path_param, safe='|:,')}"
    if marker_param:
        url += f"&markers={urllib.parse.quote(marker_param, safe='|:,')}"
    return url


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
                if f.is_file() and f.suffix.lower() == ".png":
                    names.add(f.name.lower())
    return names


# --------------------
# Main
# --------------------

def main() -> None:
    root = Path(__file__).resolve().parent.parent
    csv_path = root / CSV_PATH

    out_bbox_dir = root / OUTPUT_DIR_BBOX
    out_marker_dir = root / OUTPUT_DIR_MARKER
    no_solar_dir = root / NO_SOLAR_DIR
    yes_solar_dir = root / YES_SOLAR_DIR

    out_bbox_dir.mkdir(parents=True, exist_ok=True)
    out_marker_dir.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(csv_path)
    df = df[df["ok"] == True]
    api_key = get_api_key()

    existing = existing_image_names(out_bbox_dir, out_marker_dir, no_solar_dir, yes_solar_dir)
    session = requests.Session()

    processed = 0
    saved_bbox = 0
    saved_marker = 0
    bbox_used = 0

    for _, row in df.iterrows():
        if MAX_API_CALLS is not None and (saved_bbox + saved_marker) >= MAX_API_CALLS * 2:
            break

        processed += 1
        idx = int(row[ID_COLUMN])

        fname_bbox = f"{idx}_bbox.png"
        fname_marker = f"{idx}_marker.png"

        lat = float(row[LAT_COLUMN])
        lon = float(row[LON_COLUMN])

        # -------- BBOX IMAGE --------
        if fname_bbox.lower() not in existing:
            center_lat, center_lon = lat, lon
            path_param = None

            bbox = bbox_from_housebox(row)
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
            url = build_image_url(center=center, api_key=api_key, path_param=path_param)

            if download_image(url, out_bbox_dir / fname_bbox, session):
                saved_bbox += 1
                existing.add(fname_bbox.lower())
                print(f"[bbox {saved_bbox}] saved {fname_bbox}")

            time.sleep(REQUEST_DELAY_SECONDS)

        # -------- MARKER IMAGE --------
        if fname_marker.lower() not in existing:
            center = f"{lat},{lon}"
            marker_param = build_marker_param(lat, lon, MARKER_COLOR, MARKER_LABEL)
            url = build_image_url(center=center, api_key=api_key, marker_param=marker_param)

            if download_image(url, out_marker_dir / fname_marker, session):
                saved_marker += 1
                existing.add(fname_marker.lower())
                print(f"[marker {saved_marker}] saved {fname_marker}")

            time.sleep(REQUEST_DELAY_SECONDS)

    print(
        f"Done. Processed {processed} rows. "
        f"Saved {saved_bbox} bbox images and {saved_marker} marker images. "
        f"Used houseBox bbox on {bbox_used} rows."
    )


if __name__ == "__main__":
    main()
