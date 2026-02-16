#!/usr/bin/env python3
"""
Feature selection and modeling for solar_pv prediction.

Analyzes data/final/data_science.csv:
1. Exploratory Data Analysis (EDA) with plots
2. Feature selection: LASSO, Ridge, Elastic Net, RFE, Mutual Information
3. Classification: Logistic Regression, CART, Random Forest, Gradient Boosting, XGBoost

Targets: solar_pv, solar_pv_recent (binary)
Excluded: original_index, alt_parcelnumb1
"""

from __future__ import annotations

import os
import warnings
from collections import Counter
from pathlib import Path

# Use writable config dir to avoid font cache issues in restricted envs
os.environ.setdefault("MPLCONFIGDIR", str(Path(__file__).resolve().parent / ".mplconfig"))
import matplotlib
matplotlib.use("Agg")  # Non-interactive backend for scripts
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from sklearn.feature_selection import mutual_info_classif, RFE
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
    roc_curve,
)
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.tree import DecisionTreeClassifier

warnings.filterwarnings("ignore")

# Paths
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_PATH = PROJECT_ROOT / "data" / "final" / "data_science.csv"
OUTPUT_DIR = PROJECT_ROOT / "data_science" / "output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Columns to exclude (empty = use all features)
EXCLUDE_COLS: list[str] = []
TARGETS = ["solar_pv", "solar_pv_recent"]

# Features to drop
DROP_FEATURES = ["battery_recent"]

# Time columns: convert to 10-year bin factors (0-10, 10-20, 20-30, ...)
TIME_COLS = ["time_since_sale", "time_since_build"]
TIME_BIN_YEARS = 10


def load_and_prepare_data() -> tuple[pd.DataFrame, dict[str, pd.Series]]:
    """Load CSV, drop excluded columns and nonsensical features. X has no targets."""
    df = pd.read_csv(DATA_PATH)
    df = df.drop(columns=[c for c in EXCLUDE_COLS if c in df.columns], errors="ignore")
    drop_cols = [t for t in TARGETS if t in df.columns]
    drop_cols += [c for c in DROP_FEATURES if c in df.columns]
    X = df.drop(columns=drop_cols)
    targets = {t: df[t].copy() for t in TARGETS if t in df.columns}
    return X, targets


def get_feature_types(X: pd.DataFrame) -> tuple[list[str], list[str]]:
    """Identify numeric vs categorical columns."""
    numeric = X.select_dtypes(include=[np.number]).columns.tolist()
    categorical = X.select_dtypes(include=["object", "category"]).columns.tolist()
    return numeric, categorical


# =============================================================================
# 1. EXPLORATORY DATA ANALYSIS
# =============================================================================


