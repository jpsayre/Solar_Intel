#!/usr/bin/env python3
"""
Analyze interaction transformations for solar adoption modeling.
For each interaction pair, tests raw, log, sqrt, etc. to find the best lift.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.preprocessing import StandardScaler

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from data_science.walk_forward_modeling import (
    AVG_YEARLY_INTEREST_PATH,
    INTERACTION_PAIRS,
    LOG_TRANSFORM_COLS,
    RANDOM_STATE,
    YEAR_END,
    YEAR_START,
    compute_lift_and_capture,
    fit_preprocessor,
    get_feature_columns,
    get_feature_types,
    load_data,
    prepare_features,
)

N_FOLDS = 2
N_ESTIMATORS = 40  # Smaller for faster analysis
SUBSAMPLE_TRAIN = 15_000  # Subsample train for speed; None = use all

# Transform variants: (name, fn) where fn(va, vb) -> interaction value
# va, vb are raw series; we clip/guard for log/sqrt
TRANSFORMS = [
    ("raw", lambda va, vb: va * vb),
    ("log_a", lambda va, vb: np.log1p(np.maximum(va, 0)) * vb),
    ("log_b", lambda va, vb: va * np.log1p(np.maximum(vb, 0))),
    ("log_both", lambda va, vb: np.log1p(np.maximum(va, 0)) * np.log1p(np.maximum(vb, 0))),
    # ("sqrt_a", lambda va, vb: np.sqrt(np.maximum(va, 0)) * vb),
    # ("sqrt_b", lambda va, vb: va * np.sqrt(np.maximum(vb, 0))),
    # ("sqrt_both", lambda va, vb: np.sqrt(np.maximum(va, 0)) * np.sqrt(np.maximum(vb, 0))),
]


def add_interaction_with_transform(
    X: pd.DataFrame,
    df_raw: pd.DataFrame,
    a: str,
    b: str,
    transform_name: str,
) -> pd.DataFrame:
    """Add one interaction column using the specified transform. Uses raw values from df_raw."""
    if a not in df_raw.columns or b not in df_raw.columns:
        return X
    va = pd.to_numeric(df_raw[a], errors="coerce").fillna(df_raw[a].median())
    vb = pd.to_numeric(df_raw[b], errors="coerce").fillna(df_raw[b].median())
    va = np.maximum(va, 0) if transform_name.startswith("log") or "sqrt" in transform_name else va
    vb = np.maximum(vb, 0) if "log_b" in transform_name or "sqrt" in transform_name else vb
    fn = next(t[1] for t in TRANSFORMS if t[0] == transform_name)
    X = X.copy()
    col_name = f"{a}_x_{b}"
    if col_name in X.columns:
        X = X.drop(columns=[col_name])
    X[col_name] = fn(va.values, vb.values)
    return X


def evaluate_lift(
    X_train: np.ndarray,
    y_train: np.ndarray,
    X_test: np.ndarray,
    y_test: np.ndarray,
) -> float:
    """Fit GB and return top-10% lift."""
    model = GradientBoostingClassifier(
        n_estimators=N_ESTIMATORS, max_depth=5, random_state=RANDOM_STATE
    )
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
    if AVG_YEARLY_INTEREST_PATH.exists():
        interest = pd.read_csv(AVG_YEARLY_INTEREST_PATH)
        if "average_rate" not in df.columns:
            df = df.merge(interest, on="year", how="left")

    feature_cols = get_feature_columns(df)
    straps = df["strap"].unique()
    rng = np.random.default_rng(RANDOM_STATE)
    straps_shuf = rng.permutation(straps)
    n_test = max(1, int(len(straps) * 0.2))
    test_straps = set(straps_shuf[:n_test])
    train_straps = set(straps_shuf[n_test:])

    available = set(df.columns)
    pairs_to_test = [(a, b) for a, b in INTERACTION_PAIRS if a in available and b in available]
    install_years = list(range(YEAR_END - N_FOLDS + 1, YEAR_END + 1))
    install_years = [y for y in install_years if y > YEAR_START]

    total_evals = len(install_years) * len(pairs_to_test) * len(TRANSFORMS)
    subsample_note = f" (train subsampled to {SUBSAMPLE_TRAIN:,})" if SUBSAMPLE_TRAIN else ""
    est_per_eval = 3 if SUBSAMPLE_TRAIN else 15  # sec per eval
    est_mins = total_evals * est_per_eval / 60
    print(f"Testing {len(pairs_to_test)} pairs × {len(TRANSFORMS)} transforms × {len(install_years)} years = {total_evals} evals{subsample_note}")
    print(f"Estimated runtime: ~{est_mins:.0f} min (~{est_per_eval}s per eval)")
    print("Transforms:", [t[0] for t in TRANSFORMS])
    print()

    results: dict[tuple[str, str], dict[str, list[float]]] = {
        (a, b): {t[0]: [] for t in TRANSFORMS} for a, b in pairs_to_test
    }

    t0 = time.perf_counter()
    eval_count = 0
    for fold_idx, install_year in enumerate(install_years):
        fold_start = time.perf_counter()
        feature_year = install_year - 1
        train_years = list(range(YEAR_START, install_year))
        train_df = df[(df["year"].isin(train_years)) & (df["strap"].isin(train_straps))]
        test_df = df[(df["year"] == feature_year) & (df["strap"].isin(test_straps))]

        if len(train_df) < 100 or len(test_df) < 20 or test_df["solar_next_year"].sum() < 5:
            print(f"  [Fold {install_year}] Skipping: train={len(train_df)}, test={len(test_df)}")
            continue

        if SUBSAMPLE_TRAIN is not None and len(train_df) > SUBSAMPLE_TRAIN:
            pos = train_df[train_df["solar_next_year"] == 1]
            neg = train_df[train_df["solar_next_year"] == 0]
            n_pos = min(len(pos), max(500, SUBSAMPLE_TRAIN // 10))
            n_neg = min(len(neg), SUBSAMPLE_TRAIN - n_pos)
            pos_samp = pos.sample(n=n_pos, random_state=RANDOM_STATE + fold_idx) if len(pos) > 0 else pos
            neg_samp = neg.sample(n=n_neg, random_state=RANDOM_STATE + fold_idx + 1) if len(neg) > 0 else neg
            train_df = pd.concat([pos_samp, neg_samp], ignore_index=True)
            print(f"[Fold {fold_idx+1}/{len(install_years)}] Install year {install_year} (train n={len(train_df):,} subsampled, test n={len(test_df):,})...")
        else:
            print(f"[Fold {fold_idx+1}/{len(install_years)}] Install year {install_year} (train n={len(train_df):,}, test n={len(test_df):,})...")
        y_train = train_df["solar_next_year"].astype(int).values
        y_test = test_df["solar_next_year"].astype(int).values

        # Baseline: prepare_features with ALL interactions (default)
        X_train_base = prepare_features(train_df, feature_cols)
        X_test_base = prepare_features(test_df, feature_cols)
        numeric, categorical = get_feature_types(X_train_base)
        preprocessor = fit_preprocessor(X_train_base, numeric, categorical)

        for pair_idx, (a, b) in enumerate(pairs_to_test):
            col_name = f"{a}_x_{b}"
            # Remove this pair's interaction from base (we'll add our variant)
            X_tr = X_train_base.drop(columns=[col_name], errors="ignore")
            X_te = X_test_base.drop(columns=[col_name], errors="ignore")
            if col_name not in X_train_base.columns:
                continue  # Pair not in default (e.g. missing column)
            for transform_name, _ in TRANSFORMS:
                eval_count += 1
                if eval_count % 20 == 0 or eval_count <= 3:
                    elapsed = time.perf_counter() - t0
                    per_eval = elapsed / eval_count if eval_count > 0 else 0
                    eta = per_eval * (total_evals - eval_count) if eval_count > 0 else 0
                    print(f"  eval {eval_count}/{total_evals} ({a}×{b} {transform_name}) ... ~{per_eval:.0f}s/eval, {eta/60:.1f}m left")
                X_tr_v = add_interaction_with_transform(
                    X_tr, train_df, a, b, transform_name
                )
                X_te_v = add_interaction_with_transform(
                    X_te, test_df, a, b, transform_name
                )
                numeric_v, cat_v = get_feature_types(X_tr_v)
                prep = fit_preprocessor(X_tr_v, numeric_v, cat_v)
                X_tr_scaled = prep.transform(X_tr_v)
                X_te_scaled = prep.transform(X_te_v)
                lift = evaluate_lift(X_tr_scaled, y_train, X_te_scaled, y_test)
                results[(a, b)][transform_name].append(lift)

        fold_elapsed = time.perf_counter() - fold_start
        print(f"  Fold {install_year} done in {fold_elapsed:.1f}s")

    total_elapsed = time.perf_counter() - t0
    print()
    print("=" * 90)
    print(f"INTERACTION TRANSFORM ANALYSIS (top-10% lift, avg over folds) — {total_elapsed/60:.1f} min total")
    print("=" * 90)

    best_overall = []
    for (a, b) in pairs_to_test:
        lifts = results[(a, b)]
        valid = {k: v for k, v in lifts.items() if v}
        if not valid:
            continue
        best_name = max(valid, key=lambda k: np.mean(valid[k]))
        best_lift = np.mean(valid[best_name])
        raw_lift = np.mean(valid.get("raw", [0]))
        improvement = (best_lift - raw_lift) / raw_lift if raw_lift > 0 else 0

        print(f"\n{a} x {b}:")
        for tname in [t[0] for t in TRANSFORMS]:
            vals = valid.get(tname, [])
            avg = np.mean(vals) if vals else 0
            mark = " <-- BEST" if tname == best_name else ""
            print(f"  {tname:12s}: {avg:.3f}x{mark}")
        if improvement > 0.02:
            best_overall.append(((a, b), best_name, best_lift, improvement))
            print(f"  >>> Prefer {best_name} over raw ({improvement:+.1%} lift gain)")

    if best_overall:
        print("\n" + "=" * 90)
        print("RECOMMENDED: Use these transforms in walk_forward_modeling INTERACTION_TRANSFORMS")
        for ((a, b), tname, lift, imp) in sorted(best_overall, key=lambda x: -x[3]):
            print(f"  ('{a}', '{b}'): '{tname}'  # +{imp:.1%} vs raw")
    else:
        print("\nNo transform beat raw by >2% for any pair.")


if __name__ == "__main__":
    main()
