"""Tests for pure transform/utility functions across the pipeline."""

import json

import numpy as np
import pandas as pd
import pytest


class TestOwnerParsing:
    """Test owner name parsing from FinalFilters.py."""

    @pytest.fixture(autouse=True)
    def _import(self):
        from FinalFilters import parse_owner, is_legal_entity, format_subdivision
        self.parse_owner = parse_owner
        self.is_legal_entity = is_legal_entity
        self.format_subdivision = format_subdivision

    def test_single_owner(self):
        o1, o2 = self.parse_owner("SMITH JOHN A")
        assert o1 == "Smith, John A"
        assert pd.isna(o2)

    def test_two_owners_shared_last(self):
        o1, o2 = self.parse_owner("SMITH JOHN & JANE")
        assert o1 == "Smith, John"
        assert o2 == "Smith, Jane"

    def test_two_owners_different_last(self):
        o1, o2 = self.parse_owner("SMITH JOHN & JANE DOE")
        assert o1 == "Smith, John"
        assert "Doe" in o2

    def test_legal_entity_passthrough(self):
        o1, o2 = self.parse_owner("JONES FAMILY TRUST")
        assert "TRUST" in o1
        assert pd.isna(o2)

    def test_legal_entity_detection(self):
        assert self.is_legal_entity("SMITH LLC")
        assert self.is_legal_entity("JONES FAMILY TRUST")
        assert self.is_legal_entity("ABC CORPORATION")
        assert not self.is_legal_entity("SMITH JOHN")
        assert not self.is_legal_entity("DOE JANE A")

    def test_empty_owner(self):
        o1, o2 = self.parse_owner("")
        assert pd.isna(o1)
        assert pd.isna(o2)

    def test_na_owner(self):
        o1, o2 = self.parse_owner(pd.NA)
        assert pd.isna(o1)
        assert pd.isna(o2)


class TestSubdivisionFormatting:
    """Test subdivision name formatting from FinalFilters.py."""

    @pytest.fixture(autouse=True)
    def _import(self):
        from FinalFilters import format_subdivision
        self.format_subdivision = format_subdivision

    def test_removes_boilerplate(self):
        result = self.format_subdivision("Green Meadows Filing 2")
        assert "Filing" not in result
        assert "2" not in result
        assert "Green" in result

    def test_limits_tokens(self):
        result = self.format_subdivision("Very Long Subdivision Name Here Phase 3")
        tokens = result.split()
        assert len(tokens) <= 3

    def test_na_passthrough(self):
        assert pd.isna(self.format_subdivision(pd.NA))

    def test_capitalizes(self):
        result = self.format_subdivision("OAK HILLS")
        assert result == "Oak Hills"


class TestHaversineDistance:
    """Test haversine distance calculations."""

    @pytest.fixture(autouse=True)
    def _import(self):
        from Add_Derived_Columns import haversine_miles
        self.haversine_miles = haversine_miles

    def test_same_point_is_zero(self):
        d = self.haversine_miles(
            np.array([40.0]), np.array([-105.0]),
            np.array([40.0]), np.array([-105.0]),
        )
        assert d[0] == pytest.approx(0.0, abs=1e-10)

    def test_known_distance(self):
        # Boulder to Denver is roughly 25-30 miles
        d = self.haversine_miles(
            np.array([40.015]), np.array([-105.270]),  # Boulder
            np.array([39.739]), np.array([-104.990]),   # Denver
        )
        assert 20 < d[0] < 35

    def test_vectorized(self):
        lats1 = np.array([40.0, 40.0])
        lons1 = np.array([-105.0, -105.0])
        lats2 = np.array([40.0, 41.0])
        lons2 = np.array([-105.0, -105.0])
        d = self.haversine_miles(lats1, lons1, lats2, lons2)
        assert d[0] == pytest.approx(0.0, abs=1e-10)
        assert d[1] > 60  # ~69 miles per degree latitude