def run_eda(X: pd.DataFrame, targets: dict[str, pd.Series], target_name: str | None = None) -> None:
    """Generate EDA plots and summaries. If target_name given, run target-specific EDA only."""
    suffix = f"_{target_name}" if target_name else ""

    if target_name:
        y = targets[target_name]
        print("\n" + "=" * 60)
        print(f"EDA: {target_name}")
        print("=" * 60)
        print(f"\n--- Target distribution ({target_name}) ---")
        print(y.value_counts())
        print(f"Class balance: {y.mean():.2%} positive")

        # Target distribution plot
        fig, ax = plt.subplots(figsize=(6, 4))
        y.value_counts().plot(kind="bar", ax=ax, color=["#2ecc71", "#3498db"])
        ax.set_title(f"Target Distribution ({target_name})")
        ax.set_xlabel(target_name)
        ax.set_ylabel("Count")
        plt.tight_layout()
        plt.savefig(OUTPUT_DIR / f"eda_target_distribution{suffix}.png", dpi=150)
        plt.close()
        print(f"Saved: {OUTPUT_DIR / f'eda_target_distribution{suffix}.png'}")
    else:
        # Shared EDA (once)
        print("\n" + "=" * 60)
        print("EXPLORATORY DATA ANALYSIS")
        print("=" * 60)
        print("\n--- Shape ---")
        print(f"Rows: {len(X)}, Features: {X.shape[1]}")

    if not target_name:
        print("\n--- Missing values ---")
        missing = X.isnull().sum()
        missing = missing[missing > 0].sort_values(ascending=False)
        if len(missing) > 0:
            print(missing)
        else:
            print("No missing values in features.")
        numeric, categorical = get_feature_types(X)
        print(f"\nNumeric features: {len(numeric)}")
        print(f"Categorical features: {len(categorical)}")
        # Numeric distributions (shared, no target needed)
        if numeric:
            n_cols = 4
            n_rows = min(8, (len(numeric) + n_cols - 1) // n_cols)
            numeric_subset = numeric[: n_cols * n_rows]
            fig, axes = plt.subplots(n_rows, n_cols, figsize=(16, 4 * n_rows))
            axes = np.atleast_2d(axes) if n_rows > 1 else np.array([axes])
            axes = axes.flatten()
            for i, col in enumerate(numeric_subset):
                axes[i].hist(X[col].dropna(), bins=50, edgecolor="black", alpha=0.7)
                axes[i].set_title(col, fontsize=9)
            for j in range(len(numeric_subset), len(axes)):
                axes[j].set_visible(False)
            plt.tight_layout()
            plt.savefig(OUTPUT_DIR / "eda_numeric_distributions.png", dpi=150)
            plt.close()
            print(f"Saved: {OUTPUT_DIR / 'eda_numeric_distributions.png'}")
    else:
        numeric, categorical = get_feature_types(X)
        y = targets[target_name]

    # Target-specific: correlations, heatmap, boxplots
    if numeric and target_name:
        # Correlation with target (for numeric)
        corr_target = X[numeric].corrwith(y).abs().sort_values(ascending=False)
        top_corr = corr_target.head(20)
        fig, ax = plt.subplots(figsize=(10, 8))
        top_corr.plot(kind="barh", ax=ax, color="steelblue")
        ax.set_title(f"Top 20 Numeric Features by |Correlation| with {target_name}")
        ax.set_xlabel("|Correlation|")
        plt.tight_layout()
        plt.savefig(OUTPUT_DIR / f"eda_correlation_with_target{suffix}.png", dpi=150)
        plt.close()
        print(f"Saved: {OUTPUT_DIR / f'eda_correlation_with_target{suffix}.png'}")

        # Correlation heatmap (top numeric only, to avoid huge matrix)
        top_n = min(20, len(numeric))
        top_numeric = corr_target.head(top_n).index.tolist()
        corr_matrix = X[top_numeric].corr()
        fig, ax = plt.subplots(figsize=(12, 10))
        sns.heatmap(corr_matrix, annot=False, cmap="RdBu_r", center=0, ax=ax)
        ax.set_title("Correlation Matrix (Top 20 Numeric by Target Correlation)")
        plt.tight_layout()
        plt.savefig(OUTPUT_DIR / f"eda_correlation_heatmap{suffix}.png", dpi=150)
        plt.close()
        print(f"Saved: {OUTPUT_DIR / f'eda_correlation_heatmap{suffix}.png'}")

    # Key numeric features vs target (boxplots)
    if numeric and target_name:
        top_5 = corr_target.head(5).index.tolist()
        fig, axes = plt.subplots(2, 3, figsize=(14, 8))
        axes = axes.flatten()
        for i, col in enumerate(top_5):
            X.assign(_target=y).boxplot(column=col, by="_target", ax=axes[i])
            axes[i].set_title(col)
            axes[i].set_xlabel(target_name)
        axes[-1].set_visible(False)
        plt.suptitle(f"Top 5 Numeric Features by {target_name}")
        plt.tight_layout()
        plt.savefig(OUTPUT_DIR / f"eda_boxplots_by_target{suffix}.png", dpi=150)
        plt.close()
        print(f"Saved: {OUTPUT_DIR / f'eda_boxplots_by_target{suffix}.png'}")

    # Time columns: target rate by bins (non-linear relationship check)
    if target_name:
        y = targets[target_name]
        for time_col in TIME_COLS:
            if time_col in X.columns and X[time_col].notna().any():
                df_plot = pd.DataFrame({time_col: X[time_col], "_target": y})
                df_plot = df_plot.dropna()
                if len(df_plot) > 0:
                    # 1-year bins to see where biggest drop-off occurs
                    t_max = int(df_plot[time_col].max())
                    bins = np.arange(0, t_max + 2, 1)
                    df_plot["bin"] = pd.cut(
                        df_plot[time_col], bins=bins, include_lowest=True, right=False
                    )
                    rate_by_bin = df_plot.groupby("bin", observed=True)["_target"].mean()
                    n_bins = len(rate_by_bin)
                    fig, ax = plt.subplots(figsize=(max(12, n_bins * 0.25), 5))
                    rate_by_bin.plot(kind="bar", ax=ax, color="steelblue", edgecolor="black")
                    ax.set_title(f"{target_name} Rate by {time_col} (1-year bins, longer = less likely?)")
                    ax.set_xlabel(time_col + " (years)")
                    ax.set_ylabel(f"{target_name} rate")
                    ax.tick_params(axis="x", rotation=90)
                    plt.tight_layout()
                    plt.savefig(OUTPUT_DIR / f"eda_{time_col}_vs_{target_name}.png", dpi=150)
                    plt.close()
                    print(f"Saved: {OUTPUT_DIR / f'eda_{time_col}_vs_{target_name}.png'}")


# =============================================================================
# 2. FEATURE SELECTION
# =============================================================================


def add_time_bin_factors(X: pd.DataFrame) -> pd.DataFrame:
    """
    Convert time_since_sale and time_since_build to categorical factors with 10-year bins.
    Drops the original continuous columns. Bins: 0-10, 10-20, 20-30, ...
    """
    X = X.copy()
    for col in TIME_COLS:
        if col not in X.columns:
            continue
        t = X[col].fillna(X[col].median())
        t = np.maximum(t, 0)
        # 10-year bins: 0-10, 10-20, 20-30, ...
        t_max = int(t.max()) + 1
        bin_edges = np.arange(0, t_max + TIME_BIN_YEARS, TIME_BIN_YEARS)
        bin_edges = np.unique(bin_edges)
        labels = [f"{int(bin_edges[i])}-{int(bin_edges[i+1])}" for i in range(len(bin_edges) - 1)]
        if len(bin_edges) > 1:
            X[f"{col}_bin"] = pd.cut(t, bins=bin_edges, include_lowest=True, right=False, labels=labels)
            X[f"{col}_bin"] = X[f"{col}_bin"].astype(str)  # for one-hot encoding
        X = X.drop(columns=[col])
    return X


def prepare_modeling_data(
    X: pd.DataFrame, y: pd.Series
) -> tuple[np.ndarray, np.ndarray, list[str], object]:
    """
    Prepare X, y for modeling: handle missing, encode categoricals, scale.
    Converts time_since_sale/build to 5-year bin factors (categorical).
    Returns X_processed, y_processed, feature_names, preprocessor.
    """
    numeric, categorical = get_feature_types(X)

    # Drop rows with missing target
    mask = y.notna()
    X, y = X[mask].copy(), y[mask].astype(int)

    # Convert time columns to 5-year bin factors (drops continuous time cols)
    X = add_time_bin_factors(X)
    numeric, categorical = get_feature_types(X)  # refresh after new columns

    # Fill missing numeric with median
    for c in numeric:
        if X[c].isnull().any():
            X[c] = X[c].fillna(X[c].median())

    # For high-cardinality categoricals, drop columns with > 20 unique values
    # to avoid feature explosion from one-hot encoding
    cat_to_use = []
    for c in categorical:
        if X[c].nunique() <= 20:
            X[c] = X[c].fillna("MISSING")
            cat_to_use.append(c)

    # Build preprocessor
    transformers = []
    if numeric:
        transformers.append(("num", StandardScaler(), numeric))
    if cat_to_use:
        transformers.append(
            (
                "cat",
                OneHotEncoder(handle_unknown="ignore", sparse_output=False),
                cat_to_use,
            )
        )

    preprocessor = ColumnTransformer(transformers, remainder="drop")
    X_processed = preprocessor.fit_transform(X)
    feature_names = []
    if numeric:
        feature_names.extend(numeric)
    if cat_to_use:
        cat_names = preprocessor.named_transformers_["cat"].get_feature_names_out(
            cat_to_use
        )
        feature_names.extend(cat_names)

    return X_processed, np.array(y), feature_names, preprocessor


def run_lasso_selection(X: np.ndarray, y: np.ndarray, feature_names: list[str]) -> list[str]:
    """LASSO (L1) for feature selection. Use LogisticRegression with L1 penalty."""
    # For binary classification, we use LogisticRegression with L1
    model = LogisticRegression(penalty="l1", solver="saga", C=0.1, max_iter=2000, random_state=42)
    model.fit(X, y)
    coef = np.abs(model.coef_[0])
    threshold = np.percentile(coef[coef > 0], 10) if (coef > 0).any() else 0
    selected = [feature_names[i] for i in range(len(feature_names)) if coef[i] > threshold]
    return selected, coef


def run_ridge_selection(X: np.ndarray, y: np.ndarray, feature_names: list[str]) -> tuple[list[str], np.ndarray]:
    """Ridge regression - coefficients indicate importance (no sparsity)."""
    model = LogisticRegression(penalty="l2", solver="lbfgs", C=1.0, max_iter=2000, random_state=42)
    model.fit(X, y)
    coef = np.abs(model.coef_[0])
    # Take top 30 by magnitude
    top_k = min(30, len(feature_names))
    idx = np.argsort(coef)[::-1][:top_k]
    selected = [feature_names[i] for i in idx]
    return selected, coef


def run_elastic_net_selection(
    X: np.ndarray, y: np.ndarray, feature_names: list[str]
) -> tuple[list[str], np.ndarray]:
    """Elastic Net (L1 + L2) for feature selection."""
    model = LogisticRegression(
        penalty="elasticnet", solver="saga", l1_ratio=0.5, C=0.1, max_iter=2000, random_state=42
    )
    model.fit(X, y)
    coef = np.abs(model.coef_[0])
    threshold = np.percentile(coef[coef > 0], 10) if (coef > 0).any() else 0
    selected = [feature_names[i] for i in range(len(feature_names)) if coef[i] > threshold]
    return selected, coef


def run_rfe_selection(
    X: np.ndarray, y: np.ndarray, feature_names: list[str], n_features: int = 25
) -> list[str]:
    """Recursive Feature Elimination with Logistic Regression."""
    model = LogisticRegression(max_iter=2000, random_state=42)
    # step=5 for speed when many features
    step = max(1, min(5, X.shape[1] // 20))
    rfe = RFE(model, n_features_to_select=n_features, step=step)
    rfe.fit(X, y)
    selected = [feature_names[i] for i in range(len(feature_names)) if rfe.support_[i]]
    return selected


def run_mutual_info_selection(
    X: np.ndarray, y: np.ndarray, feature_names: list[str], k: int = 25
) -> tuple[list[str], np.ndarray]:
    """Mutual information for feature importance."""
    mi = mutual_info_classif(X, y, random_state=42)
    idx = np.argsort(mi)[::-1][:k]
    selected = [feature_names[i] for i in idx]
    return selected, mi


def run_feature_selection(
    X: np.ndarray, y: np.ndarray, feature_names: list[str], target_name: str
) -> dict[str, list[str]]:
    """Run all feature selection methods and return selected features."""
    suffix = f"_{target_name}"
    print("\n" + "=" * 60)
    print(f"FEATURE SELECTION: {target_name}")
    print("=" * 60)

    results = {}

    # LASSO
    selected_lasso, coef_lasso = run_lasso_selection(X, y, feature_names)
    results["lasso"] = selected_lasso
    print(f"\nLASSO selected {len(selected_lasso)} features")
    print("  Top 10:", selected_lasso[:10])

    # Ridge (top 30 by |coefficient|)
    selected_ridge, coef_ridge = run_ridge_selection(X, y, feature_names)
    results["ridge"] = selected_ridge
    print(f"\nRidge top 30: {len(selected_ridge)} features")
    print("  Top 10:", selected_ridge[:10])

    # Elastic Net
    selected_en, coef_en = run_elastic_net_selection(X, y, feature_names)
    results["elastic_net"] = selected_en
    print(f"\nElastic Net selected {len(selected_en)} features")
    print("  Top 10:", selected_en[:10])

    # RFE
    selected_rfe = run_rfe_selection(X, y, feature_names, n_features=25)
    results["rfe"] = selected_rfe
    print(f"RFE selected {len(selected_rfe)} features")

    # Mutual Information
    selected_mi, mi_scores = run_mutual_info_selection(X, y, feature_names, k=25)
    results["mutual_info"] = selected_mi
    print(f"Mutual Info top 25: {len(selected_mi)} features")

    # Consensus: features selected by at least 2 methods
    all_selected = []
    for method, feats in results.items():
        all_selected.extend(feats)
    counts = Counter(all_selected)
    consensus = [f for f, c in counts.items() if c >= 2]
    results["consensus"] = consensus
    print(f"\nConsensus (≥2 methods): {len(consensus)} features")

    # Plot feature importance from LASSO
    top_k = min(25, len(feature_names))
    idx = np.argsort(coef_lasso)[::-1][:top_k]
    fig, ax = plt.subplots(figsize=(10, 8))
    ax.barh(range(top_k), coef_lasso[idx], color="steelblue")
    ax.set_yticks(range(top_k))
    ax.set_yticklabels([feature_names[i] for i in idx], fontsize=8)
    ax.invert_yaxis()
    ax.set_title(f"LASSO Feature Importance (|coefficient|) - {target_name}")
    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / f"feature_selection_lasso_importance{suffix}.png", dpi=150)
    plt.close()
    print(f"\nSaved: {OUTPUT_DIR / f'feature_selection_lasso_importance{suffix}.png'}")

    # Plot Mutual Information
    top_k = min(25, len(feature_names))
    idx = np.argsort(mi_scores)[::-1][:top_k]
    fig, ax = plt.subplots(figsize=(10, 8))
    ax.barh(range(top_k), mi_scores[idx], color="coral")
    ax.set_yticks(range(top_k))
    ax.set_yticklabels([feature_names[i] for i in idx], fontsize=8)
    ax.invert_yaxis()
    ax.set_title(f"Mutual Information Feature Importance - {target_name}")
    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / f"feature_selection_mutual_info{suffix}.png", dpi=150)
    plt.close()
    print(f"Saved: {OUTPUT_DIR / f'feature_selection_mutual_info{suffix}.png'}")

    # Plot Ridge (top 25 by |coefficient|)
    top_k = min(25, len(feature_names))
    idx = np.argsort(coef_ridge)[::-1][:top_k]
    fig, ax = plt.subplots(figsize=(10, 8))
    ax.barh(range(top_k), coef_ridge[idx], color="seagreen")
    ax.set_yticks(range(top_k))
    ax.set_yticklabels([feature_names[i] for i in idx], fontsize=8)
    ax.invert_yaxis()
    ax.set_title(f"Ridge Feature Importance (|coefficient|) - {target_name}")
    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / f"feature_selection_ridge_importance{suffix}.png", dpi=150)
    plt.close()
    print(f"Saved: {OUTPUT_DIR / f'feature_selection_ridge_importance{suffix}.png'}")

    # Plot Elastic Net (top 25 by |coefficient|)
    top_k = min(25, len(feature_names))
    idx = np.argsort(coef_en)[::-1][:top_k]
    fig, ax = plt.subplots(figsize=(10, 8))
    ax.barh(range(top_k), coef_en[idx], color="darkorange")
    ax.set_yticks(range(top_k))
    ax.set_yticklabels([feature_names[i] for i in idx], fontsize=8)
    ax.invert_yaxis()
    ax.set_title(f"Elastic Net Feature Importance (|coefficient|) - {target_name}")
    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / f"feature_selection_elasticnet_importance{suffix}.png", dpi=150)
    plt.close()
    print(f"Saved: {OUTPUT_DIR / f'feature_selection_elasticnet_importance{suffix}.png'}")

    return results


