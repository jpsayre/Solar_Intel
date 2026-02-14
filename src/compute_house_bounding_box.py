#!/usr/bin/env python3
"""
Read Boulder_CO_Python_SunroofAPI_Output.csv, compute for each row a single
bounding box (houseBox) that encompasses all boundingBox1..boundingBox25
(most North/East and South/West lat/lons), and write the result to a _test copy.
"""

import csv
import json
import os

# Paths relative to project root
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
INPUT_CSV = os.path.join(
    PROJECT_ROOT, "data", "working", "Boulder_CO_Python_SunroofAPI_Output_test.csv"
)
OUTPUT_CSV = os.path.join(
    PROJECT_ROOT, "data", "working", "Boulder_CO_Python_SunroofAPI_Output_test_box.csv"
)


def parse_bbox_cell(value: str) -> tuple[dict | None, dict | None]:
    """Parse a boundingBox cell (JSON). Returns (sw, ne) or (None, None) if empty/invalid."""
    if not value or not value.strip():
        return None, None
    try:
        data = json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return None, None
    sw = data.get("sw") if isinstance(data, dict) else None
    ne = data.get("ne") if isinstance(data, dict) else None
    if not isinstance(sw, dict):
        sw = None
    if not isinstance(ne, dict):
        ne = None
    return sw, ne


def extract_lat_lon(point: dict) -> tuple[float | None, float | None]:
    """Get lat/lon from a point dict; accepts 'lat'/'lon' or 'latitude'/'longitude'."""
    if not point:
        return None, None
    lat = point.get("lat") or point.get("latitude")
    lon = point.get("lon") or point.get("longitude")
    try:
        lat = float(lat) if lat is not None else None
    except (TypeError, ValueError):
        lat = None
    try:
        lon = float(lon) if lon is not None else None
    except (TypeError, ValueError):
        lon = None
    return lat, lon


def compute_house_box(row: dict) -> str | None:
    """
    From boundingBox1..boundingBox25 in row, compute one encompassing box:
    sw = (min lat, min lon), ne = (max lat, max lon).
    Returns JSON string for houseBox, or None if no valid boxes.
    """
    lats, lons = [], []
    for i in range(1, 26):
        col = f"boundingBox{i}"
        raw = row.get(col, "")
        sw, ne = parse_bbox_cell(raw)
        for pt in (sw, ne):
            if pt is None:
                continue
            lat, lon = extract_lat_lon(pt)
            if lat is not None:
                lats.append(lat)
            if lon is not None:
                lons.append(lon)
    if not lats or not lons:
        return None
    sw_lat, ne_lat = min(lats), max(lats)
    sw_lon, ne_lon = min(lons), max(lons)
    house = {
        "sw": {"lat": sw_lat, "lon": sw_lon},
        "ne": {"lat": ne_lat, "lon": ne_lon},
    }
    return json.dumps(house)


def main() -> None:
    if not os.path.isfile(INPUT_CSV):
        raise SystemExit(f"Input file not found: {INPUT_CSV}")

    with open(INPUT_CSV, newline="", encoding="utf-8") as f_in:
        reader = csv.DictReader(f_in)
        fieldnames = list(reader.fieldnames) + ["houseBox"]
        rows = list(reader)

    for row in rows:
        row["houseBox"] = compute_house_box(row) or ""

    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f_out:
        writer = csv.DictWriter(f_out, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Wrote {len(rows)} rows with houseBox to {OUTPUT_CSV}")


if __name__ == "__main__":
    main()
