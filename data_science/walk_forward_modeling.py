#!/usr/bin/env python3
"""
Walk-forward modeling for solar_pv prediction using parsed_permits_by_year.csv.

Uses expanding-window walk-forward validation:
- Start in 2012: train on 2012 data, predict solar installation in 2013
- Move to 2013: train on 2012+2013 data, predict solar installation in 2014
- Continue through 2024: train on 2012..2024, predict solar installation in 2025

Target: solar_next_year (1 = solar installed next year, 0 = not, 2 = already have solar - excluded)
Uses strap-based train/test split for proper out-of-sample evaluation.
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
from sklearn.calibration import CalibratedClassifierCV
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.neural_network import MLPClassifier
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.tree import DecisionTreeClassifier

warnings.filterwarnings("ignore")

# High-scale numeric columns: log-transform before scaling (prices, areas in $ or sqft)
LOG_TRANSFORM_COLS = ["saleprice", "saleprice_int", "sqft", "area_building", "recrdareano", "mainfloorsf", "mainfloorsf_int", "bsmtsf", "carstoragesf", "electricity_use_proxy"]

# Feature selection: top N features to keep per fold (None = use all)
N_FEATURES_SELECT = 25
# Stage 1 candidate pool size for lift rerank (2x final count); only used when USE_LIFT_RERANK=True
N_FEATURES_CANDIDATE = 50
# Stage 2: rerank coefficient-selected candidates by lift (permutation importance)
USE_LIFT_RERANK = True
# Max rows for feature selection (subsample if larger - SAGA is slow on big data).
# Set to None to use all data (slower but no subsampling).
FEATURE_SELECTION_MAX_ROWS = 10_000
# Skip feature selection if fewer than this many positives in train (Lasso/Ridge unstable)
FEATURE_SELECTION_MIN_POSITIVES = 30
# Drop one-hot/binary features with fewer than this many samples (n=1) in train
FEATURE_MIN_SAMPLES = 100
# High-signal features exempt from min-sample filter (battery/ev_charger/heat_pump ~2x adoption lift)
FEATURE_MIN_SAMPLES_EXEMPT = ["battery", "ev_charger", "heat_pump"]

# Feature interactions to add (col_a * col_b). Both columns must exist. Evaluated in evaluate_interactions.py.
# Optional: INTERACTION_TRANSFORMS maps (a, b) -> "log_a"|"log_b"|"log_both"|"sqrt_a"|"sqrt_b"|"sqrt_both" for optimized lift (from analyze_interaction_transforms.py)
INTERACTION_TRANSFORMS: dict[tuple[str, str], str] = {
    ("likely_mortgage_rate", "saleprice"): "log_b",
    ("electricity_use_proxy", "likely_mortgage_rate"): "log_both",
    ("avg_electricity_price", "mainfloorsf"): "log_both",
    ("avg_electricity_price", "average_rate"): "log_a",
    ("avg_electricity_price", "likely_mortgage_rate"): "log_a",
    ("closest_fifty_percentage", "avg_electricity_price"): "log_a",
    ("average_rate", "mainfloorsf"): "log_both",
}
INTERACTION_PAIRS = [
    ("avg_electricity_price", "mainfloorsf"),   # Electricity cost proxy: larger home x higher $/kWh
    ("average_rate", "mainfloorsf"),            # Mortgage sensitivity for larger homes
    ("roof_score", "mainfloorsf"),              # Good roof + large home = more solar potential
    ("closest_fifty_percentage", "avg_electricity_price"),  # Neighbors + high electricity
    # National 30-year mortgage rate interactions
    ("average_rate", "recent_purchase"),
    ("average_rate", "saleprice"),
    ("avg_electricity_price", "average_rate"),
    # likely_mortgage_rate (rate at purchase or refi if >=1 pct lower) - same interactions
    ("likely_mortgage_rate", "recent_purchase"),
    ("likely_mortgage_rate", "saleprice"),
    ("avg_electricity_price", "likely_mortgage_rate"),
    # electricity_use_proxy interactions (high usage × price/rate = strong solar incentive)
    ("electricity_use_proxy", "avg_electricity_price"),
    ("electricity_use_proxy", "likely_mortgage_rate"),
]

# Paths
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_PATH = PROJECT_ROOT / "data" / "working" / "parsed_permits_by_year.csv"
AVG_YEARLY_INTEREST_PATH = PROJECT_ROOT / "data" / "final" / "avg_yearly_interest.csv"
OUTPUT_DIR = PROJECT_ROOT / "data_science" / "output" / "walk_forward"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Columns to exclude from features (identifiers, target, leakage)
EXCLUDE_COLS = [
    "strap", "year", "solar_pv", "solar_next_year", "original_index",
    "owner", "mailadd", "mail_city", "mail_state2", "mail_zip",
    "original_mailing_address", "address", "scity", "original_address",
    "city", "county", "state2", "szip", "szip5", "subdivision",
    "saledate",  # use time_since_sale instead
    "roof_coverdscr",  # insufficient sample size
]

# Optional: drop potential leaky permit flags (battery, ev_charger, etc.) if present
DROP_POTENTIAL_LEAKY_FLAGS = False
POTENTIAL_LEAKY_COLS = ["battery", "ev_charger", "generator", "roof_new_or_replace", "kitchen_bath_remodel"]

# Time columns: convert to 10-year bin factors
TIME_COLS = ["time_since_sale", "time_since_build"]
TIME_BIN_YEARS = 10

# Garage recategorization: reduce cardinality to avoid overfitting
GARAGE_COL = "carstoragetypedscr"
GARAGE_MAP = {
    "0": "no_garage",
    0: "no_garage",
    "ATTACHED GARAGE AREA": "attached_garage",
    "DETACHED GARAGE": "detached_garage",
    "BASEMENT GARAGE AREA": "other",
    "CARPORT AREA": "other",
    "GARAGE SET UP AS A WORKSHOP (ELEC., ETC.) AREA": "other",
    "GARAGE W/ FINISHED WALLS AREA": "other",
}

YEAR_START = 2012
YEAR_END = 2026  # predict solar through 2026 (train on 2012..2025)
TEST_STRAP_FRACTION = 0.2
RANDOM_STATE = 42

# Rolling vs cumulative: None = cumulative (use all years from YEAR_START); int = rolling (use last N years only)
TRAIN_YEARS_WINDOW = 5  # Set to 5 for rolling 5-year window

# Calibration: wrap RF/GB in CalibratedClassifierCV for better probability estimates (boosts lift when baseline shifts)
USE_CALIBRATION = True
CALIBRATION_METHOD = "isotonic"  # "isotonic" or "sigmoid" (Platt)

# Year-specific feature selection: for last install year (e.g. 2025), use only recent N years for feature selection
RECENT_FEATURE_SELECTION_YEARS = 5  # Use 2022-2024 for feature selection when predicting 2025


def get_feature_types(X: pd.DataFrame) -> tuple[list[str], list[str]]:
    """Identify numeric vs categorical columns."""
    numeric = X.select_dtypes(include=[np.number]).columns.tolist()
    categorical = X.select_dtypes(include=["object", "category"]).columns.tolist()
    return numeric, categorical


def _interaction_transform(va: np.ndarray, vb: np.ndarray, name: str) -> np.ndarray:
    """Apply transform to interaction. va, vb are 1d arrays."""
    va = np.asarray(va, dtype=float)
    vb = np.asarray(vb, dtype=float)
    va = np.where(np.isnan(va), np.nanmedian(va), va)
    vb = np.where(np.isnan(vb), np.nanmedian(vb), vb)
    if name == "raw":
        return va * vb
    if name == "log_a":
        return np.log1p(np.maximum(va, 0)) * vb
    if name == "log_b":
        return va * np.log1p(np.maximum(vb, 0))
    if name == "log_both":
        return np.log1p(np.maximum(va, 0)) * np.log1p(np.maximum(vb, 0))
    if name == "sqrt_a":
        return np.sqrt(np.maximum(va, 0)) * vb
    if name == "sqrt_b":
        return va * np.sqrt(np.maximum(vb, 0))
    if name == "sqrt_both":
        return np.sqrt(np.maximum(va, 0)) * np.sqrt(np.maximum(vb, 0))
    return va * vb


def add_interaction_columns(
    X: pd.DataFrame,
    pairs: list[tuple[str, str]],
    df_raw: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Add interaction columns. Uses INTERACTION_TRANSFORMS when set; else raw product."""
    for a, b in pairs:
        if a not in X.columns or b not in X.columns:
            continue
        transform = INTERACTION_TRANSFORMS.get((a, b), "raw")
        if transform != "raw" and df_raw is not None and a in df_raw.columns and b in df_raw.columns:
            va = pd.to_numeric(df_raw[a], errors="coerce").values
            vb = pd.to_numeric(df_raw[b], errors="coerce").values
            if len(va) == len(X):
                X[f"{a}_x_{b}"] = _interaction_transform(va, vb, transform)
            else:
                X[f"{a}_x_{b}"] = _interaction_transform(X[a].values, X[b].values, "raw")
        else:
            va = pd.to_numeric(X[a], errors="coerce")
            vb = pd.to_numeric(X[b], errors="coerce")
            if np.issubdtype(va.dtype, np.number) and np.issubdtype(vb.dtype, np.number):
                med_a = va.median()
                med_b = vb.median()
                X[f"{a}_x_{b}"] = va.fillna(med_a if pd.notna(med_a) else 0) * vb.fillna(med_b if pd.notna(med_b) else 0)
    return X


