"""
Step 4: Final filters, owner name parsing, and column selection for delivery dataset.
"""

import pandas as pd
import numpy as np
import re


# Expand as you see more patterns
LEGAL_ENTITY_PAT = re.compile(
    r"\b(LLC|L\.L\.C\.|INC|INC\.|CORP|CORPORATION|CO|CO\.|COMPANY|"
    r"TRUST|TR|REVOCABLE|IRREVOCABLE|LIVING|ESTATE|"
    r"LP|L\.P\.|LLP|L\.L\.P\.|PLLC|P\.L\.L\.C\.|"
    r"FOUNDATION|ASSOCIATION|PARTNERSHIP|HOLDINGS?|"
    r"ET\s+AL)\b",
    re.IGNORECASE
)

def is_legal_entity(s: str) -> bool:
    if pd.isna(s):
        return False
    return bool(LEGAL_ENTITY_PAT.search(str(s)))

def title_token(t: str) -> str:
    u = t.upper().strip(".")
    if u in {"LLC", "INC", "CORP", "TRUST", "LP", "LLP", "PLLC"}:
        return u
    return t.capitalize()

def format_owner1_person(s: str) -> str:
    if pd.isna(s) or str(s).strip() == "":
        return pd.NA
    parts = str(s).strip().split()
    parts = [title_token(p) for p in parts]
    if len(parts) >= 2:
        return f"{parts[0]}, {' '.join(parts[1:])}"
    return parts[0]

def owner2_has_last_name(owner2_raw: str) -> bool:
    if pd.isna(owner2_raw) or str(owner2_raw).strip() == "":
        return False
    toks = str(owner2_raw).strip().split()
    if len(toks) == 1:
        return False
    last = toks[-1].strip(".")
    if len(last) == 1:
        return False
    if len(toks) == 2:
        return len(toks[1].strip(".")) != 1
    return True

def format_owner2_person(owner2_raw: str, owner1_last: str) -> str:
    if pd.isna(owner2_raw) or str(owner2_raw).strip() == "":
        return pd.NA
    toks = str(owner2_raw).strip().split()
    if not owner2_has_last_name(owner2_raw):
        toks = toks + [owner1_last]
    last = title_token(toks[-1])
    first_middle = [title_token(t) for t in toks[:-1]]
    return f"{last}, {' '.join(first_middle)}" if first_middle else last

def parse_owner(owner_raw: str):
    if pd.isna(owner_raw) or str(owner_raw).strip() == "":
        return (pd.NA, pd.NA)
    s = str(owner_raw).strip()
    if is_legal_entity(s):
        return (s, pd.NA)
    if " & " in s:
        owner1_raw, owner2_raw = s.split(" & ", 1)
        owner1_raw = owner1_raw.strip()
        owner2_raw = owner2_raw.strip()
    else:
        owner1_raw, owner2_raw = s, None
    owner1_last = owner1_raw.split()[0] if owner1_raw else ""
    owner1_fmt = format_owner1_person(owner1_raw)
    owner2_fmt = (
        format_owner2_person(owner2_raw, owner1_last) if owner2_raw else pd.NA
    )
    return (owner1_fmt, owner2_fmt)


removeList = ['Parcel','Addition','Pud','Ot','&','LG','FLG','Filing','Phase','PATIO HOMES','Patio','PH','Sub','-','Rep','(replat)','replat','replat of','ii','iii','1st','2nd','3rd','4th','5th','6th','7th','8th','9th','10th','0','1','2','3','4','5','6','7','8','9','10','11','12','13','14','15','16','17','18','19','20','A','B','C','D','E','F','G','H','I','J','K']

def format_subdivision(name):
    if pd.isna(name):
        return name
    parts = name.strip().split()
    parts = parts[:3]
    parts = [
        p for p in parts
        if p.upper() not in {r.upper() for r in removeList}
    ]
    parts = [p.capitalize() for p in parts]
    if parts and parts[-1] == 'Of':
        parts.pop()
    return " ".join(parts)


def run(config=None):
    """Apply final filters, parse owners, select columns.

    Args:
        config: CountyConfig object. If None, uses legacy hardcoded paths.
    """
    if config:
        input_path = str(config.regrid_joined_path)
        output_path = str(config.final_data_path)
        config.ensure_dirs()
    else:
        location = "Boulder_CO"
        input_path = f"/Users/jeffs/Projects/SolarProject/data/working/{location}_Regrid_joined_with_API.csv"
        output_path = f"/Users/jeffs/Projects/SolarProject/data/final/{location}_Final_Data.csv"

    final = pd.read_csv(input_path)

    # Filter out rejected rows (if manual review was done)
    if 'result_manual_check' in final.columns:
        final = final[final['result_manual_check'] != 'Rejected']

    # Filter to non-solar homes (if solar_panels column exists from permits/classification)
    if 'solar_panels' in final.columns:
        final = final[final['solar_panels'] == 'No']

    cols_to_upper = ["city", "county"]
    for col in cols_to_upper:
        if col in final.columns:
            final[col] = final[col].astype(str).str.upper()

    if "county" in final.columns and "state2" in final.columns:
        final["index"] = final["county"].astype(str) + "_" + final["state2"].astype(str) + "_" + final["original_index"].astype(str)

    # Parse owner names
    if "owner" in final.columns:
        final[["owner_1", "owner_2"]] = final["owner"].apply(lambda x: pd.Series(parse_owner(x)))

    # Format subdivision
    if "subdivision" in final.columns:
        final["subdivision_formatted"] = final["subdivision"].apply(format_subdivision)

    # Select and rename columns (only include columns that exist)
    filtered_columns = [
        "original_index", "index", "roof_orientation", "saleprice", "saledate",
        "owner", "owner_1", "owner_2", "mailadd",
        "city", "county", "state2",
        "szip5", "subdivision_formatted", "area_building",
        "roof_coverdscr", "calculated_build_year",
        "latitude", "longitude",
        "numstories", "numrooms",
        "num_bath", "num_bath_partial", "num_bedrooms",
        "solar_panels", "solar_score"
    ]
    available_cols = [c for c in filtered_columns if c in final.columns]
    final = final[available_cols]

    if 'solar_score' in final.columns:
        score_max = final['solar_score'].max()
        if score_max > 0:
            final['solar_score'] = (final['solar_score'] / score_max) * 100

    rename_map = {
        "mailadd": "address",
        "state2": "state",
        "owner": "owner_unaltered",
        "roof_orientation": "qualified_orientations",
        "szip5": "zip_code",
        "area_building": "building_sqft",
        "numstories": "count_stories",
        "numrooms": "count_rooms",
        "num_bath": "count_bath",
        "num_bath_partial": "count_bath_partial",
        "num_bedrooms": "count_bedrooms",
        "roof_coverdscr": "roof_type",
    }
    rename_map = {k: v for k, v in rename_map.items() if k in final.columns}
    final = final.rename(columns=rename_map)

    print(f"Final dataset: {len(final)} rows")
    final.to_csv(output_path, index=False)
    print(f"Saved to {output_path}")
    return final


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", help="County config name or path")
    args = parser.parse_args()

    if args.config:
        from pipeline_config import load_config
        run(load_config(args.config))
    else:
        run()