class TestSaleDateParsing:
    """Test sale date year parsing."""

    @pytest.fixture(autouse=True)
    def _import(self):
        from Add_Derived_Columns import parse_sale_year
        self.parse_sale_year = parse_sale_year

    def test_mdy_short_year(self):
        s = pd.Series(["6/15/18", "3/22/21"])
        result = self.parse_sale_year(s)
        assert result.iloc[0] == 2018
        assert result.iloc[1] == 2021

    def test_mdy_long_year(self):
        s = pd.Series(["6/15/2018"])
        result = self.parse_sale_year(s)
        assert result.iloc[0] == 2018

    def test_old_dates(self):
        s = pd.Series(["1/1/95", "12/31/85"])
        result = self.parse_sale_year(s)
        assert result.iloc[0] == 1995
        assert result.iloc[1] == 1985

    def test_na_handling(self):
        s = pd.Series([None, "", pd.NA])
        result = self.parse_sale_year(s)
        assert result.isna().all()

    def test_garbage_returns_nan(self):
        s = pd.Series(["not_a_date", "abc"])
        result = self.parse_sale_year(s)
        assert result.isna().all()


class TestRegridFilters:
    """Test Regrid property filters from InitialScript.py."""

    @pytest.fixture(autouse=True)
    def _import(self):
        from InitialScript import apply_regrid_filters
        self.apply_regrid_filters = apply_regrid_filters

    def test_no_filters_returns_all(self, sample_regrid_df):
        result = self.apply_regrid_filters(sample_regrid_df, {})
        assert len(result) == len(sample_regrid_df)

    def test_usedesc_filter(self, sample_regrid_df):
        sample_regrid_df.loc[0, "usedesc"] = "COMMERCIAL"
        result = self.apply_regrid_filters(sample_regrid_df, {
            "usedesc": ["SINGLE FAM.RES.-LAND"]
        })
        assert len(result) == 4

    def test_mainfloorsf_min_filter(self, sample_regrid_df):
        result = self.apply_regrid_filters(sample_regrid_df, {
            "mainfloorsf_min": 1500
        })
        assert all(result["mainfloorsf"] >= 1500)

    def test_saleprice_min_filter(self, sample_regrid_df):
        result = self.apply_regrid_filters(sample_regrid_df, {
            "saleprice_min": 400000
        })
        assert all(result["saleprice"] >= 400000)

    def test_combined_filters(self, sample_regrid_df):
        filters = {
            "usedesc": ["SINGLE FAM.RES.-LAND"],
            "mainfloorsf_min": 1000,
            "saleprice_min": 300000,
        }
        result = self.apply_regrid_filters(sample_regrid_df, filters)
        assert len(result) <= len(sample_regrid_df)
        assert all(result["mainfloorsf"] >= 1000)
        assert all(result["saleprice"] >= 300000)


class TestSolarScoring:
    """Test solar roof scoring functions from Analyze_ProjectSunroof_Data.py."""

    @pytest.fixture(autouse=True)
    def _import(self):
        from Analyze_ProjectSunroof_Data import find_matching_segments, get_all_orientations
        self.find_matching_segments = find_matching_segments
        self.get_all_orientations = get_all_orientations

    def test_south_facing_matches(self):
        row = {"azimuth1": 180, "areaSqMeters1": 50, "quantileStats1": '{"Avg": 1500}'}
        matches = self.find_matching_segments(row, 140, 220)
        assert len(matches) == 1

    def test_too_small_area_rejected(self):
        row = {"azimuth1": 180, "areaSqMeters1": 20, "quantileStats1": '{"Avg": 1500}'}
        matches = self.find_matching_segments(row, 140, 220)
        assert len(matches) == 0

    def test_wrong_azimuth_rejected(self):
        row = {"azimuth1": 10, "areaSqMeters1": 50, "quantileStats1": '{"Avg": 1500}'}
        matches = self.find_matching_segments(row, 140, 220)
        assert len(matches) == 0

    def test_all_orientations(self):
        row = {
            "azimuth0": 100, "areaSqMeters0": 50, "quantileStats0": '{"Avg": 1500}',  # East
            "azimuth1": 180, "areaSqMeters1": 50, "quantileStats1": '{"Avg": 1500}',  # South
            "azimuth2": 250, "areaSqMeters2": 50, "quantileStats2": '{"Avg": 1500}',  # West
        }
        orientations, segments = self.get_all_orientations(row)
        assert "East" in orientations
        assert "South" in orientations
        assert "West" in orientations
        assert len(segments) == 3

    def test_na_values_skipped(self):
        row = {"azimuth1": None, "areaSqMeters1": None, "quantileStats1": None}
        matches = self.find_matching_segments(row, 140, 220)
        assert len(matches) == 0


