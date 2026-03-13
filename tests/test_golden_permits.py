"""
Golden test set: real permit examples with manually verified classifications.

Each row in fixtures/golden_permits.csv is a permit with known-correct
expected_permit_type and expected_features. This test runs compute_features()
and classify_permit_type() on each row and asserts the expected output.

Add new rows to the CSV as edge cases are discovered (especially from
AI cross-check disagreements).
"""

import pandas as pd
import pytest
from pathlib import Path

FIXTURES_DIR = Path(__file__).parent / "fixtures"
GOLDEN_CSV = FIXTURES_DIR / "golden_permits.csv"


@pytest.fixture(scope="module")
def golden_data():
    return pd.read_csv(GOLDEN_CSV, keep_default_na=False)


@pytest.fixture(scope="module")
def feature_funcs():
    from parse_permits_features import compute_features, classify_permit_type, get_feature_names
    return compute_features, classify_permit_type, get_feature_names


def _make_row_df(row):
    """Build a single-row DataFrame for compute_features()."""
    return pd.DataFrame({
        "strap": ["TEST"],
        "permit_category": [row["permit_category"] if row["permit_category"] else ""],
        "description": [row["description"] if row["description"] else ""],
    })


def _row_id(row):
    """Generate readable test ID from row."""
    desc = row["description"][:40] if row["description"] else "(empty)"
    return f"{row['expected_permit_type']}:{desc}"


class TestGoldenPermits:

    def test_golden_csv_exists(self):
        assert GOLDEN_CSV.exists(), f"Golden CSV not found: {GOLDEN_CSV}"

    def test_golden_csv_has_rows(self, golden_data):
        assert len(golden_data) > 0, "Golden CSV is empty"

    def test_permit_type_classification(self, golden_data, feature_funcs):
        compute_features, classify_permit_type, get_feature_names = feature_funcs
        feature_names = get_feature_names()
        failures = []

        for i, row in golden_data.iterrows():
            df = _make_row_df(row)

            # Pass estimated_value if present
            val = row.get("estimated_value")
            est_val = pd.Series([float(val)]) if val != "" else None
            result = compute_features(df, estimated_value=est_val)

            # Classify
            feature_row = {f: result[f].iloc[0] for f in feature_names}
            actual_type = classify_permit_type(feature_row)
            expected_type = row["expected_permit_type"]

            # Compare as sets since permit_type can be comma-separated (multi-type)
            actual_set = set(t.strip() for t in actual_type.split(","))
            expected_set = set(t.strip() for t in expected_type.split(","))
            if actual_set != expected_set:
                desc = row["description"][:50] if row["description"] else "(empty)"
                failures.append(
                    f"Row {i}: expected '{expected_type}', got '{actual_type}' "
                    f"({row['permit_category']} | {desc})"
                )

        if failures:
            pytest.fail(f"{len(failures)} permit_type mismatches:\n" + "\n".join(failures))

    def test_feature_flags(self, golden_data, feature_funcs):
        compute_features, classify_permit_type, get_feature_names = feature_funcs
        feature_names = get_feature_names()
        failures = []

        for i, row in golden_data.iterrows():
            expected_str = row.get("expected_features", "")
            if not expected_str:
                continue  # Skip rows without expected_features

            expected_features = set(f.strip() for f in expected_str.split(",") if f.strip())

            df = _make_row_df(row)
            val = row.get("estimated_value")
            est_val = pd.Series([float(val)]) if val != "" else None
            result = compute_features(df, estimated_value=est_val)

            actual_features = set()
            for f in feature_names:
                if result[f].iloc[0] == 1:
                    actual_features.add(f)

            if actual_features != expected_features:
                desc = row["description"][:50] if row["description"] else "(empty)"
                missing = expected_features - actual_features
                extra = actual_features - expected_features
                msg = f"Row {i} ({desc}):"
                if missing:
                    msg += f" missing={missing}"
                if extra:
                    msg += f" unexpected={extra}"
                failures.append(msg)

        if failures:
            pytest.fail(f"{len(failures)} feature mismatches:\n" + "\n".join(failures))