def add_time_bin_factors(X: pd.DataFrame) -> pd.DataFrame:
    """Convert time_since_sale and time_since_build to categorical bins.
    time_since_sale: 0-10, 10-20, 20-30, 30+ (collapse >=30 into one bin for sample size).
    time_since_build: 10-year bins as before.
    """
    X = X.copy()
    for col in TIME_COLS:
        if col not in X.columns:
            continue
        t = X[col].fillna(X[col].median())
        t = np.maximum(t, 0)
        if col == "time_since_sale":
            # Bins: 0-10, 10-20, 20-30, 30+ (all >=30 in one bin)
            bin_edges = [0, 10, 20, 30, np.inf]
            labels = ["0-10", "10-20", "20-30", "30+"]
            X[f"{col}_bin"] = pd.cut(t, bins=bin_edges, include_lowest=True, right=False, labels=labels)
            X[f"{col}_bin"] = X[f"{col}_bin"].astype(str)
        else:
            t_max = int(t.max()) + 1
            bin_edges = np.arange(0, t_max + TIME_BIN_YEARS, TIME_BIN_YEARS)
            bin_edges = np.unique(bin_edges)
            labels = [f"{int(bin_edges[i])}-{int(bin_edges[i+1])}" for i in range(len(bin_edges) - 1)]
            if len(bin_edges) > 1:
                X[f"{col}_bin"] = pd.cut(t, bins=bin_edges, include_lowest=True, right=False, labels=labels)
                X[f"{col}_bin"] = X[f"{col}_bin"].astype(str)
        X = X.drop(columns=[col], errors="ignore")
    return X


def prepare_features(df: pd.DataFrame, feature_cols: list[str]) -> pd.DataFrame:
    """Prepare feature matrix: log-transform high-scale cols, time bins, missing values, categoricals."""
    X = df[feature_cols].copy()
    # Recategorize garage to reduce overfitting (no_garage, attached_garage, detached_garage, other)
    if GARAGE_COL in X.columns:
        X[GARAGE_COL] = X[GARAGE_COL].apply(lambda v: GARAGE_MAP.get(str(v).strip(), "other"))
    # Log-transform high-scale columns (prices, areas) to compress scale
    for c in LOG_TRANSFORM_COLS:
        if c in X.columns and X[c].dtype in (np.float64, np.int64, "float64", "int64", "Int64"):
            vals = X[c].fillna(X[c].median())
            vals = np.maximum(vals, 1)  # avoid log(0)
            X[c] = np.log1p(vals)
    X = add_time_bin_factors(X)
    X = add_interaction_columns(X, INTERACTION_PAIRS, df_raw=df)
    numeric, categorical = get_feature_types(X)
    for c in numeric:
        if X[c].isnull().any():
            X[c] = X[c].fillna(X[c].median())
    for c in categorical:
        if c in X.columns and X[c].nunique() <= 20:
            X[c] = X[c].fillna("MISSING")
    return X


def fit_preprocessor(X: pd.DataFrame, numeric: list[str], categorical: list[str]):
    """Build and fit ColumnTransformer."""
    transformers = []
    if numeric:
        transformers.append(("num", StandardScaler(), numeric))
    cat_to_use = [c for c in categorical if c in X.columns and X[c].nunique() <= 20]
    if cat_to_use:
        transformers.append((
            "cat",
            OneHotEncoder(handle_unknown="ignore", sparse_output=False),
            cat_to_use,
        ))
    preprocessor = ColumnTransformer(transformers, remainder="drop")
    preprocessor.fit(X)
    return preprocessor


def get_preprocessor_feature_names(
    preprocessor, numeric: list[str], categorical: list[str]
) -> list[str]:
    """
    Get feature names from preprocessor output, robust to sklearn version.
    Tries get_feature_names_out(); fallback: num__ + cat__ prefixes.
    """
    try:
        names = preprocessor.get_feature_names_out()
        if names is not None and len(names) > 0:
            return list(names)
    except (AttributeError, TypeError):
        pass
    # Fallback: build names in same order as ColumnTransformer output
    out = []
    for name, trans, cols in preprocessor.transformers_:
        if name == "num" and cols:
            out.extend(f"num__{c}" for c in cols)
        elif name == "cat" and cols and hasattr(trans, "get_feature_names_out"):
            try:
                cat_names = trans.get_feature_names_out(cols)
            except (TypeError, ValueError):
                cat_names = trans.get_feature_names_out()
            out.extend(f"cat__{n}" for n in cat_names)
    return out


