"""
Add derived columns to the Regrid+API joined CSV:

1. neighbors_w_solar at several radii (if solar_panels column exists)
2. time_since_sale: years since saledate
3. time_since_build: years since calculated_build_year
4. city_solar_percentage (if solar_panels column exists)
5. recent_rebuild: 1 if year_built_effective_date within last N years
6. recent_purchase: 1 if saledate within last N years
7. recent_build: 1 if yearbuilt within last N years
8. electric_heating: 1 if heatingdscr contains "Electric" or "Heat Pump"
"""

from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pandas as pd
# Radii (miles) for neighbor-with-solar counts; one column per radius
NEIGHBOR_RADIUS_MILES = [0.5, 0.25, 0.1, 0.05]
CURRENT_YEAR = 2026
RECENT_REBUILD_YEARS = 5  # year_built_effective_date within this many years -> recent_rebuild=1
RECENT_PURCHASE_YEARS = 5  # saledate within this many years -> recent_purchase=1
RECENT_BUILD_YEARS = 5     # yearbuilt within this many years -> recent_build=1

# Earth radius in miles for haversine
EARTH_RADIUS_MILES = 3958.8


def haversine_miles(
    lat1: np.ndarray, lon1: np.ndarray, lat2: np.ndarray, lon2: np.ndarray
) -> np.ndarray:
    """Vectorized haversine distance in miles. All inputs in degrees."""
    lat1, lon1, lat2, lon2 = (
        np.radians(lat1),
        np.radians(lon1),
        np.radians(lat2),
        np.radians(lon2),
    )
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = np.sin(dlat / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2) ** 2
    c = 2 * np.arcsin(np.sqrt(np.minimum(a, 1.0)))
    return EARTH_RADIUS_MILES * c


def parse_effective_year(series: pd.Series) -> pd.Series:
    """Extract year from year_built_effective_date (numeric year or date string). Returns NaN where unparseable."""
    def one(val):
        if pd.isna(val):
            return np.nan
        if isinstance(val, (int, float)):
            y = int(val)
            return y if 1900 <= y <= 2100 else np.nan
        s = str(val).strip()
        if not s:
            return np.nan
        parts = re.split(r"[/\-\.]", s)
        if not parts:
            return np.nan
        try:
            # Prefer last token as year (handles M/D/YYYY or YYYY)
            raw = int(float(parts[-1])) if parts[-1] else np.nan
            if pd.isna(raw):
                return np.nan
            y = raw if raw >= 100 else (2000 + raw if raw < 50 else 1900 + raw)
            return y if 1900 <= y <= 2100 else np.nan
        except (ValueError, IndexError):
            return np.nan

    return series.map(one)


def parse_sale_year(saledate_series: pd.Series) -> pd.Series:
    """Parse saledate (e.g. '6/4/13', '10/12/04') to integer year. Returns NaN where unparseable."""
    def one(s):
        if pd.isna(s) or not isinstance(s, str):
            return np.nan
        s = s.strip()
        if not s:
            return np.nan
        # Assume M/D/YY or M/D/YYYY
        parts = re.split(r"[/\-\.]", s)
        if len(parts) < 3:
            return np.nan
        try:
            y = int(parts[2])
            if y < 100:
                y = 2000 + y if y < 50 else 1900 + y
            return y
        except (ValueError, IndexError):
            return np.nan

    return saledate_series.map(one)


