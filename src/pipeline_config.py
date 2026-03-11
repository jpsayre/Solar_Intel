"""
County-agnostic pipeline configuration.

Each county gets a Python dict config. The CountyConfig dataclass
provides typed access and auto-generates all intermediate file paths.

Usage:
    from pipeline_config import load_config

    config = load_config("boulder_co")  # loads configs/boulder_co.py
    # or
    config = load_config("/path/to/my_config.py")
"""

from __future__ import annotations

import importlib.util
import sys
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent


@dataclass
class PermitSource:
    """One permit data source (e.g. one city's permit records).

    Each source has its own column mappings since different cities/counties
    use different column names and formats.
    """
    csv: str                                # path to the CSV file
    label: str = ""                         # human label (e.g. "City of Boulder")
    strap_column: str = "strap"             # parcel ID column (must match Regrid's strap_column)
    date_column: str = "issue_dt"           # permit date column
    category_column: str = "permit_category"  # permit category/type column (optional)
    description_column: str = "description"  # permit description column

    def __post_init__(self):
        self.csv = str(_resolve_path(self.csv))
        if not self.label:
            self.label = Path(self.csv).stem


def _resolve_path(p: str) -> Path:
    path = Path(p)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path


@dataclass
class CountyConfig:
    """All settings for a single county pipeline run."""

    # --- Required ---
    county_id: str              # e.g. "Boulder_CO"
    state_fips: str             # e.g. "08" for Colorado
    state_abbrev: str           # e.g. "CO"
    regrid_csv: str             # path to raw Regrid export

    # --- Permit sources (list of dicts or single path) ---
    # Use permit_sources for multiple cities/sources:
    #   permit_sources: [{"csv": "...", "strap_column": "...", ...}, ...]
    # Or use permits_csv for a single source (backward compatible):
    #   permits_csv: "path/to/permits.csv"
    permit_sources: list = field(default_factory=list)
    permits_csv: str = ""  # legacy single-source shorthand

    # Legacy single-source column mappings (used when permits_csv is set)
    permit_strap_column: str = "strap"
    permit_date_column: str = "issue_dt"
    permit_category_column: str = "permit_category"
    permit_description_column: str = "description"

    # --- Shared data (defaults point to project data/raw/) ---
    electricity_csv: str = ""
    mortgage_csv: str = ""

    # --- Year range for permit panel ---
    year_min: int = 2012
    year_max: int = 2026

    # --- Column mappings (Regrid) ---
    strap_column: str = "alt_parcelnumb1"
    lat_column: str = "lat"
    lon_column: str = "lon"

    # --- Regrid filters (customize per county) ---
    regrid_filters: dict = field(default_factory=dict)

    # --- Permit category overrides (for counties with different naming) ---
    permit_category_overrides: dict = field(default_factory=dict)

    def __post_init__(self):
        # Resolve paths relative to project root
        self.regrid_csv = str(_resolve_path(self.regrid_csv))
        if not self.electricity_csv:
            self.electricity_csv = str(PROJECT_ROOT / "data" / "raw" / "Average_retail_price_of_electricity.csv")
        else:
            self.electricity_csv = str(_resolve_path(self.electricity_csv))
        if not self.mortgage_csv:
            self.mortgage_csv = str(PROJECT_ROOT / "data" / "raw" / "MORTGAGE30US.csv")
        else:
            self.mortgage_csv = str(_resolve_path(self.mortgage_csv))

        # Build permit_sources from either format
        if self.permit_sources:
            # Convert dicts to PermitSource objects
            self.permit_sources = [
                PermitSource(**s) if isinstance(s, dict) else s
                for s in self.permit_sources
            ]
        elif self.permits_csv:
            # Legacy single-source: wrap in a PermitSource
            self.permits_csv = str(_resolve_path(self.permits_csv))
            self.permit_sources = [PermitSource(
                csv=self.permits_csv,
                label="permits",
                strap_column=self.permit_strap_column,
                date_column=self.permit_date_column,
                category_column=self.permit_category_column,
                description_column=self.permit_description_column,
            )]

    # --- Derived directory paths ---

    @property
    def data_dir(self) -> Path:
        return PROJECT_ROOT / "data" / self.county_id

    @property
    def working_dir(self) -> Path:
        return self.data_dir / "working"

    @property
    def final_dir(self) -> Path:
        return self.data_dir / "final"

    @property
    def output_dir(self) -> Path:
        return PROJECT_ROOT / "data_science" / "output" / self.county_id / "walk_forward"

    def ensure_dirs(self):
        """Create all per-county directories if they don't exist."""
        for d in [self.working_dir, self.final_dir, self.output_dir]:
            d.mkdir(parents=True, exist_ok=True)

    # --- Standard intermediate file paths ---

    @property
    def regrid_filtered_path(self) -> Path:
        return self.final_dir / "regrid_filtered.csv"

    @property
    def sunroof_api_output_path(self) -> Path:
        return self.working_dir / "sunroof_api_output.csv"

    @property
    def filtered_api_output_path(self) -> Path:
        return self.working_dir / "filtered_api_output.csv"

    @property
    def regrid_joined_path(self) -> Path:
        return self.working_dir / "regrid_joined_with_api.csv"

    @property
    def final_data_path(self) -> Path:
        return self.final_dir / "final_data.csv"

    @property
    def parsed_permits_path(self) -> Path:
        return self.final_dir / "parsed_permits.csv"

    @property
    def parsed_permits_by_year_path(self) -> Path:
        return self.working_dir / "parsed_permits_by_year.csv"

    @property
    def roof_score_path(self) -> Path:
        return self.final_dir / "roof_score.csv"

    @property
    def avg_yearly_interest_path(self) -> Path:
        return self.final_dir / "avg_yearly_interest.csv"

    @property
    def strap_census_lookup_path(self) -> Path:
        return self.final_dir / "strap_census_lookup.csv"

    @property
    def acs_csv_path(self) -> Path:
        """ACS data cached per-state (shared across counties in same state)."""
        return PROJECT_ROOT / "data" / "raw" / f"acs_{self.state_fips}_block_group_data.csv"

    @property
    def block_group_geocoded_path(self) -> Path:
        return self.final_dir / "block_group_geocoded.csv"

    @property
    def strap_block_group_geocoded_path(self) -> Path:
        return self.final_dir / "strap_block_group_geocoded.csv"

    @property
    def regrid_model_rank_path(self) -> Path:
        return self.final_dir / "regrid_model_rank.csv"

    @property
    def regrid_model_rank_census_path(self) -> Path:
        return self.final_dir / "regrid_model_rank_census.csv"

    @property
    def straps_no_solar_path(self) -> Path:
        return self.output_dir / f"straps_no_solar_as_of_{self.year_max}.csv"


