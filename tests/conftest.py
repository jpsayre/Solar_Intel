"""Shared fixtures for pipeline tests."""

import sys
from pathlib import Path

import pandas as pd
import pytest

# Ensure src/ and data_science/ are importable
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "data_science"))


@pytest.fixture
def project_root():
    return PROJECT_ROOT


@pytest.fixture
def tmp_county_dir(tmp_path):
    """Create a temporary county directory structure with fixture data."""
    county_id = "Test_County"
    county_dir = tmp_path / "data" / county_id

    (county_dir / "working").mkdir(parents=True)
    (county_dir / "final").mkdir(parents=True)
    (tmp_path / "data" / "raw").mkdir(parents=True)
    (tmp_path / "data_science" / "output" / county_id / "walk_forward").mkdir(parents=True)
    (tmp_path / "configs").mkdir(parents=True)

    return tmp_path, county_id


@pytest.fixture
def sample_regrid_df():
    """Minimal Regrid-like DataFrame for testing."""
    return pd.DataFrame({
        "original_index": [0, 1, 2, 3, 4],
        "alt_parcelnumb1": ["S001", "S002", "S003", "S004", "S005"],
        "lat": [40.01, 40.02, 40.03, 40.04, 40.05],
        "lon": [-105.27, -105.28, -105.29, -105.30, -105.31],
        "usedesc": ["SINGLE FAM.RES.-LAND"] * 5,
        "zoning_description": ["residential"] * 5,
        "designcodedscr": ["1 Story - Ranch", "2-3 Story", "Split-level", "1 Story - Ranch", "Bi-level"],
        "sales_cd": ["Q"] * 5,
        "mainfloorsf": [1200, 1800, 900, 2000, 1500],
        "saleprice": [350000, 500000, 280000, 600000, 400000],
        "mailadd": ["123 Main St", "456 Oak Ave", "789 Pine Dr", "321 Elm St", "654 Birch Ln"],
        "address": ["123 Main St", "456 Oak Ave", "789 Pine Dr", "321 Elm St", "654 Birch Ln"],
        "yearbuilt": [1990, 2005, 1975, 2015, 1985],
        "year_built_effective_date": [1990, 2005, 1975, 2015, 1985],
        "owner": ["SMITH JOHN & JANE", "DOE ROBERT", "JONES LLC", "MILLER ANNA K", "WILSON MARK & SUE"],
        "city": ["Boulder", "Boulder", "Louisville", "Boulder", "Lafayette"],
        "county": ["Boulder", "Boulder", "Boulder", "Boulder", "Boulder"],
        "state2": ["CO", "CO", "CO", "CO", "CO"],
        "szip5": ["80301", "80302", "80027", "80303", "80026"],
        "subdivision": ["Green Meadows Filing 2", "Oak Hills Pud Phase 1", "", "Elm Creek Addition", "Birch Estates"],
        "area_building": [1200, 1800, 900, 2000, 1500],
        "roof_coverdscr": ["Asphalt", "Tile", "Metal", "Asphalt", "Asphalt"],
        "numstories": [1, 2, 1, 2, 1],
        "numrooms": [6, 8, 5, 9, 7],
        "num_bath": [2, 3, 1, 3, 2],
        "num_bath_partial": [0, 1, 0, 1, 0],
        "num_bedrooms": [3, 4, 2, 4, 3],
        "heatingdscr": ["Forced Air", "Heat Pump", "Electric", "Forced Air", "Forced Air"],
        "calculated_build_year": [1990, 2005, 1975, 2015, 1985],
        "saledate": ["6/15/18", "3/22/21", "11/5/09", "8/1/23", "2/14/15"],
        "sqft": [5000, 7000, 3500, 8000, 6000],
    })


@pytest.fixture
def sample_permits_df():
    """Minimal permits DataFrame for testing."""
    return pd.DataFrame({
        "strap": ["S001", "S001", "S002", "S003", "S004", "S005", "S001"],
        "permit_category": [
            "energy efficient system",
            "re-roof",
            "air conditioner",
            "electrical/mechanical",
            "re-roof",
            "energy efficient system",
            "water heater",
        ],
        "description": [
            "Install solar PV panel array 8.5kW",
            "Tear off and reroof asphalt shingles",
            "Replace AC condenser unit",
            "Service upgrade 200 amp panel",
            "Reroof with new shingles",
            "Install solar PV system 10kW with battery storage powerwall",
            "Replace gas water heater 50 gal",
        ],
        "issue_dt": [
            "2020-03-15", "2019-06-01", "2021-07-20",
            "2018-11-10", "2022-04-05", "2023-01-15", "2020-09-01",
        ],
    })


@pytest.fixture
def sample_sunroof_api_df():
    """Minimal Sunroof API output DataFrame for testing."""
    import json
    rows = []
    for i in range(5):
        row = {
            "original_index": i,
            "input_lat": 40.01 + i * 0.01,
            "input_lon": -105.27 - i * 0.01,
            "ok": True,
            "error": None,
            "latitude": 40.01 + i * 0.01,
            "longitude": -105.27 - i * 0.01,
            "sunshine": 1500 + i * 50,
            "segment_count": 3,
            "center_distance_m": 2.0 + i * 0.5,
        }
        # Add 3 roof segments per property
        for seg in range(1, 4):
            az = 160 + seg * 20  # South-facing
            area = 40.0 + seg * 5
            row[f"azimuth{seg}"] = az
            row[f"areaSqMeters{seg}"] = area
            row[f"sunshineQuantiles{seg}"] = json.dumps([1400 + seg * 10] * 11)
            row[f"quantileStats{seg}"] = json.dumps({
                "Max": 1600.0, "Min": 1200.0, "Avg": 1450.0 + seg * 10
            })
            row[f"center{seg}"] = json.dumps({"lat": 40.01, "lon": -105.27})
            row[f"boundingBox{seg}"] = json.dumps({"sw": {"lat": 40.0, "lon": -105.3}, "ne": {"lat": 40.02, "lon": -105.25}})
        # Fill remaining segments with None
        for seg in range(4, 26):
            for col in ["azimuth", "areaSqMeters", "sunshineQuantiles", "quantileStats", "center", "boundingBox"]:
                row[f"{col}{seg}"] = None
        rows.append(row)
    return pd.DataFrame(rows)
