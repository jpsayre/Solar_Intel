#!/usr/bin/env python3
"""
Fast walk-forward modeling: GB-only, one-time feature selection, curated features.

Simplified version of walk_forward_modeling.py:
- Curated feature list (no ID columns, no address junk)
- Auto-detects first year with positives, skips empty years
- Feature selection done ONCE on pooled data, reused for all years
- Gradient Boosting only (calibrated)
- Single preprocessor fit, reused across folds
"""

from __future__ import annotations

import json
import os
import sys
import warnings
from datetime import datetime
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", str(Path(__file__).resolve().parent / ".mplconfig"))
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, roc_auc_score
from sklearn.preprocessing import OneHotEncoder, StandardScaler

warnings.filterwarnings("ignore")

sys.path.insert(0, str(Path(__file__).resolve().parent))
from walk_forward_modeling import (
    CALIBRATION_METHOD,
    INTERACTION_PAIRS,
    INTERACTION_TRANSFORMS,
    LOG_TRANSFORM_COLS,
    RANDOM_STATE,
    SAMPLE_WEIGHT_DECAY,
    TRAIN_YEARS_WINDOW,
    USE_CALIBRATION,
    add_interaction_columns,
    add_time_bin_factors,
    assign_deciles,
    compute_decile_lift,
    compute_lift_and_capture,
    load_data,
    set_config,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
N_FEATURES_SELECT = 25

# ============================================================
# CURATED FEATURE LIST — matches Boulder County data_science_input.csv
# No IDs, no addresses, no owner names. Consistent across counties.
# ============================================================

# Permit flags (binary, from permit parsing)
PERMIT_FEATURES = [
    "solar_pv", "battery", "ev_charger", "roof_new_or_replace",
    "electrical_service_upgrade", "heat_pump", "ac", "furnace",
    "water_heater", "water_heater_electric", "water_heater_gas",
    "water_heater_solar_thermal", "windows_doors", "insulation_airseal",
    "generator", "addition_new_build", "kitchen_bath_remodel",
    "pool_hot_tub", "evaporative_cooler",
]

# Neighbor / social contagion features
NEIGHBOR_FEATURES = [
    "count_3mi", "count_1mi", "count_0_5mi", "count_0_25mi",
    "count_0_1mi", "count_0_05mi",
    "last_year_neighbors_w_solar_0_05mi", "last_year_neighbors_w_solar_0_1mi",
    "last_year_neighbors_w_solar_0_25mi", "last_year_neighbors_w_solar_0_5mi",
    "last_year_neighbors_w_solar_1mi",
    "closest_fifty_percentage", "solar_neighbor_momentum",
    "neighbor_solar_slope_3yr", "permit_velocity_3yr",
]

# Property characteristics (from Regrid allowlist — only clean columns)
PROPERTY_FEATURES = [
    "yearbuilt", "saleprice", "area_building", "sqft", "mainfloorsf",
    "calculated_build_year",
]

# Property categorical (Boulder has carstoragetypedscr, acdscr, heatingdscr)
PROPERTY_CATEGORICAL = [
    "carstoragetypedscr", "acdscr", "heatingdscr",
]

# Census / demographic
CENSUS_FEATURES = [
    "median_household_income", "median_home_value", "median_age",
    "median_year_moved_in", "median_year_built",
    "pct_college_educated", "pct_owner_occupied",
    "pct_family_households", "pct_multi_vehicle",
]

# Derived / engineered
DERIVED_FEATURES = [
    "income_per_sqft", "home_value_to_income", "census_vs_property_age",
    "calculated_roof_age", "roof_score",
    "avg_electricity_price", "electricity_year_trend",
    "time_since_sale", "time_since_build",
    "recent_build", "land_price_sqft", "building_price_sqft",
    "recent_purchase", "electricity_use_proxy",
    "est_annual_electricity_cost", "likely_mortgage_rate",
]

ALL_CURATED_FEATURES = (
    PERMIT_FEATURES + NEIGHBOR_FEATURES + PROPERTY_FEATURES +
    PROPERTY_CATEGORICAL + CENSUS_FEATURES + DERIVED_FEATURES
)

# Time-varying features only (genuinely different signal year to year)
# Excludes anything that's just "static value + year offset" (building age, time_since_build, etc.)
# Used with --temporal-only to diagnose static feature inflation
TEMPORAL_FEATURES = (
    PERMIT_FEATURES  # permit flags accumulate over time (new permits each year)
    + NEIGHBOR_FEATURES  # neighbor counts change each year (new installations)
    + [
        "likely_mortgage_rate",  # macro rate changes with year
        "avg_electricity_price", "electricity_year_trend",  # macro price changes
    ]
)

# Time columns to bin (from walk_forward_modeling)
TIME_COLS = ["time_since_sale", "time_since_build"]
TIME_BIN_YEARS = 10


def log(msg: str) -> None:
    print(msg, flush=True)


def prepare_features_fast(df, feature_cols, train_medians=None):
    """Prepare features: log-transform, time bins, interactions, fill NaN."""
    if train_medians is None:
        train_medians = {}
    X = df[feature_cols].copy()

    # Log-transform high-scale numeric columns
    for c in LOG_TRANSFORM_COLS:
        if c in X.columns and X[c].dtype in (np.float64, np.int64, "float64", "int64", "Int64"):
            med = train_medians.get(c)
            vals = X[c].fillna(med if med is not None else X[c].median())
            vals = np.maximum(vals, 1)
            X[c] = np.log1p(vals)

    # Time bins
    X = add_time_bin_factors(X)

    # Interactions
    X = add_interaction_columns(X, INTERACTION_PAIRS, df_raw=df, train_medians=train_medians)

    # Fill NaN
    numeric = X.select_dtypes(include=[np.number]).columns.tolist()
    categorical = X.select_dtypes(include=["object", "category"]).columns.tolist()
    for c in numeric:
        if X[c].isnull().any():
            med = train_medians.get(c)
            X[c] = X[c].fillna(med if med is not None else X[c].median())
    for c in categorical:
        if c in X.columns and X[c].nunique() <= 20:
            X[c] = X[c].fillna("MISSING").astype(str)
    return X


def fit_preprocessor_fast(X):
    """Build and fit ColumnTransformer on prepared features."""
    numeric = X.select_dtypes(include=[np.number]).columns.tolist()
    categorical = [c for c in X.select_dtypes(include=["object", "category"]).columns if X[c].nunique() <= 20]
    transformers = []
    if numeric:
        transformers.append(("num", StandardScaler(), numeric))
    if categorical:
        transformers.append(("cat", OneHotEncoder(handle_unknown="ignore", sparse_output=False), categorical))
    preprocessor = ColumnTransformer(transformers, remainder="drop")
    preprocessor.fit(X)
    # Get feature names
    names = []
    try:
        names = list(preprocessor.get_feature_names_out())
    except (AttributeError, TypeError):
        for name, trans, cols in preprocessor.transformers_:
            if name == "num":
                names.extend(f"num__{c}" for c in cols)
            elif name == "cat" and hasattr(trans, "get_feature_names_out"):
                names.extend(f"cat__{n}" for n in trans.get_feature_names_out(cols))
    return preprocessor, names, numeric, categorical


CORRELATION_THRESHOLD = 0.80  # skip features correlated above this with any already-selected feature

# Feature group caps: max N features from each conceptual group.
# Keys are prefix patterns matched against the feature name (after stripping num__/cat__).
# Features not matching any group have no cap.
FEATURE_GROUP_MAX = 2
FEATURE_GROUPS = {
    "building_age": [
        "calculated_roof_age", "calculated_build_year", "yearbuilt",
        "census_vs_property_age", "time_since_build", "recent_build",
        "median_year_built", "time_since_build_bin_",
    ],
    "sale_recency": [
        "time_since_sale", "recent_purchase", "time_since_sale_bin_",
    ],
    "neighbor_contagion": [
        "count_3mi", "count_1mi", "count_0_5mi", "count_0_25mi",
        "count_0_1mi", "count_0_05mi",
        "last_year_neighbors_w_solar_", "closest_fifty_percentage",
        "solar_neighbor_momentum", "neighbor_solar_slope_3yr",
        "permit_velocity_3yr",
        "pct_owner_occupied_x_closest_fifty_percentage",
        "median_household_income_x_closest_fifty_percentage",
    ],
}


def _get_feature_group(fname: str) -> str | None:
    """Return the group name for a feature, or None if ungrouped."""
    # Strip num__/cat__ prefix
    clean = fname.split("__", 1)[-1] if "__" in fname else fname
    for group, patterns in FEATURE_GROUPS.items():
        for pat in patterns:
            if clean == pat or clean.startswith(pat):
                return group
    return None


MIN_PREVALENCE = 0.02  # features with <2% non-zero rows are dropped before selection


def run_feature_selection(X, y, feature_names, n_features=25):
    """Lasso/Ridge/ElasticNet average importance -> top N, with correlation + group dedup."""
    if X.shape[1] <= n_features:
        return np.arange(X.shape[1]), feature_names, {}

    # Drop rare features (< MIN_PREVALENCE non-zero)
    prevalence = (X != 0).mean(axis=0)
    rare_mask = prevalence < MIN_PREVALENCE
    n_rare = int(rare_mask.sum())
    if n_rare > 0:
        rare_indices = np.where(rare_mask)[0]
        log(f"  Dropping {n_rare} rare features (<{MIN_PREVALENCE:.0%} non-zero):")
        for ri in rare_indices[:8]:
            log(f"    {feature_names[ri].split('__',1)[-1]} ({prevalence[ri]:.2%})")
        if n_rare > 8:
            log(f"    ... and {n_rare-8} more")
        keep_mask = ~rare_mask
        # Track original indices so we can map back
        orig_indices = np.where(keep_mask)[0]
        X = X[:, keep_mask]
        feature_names = [feature_names[i] for i in orig_indices]
    else:
        orig_indices = np.arange(len(feature_names))

    if X.shape[1] <= n_features:
        return orig_indices, feature_names, {}

    log("  Fitting Lasso...")
    lasso = LogisticRegression(
        penalty="l1", solver="saga", C=0.1, max_iter=2000,
        random_state=RANDOM_STATE, class_weight="balanced",
    )
    lasso.fit(X, y)

    log("  Fitting Ridge...")
    ridge = LogisticRegression(
        penalty="l2", solver="lbfgs", C=1.0, max_iter=2000,
        random_state=RANDOM_STATE, class_weight="balanced",
    )
    ridge.fit(X, y)

    log("  Fitting Elastic Net...")
    enet = LogisticRegression(
        penalty="elasticnet", solver="saga", l1_ratio=0.5, C=0.1, max_iter=2000,
        random_state=RANDOM_STATE, class_weight="balanced",
    )
    enet.fit(X, y)

    def norm(x):
        m = x.max()
        return x / m if m > 0 else x

    avg_imp = (norm(np.abs(lasso.coef_[0])) + norm(np.abs(ridge.coef_[0])) + norm(np.abs(enet.coef_[0]))) / 3
    importance = {feature_names[i]: float(avg_imp[i]) for i in range(len(feature_names))}

    # Rank all features by importance
    ranked_idx = np.argsort(avg_imp)[::-1]

    # Pre-compute correlation matrix
    log(f"  Correlation + group dedup (corr>{CORRELATION_THRESHOLD}, max {FEATURE_GROUP_MAX}/group)...")
    corr_matrix = np.corrcoef(X.T)
    corr_matrix = np.nan_to_num(corr_matrix, nan=0.0)

    selected_idx = []
    group_counts: dict[str, int] = {}
    skipped_corr = []
    skipped_group = []

    for idx in ranked_idx:
        if len(selected_idx) >= n_features:
            break
        fname = feature_names[idx]

        # Check group cap
        group = _get_feature_group(fname)
        if group is not None:
            if group_counts.get(group, 0) >= FEATURE_GROUP_MAX:
                skipped_group.append((fname, group))
                continue

        # Check correlation with already-selected features
        too_correlated = False
        for sel_idx in selected_idx:
            r = abs(corr_matrix[idx, sel_idx])
            if r > CORRELATION_THRESHOLD:
                skipped_corr.append((fname, feature_names[sel_idx], r))
                too_correlated = True
                break
        if too_correlated:
            continue

        selected_idx.append(idx)
        if group is not None:
            group_counts[group] = group_counts.get(group, 0) + 1

    if skipped_group:
        log(f"  Group-capped {len(skipped_group)} features:")
        for fname, group in skipped_group[:10]:
            log(f"    {fname.split('__',1)[-1]} (group '{group}' full)")
        if len(skipped_group) > 10:
            log(f"    ... and {len(skipped_group)-10} more")
    if skipped_corr:
        log(f"  Correlation-skipped {len(skipped_corr)} features:")
        for fname, corr_with, r in skipped_corr[:6]:
            log(f"    {fname.split('__',1)[-1]} (r={r:.2f} with {corr_with.split('__',1)[-1]})")
        if len(skipped_corr) > 6:
            log(f"    ... and {len(skipped_corr)-6} more")

    # Log group allocation
    if group_counts:
        log(f"  Group slots used: {', '.join(f'{g}={n}' for g, n in sorted(group_counts.items()))}")

    # Map selected indices back to original (pre-rare-filter) feature space
    top_idx = np.array([orig_indices[i] for i in selected_idx])
    selected_names = [feature_names[i] for i in selected_idx]
    return top_idx, selected_names, importance


def run_fast(config=None, temporal_only=False):
    """GB-only walk-forward with per-year feature selection and curated features."""
    if config:
        set_config(config)
    from walk_forward_modeling import OUTPUT_DIR, YEAR_START, YEAR_END

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Load tuned GB hyperparameters
    tuned_path = Path(__file__).resolve().parent / "tuned_params.json"
    gb_params = {}
    if tuned_path.exists():
        with open(tuned_path) as f:
            gb_params = json.load(f).get("gb", {}).get("params", {})
        log(f"Loaded tuned GB params from {tuned_path.name}")

    import time as _time
    t0 = _time.time()

    log("Loading data...")
    df = load_data()
    log(f"Loaded {len(df):,} rows, years {df['year'].min()}-{df['year'].max()} ({_time.time()-t0:.1f}s)")

    df = df[df["solar_next_year"].isin([0, 1])]
    log(f"After excluding already-solar (solar_next_year=2): {len(df):,} rows")
    df["time_at_risk"] = df["year"] - YEAR_START

    # Use only curated features that exist in the data
    available = set(df.columns)
    candidate_features = TEMPORAL_FEATURES if temporal_only else ALL_CURATED_FEATURES
    if temporal_only:
        log("*** TEMPORAL-ONLY MODE: using only time-varying features ***")
    feature_cols = [c for c in candidate_features if c in available]
    missing = [c for c in candidate_features if c not in available]
    if missing:
        log(f"Note: {len(missing)} curated features not in data: {missing[:10]}{'...' if len(missing)>10 else ''}")
    log(f"Using {len(feature_cols)} {'temporal' if temporal_only else 'curated'} feature columns")

    # Auto-detect first year with positives — skip everything before
    pos_by_year = df[df["solar_next_year"] == 1].groupby("year").size()
    if len(pos_by_year) == 0:
        log("ERROR: No positives in data.")
        return
    first_pos_year = int(pos_by_year.index.min())
    # install_year = first_pos_year + 1 (feature_year with positives = first_pos_year)
    # But we need at least 1 year of training data, so first trainable install_year = first_pos_year + 1
    first_install_year = first_pos_year + 1
    log(f"First year with positives: {first_pos_year} → first install year: {first_install_year}")
    log(f"Skipping years {YEAR_START+1}-{first_install_year-1} (no positives)")

    # Drop rows before the first useful training year to save memory
    min_useful_year = first_pos_year - (TRAIN_YEARS_WINDOW or 0)
    df = df[df["year"] >= min_useful_year]
    log(f"Trimmed to {len(df):,} rows (years {df['year'].min()}-{df['year'].max()})")
    log(f"Unique homes: {df['strap'].nunique():,}")

    # ============================================================
    # ONE-TIME: preprocessor fit on all data (for consistent encoding)
    # ============================================================
    log("\n" + "=" * 60)
    log("FITTING PREPROCESSOR")
    log("=" * 60)

    # Train medians for consistent NaN fill
    train_medians = {}
    for c in feature_cols:
        if df[c].dtype in (np.float64, np.int64, "float64", "int64", "Int64"):
            med = df[c].median()
            if pd.notna(med):
                train_medians[c] = float(med)

    log("  Preparing features...")
    t1 = _time.time()
    X_all_raw = prepare_features_fast(df, feature_cols, train_medians=train_medians)
    log(f"  Prepared in {_time.time()-t1:.1f}s. Fitting preprocessor...")
    t1 = _time.time()
    preprocessor, feature_names_all, _, _ = fit_preprocessor_fast(X_all_raw)
    log(f"  Preprocessor fit in {_time.time()-t1:.1f}s → {len(feature_names_all)} features")

    FS_MAX_ROWS = 100_000

    # ============================================================
    # WALK-FORWARD: per-year feature selection + GB
    # ============================================================
    all_results = []
    all_decile_results = []
    n_years_total = YEAR_END - first_install_year + 1
    year_num = 0

    for install_year in range(first_install_year, YEAR_END + 1):
        year_num += 1
        feature_year = install_year - 1
        if TRAIN_YEARS_WINDOW is not None:
            train_years = [y for y in range(install_year - TRAIN_YEARS_WINDOW, install_year) if y >= YEAR_START]
        else:
            train_years = list(range(YEAR_START, install_year))

        train_df = df[df["year"].isin(train_years)]
        test_df = df[df["year"] == feature_year]

        y_train = train_df["solar_next_year"].astype(int).values
        y_test = test_df["solar_next_year"].astype(int).values
        n_train_pos = int(y_train.sum())
        n_test_pos = int(y_test.sum())

        if len(np.unique(y_train)) < 2:
            continue

        n_installed = int(((df["year"] == feature_year) & (df["solar_next_year"] == 1)).sum())
        elapsed = _time.time() - t0
        log(f"\n{'='*60}")
        log(f"[{year_num}/{n_years_total}] Install year {install_year}: {n_installed:,} installed | train years {train_years} ({elapsed:.0f}s elapsed)")
        log(f"  Train: {len(y_train):,} rows, {n_train_pos} pos ({y_train.mean():.2%}) | Test: {len(y_test):,} rows, {n_test_pos} pos")

        # Prepare + transform
        t_year = _time.time()
        log(f"  Preparing features...")
        X_train_full = np.nan_to_num(
            preprocessor.transform(prepare_features_fast(train_df, feature_cols, train_medians)),
            nan=0.0,
        )
        X_test_full = np.nan_to_num(
            preprocessor.transform(prepare_features_fast(test_df, feature_cols, train_medians)),
            nan=0.0,
        )
        log(f"  Features ready ({_time.time()-t_year:.1f}s)")

        # Per-year feature selection on training data
        log(f"  Feature selection (Lasso/Ridge/ElasticNet)...")
        t_fs = _time.time()
        if X_train_full.shape[0] > FS_MAX_ROWS:
            rng = np.random.default_rng(RANDOM_STATE + install_year)
            pos_idx = np.where(y_train == 1)[0]
            neg_idx = np.where(y_train == 0)[0]
            n_pos_sample = min(len(pos_idx), max(500, FS_MAX_ROWS // 5))
            n_neg_sample = FS_MAX_ROWS - n_pos_sample
            sample_idx = np.concatenate([
                rng.choice(pos_idx, n_pos_sample, replace=False),
                rng.choice(neg_idx, min(n_neg_sample, len(neg_idx)), replace=False),
            ])
            X_fs, y_fs = X_train_full[sample_idx], y_train[sample_idx]
            log(f"    Subsampled {len(y_fs):,} rows ({int(y_fs.sum()):,} pos)")
        else:
            X_fs, y_fs = X_train_full, y_train
        top_idx, selected_names, importance = run_feature_selection(
            X_fs, y_fs, feature_names_all, N_FEATURES_SELECT,
        )
        log(f"  Feature selection done in {_time.time()-t_fs:.1f}s")
        log(f"  Selected {len(selected_names)} features:")
        for r, fname in enumerate(selected_names, 1):
            log(f"    {r:2d}. {fname.split('__',1)[-1]}  (importance={importance.get(fname, 0):.4f})")

        X_train = X_train_full[:, top_idx]
        X_test = X_test_full[:, top_idx]
        log(f"  Training GB...")

        baseline_rate = y_test.mean()

        # Sample weights: exponential decay
        train_years_arr = train_df["year"].values
        sample_weight = SAMPLE_WEIGHT_DECAY ** (train_years_arr.max() - train_years_arr)

        # Gradient Boosting (calibrated)
        gb_base = GradientBoostingClassifier(
            n_estimators=gb_params.get("n_estimators", 200),
            max_depth=gb_params.get("max_depth", 7),
            learning_rate=gb_params.get("learning_rate", 0.03),
            subsample=gb_params.get("subsample", 0.7),
            min_samples_leaf=gb_params.get("min_samples_leaf", 38),
            random_state=RANDOM_STATE,
        )
        model = (
            CalibratedClassifierCV(gb_base, method=CALIBRATION_METHOD, cv=3)
            if USE_CALIBRATION else gb_base
        )
        try:
            model.fit(X_train, y_train, sample_weight=sample_weight)
        except TypeError:
            model.fit(X_train, y_train)

        y_prob = model.predict_proba(X_test)[:, 1]
        log(f"  Trained + predicted in {_time.time()-t_year:.1f}s")
        roc_auc = roc_auc_score(y_test, y_prob) if n_test_pos > 0 and len(np.unique(y_test)) > 1 else 0
        pr_auc = average_precision_score(y_test, y_prob) if n_test_pos > 0 and len(np.unique(y_test)) > 1 else 0
        brier = float(np.mean((y_prob - y_test) ** 2))
        lc = compute_lift_and_capture(y_test, y_prob, baseline_rate)

        log(
            f"  GB: ROC-AUC={roc_auc:.4f} | "
            f"lift@5%={lc.get('lift_5pct',0):.2f}x  capture@5%={lc.get('capture_5pct',0):.2%} | "
            f"lift@10%={lc.get('lift_10pct',0):.2f}x  capture@10%={lc.get('capture_10pct',0):.2%}"
        )

        metrics = {
            "model": "Gradient Boosting", "install_year": install_year,
            "feature_year": feature_year, "roc_auc": roc_auc, "pr_auc": pr_auc,
            "brier_score": brier, "baseline_adoption_rate": baseline_rate,
            "train_n": len(y_train), "test_n": len(y_test),
            "n_train_pos": n_train_pos, "n_test_pos": n_test_pos,
            "selected_features": "|".join(selected_names), **lc,
        }
        all_results.append(metrics)
        for row in compute_decile_lift(y_test, y_prob, baseline_rate):
            all_decile_results.append({"install_year": install_year, **row})
        pd.DataFrame([metrics]).to_csv(OUTPUT_DIR / f"walk_forward_fold_{install_year}.csv", index=False)

        # Final year: save scored homes
        if install_year == YEAR_END:
            # Re-score all homes using full test_df (already all homes in feature_year)
            mask_no_solar = (test_df["solar_next_year"].values == 0)
            out_df = pd.DataFrame({
                "strap": test_df["strap"].values[mask_no_solar],
                "gb_score": y_prob[mask_no_solar],
                "gb_decile": assign_deciles(y_prob[mask_no_solar]),
            })
            out_path = OUTPUT_DIR / f"straps_no_solar_as_of_{install_year}.csv"
            out_df.to_csv(out_path, index=False)
            log(f"  Saved {len(out_df):,} straps without solar: {out_path}")
            # Print final year's full feature ranking
            log(f"\n  Features selected for final year ({install_year}):")
            for r, fname in enumerate(selected_names, 1):
                log(f"    {r:2d}. {fname}  (importance={importance.get(fname, 0):.4f})")

    # ============================================================
    # SUMMARY
    # ============================================================
    if not all_results:
        log("\nNo years had enough positives to train. Done.")
        return

    results_df = pd.DataFrame(all_results)
    log("\n" + "=" * 60)
    log("WALK-FORWARD SUMMARY")
    log("=" * 60)
    for _, row in results_df.iterrows():
        log(
            f"  {int(row['install_year'])}: ROC={row['roc_auc']:.4f}  "
            f"lift@5%={row.get('lift_5pct',0):.2f}x  capture@5%={row.get('capture_5pct',0):.2%}  "
            f"lift@10%={row.get('lift_10pct',0):.2f}x  capture@10%={row.get('capture_10pct',0):.2%}  "
            f"(test_pos={int(row['n_test_pos'])})"
        )

    avg_cols = [c for c in ["roc_auc", "pr_auc", "brier_score", "lift_5pct", "lift_10pct",
                             "capture_5pct", "capture_10pct"] if c in results_df.columns]
    avgs = results_df[avg_cols].mean()
    log(f"\n--- Averages across {len(results_df)} years ---")
    log(f"  ROC-AUC:     {avgs.get('roc_auc', 0):.4f}")
    log(f"  Lift@5%:     {avgs.get('lift_5pct', 0):.2f}x")
    log(f"  Capture@5%:  {avgs.get('capture_5pct', 0):.2%}")
    log(f"  Lift@10%:    {avgs.get('lift_10pct', 0):.2f}x")
    log(f"  Capture@10%: {avgs.get('capture_10pct', 0):.2%}")

    results_df.to_csv(OUTPUT_DIR / "walk_forward_fast_results.csv", index=False)
    log(f"\nSaved: {OUTPUT_DIR / 'walk_forward_fast_results.csv'}")

    if all_decile_results:
        decile_df = pd.DataFrame(all_decile_results)
        decile_df.to_csv(OUTPUT_DIR / "walk_forward_fast_decile_lift.csv", index=False)
        latest = decile_df[decile_df["install_year"] == decile_df["install_year"].max()].sort_values("decile")
        log(f"\n--- Decile lift (install year {int(latest['install_year'].iloc[0])}) ---")
        log(latest[["decile", "lift", "adoption_rate", "n", "captured", "capture_pct"]].to_string(index=False))

    total_time = _time.time() - t0
    log(f"\nDone in {total_time:.0f}s ({total_time/60:.1f} min). Output: {OUTPUT_DIR}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Fast walk-forward: GB-only, curated features, per-year selection")
    parser.add_argument("--config", help="County config name or path")
    parser.add_argument("--temporal-only", action="store_true",
                        help="Use only time-varying features (diagnostic for static feature inflation)")
    args = parser.parse_args()

    config = None
    if args.config:
        sys.path.insert(0, str(PROJECT_ROOT / "src"))
        from pipeline_config import load_config
        config = load_config(args.config)
    run_fast(config, temporal_only=args.temporal_only)
