"""
Pipeline configuration for San Diego (City), California.

Data sources:
- Regrid: Full county export, pre-filtered to City of San Diego SFR owner-occupied
- Permits: City of San Diego open data (active + closed)

Run:  python run_pipeline.py san_diego_ca
"""

CONFIG = {
    "county_id": "SanDiego_CA",
    "state_fips": "06",
    "state_abbrev": "CA",

    # Input data paths (relative to project root)
    # This is the pre-filtered file (SFR, owner-occupied, City of San Diego)
    "regrid_csv": "data/raw/SanDiegoCA/Regrid_SanDiego_SFR_Filtered.csv",

    # Permit sources - City of San Diego open data
    "permit_sources": [
        {
            "csv": "data/raw/SanDiegoCA/permits_set2_closed_datasd.csv",
            "label": "SD City Closed Permits",
            "strap_column": "JOB_APN",
            "date_column": "DATE_APPROVAL_ISSUE",
            "category_column": "APPROVAL_TYPE",
            "description_column": "PROJECT_SCOPE",
        },
        {
            "csv": "data/raw/SanDiegoCA/permits_set2_active_datasd.csv",
            "label": "SD City Active Permits",
            "strap_column": "JOB_APN",
            "date_column": "DATE_APPROVAL_ISSUE",
            "category_column": "APPROVAL_TYPE",
            "description_column": "PROJECT_SCOPE",
        },
    ],

    # Shared data (uses defaults if empty)
    "electricity_csv": "",
    "mortgage_csv": "",

    # Year range for permit panel data
    "year_min": 2012,
    "year_max": 2026,

    # Regrid column mappings
    # San Diego Regrid uses parcelnumb (10-digit APN) as the parcel ID
    "strap_column": "parcelnumb",
    "lat_column": "lat",
    "lon_column": "lon",

    # Regrid filters - already applied in the pre-filtered file
    "regrid_filters": {},
}
