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
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", str(Path(__file__).resolve().parent / ".mplconfig"))
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    brier_score_loss,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.feature_selection import mutual_info_classif
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.tree import DecisionTreeClassifier

warnings.filterwarnings("ignore")

# High-scale numeric columns: log-transform before scaling (prices, areas in $ or sqft)
LOG_TRANSFORM_COLS = ["saleprice", "saleprice_int", "sqft", "area_building", "recrdareano", "mainfloorsf", "mainfloorsf_int", "bsmtsf", "carstoragesf"]

# Feature selection: top N features to keep per fold (None = use all)
N_FEATURES_SELECT = 25

# Paths
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_PATH = PROJECT_ROOT / "data" / "working" / "parsed_permits_by_year.csv"
OUTPUT_DIR = PROJECT_ROOT / "data_science" / "output" / "walk_forward"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Columns to exclude from features (identifiers, target, leakage)
EXCLUDE_COLS = [
    "strap", "year", "solar_pv", "solar_next_year", "original_index",
    "owner", "mailadd", "mail_city", "mail_state2", "mail_zip",
    "original_mailing_address", "address", "scity", "original_address",
    "city", "county", "state2", "szip", "szip5", "subdivision",
    "saledate",  # use time_since_sale instead
]

# Time columns: convert to 10-year bin factors
TIME_COLS = ["time_since_sale", "time_since_build"]
TIME_BIN_YEARS = 10

YEAR_START = 2012
YEAR_END = 2025  # predict solar in 2025 (train on 2012..2024)
TEST_STRAP_FRACTION = 0.2
RANDOM_STATE = 42


def get_feature_types(X: pd.DataFrame) -> tuple[list[str], list[str]]:
    """Identify numeric vs categorical columns."""
    numeric = X.select_dtypes(include=[np.number]).columns.tolist()
    categorical = X.select_dtypes(include=["object", "category"]).columns.tolist()
    return numeric, categorical


def add_time_bin_factors(X: pd.DataFrame) -> pd.DataFrame:
    """Convert time_since_sale and time_since_build to categorical 10-year bins."""
    X = X.copy()
    for col in TIME_COLS:
        if col not in X.columns:
            continue
        t = X[col].fillna(X[col].median())
        t = np.maximum(t, 0)
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
    # Log-transform high-scale columns (prices, areas) to compress scale
    for c in LOG_TRANSFORM_COLS:
        if c in X.columns and X[c].dtype in (np.float64, np.int64, "float64", "int64", "Int64"):
            vals = X[c].fillna(X[c].median())
            vals = np.maximum(vals, 1)  # avoid log(0)
            X[c] = np.log1p(vals)
    X = add_time_bin_factors(X)
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


def select_features_lasso(
    X: np.ndarray, y: np.ndarray, feature_names: list[str], n_features: int = 25
) -> list[str]:
    """LASSO (L1) feature selection. Returns top n_features by |coefficient|."""
    if X.shape[1] <= n_features:
        return feature_names
    model = LogisticRegression(
        penalty="l1", solver="saga", C=0.1, max_iter=2000,
        random_state=RANDOM_STATE, class_weight="balanced"
    )
    model.fit(X, y)
    coef = np.abs(model.coef_[0])
    idx = np.argsort(coef)[::-1][:n_features]
    return [feature_names[i] for i in idx]


def select_features_mutual_info(
    X: np.ndarray, y: np.ndarray, feature_names: list[str], n_features: int = 25
) -> list[str]:
    """Mutual information feature selection. Returns top n_features."""
    if X.shape[1] <= n_features:
        return feature_names
    mi = mutual_info_classif(X, y, random_state=RANDOM_STATE)
    idx = np.argsort(mi)[::-1][:n_features]
    return [feature_names[i] for i in idx]


def get_feature_indices(selected_names: list[str], all_names: list[str]) -> np.ndarray:
    """Get column indices for selected feature names."""
    name_to_idx = {n: i for i, n in enumerate(all_names)}
    return np.array([name_to_idx[n] for n in selected_names if n in name_to_idx])


