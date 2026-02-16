# Data Science: Solar PV Prediction

Feature selection and modeling for predicting `solar_pv` and `solar_pv_recent` (binary) from `data/final/data_science.csv`. The full pipeline (EDA, feature selection, classification) runs for each target; outputs are saved with target-specific suffixes (e.g. `_solar_pv`, `_solar_pv_recent`).

## Setup

```bash
pip install -r requirements.txt
```

## Run

```bash
python feature_selection_and_modeling.py
```

Outputs are saved to `data_science/output/`.

## Non-linear Time Features

For `time_since_sale` and `time_since_build`, we add transforms to capture the hypothesis that **longer time = less likely to get solar** (people who haven't installed for years may not intend to):

- **recency** = 1/(1+time) — higher when recent, decays with time
- **log** = log(1+time) — diminishing effect of each additional year
- **sq** = time² — curvature / amplification at high values

EDA plots `eda_time_since_sale_vs_solar.png` and `eda_time_since_build_vs_solar.png` show solar rate by time bins.

## Pipeline

1. **Exploratory Data Analysis (EDA)**
   - Target distribution
   - Missing values summary
   - Numeric feature distributions
   - Correlation with target
   - Correlation heatmap
   - Boxplots of top features by target
   - Solar PV rate by time_since_sale and time_since_build bins

2. **Feature Selection**
   - **LASSO** (L1 logistic regression) – sparse coefficients
   - **Ridge** (L2) – top 30 by coefficient magnitude
   - **Elastic Net** (L1 + L2)
   - **RFE** (Recursive Feature Elimination)
   - **Mutual Information**
   - **Consensus** – features selected by ≥2 methods

3. **Classification Models**
   - Logistic Regression
   - Decision Tree (CART)
   - Random Forest
   - Gradient Boosting
   - XGBoost (if installed)

## Excluded Columns

- `original_index`, `alt_parcelnumb1` – no predictive power