class TestRoofScore:
    """Test roof score computation from roof_score.py."""

    @pytest.fixture(autouse=True)
    def _import(self):
        from roof_score import compute_roof_score, get_all_orientations, parse_quantile_avg
        self.compute_roof_score = compute_roof_score
        self.get_all_orientations = get_all_orientations
        self.parse_quantile_avg = parse_quantile_avg

    def test_parse_quantile_avg_json_string(self):
        val = json.dumps({"Avg": 1450.5, "Max": 1600, "Min": 1200})
        assert self.parse_quantile_avg(val) == pytest.approx(1450.5)

    def test_parse_quantile_avg_dict(self):
        val = {"Avg": 1450.5}
        assert self.parse_quantile_avg(val) == pytest.approx(1450.5)

    def test_parse_quantile_avg_none(self):
        assert self.parse_quantile_avg(None) is None

    def test_roof_score_south_facing(self):
        row = {
            "azimuth1": 180, "areaSqMeters1": 50,
            "quantileStats1": json.dumps({"Avg": 1500}),
            "segment_count": 3,
        }
        _, segments = self.get_all_orientations(row)
        score = self.compute_roof_score(row, segments)
        assert score is not None
        assert score > 0

    def test_roof_score_no_segments(self):
        row = {"segment_count": 0}
        score = self.compute_roof_score(row, [])
        assert score is None


class TestPermitFeatures:
    """Test permit feature extraction from parse_permits_features.py."""

    @pytest.fixture(autouse=True)
    def _import(self):
        from parse_permits_features import compute_features, get_feature_names
        self.compute_features = compute_features
        self.get_feature_names = get_feature_names

    def test_solar_pv_detected(self):
        df = pd.DataFrame({
            "strap": ["S1"],
            "permit_category": ["energy efficient system"],
            "description": ["Install solar PV panel array 8.5kW"],
        })
        result = self.compute_features(df)
        assert result["solar_pv"].iloc[0] == 1

    def test_battery_detected(self):
        df = pd.DataFrame({
            "strap": ["S1"],
            "permit_category": [""],
            "description": ["Tesla Powerwall battery storage installation"],
        })
        result = self.compute_features(df)
        assert result["battery"].iloc[0] == 1

    def test_ev_charger_detected(self):
        df = pd.DataFrame({
            "strap": ["S1"],
            "permit_category": ["electrical/mechanical"],
            "description": ["Install Level 2 EV charger in garage"],
        })
        result = self.compute_features(df)
        assert result["ev_charger"].iloc[0] == 1

    def test_roof_detected(self):
        df = pd.DataFrame({
            "strap": ["S1"],
            "permit_category": ["re-roof"],
            "description": ["Tear off and reroof"],
        })
        result = self.compute_features(df)
        assert result["roof_new_or_replace"].iloc[0] == 1

    def test_solar_thermal_not_pv(self):
        df = pd.DataFrame({
            "strap": ["S1"],
            "permit_category": ["energy efficient system"],
            "description": ["Install solar water heater thermal system"],
        })
        result = self.compute_features(df)
        assert result["solar_pv"].iloc[0] == 0
        assert result["water_heater_solar_thermal"].iloc[0] == 1

    def test_gas_water_heater(self):
        df = pd.DataFrame({
            "strap": ["S1"],
            "permit_category": ["water heater"],
            "description": ["Replace gas water heater 50 gal"],
        })
        result = self.compute_features(df)
        assert result["water_heater"].iloc[0] == 1
        assert result["water_heater_gas"].iloc[0] == 1
        assert result["water_heater_electric"].iloc[0] == 0

    def test_heat_pump_not_water_heater(self):
        df = pd.DataFrame({
            "strap": ["S1"],
            "permit_category": [""],
            "description": ["Install mini split heat pump HVAC system"],
        })
        result = self.compute_features(df)
        assert result["heat_pump"].iloc[0] == 1

    def test_feature_names_complete(self):
        names = self.get_feature_names()
        assert "solar_pv" in names
        assert "battery" in names
        assert "ev_charger" in names
        assert len(names) == 19

    def test_all_features_are_binary(self, sample_permits_df):
        result = self.compute_features(sample_permits_df)
        feature_cols = [c for c in result.columns if c != "strap"]
        for col in feature_cols:
            assert set(result[col].unique()).issubset({0, 1}), f"{col} has non-binary values"

    def test_empty_descriptions_dont_crash(self):
        df = pd.DataFrame({
            "strap": ["S1", "S2"],
            "permit_category": ["", None],
            "description": [None, ""],
        })
        result = self.compute_features(df)
        assert len(result) == 2