# =============================================================================
# 3. CLASSIFICATION MODELS
# =============================================================================


def get_feature_indices(selected_names: list[str], all_names: list[str]) -> list[int]:
    """Get column indices for selected feature names."""
    name_to_idx = {n: i for i, n in enumerate(all_names)}
    return [name_to_idx[n] for n in selected_names if n in name_to_idx]


def evaluate_model(
    model,
    X_train: np.ndarray,
    X_test: np.ndarray,
    y_train: np.ndarray,
    y_test: np.ndarray,
    name: str,
) -> dict:
    """Train, predict, and return metrics."""
    model.fit(X_train, y_train)
    y_pred = model.predict(X_test)
    y_prob = model.predict_proba(X_test)[:, 1] if hasattr(model, "predict_proba") else None

    metrics = {
        "model": name,
        "accuracy": accuracy_score(y_test, y_pred),
        "precision": precision_score(y_test, y_pred, zero_division=0),
        "recall": recall_score(y_test, y_pred, zero_division=0),
        "f1": f1_score(y_test, y_pred, zero_division=0),
        "roc_auc": roc_auc_score(y_test, y_prob) if y_prob is not None else 0,
    }
    return metrics, y_pred, y_prob


def run_classification_models(
    X: np.ndarray,
    y: np.ndarray,
    feature_names: list[str],
    selected_features: list[str],
    target_name: str,
) -> None:
    """Train and evaluate classification models on selected features."""
    suffix = f"_{target_name}"
    print("\n" + "=" * 60)
    print(f"CLASSIFICATION MODELS: {target_name}")
    print("=" * 60)

    idx = get_feature_indices(selected_features, feature_names)
    X_sel = X[:, idx] if idx else X
    selected_feature_names = [feature_names[i] for i in idx] if idx else feature_names[: X.shape[1]]

    X_train, X_test, y_train, y_test = train_test_split(
        X_sel, y, test_size=0.25, random_state=42, stratify=y
    )

    models = {
        "Logistic Regression": LogisticRegression(max_iter=2000, random_state=42),
        "Decision Tree (CART)": DecisionTreeClassifier(random_state=42, max_depth=10),
        "Random Forest": RandomForestClassifier(n_estimators=100, random_state=42, max_depth=10),
        "Gradient Boosting": GradientBoostingClassifier(
            n_estimators=100, max_depth=5, random_state=42
        ),
    }

    # Try XGBoost if available
    try:
        import xgboost as xgb
        models["XGBoost"] = xgb.XGBClassifier(n_estimators=100, max_depth=5, random_state=42)
    except ImportError:
        pass

    all_metrics = []
    fig, axes = plt.subplots(2, 3, figsize=(14, 10))
    axes = axes.flatten()

    for i, (name, model) in enumerate(models.items()):
        metrics, y_pred, y_prob = evaluate_model(
            model, X_train, X_test, y_train, y_test, name
        )
        all_metrics.append(metrics)
        print(f"\n{name}:")
        print(f"  Accuracy: {metrics['accuracy']:.4f}, F1: {metrics['f1']:.4f}, ROC-AUC: {metrics['roc_auc']:.4f}")

        # Confusion matrix
        cm = confusion_matrix(y_test, y_pred)
        ax = axes[i]
        sns.heatmap(cm, annot=True, fmt="d", cmap="Blues", ax=ax)
        ax.set_title(name)
        ax.set_xlabel("Predicted")
        ax.set_ylabel("Actual")

    # Hide unused subplot
    for j in range(len(models), len(axes)):
        axes[j].set_visible(False)

    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / f"classification_confusion_matrices{suffix}.png", dpi=150)
    plt.close()
    print(f"\nSaved: {OUTPUT_DIR / f'classification_confusion_matrices{suffix}.png'}")

    # ROC curves
    fig, ax = plt.subplots(figsize=(8, 6))
    for (name, model), m in zip(models.items(), all_metrics):
        model.fit(X_train, y_train)
        y_prob = model.predict_proba(X_test)[:, 1]
        fpr, tpr, _ = roc_curve(y_test, y_prob)
        ax.plot(fpr, tpr, label=f"{name} (AUC={m['roc_auc']:.3f})")
    ax.plot([0, 1], [0, 1], "k--")
    ax.set_xlabel("False Positive Rate")
    ax.set_ylabel("True Positive Rate")
    ax.set_title(f"ROC Curves - {target_name}")
    ax.legend()
    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / f"classification_roc_curves{suffix}.png", dpi=150)
    plt.close()
    print(f"Saved: {OUTPUT_DIR / f'classification_roc_curves{suffix}.png'}")

    # Summary table
    df_metrics = pd.DataFrame(all_metrics)
    df_metrics = df_metrics.drop(columns=["model"]).assign(model=[m["model"] for m in all_metrics])
    df_metrics = df_metrics[["model", "accuracy", "precision", "recall", "f1", "roc_auc"]]
    print("\n--- Summary ---")
    print(df_metrics.to_string(index=False))
    df_metrics.to_csv(OUTPUT_DIR / f"classification_metrics{suffix}.csv", index=False)
    print(f"\nSaved: {OUTPUT_DIR / f'classification_metrics{suffix}.csv'}")

    # Logistic Regression interpretability: coefficients, p-values, % change in odds
    logit_coef_report(
        X_train, y_train, selected_feature_names, target_name
    )