def load_data() -> pd.DataFrame:
    """Load parsed_permits_by_year and filter to valid prediction rows."""
    df = pd.read_csv(DATA_PATH)
    df = df[df["year"].between(YEAR_START, YEAR_END)]
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
        return {"lift_10pct": 0, "lift_5pct": 0, "lift_2pct": 0, "capture_10pct": 0, "capture_5pct": 0, "capture_2pct": 0}
    n = len(y_true)
    n_pos = int(y_true.sum())
    if n_pos == 0:
        return {"lift_10pct": 0, "lift_5pct": 0, "lift_2pct": 0, "capture_10pct": 0, "capture_5pct": 0, "capture_2pct": 0}
    order = np.argsort(y_prob)[::-1]
    result = {}
    for pct, key in [(0.10, "10pct"), (0.05, "5pct"), (0.02, "2pct")]:
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


def evaluate_model(
    model, X_train, y_train, X_test, y_test, name: str, baseline_rate: float
) -> tuple[dict, np.ndarray | None]:
    """Train model and return metrics on test set. Also returns y_prob for calibration."""
    model.fit(X_train, y_train)
    y_pred = model.predict(X_test)
    y_prob = model.predict_proba(X_test)[:, 1] if hasattr(model, "predict_proba") else None

    roc_auc = roc_auc_score(y_test, y_prob) if y_prob is not None and len(np.unique(y_test)) > 1 else 0
    pr_auc = average_precision_score(y_test, y_prob) if y_prob is not None and len(np.unique(y_test)) > 1 else 0
    brier = brier_score_loss(y_test, y_prob) if y_prob is not None else 0

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
        "baseline_adoption_rate": baseline_rate,
        **lift_capture,
    }
    return metrics, y_prob


