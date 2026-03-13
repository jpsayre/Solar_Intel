"""
Create data_science_input.csv from parsed_permits.csv.

Builds a strap × year panel for ML modeling:
- Aggregates permits by strap and year (max of each binary column per year)
- Fills missing years (2012-2026) per strap with 0s
- Applies configurable persistence (e.g. solar ~25yr, roof ~7yr)
- Computes spatial neighbor features (BallTree at multiple radii)
- Joins regrid, census, roof_score, electricity, interest rate data
- Adds derived features: calculated_roof_age, electricity_use_proxy, likely_mortgage_rate, etc.

Usage:
    python src/create_data_science_input.py --config boulder_co

Input:  parsed_permits.csv (from parse_permits.py)
Output: data_science_input.csv (one row per strap × year)
"""

import re
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.neighbors import BallTree

_PROJECT_ROOT = Path(__file__).resolve().parents[1]

# Default paths (used when no config provided)
_DEFAULTS = {
    "INPUT_PATH": _PROJECT_ROOT / "data" / "final" / "parsed_permits.csv",
    "OUTPUT_PATH": _PROJECT_ROOT / "data" / "working" / "data_science_input.csv",
    "REGRID_FILTERED_PATH": _PROJECT_ROOT / "data" / "final" / "regrid_filtered.csv",
    "ROOF_SCORE_PATH": _PROJECT_ROOT / "data" / "final" / "roof_score.csv",
    "STRAP_CENSUS_LOOKUP_PATH": _PROJECT_ROOT / "data" / "final" / "strap_census_lookup.csv",
    "ELECTRICITY_PRICE_PATH": _PROJECT_ROOT / "data" / "raw" / "Average_retail_price_of_electricity.csv",
    "AVG_YEARLY_INTEREST_PATH": _PROJECT_ROOT / "data" / "final" / "avg_yearly_interest.csv",
    "YEAR_MIN": 2012,
    "YEAR_MAX": 2026,
}


def _get_paths(config=None):
    if config:
        paths = {
            "INPUT_PATH": config.parsed_permits_path,
            "OUTPUT_PATH": config.data_science_input_path,
            "REGRID_FILTERED_PATH": config.regrid_filtered_path,
            "ROOF_SCORE_PATH": config.roof_score_path,
            "STRAP_CENSUS_LOOKUP_PATH": config.strap_census_lookup_path,
            "ELECTRICITY_PRICE_PATH": Path(config.electricity_csv),
            "AVG_YEARLY_INTEREST_PATH": config.avg_yearly_interest_path,
            "YEAR_MIN": config.year_min,
            "YEAR_MAX": config.year_max,
        }
        # Interest rates are national (FRED), not county-specific — fall back to shared path
        if not Path(paths["AVG_YEARLY_INTEREST_PATH"]).exists():
            shared = Path(__file__).resolve().parents[1] / "data" / "final" / "avg_yearly_interest.csv"
            if shared.exists():
                paths["AVG_YEARLY_INTEREST_PATH"] = shared
                print(f"Note: using shared interest rate file at {shared}")
        return paths
    return _DEFAULTS