def logit_coef_report(
    X_train: np.ndarray,
    y_train: np.ndarray,
    feature_names: list[str],
    target_name: str,
) -> None:
    """
    Fit Logistic Regression via statsmodels for interpretability.
    Report: coefficient (log-odds), p-value, odds ratio, % change in odds.
    """
    suffix = f"_{target_name}"
    try:
        import statsmodels.api as sm
    except ImportError:
        print("\n(statsmodels not installed; skipping logistic regression coefficients report)")
        return

    # Add constant for intercept
    X_sm = sm.add_constant(X_train, has_constant="add")
    # Truncate long feature names for display
    sm_names = ["const"] + list(feature_names)

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")  # suppress convergence warnings from statsmodels
            logit = sm.Logit(y_train, X_sm)
            result = logit.fit(disp=0, maxiter=500)
    except Exception as e:
        print(f"\nStatsmodels Logit failed ({e}); skipping coefficients report")
        return

    # Build report
    coef = np.asarray(result.params)
    pvalues = np.asarray(result.pvalues)
    odds_ratio = np.exp(coef)
    # % change in odds per 1-unit increase: (exp(coef)-1)*100
    pct_change = (odds_ratio - 1) * 100

    df = pd.DataFrame({
        "feature": sm_names,
        "coef_log_odds": coef,
        "pvalue": pvalues,
        "odds_ratio": odds_ratio,
        "pct_change_odds": pct_change,
    })
    # Sort by |coef| for interpretability
    df = df.sort_values("coef_log_odds", key=abs, ascending=False).reset_index(drop=True)
    df["significant"] = df["pvalue"] < 0.05

    out_path = OUTPUT_DIR / f"logistic_regression_coefficients{suffix}.csv"
    df.to_csv(out_path, index=False)
    print(f"\nSaved: {out_path}")

    n_sig = df["significant"].sum()
    print("\n" + "-" * 70)
    print(f"Logistic Regression Coefficients ({target_name})")
    print("-" * 70)
    print("coef_log_odds = log-odds; pct_change_odds = % change in odds per 1-unit increase")
    print(f"significant = p < 0.05 ({n_sig} of {len(df)} features)")
    # Display with rounded values
    df_display = df.copy()
    df_display["coef_log_odds"] = df_display["coef_log_odds"].round(4)
    def fmt_pval(x):
        if pd.isna(x) or x == 0:
            return str(x)
        return f"{x:.2e}" if x < 0.01 else f"{x:.4f}"
    df_display["pvalue"] = df_display["pvalue"].apply(fmt_pval)
    df_display["odds_ratio"] = df_display["odds_ratio"].round(4)
    df_display["pct_change_odds"] = df_display["pct_change_odds"].round(2)
    print(df_display.to_string(index=False))
    print("-" * 70)


