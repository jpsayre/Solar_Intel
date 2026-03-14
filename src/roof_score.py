#!/usr/bin/env python3
"""
Calculate roof scoring algorithm from Sunroof API data.

Evaluates the whole roof holistically using a weighted sum of all qualifying
segments (East/South/West, azimuth 80–280°). Each segment contributes:

    total_weighted_area^0.5 where each segment's weighted area is:
    area × orientation_weight(azimuth) × (sunshine_avg / 1800)

Diminishing returns are applied to the total weighted area (not per segment)
via sqrt, so doubling total usable area only adds ~41%. South-facing
orientation with low shade matters most.

Orientation weights are physics-based with a west preference (evening solar
is more valuable): South=1.0, West≈0.47, East≈0.43.

A complexity discount (up to 25%) applies when usable area is spread across
many small segments rather than concentrated on one large surface.

Output: 0–100 score (10 floor for homes with Sunroof data but no qualifying
segments, NULL for homes without Sunroof data).

Env:
  DATABASE_SOLAR_INTEL_URL   Postgres connection string

Output: CSV with original_index and roof_score.
"""

from __future__ import annotations

import json
import math
import os
import sys

import pandas as pd
import psycopg2

# Scoring constants
MAX_INDEX = 25              # Sunroof API returns up to 25 roof segments
MIN_AZ = 80                 # Minimum azimuth for qualifying segments
MAX_AZ = 280                # Maximum azimuth for qualifying segments
REFERENCE_SUNSHINE = 1800.0  # Annual kWh/m² normalizer (typical max for Boulder)
IDEAL_SOLAR_VALUE = 14.0    # calibrated so ~3% of scores reach 100
FLOOR_SCORE = 10.0          # Score for homes with API data but no qualifying segments

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
DEFAULT_OUTPUT_CSV = os.path.join(PROJECT_ROOT, "data", "working", "roof_scores.csv")


def _col(row: dict, base: str, i: int):
    """Get cell value trying camelCase and lowercase column names (Postgres often lowercases)."""
    camel = f"{base}{i}"
    lower = camel.lower()
    return row.get(camel) if camel in row else row.get(lower)


def find_qualifying_segments(row: dict) -> list[dict]:
    """Find all roof segments with azimuth in the E/S/W range (80–280°)."""
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

        if MIN_AZ <= az <= MAX_AZ:
            matches.append({
                "segment": i,
                f"azimuth{i}": az,
                f"areaSqMeters{i}": area,
                f"quantileStats{i}": quant_val,
            })
    return matches


def get_orientations(segments: list[dict]) -> list[str]:
    """Derive orientation labels from qualifying segments."""
    orientations = set()
    for seg in segments:
        idx = seg["segment"]
        az = float(seg[f"azimuth{idx}"])
        if az < 140:
            orientations.add("East")
        elif az <= 220:
            orientations.add("South")
        else:
            orientations.add("West")
    return sorted(orientations)


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


def orientation_weight(azimuth: float) -> float:
    """Physics-based orientation weight. South=1.0, West>East, north=0.

    Power-curve falloff from south with a west bonus (evening solar is more
    valuable). At due south (180°) weight is 1.0; at due east (90°) ≈0.43;
    at due west (270°) ≈0.47.
    """
    delta = azimuth - 180  # signed: negative=east, positive=west
    abs_delta = abs(delta)
    if abs_delta > 100:
        return 0.0
    # Power-curve falloff: steep penalty as you move away from south
    normalized = abs_delta / 100  # 0 at south, 1 at east/west edges
    base = 1.0 - 0.65 * (normalized ** 1.2)
    if delta > 0:  # west side bonus (evening solar more valuable)
        base += 0.05 * normalized
    return max(base, 0.0)


