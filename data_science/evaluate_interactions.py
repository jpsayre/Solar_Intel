#!/usr/bin/env python3
"""
Evaluate feature interactions for solar adoption modeling.
Tests candidate pairs (e.g. avg_electricity_price x mainfloorsf) and measures lift impact.
Interactions that significantly increase lift are added to walk_forward_modeling.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from sklearn.preprocessing import StandardScaler

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from data_science.walk_forward_modeling import (
    AVG_YEARLY_INTEREST_PATH,
    INTERACTION_PAIRS,
    RANDOM_STATE,
    YEAR_END,
    YEAR_START,
    add_interaction_columns,
    compute_lift_and_capture,
    fit_preprocessor,
    get_feature_columns,
    get_feature_types,
    load_data,
    prepare_features,
)

# Additional candidates beyond INTERACTION_PAIRS to evaluate
EXTRA_CANDIDATES = [
    ("avg_electricity_price", "sqft"),
    ("roof_score", "sqft"),
    ("saleprice", "avg_electricity_price"),
    ("building_price_sqft", "mainfloorsf"),
    ("closest_fifty_percentage", "mainfloorsf"),
    ("count_0_05mi", "avg_electricity_price"),
]
INTERACTION_CANDIDATES = list(INTERACTION_PAIRS) + EXTRA_CANDIDATES

N_FOLDS = 2  # Quick evaluation: test on last N install years
LIFT_IMPROVEMENT_THRESHOLD = 0.05  # Min lift improvement (e.g. 0.05 = 5% relative) to keep


def add_interaction_columns(X: pd.DataFrame, pairs: list[tuple[str, str]]) -> pd.DataFrame:
    """Add interaction columns (col_a * col_b) when both exist."""
    X = X.copy()
    for a, b in pairs:
        if a in X.columns and b in X.columns:
            va = pd.to_numeric(X[a], errors="coerce").fillna(X[a].median())
            vb = pd.to_numeric(X[b], errors="coerce").fillna(X[b].median())
            X[f"{a}_x_{b}"] = va * vb
    return X


def evaluate_lift(
    X_train: np.ndarray,
    y_train: np.ndarray,
    X_test: np.ndarray,
    y_test: np.ndarray,
    model_name: str = "Gradient Boosting",
) -> float:
    """Fit model and return top-10% lift on test set."""
    if model_name == "Gradient Boosting":
        model = GradientBoostingClassifier(n_estimators=100, max_depth=5, random_state=RANDOM_STATE)
    else:
        model = RandomForestClassifier(n_estimators=100, max_depth=10, random_state=RANDOM_STATE, class_weight="balanced")
    model.fit(X_train, y_train)
    y_prob = model.predict_proba(X_test)[:, 1]
    baseline_rate = y_test.mean()
    if baseline_rate <= 0:
        return 0.0
    metrics = compute_lift_and_capture(y_test, y_prob, baseline_rate)
    return metrics.get("lift_10pct", 0.0)


def main() -> None:
    print("Loading data...")
    df = load_data()
    df = df[df["solar_next_year"].isin([0, 1])]
    feature_cols = get_feature_columns(df)
    if AVG_YEARLY_INTEREST_PATH.exists():
        interest = pd.read_csv(AVG_YEARLY_INTEREST_PATH)
        if "average_rate" not in df.columns:
            df = df.merge(interest, on="year", how="left")

    # Strap split
    straps = df["strap"].unique()
    rng = np.random.default_rng(RANDOM_STATE)
    straps_shuf = rng.permutation(straps)
    n_test = max(1, int(len(straps) * 0.2))
    test_straps = set(straps_shuf[:n_test])
    train_straps = set(straps_shuf[n_test:])

    # Filter to pairs where both columns exist in data
    available = set(df.columns)
    pairs_to_test = [(a, b) for a, b in INTERACTION_CANDIDATES if a in available and b in available]
    print(f"Testing {len(pairs_to_test)} interaction pairs (columns present in data)")

    # Test years: last N install years
    install_years = list(range(YEAR_END - N_FOLDS + 1, YEAR_END + 1))
    install_years = [y for y in install_years if y > YEAR_START]

    baseline_lifts = []
    interaction_lifts: dict[tuple[str, str], list[float]] = {(a, b): [] for a, b in pairs_to_test}

    for install_year in install_years:
        feature_year = install_year - 1
        train_years = list(range(YEAR_START, install_year))
        train_df = df[(df["year"].isin(train_years)) & (df["strap"].isin(train_straps))]
        test_df = df[(df["year"] == feature_year) & (df["strap"].isin(test_straps))]

        if len(train_df) < 100 or len(test_df) < 20:
            continue
        y_train = train_df["solar_next_year"].astype(int).values
        y_test = test_df["solar_next_year"].astype(int).values
        if y_test.sum() < 5:
            continue

        # Baseline (no interactions)
        X_train_raw = prepare_features(train_df, feature_cols)
        X_test_raw = prepare_features(test_df, feature_cols)
        numeric, categorical = get_feature_types(X_train_raw)
        preprocessor = fit_preprocessor(X_train_raw, numeric, categorical)
        X_train_base = preprocessor.transform(X_train_raw)
        X_test_base = preprocessor.transform(X_test_raw)
        lift_base = evaluate_lift(X_train_base, y_train, X_test_base, y_test)
        baseline_lifts.append(lift_base)

        # With each interaction
        for a, b in pairs_to_test:
            X_train_int = add_interaction_columns(X_train_raw, [(a, b)])
            X_test_int = add_interaction_columns(X_test_raw, [(a, b)])
            numeric_int, cat_int = get_feature_types(X_train_int)
            preprocessor_int = fit_preprocessor(X_train_int, numeric_int, cat_int)
            X_tr = preprocessor_int.transform(X_train_int)
            X_te = preprocessor_int.transform(X_test_int)
            lift_int = evaluate_lift(X_tr, y_train, X_te, y_test)
            interaction_lifts[(a, b)].append(lift_int)

    if not baseline_lifts:
        print("No valid folds; cannot evaluate.")
        return

    avg_baseline = np.mean(baseline_lifts)
    print(f"\nBaseline top-10% lift (avg over {len(baseline_lifts)} folds): {avg_baseline:.3f}x")
    print("\nInteraction lift impact (avg over folds):")
    print("-" * 70)

    significant = []
    for (a, b), lifts in interaction_lifts.items():
        if not lifts:
            continue
        avg_lift = np.mean(lifts)
        improvement = (avg_lift - avg_baseline) / avg_baseline if avg_baseline > 0 else 0
        status = "*** KEEP ***" if improvement >= LIFT_IMPROVEMENT_THRESHOLD else ""
        print(f"  {a} x {b}: {avg_lift:.3f}x  (Δ={improvement:+.1%})  {status}")
        if improvement >= LIFT_IMPROVEMENT_THRESHOLD:
            significant.append((a, b))

    print("\n" + "=" * 70)
    if significant:
        print(f"Interactions to add to feature pool ({len(significant)}):")
        for a, b in significant:
            print(f"  ('{a}', '{b}')")
    else:
        print("No interactions met the lift improvement threshold.")


if __name__ == "__main__":
    main()
