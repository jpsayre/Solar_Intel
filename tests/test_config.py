"""Tests for the pipeline configuration system."""

import pytest
import pandas as pd
from pathlib import Path

from pipeline_config import CountyConfig, load_config, validate_inputs


class TestCountyConfig:
    """Test CountyConfig dataclass behavior."""

    def test_basic_creation(self, tmp_path):
        config = CountyConfig(
            county_id="Test_CO",
            state_fips="08",
            state_abbrev="CO",
            regrid_csv=str(tmp_path / "regrid.csv"),
            permits_csv=str(tmp_path / "permits.csv"),
        )
        assert config.county_id == "Test_CO"
        assert config.state_fips == "08"
        assert config.year_min == 2012
        assert config.year_max == 2026

    def test_derived_paths(self, tmp_path):
        config = CountyConfig(
            county_id="Test_CO",
            state_fips="08",
            state_abbrev="CO",
            regrid_csv=str(tmp_path / "regrid.csv"),
            permits_csv=str(tmp_path / "permits.csv"),
        )
        # working/final dirs are under data/{county_id}/
        assert config.county_id in str(config.working_dir)
        assert config.county_id in str(config.final_dir)
        assert config.working_dir.name == "working"
        assert config.final_dir.name == "final"

    def test_intermediate_file_paths_consistent(self, tmp_path):
        config = CountyConfig(
            county_id="Test_CO",
            state_fips="08",
            state_abbrev="CO",
            regrid_csv=str(tmp_path / "regrid.csv"),
            permits_csv=str(tmp_path / "permits.csv"),
        )
        # All working files should be under working_dir
        assert config.sunroof_api_output_path.parent == config.working_dir
        assert config.filtered_api_output_path.parent == config.working_dir
        assert config.regrid_joined_path.parent == config.working_dir
        assert config.parsed_permits_by_year_path.parent == config.working_dir

        # All final files should be under final_dir
        assert config.final_data_path.parent == config.final_dir
        assert config.parsed_permits_path.parent == config.final_dir
        assert config.roof_score_path.parent == config.final_dir
        assert config.regrid_filtered_path.parent == config.final_dir

    def test_acs_cached_per_state(self, tmp_path):
        config_co = CountyConfig(
            county_id="Boulder_CO",
            state_fips="08",
            state_abbrev="CO",
            regrid_csv=str(tmp_path / "a.csv"),
            permits_csv=str(tmp_path / "b.csv"),
        )
        config_co2 = CountyConfig(
            county_id="Jefferson_CO",
            state_fips="08",
            state_abbrev="CO",
            regrid_csv=str(tmp_path / "c.csv"),
            permits_csv=str(tmp_path / "d.csv"),
        )
        # Same state = same ACS cache file
        assert config_co.acs_csv_path == config_co2.acs_csv_path

        config_az = CountyConfig(
            county_id="Maricopa_AZ",
            state_fips="04",
            state_abbrev="AZ",
            regrid_csv=str(tmp_path / "e.csv"),
            permits_csv=str(tmp_path / "f.csv"),
        )
        # Different state = different ACS cache file
        assert config_co.acs_csv_path != config_az.acs_csv_path

    def test_ensure_dirs_creates_directories(self, tmp_path):
        config = CountyConfig(
            county_id="Test_CO",
            state_fips="08",
            state_abbrev="CO",
            regrid_csv=str(tmp_path / "regrid.csv"),
            permits_csv=str(tmp_path / "permits.csv"),
        )
        config.ensure_dirs()
        assert config.working_dir.exists()
        assert config.final_dir.exists()
        assert config.output_dir.exists()

    def test_default_column_mappings(self, tmp_path):
        config = CountyConfig(
            county_id="Test_CO",
            state_fips="08",
            state_abbrev="CO",
            regrid_csv=str(tmp_path / "r.csv"),
            permits_csv=str(tmp_path / "p.csv"),
        )
        assert config.strap_column == "alt_parcelnumb1"
        assert config.lat_column == "lat"
        assert config.lon_column == "lon"
        assert config.permit_strap_column == "strap"
        assert config.permit_date_column == "issue_dt"

    def test_custom_column_mappings(self, tmp_path):
        config = CountyConfig(
            county_id="Test_CO",
            state_fips="08",
            state_abbrev="CO",
            regrid_csv=str(tmp_path / "r.csv"),
            permits_csv=str(tmp_path / "p.csv"),
            permit_strap_column="parcel_no",
            permit_date_column="date_issued",
        )
        assert config.permit_strap_column == "parcel_no"
        assert config.permit_date_column == "date_issued"


class TestLoadConfig:
    """Test config file loading."""

    def test_load_boulder_co(self):
        config = load_config("boulder_co")
        assert config.county_id == "Boulder_CO"
        assert config.state_fips == "08"
        assert config.state_abbrev == "CO"
        assert "regrid" in config.regrid_csv.lower() or "boulder" in config.regrid_csv.lower()
        assert len(config.permit_sources) >= 1

    def test_load_nonexistent_raises(self):
        with pytest.raises(FileNotFoundError):
            load_config("nonexistent_county_xyz")

    def test_load_from_explicit_path(self, project_root):
        config = load_config(str(project_root / "configs" / "boulder_co.py"))
        assert config.county_id == "Boulder_CO"

    def test_load_missing_CONFIG_raises(self, tmp_path):
        bad_config = tmp_path / "bad.py"
        bad_config.write_text("FOO = 'bar'\n")
        with pytest.raises(ValueError, match="must define a CONFIG"):
            load_config(str(bad_config))