def load_config(name_or_path: str) -> CountyConfig:
    """Load a county config from configs/{name}.py or a full file path.

    The config file must define a dictionary called CONFIG.
    """
    path = Path(name_or_path)
    if not path.suffix:
        # Treat as a config name: look in configs/ directory
        path = PROJECT_ROOT / "configs" / f"{name_or_path}.py"

    if not path.is_absolute():
        path = PROJECT_ROOT / path

    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    # Load the Python file as a module
    spec = importlib.util.spec_from_file_location("county_config", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    if not hasattr(mod, "CONFIG"):
        raise ValueError(f"Config file {path} must define a CONFIG dictionary")

    return CountyConfig(**mod.CONFIG)


def validate_inputs(config: CountyConfig) -> list[str]:
    """Check that required input files exist and have expected columns.
    Returns list of error messages (empty = all good).
    """
    errors = []

    # Check shared files exist
    for label, path in [
        ("Regrid CSV", config.regrid_csv),
        ("Electricity CSV", config.electricity_csv),
        ("Mortgage CSV", config.mortgage_csv),
    ]:
        if not Path(path).exists():
            errors.append(f"{label} not found: {path}")

    # Check Regrid columns
    regrid_path = Path(config.regrid_csv)
    if regrid_path.exists():
        try:
            cols = set(pd.read_csv(regrid_path, nrows=0).columns)
            required = {config.lat_column, config.lon_column, config.strap_column}
            missing = required - cols
            if missing:
                errors.append(f"Regrid CSV missing columns: {missing}")
        except Exception as e:
            errors.append(f"Error reading Regrid CSV: {e}")

    # Check each permit source
    if not config.permit_sources:
        errors.append("No permit sources configured (set permit_sources or permits_csv)")

    for i, src in enumerate(config.permit_sources):
        src_label = src.label or f"source {i+1}"
        src_path = Path(src.csv)
        if not src_path.exists():
            errors.append(f"Permit source '{src_label}' not found: {src.csv}")
            continue

        try:
            cols = set(pd.read_csv(src_path, nrows=0).columns)
            required = {src.strap_column, src.date_column, src.description_column}
            missing = required - cols
            if missing:
                errors.append(f"Permit source '{src_label}' missing columns: {missing}")
        except Exception as e:
            errors.append(f"Error reading permit source '{src_label}': {e}")

    return errors