# Allowlist: only these Regrid columns are joined into the strap-year panel.
# This keeps the feature set consistent across counties and avoids leaking IDs/addresses.
# Matches the Boulder County output columns.
REGRID_ALLOW_COLUMNS = [
    "strap",
    "original_index",       # needed for roof_score join
    "yearbuilt",
    "saleprice",
    "saledate",
    "area_building",
    "sqft",
    "carstoragetypedscr",   # garage type (Boulder-specific, may be missing)
    "acdscr",               # AC description (Boulder-specific, may be missing)
    "heatingdscr",          # heating description (Boulder-specific, may be missing)
    "mainfloorsf",          # main floor sqft (Boulder-specific, may be missing)
    "year_built_effective_date",  # used with yearbuilt to derive calculated_build_year
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

def _load_electricity_by_year(electricity_path=None) -> pd.DataFrame:
    """Load electricity price CSV and return avg_electricity_price, electricity_year_trend per year."""
    path = electricity_path or _DEFAULTS["ELECTRICITY_PRICE_PATH"]
    df = pd.read_csv(path)
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
    """Parse saledate to integer year. Returns NaN where unparseable.
    Handles both M/D/YY and YYYY-MM-DD formats."""

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
            # Detect YYYY-MM-DD: first part is 4-digit year
            first = int(float(parts[0])) if parts[0] else 0
            if first >= 1900:
                return first if first <= 2100 else np.nan
            # Otherwise assume M/D/YY or M/D/YYYY: year is last part
            y = int(float(parts[-1])) if parts[-1] else np.nan
            if pd.isna(y):
                return np.nan
            if y < 100:
                y = 2000 + y if y < 50 else 1900 + y
            return y if 1900 <= y <= 2100 else np.nan
        except (ValueError, IndexError):
            return np.nan

    return s.map(one)


from parse_permits_features import get_feature_names
BINARY_COLUMNS = get_feature_names()


def main(config=None):
    p = _get_paths(config)
    YEAR_MIN = p["YEAR_MIN"]
    YEAR_MAX = p["YEAR_MAX"]
    strap_col = config.strap_column if config else "alt_parcelnumb1"

    if config:
        config.ensure_dirs()

    regrid = pd.read_csv(p["REGRID_FILTERED_PATH"])
    regrid["strap"] = regrid[strap_col].astype(str)
    regrid = regrid.dropna(subset=["strap"])
    regrid = regrid.drop_duplicates(subset=["strap"], keep="first")
    filtered_straps = set(regrid["strap"].unique())
    print(f"Filtering to {len(filtered_straps)} straps from {Path(p['REGRID_FILTERED_PATH']).name} ({strap_col})")

    df = pd.read_csv(p["INPUT_PATH"])
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

    # Save raw (pre-persistence) binary columns for permit velocity
    NON_SOLAR_BINARY = [c for c in BINARY_COLUMNS if c != "solar_pv"]
    result_raw_permits = result[["strap", "year"] + NON_SOLAR_BINARY].copy()

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

    # Find first year with any solar permit — skip neighbor computation for earlier years
    any_solar_mask = result.groupby("year")["solar_pv"].max()
    first_solar_year_global = int(any_solar_mask[any_solar_mask > 0].index.min()) if (any_solar_mask > 0).any() else YEAR_MAX
    # Start 1 year before first solar so last_year_neighbors captures it
    neighbor_start_year = max(YEAR_MIN, first_solar_year_global - 1)
    n_skip = neighbor_start_year - YEAR_MIN
    if n_skip > 0:
        print(f"Skipping neighbor computation for years {YEAR_MIN}-{neighbor_start_year - 1} (no solar permits)")

    print(f"Computing neighbors_w_solar by year at {NEIGHBOR_RADIUS_MILES} mi ...")
    for year in range(neighbor_start_year, YEAR_MAX + 1):
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

    # Temporal momentum: year-over-year change and 3-year slope of closest_fifty_percentage
    result = result.sort_values(["strap", "year"])
    result["solar_neighbor_momentum"] = result.groupby("strap")["closest_fifty_percentage"].diff().fillna(0)
    result["neighbor_solar_slope_3yr"] = (
        result.groupby("strap")["closest_fifty_percentage"]
        .transform(lambda x: x.rolling(3, min_periods=2).apply(
            lambda w: np.polyfit(range(len(w)), w, 1)[0] if len(w) >= 2 else 0, raw=False
        ))
        .fillna(0)
    )
    print("Added temporal momentum features (solar_neighbor_momentum, neighbor_solar_slope_3yr)")

    # Permit velocity: count of distinct non-solar permit types pulled in last 3 years (pre-persistence)
    PERMIT_VELOCITY_YEARS = 3
    result_raw_permits = result_raw_permits.sort_values(["strap", "year"])
    result_raw_permits["_any_permit"] = result_raw_permits[NON_SOLAR_BINARY].sum(axis=1)
    result_raw_permits["permit_velocity_3yr"] = (
        result_raw_permits.groupby("strap")["_any_permit"]
        .transform(lambda x: x.rolling(PERMIT_VELOCITY_YEARS, min_periods=1).sum())
        .fillna(0)
        .astype(int)
    )
    result = result.merge(
        result_raw_permits[["strap", "year", "permit_velocity_3yr"]],
        on=["strap", "year"],
        how="left",
    )
    result["permit_velocity_3yr"] = result["permit_velocity_3yr"].fillna(0).astype(int)
    print(f"Added permit_velocity_3yr (non-solar permits in last {PERMIT_VELOCITY_YEARS} years)")

    # Join regrid_filtered (allowlist only — consistent across counties, no IDs/addresses)
    regrid_keep = [c for c in REGRID_ALLOW_COLUMNS if c in regrid.columns]
    regrid_missing = [c for c in REGRID_ALLOW_COLUMNS if c not in regrid.columns and c != "strap"]
    if regrid_missing:
        print(f"  Note: {len(regrid_missing)} allowlisted Regrid columns not in data: {regrid_missing}")
    regrid_join = regrid[regrid_keep]
    result = result.merge(regrid_join, on="strap", how="left")
    print(f"Joined regrid_filtered ({len(regrid_keep)} allowlisted columns)")

    # Derive calculated_build_year = max(yearbuilt, year_built_effective_date)
    if "yearbuilt" in result.columns:
        yb = pd.to_numeric(result["yearbuilt"], errors="coerce")
        ybe = pd.to_numeric(result.get("year_built_effective_date", np.nan), errors="coerce")
        result["calculated_build_year"] = pd.concat([yb, ybe], axis=1).max(axis=1)
        print(f"Derived calculated_build_year from yearbuilt + year_built_effective_date")

    # Join census demographics (static per strap, from enrich_census.py --export-strap-lookup)
    if Path(p["STRAP_CENSUS_LOOKUP_PATH"]).exists():
        census_df = pd.read_csv(p["STRAP_CENSUS_LOOKUP_PATH"])
        census_df["strap"] = census_df["strap"].astype(str)
        census_cols = [c for c in census_df.columns if c != "strap"]
        result = result.merge(census_df, on="strap", how="left")
        # Fill NaN census values with column medians
        for col in census_cols:
            if col in result.columns:
                median_val = result[col].median()
                null_count = result[col].isna().sum()
                result[col] = result[col].fillna(median_val)
        # Derived census features
        _sf_col = "mainfloorsf" if "mainfloorsf" in result.columns else "area_building"
        main_sf = pd.to_numeric(result[_sf_col], errors="coerce")
        result["income_per_sqft"] = (
            result["median_household_income"] / main_sf.replace(0, np.nan)
        )
        result["income_per_sqft"] = result["income_per_sqft"].fillna(
            result["income_per_sqft"].median()
        )
        result["home_value_to_income"] = (
            result["median_home_value"]
            / result["median_household_income"].replace(0, np.nan)
        )
        result["home_value_to_income"] = result["home_value_to_income"].fillna(
            result["home_value_to_income"].median()
        )
        build_yr = pd.to_numeric(result["calculated_build_year"], errors="coerce")
        result["census_vs_property_age"] = result["median_year_built"] - build_yr
        result["census_vs_property_age"] = result["census_vs_property_age"].fillna(0)
        print(f"Joined census demographics ({len(census_cols)} + 3 derived columns, "
              f"filled nulls with medians)")
    else:
        print(f"Warning: {Path(p['STRAP_CENSUS_LOOKUP_PATH']).name} not found, skipping census join. "
              f"Run: python src/enrich_census.py --export-strap-lookup")

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

    # Join roof_score (on original_index from regrid) — skip if too few scores
    roof_score_path = Path(p["ROOF_SCORE_PATH"])
    if roof_score_path.exists():
        roof_score_df = pd.read_csv(roof_score_path)
        n_scores = len(roof_score_df)
        n_straps = result["strap"].nunique()
        coverage = n_scores / n_straps if n_straps > 0 else 0
        if coverage >= 0.10:  # need at least 10% coverage to be useful
            result = result.merge(roof_score_df, on="original_index", how="left")
            null_count = result["roof_score"].isna().sum()
            roof_mean = result["roof_score"].mean()
            result["roof_score"] = result["roof_score"].fillna(roof_mean)
            print(f"Joined roof_score ({n_scores:,} scores, {coverage:.1%} coverage, filled {null_count:,} nulls with mean {roof_mean:.2f})")
        else:
            result["roof_score"] = np.nan
            print(f"Skipped roof_score: only {n_scores:,} scores for {n_straps:,} straps ({coverage:.1%} coverage — need >=10%)")
    else:
        result["roof_score"] = np.nan
        print(f"Skipped roof_score: {roof_score_path.name} not found")

    # Join electricity price metrics by year — validate state matches
    electricity_path = Path(p["ELECTRICITY_PRICE_PATH"])
    if electricity_path.exists():
        state_abbrev = config.state_abbrev if config else "CO"
        # Read first data row to check state
        _elec_check = pd.read_csv(electricity_path, nrows=1)
        elec_desc = str(_elec_check.iloc[0, 0]) if len(_elec_check) > 0 else ""
        if state_abbrev.upper() in elec_desc.upper() or state_abbrev == "CO":
            electricity_df = _load_electricity_by_year(electricity_path=electricity_path)
            result = result.merge(electricity_df, on="year", how="left")
            print(f"Joined electricity price metrics ({len(electricity_df)} years, source: {elec_desc.strip()})")
        else:
            print(f"Skipped electricity data: file is for '{elec_desc.strip()}', not {state_abbrev}. "
                  f"Set electricity_csv in config to a {state_abbrev}-specific file.")
    else:
        print(f"Skipped electricity data: {electricity_path.name} not found")

    # Derived columns (year = current year for each row)
    sale_year = _parse_sale_year(result["saledate"])
    build_year = pd.to_numeric(result["calculated_build_year"], errors="coerce")

    result["time_since_sale"] = (result["year"] - sale_year).astype("Int64")
    result.loc[result["time_since_sale"] < 0, "time_since_sale"] = pd.NA
    result["time_since_build"] = (result["year"] - build_year).astype("Int64")

    result["recent_build"] = (result["time_since_build"] <= 7).astype(int)

    saleprice = pd.to_numeric(result["saleprice"], errors="coerce")
    sqft = pd.to_numeric(result["sqft"], errors="coerce")
    _sf_col = "mainfloorsf" if "mainfloorsf" in result.columns else "area_building"
    building_sf = pd.to_numeric(result[_sf_col], errors="coerce")
    result["land_price_sqft"] = saleprice / sqft.replace(0, np.nan)
    result["building_price_sqft"] = saleprice / building_sf.replace(0, np.nan)

    # recent_purchase: sale happened by this year AND within last RECENT_YEARS (sale_year in [year-5, year])
    min_year_purchase = result["year"] - RECENT_YEARS
    result["recent_purchase"] = (
        (sale_year <= result["year"])
        & (sale_year >= min_year_purchase)
        & sale_year.notna()
    ).astype(int)

    # electricity_use_proxy: weighted proxy for expected electricity use (area + heating/AC type + appliances)
    _sf_col2 = "mainfloorsf" if "mainfloorsf" in result.columns else "area_building"
    base_area = result[_sf_col2] if _sf_col2 == "area_building" else result["mainfloorsf"].fillna(result.get("area_building", 0))
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

    # Estimated annual electricity cost: proxy × price (higher = stronger solar ROI)
    if "avg_electricity_price" in result.columns:
        result["est_annual_electricity_cost"] = (
            result["electricity_use_proxy"] * result["avg_electricity_price"]
        ).fillna(0).astype(np.float64)
        print("Added est_annual_electricity_cost (electricity_use_proxy × avg_electricity_price)")

    # likely_mortgage_rate: time-aware. Starts at 2012 rate, drops when national rate falls >0.75 pct, resets on sale year.
    REFI_THRESHOLD = 0.75
    if Path(p["AVG_YEARLY_INTEREST_PATH"]).exists():
        rates_df = pd.read_csv(p["AVG_YEARLY_INTEREST_PATH"])
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

    # Trim years before any permit data exists (saves disk and model load time)
    # Keep 1 year before first solar for solar_next_year=1 labeling
    min_output_year = max(YEAR_MIN, first_solar_year_global - 1) if first_solar_year_global < YEAR_MAX else YEAR_MIN
    rows_before = len(result)
    result = result[result["year"] >= min_output_year]
    if len(result) < rows_before:
        print(f"Trimmed output to years {min_output_year}-{YEAR_MAX} ({rows_before - len(result):,} rows dropped)")

    output_path = p["OUTPUT_PATH"]
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(output_path, index=False)
    print(f"Wrote {len(result):,} rows to {output_path}")


def run(config):
    """Pipeline entry point."""
    main(config=config)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", help="County config name or path")
    args = parser.parse_args()

    if args.config:
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from pipeline_config import load_config
        main(config=load_config(args.config))
    else:
        main()