def main(config=None) -> None:
    if config:
        input_path = config.regrid_joined_path
        output_path = config.working_dir / "regrid_with_derived.csv"
        config.ensure_dirs()
    else:
        base = Path(__file__).resolve().parent.parent
        input_path = base / "data" / "working" / "Boulder_CO_Regrid_joined_with_API.csv"
        output_path = base / "data" / "working" / "Boulder_CO_Regrid_joined_with_API test.csv"

    if not input_path.exists():
        raise FileNotFoundError(f"Input CSV not found: {input_path}")

    print(f"Reading {input_path} ...")
    df = pd.read_csv(input_path, low_memory=False)

    # Prefer latitude/longitude; fallback to lat/lon
    if "latitude" in df.columns and "longitude" in df.columns:
        lat = pd.to_numeric(df["latitude"], errors="coerce")
        lon = pd.to_numeric(df["longitude"], errors="coerce")
    elif "lat" in df.columns and "lon" in df.columns:
        lat = pd.to_numeric(df["lat"], errors="coerce")
        lon = pd.to_numeric(df["lon"], errors="coerce")
    else:
        raise ValueError("Need either (latitude, longitude) or (lat, lon) columns")

    # 1) neighbors_w_solar at each radius: count others within radius with solar_panels == 'Yes'
    has_solar_col = "solar_panels" in df.columns
    if has_solar_col:
        solar_yes = (df["solar_panels"].astype(str).str.strip().str.lower() == "yes").values
    else:
        solar_yes = np.zeros(len(df), dtype=bool)
    lat_arr = lat.values.astype(float)
    lon_arr = lon.values.astype(float)
    n = len(df)
    num_radii = len(NEIGHBOR_RADIUS_MILES)
    neighbors = np.zeros((n, num_radii), dtype=int)

    print(f"Computing neighbors_w_solar at {NEIGHBOR_RADIUS_MILES} mi ...")
    for i in range(n):
        if np.isnan(lat_arr[i]) or np.isnan(lon_arr[i]):
            neighbors[i, :] = 0
            continue
        dist = haversine_miles(
            np.full(n, lat_arr[i]),
            np.full(n, lon_arr[i]),
            lat_arr,
            lon_arr,
        )
        others_with_solar = (np.arange(n) != i) & solar_yes
        for j, radius_mi in enumerate(NEIGHBOR_RADIUS_MILES):
            neighbors[i, j] = np.sum(others_with_solar & (dist <= radius_mi))

    for j, radius_mi in enumerate(NEIGHBOR_RADIUS_MILES):
        col_name = f"neighbors_w_solar_{str(radius_mi).replace('.', '_')}_mi"
        df[col_name] = neighbors[:, j]

    # 2) time_since_sale
    sale_year = parse_sale_year(df["saledate"])
    df["time_since_sale"] = (CURRENT_YEAR - sale_year).astype("Int64")  # nullable int

    # 3) time_since_build
    build_year = pd.to_numeric(df["calculated_build_year"], errors="coerce")
    df["time_since_build"] = (CURRENT_YEAR - build_year).astype("Int64")

    # 4) city_solar_percentage
    if has_solar_col:
        city_pct = (
            df.groupby("city")["solar_panels"]
            .transform(lambda s: 100.0 * (s.astype(str).str.strip().str.lower() == "yes").mean())
        )
        df["city_solar_percentage"] = city_pct.round(2)
    else:
        df["city_solar_percentage"] = 0.0

    # 5) recent_rebuild: 1 if year_built_effective_date within last RECENT_REBUILD_YEARS years
    effective_year = parse_effective_year(df["year_built_effective_date"])
    min_year = CURRENT_YEAR - RECENT_REBUILD_YEARS
    df["recent_rebuild"] = ((effective_year >= min_year) & effective_year.notna()).astype(int)

    # 6) recent_purchase: 1 if saledate within last RECENT_PURCHASE_YEARS years
    min_sale_year = CURRENT_YEAR - RECENT_PURCHASE_YEARS
    df["recent_purchase"] = ((sale_year >= min_sale_year) & sale_year.notna()).astype(int)

    # 7) recent_build: 1 if yearbuilt within last RECENT_BUILD_YEARS years
    yearbuilt = pd.to_numeric(df["yearbuilt"], errors="coerce")
    min_build_year = CURRENT_YEAR - RECENT_BUILD_YEARS
    df["recent_build"] = ((yearbuilt >= min_build_year) & yearbuilt.notna()).astype(int)

    # 8) electric_heating: 1 if heatingdscr contains "Electric" or "Heat Pump", else 0
    h = df["heatingdscr"].astype(str).str.strip()
    df["electric_heating"] = (
        h.str.contains("Electric", case=False, na=False)
        | h.str.contains("Heat Pump", case=False, na=False)
    ).astype(int)

    print(f"Writing {output_path} ...")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False)
    print("Done.")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", help="County config name or path")
    args = parser.parse_args()

    if args.config:
        from pipeline_config import load_config
        main(load_config(args.config))
    else:
        main()
