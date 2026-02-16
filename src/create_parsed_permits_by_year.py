"""
Create parsed_permits_by_year.csv from parsed_permits_test.csv.
Aggregates permits by strap and year, taking max of each binary column per year.
Fills missing years (2012-2026) per strap with 0s.
Applies configurable persistence: each column can persist for N years (e.g. solar ~25yr, roof ~7yr).
Filters to straps in data/final/regrid_filtered.csv (alt_parcelnumb1 = strap).
Computes neighbors_w_solar by year at radii 3, 1, 0.5, 0.25, 0.1, 0.05 miles.
Joins roof_score, adds time_since_sale, time_since_build, recent_build, recent_purchase, solar_next_year.
"""

import re
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.neighbors import BallTree

INPUT_PATH = Path(__file__).resolve().parents[1] / "data" / "working" / "parsed_permits_test.csv"
OUTPUT_PATH = Path(__file__).resolve().parents[1] / "data" / "working" / "parsed_permits_by_year.csv"
REGRID_FILTERED_PATH = Path(__file__).resolve().parents[1] / "data" / "final" / "regrid_filtered.csv"
ROOF_SCORE_PATH = Path(__file__).resolve().parents[1] / "data" / "final" / "roof_score.csv"

RECENT_YEARS = 5  # <5 years for recent_rebuild, recent_purchase

YEAR_MIN = 2012
YEAR_MAX = 2026

NEIGHBOR_RADIUS_MILES = [3.0, 1.0, 0.5, 0.25, 0.1, 0.05]
EARTH_RADIUS_MILES = 3958.8

# Persistence in years: how long a "1" remains relevant after the permit year.
# None or 0 = no persistence (use raw year-by-year value only).
# Use a large number (e.g. 999) for "effectively forever" (solar, battery, ev_charger).
PERSISTENCE_YEARS = {
    "solar_pv": 25,
    "battery": 15,
    "ev_charger": 25,
    "roof_new_or_replace": 7,
    "electrical_service_upgrade": 10,
    "heat_pump": 15,
    "ac": 15,
    "furnace": 20,
    "water_heater": 15,
    "water_heater_electric": 15,
    "water_heater_gas": 15,
    "water_heater_solar_thermal": 20,
    "windows_doors": 25,
    "insulation_airseal": 20,
    "generator": 15,
    "addition_new_build": 999,  # permanent
    "kitchen_bath_remodel": 15,
    "pool_hot_tub": 25,
    "evaporative_cooler": 15,
}

def _parse_sale_year(s: pd.Series) -> pd.Series:
    """Parse saledate to integer year. Returns NaN where unparseable."""

    def one(val):
        if pd.isna(val):
            return np.nan
        s = str(val).strip()
        if not s:
            return np.nan
        parts = re.split(r"[/\-\.]", s)
        if len(parts) < 3:
            return np.nan
        try:
            y = int(float(parts[-1])) if parts[-1] else np.nan
            if pd.isna(y):
                return np.nan
            if y < 100:
                y = 2000 + y if y < 50 else 1900 + y
            return y if 1900 <= y <= 2100 else np.nan
        except (ValueError, IndexError):
            return np.nan

    return s.map(one)


BINARY_COLUMNS = [
    "solar_pv",
    "battery",
    "ev_charger",
    "roof_new_or_replace",
    "electrical_service_upgrade",
    "heat_pump",
    "ac",
    "furnace",
    "water_heater",
    "water_heater_electric",
    "water_heater_gas",
    "water_heater_solar_thermal",
    "windows_doors",
    "insulation_airseal",
    "generator",
    "addition_new_build",
    "kitchen_bath_remodel",
    "pool_hot_tub",
    "evaporative_cooler",
]


