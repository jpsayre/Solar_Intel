#!/usr/bin/env python3
"""
Calculate roof scoring algorithm from solarintel.raw.sunroof data.

Reads from Postgres: solarintel.raw.sunroof (same schema as Boulder_CO_Python_SunroofAPI_Output.csv).
Uses the roof scoring algorithm from Analyze_ProjectSunroof_Data.py:
  - Finds matching segments (East/South/West by azimuth + min area)
  - For each matching segment: (quant_avg/1800)*100 + modified_azimuth_score*150 - (segment_count**2)/15
  - roof_score = max(score_sum) over matching segments, or NULL if no qualifying segments

Env:
  DATABASE_SOLAR_INTEL_URL   Postgres connection string

Output: CSV with original_index and roof_score.
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
MAX_INDEX = 25

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
DEFAULT_OUTPUT_CSV = os.path.join(PROJECT_ROOT, "data", "working", "roof_scores.csv")


def _col(row: dict, base: str, i: int):
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


def parse_quantile_avg(quant_val) -> float | None:
    """Parse quantileStats and return Avg value. Handles JSON string or dict."""
    if quant_val is None:
        return None
    if isinstance(quant_val, dict):
        avg = quant_val.get("Avg") or quant_val.get("avg")
        return float(avg) if avg is not None else None
    if isinstance(quant_val, str):
        try:
            data = json.loads(quant_val)
            if isinstance(data, dict):
                avg = data.get("Avg") or data.get("avg")
                return float(avg) if avg is not None else None
        except (json.JSONDecodeError, TypeError):
            pass
    return None


def get_segment_count(row: dict) -> int:
    """Get segment_count from row; fallback to 0 if missing."""
    val = row.get("segment_count") or row.get("segmentcount")
    if val is None or pd.isna(val):
        return 0
    try:
        return int(float(val))
    except (TypeError, ValueError):
        return 0


def compute_roof_score(row: dict, matching_segments: list[dict]) -> float | None:
    """
    Compute roof score from matching segments using the algorithm from Analyze_ProjectSunroof_Data.
    Returns None if no qualifying segments.
    """
    if not matching_segments:
        return None

    segment_count = get_segment_count(row)
    score_sum = []

    for segment in matching_segments:
        current_segment = segment["segment"]
        segment_area = float(segment[f"areaSqMeters{current_segment}"])
        segment_azimuth = float(segment[f"azimuth{current_segment}"])
        quant_val = segment[f"quantileStats{current_segment}"]
        quant_avg = parse_quantile_avg(quant_val)

        if quant_avg is None:
            continue

        # azimuth_score: east facing > 0, west facing < 0
        azimuth_score = ((180 - (segment_azimuth - 180)) / 180) - 1

        if azimuth_score > 0:  # east
            modified_azimuth_score = 1 - abs(azimuth_score * 1.2)
        else:  # west
            modified_azimuth_score = 1 - abs(azimuth_score * 0.8)

        score_sum.append(
            (quant_avg / 1800) * 100 + modified_azimuth_score * 150 - (segment_count ** 2) / 15
        )

    if not score_sum:
        return None

    return round(max(score_sum), 2)


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

    rows = df.to_dict("records")

    # Get original_index column (handle Postgres lowercase)
    original_index_col = "original_index"
    if original_index_col not in df.columns:
        for c in df.columns:
            if c.lower() == "original_index":
                original_index_col = c
                break

    # ok: may be column "ok" or "OK"
    ok_col = "ok" if "ok" in df.columns else "OK"
    is_ok = df[ok_col].astype(str).str.strip().str.lower() == "true"

    roof_scores = []
    for i, row in enumerate(rows):
        if not is_ok.iloc[i]:
            roof_scores.append(None)
            continue

        orientations, matching_segments = get_all_orientations(row)
        score = compute_roof_score(row, matching_segments)
        roof_scores.append(score)

    out_df = pd.DataFrame({
        "original_index": df[original_index_col],
        "roof_score": roof_scores,
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
