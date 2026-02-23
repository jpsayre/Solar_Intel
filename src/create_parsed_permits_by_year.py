"""
Create parsed_permits_by_year.csv from parsed_permits_test.csv.
Aggregates permits by strap and year, taking max of each binary column per year.
Fills missing years (2012-2026) per strap with 0s.
Applies configurable persistence: each column can persist for N years (e.g. solar ~25yr, roof ~7yr).
Filters to straps in data/final/regrid_filtered.csv (alt_parcelnumb1 = strap).
Computes neighbors_w_solar by year at radii 3, 1, 0.5, 0.25, 0.1, 0.05 miles.
Computes last_year_neighbors_w_solar (neighbors who had solar in prev year) at 0.05, 0.1, 0.25, 0.5, 1.0 mi.
Computes closest_fifty_percentage: % of 50 nearest neighbors with solar (year-aware).
Joins roof_score. Adds calculated_roof_age (time-aware, permit-aware: year - build_year, resets to 0 when roof permit pulled),
time_since_sale, time_since_build, recent_build, recent_purchase,
electricity_use_proxy (area × load factors: electric heat, AC, pool, EV, battery, etc.),
likely_mortgage_rate (time-aware: starts 2012, drops when rate falls >0.75 pct, resets on sale year),
solar_next_year.
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
ELECTRICITY_PRICE_PATH = Path(__file__).resolve().parents[1] / "data" / "raw" / "Average_retail_price_of_electricity.csv"
AVG_YEARLY_INTEREST_PATH = Path(__file__).resolve().parents[1] / "data" / "final" / "avg_yearly_interest.csv"

# Columns to exclude from regrid when joining (alt_parcelnumb1 is redundant with strap)
REGRID_EXCLUDE_COLUMNS = [
    "alt_parcelnumb1",
    "usedesc",
    "zoning",
    "zoning_description",
    "year_built_effective_date",
    "numstories",
    "numrooms",
    "num_bath",
    "num_bath_partial",
    "num_bedrooms",
    "owner",
    "mailadd",
    "original_mailing_address",
    "mail_state2",
    "address",
    "scity",
    "original_address",
    "city",
    "county",
    "state2",
    "subdivision",
    "lat",
    "lon",
    "recrdareano",
    "area_building_definition",
    "designcodedscr",
    "qualitycodedscr",
    "bldgclassdscr",
    "constcodedscr",
    "effectiveyear",
    "bsmtsf",
    "bsmttypedscr",
    "carstoragesf",
    "extwalldscrprim",
    "extwalldscrsec",
    "intwalldscr",
    "roof_coverdscr",
    "sales_cd",
    "mainfloorsf_int",
    "saleprice_int",
    "owneroccupied",
]

# Required for roof_score join and derived columns - never exclude (silently ignored if in REGRID_EXCLUDE_COLUMNS)
REGRID_REQUIRED_COLUMNS = [
    "strap",
    "original_index",
    "saledate",
    "calculated_build_year",
    "saleprice",
    "sqft",
    "mainfloorsf",
]

RECENT_YEARS = 3  # <5 years for recent_rebuild, recent_purchase

YEAR_MIN = 2012
YEAR_MAX = 2026

NEIGHBOR_RADIUS_MILES = [3.0, 1.0, 0.5, 0.25, 0.1, 0.05]
LAST_YEAR_NEIGHBOR_RADIUS_MILES = [0.05, 0.1, 0.25, 0.5, 1.0]
CLOSEST_N_NEIGHBORS = 50
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

def _load_electricity_by_year() -> pd.DataFrame:
    """Load electricity price CSV and return avg_electricity_price, electricity_year_trend per year."""
    df = pd.read_csv(ELECTRICITY_PRICE_PATH)
    # First row has data; columns are description, units, Jan-01, Feb-01, ..., Nov-25
    row = df.iloc[0]
    year_metrics = []
    for col in df.columns[2:]:  # skip description, units
        parts = col.split("-")
        if len(parts) == 2:
            month_abbr, yy = parts[0], int(parts[1])
            year = 2000 + yy if yy < 50 else 1900 + yy
            month_num = {
                "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
                "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12,
            }.get(month_abbr)
            if month_num is not None:
                try:
                    val = float(row[col])
                    year_metrics.append({"year": year, "month": month_num, "price": val})
                except (ValueError, TypeError):
                    pass
    monthly = pd.DataFrame(year_metrics)
    if monthly.empty:
        return pd.DataFrame(columns=["year", "avg_electricity_price", "electricity_year_trend"])

    by_year = monthly.groupby("year")
    avg_price = by_year["price"].mean()
    slopes = []
    for year, grp in by_year:
        grp = grp.sort_values("month")
        if len(grp) >= 2:
            x = grp["month"].values.astype(float)
            y = grp["price"].values.astype(float)
            slope = np.polyfit(x, y, 1)[0]
        else:
            slope = np.nan
        slopes.append({"year": year, "avg_electricity_price": avg_price[year], "electricity_year_trend": slope})
    return pd.DataFrame(slopes)


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

    # Roof permit years (before persistence) - years when a roof permit was actually pulled
    roof_permit_years = (
        result[result["roof_new_or_replace"] == 1]
        .groupby("strap")["year"]
        .apply(set)
        .to_dict()
    )

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
    last_year_neighbor_cols = [
        "last_year_neighbors_w_solar_0_05mi",
        "last_year_neighbors_w_solar_0_1mi",
        "last_year_neighbors_w_solar_0_25mi",
        "last_year_neighbors_w_solar_0_5mi",
        "last_year_neighbors_w_solar_1mi",
    ]
    for col in neighbor_cols:
        result[col] = 0
    for col in last_year_neighbor_cols:
        result[col] = 0
    result["closest_fifty_percentage"] = 0.0

    # first_solar_year: first year each strap has solar_pv=1 (for last_year_neighbors: "installed in prev year")
    first_solar_year = result[result["solar_pv"] == 1].groupby("strap")["year"].min()
    first_solar_year = first_solar_year.to_dict()

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

        # closest_fifty_percentage: % of 50 nearest neighbors that have solar (this year's snapshot)
        k = min(CLOSEST_N_NEIGHBORS + 1, len(valid_idx))
        _, neighbors_k_idx = tree.query(coords_rad, k=k)
        pct_solar = np.zeros(len(valid_idx), dtype=np.float64)
        for i in range(len(valid_idx)):
            others = neighbors_k_idx[i, 1:] if k > 1 else np.array([], dtype=int)
            n_others = len(others)
            if n_others > 0:
                pct_solar[i] = 100.0 * np.sum(solar_yes[others] == 1) / n_others

        year_counts = pd.DataFrame(
            {"strap": [regrid_strap[valid_idx[i]] for i in range(len(valid_idx))]}
        )
        for j, col in enumerate(neighbor_cols):
            year_counts[col] = counts[:, j]
        year_counts["closest_fifty_percentage"] = pct_solar.astype(np.float64)

        year_mask = result["year"] == year
        result_year = result.loc[year_mask].merge(
            year_counts, on="strap", how="left", suffixes=("_old", "")
        )
        for col in neighbor_cols:
            result.loc[year_mask, col] = result_year[col].fillna(0).astype(int).values
        result.loc[year_mask, "closest_fifty_percentage"] = (
            result_year["closest_fifty_percentage"].fillna(0).astype(np.float64).values
        )

        # last_year_neighbors_w_solar: count neighbors who INSTALLED solar in previous year (Y-1)
        # Use first_solar_year: only count straps whose first year with solar is Y-1 (then "removed" from future)
        prev_year = year - 1
        if prev_year >= YEAR_MIN:
            solar_yes_prev = np.array(
                [
                    1 if first_solar_year.get(str(regrid_strap[i])) == prev_year else 0
                    for i in valid_idx
                ],
                dtype=int,
            )
            counts_prev = np.zeros(
                (len(valid_idx), len(LAST_YEAR_NEIGHBOR_RADIUS_MILES)), dtype=int
            )
            for j, radius_mi in enumerate(LAST_YEAR_NEIGHBOR_RADIUS_MILES):
                radius_rad = radius_mi / EARTH_RADIUS_MILES
                neighbors_idx = tree.query_radius(coords_rad, r=radius_rad)
                for i in range(len(valid_idx)):
                    idx_list = neighbors_idx[i]
                    others = idx_list[idx_list != i]
                    counts_prev[i, j] = np.sum(solar_yes_prev[others] == 1)
            year_counts_prev = pd.DataFrame(
                {"strap": [regrid_strap[valid_idx[i]] for i in range(len(valid_idx))]}
            )
            for j, col in enumerate(last_year_neighbor_cols):
                year_counts_prev[col] = counts_prev[:, j]
            result_year_prev = result.loc[year_mask].merge(
                year_counts_prev, on="strap", how="left", suffixes=("_old", "")
            )
            for col in last_year_neighbor_cols:
                result.loc[year_mask, col] = (
                    result_year_prev[col].fillna(0).astype(int).values
                )

        print(f"  Year {year} done")

    for col in neighbor_cols + last_year_neighbor_cols:
        result[col] = result[col].fillna(0).astype(int)
    result["closest_fifty_percentage"] = result["closest_fifty_percentage"].fillna(0).astype(np.float64)

    # Join regrid_filtered (property attributes, same for each strap year after year)
    exclude = [c for c in REGRID_EXCLUDE_COLUMNS if c not in REGRID_REQUIRED_COLUMNS]
    regrid_join = regrid.drop(columns=exclude, errors="ignore")
    result = result.merge(regrid_join, on="strap", how="left")
    print(f"Joined regrid_filtered ({len(regrid_join.columns)} columns)")

    # calculated_roof_age: time-aware, permit-aware. Starts at year - calculated_build_year, resets to 0 when roof permit pulled, then increments.
    build_year = pd.to_numeric(result["calculated_build_year"], errors="coerce")

    def _roof_age_series(strap_rows: pd.DataFrame) -> pd.Series:
        strap = strap_rows["strap"].iloc[0]
        permit_years = roof_permit_years.get(str(strap), set())
        by = strap_rows["_build_year"].iloc[0]
        out = []
        prev_age = None
        for _, row in strap_rows.sort_values("year").iterrows():
            y = row["year"]
            if prev_age is None:
                prev_age = 0 if y in permit_years else (max(0, int(y - by)) if pd.notna(by) else 0)
            else:
                prev_age = 0 if y in permit_years else prev_age + 1
            out.append(prev_age)
        return pd.Series(out, index=strap_rows.index)

    result["_build_year"] = build_year
    result = result.sort_values(["strap", "year"])
    roof_age_series = result.groupby("strap", group_keys=False).apply(_roof_age_series)
    result["calculated_roof_age"] = roof_age_series.astype(np.int64)
    result.drop(columns=["_build_year"], inplace=True)
    print("Added calculated_roof_age (time-aware, permit-aware: resets to 0 when roof permit pulled)")

    # Join roof_score (on original_index from regrid)
    roof_score_df = pd.read_csv(ROOF_SCORE_PATH)
    result = result.merge(roof_score_df, on="original_index", how="left")
    null_count = result["roof_score"].isna().sum()
    roof_mean = result["roof_score"].mean()
    result["roof_score"] = result["roof_score"].fillna(roof_mean)
    print(f"Joined roof_score (filled {null_count} nulls with mean {roof_mean:.2f})")

    # Join electricity price metrics by year
    electricity_df = _load_electricity_by_year()
    result = result.merge(electricity_df, on="year", how="left")
    print(f"Joined electricity price metrics ({len(electricity_df)} years)")

    # Derived columns (year = current year for each row)
    sale_year = _parse_sale_year(result["saledate"])
    build_year = pd.to_numeric(result["calculated_build_year"], errors="coerce")

    result["time_since_sale"] = (result["year"] - sale_year).astype("Int64")
    result.loc[result["time_since_sale"] < 0, "time_since_sale"] = 10
    result["time_since_build"] = (result["year"] - build_year).astype("Int64")

    result["recent_build"] = (result["time_since_build"] <= 7).astype(int)

    saleprice = pd.to_numeric(result["saleprice"], errors="coerce")
    sqft = pd.to_numeric(result["sqft"], errors="coerce")
    mainfloorsf = pd.to_numeric(result["mainfloorsf"], errors="coerce")
    result["land_price_sqft"] = saleprice / sqft.replace(0, np.nan)
    result["building_price_sqft"] = saleprice / mainfloorsf.replace(0, np.nan)

    # recent_purchase: sale happened by this year AND within last RECENT_YEARS (sale_year in [year-5, year])
    min_year_purchase = result["year"] - RECENT_YEARS
    result["recent_purchase"] = (
        (sale_year <= result["year"])
        & (sale_year >= min_year_purchase)
        & sale_year.notna()
    ).astype(int)

    # electricity_use_proxy: weighted proxy for expected electricity use (area + heating/AC type + appliances)
    base_area = result["mainfloorsf"].fillna(result["area_building"])
    base_area = pd.to_numeric(base_area, errors="coerce").fillna(base_area.median()).clip(lower=100)
    heating_str = result["heatingdscr"].astype(str).str.upper() if "heatingdscr" in result.columns else pd.Series("", index=result.index)
    ac_str = result["acdscr"].astype(str).str.upper() if "acdscr" in result.columns else pd.Series("", index=result.index)
    electric_heating = ((heating_str.str.contains("ELECTRIC|HEAT PUMP", na=False)) | (result["heat_pump"] == 1)).astype(int)
    central_ac = ((ac_str.str.contains("WHOLE HOUSE", na=False)) | (result["ac"] == 1)).astype(int)
    evaporative = ((ac_str.str.contains("EVAPORATIVE", na=False)) | (result["evaporative_cooler"] == 1)).astype(int)
    result["electricity_use_proxy"] = (
        base_area
        * (
            1.0
            + 0.15 * electric_heating
            + 0.25 * central_ac
            + 0.05 * evaporative
            + 0.20 * result["pool_hot_tub"].fillna(0)
            + 0.30 * result["ev_charger"].fillna(0)
            + 0.10 * result["battery"].fillna(0)
            + 0.10 * result["water_heater_electric"].fillna(0)
        )
    ).astype(np.float64)
    print("Added electricity_use_proxy (area × load factors: electric heat, AC, pool, EV, battery, etc.)")

    # likely_mortgage_rate: time-aware. Starts at 2012 rate, drops when national rate falls >0.75 pct, resets on sale year.
    REFI_THRESHOLD = 0.75
    if AVG_YEARLY_INTEREST_PATH.exists():
        rates_df = pd.read_csv(AVG_YEARLY_INTEREST_PATH)
        rates = rates_df.set_index("year")["average_rate"].to_dict()
        years_sorted = sorted(rates.keys())
        rate_median = rates_df["average_rate"].median()

        def _likely_rate_series(strap_rows: pd.DataFrame) -> pd.Series:
            sy = strap_rows["_sale_year"].iloc[0]
            out = []
            prev_likely = None
            for _, row in strap_rows.sort_values("year").iterrows():
                y = row["year"]
                r = rates.get(y, np.nan)
                if pd.isna(r):
                    r = rate_median
                if prev_likely is None:
                    prev_likely = r
                elif pd.notna(sy) and y == int(sy):
                    prev_likely = r
                elif r <= prev_likely - REFI_THRESHOLD:
                    prev_likely = r
                out.append(prev_likely)
            return pd.Series(out, index=strap_rows.index)

        result["_sale_year"] = sale_year
        result = result.sort_values(["strap", "year"])
        likely_series = result.groupby("strap", group_keys=False).apply(
            _likely_rate_series, include_groups=False
        )
        result["likely_mortgage_rate"] = likely_series
        result.drop(columns=["_sale_year"], inplace=True)
        result["likely_mortgage_rate"] = result["likely_mortgage_rate"].fillna(rate_median).astype(np.float64)
        print(f"Added likely_mortgage_rate (time-aware, refi threshold {REFI_THRESHOLD} pct)")
    else:
        result["likely_mortgage_rate"] = np.nan

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
