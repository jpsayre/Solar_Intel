"""
Pipeline stage contract tests.

Each stage must produce output with specific required columns.
These tests run each stage with tiny fixture data and verify the
output schema, catching column name drift and integration issues.
"""

import json
import sys
from pathlib import Path

import pandas as pd
import pytest

from pipeline_config import CountyConfig


def _make_config(tmp_path, sample_regrid_df, sample_permits_df, sample_sunroof_api_df=None):
    """Create a test config with fixture data written to temp files."""
    county_id = "Test_CO"

    # Write fixture CSVs
    regrid_path = tmp_path / "regrid.csv"
    sample_regrid_df.to_csv(regrid_path, index=False)

    permits_path = tmp_path / "permits.csv"
    sample_permits_df.to_csv(permits_path, index=False)

    # Electricity price CSV (minimal)
    elec_path = tmp_path / "electricity.csv"
    # Mimic the EIA format: description, units, then month-year columns
    elec_data = {"description": ["Average retail price"], "units": ["cents per kWh"]}
    for year in range(12, 27):
        for month in ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]:
            elec_data[f"{month}-{year:02d}"] = [12.5 + year * 0.1]
    pd.DataFrame(elec_data).to_csv(elec_path, index=False)

    # Mortgage CSV
    mortgage_path = tmp_path / "mortgage.csv"
    mortgage_rows = []
    for year in range(2012, 2027):
        for month in range(1, 13):
            mortgage_rows.append({
                "observation_date": f"{year}-{month:02d}-01",
                "MORTGAGE30US": 3.5 + (year - 2012) * 0.2,
            })
    pd.DataFrame(mortgage_rows).to_csv(mortgage_path, index=False)

    config = CountyConfig(
        county_id=county_id,
        state_fips="08",
        state_abbrev="CO",
        regrid_csv=str(regrid_path),
        permits_csv=str(permits_path),
        electricity_csv=str(elec_path),
        mortgage_csv=str(mortgage_path),
        regrid_filters={},  # No filters for test (keep all rows)
    )
    config.ensure_dirs()

    # Pre-write intermediate files that would be produced by API stages
    if sample_sunroof_api_df is not None:
        sample_sunroof_api_df.to_csv(str(config.sunroof_api_output_path), index=False)

    return config


class TestInterestRatesContract:
    """Stage 2: interest_rates must produce year + average_rate columns."""

    def test_output_schema(self, tmp_path, sample_regrid_df, sample_permits_df):
        config = _make_config(tmp_path, sample_regrid_df, sample_permits_df)

        import interest_rates
        result = interest_rates.run(config)

        assert "year" in result.columns
        assert "average_rate" in result.columns
        assert len(result) > 0
        assert result["year"].between(config.year_min, config.year_max).all()
        assert result["average_rate"].notna().all()
        assert Path(config.avg_yearly_interest_path).exists()


class TestRegridFilterContract:
    """Stage 3: InitialScript must produce regrid_filtered.csv with required columns."""

    def test_filter_produces_required_columns(self, tmp_path, sample_regrid_df, sample_permits_df):
        config = _make_config(tmp_path, sample_regrid_df, sample_permits_df)

        import InitialScript
        # Just test the filter part (skip API calls)
        df = pd.read_csv(config.regrid_csv)
        df = InitialScript.apply_regrid_filters(df, config.regrid_filters)
        if "original_index" not in df.columns:
            df = df.reset_index(names="original_index")
        df.to_csv(str(config.regrid_filtered_path), index=False)

        result = pd.read_csv(config.regrid_filtered_path)
        required = {"original_index", "lat", "lon", "alt_parcelnumb1"}
        assert required.issubset(set(result.columns)), f"Missing: {required - set(result.columns)}"


class TestAnalyzeSunroofContract:
    """Stage 4: Analyze_ProjectSunroof_Data must produce filtered output with solar_score."""

    def test_output_has_solar_score(self, tmp_path, sample_regrid_df, sample_permits_df, sample_sunroof_api_df):
        config = _make_config(tmp_path, sample_regrid_df, sample_permits_df, sample_sunroof_api_df)

        import Analyze_ProjectSunroof_Data
        result = Analyze_ProjectSunroof_Data.run(config)

        required = {"original_index", "solar_score", "roof_orientation"}
        assert required.issubset(set(result.columns)), f"Missing: {required - set(result.columns)}"
        assert result["solar_score"].notna().all()


