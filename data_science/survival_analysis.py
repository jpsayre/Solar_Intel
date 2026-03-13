#!/usr/bin/env python3
"""
Survival analysis for solar panel adoption using discrete-time hazard modeling.

Instead of binary "installs next year", models time-to-adoption as a survival problem.
Each property enters the risk set in 2012 and either adopts solar (event) or is censored.

Uses:
  - Cox Proportional Hazards (via lifelines)
  - Discrete-time logistic hazard model (pooled logistic regression)

Outputs survival curves, hazard ratios, and risk scores for targeting.
"""

from __future__ import annotations

import os
import warnings
from datetime import datetime
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", str(Path(__file__).resolve().parent / ".mplconfig"))
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from lifelines import CoxPHFitter
from lifelines.utils import concordance_index
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.preprocessing import StandardScaler

warnings.filterwarnings("ignore")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_PATH = PROJECT_ROOT / "data" / "working" / "data_science_input.csv"
AVG_YEARLY_INTEREST_PATH = PROJECT_ROOT / "data" / "final" / "avg_yearly_interest.csv"
OUTPUT_DIR = PROJECT_ROOT / "data_science" / "output" / "survival"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

YEAR_START = 2012
YEAR_END = 2025
RANDOM_STATE = 42
TEST_STRAP_FRACTION = 0.2

# Features to use (static + time-varying)
STATIC_FEATURES = [
    "mainfloorsf", "sqft", "saleprice", "calculated_build_year",
    "roof_score", "yearbuilt",
    "median_household_income", "median_home_value", "median_age",
    "pct_college_educated", "pct_owner_occupied", "pct_family_households",
    "pct_multi_vehicle", "income_per_sqft", "home_value_to_income",
]

TIME_VARYING_FEATURES = [
    "closest_fifty_percentage", "count_0_1mi", "count_0_25mi",
    "solar_neighbor_momentum", "neighbor_solar_slope_3yr",
    "permit_velocity_3yr", "calculated_roof_age",
    "avg_electricity_price", "electricity_use_proxy",
    "est_annual_electricity_cost", "likely_mortgage_rate",
    "time_since_sale", "recent_purchase",
]

LOG_COLS = ["mainfloorsf", "sqft", "saleprice", "median_household_income",
            "median_home_value", "income_per_sqft", "electricity_use_proxy",
            "est_annual_electricity_cost"]

EXCLUDE_FEATURES = [
    "strap", "year", "solar_pv", "solar_next_year", "original_index",
    "saledate", "owner", "mailadd",
]


def load_and_prepare() -> pd.DataFrame:
    """Load data and create survival analysis format."""
    df = pd.read_csv(DATA_PATH)
    df = df[df["year"].between(YEAR_START, YEAR_END)]

    if AVG_YEARLY_INTEREST_PATH.exists():
        interest = pd.read_csv(AVG_YEARLY_INTEREST_PATH)
        if "average_rate" not in df.columns:
            df = df.merge(interest, on="year", how="left")

    # Determine event time: first year with solar_pv=1 (or solar_next_year=1 means event next year)
    df = df.sort_values(["strap", "year"])

    # For each strap: duration = years from YEAR_START to event (or censoring)
    # Event = first year solar_pv == 1
    first_solar = df[df["solar_pv"] == 1].groupby("strap")["year"].min().reset_index()
    first_solar.columns = ["strap", "event_year"]

    strap_info = df.groupby("strap").agg(
        first_year=("year", "min"),
        last_year=("year", "max"),
    ).reset_index()
    strap_info = strap_info.merge(first_solar, on="strap", how="left")

    # Duration: time from entry to event or censoring
    strap_info["duration"] = np.where(
        strap_info["event_year"].notna(),
        strap_info["event_year"] - strap_info["first_year"],
        strap_info["last_year"] - strap_info["first_year"],
    ).astype(int)
    strap_info["event"] = strap_info["event_year"].notna().astype(int)
    # Minimum duration of 1
    strap_info["duration"] = strap_info["duration"].clip(lower=1)

    return df, strap_info