# =============================================================================
# MAIN
# =============================================================================


def main() -> None:
    print("Loading data...")
    X, targets = load_and_prepare_data()
    print(f"Targets: {list(targets.keys())}")

    # Shared EDA (once)
    run_eda(X, targets, target_name=None)

    for target_name in TARGETS:
        if target_name not in targets:
            print(f"\nSkipping {target_name} (not in data)")
            continue

        # Target-specific EDA
        run_eda(X, targets, target_name=target_name)

        print(f"\nPreparing data for modeling ({target_name})...")
        X_processed, y_processed, feature_names, preprocessor = prepare_modeling_data(
            X, targets[target_name]
        )
        print(f"Processed shape: {X_processed.shape}")

        results = run_feature_selection(
            X_processed, y_processed, feature_names, target_name
        )

        # Use consensus features for modeling (fallback to LASSO if empty)
        selected = results["consensus"]
        if not selected:
            selected = results["lasso"]
        if not selected:
            selected = feature_names[:30]  # fallback

        print(f"\nUsing {len(selected)} features for classification ({target_name}).")
        run_classification_models(
            X_processed, y_processed, feature_names, selected, target_name
        )

    print("\n" + "=" * 60)
    print("DONE. Outputs saved to:", OUTPUT_DIR)
    print("=" * 60)


if __name__ == "__main__":
    main()
