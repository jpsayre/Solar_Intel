# Setting Up a New County

Step-by-step guide to running the solar pipeline for a new county.

## 1. Get Your Data

You need two types of input data:

**Regrid parcel export** (required)
- Purchase a Regrid data export for your target county
- Save it to `data/raw/` (e.g. `data/raw/MaricopaAZ_Regrid.csv`)
- Must contain columns: `alt_parcelnumb1` (parcel ID), `lat`, `lon`, plus property attributes

**Permit records** (required, one or more sources)
- Download permit data from each city/county in your target area
- Each source can have different column names -- you'll map them in the config
- At minimum each source needs: a parcel ID column, a date column, and a description column

**Shared data** (included in repo)
- `data/raw/Average_retail_price_of_electricity.csv` -- EIA electricity prices
- `data/raw/MORTGAGE30US.csv` -- 30-year mortgage rates
- These are national data and work for any county

## 2. Create a Config File

Create `configs/{county_id}.py` (lowercase, underscored). Use `configs/boulder_co.py` as a template.

```python
CONFIG = {
    "county_id": "Maricopa_AZ",      # Used for folder names
    "state_fips": "04",               # FIPS code (needed for Census API)
    "state_abbrev": "AZ",

    "regrid_csv": "data/raw/MaricopaAZ_Regrid.csv",

    # One entry per permit data source
    "permit_sources": [
        {
            "csv": "data/raw/phoenix_permits.csv",
            "label": "City of Phoenix",
            "strap_column": "parcel_number",     # column matching Regrid's alt_parcelnumb1
            "date_column": "issue_date",
            "category_column": "permit_type",
            "description_column": "work_description",
        },
        {
            "csv": "data/raw/scottsdale_permits.csv",
            "label": "City of Scottsdale",
            "strap_column": "apn",
            "date_column": "issued",
            "category_column": "category",
            "description_column": "description",
        },
    ],

    # Year range for the permit panel
    "year_min": 2012,
    "year_max": 2026,

    # Regrid column mappings (usually these defaults work)
    "strap_column": "alt_parcelnumb1",
    "lat_column": "lat",
    "lon_column": "lon",

    # Regrid filters -- customize for your county's property types
    "regrid_filters": {
        "usedesc": ["SINGLE FAM.RES.-LAND"],       # property use descriptions to include
        "mainfloorsf_min": 800,                     # minimum square footage
        "saleprice_min": 200000,                     # minimum sale price
        # Add more filters as needed -- see InitialScript.apply_regrid_filters()
    },
}
```

### Finding Your State FIPS Code

Common codes: CO=08, AZ=04, CA=06, TX=48, FL=12, NY=36, WA=53.
Full list: https://www.census.gov/library/reference/code-lists/ansi.html

### Matching Permit Parcel IDs to Regrid

The `strap_column` in each permit source must contain values that match Regrid's `alt_parcelnumb1`. Investigate your permit data to find the right column. Common names: `parcel_number`, `apn`, `pin`, `parcel_id`, `tax_id`.

If formats differ (e.g. permits use dashes, Regrid doesn't), you'll need to normalize them. This is the most common integration challenge.

## 3. Validate Your Setup

```bash
# Dry run -- shows what stages would execute, checks files exist
python run_pipeline.py maricopa_az --dry-run

# Run just validation (stage 1)
python run_pipeline.py maricopa_az --step 1
```

## 4. Test With a Small Batch

Before burning API credits on the full dataset, test with a few homes:

```bash
# Process only 50 homes (limits Sunroof API calls)
python run_pipeline.py maricopa_az --limit 50

# Or skip the API entirely if you already have Sunroof data
python run_pipeline.py maricopa_az --skip-api
```

## 5. Run the Full Pipeline

```bash
python run_pipeline.py maricopa_az
```

### Pipeline Stages

| # | Stage | What it does |
|---|-------|-------------|
| 1 | validate | Checks input files exist with expected columns |
| 2 | interest_rates | Computes average yearly mortgage rates |
| 3 | filter_regrid_api | Filters Regrid data + calls Google Sunroof API |
| 4 | filter_solar | Filters API output by solar potential |
| 5 | merge_regrid_api | Merges Regrid with Sunroof API output |
| 6 | roof_score | Computes roof scores from Sunroof data |
| 7 | parse_permits | Parses all permit sources into binary features |
| 8 | census_enrichment | Adds Census ACS demographic data |
| 9 | permits_by_year | Aggregates permits by strap-year with derived features |
| 10 | walk_forward_model | Walk-forward ML modeling |
| 11 | combine_ranks | Produces final ranked output |

### Resuming After a Failure

If a stage fails, fix the issue and resume:

```bash
# Resume from stage 7
python run_pipeline.py maricopa_az --start-from 7

# Run just one stage
python run_pipeline.py maricopa_az --step 8
```

## 6. Output

Results are saved to:
- `data/{county_id}/final/` -- intermediate outputs (filtered regrid, parsed permits, etc.)
- `data/{county_id}/working/` -- working files (API output, permit aggregation)
- `data_science/output/{county_id}/walk_forward/` -- ML model output
- `data/{county_id}/final/regrid_model_rank.csv` -- final ranked homes

## Environment Variables

- `GOOGLE_SUNROOF_API_KEY` -- required for stage 3 (Sunroof API calls)
- `CENSUS_API_KEY` -- required for stage 8 (Census ACS data)
- `DATABASE_SOLAR_INTEL_URL` -- optional Postgres connection for roof score storage

## Troubleshooting

**"No permit sources configured"**
Your config needs either `permit_sources` (list of dicts) or `permits_csv` (single path).

**Permit parcel IDs don't match Regrid**
Check the format of parcel IDs in both datasets. They need to match exactly. You may need to strip leading zeros, remove dashes, etc.

**Census API rate limited**
Stage 8 fetches ACS data per block group. The data is cached at `data/raw/acs_{state_fips}_block_group_data.csv` so subsequent runs skip the API.

**"Regrid CSV missing columns"**
Your Regrid export may use different column names. Check the CSV headers and update `strap_column`, `lat_column`, `lon_column` in your config.
