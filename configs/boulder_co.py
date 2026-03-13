"""
Pipeline configuration for Boulder County, Colorado.

Data sources:
- Regrid: Full county export (paid), pre-filtered to SFR owner-occupied
- Permits: Boulder County Assessor public data download
  https://bouldercounty.gov/property-and-land/assessor/data-download/
  Direct CSV: https://assessor.boco.solutions/ASR_PublicDataFiles/Permits.csv

Drop your Regrid export and permits CSV into data/Boulder_CO/raw/
then run:  python run_pipeline.py boulder_co
"""

CONFIG = {
    "county_id": "Boulder_CO",
    "state_fips": "08",
    "state_abbrev": "CO",

    # Input data paths (relative to project root)
    "regrid_csv": "data/raw/BoulderColorado_Full_Paid_WorkingCopy.csv",

    # Permit sources (one entry per city/source)
    "permit_sources": [
        {
            "csv": "data/raw/Boulder_CO_Permits_3_11_26.csv",
            "label": "Boulder County",
            "strap_column": "strap",
            "date_column": "issue_dt",
            "category_column": "permit_category",
            "description_column": "description",
        },
        # To add another city's permits, append another dict:
        # {
        #     "csv": "data/raw/Louisville_Permits.csv",
        #     "label": "City of Louisville",
        #     "strap_column": "parcel_id",
        #     "date_column": "permit_date",
        #     "category_column": "type",
        #     "description_column": "work_description",
        # },
    ],

    # Shared data (uses defaults if empty)
    "electricity_csv": "",
    "mortgage_csv": "",

    # Year range for permit panel data
    "year_min": 2012,
    "year_max": 2026,

    # Regrid column mappings
    "strap_column": "alt_parcelnumb1",
    "lat_column": "lat",
    "lon_column": "lon",

    # Regrid filters applied before calling Sunroof API
    "regrid_filters": {
        "usedesc": ["SINGLE FAM.RES.-LAND"],
        "zoning_description_contains": "residential",
        "designcodedscr": [
            "1 Story - Ranch",
            "2-3 Story",
            "Split-level",
            "Bi-level",
            "PATIO HOMES",
            "MODULAR",
            "A-Frame",
        ],
        # "sales_cd": ["Q"],
        "mainfloorsf_min": 800,
        "saleprice_min": 100000,
        "owner_occupied": True,
        # "calculated_build_year_min": 1960,
    },
}
