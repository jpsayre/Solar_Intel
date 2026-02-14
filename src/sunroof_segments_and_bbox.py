#!/usr/bin/env python3
"""
Combine segment/orientation matching (from Analyze_ProjectSunroof_Data) with
house bounding box computation (from compute_house_bounding_box).

- Reads from Postgres: solarintel.raw.sunroof (same schema as Boulder_CO_Python_SunroofAPI_Output.csv).
- For every row: finds matching segments and orientations (East/South/West by azimuth + min area).
  Does NOT filter rows: rows with no match get 0 matching segments.
- Computes house bounding box from boundingBox1..boundingBox25.
- Does NOT compute solar score.
- Writes all rows plus new columns to a CSV file.

Env:
  DATABASE_SOLAR_INTEL_URL   Postgres connection string

Output columns: original_index, roof_orientation, matching_segments, matching_segment_count,
  matching_segment_sum, matching_segment_max, houseBox.
When ok==False, matching_segments (and count/sum/max) are set to "Unknown".
"""

from __future__ import annotations

import json
import os
import sys

import pandas as pd
import psycopg2

# Segment/orientation constants (from Analyze_ProjectSunroof_Data)
EAST_MIN_AZ = 80
EAST_MAX_AZ = 140
SOUTH_MIN_AZ = 140
SOUTH_MAX_AZ = 220
WEST_MIN_AZ = 220
WEST_MAX_AZ = 280
MIN_AREA = 30
MAX_INDEX = 25  # 1-based: segments 1..25

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
DEFAULT_OUTPUT_CSV = os.path.join(PROJECT_ROOT, "data", "working", "sunroof_segments_and_bbox.csv")


def _col(row: dict, base: str, i: int) -> str | None:
    """Get cell value trying camelCase and lowercase column names (Postgres often lowercases)."""
    camel = f"{base}{i}"
    lower = camel.lower()
    return row.get(camel) if camel in row else row.get(lower)


def find_matching_segments(row: dict, min_az: float, max_az: float) -> list[dict]:
    """Find roof segments matching azimuth and area criteria. Uses 1-based segment indices 1..25."""
    matches = []
    for i in range(1, MAX_INDEX + 1):
        az_val = _col(row, "azimuth", i)
        area_val = _col(row, "areaSqMeters", i)
        quant_val = _col(row, "quantileStats", i)

        if az_val is None and area_val is None:
            continue
        if pd.isna(az_val) or pd.isna(area_val):
            continue
        try:
            az = float(az_val)
            area = float(area_val)
        except (TypeError, ValueError):
            continue

        if min_az <= az <= max_az and area >= MIN_AREA:
            matches.append({
                "segment": i,
                f"azimuth{i}": az,
                f"areaSqMeters{i}": area,
                f"quantileStats{i}": quant_val,
            })
    return matches


def get_all_orientations(row: dict) -> tuple[list[str], list[dict]]:
    """Return (list of orientation names, list of all matching segment dicts)."""
    orientations = []
    all_matching_segments = []

    east_segments = find_matching_segments(row, EAST_MIN_AZ, EAST_MAX_AZ)
    if east_segments:
        orientations.append("East")
        all_matching_segments.extend(east_segments)

    south_segments = find_matching_segments(row, SOUTH_MIN_AZ, SOUTH_MAX_AZ)
    if south_segments:
        orientations.append("South")
        all_matching_segments.extend(south_segments)

    west_segments = find_matching_segments(row, WEST_MIN_AZ, WEST_MAX_AZ)
    if west_segments:
        orientations.append("West")
        all_matching_segments.extend(west_segments)

    return orientations, all_matching_segments


# --- House bounding box (from compute_house_bounding_box) ---

def parse_bbox_cell(value) -> tuple[dict | None, dict | None]:
    """Parse a boundingBox cell (JSON). Returns (sw, ne) or (None, None) if empty/invalid."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return None, None
    if isinstance(value, dict):
        data = value
    else:
        try:
            data = json.loads(value) if isinstance(value, str) else None
        except (json.JSONDecodeError, TypeError):
            return None, None
    if not isinstance(data, dict):
        return None, None
    sw = data.get("sw") if isinstance(data.get("sw"), dict) else None
    ne = data.get("ne") if isinstance(data.get("ne"), dict) else None
    return sw, ne


def extract_lat_lon(point: dict | None) -> tuple[float | None, float | None]:
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
    From boundingBox1..boundingBox25 in row, compute one encompassing box.
    Returns JSON string for houseBox, or None if no valid boxes.
    """
    lats, lons = [], []
    for i in range(1, 26):
        raw = _col(row, "boundingBox", i)
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
    house = {
        "sw": {"lat": min(lats), "lon": min(lons)},
        "ne": {"lat": max(lats), "lon": max(lons)},
    }
    return json.dumps(house)


