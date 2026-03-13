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
| 7 | parse_permits | `src/parse_permits.py` | Parse and classify permits into 19 binary features + permit_type |
| 8 | census_enrichment | `src/enrich_census.py` | Geocode parcels, pull Census ACS demographics |
| 9 | data_science_input | `src/create_data_science_input.py` | Build strap-year panel with all features and derived columns |
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
            "permit_num_column": "permit_num",
            "valuation_column": "estimated_value",
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
  parse_permits.py        Permit parsing, normalization, and classification
  parse_permits_features.py  Classification logic: category matching, description regex, valuation checks
  enrich_census.py        Census ACS demographic enrichment
  create_data_science_input.py  Strap-year panel builder for ML
  FinalFilters.py         Column selection and name formatting
  Add_Derived_Columns.py  Haversine distances, derived features
data_science/             ML modeling
  walk_forward_modeling.py  Walk-forward temporal validation
  combine_regrid_model_rank.py  Final output assembly
scripts/                  Standalone scripts (not pipeline stages)
  upload_permits_to_supabase.py  Upload permits to Supabase
  validate_permits.py     Statistical validation report
  validate_permits_ai.py  AI cross-check for classification
tests/                    Pytest test suite
  conftest.py             Shared fixtures
  test_config.py          Config system tests
  test_transforms.py      Pure function tests
  test_golden_permits.py  Golden test set for permit classification
  test_pipeline_contracts.py  Stage output schema tests
  fixtures/golden_permits.csv  Manually verified permit test cases
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
| `parsed_permits.csv` | 7 | One row per permit with normalized columns (`strap`, `permit_num`, `issue_dt`, `permit_category`, `description`, `estimated_value`), 19 binary feature flags, and a `permit_type` label. Used by both data science (stage 9) and Supabase upload. |
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
| `data_science_input.csv` | 9 | **Main ML input.** Strap-year panel (one row per home per year) with 180+ features: permit flags with persistence, neighbor solar counts at multiple radii, roof age, electricity proxy, mortgage rates, census data, and derived columns. |

### ML Output (`data_science/output/{county_id}/walk_forward/`)

| File | Stage | Description |
|------|-------|-------------|
| `walk_forward_results.csv` | 10 | Per-model, per-year predictions and metrics from walk-forward validation. |
| `straps_no_solar_as_of_{year}.csv` | 10 | Homes that haven't installed solar yet -- the prediction target list. |

## Permit Classification

All permit classification logic lives in `src/parse_permits_features.py` — single source of truth used by both the ML pipeline and Supabase upload.

**Classification pipeline:**
```
raw permit → compute_features() → 19 binary flags → classify_permit_type() → permit_type string
```

**Three layers of classification:**
1. **Category matching** — permit_category keywords (e.g. "ENERGY EFFICIENT SYSTEM" → solar candidate)
2. **Description regex** — regex on combined category+description text for each of 19 features
3. **Valuation sanity checks** — solar permits < $3k without strong keywords ("solar", "photovoltaic", "pv system") are excluded

**Cross-feature independence:** `solar_pv`, `battery`, and `ev_charger` are independent — a single permit can have multiple features (e.g. a combined solar PV + battery storage install). Solar thermal exclusion prevents double-counting with solar_pv; heat pump water heaters excluded from HVAC heat pump.

**Multi-type classification:** `classify_permit_type()` returns all matching types as a comma-separated string (e.g. `"solar,battery"`). A permit with both solar PV and battery features becomes two rows in Supabase (one per type), and feeds both binary flags into the ML pipeline.

**19 binary features:** `solar_pv`, `battery`, `ev_charger`, `roof_new_or_replace`, `electrical_service_upgrade`, `heat_pump`, `ac`, `furnace`, `water_heater`, `water_heater_electric`, `water_heater_gas`, `water_heater_solar_thermal`, `windows_doors`, `insulation_airseal`, `generator`, `addition_new_build`, `kitchen_bath_remodel`, `pool_hot_tub`, `evaporative_cooler`

**permit_type values:** `solar`, `battery`, `ev_charger`, `heat_pump`, `generator`, `roof`, `hvac`, `electrical`, `water_heater`, `construction`, `remodel`, `envelope`, `pool`, `other`

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

## Permit Validation

Two scripts validate classification quality, especially when onboarding new counties with different permit formats.

### Statistical Report (`scripts/validate_permits.py`)

```bash
python scripts/validate_permits.py --config boulder_co
```

Reads `parsed_permits.csv` and `regrid_filtered.csv`, filters to matched homes only, and reports:
1. **Category coverage** — which `permit_category` values trigger `CATEGORY_MATCHES`, and which don't (candidates for new rules)
2. **permit_type distribution** — counts per type with baseline drift detection; flags if "other" > 50% or solar rate is abnormal
3. **"Other" analysis** — top category+description pairs for permits that fell through all patterns
4. **Cross-strap duplicates** — descriptions appearing on >2 straps (parsing bug indicator)
5. **Valuation stats** — per-type median/mean/min/max; flags solar permits with suspiciously low valuation

Saves `data/{county_id}/validation/baseline_distribution.json` for future drift comparison.

### AI Cross-Check (`scripts/validate_permits_ai.py`)

```bash
python scripts/validate_permits_ai.py --config boulder_co
python scripts/validate_permits_ai.py --config boulder_co --sample-size 50
python scripts/validate_permits_ai.py --config boulder_co --other-only
```

Uses GPT-4o-mini to independently classify a stratified sample of permits from raw text, then compares against the rule-based system. Flags disagreements by type, confidence level, and pattern (e.g. "rule=other, AI=solar" reveals missed solar permits). Requires `OPEN_AI_API_KEY`.

Results saved to `data/{county_id}/validation/ai_review.csv`.

### Golden Test Set

`tests/fixtures/golden_permits.csv` contains 26+ manually verified permit rows covering all 14 types plus edge cases (multi-type permits, low-valuation solar, solar thermal vs solar PV, etc.). `tests/test_golden_permits.py` runs `compute_features()` and `classify_permit_type()` on each row and asserts correct output. Add new rows as edge cases are discovered from AI cross-check disagreements.

```bash
python -m pytest tests/test_golden_permits.py -v
```

## Supabase Upload

Upload classified permits to Supabase (separate from the ML pipeline):

```bash
# Dry run — show stats without uploading
python scripts/upload_permits_to_supabase.py --config boulder_co --dry-run

# Upload permits from 2024 onward
python scripts/upload_permits_to_supabase.py --config boulder_co --since 2024

# List available configs
python scripts/upload_permits_to_supabase.py --help
```

Reads `parsed_permits.csv` (output of stage 7), maps straps to Supabase `homes` table, and upserts to `permits` table. Requires `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY`.

## Environment Variables

- `GOOGLE_SUNROOF_API_KEY` - Google Solar API key (stage 3)
- `CENSUS_API_KEY` - Census Bureau API key (stage 8, optional but recommended)
- `SUPABASE_URL` - Supabase project URL (permit upload)
- `SUPABASE_SERVICE_ROLE_KEY` - Supabase service role key (permit upload)
- `OPEN_AI_API_KEY` - OpenAI API key (AI permit validation cross-check)
- `DATABASE_SOLAR_INTEL_URL` - PostgreSQL connection string (optional, for roof score storage)

## Tests

```bash
python -m pytest tests/ -v
```

69 tests covering config validation, pure transforms, and stage output contracts.

## Current Counties

- **Boulder, CO** (`configs/boulder_co.py`) - production
- **San Diego, CA** (`configs/san_diego_ca.py`) - in progress