def run_cox_ph(strap_info: pd.DataFrame, df: pd.DataFrame) -> None:
    """Run Cox Proportional Hazards model on static features."""
    print("=" * 60)
    print("Cox Proportional Hazards (static features)")
    print("=" * 60)

    # Get static features: use the latest available year per strap
    latest = df.sort_values("year").groupby("strap").last().reset_index()
    cox_df = strap_info[["strap", "duration", "event"]].merge(latest, on="strap", how="left")

    # Select features
    feature_cols = [c for c in STATIC_FEATURES if c in cox_df.columns]
    cox_data = cox_df[["duration", "event"] + feature_cols].copy()

    # Log transform
    for c in LOG_COLS:
        if c in cox_data.columns:
            cox_data[c] = np.log1p(cox_data[c].clip(lower=0))

    # Fill missing
    for c in feature_cols:
        cox_data[c] = cox_data[c].fillna(cox_data[c].median())

    # Train/test split by strap
    straps = cox_df["strap"].unique()
    np.random.seed(RANDOM_STATE)
    np.random.shuffle(straps)
    n_test = max(1, int(len(straps) * TEST_STRAP_FRACTION))
    test_straps = set(straps[:n_test])

    train_mask = ~cox_df["strap"].isin(test_straps)
    test_mask = cox_df["strap"].isin(test_straps)
    train_data = cox_data[train_mask.values].reset_index(drop=True)
    test_data = cox_data[test_mask.values].reset_index(drop=True)

    # Fit Cox PH
    cph = CoxPHFitter(penalizer=0.1)
    cph.fit(train_data, duration_col="duration", event_col="event")

    print("\nCox PH Summary (top features by |coef|):")
    summary = cph.summary.sort_values("coef", key=abs, ascending=False)
    print(summary[["coef", "exp(coef)", "p"]].head(15).to_string())

    # Concordance index on test set
    c_index_train = cph.concordance_index_
    c_index_test = concordance_index(
        test_data["duration"], -cph.predict_partial_hazard(test_data), test_data["event"]
    )
    print(f"\nConcordance Index: train={c_index_train:.4f}, test={c_index_test:.4f}")

    # Hazard ratios plot
    fig, ax = plt.subplots(figsize=(10, 6))
    cph.plot(ax=ax)
    ax.set_title("Cox PH Hazard Ratios (exp(coef))")
    plt.tight_layout()
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    plt.savefig(OUTPUT_DIR / f"cox_hazard_ratios_{ts}.png", dpi=150)
    plt.close()
    print(f"Saved: {OUTPUT_DIR / f'cox_hazard_ratios_{ts}.png'}")

    # Survival curves for high vs low risk
    risk_scores = cph.predict_partial_hazard(test_data).values.flatten()
    median_risk = float(np.median(risk_scores))
    high_risk = test_data[risk_scores >= median_risk]
    low_risk = test_data[risk_scores < median_risk]

    fig, ax = plt.subplots(figsize=(10, 6))
    from lifelines import KaplanMeierFitter
    kmf = KaplanMeierFitter()
    kmf.fit(high_risk["duration"], high_risk["event"], label="High adoption propensity")
    kmf.plot_survival_function(ax=ax)
    kmf.fit(low_risk["duration"], low_risk["event"], label="Low adoption propensity")
    kmf.plot_survival_function(ax=ax)
    ax.set_xlabel("Years from 2012")
    ax.set_ylabel("Survival (no solar)")
    ax.set_title("Kaplan-Meier: High vs Low Adoption Propensity")
    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / f"km_survival_curves_{ts}.png", dpi=150)
    plt.close()
    print(f"Saved: {OUTPUT_DIR / f'km_survival_curves_{ts}.png'}")

    return cph