def load_sunroof_table(conn) -> pd.DataFrame:
    """Read full solarintel.raw.sunroof into a DataFrame."""
    return pd.read_sql("SELECT * FROM solarintel.raw.sunroof", conn)


def run(output_csv: str | None = None, sql_limit: int | None = None) -> None:
    db_url = os.getenv("DATABASE_SOLAR_INTEL_URL")
    if not db_url:
        raise RuntimeError("DATABASE_SOLAR_INTEL_URL is not set")

    out_path = output_csv or DEFAULT_OUTPUT_CSV
    conn = psycopg2.connect(db_url)

    try:
        sql = "SELECT * FROM solarintel.raw.sunroof"
        if sql_limit is not None:
            sql += f" LIMIT {int(sql_limit)}"
        df = pd.read_sql(sql, conn)
    finally:
        conn.close()

    print(f"Loaded {len(df)} rows from solarintel.raw.sunroof")

    # Convert to list of dicts for row-wise helpers that need both camelCase and lowercase keys
    # (Postgres may return lowercase column names)
    rows = df.to_dict("records")

    # Matching segments and orientations (no filtering: keep all rows)
    roof_orientations_list = []
    matching_segments_list = []
    for row in rows:
        orients, segs = get_all_orientations(row)
        roof_orientations_list.append(orients)
        matching_segments_list.append(segs)

    # ok: may be column "ok" or "OK" (Postgres often lowercases)
    ok_col = "ok" if "ok" in df.columns else "OK"
    is_ok = df[ok_col].astype(str).str.strip().str.lower() == "true"

    def sum_matching_area(segments):
        total = 0.0
        for seg in segments:
            for k, v in seg.items():
                if k.startswith("areaSqMeters") and isinstance(v, (int, float)):
                    total += float(v)
        return round(total, 2)

    def max_matching_area(segments):
        if not segments:
            return 0.0
        vals = []
        for seg in segments:
            for k, v in seg.items():
                if k.startswith("areaSqMeters") and isinstance(v, (int, float)):
                    vals.append(float(v))
        return round(max(vals), 2) if vals else 0.0

    roof_orientation = [", ".join(o) if o else "" for o in roof_orientations_list]
    matching_segment_count = [
        "Unknown" if not ok else len(segs)
        for ok, segs in zip(is_ok, matching_segments_list)
    ]
    matching_segment_sum = [
        "Unknown" if not ok else sum_matching_area(segs)
        for ok, segs in zip(is_ok, matching_segments_list)
    ]
    matching_segment_max = [
        "Unknown" if not ok else max_matching_area(segs)
        for ok, segs in zip(is_ok, matching_segments_list)
    ]
    def segments_to_json(segs):
        """Serialize segment list with quantileStats as real JSON objects (no escaped quotes)."""
        cleaned = []
        for s in segs:
            d = dict(s)
            for k in list(d):
                if k.startswith("quantileStats") and isinstance(d[k], str):
                    try:
                        d[k] = json.loads(d[k])
                    except (json.JSONDecodeError, TypeError):
                        pass
            cleaned.append(d)
        return json.dumps(cleaned)

    matching_segments = [
        "Unknown" if not ok else (segments_to_json(segs) if segs else "[]")
        for ok, segs in zip(is_ok, matching_segments_list)
    ]

    # House bounding box per row
    house_boxes = []
    for row in rows:
        hb = compute_house_box(row)
        house_boxes.append(hb if hb else "")

    # Output only original_index and calculated fields
    original_index_col = "original_index"
    if original_index_col not in df.columns:
        for c in df.columns:
            if c.lower() == "original_index":
                original_index_col = c
                break
    out_df = pd.DataFrame({
        "original_index": df[original_index_col],
        "roof_orientation": roof_orientation,
        "matching_segments": matching_segments,
        "matching_segment_count": matching_segment_count,
        "matching_segment_sum": matching_segment_sum,
        "matching_segment_max": matching_segment_max,
        "houseBox": house_boxes,
    })

    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    out_df.to_csv(out_path, index=False)
    print(f"Wrote {len(out_df)} rows to {out_path}")


if __name__ == "__main__":
    output = sys.argv[1] if len(sys.argv) > 1 else None
    limit = None
    if len(sys.argv) > 2:
        try:
            limit = int(sys.argv[2])
        except ValueError:
            pass
    run(output_csv=output, sql_limit=limit)