def compute_roof_score(matching_segments: list[dict]) -> float | None:
    """Compute roof score from all qualifying segments.

    Uses a whole-roof weighted sum with diminishing returns on total area:
    1. Each segment contributes area × orientation_weight × sunshine_quality
    2. Total weighted area is compressed via pow(x, 0.5) for diminishing returns
    3. A complexity discount applies when area is spread across many segments
    4. Result is normalized to 0–100 against IDEAL_SOLAR_VALUE
    """
    if not matching_segments:
        return FLOOR_SCORE

    weighted_areas = []  # area weighted by orientation and sunshine
    raw_areas = []

    for segment in matching_segments:
        idx = segment["segment"]
        area = float(segment[f"areaSqMeters{idx}"])
        azimuth = float(segment[f"azimuth{idx}"])
        quant_avg = parse_quantile_avg(segment[f"quantileStats{idx}"])
        if quant_avg is None:
            continue
        weight = orientation_weight(azimuth)
        # Weighted area: how much "south-equivalent" area this segment provides
        weighted_areas.append(area * weight * (quant_avg / REFERENCE_SUNSHINE))
        raw_areas.append(area)

    if not weighted_areas:
        return FLOOR_SCORE

    total_weighted_area = sum(weighted_areas)

    # Diminishing returns on TOTAL weighted area: area^0.55 applied once
    # to the whole roof, not per segment. This prevents massive E/W roofs
    # from outscoring moderate south-facing roofs purely on volume.
    # 50 m² → 8.5, 100 m² → 12.0, 200 m² → 17.0, 400 m² → 24.0
    effective_value = pow(total_weighted_area, 0.55)

    # Complexity discount: penalize when usable area is spread across many
    # small segments (harder to install), but not if one large segment dominates.
    max_area = max(raw_areas)
    total_area = sum(raw_areas)
    concentration = max_area / total_area  # 1.0 = single segment, lower = fragmented
    complexity_factor = 0.75 + 0.25 * concentration  # 0.75–1.0

    raw = (effective_value * complexity_factor / IDEAL_SOLAR_VALUE) * 100
    return round(max(FLOOR_SCORE, min(100.0, raw)), 2)


def run(output_csv: str | None = None, sql_limit: int | None = None, config=None) -> None:
    if config:
        out_path = str(config.roof_score_path)
        config.ensure_dirs()
    else:
        out_path = output_csv or DEFAULT_OUTPUT_CSV

    # Try CSV first (preferred — no DB dependency)
    csv_path = config.sunroof_api_output_path if config else None
    if csv_path and os.path.exists(csv_path):
        print(f"Computing roof scores from {csv_path}")
        df = pd.read_csv(csv_path)
        return _compute_from_dataframe(df, out_path)

    # Fall back to Postgres
    db_url = os.getenv("DATABASE_SOLAR_INTEL_URL")
    if not db_url:
        raise RuntimeError("No Sunroof API CSV found and DATABASE_SOLAR_INTEL_URL is not set")
    conn = psycopg2.connect(db_url)

    try:
        sql = "SELECT * FROM solarintel.raw.sunroof"
        if sql_limit is not None:
            sql += f" LIMIT {int(sql_limit)}"
        df = pd.read_sql(sql, conn)
    finally:
        conn.close()

    print(f"Loaded {len(df)} rows from solarintel.raw.sunroof")
    _compute_from_dataframe(df, out_path)


def _compute_from_dataframe(df: pd.DataFrame, out_path: str) -> None:
    """Compute roof scores from a DataFrame."""
    rows = df.to_dict("records")

    original_index_col = "original_index"
    if original_index_col not in df.columns:
        for c in df.columns:
            if c.lower() == "original_index":
                original_index_col = c
                break

    ok_col = "ok" if "ok" in df.columns else "OK"
    is_ok = df[ok_col].astype(str).str.strip().str.lower() == "true"

    roof_scores = []
    for i, row in enumerate(rows):
        if not is_ok.iloc[i]:
            roof_scores.append(None)
            continue
        segments = find_qualifying_segments(row)
        score = compute_roof_score(segments)
        roof_scores.append(score)

    out_df = pd.DataFrame({
        "original_index": df[original_index_col],
        "roof_score": roof_scores,
    })

    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    out_df.to_csv(out_path, index=False)
    print(f"Wrote {len(out_df)} rows to {out_path}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", help="County config name or path")
    parser.add_argument("--output", help="Output CSV path")
    parser.add_argument("--limit", type=int, help="SQL LIMIT")
    args = parser.parse_args()

    if args.config:
        from pipeline_config import load_config
        run(config=load_config(args.config), sql_limit=args.limit)
    else:
        run(output_csv=args.output, sql_limit=args.limit)