class TestValidateInputs:
    """Test input file validation."""

    def test_missing_regrid_file(self, tmp_path):
        config = CountyConfig(
            county_id="Test_CO",
            state_fips="08",
            state_abbrev="CO",
            regrid_csv=str(tmp_path / "nonexistent.csv"),
            permits_csv=str(tmp_path / "nonexistent2.csv"),
        )
        errors = validate_inputs(config)
        assert any("Regrid CSV not found" in e for e in errors)

    def test_missing_columns_in_regrid(self, tmp_path):
        # Create a CSV with wrong columns
        regrid = tmp_path / "regrid.csv"
        pd.DataFrame({"wrong_col": [1]}).to_csv(regrid, index=False)
        permits = tmp_path / "permits.csv"
        pd.DataFrame({"strap": ["S1"], "issue_dt": ["2020-01-01"], "description": ["test"]}).to_csv(permits, index=False)

        config = CountyConfig(
            county_id="Test_CO",
            state_fips="08",
            state_abbrev="CO",
            regrid_csv=str(regrid),
            permits_csv=str(permits),
        )
        errors = validate_inputs(config)
        assert any("Regrid CSV missing columns" in e for e in errors)

    def test_valid_inputs_no_errors(self, tmp_path, sample_regrid_df, sample_permits_df):
        regrid = tmp_path / "regrid.csv"
        sample_regrid_df.to_csv(regrid, index=False)
        permits = tmp_path / "permits.csv"
        sample_permits_df.to_csv(permits, index=False)

        # Also need electricity and mortgage CSVs
        elec = tmp_path / "electricity.csv"
        pd.DataFrame({"col": [1]}).to_csv(elec, index=False)
        mortgage = tmp_path / "mortgage.csv"
        pd.DataFrame({"observation_date": ["2020-01-01"], "MORTGAGE30US": [3.5]}).to_csv(mortgage, index=False)

        config = CountyConfig(
            county_id="Test_CO",
            state_fips="08",
            state_abbrev="CO",
            regrid_csv=str(regrid),
            permits_csv=str(permits),
            electricity_csv=str(elec),
            mortgage_csv=str(mortgage),
        )
        errors = validate_inputs(config)
        assert errors == []

    def test_custom_permit_columns_validated(self, tmp_path, sample_regrid_df):
        regrid = tmp_path / "regrid.csv"
        sample_regrid_df.to_csv(regrid, index=False)

        # Create permits with non-standard column names
        permits = tmp_path / "permits.csv"
        pd.DataFrame({
            "parcel_no": ["S1"],
            "date_issued": ["2020-01-01"],
            "work_description": ["solar pv"],
        }).to_csv(permits, index=False)

        elec = tmp_path / "e.csv"
        pd.DataFrame({"col": [1]}).to_csv(elec, index=False)
        mortgage = tmp_path / "m.csv"
        pd.DataFrame({"col": [1]}).to_csv(mortgage, index=False)

        config = CountyConfig(
            county_id="Test_CO",
            state_fips="08",
            state_abbrev="CO",
            regrid_csv=str(regrid),
            permits_csv=str(permits),
            electricity_csv=str(elec),
            mortgage_csv=str(mortgage),
            permit_strap_column="parcel_no",
            permit_date_column="date_issued",
            permit_description_column="work_description",
        )
        errors = validate_inputs(config)
        assert errors == []

    def test_multi_source_permit_validation(self, tmp_path, sample_regrid_df):
        regrid = tmp_path / "regrid.csv"
        sample_regrid_df.to_csv(regrid, index=False)

        permits1 = tmp_path / "permits1.csv"
        pd.DataFrame({
            "strap": ["S1"], "issue_dt": ["2020-01-01"], "description": ["solar pv"],
        }).to_csv(permits1, index=False)

        permits2 = tmp_path / "permits2.csv"
        pd.DataFrame({
            "parcel_id": ["S2"], "permit_date": ["2021-01-01"], "work_desc": ["reroof"],
        }).to_csv(permits2, index=False)

        elec = tmp_path / "e.csv"
        pd.DataFrame({"col": [1]}).to_csv(elec, index=False)
        mortgage = tmp_path / "m.csv"
        pd.DataFrame({"col": [1]}).to_csv(mortgage, index=False)

        config = CountyConfig(
            county_id="Test_CO",
            state_fips="08",
            state_abbrev="CO",
            regrid_csv=str(regrid),
            electricity_csv=str(elec),
            mortgage_csv=str(mortgage),
            permit_sources=[
                {"csv": str(permits1), "label": "Source 1"},
                {
                    "csv": str(permits2), "label": "Source 2",
                    "strap_column": "parcel_id", "date_column": "permit_date",
                    "description_column": "work_desc",
                },
            ],
        )
        errors = validate_inputs(config)
        assert errors == []

    def test_multi_source_missing_file_reported(self, tmp_path, sample_regrid_df):
        regrid = tmp_path / "regrid.csv"
        sample_regrid_df.to_csv(regrid, index=False)

        permits1 = tmp_path / "permits1.csv"
        pd.DataFrame({
            "strap": ["S1"], "issue_dt": ["2020-01-01"], "description": ["test"],
        }).to_csv(permits1, index=False)

        config = CountyConfig(
            county_id="Test_CO",
            state_fips="08",
            state_abbrev="CO",
            regrid_csv=str(regrid),
            permit_sources=[
                {"csv": str(permits1), "label": "Good"},
                {"csv": str(tmp_path / "missing.csv"), "label": "Missing"},
            ],
        )
        errors = validate_inputs(config)
        assert any("Missing" in e for e in errors)
