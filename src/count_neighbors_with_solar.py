#!/usr/bin/env python3
"""
Count neighbors with solar at multiple radii for each home in raw.regrid_filtered.

Replicates the neighbor-with-solar logic from Add_Derived_Columns.py using:
- raw.permits_by_strap (strap, solar_pv) for solar panel status (solar_pv=1 means has solar)
- raw.regrid_filtered (original_index, lat, lon, alt_parcelnumb1) joined on strap = alt_parcelnumb1

For each home, counts OTHER homes with solar_pv=1 within radii:
  3 mi, 1 mi, 0.5 mi, 0.25 mi, 0.1 mi, 0.05 mi

Uses haversine distance (lat/lon) to compute distances.

Output: Refreshes raw.counts_of_neighbors_with_solar table with columns:
  original_index, strap, count_3mi, count_1mi, count_0_5mi, count_0_25mi, count_0_1mi, count_0_05mi

Env:
  DATABASE_SOLAR_INTEL_URL   Postgres connection string
"""

from __future__ import annotations

import os

import numpy as np
import pandas as pd
import psycopg2
from psycopg2.extras import execute_values

# Radii (miles) for neighbor-with-solar counts
NEIGHBOR_RADIUS_MILES = [3.0, 1.0, 0.5, 0.25, 0.1, 0.05]
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


def main() -> None:
    db_url = os.getenv("DATABASE_SOLAR_INTEL_URL")
    if not db_url:
        raise RuntimeError("DATABASE_SOLAR_INTEL_URL is not set")

    conn = psycopg2.connect(db_url)

    try:
        # Load permits_by_strap: strap, solar_pv (solar_pv=1 means has solar)
        permits_sql = "SELECT strap, solar_pv FROM raw.permits_by_strap"
        permits_df = pd.read_sql(permits_sql, conn)
        print(f"Loaded {len(permits_df)} rows from raw.permits_by_strap")

        # Load regrid_filtered: original_index, lat, lon, alt_parcelnumb1
        # (If your table uses latitude/longitude instead of lat/lon, change the SQL below)
        regrid_sql = """
            SELECT original_index, lat, lon, alt_parcelnumb1
            FROM raw.regrid_filtered
        """
        regrid_df = pd.read_sql(regrid_sql, conn)
        print(f"Loaded {len(regrid_df)} rows from raw.regrid_filtered")

        # Left join: regrid_filtered keeps all rows, add solar_pv from permits_by_strap
        # strap in permits = alt_parcelnumb1 in regrid
        regrid_df = regrid_df.merge(
            permits_df,
            left_on="alt_parcelnumb1",
            right_on="strap",
            how="left",
        )
        # Output strap = alt_parcelnumb1 (parcel id for each regrid row)
        regrid_df["strap"] = regrid_df["alt_parcelnumb1"].astype(str)

        # solar_pv: 1 = has solar, 0 or NaN = no solar (for neighbor counting)
        solar_pv = regrid_df["solar_pv"].fillna(0).astype(int)
        solar_yes = (solar_pv == 1).values

        # Lat/lon - handle Postgres lowercase
        lat_col = "lat" if "lat" in regrid_df.columns else "latitude"
        lon_col = "lon" if "lon" in regrid_df.columns else "longitude"
        lat = pd.to_numeric(regrid_df[lat_col], errors="coerce").values.astype(float)
        lon = pd.to_numeric(regrid_df[lon_col], errors="coerce").values.astype(float)

        n = len(regrid_df)
        num_radii = len(NEIGHBOR_RADIUS_MILES)
        neighbors = np.zeros((n, num_radii), dtype=int)

        print(f"Computing neighbor counts at {NEIGHBOR_RADIUS_MILES} mi ...")
        for i in range(n):
            if np.isnan(lat[i]) or np.isnan(lon[i]):
                neighbors[i, :] = 0
                continue
            dist = haversine_miles(
                np.full(n, lat[i]),
                np.full(n, lon[i]),
                lat,
                lon,
            )
            others_with_solar = (np.arange(n) != i) & solar_yes
            for j, radius_mi in enumerate(NEIGHBOR_RADIUS_MILES):
                neighbors[i, j] = np.sum(others_with_solar & (dist <= radius_mi))

        # Build output DataFrame
        col_names = [
            "count_3mi",
            "count_1mi",
            "count_0_5mi",
            "count_0_25mi",
            "count_0_1mi",
            "count_0_05mi",
        ]
        out_df = regrid_df[["original_index", "strap"]].copy()
        for j, col_name in enumerate(col_names):
            out_df[col_name] = neighbors[:, j]

        # Ensure table exists (first run), then truncate and insert
        with conn.cursor() as cur:
            cur.execute("CREATE SCHEMA IF NOT EXISTS raw")
            cur.execute("""
                CREATE TABLE IF NOT EXISTS raw.counts_of_neighbors_with_solar (
                    original_index VARCHAR(100) NOT NULL,
                    strap VARCHAR(100),
                    count_3mi INTEGER NOT NULL DEFAULT 0,
                    count_1mi INTEGER NOT NULL DEFAULT 0,
                    count_0_5mi INTEGER NOT NULL DEFAULT 0,
                    count_0_25mi INTEGER NOT NULL DEFAULT 0,
                    count_0_1mi INTEGER NOT NULL DEFAULT 0,
                    count_0_05mi INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (original_index)
                )
            """)
            cur.execute("TRUNCATE TABLE raw.counts_of_neighbors_with_solar")
            conn.commit()

        # Insert using execute_values (handles special chars, reasonably fast)
        rows = []
        for _, row in out_df.iterrows():
            orig_idx = row["original_index"]
            orig_idx_val = orig_idx if pd.isna(orig_idx) else str(orig_idx)
            strap_val = None if pd.isna(row["strap"]) or str(row["strap"]) == "nan" else str(row["strap"])
            rows.append(
                (
                    orig_idx_val,
                    strap_val,
                    int(row["count_3mi"]),
                    int(row["count_1mi"]),
                    int(row["count_0_5mi"]),
                    int(row["count_0_25mi"]),
                    int(row["count_0_1mi"]),
                    int(row["count_0_05mi"]),
                )
            )

        with conn.cursor() as cur:
            execute_values(
                cur,
                """
                INSERT INTO raw.counts_of_neighbors_with_solar
                (original_index, strap, count_3mi, count_1mi, count_0_5mi, count_0_25mi, count_0_1mi, count_0_05mi)
                VALUES %s
                """,
                rows,
                page_size=5000,
            )
            conn.commit()

        print(f"Wrote {len(out_df)} rows to raw.counts_of_neighbors_with_solar")

    finally:
        conn.close()


if __name__ == "__main__":
    main()
