#!/usr/bin/env python3
"""
Score ALL homes (including solar adopters) and show decile distribution of installs.

Uses 5-fold cross-validation on straps so every home gets an out-of-sample score.
For each fold: train GB on 80% of straps, score the remaining 20%.
Then show where homes that installed solar fall across score deciles.
"""

import os
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", str(Path(__file__).resolve().parent / ".mplconfig"))
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.preprocessing import StandardScaler, OneHotEncoder
from sklearn.compose import ColumnTransformer

# Import shared functions from walk_forward_modeling
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from walk_forward_modeling import (
    load_data, get_feature_columns, prepare_features, get_feature_types,
    fit_preprocessor, RANDOM_STATE, TRAIN_YEARS_WINDOW, INTERACTION_PAIRS,
    LOG_TRANSFORM_COLS, FEATURE_MIN_SAMPLES, FEATURE_MIN_SAMPLES_EXEMPT,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = PROJECT_ROOT / "data_science" / "output" / "walk_forward"
TUNED_PATH = PROJECT_ROOT / "data_science" / "tuned_params.json"


def main():
    import json

    # Load tuned params
    tuned = {}
    if TUNED_PATH.exists():
        with open(TUNED_PATH) as f:
            raw = json.load(f)
        for k, v in raw.items():
            if "params" in v:
                tuned[k] = v
            else:
                tuned[k] = {"params": v}

    gb_params = tuned.get("gb", {}).get("params", {})

    # Load data
    df = load_data()
    feature_cols = get_feature_columns(df)

    # Use the most recent feature year (2025) — all homes as of this snapshot
    feature_year = df["year"].max()
    print(f"Using feature year {feature_year}")

    # Get all homes at this feature year
    df_year = df[df["year"] == feature_year].copy()
    print(f"Total homes in {feature_year}: {len(df_year)}")

    # Identify solar adopters: solar_pv == 1 OR solar_next_year == 2 at this year
    # solar_next_year == 2 means already have solar
    # solar_pv == 1 means has solar this year
    has_solar = (df_year["solar_pv"] == 1) | (df_year.get("solar_next_year", pd.Series(dtype=int)) == 2)
    n_solar = has_solar.sum()
    print(f"Homes with solar: {n_solar}")
    print(f"Homes without solar: {(~has_solar).sum()}")

    # 5-fold CV on straps for out-of-sample scoring
    all_straps = df_year["strap"].unique()
    rng = np.random.RandomState(RANDOM_STATE)
    rng.shuffle(all_straps)
    n_folds = 5
    fold_assignments = np.array_split(all_straps, n_folds)

    # For training, use recent years (matching walk-forward's rolling window)
    if TRAIN_YEARS_WINDOW is not None:
        train_years = list(range(feature_year - TRAIN_YEARS_WINDOW, feature_year + 1))
    else:
        train_years = sorted(df["year"].unique())
    train_years = [y for y in train_years if y in df["year"].unique()]
    print(f"Training years: {train_years}")

    # For training, exclude solar_next_year == 2 (already have solar) — same as walk-forward
    df_trainable = df[
        (df["year"].isin(train_years)) &
        (df["solar_next_year"].isin([0, 1]))
    ].copy()

    all_scores = []

    for fold_i in range(n_folds):
        test_straps = set(fold_assignments[fold_i])
        train_straps = set(all_straps) - test_straps

        # Train set: all trainable rows for train straps
        train_df = df_trainable[df_trainable["strap"].isin(train_straps)]
        # Test set: feature_year rows for test straps (ALL homes, including solar)
        test_df = df_year[df_year["strap"].isin(test_straps)]

        y_train = train_df["solar_next_year"].astype(int).values

        # Compute train medians
        train_medians = {}
        for c in feature_cols:
            if train_df[c].dtype in (np.float64, np.int64, "float64", "int64", "Int64"):
                med = train_df[c].median()
                if pd.notna(med):
                    train_medians[c] = float(med)

        X_train_raw = prepare_features(train_df, feature_cols, train_medians=train_medians)
        X_test_raw = prepare_features(test_df, feature_cols, train_medians=train_medians)

        numeric, categorical = get_feature_types(X_train_raw)
        preprocessor = fit_preprocessor(X_train_raw, numeric, categorical)
        X_train = np.nan_to_num(preprocessor.transform(X_train_raw), nan=0.0)
        X_test = np.nan_to_num(preprocessor.transform(X_test_raw), nan=0.0)

        # Train GB
        gb = CalibratedClassifierCV(
            GradientBoostingClassifier(
                n_estimators=gb_params.get("n_estimators", 100),
                max_depth=gb_params.get("max_depth", 5),
                learning_rate=gb_params.get("learning_rate", 0.1),
                subsample=gb_params.get("subsample", 1.0),
                min_samples_leaf=gb_params.get("min_samples_leaf", 1),
                random_state=RANDOM_STATE,
            ),
            method="isotonic", cv=3,
        )

        # Sample weights (exponential decay)
        decay = 0.85
        max_year = train_df["year"].max()
        sample_weights = np.array([decay ** (max_year - y) for y in train_df["year"]])

        gb.fit(X_train, y_train, sample_weight=sample_weights)
        probs = gb.predict_proba(X_test)[:, 1]

        for strap, prob, solar in zip(test_df["strap"].values, probs, test_df["solar_pv"].values):
            all_scores.append({"strap": strap, "score": prob, "has_solar": int(solar == 1)})

        print(f"  Fold {fold_i+1}/{n_folds}: trained on {len(train_df)} rows, scored {len(test_df)} homes")

    scores_df = pd.DataFrame(all_scores)
    print(f"\nTotal scored: {len(scores_df)}")
    print(f"Solar adopters scored: {scores_df['has_solar'].sum()}")

    # Assign deciles based on score (1 = highest)
    scores_df["decile"] = pd.qcut(scores_df["score"], 10, labels=False, duplicates="drop")
    scores_df["decile"] = 10 - scores_df["decile"]  # 1 = highest score

    # Solar adopters by decile
    solar = scores_df[scores_df["has_solar"] == 1]
    all_by_decile = scores_df.groupby("decile").size().reset_index(name="total_homes")
    solar_by_decile = solar.groupby("decile").size().reset_index(name="installs")
    merged = all_by_decile.merge(solar_by_decile, on="decile", how="left").fillna(0)
    merged["installs"] = merged["installs"].astype(int)
    merged["adoption_rate"] = merged["installs"] / merged["total_homes"] * 100

    total_installs = merged["installs"].sum()

    # --- Chart ---
    fig, ax1 = plt.subplots(figsize=(10, 6))

    bars = ax1.bar(
        merged["decile"], merged["installs"],
        color=plt.cm.RdYlBu_r(np.linspace(0.15, 0.85, len(merged))),
        edgecolor="white", linewidth=0.8, zorder=3,
    )
    ax1.set_xlabel("Model Score Decile (1 = highest scored)", fontsize=12)
    ax1.set_ylabel("Solar Installations", fontsize=12, color="#333")
    ax1.set_xticks(range(1, 11))
    ax1.set_xticklabels([f"D{i}" for i in range(1, 11)])
    ax1.grid(axis="y", alpha=0.3, zorder=0)

    for bar, val in zip(bars, merged["installs"]):
        ax1.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 5,
                 str(int(val)), ha="center", va="bottom", fontsize=10, fontweight="bold")

    ax2 = ax1.twinx()
    ax2.plot(merged["decile"], merged["adoption_rate"], "ko-", linewidth=2, markersize=6, zorder=4)
    ax2.set_ylabel("Adoption Rate (%)", fontsize=12, color="#333")

    top2 = merged.loc[merged["decile"] <= 2, "installs"].sum()
    top2_pct = top2 / total_installs * 100 if total_installs > 0 else 0

    ax1.set_title(
        f"All Solar Installations by Score Decile — Gradient Boosting\n"
        f"5-Fold CV Out-of-Sample Scoring  |  {int(total_installs)} total installs  |  Top 2 deciles: {top2_pct:.0f}%",
        fontsize=13, fontweight="bold", pad=12,
    )

    fig.tight_layout()
    out = OUTPUT_DIR / "decile_all_installs.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    print(f"\nSaved: {out}")
    plt.close(fig)

    # Print table
    print(f"\n{'Decile':<8} {'Installs':>10} {'Homes':>8} {'Rate':>8} {'% of Total':>12}")
    print("-" * 50)
    for _, row in merged.iterrows():
        pct = row["installs"] / total_installs * 100 if total_installs > 0 else 0
        print(f"D{int(row['decile']):<7} {int(row['installs']):>10} {int(row['total_homes']):>8} {row['adoption_rate']:>7.2f}% {pct:>11.1f}%")
    print("-" * 50)
    print(f"{'Total':<8} {int(total_installs):>10}")


if __name__ == "__main__":
    main()