def run_discrete_time_hazard(df: pd.DataFrame, strap_info: pd.DataFrame) -> None:
    """Run discrete-time hazard model (pooled logistic regression with time-varying covariates)."""
    print("\n" + "=" * 60)
    print("Discrete-Time Hazard Model (time-varying features)")
    print("=" * 60)

    # Create person-period dataset: one row per strap per year, up to event or censoring
    # For each strap: include rows from first_year to event_year (or last observed year)
    event_info = strap_info.set_index("strap")[["event_year", "event"]].to_dict("index")

    # Filter: only keep rows up to and including the event year (or all rows if censored)
    records = []
    for strap, info in event_info.items():
        strap_rows = df[df["strap"] == strap].sort_values("year")
        ey = info["event_year"]
        for _, row in strap_rows.iterrows():
            y = row["year"]
            if pd.notna(ey) and y > ey:
                break  # past event year
            hazard_event = 1 if (pd.notna(ey) and y == ey) else 0
            records.append({**row.to_dict(), "hazard_event": hazard_event})

    pp_df = pd.DataFrame(records)
    print(f"Person-period dataset: {len(pp_df)} rows, {pp_df['hazard_event'].sum()} events")

    # Features
    all_features = STATIC_FEATURES + TIME_VARYING_FEATURES
    feature_cols = [c for c in all_features if c in pp_df.columns]

    # Add time-at-risk as a feature
    pp_df["time_at_risk"] = pp_df["year"] - YEAR_START

    feature_cols.append("time_at_risk")

    # Log transform
    for c in LOG_COLS:
        if c in pp_df.columns:
            pp_df[c] = np.log1p(pp_df[c].clip(lower=0))

    # Fill missing
    for c in feature_cols:
        if c in pp_df.columns:
            pp_df[c] = pd.to_numeric(pp_df[c], errors="coerce")
            pp_df[c] = pp_df[c].fillna(pp_df[c].median())

    # Train/test split by strap
    straps = pp_df["strap"].unique()
    np.random.seed(RANDOM_STATE)
    np.random.shuffle(straps)
    n_test = max(1, int(len(straps) * TEST_STRAP_FRACTION))
    test_straps = set(straps[:n_test])

    train_pp = pp_df[~pp_df["strap"].isin(test_straps)]
    test_pp = pp_df[pp_df["strap"].isin(test_straps)]

    X_train = train_pp[feature_cols].values
    y_train = train_pp["hazard_event"].values
    X_test = test_pp[feature_cols].values
    y_test = test_pp["hazard_event"].values

    # Scale
    scaler = StandardScaler()
    X_train = scaler.fit_transform(X_train)
    X_test = scaler.transform(X_test)

    print(f"Train: {len(y_train)} person-periods, {y_train.sum()} events")
    print(f"Test: {len(y_test)} person-periods, {y_test.sum()} events")

    # Fit pooled logistic regression
    lr = LogisticRegression(
        max_iter=2000, C=0.1, solver="saga", penalty="l1",
        class_weight="balanced", random_state=RANDOM_STATE,
    )
    lr.fit(X_train, y_train)
    y_prob = lr.predict_proba(X_test)[:, 1]

    roc = roc_auc_score(y_test, y_prob) if len(np.unique(y_test)) > 1 else 0
    print(f"ROC-AUC: {roc:.4f}")

    # Feature importance
    coefs = pd.DataFrame({
        "feature": feature_cols,
        "coef": lr.coef_[0],
        "abs_coef": np.abs(lr.coef_[0]),
        "hazard_ratio": np.exp(lr.coef_[0]),
    }).sort_values("abs_coef", ascending=False)
    print("\nTop features (hazard ratios):")
    print(coefs.head(20).to_string(index=False))

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    coefs.to_csv(OUTPUT_DIR / f"discrete_hazard_coefficients_{ts}.csv", index=False)

    # Lift analysis on test set (last year only for comparability with walk-forward)
    last_year_mask = test_pp["year"].values == YEAR_END
    if last_year_mask.sum() > 0:
        y_last = y_test[last_year_mask]
        prob_last = y_prob[last_year_mask]
        n = len(y_last)
        n_pos = y_last.sum()
        baseline = y_last.mean()
        if n_pos > 0 and baseline > 0:
            order = np.argsort(prob_last)[::-1]
            for pct, label in [(0.05, "5%"), (0.10, "10%"), (0.20, "20%")]:
                k = max(1, int(n * pct))
                rate_top = y_last[order[:k]].mean()
                lift = rate_top / baseline
                capture = y_last[order[:k]].sum() / n_pos
                print(f"  Top {label}: lift={lift:.2f}x, capture={capture:.1%}")

    # Feature importance plot
    top_n = min(20, len(coefs))
    fig, ax = plt.subplots(figsize=(10, 6))
    top = coefs.head(top_n).sort_values("abs_coef")
    colors = ["#e74c3c" if c > 0 else "#3498db" for c in top["coef"].values]
    ax.barh(top["feature"], top["coef"], color=colors)
    ax.set_xlabel("Coefficient (positive = increases adoption hazard)")
    ax.set_title("Discrete-Time Hazard Model: Feature Coefficients")
    ax.grid(True, alpha=0.3, axis="x")
    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / f"discrete_hazard_features_{ts}.png", dpi=150)
    plt.close()
    print(f"Saved: {OUTPUT_DIR / f'discrete_hazard_features_{ts}.png'}")

    # Risk score output for all straps (latest year)
    latest_pp = pp_df[pp_df["year"] == pp_df.groupby("strap")["year"].transform("max")]
    X_all = scaler.transform(latest_pp[feature_cols].values)
    risk_scores = lr.predict_proba(X_all)[:, 1]
    risk_df = pd.DataFrame({
        "strap": latest_pp["strap"].values,
        "survival_risk_score": risk_scores,
    })
    # Only non-adopters
    adopters = set(strap_info[strap_info["event"] == 1]["strap"])
    risk_df = risk_df[~risk_df["strap"].isin(adopters)]
    risk_df = risk_df.sort_values("survival_risk_score", ascending=False)
    risk_df.to_csv(OUTPUT_DIR / f"survival_risk_scores_{ts}.csv", index=False)
    print(f"Saved risk scores for {len(risk_df)} non-adopter straps")


def main():
    print("Loading data...")
    df, strap_info = load_and_prepare()
    print(f"Loaded {len(strap_info)} straps: {strap_info['event'].sum()} adopted, "
          f"{(~strap_info['event'].astype(bool)).sum()} censored")
    print(f"Median duration: {strap_info['duration'].median():.0f} years")

    cph = run_cox_ph(strap_info, df)
    run_discrete_time_hazard(df, strap_info)

    print(f"\nAll outputs saved to {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