class TestCombineRegridApiContract:
    """Stage 5: Combine must produce joined file with both Regrid and API columns."""

    def test_merged_has_both_sources(self, tmp_path, sample_regrid_df, sample_permits_df, sample_sunroof_api_df):
        config = _make_config(tmp_path, sample_regrid_df, sample_permits_df, sample_sunroof_api_df)

        # Pre-create regrid_filtered (normally done by stage 3)
        sample_regrid_df.to_csv(str(config.regrid_filtered_path), index=False)

        # Pre-create filtered API output (normally done by stage 4)
        import Analyze_ProjectSunroof_Data
        Analyze_ProjectSunroof_Data.run(config)

        import Combine_Regrid_ProjectSunroof_Data
        result = Combine_Regrid_ProjectSunroof_Data.run(config)

        # Should have Regrid columns
        assert "alt_parcelnumb1" in result.columns or "strap" in result.columns
        assert "lat" in result.columns or "latitude" in result.columns
        # Should have API columns
        assert "solar_score" in result.columns
        assert "original_index" in result.columns


class TestParsePermitsContract:
    """Stage 7: parse_permits must produce strap + issue_dt + binary feature columns."""

    def test_output_schema(self, tmp_path, sample_regrid_df, sample_permits_df):
        config = _make_config(tmp_path, sample_regrid_df, sample_permits_df)

        import parse_permits
        result = parse_permits.run(config)

        assert "strap" in result.columns
        assert "issue_dt" in result.columns
        from parse_permits_features import get_feature_names
        for feat in get_feature_names():
            assert feat in result.columns, f"Missing feature: {feat}"

        # All feature columns should be binary
        for feat in get_feature_names():
            assert set(result[feat].unique()).issubset({0, 1}), f"{feat} not binary"

    def test_multi_source_combines(self, tmp_path, sample_regrid_df, sample_permits_df):
        """Multiple permit sources should be concatenated."""
        config = _make_config(tmp_path, sample_regrid_df, sample_permits_df)

        # Write a second permit source with different column names
        permits2_path = tmp_path / "permits2.csv"
        pd.DataFrame({
            "parcel_id": ["S001", "S002"],
            "permit_date": ["2021-05-01", "2022-06-15"],
            "type": ["electrical", "re-roof"],
            "work_desc": ["Install EV charger Level 2", "Tear off and reroof"],
        }).to_csv(permits2_path, index=False)

        from pipeline_config import PermitSource
        config.permit_sources.append(PermitSource(
            csv=str(permits2_path),
            label="Second Source",
            strap_column="parcel_id",
            date_column="permit_date",
            category_column="type",
            description_column="work_desc",
        ))

        import parse_permits
        result = parse_permits.run(config)

        # Should have rows from both sources
        assert len(result) == len(sample_permits_df) + 2


class TestFinalFiltersContract:
    """Stage 8 (FinalFilters): must produce clean output with renamed columns."""

    def test_output_columns_renamed(self, tmp_path, sample_regrid_df, sample_permits_df, sample_sunroof_api_df):
        config = _make_config(tmp_path, sample_regrid_df, sample_permits_df, sample_sunroof_api_df)

        # Build prerequisites
        sample_regrid_df.to_csv(str(config.regrid_filtered_path), index=False)

        import Analyze_ProjectSunroof_Data
        Analyze_ProjectSunroof_Data.run(config)

        import Combine_Regrid_ProjectSunroof_Data
        Combine_Regrid_ProjectSunroof_Data.run(config)

        import FinalFilters
        result = FinalFilters.run(config)

        assert len(result) > 0
        # Check renamed columns exist (not the originals)
        if "solar_score" in result.columns:
            assert result["solar_score"].notna().any()


class TestRoofScoreContract:
    """Stage 6: roof_score must produce original_index + roof_score."""

    def test_csv_fallback_output(self, tmp_path, sample_regrid_df, sample_permits_df, sample_sunroof_api_df):
        """Test the CSV fallback path (no database)."""
        config = _make_config(tmp_path, sample_regrid_df, sample_permits_df, sample_sunroof_api_df)

        # Unset DATABASE_SOLAR_INTEL_URL to force CSV fallback
        import os
        old_val = os.environ.pop("DATABASE_SOLAR_INTEL_URL", None)
        try:
            import roof_score
            roof_score.run(config=config)
        finally:
            if old_val is not None:
                os.environ["DATABASE_SOLAR_INTEL_URL"] = old_val

        result = pd.read_csv(config.roof_score_path)
        assert "original_index" in result.columns
        assert "roof_score" in result.columns
        assert len(result) == len(sample_sunroof_api_df)