def run_feature_selection_once(
    X: np.ndarray, y: np.ndarray, feature_names: list[str], n_features: int = 25, log=None
) -> tuple[list[str], dict[str, float]]:
    """
    Run Lasso, Ridge, Elastic Net; average importance; return top n_features ranked by avg.
    Subsamples to FEATURE_SELECTION_MAX_ROWS if larger (SAGA is slow on big data).
    Returns (selected_names, importance_by_feature).
    """
    if X.shape[1] <= n_features:
        imp = {f: 1.0 for f in feature_names}
        return feature_names, imp

    # Subsample for speed when dataset is large (skip if FEATURE_SELECTION_MAX_ROWS is None)
    n = X.shape[0]
    if FEATURE_SELECTION_MAX_ROWS is not None and n > FEATURE_SELECTION_MAX_ROWS:
        max_rows = FEATURE_SELECTION_MAX_ROWS
        rng = np.random.default_rng(RANDOM_STATE)
        # Stratify: ensure we keep enough positives
        pos_idx = np.where(y == 1)[0]
        neg_idx = np.where(y == 0)[0]
        n_pos = min(len(pos_idx), max(500, max_rows // 10))
        n_neg = max_rows - n_pos
        idx_pos = rng.choice(pos_idx, min(n_pos, len(pos_idx)), replace=False)
        idx_neg = rng.choice(neg_idx, min(n_neg, len(neg_idx)), replace=False)
        idx = np.concatenate([idx_pos, idx_neg])
        X, y = X[idx], y[idx]
        if log:
            log(f"  (Subsampled to {len(y)} rows for feature selection)")

    # Lasso
    if log:
        log("  Fitting Lasso...")
    lasso = LogisticRegression(
        penalty="l1", solver="saga", C=0.1, max_iter=2000,
        random_state=RANDOM_STATE, class_weight="balanced"
    )
    lasso.fit(X, y)
    coef_lasso = np.abs(lasso.coef_[0])

    # Ridge
    if log:
        log("  Fitting Ridge...")
    ridge = LogisticRegression(
        penalty="l2", solver="lbfgs", C=1.0, max_iter=2000,
        random_state=RANDOM_STATE, class_weight="balanced"
    )
    ridge.fit(X, y)
    coef_ridge = np.abs(ridge.coef_[0])

    # Elastic Net
    if log:
        log("  Fitting Elastic Net...")
    enet = LogisticRegression(
        penalty="elasticnet", solver="saga", l1_ratio=0.5, C=0.1, max_iter=2000,
        random_state=RANDOM_STATE, class_weight="balanced"
    )
    enet.fit(X, y)
    coef_enet = np.abs(enet.coef_[0])

    # Normalize each to [0, 1] and average
    def norm(x: np.ndarray) -> np.ndarray:
        m = x.max()
        return x / m if m > 0 else x
    avg_imp = (norm(coef_lasso) + norm(coef_ridge) + norm(coef_enet)) / 3
    importance_by_feature = {feature_names[i]: float(avg_imp[i]) for i in range(len(feature_names))}
    idx = np.argsort(avg_imp)[::-1][:n_features]
    selected = [feature_names[i] for i in idx]
    return selected, importance_by_feature


def get_feature_indices(selected_names: list[str], all_names: list[str]) -> np.ndarray:
    """Get column indices for selected feature names."""
    name_to_idx = {n: i for i, n in enumerate(all_names)}
    return np.array([name_to_idx[n] for n in selected_names if n in name_to_idx])


def _compute_lift_10pct(y_true: np.ndarray, y_prob: np.ndarray, baseline_rate: float) -> float:
    """Compute lift at top 10% (for reranking)."""
    if y_prob is None or len(y_true) == 0 or baseline_rate <= 0:
        return 0.0
    n = len(y_true)
    k = max(1, int(n * 0.10))
    order = np.argsort(y_prob)[::-1]
    rate_in_top = y_true[order[:k]].mean()
    return float(rate_in_top / baseline_rate) if baseline_rate > 0 else 0.0


def run_lift_rerank(
    X_train_full: np.ndarray,
    y_train: np.ndarray,
    candidate_names: list[str],
    feature_names_fold: list[str],
    train_df: pd.DataFrame,
    n_select: int,
    log=None,
) -> tuple[list[str], dict[str, float]]:
    """
    Stage 2: Rerank candidates by permutation importance for lift.
    Splits train by strap (80/20), fits LR on candidates, computes lift drop when each feature is permuted.
    Returns (top n_select by lift importance, importance_by_feature).
    """
    if len(candidate_names) <= n_select:
        imp = {f: 1.0 for f in candidate_names}
        return candidate_names, imp

    # Strap-based train/val split (no leakage)
    straps = train_df["strap"].unique()
    if len(straps) < 20:
        if log:
            log(f"  (Lift rerank skipped: only {len(straps)} straps)")
        return candidate_names[:n_select], {f: 1.0 for f in candidate_names[:n_select]}

    rng = np.random.default_rng(RANDOM_STATE)
    straps_shuf = rng.permutation(straps)
    n_val = max(1, int(len(straps) * 0.2))
    val_straps = set(straps_shuf[:n_val])
    train_inner_mask = ~train_df["strap"].isin(val_straps).values
    val_inner_mask = train_df["strap"].isin(val_straps).values

    X_tr = X_train_full[train_inner_mask]
    y_tr = y_train[train_inner_mask]
    X_val = X_train_full[val_inner_mask]
    y_val = y_train[val_inner_mask]

    if y_val.sum() < 5:
        if log:
            log(f"  (Lift rerank skipped: too few positives in val)")
        return candidate_names[:n_select], {f: 1.0 for f in candidate_names[:n_select]}

    cand_idx = get_feature_indices(candidate_names, feature_names_fold)
    X_cand_tr = X_tr[:, cand_idx]
    X_cand_val = X_val[:, cand_idx].copy()

    lr = LogisticRegression(
        max_iter=1000, random_state=RANDOM_STATE, class_weight="balanced"
    )
    lr.fit(X_cand_tr, y_tr)
    y_prob = lr.predict_proba(X_cand_val)[:, 1]
    baseline_rate = y_val.mean()
    lift_baseline = _compute_lift_10pct(y_val, y_prob, baseline_rate)

    lift_drop = {}
    for j, fname in enumerate(candidate_names):
        X_perm = X_cand_val.copy()
        perm_idx = rng.permutation(X_perm.shape[0])
        X_perm[:, j] = X_perm[perm_idx, j]
        y_prob_perm = lr.predict_proba(X_perm)[:, 1]
        lift_perm = _compute_lift_10pct(y_val, y_prob_perm, baseline_rate)
        drop = lift_baseline - lift_perm
        lift_drop[fname] = max(0, drop)

    # Rank by lift drop (descending), take top n_select
    sorted_names = sorted(candidate_names, key=lambda f: lift_drop.get(f, 0), reverse=True)
    selected = sorted_names[:n_select]
    importance_by_feature = {f: lift_drop.get(f, 0) for f in candidate_names}
    if log:
        log(f"  Lift rerank: baseline lift={lift_baseline:.2f}x, selected top {n_select} by lift drop")
    return selected, importance_by_feature


def load_data() -> pd.DataFrame:
    """Load parsed_permits_by_year and filter to valid prediction rows."""
    df = pd.read_csv(DATA_PATH)
    df = df[df["year"].between(YEAR_START, YEAR_END)]
    # Merge avg yearly interest on year
    if AVG_YEARLY_INTEREST_PATH.exists():
        interest = pd.read_csv(AVG_YEARLY_INTEREST_PATH)
        df = df.merge(interest, on="year", how="left")
    # Compute solar_next_year if missing (e.g. CSV from older pipeline)
    if "solar_next_year" not in df.columns and "solar_pv" in df.columns and "year" in df.columns:
        df = df.sort_values(["strap", "year"])
        first_solar_year = df[df["solar_pv"] == 1].groupby("strap")["year"].min()
        df = df.merge(first_solar_year.rename("_fsy"), on="strap", how="left")
        df["solar_next_year"] = 0
        df.loc[df["year"] == df["_fsy"] - 1, "solar_next_year"] = 1
        df.loc[df["year"] >= df["_fsy"], "solar_next_year"] = 2
        df.drop(columns=["_fsy"], inplace=True)
    return df


def get_feature_columns(df: pd.DataFrame) -> list[str]:
    """Get list of feature columns (exclude identifiers, target, leakage)."""
    drop = [c for c in EXCLUDE_COLS if c in df.columns]
    candidates = [c for c in df.columns if c not in drop]
    # Keep only numeric and low-cardinality object columns
    feature_cols = []
    for c in candidates:
        if df[c].dtype in (np.float64, np.int64, "float64", "int64", "Int64"):
            feature_cols.append(c)
        elif df[c].dtype == object and df[c].nunique() <= 20:
            feature_cols.append(c)
    return feature_cols


def compute_lift_and_capture(y_true: np.ndarray, y_prob: np.ndarray, baseline_rate: float) -> dict:
    """Compute top-k lift and capture rate. Returns dict with lift/capture for 10%, 5%, 2%."""
    if y_prob is None or len(y_true) == 0 or baseline_rate <= 0:
        return {"lift_10pct": 0, "lift_5pct": 0, "lift_2pct": 0, "lift_20pct": 0, "capture_10pct": 0, "capture_5pct": 0, "capture_2pct": 0, "capture_20pct": 0}
    n = len(y_true)
    n_pos = int(y_true.sum())
    if n_pos == 0:
        return {"lift_10pct": 0, "lift_5pct": 0, "lift_2pct": 0, "lift_20pct": 0, "capture_10pct": 0, "capture_5pct": 0, "capture_2pct": 0, "capture_20pct": 0}
    order = np.argsort(y_prob)[::-1]
    result = {}
    for pct, key in [(0.20, "20pct"), (0.10, "10pct"), (0.05, "5pct"), (0.02, "2pct")]:
        k = max(1, int(n * pct))
        top_k = order[:k]
        rate_in_top = y_true[top_k].mean()
        result[f"lift_{key}"] = rate_in_top / baseline_rate if baseline_rate > 0 else 0
        captured = y_true[top_k].sum()
        result[f"capture_{key}"] = captured / n_pos if n_pos > 0 else 0
    return result


def compute_decile_lift(
    y_true: np.ndarray, y_prob: np.ndarray, baseline_rate: float
) -> list[dict]:
    """Compute lift for each decile (1=top 10% by score, 10=bottom 10%). Returns list of dicts."""
    if y_prob is None or len(y_true) == 0 or baseline_rate <= 0:
        return []
    n = len(y_true)
    n_pos = int(y_true.sum())
    order = np.argsort(y_prob)[::-1]
    deciles = []
    for d in range(10):
        start = int(n * d / 10)
        end = int(n * (d + 1) / 10)
        if start >= end:
            continue
        idx = order[start:end]
        rate = y_true[idx].mean()
        lift = rate / baseline_rate if baseline_rate > 0 else 0
        captured = y_true[idx].sum()
        capture_pct = captured / n_pos if n_pos > 0 else 0
        deciles.append({
            "decile": d + 1,
            "lift": lift,
            "adoption_rate": rate,
            "n": len(idx),
            "captured": int(captured),
            "capture_pct": capture_pct,
        })
    return deciles


def assign_deciles(scores: np.ndarray) -> np.ndarray:
    """Assign decile to each score: 0.5=top 5%, 1=5-10%, 2=10-20%, ..., 10=bottom 10%."""
    n = len(scores)
    if n == 0:
        return np.array([], dtype=float)
    order = np.argsort(scores)[::-1]
    deciles = np.empty(n, dtype=float)
    # Boundaries (exclusive upper): 0-5%, 5-10%, 10-20%, ..., 90-100%
    boundaries = [(0.05, 0.5), (0.10, 1), (0.20, 2), (0.30, 3), (0.40, 4), (0.50, 5),
                  (0.60, 6), (0.70, 7), (0.80, 8), (0.90, 9), (1.01, 10)]
    for i, idx in enumerate(order):
        pct = (i + 1) / n  # cumulative fraction (1st = 1/n, 2nd = 2/n, ...)
        for thresh, val in boundaries:
            if pct <= thresh:
                deciles[idx] = val
                break
    return deciles


def evaluate_model(
    model,
    X_train,
    y_train,
    X_test,
    y_test,
    name: str,
    baseline_rate: float,
    brier_baseline_zero: float,
    brier_baseline_rate: float,
) -> tuple[dict, np.ndarray | None]:
    """Train model and return metrics on test set. Also returns y_prob for calibration."""
    model.fit(X_train, y_train)
    y_pred = model.predict(X_test)
    y_prob = model.predict_proba(X_test)[:, 1] if hasattr(model, "predict_proba") else None

    n_test_pos = int(y_test.sum())
    roc_auc = (
        roc_auc_score(y_test, y_prob)
        if y_prob is not None and len(np.unique(y_test)) > 1 and n_test_pos > 0
        else 0
    )
    pr_auc = (
        average_precision_score(y_test, y_prob)
        if y_prob is not None and len(np.unique(y_test)) > 1 and n_test_pos > 0
        else 0
    )
    brier = float(np.mean((y_prob - y_test) ** 2)) if y_prob is not None else 0
    brier_improvement_vs_rate = brier_baseline_rate - brier

    lift_capture = compute_lift_and_capture(y_test, y_prob, baseline_rate) if y_prob is not None else {}

    metrics = {
        "model": name,
        "accuracy": accuracy_score(y_test, y_pred),
        "precision": precision_score(y_test, y_pred, zero_division=0),
        "recall": recall_score(y_test, y_pred, zero_division=0),
        "f1": f1_score(y_test, y_pred, zero_division=0),
        "roc_auc": roc_auc,
        "pr_auc": pr_auc,
        "brier_score": brier,
        "brier_baseline_zero": brier_baseline_zero,
        "brier_baseline_rate": brier_baseline_rate,
        "brier_improvement_vs_rate": brier_improvement_vs_rate,
        "baseline_adoption_rate": baseline_rate,
        **lift_capture,
    }
    return metrics, y_prob, model


def metrics_from_proba(
    y_test: np.ndarray,
    y_prob: np.ndarray,
    name: str,
    baseline_rate: float,
    brier_baseline_zero: float,
    brier_baseline_rate: float,
) -> dict:
    """Compute metrics from predicted probabilities (for ensemble, no model fit)."""
    y_pred = (y_prob >= 0.5).astype(int) if y_prob is not None else np.zeros_like(y_test)
    n_test_pos = int(y_test.sum())
    roc_auc = (
        roc_auc_score(y_test, y_prob)
        if y_prob is not None and len(np.unique(y_test)) > 1 and n_test_pos > 0
        else 0
    )
    pr_auc = (
        average_precision_score(y_test, y_prob)
        if y_prob is not None and len(np.unique(y_test)) > 1 and n_test_pos > 0
        else 0
    )
    brier = float(np.mean((y_prob - y_test) ** 2)) if y_prob is not None else 0
    brier_improvement_vs_rate = brier_baseline_rate - brier
    lift_capture = compute_lift_and_capture(y_test, y_prob, baseline_rate) if y_prob is not None else {}
    return {
        "model": name,
        "accuracy": accuracy_score(y_test, y_pred),
        "precision": precision_score(y_test, y_pred, zero_division=0),
        "recall": recall_score(y_test, y_pred, zero_division=0),
        "f1": f1_score(y_test, y_pred, zero_division=0),
        "roc_auc": roc_auc,
        "pr_auc": pr_auc,
        "brier_score": brier,
        "brier_baseline_zero": brier_baseline_zero,
        "brier_baseline_rate": brier_baseline_rate,
        "brier_improvement_vs_rate": brier_improvement_vs_rate,
        "baseline_adoption_rate": baseline_rate,
        **lift_capture,
    }


def _model_coef_summary(model) -> str:
    """Return a short coefficient/importance summary for logging."""
    if hasattr(model, "coef_") and model.coef_ is not None:
        c = np.abs(model.coef_[0])
        return f"max|coef|={c.max():.4f}" if len(c) > 0 else ""
    if hasattr(model, "feature_importances_"):
        fi = model.feature_importances_
        return f"max_imp={fi.max():.4f}" if len(fi) > 0 else ""
    if hasattr(model, "coefs_") and model.coefs_:
        # MLPClassifier: coefs_ is list of weight arrays
        flat = np.concatenate([np.abs(c).ravel() for c in model.coefs_])
        return f"max|w|={flat.max():.4f}" if len(flat) > 0 else ""
    return ""


def run_walk_forward() -> None:
    """Run walk-forward modeling from 2012 through predicting 2025."""
    def log(msg: str) -> None:
        print(msg, flush=True)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    log("Loading data...")
    df = load_data()
    log(f"Loaded {len(df)} rows, years {df['year'].min()}-{df['year'].max()}")

    # Scale diagnostic: report high-variance numeric features before transform
    num_cols = [c for c in df.columns if c in LOG_TRANSFORM_COLS and c in df.columns]
    if num_cols:
        for c in num_cols[:5]:
            s = df[c].dropna()
            if len(s) > 0:
                log(f"  Scale check: {c} range [{s.min():.0f}, {s.max():.0f}], std={s.std():.0f} (will log-transform)")

    # Filter to rows with valid target (0 or 1; exclude 2 = already have solar)
    df = df[df["solar_next_year"].isin([0, 1])]
    log(f"After excluding solar_next_year=2: {len(df)} rows")

    feature_cols = get_feature_columns(df)
    if DROP_POTENTIAL_LEAKY_FLAGS:
        leaky_set = set(POTENTIAL_LEAKY_COLS)
        dropped = [c for c in feature_cols if c in leaky_set]
        feature_cols = [c for c in feature_cols if c not in leaky_set]
        if dropped:
            log(f"Dropped potential leaky flags: {dropped}")
    log(f"Using {len(feature_cols)} feature columns")

    # Strap-based split: same straps for all folds
    straps = df["strap"].unique()
    np.random.seed(RANDOM_STATE)
    np.random.shuffle(straps)
    n_test = max(1, int(len(straps) * TEST_STRAP_FRACTION))
    test_straps = set(straps[:n_test])
    train_straps = set(straps[n_test:])
    log(f"Train straps: {len(train_straps)}, Test straps: {len(test_straps)}")

    rf_base = RandomForestClassifier(
        n_estimators=100, random_state=RANDOM_STATE, max_depth=10, class_weight="balanced"
    )
    gb_base = GradientBoostingClassifier(
        n_estimators=100, max_depth=5, random_state=RANDOM_STATE
    )
    models = {
        "Random Forest": (
            CalibratedClassifierCV(rf_base, method=CALIBRATION_METHOD, cv=3)
            if USE_CALIBRATION
            else rf_base
        ),
        "Gradient Boosting": (
            CalibratedClassifierCV(gb_base, method=CALIBRATION_METHOD, cv=3)
            if USE_CALIBRATION
            else gb_base
        ),
    }
    try:
        import xgboost as xgb
        models["XGBoost"] = xgb.XGBClassifier(
            n_estimators=100, max_depth=5, random_state=RANDOM_STATE,
            scale_pos_weight=50,  # approximate 1/0.02 for ~2% positive rate
        )
    except ImportError:
        pass
    models["Neural Net"] = MLPClassifier(
        hidden_layer_sizes=(64, 32),
        max_iter=500,
        random_state=RANDOM_STATE,
        early_stopping=True,
    )

    all_results = []
    all_decile_results: list[dict] = []
    feature_importance_by_year: dict[int, dict[str, float]] = {}  # install_year -> {feat: importance}
    for install_year in range(YEAR_START + 1, YEAR_END + 1):
        # install_year = year solar gets installed (what we predict)
        # feature_year = install_year - 1 (year of features; test uses rows with year == feature_year)
        feature_year = install_year - 1
        if TRAIN_YEARS_WINDOW is not None:
            train_years = list(range(install_year - TRAIN_YEARS_WINDOW, install_year))
            train_years = [y for y in train_years if y >= YEAR_START]
        else:
            train_years = list(range(YEAR_START, install_year))
        n_installed = int(((df["year"] == feature_year) & (df["solar_next_year"] == 1)).sum())
        log(f"\n{'='*60}")
        log(f"Install year {install_year}: {n_installed:,} homes installed solar | train on feature years {train_years} ({'rolling' if TRAIN_YEARS_WINDOW else 'cumulative'})")
        log("=" * 60)

        train_df = df[
            (df["year"].isin(train_years)) &
            (df["strap"].isin(train_straps))
        ]
        test_df = df[
            (df["year"] == feature_year) &
            (df["strap"].isin(test_straps))
        ]

        if len(train_df) < 10 or len(test_df) < 5:
            log(f"  Skipping: too few samples (train={len(train_df)}, test={len(test_df)})")
            continue

        y_train = train_df["solar_next_year"].astype(int).values
        y_test = test_df["solar_next_year"].astype(int).values

        X_train_raw = prepare_features(train_df, feature_cols)
        X_test_raw = prepare_features(test_df, feature_cols)

        # Fit preprocessor on this fold's training data only (no look-ahead leakage)
        numeric_fold, categorical_fold = get_feature_types(X_train_raw)
        preprocessor = fit_preprocessor(X_train_raw, numeric_fold, categorical_fold)
        X_train_full = preprocessor.transform(X_train_raw)
        X_test_full = preprocessor.transform(X_test_raw)

        # Get feature names (robust to sklearn version)
        feature_names_fold = get_preprocessor_feature_names(
            preprocessor, numeric_fold, categorical_fold
        )
        if len(feature_names_fold) != X_train_full.shape[1]:
            raise ValueError(
                f"Feature name count ({len(feature_names_fold)}) != transformed columns ({X_train_full.shape[1]})"
            )

        # Drop low-sample features (one-hot with n=1 < FEATURE_MIN_SAMPLES), except high-signal exempt
        keep_mask = np.ones(X_train_full.shape[1], dtype=bool)
        dropped_low_sample = []
        for i, fname in enumerate(feature_names_fold):
            col = X_train_full[:, i]
            is_binary = np.all(np.isin(col, [0, 1]))
            if is_binary:
                n_count = int((col == 1).sum())
                is_exempt = any(ex in fname for ex in FEATURE_MIN_SAMPLES_EXEMPT)
                if n_count < FEATURE_MIN_SAMPLES and not is_exempt:
                    keep_mask[i] = False
                    dropped_low_sample.append((fname, n_count))
        if dropped_low_sample:
            log(f"  Dropped {len(dropped_low_sample)} low-sample features (n<{FEATURE_MIN_SAMPLES}): {[(f, n) for f, n in dropped_low_sample[:5]]}{'...' if len(dropped_low_sample) > 5 else ''}")
        X_train_full = X_train_full[:, keep_mask]
        X_test_full = X_test_full[:, keep_mask]
        feature_names_fold = [f for f, k in zip(feature_names_fold, keep_mask) if k]

        # Feature selection on this fold's training data only
        # For last install year, use only recent years for feature selection (captures current market patterns)
        use_recent_for_fs = (
            install_year == YEAR_END
            and RECENT_FEATURE_SELECTION_YEARS is not None
            and (TRAIN_YEARS_WINDOW is None or TRAIN_YEARS_WINDOW >= RECENT_FEATURE_SELECTION_YEARS)
        )
        if use_recent_for_fs:
            train_df_fs = train_df[train_df["year"] >= install_year - RECENT_FEATURE_SELECTION_YEARS]
            X_train_fs_raw = prepare_features(train_df_fs, feature_cols)
            X_train_fs = preprocessor.transform(X_train_fs_raw)[:, keep_mask]
            y_train_fs = train_df_fs["solar_next_year"].astype(int).values
            n_pos_fs = int(y_train_fs.sum())
            log(f"  Feature selection on recent {RECENT_FEATURE_SELECTION_YEARS} years only ({len(y_train_fs)} rows, {n_pos_fs} positives)")
        else:
            train_df_fs = train_df
            X_train_fs = X_train_full
            y_train_fs = y_train
            n_pos_fs = int(y_train.sum())

        selected_features = feature_names_fold
        selected_idx = np.arange(X_train_full.shape[1])
        importance_by_feat = {}
        n_pos = int(y_train.sum())
        if N_FEATURES_SELECT and X_train_full.shape[1] > N_FEATURES_SELECT:
            if n_pos_fs < FEATURE_SELECTION_MIN_POSITIVES:
                log(f"  Skipping feature selection: only {n_pos_fs} positives (min={FEATURE_SELECTION_MIN_POSITIVES})")
            else:
                try:
                    n_cand = min(N_FEATURES_CANDIDATE, X_train_full.shape[1]) if USE_LIFT_RERANK else N_FEATURES_SELECT
                    candidates, importance_by_feat = run_feature_selection_once(
                        X_train_fs, y_train_fs, feature_names_fold, n_cand, log=log
                    )
                    if USE_LIFT_RERANK and len(candidates) > N_FEATURES_SELECT:
                        selected_features, importance_by_feat = run_lift_rerank(
                            X_train_fs,
                            y_train_fs,
                            candidates,
                            feature_names_fold,
                            train_df_fs,
                            N_FEATURES_SELECT,
                            log=log,
                        )
                    else:
                        selected_features = candidates[:N_FEATURES_SELECT]
                    selected_idx = get_feature_indices(selected_features, feature_names_fold)
                    log(f"  Selected {len(selected_features)} features for install year {install_year}")
                except Exception as e:
                    log(f"  Feature selection failed ({e}), using all features")
        X_train = X_train_full[:, selected_idx]
        X_test = X_test_full[:, selected_idx]
        used_feature_names = selected_features

        # Get Lasso coefficients for all features (for printing; also used for stability)
        try:
            lasso = LogisticRegression(
                penalty="l1", solver="saga", C=0.1, max_iter=2000,
                random_state=RANDOM_STATE, class_weight="balanced"
            )
            lasso.fit(X_train_full, y_train)
            coef_by_feat = {f: float(np.abs(c)) for f, c in zip(feature_names_fold, lasso.coef_[0])}
            feature_importance_by_year[install_year] = coef_by_feat
        except Exception:
            coef_by_feat = {}
        if not importance_by_feat:
            importance_by_feat = coef_by_feat

        # Print selected features with counts and coefficients
        log(f"  Selected features for install year {install_year}:")
        for r, fname in enumerate(used_feature_names, 1):
            col = X_train[:, r - 1]
            is_binary = np.all(np.isin(col, [0, 1]))
            coef_val = importance_by_feat.get(fname, np.nan)
            coef_str = f"  coef={coef_val:.4f}" if not np.isnan(coef_val) else ""
            if is_binary:
                n_count = int((col == 1).sum())
                log(f"    {r:2d}. {fname}  n=1: {n_count:,}{coef_str}")
            else:
                n_nonzero = int((col != 0).sum())
                log(f"    {r:2d}. {fname}  n_nonzero: {n_nonzero:,}{coef_str}")

        pos_rate_train = y_train.mean()
        baseline_rate = pos_rate_test = y_test.mean()
        n_train_pos = int(y_train.sum())
        n_test_pos = int(y_test.sum())
        log(f"  Train: {len(y_train)} rows, {n_train_pos} positives ({pos_rate_train:.2%})")
        log(f"  Test:  {len(y_test)} rows, {n_test_pos} positives, baseline adoption rate={baseline_rate:.2%}")

        # Baseline Brier scores for comparison
        brier_baseline_zero = float(np.mean((0 - y_test) ** 2))
        brier_baseline_rate = float(np.mean((baseline_rate - y_test) ** 2))
        log(f"  Brier baselines: zero={brier_baseline_zero:.4f}, rate={brier_baseline_rate:.4f}")

        # Guard: skip model training if train has <2 classes
        if len(np.unique(y_train)) < 2:
            log(f"  Skipping: y_train has only one class")
            continue

        fold_results = []
        lr_y_prob = None
        model_probs = {}
        for name, model in models.items():
            metrics, y_prob, fitted_model = evaluate_model(
                model,
                X_train,
                y_train,
                X_test,
                y_test,
                name,
                baseline_rate,
                brier_baseline_zero,
                brier_baseline_rate,
            )
            metrics["install_year"] = install_year
            metrics["feature_year"] = feature_year
            metrics["train_n"] = len(y_train)
            metrics["test_n"] = len(y_test)
            fold_results.append(metrics)
            all_results.append(metrics)
            if y_prob is not None:
                model_probs[name] = y_prob
            # if name == "Logistic Regression":
            #     lr_y_prob = y_prob
            # Decile lift
            for row in compute_decile_lift(y_test, y_prob, baseline_rate):
                all_decile_results.append({
                    "model": name,
                    "install_year": install_year,
                    "feature_year": feature_year,
                    **row,
                })
            coef_str = _model_coef_summary(fitted_model)
            coef_part = f" [{coef_str}]" if coef_str else ""
            log(
                f"  {name}: ROC-AUC={metrics['roc_auc']:.4f}, PR-AUC={metrics['pr_auc']:.4f}, "
                f"Brier={metrics['brier_score']:.4f} (Δvs_rate={metrics['brier_improvement_vs_rate']:+.4f}){coef_part} | "
                f"lift@20/10/5/2%={metrics.get('lift_20pct', 0):.2f}/{metrics.get('lift_10pct', 0):.2f}/{metrics.get('lift_5pct', 0):.2f}/{metrics.get('lift_2pct', 0):.2f}x | "
                f"capture@20/10/5/2%={metrics.get('capture_20pct', 0):.2%}/{metrics.get('capture_10pct', 0):.2%}/{metrics.get('capture_5pct', 0):.2%}/{metrics.get('capture_2pct', 0):.2%}"
            )

        # RF + GB ensemble: average predicted probabilities
        if "Random Forest" in model_probs and "Gradient Boosting" in model_probs:
            y_prob_ens = (model_probs["Random Forest"] + model_probs["Gradient Boosting"]) / 2
            metrics_ens = metrics_from_proba(
                y_test, y_prob_ens, "RF+GB Ensemble",
                baseline_rate, brier_baseline_zero, brier_baseline_rate,
            )
            metrics_ens["install_year"] = install_year
            metrics_ens["feature_year"] = feature_year
            metrics_ens["train_n"] = len(y_train)
            metrics_ens["test_n"] = len(y_test)
            fold_results.append(metrics_ens)
            all_results.append(metrics_ens)
            for row in compute_decile_lift(y_test, y_prob_ens, baseline_rate):
                all_decile_results.append({
                    "model": "RF+GB Ensemble",
                    "install_year": install_year,
                    "feature_year": feature_year,
                    **row,
                })
            log(
                f"  RF+GB Ensemble: ROC-AUC={metrics_ens['roc_auc']:.4f}, PR-AUC={metrics_ens['pr_auc']:.4f}, "
                f"Brier={metrics_ens['brier_score']:.4f} (Δvs_rate={metrics_ens['brier_improvement_vs_rate']:+.4f}) | "
                f"lift@20/10/5/2%={metrics_ens.get('lift_20pct', 0):.2f}/{metrics_ens.get('lift_10pct', 0):.2f}/{metrics_ens.get('lift_5pct', 0):.2f}/{metrics_ens.get('lift_2pct', 0):.2f}x | "
                f"capture@20/10/5/2%={metrics_ens.get('capture_20pct', 0):.2%}/{metrics_ens.get('capture_10pct', 0):.2%}/{metrics_ens.get('capture_5pct', 0):.2%}/{metrics_ens.get('capture_2pct', 0):.2%}"
            )

            # Hybrid: 70% Gradient Boosting + 30% RF+GB Ensemble
            y_prob_hybrid = 0.7 * model_probs["Gradient Boosting"] + 0.3 * y_prob_ens
            metrics_hybrid = metrics_from_proba(
                y_test, y_prob_hybrid, "GB+Ensemble Hybrid (70/30)",
                baseline_rate, brier_baseline_zero, brier_baseline_rate,
            )
            metrics_hybrid["install_year"] = install_year
            metrics_hybrid["feature_year"] = feature_year
            metrics_hybrid["train_n"] = len(y_train)
            metrics_hybrid["test_n"] = len(y_test)
            fold_results.append(metrics_hybrid)
            all_results.append(metrics_hybrid)
            for row in compute_decile_lift(y_test, y_prob_hybrid, baseline_rate):
                all_decile_results.append({
                    "model": "GB+Ensemble Hybrid (70/30)",
                    "install_year": install_year,
                    "feature_year": feature_year,
                    **row,
                })
            log(
                f"  GB+Ensemble Hybrid (70/30): ROC-AUC={metrics_hybrid['roc_auc']:.4f}, PR-AUC={metrics_hybrid['pr_auc']:.4f}, "
                f"Brier={metrics_hybrid['brier_score']:.4f} (Δvs_rate={metrics_hybrid['brier_improvement_vs_rate']:+.4f}) | "
                f"lift@20/10/5/2%={metrics_hybrid.get('lift_20pct', 0):.2f}/{metrics_hybrid.get('lift_10pct', 0):.2f}/{metrics_hybrid.get('lift_5pct', 0):.2f}/{metrics_hybrid.get('lift_2pct', 0):.2f}x | "
                f"capture@20/10/5/2%={metrics_hybrid.get('capture_20pct', 0):.2%}/{metrics_hybrid.get('capture_10pct', 0):.2%}/{metrics_hybrid.get('capture_5pct', 0):.2%}/{metrics_hybrid.get('capture_2pct', 0):.2%}"
            )

            # Output straps without solar as of install_year (for YEAR_END only)
            if install_year == YEAR_END:
                full_df = df[(df["year"] == feature_year)]
                X_full_raw = prepare_features(full_df, feature_cols)
                X_full = preprocessor.transform(X_full_raw)[:, keep_mask][:, selected_idx]
                y_prob_gb_full = models["Gradient Boosting"].predict_proba(X_full)[:, 1]
                y_prob_rf_full = models["Random Forest"].predict_proba(X_full)[:, 1]
                y_prob_ens_full = (y_prob_rf_full + y_prob_gb_full) / 2
                y_prob_hybrid_full = 0.7 * y_prob_gb_full + 0.3 * y_prob_ens_full
                mask_no_solar = (full_df["solar_next_year"].values == 0)
                straps_no_solar = full_df["strap"].values[mask_no_solar]
                gb_scores = y_prob_gb_full[mask_no_solar]
                ens_scores = y_prob_ens_full[mask_no_solar]
                hybrid_scores = y_prob_hybrid_full[mask_no_solar]
                out_df = pd.DataFrame({
                    "strap": straps_no_solar,
                    "gb_score": gb_scores,
                    "gb_decile": assign_deciles(gb_scores),
                    "ensemble_score": ens_scores,
                    "ensemble_decile": assign_deciles(ens_scores),
                    "hybrid_score": hybrid_scores,
                    "hybrid_decile": assign_deciles(hybrid_scores),
                })
                out_path = OUTPUT_DIR / f"straps_no_solar_as_of_{install_year}.csv"
                out_df.to_csv(out_path, index=False)
                log(f"  Saved {len(out_df):,} straps without solar as of {install_year}: {out_path}")

        # LogReg Calibrated: CalibratedClassifierCV (sigmoid default, isotonic when n_pos >= 200)
        # if n_train_pos >= 2:
        #     cal_method = "isotonic" if n_train_pos >= 200 else "sigmoid"
        #     lr_cal = CalibratedClassifierCV(
        #         LogisticRegression(
        #             max_iter=2000, random_state=RANDOM_STATE, class_weight="balanced"
        #         ),
        #         method=cal_method,
        #         cv=5,
        #     )
        #     metrics_cal, _ = evaluate_model(
        #         lr_cal,
        #         X_train,
        #         y_train,
        #         X_test,
        #         y_test,
        #         "LogReg Calibrated",
        #         baseline_rate,
        #         brier_baseline_zero,
        #         brier_baseline_rate,
        #     )
        #     metrics_cal["install_year"] = install_year
        #     metrics_cal["feature_year"] = feature_year
        #     metrics_cal["train_n"] = len(y_train)
        #     metrics_cal["test_n"] = len(y_test)
        #     fold_results.append(metrics_cal)
        #     all_results.append(metrics_cal)
        #     cal_y_prob = lr_cal.predict_proba(X_test)[:, 1]
        #     for row in compute_decile_lift(y_test, cal_y_prob, baseline_rate):
        #         all_decile_results.append({
        #             "model": "LogReg Calibrated",
        #             "install_year": install_year,
        #             "feature_year": feature_year,
        #             **row,
        #         })
        #     log(
        #         f"  LogReg Calibrated ({cal_method}): ROC-AUC={metrics_cal['roc_auc']:.4f}, PR-AUC={metrics_cal['pr_auc']:.4f}, "
        #         f"Brier={metrics_cal['brier_score']:.4f} (Δvs_rate={metrics_cal['brier_improvement_vs_rate']:+.4f})"
        #     )

        # Per-year fold diagnostics CSV
        fold_df = pd.DataFrame(fold_results)
        fold_df["n_train_positives"] = n_train_pos
        fold_df["n_test_positives"] = n_test_pos
        fold_df.to_csv(OUTPUT_DIR / f"walk_forward_fold_{install_year}.csv", index=False)

        # Calibration curve (reliability diagram) for Logistic Regression
        if lr_y_prob is not None and len(np.unique(y_test)) > 1:
            n_bins = 10
            bin_edges = np.linspace(0, 1, n_bins + 1)
            bin_indices = np.digitize(lr_y_prob, bin_edges) - 1
            bin_indices = np.clip(bin_indices, 0, n_bins - 1)
            bin_means_true = np.array([
                y_test[bin_indices == b].mean() if (bin_indices == b).any() else np.nan
                for b in range(n_bins)
            ])
            bin_means_pred = np.array([
                lr_y_prob[bin_indices == b].mean() if (bin_indices == b).any() else np.nan
                for b in range(n_bins)
            ])
            valid = ~(np.isnan(bin_means_true) | np.isnan(bin_means_pred))
            fig, ax = plt.subplots(figsize=(6, 5))
            ax.plot([0, 1], [0, 1], "k--", label="Perfect")
            ax.plot(bin_means_pred[valid], bin_means_true[valid], "s-", color="steelblue", label="Model")
            ax.set_xlabel("Mean predicted probability")
            ax.set_ylabel("Fraction of positives")
            ax.set_title(f"Calibration curve (install year {install_year})")
            ax.legend()
            ax.grid(True, alpha=0.3)
            plt.tight_layout()
            plt.savefig(OUTPUT_DIR / f"calibration_predict_{install_year}_{ts}.png", dpi=150)
            plt.close()

    # Summary
    results_df = pd.DataFrame(all_results)
    metric_cols = [
        "feature_year",
        "f1", "roc_auc", "pr_auc", "brier_score", "brier_baseline_zero", "brier_baseline_rate",
        "brier_improvement_vs_rate", "accuracy", "precision", "recall",
        "baseline_adoption_rate", "lift_20pct", "lift_10pct", "lift_5pct", "lift_2pct",
        "capture_20pct", "capture_10pct", "capture_5pct", "capture_2pct",
    ]
    agg_dict = {c: "first" for c in metric_cols if c in results_df.columns}
    summary = results_df.groupby(["model", "install_year"]).agg(agg_dict).reset_index()
    summary["feature_year"] = summary["install_year"] - 1

    log("\n" + "=" * 60)
    log("WALK-FORWARD SUMMARY (per year)")
    log("=" * 60)
    log(summary.to_string(index=False))

    # Year-over-year metric stability (std across years)
    stability_cols = [c for c in ["roc_auc", "pr_auc", "f1", "brier_score", "lift_20pct", "lift_10pct", "lift_5pct", "lift_2pct", "capture_20pct", "capture_10pct", "capture_5pct", "capture_2pct"] if c in results_df.columns]
    yoy_stability = None
    if stability_cols:
        yoy_stability = results_df.groupby("model")[stability_cols].std().round(4)
        yoy_stability.columns = [f"{c}_std" for c in stability_cols]
        log("\n--- Year-over-year metric stability (std across years) ---")
        log(str(yoy_stability))

    # Feature importance stability: use union of all feature names for consistent vector ordering
    feat_stability = None
    if len(feature_importance_by_year) >= 2:
        all_feat_names = sorted(set().union(*(d.keys() for d in feature_importance_by_year.values())))
        if len(all_feat_names) >= 3:
            years = sorted(feature_importance_by_year.keys())
            corrs = []
            for i in range(len(years) - 1):
                y1, y2 = years[i], years[i + 1]
                imp1 = feature_importance_by_year[y1]
                imp2 = feature_importance_by_year[y2]
                v1 = np.array([imp1.get(f, 0) for f in all_feat_names])
                v2 = np.array([imp2.get(f, 0) for f in all_feat_names])
                if v1.std() > 1e-10 and v2.std() > 1e-10:
                    r = np.corrcoef(v1, v2)[0, 1]
                    corrs.append((y1, y2, r))
            if corrs:
                feat_stability = np.mean([c[2] for c in corrs])
                log(f"\n--- Feature importance stability (mean corr year-to-year, {len(all_feat_names)} features): {feat_stability:.4f} ---")
                for y1, y2, r in corrs:
                    log(f"  install {y1}->{y2}: {r:.4f}")
                pd.DataFrame(corrs, columns=["install_year_from", "install_year_to", "correlation"]).to_csv(
                    OUTPUT_DIR / "walk_forward_feature_importance_stability.csv", index=False
                )

    # Average metrics by model across years
    avg_cols = ["f1", "roc_auc", "pr_auc", "brier_score", "accuracy", "lift_20pct", "lift_10pct", "lift_5pct", "lift_2pct", "capture_20pct", "capture_10pct", "capture_5pct", "capture_2pct"]
    avg_cols = [c for c in avg_cols if c in results_df.columns]
    avg_by_model = results_df.groupby("model")[avg_cols].mean().round(4)
    log("\n--- Average by model (across years) ---")
    core_cols = [c for c in ["f1", "roc_auc", "pr_auc", "brier_score", "accuracy"] if c in avg_by_model.columns]
    if core_cols:
        log(str(avg_by_model[core_cols]))
    lift_cols = [c for c in ["lift_20pct", "lift_10pct", "lift_5pct", "lift_2pct", "capture_20pct", "capture_10pct", "capture_5pct", "capture_2pct"] if c in avg_by_model.columns]
    if lift_cols:
        log(str(avg_by_model[lift_cols]))

    results_df.to_csv(OUTPUT_DIR / "walk_forward_metrics.csv", index=False)
    summary.to_csv(OUTPUT_DIR / "walk_forward_summary.csv", index=False)
    if yoy_stability is not None:
        yoy_stability.to_csv(OUTPUT_DIR / "walk_forward_yoy_stability.csv")
    if all_decile_results:
        decile_df = pd.DataFrame(all_decile_results)
        decile_df.to_csv(OUTPUT_DIR / "walk_forward_decile_lift.csv", index=False)
        log(f"\nSaved decile lift to walk_forward_decile_lift.csv")
        # Print decile lift table for Gradient Boosting, most recent year
        lr_decile = decile_df[decile_df["model"] == "Gradient Boosting"]
        if len(lr_decile) > 0:
            latest_year = lr_decile["install_year"].max()
            latest = lr_decile[lr_decile["install_year"] == latest_year].sort_values("decile")
            log(f"\n--- Decile lift (Gradient Boosting, install year {latest_year}) ---")
            log(latest[["decile", "lift", "adoption_rate", "n", "captured", "capture_pct"]].to_string(index=False))
    log(f"\nSaved outputs to {OUTPUT_DIR}")

    # Decile lift chart (Gradient Boosting, average across years)
    if all_decile_results:
        decile_df = pd.DataFrame(all_decile_results)
        lr_decile = decile_df[decile_df["model"] == "Gradient Boosting"]
        if len(lr_decile) > 0:
            avg_by_decile = lr_decile.groupby("decile").agg({
                "lift": "mean",
                "adoption_rate": "mean",
            }).reset_index()
            fig, ax = plt.subplots(figsize=(10, 5))
            ax.bar(avg_by_decile["decile"] - 0.4, avg_by_decile["lift"], width=0.8, color="steelblue", label="Lift")
            ax.axhline(1, color="gray", linestyle="--", alpha=0.7)
            ax.set_xlabel("Decile (1=top 10% by predicted score)")
            ax.set_ylabel("Lift (vs baseline)")
            ax.set_title("Decile Lift - Gradient Boosting (avg across years)")
            ax.set_xticks(range(1, 11))
            ax.legend()
            ax.grid(True, alpha=0.3, axis="y")
            plt.tight_layout()
            plt.savefig(OUTPUT_DIR / f"walk_forward_decile_lift_{ts}.png", dpi=150)
            plt.close()
            log(f"Saved: {OUTPUT_DIR / f'walk_forward_decile_lift_{ts}.png'}")

        # Decile lift by year (Gradient Boosting) - line chart
        if len(lr_decile) > 0:
            fig, ax = plt.subplots(figsize=(10, 5))
            for year in sorted(lr_decile["install_year"].unique()):
                yd = lr_decile[lr_decile["install_year"] == year].sort_values("decile")
                ax.plot(yd["decile"], yd["lift"], "-o", label=str(year), markersize=4)
            ax.axhline(1, color="gray", linestyle="--", alpha=0.7)
            ax.set_xlabel("Decile (1=top 10% by predicted score)")
            ax.set_ylabel("Lift (vs baseline)")
            ax.set_title("Decile Lift by Year - Gradient Boosting")
            ax.set_xticks(range(1, 11))
            ax.legend(ncol=2, fontsize=8)
            ax.grid(True, alpha=0.3)
            plt.tight_layout()
            plt.savefig(OUTPUT_DIR / f"walk_forward_decile_lift_by_year_{ts}.png", dpi=150)
            plt.close()
            log(f"Saved: {OUTPUT_DIR / f'walk_forward_decile_lift_by_year_{ts}.png'}")

        # Helper to add baseline adoption rate on secondary y-axis
        def _add_baseline_axis(ax, results_df: pd.DataFrame) -> None:
            baseline = results_df.groupby("install_year")["baseline_adoption_rate"].first().reset_index()
            if len(baseline) > 0:
                ax2 = ax.twinx()
                ax2.plot(baseline["install_year"], baseline["baseline_adoption_rate"], "k:", alpha=0.7, linewidth=1.5, label="Baseline adoption rate")
                ax2.set_ylabel("Baseline adoption rate")
                ax2.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"{x:.1%}"))
                ax2.legend(loc="upper right", fontsize=8)

        # Top 10% decile lift by install year: Gradient Boosting vs Random Forest vs Ensemble
        decile1 = decile_df[decile_df["decile"] == 1]
        fig, ax_top10 = plt.subplots(figsize=(10, 5))
        for model_name in ["Gradient Boosting", "Random Forest", "RF+GB Ensemble", "GB+Ensemble Hybrid (70/30)"]:
            m = decile1[decile1["model"] == model_name].sort_values("install_year")
            if len(m) > 0:
                ax_top10.plot(m["install_year"], m["lift"], "-o", label=model_name, markersize=6)
        ax_top10.axhline(1, color="gray", linestyle="--", alpha=0.7)
        _add_baseline_axis(ax_top10, results_df)
        ax_top10.set_xlabel("Install Year")
        ax_top10.set_ylabel("Top 10% Decile Lift (vs baseline)")
        ax_top10.set_title("Top 10% Decile Lift by Install Year - GB vs RF vs Ensemble")
        ax_top10.legend(loc="upper left")
        ax_top10.grid(True, alpha=0.3)
        plt.tight_layout()
        plt.savefig(OUTPUT_DIR / f"walk_forward_top10_decile_lift_by_year_{ts}.png", dpi=150)
        plt.close()
        log(f"Saved: {OUTPUT_DIR / f'walk_forward_top10_decile_lift_by_year_{ts}.png'}")

        # Top 10% decile capture by install year: Gradient Boosting vs Random Forest vs Ensemble
        decile1 = decile_df[decile_df["decile"] == 1]
        fig, ax_cap = plt.subplots(figsize=(10, 5))
        for model_name in ["Gradient Boosting", "Random Forest", "RF+GB Ensemble", "GB+Ensemble Hybrid (70/30)"]:
            m = decile1[decile1["model"] == model_name].sort_values("install_year")
            if len(m) > 0:
                ax_cap.plot(m["install_year"], m["capture_pct"], "-o", label=model_name, markersize=6)
        ax_cap.axhline(0.10, color="gray", linestyle="--", alpha=0.7, label="Random (10%)")
        ax_cap.set_xlabel("Install Year")
        ax_cap.set_ylabel("Top 10% Decile Capture (% of positives)")
        ax_cap.set_title("Top 10% Decile Capture by Install Year - GB vs RF vs Ensemble")
        ax_cap.legend()
        ax_cap.grid(True, alpha=0.3)
        ax_cap.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"{x:.0%}"))
        plt.tight_layout()
        plt.savefig(OUTPUT_DIR / f"walk_forward_top10_decile_capture_by_year_{ts}.png", dpi=150)
        plt.close()
        log(f"Saved: {OUTPUT_DIR / f'walk_forward_top10_decile_capture_by_year_{ts}.png'}")

    # Top 5% and 2% lift by install year (from results_df) with baseline adoption rate
    if "lift_5pct" in results_df.columns and "lift_2pct" in results_df.columns:
        baseline = results_df.groupby("install_year")["baseline_adoption_rate"].first().reset_index()

        for pct, col, title_suffix in [(5, "lift_5pct", "5%"), (2, "lift_2pct", "2%")]:
            fig, ax = plt.subplots(figsize=(10, 5))
            for model_name in ["Gradient Boosting", "Random Forest", "RF+GB Ensemble", "GB+Ensemble Hybrid (70/30)"]:
                m = results_df[results_df["model"] == model_name].sort_values("install_year")
                if len(m) > 0:
                    ax.plot(m["install_year"], m[col], "-o", label=model_name, markersize=6)
            ax.axhline(1, color="gray", linestyle="--", alpha=0.7)
            if len(baseline) > 0:
                ax2 = ax.twinx()
                ax2.plot(baseline["install_year"], baseline["baseline_adoption_rate"], "k:", alpha=0.7, linewidth=1.5, label="Baseline adoption rate")
                ax2.set_ylabel("Baseline adoption rate")
                ax2.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"{x:.1%}"))
                ax2.legend(loc="upper right", fontsize=8)
            ax.set_xlabel("Install Year")
            ax.set_ylabel(f"Top {title_suffix} Lift (vs baseline)")
            ax.set_title(f"Top {title_suffix} Lift by Install Year - GB vs RF vs Ensemble")
            ax.legend(loc="upper left")
            ax.grid(True, alpha=0.3)
            plt.tight_layout()
            plt.savefig(OUTPUT_DIR / f"walk_forward_top{pct}pct_lift_by_year_{ts}.png", dpi=150)
            plt.close()
            log(f"Saved: {OUTPUT_DIR / f'walk_forward_top{pct}pct_lift_by_year_{ts}.png'}")

    # Plot metrics over years by model (2x5 grid for lift/capture)
    fig, axes = plt.subplots(2, 5, figsize=(20, 10))
    axes = axes.flatten()
    plot_configs = [
        ("roc_auc", "ROC-AUC"),
        ("pr_auc", "PR-AUC"),
        ("lift_20pct", "Top 20% Lift"),
        ("lift_10pct", "Top 10% Lift"),
        ("lift_5pct", "Top 5% Lift"),
        ("lift_2pct", "Top 2% Lift"),
        ("capture_20pct", "Capture Rate Top 20%"),
        ("capture_10pct", "Capture Rate Top 10%"),
        ("capture_5pct", "Capture Rate Top 5%"),
        ("capture_2pct", "Capture Rate Top 2%"),
    ]
    for ax, (col, title) in zip(axes, plot_configs):
        if col in results_df.columns:
            for model_name in results_df["model"].unique():
                m = results_df[results_df["model"] == model_name].sort_values("install_year")
                ax.plot(m["install_year"], m[col], "-o", label=model_name, markersize=4)
        ax.set_xlabel("Install Year")
        ax.set_ylabel(title)
        ax.set_title(title + " by Year")
        ax.legend(fontsize=7)
        ax.grid(True, alpha=0.3)
    for j in range(len(plot_configs), len(axes)):
        axes[j].set_visible(False)
    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / f"walk_forward_metrics_over_time_{ts}.png", dpi=150)
    plt.close()
    log(f"Saved: {OUTPUT_DIR / f'walk_forward_metrics_over_time_{ts}.png'}")

    # Hybrid model only: 20%, 10%, 5% lift and capture graphs (exclude 2026, no baseline lines)
    hybrid_name = "GB+Ensemble Hybrid (70/30)"
    hybrid_df = results_df[
        (results_df["model"] == hybrid_name) & (results_df["install_year"] < 2026)
    ].sort_values("install_year")
    hybrid_color = "#f59e0b"
    if len(hybrid_df) > 0:
        for pct, lift_col, cap_col in [
            (20, "lift_20pct", "capture_20pct"),
            (10, "lift_10pct", "capture_10pct"),
            (5, "lift_5pct", "capture_5pct"),
        ]:
            if lift_col in results_df.columns:
                fig, ax = plt.subplots(figsize=(10, 5))
                ax.plot(hybrid_df["install_year"], hybrid_df[lift_col], "-o", color=hybrid_color, markersize=8)
                ax.set_ylim(bottom=0)
                ax.set_xlabel("Install Year")
                ax.set_ylabel(f"Top {pct}% Lift (vs baseline)")
                ax.set_title(f"Top {pct}% Lift by Install Year")
                ax.grid(True, alpha=0.3)
                plt.tight_layout()
                plt.savefig(OUTPUT_DIR / f"hybrid_top{pct}pct_lift_by_year_{ts}.png", dpi=150)
                plt.close()
                log(f"Saved: {OUTPUT_DIR / f'hybrid_top{pct}pct_lift_by_year_{ts}.png'}")
            if cap_col in results_df.columns:
                fig, ax = plt.subplots(figsize=(10, 5))
                ax.plot(hybrid_df["install_year"], hybrid_df[cap_col], "-o", color=hybrid_color, markersize=8)
                ax.set_ylim(bottom=0)
                ax.set_xlabel("Install Year")
                ax.set_ylabel(f"Top {pct}% Capture (% of positives)")
                ax.set_title(f"Top {pct}% Capture by Install Year")
                ax.grid(True, alpha=0.3)
                ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"{x:.0%}"))
                plt.tight_layout()
                plt.savefig(OUTPUT_DIR / f"hybrid_top{pct}pct_capture_by_year_{ts}.png", dpi=150)
                plt.close()
                log(f"Saved: {OUTPUT_DIR / f'hybrid_top{pct}pct_capture_by_year_{ts}.png'}")


def main() -> None:
    run_walk_forward()


if __name__ == "__main__":
    main()
