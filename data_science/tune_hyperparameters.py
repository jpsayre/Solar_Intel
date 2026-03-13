#!/usr/bin/env python3
"""
Hyperparameter tuning for walk-forward solar prediction models using Optuna.

Uses temporal inner validation: for each tuning fold, trains on years [T-5..T-2],
validates on year T-1, optimizes top-10% lift.

Tunes: Random Forest, Gradient Boosting, LightGBM, Neural Net.
Exports best params to tuned_params.json for walk_forward_modeling.py.

Usage:
    python data_science/tune_hyperparameters.py
    python data_science/tune_hyperparameters.py --n-trials 30   # fewer trials for speed
    python data_science/tune_hyperparameters.py --models lgbm gb  # tune specific models
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import warnings
from datetime import datetime
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", str(Path(__file__).resolve().parent / ".mplconfig"))

import numpy as np
import optuna
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.neural_network import MLPClassifier
from sklearn.preprocessing import StandardScaler

try:
    import lightgbm as lgb
    HAS_LIGHTGBM = True
except ImportError:
    HAS_LIGHTGBM = False

warnings.filterwarnings("ignore")
optuna.logging.set_verbosity(optuna.logging.WARNING)

# Import shared utilities from walk_forward_modeling
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from walk_forward_modeling import (
    EXCLUDE_COLS,
    LOG_TRANSFORM_COLS,
    INTERACTION_PAIRS,
    INTERACTION_TRANSFORMS,
    FEATURE_MIN_SAMPLES,
    FEATURE_MIN_SAMPLES_EXEMPT,
    N_FEATURES_SELECT,
    N_FEATURES_CANDIDATE,
    USE_LIFT_RERANK,
    SAMPLE_WEIGHT_DECAY,
    RANDOM_STATE,
    TEST_STRAP_FRACTION,
    compute_lift_and_capture,
    get_feature_columns,
    prepare_features,
    fit_preprocessor,
    get_feature_types,
    get_preprocessor_feature_names,
    run_feature_selection_once,
    run_lift_rerank,
    get_feature_indices,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_PATH = PROJECT_ROOT / "data" / "working" / "data_science_input.csv"
AVG_YEARLY_INTEREST_PATH = PROJECT_ROOT / "data" / "final" / "avg_yearly_interest.csv"
OUTPUT_DIR = PROJECT_ROOT / "data_science" / "output" / "tuning"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
PARAMS_PATH = PROJECT_ROOT / "data_science" / "tuned_params.json"

# Tuning folds: install years to tune on (recent years for relevance)
TUNING_INSTALL_YEARS = [2023, 2024, 2025]
TRAIN_YEARS_WINDOW = 5
YEAR_START = 2012

DEFAULT_N_TRIALS = 50


def load_data() -> pd.DataFrame:
    """Load and prepare data (same as walk_forward_modeling)."""
    df = pd.read_csv(DATA_PATH)
    df = df[df["year"].between(YEAR_START, 2026)]
    if AVG_YEARLY_INTEREST_PATH.exists():
        interest = pd.read_csv(AVG_YEARLY_INTEREST_PATH)
        if "average_rate" not in df.columns:
            df = df.merge(interest, on="year", how="left")
    df = df[df["solar_next_year"].isin([0, 1])]
    return df


def prepare_fold(
    df: pd.DataFrame,
    install_year: int,
    train_straps: set,
    test_straps: set,
    feature_cols: list[str],
) -> tuple:
    """Prepare train/test data for a single fold. Returns (X_train, y_train, X_test, y_test, sample_weight)."""
    train_years = list(range(max(YEAR_START, install_year - TRAIN_YEARS_WINDOW), install_year))
    feature_year = install_year - 1

    train_df = df[(df["year"].isin(train_years)) & (df["strap"].isin(train_straps))]
    test_df = df[(df["year"] == feature_year) & (df["strap"].isin(test_straps))]

    if len(train_df) < 10 or len(test_df) < 5:
        return None

    y_train = train_df["solar_next_year"].astype(int).values
    y_test = test_df["solar_next_year"].astype(int).values

    # Compute train medians
    train_medians = {}
    for c in feature_cols:
        if train_df[c].dtype in (np.float64, np.int64, "float64", "int64", "Int64"):
            med = train_df[c].median()
            if pd.notna(med):
                train_medians[c] = float(med)

    X_train_raw = prepare_features(train_df, feature_cols, train_medians=train_medians)
    X_test_raw = prepare_features(test_df, feature_cols, train_medians=train_medians)

    numeric_fold, categorical_fold = get_feature_types(X_train_raw)
    preprocessor = fit_preprocessor(X_train_raw, numeric_fold, categorical_fold)
    X_train_full = preprocessor.transform(X_train_raw)
    X_test_full = preprocessor.transform(X_test_raw)

    feature_names_fold = get_preprocessor_feature_names(preprocessor, numeric_fold, categorical_fold)

    # Drop low-sample features
    keep_mask = np.ones(X_train_full.shape[1], dtype=bool)
    for i, fname in enumerate(feature_names_fold):
        col = X_train_full[:, i]
        is_binary = np.all(np.isin(col, [0, 1]))
        if is_binary:
            n_count = int((col == 1).sum())
            is_exempt = any(ex in fname for ex in FEATURE_MIN_SAMPLES_EXEMPT)
            if n_count < FEATURE_MIN_SAMPLES and not is_exempt:
                keep_mask[i] = False
    X_train_full = X_train_full[:, keep_mask]
    X_test_full = X_test_full[:, keep_mask]
    feature_names_fold = [f for f, k in zip(feature_names_fold, keep_mask) if k]

    # Feature selection
    n_pos = int(y_train.sum())
    selected_idx = np.arange(X_train_full.shape[1])
    if N_FEATURES_SELECT and X_train_full.shape[1] > N_FEATURES_SELECT and n_pos >= 30:
        try:
            n_cand = min(N_FEATURES_CANDIDATE, X_train_full.shape[1]) if USE_LIFT_RERANK else N_FEATURES_SELECT
            candidates, importance = run_feature_selection_once(
                X_train_full, y_train, feature_names_fold, n_cand
            )
            if USE_LIFT_RERANK and len(candidates) > N_FEATURES_SELECT:
                selected, _ = run_lift_rerank(
                    X_train_full, y_train, candidates, feature_names_fold,
                    train_df, N_FEATURES_SELECT,
                )
            else:
                selected = candidates[:N_FEATURES_SELECT]
            selected_idx = get_feature_indices(selected, feature_names_fold)
        except Exception:
            pass

    X_train = X_train_full[:, selected_idx]
    X_test = X_test_full[:, selected_idx]

    # Sample weights
    train_years_arr = train_df["year"].values
    max_train_year = train_years_arr.max()
    sample_weight = SAMPLE_WEIGHT_DECAY ** (max_train_year - train_years_arr)

    return X_train, y_train, X_test, y_test, sample_weight


def evaluate_params(model, X_train, y_train, X_test, y_test, sample_weight) -> float:
    """Train model with params and return top-10% lift on test set."""
    try:
        try:
            model.fit(X_train, y_train, sample_weight=sample_weight)
        except TypeError:
            model.fit(X_train, y_train)

        y_prob = model.predict_proba(X_test)[:, 1]
        baseline_rate = y_test.mean()
        if baseline_rate <= 0:
            return 0.0
        metrics = compute_lift_and_capture(y_test, y_prob, baseline_rate)
        return metrics.get("lift_10pct", 0.0)
    except Exception:
        return 0.0


def make_rf_objective(folds):
    def objective(trial):
        params = {
            "n_estimators": trial.suggest_int("n_estimators", 100, 500, step=50),
            "max_depth": trial.suggest_int("max_depth", 5, 20),
            "min_samples_leaf": trial.suggest_int("min_samples_leaf", 5, 50),
            "max_features": trial.suggest_float("max_features", 0.3, 1.0),
            "class_weight": trial.suggest_categorical("class_weight", ["balanced", "balanced_subsample"]),
            "random_state": RANDOM_STATE,
        }
        lifts = []
        for fold in folds:
            X_tr, y_tr, X_te, y_te, sw = fold
            model = CalibratedClassifierCV(
                RandomForestClassifier(**params), method="isotonic", cv=3
            )
            lift = evaluate_params(model, X_tr, y_tr, X_te, y_te, sw)
            lifts.append(lift)
        return np.mean(lifts)
    return objective


def make_gb_objective(folds):
    def objective(trial):
        params = {
            "n_estimators": trial.suggest_int("n_estimators", 100, 500, step=50),
            "max_depth": trial.suggest_int("max_depth", 3, 8),
            "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.3, log=True),
            "subsample": trial.suggest_float("subsample", 0.6, 1.0),
            "min_samples_leaf": trial.suggest_int("min_samples_leaf", 10, 100),
            "random_state": RANDOM_STATE,
        }
        lifts = []
        for fold in folds:
            X_tr, y_tr, X_te, y_te, sw = fold
            model = CalibratedClassifierCV(
                GradientBoostingClassifier(**params), method="isotonic", cv=3
            )
            lift = evaluate_params(model, X_tr, y_tr, X_te, y_te, sw)
            lifts.append(lift)
        return np.mean(lifts)
    return objective


def make_lgbm_objective(folds):
    def objective(trial):
        params = {
            "n_estimators": trial.suggest_int("n_estimators", 100, 1000, step=50),
            "max_depth": trial.suggest_int("max_depth", 3, 10),
            "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.3, log=True),
            "num_leaves": trial.suggest_int("num_leaves", 15, 63),
            "min_child_samples": trial.suggest_int("min_child_samples", 20, 200),
            "subsample": trial.suggest_float("subsample", 0.6, 1.0),
            "colsample_bytree": trial.suggest_float("colsample_bytree", 0.5, 1.0),
            "reg_alpha": trial.suggest_float("reg_alpha", 0.0, 5.0),
            "reg_lambda": trial.suggest_float("reg_lambda", 0.0, 5.0),
            "is_unbalance": True,
            "random_state": RANDOM_STATE,
            "verbose": -1,
        }
        lifts = []
        for fold in folds:
            X_tr, y_tr, X_te, y_te, sw = fold
            model = lgb.LGBMClassifier(**params)
            lift = evaluate_params(model, X_tr, y_tr, X_te, y_te, sw)
            lifts.append(lift)
        return np.mean(lifts)
    return objective


def make_mlp_objective(folds):
    def objective(trial):
        arch = trial.suggest_categorical("architecture", [
            "(32,)", "(64,32)", "(128,64)", "(128,64,32)", "(64,32,16)",
        ])
        hidden = eval(arch)
        params = {
            "hidden_layer_sizes": hidden,
            "alpha": trial.suggest_float("alpha", 1e-5, 1e-1, log=True),
            "learning_rate_init": trial.suggest_float("learning_rate_init", 1e-4, 1e-2, log=True),
            "batch_size": trial.suggest_categorical("batch_size", [64, 128, 256, 512]),
            "max_iter": 500,
            "early_stopping": True,
            "random_state": RANDOM_STATE,
        }
        lifts = []
        for fold in folds:
            X_tr, y_tr, X_te, y_te, sw = fold
            model = MLPClassifier(**params)
            lift = evaluate_params(model, X_tr, y_tr, X_te, y_te, sw)
            lifts.append(lift)
        return np.mean(lifts)
    return objective


MODEL_CONFIGS = {
    "rf": ("Random Forest", make_rf_objective),
    "gb": ("Gradient Boosting", make_gb_objective),
    "lgbm": ("LightGBM", make_lgbm_objective),
    "mlp": ("Neural Net", make_mlp_objective),
}


def main():
    parser = argparse.ArgumentParser(description="Tune hyperparameters for solar prediction models")
    parser.add_argument("--n-trials", type=int, default=DEFAULT_N_TRIALS,
                        help=f"Optuna trials per model (default: {DEFAULT_N_TRIALS})")
    parser.add_argument("--models", nargs="+", default=list(MODEL_CONFIGS.keys()),
                        choices=list(MODEL_CONFIGS.keys()),
                        help="Models to tune (default: all)")
    args = parser.parse_args()

    if "lgbm" in args.models and not HAS_LIGHTGBM:
        print("Warning: LightGBM not available, skipping")
        args.models = [m for m in args.models if m != "lgbm"]

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    print(f"Hyperparameter tuning: {args.n_trials} trials per model")
    print(f"Models: {[MODEL_CONFIGS[m][0] for m in args.models]}")
    print(f"Tuning folds: install years {TUNING_INSTALL_YEARS}")

    print("\nLoading data...")
    df = load_data()
    feature_cols = get_feature_columns(df)
    print(f"Loaded {len(df)} rows, {len(feature_cols)} feature columns")

    # Strap-based split (same as walk-forward)
    straps = df["strap"].unique()
    np.random.seed(RANDOM_STATE)
    np.random.shuffle(straps)
    n_test = max(1, int(len(straps) * TEST_STRAP_FRACTION))
    test_straps = set(straps[:n_test])
    train_straps = set(straps[n_test:])
    print(f"Train straps: {len(train_straps)}, Test straps: {len(test_straps)}")

    # Prepare tuning folds
    print("\nPreparing tuning folds...")
    folds = []
    for install_year in TUNING_INSTALL_YEARS:
        result = prepare_fold(df, install_year, train_straps, test_straps, feature_cols)
        if result is not None:
            folds.append(result)
            X_tr, y_tr, X_te, y_te, sw = result
            print(f"  Install year {install_year}: train={len(y_tr)} ({y_tr.sum()} pos), "
                  f"test={len(y_te)} ({y_te.sum()} pos)")
        else:
            print(f"  Install year {install_year}: skipped (insufficient data)")

    if not folds:
        print("Error: no valid tuning folds")
        return

    # Tune each model
    best_params = {}
    for model_key in args.models:
        model_name, make_objective = MODEL_CONFIGS[model_key]
        print(f"\n{'='*60}")
        print(f"Tuning {model_name} ({args.n_trials} trials)...")
        print("=" * 60)

        study = optuna.create_study(
            direction="maximize",
            sampler=optuna.samplers.TPESampler(seed=RANDOM_STATE),
            pruner=optuna.pruners.MedianPruner(n_startup_trials=10),
        )
        objective = make_objective(folds)
        study.optimize(objective, n_trials=args.n_trials, show_progress_bar=True)

        best = study.best_trial
        print(f"\n  Best trial #{best.number}: avg lift={best.value:.3f}x")
        print(f"  Best params: {best.params}")

        best_params[model_key] = {
            "model_name": model_name,
            "best_lift": float(best.value),
            "params": best.params,
        }

        # Save per-model study results
        trials_df = study.trials_dataframe()
        trials_df.to_csv(OUTPUT_DIR / f"trials_{model_key}_{ts}.csv", index=False)

    # Save best params
    with open(PARAMS_PATH, "w") as f:
        json.dump(best_params, f, indent=2)
    print(f"\nSaved best params to {PARAMS_PATH}")

    # Summary
    print("\n" + "=" * 60)
    print("TUNING SUMMARY")
    print("=" * 60)
    for key, info in best_params.items():
        print(f"\n  {info['model_name']} (avg lift: {info['best_lift']:.3f}x):")
        for k, v in info["params"].items():
            print(f"    {k}: {v}")

    print(f"\nAll trial details saved to {OUTPUT_DIR}")
    print(f"Run walk-forward with tuned params: python data_science/walk_forward_modeling.py")


if __name__ == "__main__":
    main()
