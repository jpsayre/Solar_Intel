# Solar Lead Generation Pipeline

Predicts which homeowners are most likely to install solar panels, using property records, permit history, roof analysis, census demographics, and machine learning.

## Quick Start

```bash
# Install dependencies
pip install -r scripts/requirements.txt

# Run the full pipeline for a county
python run_pipeline.py boulder_co

# Test with a small batch (10 homes, no API calls)
python run_pipeline.py boulder_co --limit 10 --skip-api
```

## Pipeline Stages

| # | Stage | Script | Description |
|---|-------|--------|-------------|
| 1 | validate | `run_pipeline.py` | Check input files exist, create output directories |
| 2 | interest_rates | `src/interest_rates.py` | Compute average yearly mortgage interest rates |
| 3 | filter_regrid_api | `src/InitialScript.py` | Filter Regrid parcel data, call Google Sunroof API |
| 4 | filter_solar | `src/Analyze_ProjectSunroof_Data.py` | Filter API output by solar potential and roof orientation |
| 5 | merge_regrid_api | `src/Combine_Regrid_ProjectSunroof_Data.py` | Merge Regrid property data with Sunroof API output |
| 6 | roof_score | `src/roof_score.py` | Compute roof quality scores from Sunroof segment data |
| 7 | parse_permits | `src/parse_permits.py` | Parse permit records into 19 binary feature columns |
| 8 | census_enrichment | `src/enrich_census.py` | Geocode parcels, pull Census ACS demographics |
| 9 | permits_by_year | `src/create_parsed_permits_by_year.py` | Build strap-year panel with all features and derived columns |
| 10 | walk_forward_model | `data_science/walk_forward_modeling.py` | Walk-forward ML modeling (expanding window, multiple models) |
| 11 | combine_ranks | `data_science/combine_regrid_model_rank.py` | Combine model scores with property data for final ranked output |

## Pipeline Runner Options

```bash
python run_pipeline.py <config_name> [options]

Options:
  --limit N        Process only N homes (limits API calls)
  --skip-api       Skip Sunroof API calls (use existing data)
  --start-from N   Resume from stage N
  --step N         Run only stage N
  --dry-run        Print stages without executing
```

## Adding a New County

See [docs/new_county_setup.md](docs/new_county_setup.md) for the full guide.

1. Get Regrid parcel export and permit records for your county
2. Create a config file in `configs/` (use `configs/boulder_co.py` as template)
3. Run `python run_pipeline.py your_county --dry-run` to validate
4. Test with `--limit 10 --skip-api` before running the full pipeline

### Config File Structure

Each county has a Python config file in `configs/` defining a `CONFIG` dict:

```python
CONFIG = {
    "county_id": "Boulder_CO",
    "state_fips": "08",
    "state_abbrev": "CO",
    "regrid_csv": "data/raw/regrid_export.csv",
    "permit_sources": [
        {
            "csv": "data/raw/permits.csv",
            "label": "Boulder County",
            "strap_column": "strap",
            "date_column": "issue_dt",
            "category_column": "permit_category",
            "description_column": "description",
        },
    ],
    "regrid_filters": { ... },
}
```

Multiple permit sources are supported (one per city/data source), each with its own column mappings.

## Project Structure

```
configs/                  County config files
src/                      Pipeline stage scripts
  pipeline_config.py      CountyConfig dataclass and loader
  InitialScript.py        Regrid filter + Sunroof API
  Analyze_ProjectSunroof_Data.py  Solar potential filter
  Combine_Regrid_ProjectSunroof_Data.py  Merge Regrid + API
  roof_score.py           Roof quality scoring
  parse_permits.py        Permit feature extraction
  parse_permits_features.py  Keyword matching rules (19 features)
  enrich_census.py        Census ACS demographic enrichment
  create_parsed_permits_by_year.py  Strap-year panel builder
  FinalFilters.py         Column selection and name formatting
  Add_Derived_Columns.py  Haversine distances, derived features
data_science/             ML modeling
  walk_forward_modeling.py  Walk-forward temporal validation
  combine_regrid_model_rank.py  Final output assembly
tests/                    Pytest test suite
  conftest.py             Shared fixtures
  test_config.py          Config system tests
  test_transforms.py      Pure function tests
  test_pipeline_contracts.py  Stage output schema tests
docs/                     Documentation
  new_county_setup.md     Step-by-step new county guide
data/                     Data directory (per-county subdirs)
  raw/                    Input data files
  {county_id}/working/    Intermediate pipeline files
  {county_id}/final/      Final output files
```

