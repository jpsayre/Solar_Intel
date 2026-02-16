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


def evaluate_model(model, X_train, y_train, X_test, y_test, name: str) -> dict:
    """Train model and return metrics on test set."""
    model.fit(X_train, y_train)
    y_pred = model.predict(X_test)
    y_prob = model.predict_proba(X_test)[:, 1] if hasattr(model, "predict_proba") else None
    return {
        "model": name,
        "accuracy": accuracy_score(y_test, y_pred),
        "precision": precision_score(y_test, y_pred, zero_division=0),
        "recall": recall_score(y_test, y_pred, zero_division=0),
        "f1": f1_score(y_test, y_pred, zero_division=0),
        "roc_auc": roc_auc_score(y_test, y_prob) if y_prob is not None and len(np.unique(y_test)) > 1 else 0,
    }


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
        if N_FEATURES_SELECT and X_train.shape[1] > N_FEATURES_SELECT:
            try:
                selected = select_features_lasso(
                    X_train, y_train, feature_names, N_FEATURES_SELECT
                )
                idx = get_feature_indices(selected, feature_names)
                if len(idx) >= 5:
                    X_train = X_train[:, idx]
                    X_test = X_test[:, idx]
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
                        log(f"  Selected {len(idx)} features (Mutual Info, LASSO failed)")
                except Exception as e2:
                    log(f"  Feature selection failed ({e2}), using all features")

        pos_rate_train = y_train.mean()
        pos_rate_test = y_test.mean()
        log(f"  Train: {len(y_train)} rows, {pos_rate_train:.2%} positive")
        log(f"  Test:  {len(y_test)} rows, {pos_rate_test:.2%} positive")

        fold_results = []
        for name, model in models.items():
            metrics = evaluate_model(model, X_train, y_train, X_test, y_test, name)
            metrics["predict_year"] = predict_year
            metrics["train_n"] = len(y_train)
            metrics["test_n"] = len(y_test)
            fold_results.append(metrics)
            all_results.append(metrics)
            log(f"  {name}: F1={metrics['f1']:.4f}, ROC-AUC={metrics['roc_auc']:.4f}")

        # Confusion matrix for Logistic Regression (first model)
        lr_metrics = fold_results[0]
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

    # Summary
    results_df = pd.DataFrame(all_results)
    summary = results_df.groupby(["model", "predict_year"]).agg({
        "f1": "first",
        "roc_auc": "first",
        "accuracy": "first",
        "precision": "first",
        "recall": "first",
    }).reset_index()

    log("\n" + "=" * 60)
    log("WALK-FORWARD SUMMARY")
    log("=" * 60)
    log(summary.to_string(index=False))

    # Average metrics by model across years
    avg_by_model = results_df.groupby("model").agg({
        "f1": "mean",
        "roc_auc": "mean",
        "accuracy": "mean",
    }).round(4)
    log("\n--- Average by model (across years) ---")
    log(str(avg_by_model))

    results_df.to_csv(OUTPUT_DIR / "walk_forward_metrics.csv", index=False)
    summary.to_csv(OUTPUT_DIR / "walk_forward_summary.csv", index=False)
    log(f"\nSaved outputs to {OUTPUT_DIR}")

    # Plot F1 and ROC-AUC over years by model
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    for model_name in results_df["model"].unique():
        m = results_df[results_df["model"] == model_name]
        axes[0].plot(m["predict_year"], m["f1"], "-o", label=model_name, markersize=4)
        axes[1].plot(m["predict_year"], m["roc_auc"], "-o", label=model_name, markersize=4)
    axes[0].set_xlabel("Prediction Year")
    axes[0].set_ylabel("F1 Score")
    axes[0].set_title("F1 by Prediction Year")
    axes[0].legend()
    axes[0].grid(True, alpha=0.3)
    axes[1].set_xlabel("Prediction Year")
    axes[1].set_ylabel("ROC-AUC")
    axes[1].set_title("ROC-AUC by Prediction Year")
    axes[1].legend()
    axes[1].grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / "walk_forward_metrics_over_time.png", dpi=150)
    plt.close()
    log(f"Saved: {OUTPUT_DIR / 'walk_forward_metrics_over_time.png'}")


def main() -> None:
    run_walk_forward()


if __name__ == "__main__":
    main()