def run_walk_forward() -> None:
    """Run walk-forward modeling from 2012 through predicting 2025."""
    def log(msg: str) -> None:
        print(msg, flush=True)

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
    log(f"Using {len(feature_cols)} feature columns")

    # Strap-based split: same straps for all folds
    straps = df["strap"].unique()
    np.random.seed(RANDOM_STATE)
    np.random.shuffle(straps)
    n_test = max(1, int(len(straps) * TEST_STRAP_FRACTION))
    test_straps = set(straps[:n_test])
    train_straps = set(straps[n_test:])
    log(f"Train straps: {len(train_straps)}, Test straps: {len(test_straps)}")

    models = {
        "Logistic Regression": LogisticRegression(
            max_iter=2000, random_state=RANDOM_STATE, class_weight="balanced"
        ),
        "Decision Tree": DecisionTreeClassifier(
            random_state=RANDOM_STATE, max_depth=10, class_weight="balanced"
        ),
        "Random Forest": RandomForestClassifier(
            n_estimators=100, random_state=RANDOM_STATE, max_depth=10, class_weight="balanced"
        ),
        "Gradient Boosting": GradientBoostingClassifier(
            n_estimators=100, max_depth=5, random_state=RANDOM_STATE
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

    all_results = []
    all_decile_results: list[dict] = []
    feature_importance_by_year: dict[int, dict[str, float]] = {}  # year -> {feat: importance}
    for predict_year in range(YEAR_START + 1, YEAR_END + 1):
        train_years = list(range(YEAR_START, predict_year))
        log(f"\n{'='*60}")
        log(f"Predicting {predict_year}: train on years {train_years}")
        log("=" * 60)

        train_df = df[
            (df["year"].isin(train_years)) &
            (df["strap"].isin(train_straps))
        ]
        test_df = df[
            (df["year"] == predict_year - 1) &
            (df["strap"].isin(test_straps))
        ]

        if len(train_df) < 10 or len(test_df) < 5:
            log(f"  Skipping: too few samples (train={len(train_df)}, test={len(test_df)})")
            continue

        y_train = train_df["solar_next_year"].astype(int).values
        y_test = test_df["solar_next_year"].astype(int).values

        X_train_raw = prepare_features(train_df, feature_cols)
        X_test_raw = prepare_features(test_df, feature_cols)

        numeric, categorical = get_feature_types(X_train_raw)
        preprocessor = fit_preprocessor(X_train_raw, numeric, categorical)

        X_train = preprocessor.transform(X_train_raw)
        X_test = preprocessor.transform(X_test_raw)

        # Feature names for selection (numeric + one-hot cat names)
        feature_names = []
        if numeric:
            feature_names.extend(numeric)
        if "cat" in preprocessor.named_transformers_:
            cat_names = preprocessor.named_transformers_["cat"].get_feature_names_out(
                preprocessor.transformers_[1][2]
            )
            feature_names.extend(cat_names)

        # Feature selection on training data (LASSO for linear models; MI as fallback)
        used_feature_names = feature_names
        idx = np.arange(X_train.shape[1])  # default: all features
        if N_FEATURES_SELECT and X_train.shape[1] > N_FEATURES_SELECT:
            try:
                selected = select_features_lasso(
                    X_train, y_train, feature_names, N_FEATURES_SELECT
                )
                idx = get_feature_indices(selected, feature_names)
                if len(idx) >= 5:
                    X_train = X_train[:, idx]
                    X_test = X_test[:, idx]
                    used_feature_names = [feature_names[i] for i in idx]
                    log(f"  Selected {len(idx)} features (LASSO)")
            except Exception as e:
                try:
                    selected = select_features_mutual_info(
                        X_train, y_train, feature_names, N_FEATURES_SELECT
                    )
                    idx = get_feature_indices(selected, feature_names)
                    if len(idx) >= 5:
                        X_train = X_train[:, idx]
                        X_test = X_test[:, idx]
                        used_feature_names = [feature_names[i] for i in idx]
                        log(f"  Selected {len(idx)} features (Mutual Info, LASSO failed)")
                except Exception as e2:
                    log(f"  Feature selection failed ({e2}), using all features")

        pos_rate_train = y_train.mean()
        baseline_rate = pos_rate_test = y_test.mean()
        log(f"  Train: {len(y_train)} rows, {pos_rate_train:.2%} positive")
        log(f"  Test:  {len(y_test)} rows, baseline adoption rate={baseline_rate:.2%}")

        fold_results = []
        lr_y_prob = None
        for name, model in models.items():
            metrics, y_prob = evaluate_model(
                model, X_train, y_train, X_test, y_test, name, baseline_rate
            )
            metrics["predict_year"] = predict_year
            metrics["train_n"] = len(y_train)
            metrics["test_n"] = len(y_test)
            fold_results.append(metrics)
            all_results.append(metrics)
            if name == "Logistic Regression":
                lr_y_prob = y_prob
            # Decile lift
            for row in compute_decile_lift(y_test, y_prob, baseline_rate):
                all_decile_results.append({
                    "model": name,
                    "predict_year": predict_year,
                    **row,
                })
            log(
                f"  {name}: ROC-AUC={metrics['roc_auc']:.4f}, PR-AUC={metrics['pr_auc']:.4f}, "
                f"Brier={metrics['brier_score']:.4f} | "
                f"lift@10/5/2%={metrics.get('lift_10pct', 0):.2f}/{metrics.get('lift_5pct', 0):.2f}/{metrics.get('lift_2pct', 0):.2f}x | "
                f"capture@10/5/2%={metrics.get('capture_10pct', 0):.2%}/{metrics.get('capture_5pct', 0):.2%}/{metrics.get('capture_2pct', 0):.2%}"
            )

        # Feature importance from LASSO (for stability tracking) - use final X_train feature set
        try:
            lasso = LogisticRegression(
                penalty="l1", solver="saga", C=0.1, max_iter=2000,
                random_state=RANDOM_STATE, class_weight="balanced"
            )
            lasso.fit(X_train, y_train)
            if len(used_feature_names) == X_train.shape[1]:
                feature_importance_by_year[predict_year] = {
                    f: float(np.abs(c)) for f, c in zip(used_feature_names, lasso.coef_[0])
                }
        except Exception:
            pass

        # Confusion matrix for Logistic Regression (first model)
        lr_model = list(models.values())[0]
        lr_model.fit(X_train, y_train)
        y_pred = lr_model.predict(X_test)
        cm = confusion_matrix(y_test, y_pred)
        fig, ax = plt.subplots(figsize=(5, 4))
        sns.heatmap(cm, annot=True, fmt="d", cmap="Blues", ax=ax)
        ax.set_title(f"Predict {predict_year} (Logistic Regression)")
        ax.set_xlabel("Predicted")
        ax.set_ylabel("Actual")
        plt.tight_layout()
        plt.savefig(OUTPUT_DIR / f"confusion_predict_{predict_year}.png", dpi=150)
        plt.close()

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
            ax.set_title(f"Calibration curve (predict {predict_year})")
            ax.legend()
            ax.grid(True, alpha=0.3)
            plt.tight_layout()
            plt.savefig(OUTPUT_DIR / f"calibration_predict_{predict_year}.png", dpi=150)
            plt.close()

    # Summary
    results_df = pd.DataFrame(all_results)
    metric_cols = [
        "f1", "roc_auc", "pr_auc", "brier_score", "accuracy", "precision", "recall",
        "baseline_adoption_rate", "lift_10pct", "lift_5pct", "lift_2pct",
        "capture_10pct", "capture_5pct", "capture_2pct",
    ]
    agg_dict = {c: "first" for c in metric_cols if c in results_df.columns}
    summary = results_df.groupby(["model", "predict_year"]).agg(agg_dict).reset_index()

    log("\n" + "=" * 60)
    log("WALK-FORWARD SUMMARY (per year)")
    log("=" * 60)
    log(summary.to_string(index=False))

    # Year-over-year metric stability (std across years)
    stability_cols = [c for c in ["roc_auc", "pr_auc", "f1", "brier_score", "lift_10pct", "lift_5pct", "lift_2pct", "capture_10pct", "capture_5pct", "capture_2pct"] if c in results_df.columns]
    yoy_stability = None
    if stability_cols:
        yoy_stability = results_df.groupby("model")[stability_cols].std().round(4)
        yoy_stability.columns = [f"{c}_std" for c in stability_cols]
        log("\n--- Year-over-year metric stability (std across years) ---")
        log(str(yoy_stability))

    # Feature importance stability (correlation across consecutive years)
    feat_stability = None
    if len(feature_importance_by_year) >= 2:
        years = sorted(feature_importance_by_year.keys())
        corrs = []
        for i in range(len(years) - 1):
            y1, y2 = years[i], years[i + 1]
            imp1 = feature_importance_by_year[y1]
            imp2 = feature_importance_by_year[y2]
            common_feats = sorted(set(imp1.keys()) & set(imp2.keys()))
            if len(common_feats) < 3:
                continue
            v1 = np.array([imp1.get(f, 0) for f in common_feats])
            v2 = np.array([imp2.get(f, 0) for f in common_feats])
            if v1.std() > 1e-10 and v2.std() > 1e-10:
                r = np.corrcoef(v1, v2)[0, 1]
                corrs.append((y1, y2, r))
        if corrs:
            feat_stability = np.mean([c[2] for c in corrs])
            log(f"\n--- Feature importance stability (mean corr year-to-year): {feat_stability:.4f} ---")
            for y1, y2, r in corrs:
                log(f"  {y1}->{y2}: {r:.4f}")
            pd.DataFrame(corrs, columns=["year_from", "year_to", "correlation"]).to_csv(
                OUTPUT_DIR / "walk_forward_feature_importance_stability.csv", index=False
            )

    # Average metrics by model across years
    avg_cols = ["f1", "roc_auc", "pr_auc", "brier_score", "accuracy", "lift_10pct", "lift_5pct", "lift_2pct", "capture_10pct", "capture_5pct", "capture_2pct"]
    avg_cols = [c for c in avg_cols if c in results_df.columns]
    avg_by_model = results_df.groupby("model")[avg_cols].mean().round(4)
    log("\n--- Average by model (across years) ---")
    log(str(avg_by_model))

    results_df.to_csv(OUTPUT_DIR / "walk_forward_metrics.csv", index=False)
    summary.to_csv(OUTPUT_DIR / "walk_forward_summary.csv", index=False)
    if yoy_stability is not None:
        yoy_stability.to_csv(OUTPUT_DIR / "walk_forward_yoy_stability.csv")
    if all_decile_results:
        decile_df = pd.DataFrame(all_decile_results)
        decile_df.to_csv(OUTPUT_DIR / "walk_forward_decile_lift.csv", index=False)
        log(f"\nSaved decile lift to walk_forward_decile_lift.csv")
        # Print decile lift table for Logistic Regression, most recent year
        lr_decile = decile_df[decile_df["model"] == "Logistic Regression"]
        if len(lr_decile) > 0:
            latest_year = lr_decile["predict_year"].max()
            latest = lr_decile[lr_decile["predict_year"] == latest_year].sort_values("decile")
            log(f"\n--- Decile lift (Logistic Regression, predict {latest_year}) ---")
            log(latest[["decile", "lift", "adoption_rate", "n", "captured", "capture_pct"]].to_string(index=False))
    log(f"\nSaved outputs to {OUTPUT_DIR}")

    # Decile lift chart (Logistic Regression, average across years)
    if all_decile_results:
        decile_df = pd.DataFrame(all_decile_results)
        lr_decile = decile_df[decile_df["model"] == "Logistic Regression"]
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
            ax.set_title("Decile Lift - Logistic Regression (avg across years)")
            ax.set_xticks(range(1, 11))
            ax.legend()
            ax.grid(True, alpha=0.3, axis="y")
            plt.tight_layout()
            plt.savefig(OUTPUT_DIR / "walk_forward_decile_lift.png", dpi=150)
            plt.close()
            log(f"Saved: {OUTPUT_DIR / 'walk_forward_decile_lift.png'}")

        # Decile lift by year (Logistic Regression) - line chart
        if len(lr_decile) > 0:
            fig, ax = plt.subplots(figsize=(10, 5))
            for year in sorted(lr_decile["predict_year"].unique()):
                yd = lr_decile[lr_decile["predict_year"] == year].sort_values("decile")
                ax.plot(yd["decile"], yd["lift"], "-o", label=str(year), markersize=4)
            ax.axhline(1, color="gray", linestyle="--", alpha=0.7)
            ax.set_xlabel("Decile (1=top 10% by predicted score)")
            ax.set_ylabel("Lift (vs baseline)")
            ax.set_title("Decile Lift by Year - Logistic Regression")
            ax.set_xticks(range(1, 11))
            ax.legend(ncol=2, fontsize=8)
            ax.grid(True, alpha=0.3)
            plt.tight_layout()
            plt.savefig(OUTPUT_DIR / "walk_forward_decile_lift_by_year.png", dpi=150)
            plt.close()
            log(f"Saved: {OUTPUT_DIR / 'walk_forward_decile_lift_by_year.png'}")

    # Plot metrics over years by model (2x4 grid for lift/capture)
    fig, axes = plt.subplots(2, 4, figsize=(16, 10))
    axes = axes.flatten()
    plot_configs = [
        ("roc_auc", "ROC-AUC"),
        ("pr_auc", "PR-AUC"),
        ("lift_10pct", "Top 10% Lift"),
        ("lift_5pct", "Top 5% Lift"),
        ("lift_2pct", "Top 2% Lift"),
        ("capture_10pct", "Capture Rate Top 10%"),
        ("capture_5pct", "Capture Rate Top 5%"),
        ("capture_2pct", "Capture Rate Top 2%"),
    ]
    for ax, (col, title) in zip(axes, plot_configs):
        if col in results_df.columns:
            for model_name in results_df["model"].unique():
                m = results_df[results_df["model"] == model_name].sort_values("predict_year")
                ax.plot(m["predict_year"], m[col], "-o", label=model_name, markersize=4)
        ax.set_xlabel("Prediction Year")
        ax.set_ylabel(title)
        ax.set_title(title + " by Year")
        ax.legend(fontsize=7)
        ax.grid(True, alpha=0.3)
    for j in range(len(plot_configs), len(axes)):
        axes[j].set_visible(False)
    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / "walk_forward_metrics_over_time.png", dpi=150)
    plt.close()
    log(f"Saved: {OUTPUT_DIR / 'walk_forward_metrics_over_time.png'}")


def main() -> None:
    run_walk_forward()


if __name__ == "__main__":
    main()