## Output Files

Each county run produces files in two directories under `data/{county_id}/`:

### Final (`data/{county_id}/final/`)

| File | Stage | Description |
|------|-------|-------------|
| `regrid_filtered.csv` | 3 | Regrid parcel data after property filters (SFR, owner-occupied, etc.). One row per home. |
| `avg_yearly_interest.csv` | 2 | Average 30-year mortgage rate per year (2012-2026). |
| `parsed_permits.csv` | 7 | Per-permit-row binary features (19 columns like `solar_pv`, `battery`, `ev_charger`, `roof_new_or_replace`) with `issue_dt` preserved for year aggregation. |
| `roof_score.csv` | 6 | Roof quality score per home based on Sunroof segment data (orientation, area, sunshine). |
| `strap_block_group_geocoded.csv` | 8 | Parcel-to-Census block group mapping via FCC geocoder. |
| `strap_census_lookup.csv` | 8 | Census ACS demographics per parcel (income, home value, education, housing age, etc.). |
| `regrid_model_rank.csv` | 11 | **Final output.** Every home with ML-predicted solar adoption probability and rank. |
| `regrid_model_rank_census.csv` | 11 | Final output enriched with census demographics. |

### Working (`data/{county_id}/working/`)

| File | Stage | Description |
|------|-------|-------------|
| `sunroof_api_output.csv` | 3 | Raw Google Sunroof API responses (roof segments, azimuth, area, sunshine quantiles). |
| `filtered_api_output.csv` | 4 | Sunroof data filtered to homes with qualifying south/east/west-facing roof segments. |
| `regrid_joined_with_api.csv` | 5 | Regrid property data merged with filtered Sunroof output on `original_index`. |
| `parsed_permits_by_year.csv` | 9 | **Main ML input.** Strap-year panel (one row per home per year) with 180+ features: permit flags with persistence, neighbor solar counts at multiple radii, roof age, electricity proxy, mortgage rates, census data, and derived columns. |

### ML Output (`data_science/output/{county_id}/walk_forward/`)

| File | Stage | Description |
|------|-------|-------------|
| `walk_forward_results.csv` | 10 | Per-model, per-year predictions and metrics from walk-forward validation. |
| `straps_no_solar_as_of_{year}.csv` | 10 | Homes that haven't installed solar yet -- the prediction target list. |

## Data Flow

```
Regrid CSV ──> Filter ──> Sunroof API ──> Solar Filter ──> Merge ──> Roof Score ─┐
                                                                                  │
Permit CSVs ──> Parse Features ──────────────────────────────────────────────────>│
                                                                                  │
Census API ──> Geocode + ACS Pull ──────────────────────────────────────────────>│
                                                                                  │
Mortgage + Electricity Data ────────────────────────────────────────────────────>│
                                                                                  ▼
                                                                   Strap-Year Panel
                                                                          │
                                                                   Walk-Forward ML
                                                                          │
                                                                   Ranked Output
```

## Environment Variables

- `GOOGLE_SUNROOF_API_KEY` - Google Solar API key (stage 3)
- `CENSUS_API_KEY` - Census Bureau API key (stage 8, optional but recommended)
- `DATABASE_SOLAR_INTEL_URL` - PostgreSQL connection string (optional, for roof score storage)

## Tests

```bash
python -m pytest tests/ -v
```

69 tests covering config validation, pure transforms, and stage output contracts.

## Current Counties

- **Boulder, CO** (`configs/boulder_co.py`) - production
- **San Diego, CA** (`configs/san_diego_ca.py`) - in progress
