"""
Logistic regression for solar panel classification (interpretable output).

- Reads CSV
- Trains a logistic regression on selected numeric features
- Prints:
  1) dataset / class balance
  2) baseline (majority-class) accuracy
  3) test performance (accuracy + confusion matrix + report)
  4) "interpretability table":
        - coefficient (log-odds)
        - odds ratio (multiplicative effect on odds per +1 unit)
        - percent change in odds
        - (optional) standardized odds ratio (effect per 1 std dev)

Requires: pandas, numpy, scikit-learn
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix
from sklearn.model_selection import train_test_split


# --------------------
# Configuration
# --------------------
INPUT_CSV = Path("data/working/Boulder_CO_Regrid_joined_with_API test.csv")
TARGET_COLUMN = "solar_panels"

FEATURE_COLUMNS: list[str] = [
    # 'usecode','zoning',
    # 'yearbuilt',
    # 'numstories','numrooms',
    # 'num_bath','num_bath_partial','num_bedrooms',
    # 'improvval','landval','parval',
    # 'saleprice',
    # 'szip5',
    # 'lat','lon',
    # 'area_building',
    # 'sqft',
    # 'll_gissqft','plss_township','plss_section','plss_range',
    # 'shapestare','shapestlen',
    # 'designcode',
    # 'qualitycode','bldgclass',
    # 'constcode','constcodedscr','compcode','effectiveyear','bsmtsf','bsmttype',
    # 'carstoragesf','carstoragetype',
    'ac',
    'heating',
    # 'extwallprim',
    # 'intwall','roof_cover',
    # 'roof_coverdscr','mainfloorsf','nbrbedroom','nbrroomsnobath',
    # 'nbrthreeqtrbaths','nbrfullbaths','nbrhalfbaths','landunitvalue',
    # 'landunittype','status_cd','sub_code','building_num','role_cd','pct_own',
    # 'taxarea','mill_levy','bldacutalval','landacutalval',
    # 'totalactualval',

    # 'calculated_build_year',
    # 'calculated_roof_age',
    # 'sunshine',
    # 'segment_count',
    # 'matching_segment_count','matching_segment_sum',
    # 'matching_segment_max',
    # 'solar_score',
    # 'neighbors_w_solar_0_5_mi',
    # 'neighbors_w_solar_0_25_mi',
    'neighbors_w_solar_0_1_mi',
    # 'neighbors_w_solar_0_05_mi',
    # 'time_since_sale',
    'time_since_build',
    'city_solar_percentage',
    'recent_rebuild',
    'recent_build',
    'recent_purchase'
]





RANDOM_STATE = 42
TEST_SIZE = 0.25
MAX_ROWS = 5000  # set to None to use all rows


# --------------------
# Helpers
# --------------------
def yes_no_to_int(s: pd.Series) -> pd.Series:
    s2 = s.astype(str).str.strip().str.lower()
    return (s2 == "yes").astype(int)


def majority_baseline_accuracy(y: pd.Series) -> float:
    # Predict the most common class every time
    p = y.value_counts(normalize=True).max()
    return float(p)


def format_confusion(cm: np.ndarray) -> pd.DataFrame:
    # cm shape: [[TN, FP], [FN, TP]]
    return pd.DataFrame(
        cm,
        index=["True: No", "True: Yes"],
        columns=["Pred: No", "Pred: Yes"],
    )


def build_effect_table(
    feature_names: list[str],
    coefs: np.ndarray,
    intercept: float,
    x_train: pd.DataFrame,
) -> pd.DataFrame:
    """
    Creates an interpretation table:
    - coef: log-odds change for +1 unit
    - odds_ratio: exp(coef)
    - pct_change_odds: (odds_ratio - 1) * 100
    - std_effect_log_odds: coef * std(feature)  (log-odds per +1 std dev)
    - std_odds_ratio: exp(std_effect_log_odds)
    """
    coefs = np.asarray(coefs).reshape(-1)
    stds = x_train[feature_names].std(ddof=0).to_numpy()

    odds_ratio = np.exp(coefs)
    pct_change = (odds_ratio - 1.0) * 100.0

    std_log_odds = coefs * stds
    std_odds_ratio = np.exp(std_log_odds)

    df = pd.DataFrame(
        {
            "feature": feature_names,
            "coef_log_odds_per_1_unit": coefs,
            "odds_ratio_per_1_unit": odds_ratio,
            "pct_change_in_odds_per_1_unit": pct_change,
            "train_std_dev": stds,
            "std_effect_log_odds_(per_1_std)": std_log_odds,
            "std_odds_ratio_(per_1_std)": std_odds_ratio,
        }
    )

    # Sort by absolute standardized effect (easier to compare across features)
    df["abs_std_effect"] = df["std_effect_log_odds_(per_1_std)"].abs()
    df = df.sort_values("abs_std_effect", ascending=False).drop(columns=["abs_std_effect"])

    # Add intercept as a separate row at the bottom (optional)
    intercept_row = pd.DataFrame(
        {
            "feature": ["(intercept)"],
            "coef_log_odds_per_1_unit": [intercept],
            "odds_ratio_per_1_unit": [np.exp(intercept)],
            "pct_change_in_odds_per_1_unit": [(np.exp(intercept) - 1.0) * 100.0],
            "train_std_dev": [np.nan],
            "std_effect_log_odds_(per_1_std)": [np.nan],
            "std_odds_ratio_(per_1_std)": [np.nan],
        }
    )

    return pd.concat([df, intercept_row], ignore_index=True)


def pretty_print_effects(df_effects: pd.DataFrame) -> None:
    # Friendlier formatting for console viewing
    df2 = df_effects.copy()
    float_cols = [c for c in df2.columns if c != "feature"]
    for c in float_cols:
        df2[c] = df2[c].astype(float)

    # Round for readability
    df2["coef_log_odds_per_1_unit"] = df2["coef_log_odds_per_1_unit"].round(4)
    df2["odds_ratio_per_1_unit"] = df2["odds_ratio_per_1_unit"].round(4)
    df2["pct_change_in_odds_per_1_unit"] = df2["pct_change_in_odds_per_1_unit"].round(1)
    df2["train_std_dev"] = df2["train_std_dev"].round(4)
    df2["std_effect_log_odds_(per_1_std)"] = df2["std_effect_log_odds_(per_1_std)"].round(4)
    df2["std_odds_ratio_(per_1_std)"] = df2["std_odds_ratio_(per_1_std)"].round(4)

    print(df2.to_string(index=False))


# --------------------
# Main
# --------------------
def main() -> None:
    print(f"Reading: {INPUT_CSV}")
    df = pd.read_csv(INPUT_CSV)

    if MAX_ROWS is not None:
        df = df.head(MAX_ROWS)

    if TARGET_COLUMN not in df.columns:
        raise ValueError(f"Target column '{TARGET_COLUMN}' not found.")

    # Clean target first
    target_raw = df[TARGET_COLUMN]
    valid_target = target_raw.notna() & (target_raw.astype(str).str.strip() != "")
    df = df.loc[valid_target].copy()
    y = yes_no_to_int(df[TARGET_COLUMN])

    # Validate features
    missing = [c for c in FEATURE_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"Feature columns not found: {missing}")

    # Keep only rows with all features present
    X = df[FEATURE_COLUMNS]
    valid_features = X.notna().all(axis=1)
    X = X.loc[valid_features].astype(float)
    y = y.loc[valid_features]

    # Basic data summary
    n = len(X)
    pos = int(y.sum())
    neg = int(n - pos)

    print("\n" + "=" * 72)
    print("Dataset summary")
    print("=" * 72)
    print(f"Rows used: {n}")
    print(f"Class balance: Yes={pos} ({pos/n:.1%}), No={neg} ({neg/n:.1%})")
    print(f"Majority-class baseline accuracy: {majority_baseline_accuracy(y):.4f}")

    # Split
    X_train, X_test, y_train, y_test = train_test_split(
        X,
        y,
        test_size=TEST_SIZE,
        random_state=RANDOM_STATE,
        stratify=y,
    )

    # Note: scikit-learn LogisticRegression uses regularization by default.
    # For more "classic" interpretability you might set penalty=None (if your sklearn supports it),
    # but regularization often helps stability. We'll keep defaults and just be explicit.
    model = LogisticRegression(random_state=RANDOM_STATE, max_iter=2000)
    model.fit(X_train, y_train)

    # Predict
    y_pred = model.predict(X_test)
    acc = accuracy_score(y_test, y_pred)
    cm = confusion_matrix(y_test, y_pred)

    print("\n" + "=" * 72)
    print("Test-set performance")
    print("=" * 72)
    print(f"Train size: {len(X_train)} | Test size: {len(X_test)}")
    print(f"Accuracy: {acc:.4f}")
    print("\nConfusion matrix (counts):")
    print(format_confusion(cm).to_string())

    print("\nClassification report:")
    print(classification_report(y_test, y_pred, target_names=["No", "Yes"]))

    # Effects / interpretation
    effects = build_effect_table(
        feature_names=FEATURE_COLUMNS,
        coefs=model.coef_[0],
        intercept=float(model.intercept_[0]),
        x_train=X_train,
    )

    print("\n" + "=" * 72)
    print("Coefficient interpretation")
    print("=" * 72)
    print(
        "How to read:\n"
        "- coef_log_odds_per_1_unit: log-odds change for +1 unit of the feature\n"
        "- odds_ratio_per_1_unit: multiply the odds by this for +1 unit ( >1 increases, <1 decreases )\n"
        "- pct_change_in_odds_per_1_unit: same idea in percent\n"
        "- std_* columns: effect scaled to a 1 standard deviation increase (easier to compare features)\n"
    )
    pretty_print_effects(effects)

    print("\nNote:")
    print("- scikit-learn does not report p-values.")
    print("- If you need p-values, use statsmodels.Logit (unregularized) or do bootstrapping.")


if __name__ == "__main__":
    main()