def main():
    regrid = pd.read_csv(REGRID_FILTERED_PATH)
    regrid["strap"] = regrid["alt_parcelnumb1"].astype(str)
    regrid = regrid.dropna(subset=["strap"])
    regrid = regrid.drop_duplicates(subset=["strap"], keep="first")
    filtered_straps = set(regrid["strap"].unique())
    print(f"Filtering to {len(filtered_straps)} straps from {REGRID_FILTERED_PATH.name} (alt_parcelnumb1)")

    df = pd.read_csv(INPUT_PATH)
    df = df[df["strap"].isin(filtered_straps)]
    df["issue_dt"] = pd.to_datetime(df["issue_dt"], errors="coerce")
    df["year"] = df["issue_dt"].dt.year
    df = df.dropna(subset=["year"])

    agg_dict = {col: "max" for col in BINARY_COLUMNS}
    result = df.groupby(["strap", "year"], as_index=False).agg(agg_dict)
    result["year"] = result["year"].astype(int)

    # Fill missing years (2012-2026) per strap with 0s (use filtered_straps as master list)
    straps = list(filtered_straps)
    full_years = pd.DataFrame(
        [(s, y) for s in straps for y in range(YEAR_MIN, YEAR_MAX + 1)],
        columns=["strap", "year"],
    )
    result = full_years.merge(result, on=["strap", "year"], how="left")
    result[BINARY_COLUMNS] = result[BINARY_COLUMNS].fillna(0).astype(int)

    # Apply configurable persistence: for each column, a "1" persists for N years
    result = result.sort_values(["strap", "year"])
    for col in BINARY_COLUMNS:
        persist_years = PERSISTENCE_YEARS.get(col)
        if persist_years is None or persist_years <= 0:
            continue
        result[col] = (
            result.groupby("strap")[col]
            .transform(lambda x: x.rolling(window=persist_years, min_periods=1).max())
            .fillna(0)
            .astype(int)
        )

    # Neighbors with solar by year: for each year, snapshot of who has solar, then count neighbors
    lat_col = "lat" if "lat" in regrid.columns else "latitude"
    lon_col = "lon" if "lon" in regrid.columns else "longitude"
    regrid_lat = pd.to_numeric(regrid[lat_col], errors="coerce").values.astype(float)
    regrid_lon = pd.to_numeric(regrid[lon_col], errors="coerce").values.astype(float)
    regrid_strap = regrid["strap"].values
    n_regrid = len(regrid)

    valid = ~(np.isnan(regrid_lat) | np.isnan(regrid_lon))
    coords_rad = np.column_stack(
        [np.radians(regrid_lat[valid]), np.radians(regrid_lon[valid])]
    )
    tree = BallTree(coords_rad, metric="haversine")
    valid_idx = np.where(valid)[0]
    neighbor_cols = [
        "count_3mi",
        "count_1mi",
        "count_0_5mi",
        "count_0_25mi",
        "count_0_1mi",
        "count_0_05mi",
    ]
    for col in neighbor_cols:
        result[col] = 0

    print(f"Computing neighbors_w_solar by year at {NEIGHBOR_RADIUS_MILES} mi ...")
    for year in range(YEAR_MIN, YEAR_MAX + 1):
        year_result = result[result["year"] == year]
        solar_by_strap = year_result.set_index("strap")["solar_pv"].to_dict()
        solar_yes = np.array(
            [solar_by_strap.get(str(regrid_strap[i]), 0) for i in valid_idx],
            dtype=int,
        )

        counts = np.zeros((len(valid_idx), len(NEIGHBOR_RADIUS_MILES)), dtype=int)
        for j, radius_mi in enumerate(NEIGHBOR_RADIUS_MILES):
            radius_rad = radius_mi / EARTH_RADIUS_MILES
            neighbors_idx = tree.query_radius(coords_rad, r=radius_rad)
            for i in range(len(valid_idx)):
                idx_list = neighbors_idx[i]
                others = idx_list[idx_list != i]
                counts[i, j] = np.sum(solar_yes[others] == 1)

        year_counts = pd.DataFrame(
            {"strap": [regrid_strap[valid_idx[i]] for i in range(len(valid_idx))]}
        )
        for j, col in enumerate(neighbor_cols):
            year_counts[col] = counts[:, j]

        year_mask = result["year"] == year
        result_year = result.loc[year_mask].merge(
            year_counts, on="strap", how="left", suffixes=("_old", "")
        )
        for col in neighbor_cols:
            result.loc[year_mask, col] = result_year[col].fillna(0).astype(int).values

        print(f"  Year {year} done")

    for col in neighbor_cols:
        result[col] = result[col].fillna(0).astype(int)

    # Join regrid_filtered (property attributes, same for each strap year after year)
    regrid_join = regrid.drop(columns=["alt_parcelnumb1"], errors="ignore")
    result = result.merge(regrid_join, on="strap", how="left")
    print(f"Joined regrid_filtered ({len(regrid_join.columns)} columns)")

    # Join roof_score (on original_index from regrid)
    roof_score_df = pd.read_csv(ROOF_SCORE_PATH)
    result = result.merge(roof_score_df, on="original_index", how="left")
    null_count = result["roof_score"].isna().sum()
    roof_mean = result["roof_score"].mean()
    result["roof_score"] = result["roof_score"].fillna(roof_mean)
    print(f"Joined roof_score (filled {null_count} nulls with mean {roof_mean:.2f})")

    # Derived columns (year = current year for each row)
    sale_year = _parse_sale_year(result["saledate"])
    build_year = pd.to_numeric(result["calculated_build_year"], errors="coerce")

    result["time_since_sale"] = (result["year"] - sale_year).astype("Int64")
    result.loc[result["time_since_sale"] < 0, "time_since_sale"] = 10
    result["time_since_build"] = (result["year"] - build_year).astype("Int64")

    result["recent_build"] = (result["time_since_build"] <= 7).astype(int)

    min_year_purchase = result["year"] - RECENT_YEARS
    result["recent_purchase"] = (
        (sale_year >= min_year_purchase) & sale_year.notna()
    ).astype(int)

    # solar_next_year: 1 = year before first solar (for prediction), 2 = already have solar (filter out), 0 = no solar next year
    result = result.sort_values(["strap", "year"])
    first_solar_year = result[result["solar_pv"] == 1].groupby("strap")["year"].min()
    result = result.merge(first_solar_year.rename("_fsy"), on="strap", how="left")
    result["solar_next_year"] = 0
    result.loc[result["year"] == result["_fsy"] - 1, "solar_next_year"] = 1
    result.loc[result["year"] >= result["_fsy"], "solar_next_year"] = 2
    result.drop(columns=["_fsy"], inplace=True)

    result.to_csv(OUTPUT_PATH, index=False)
    print(f"Wrote {len(result)} rows to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
