#Step 4

import pandas as pd
import numpy as np
import re

#Filter columns to have a usable dataset
location = "Boulder_CO"

all_columns = [
    "original_index", "geoid", "parcelnumb", "parcelnumb_no_formatting", "state_parcelnumb",
    "account_number", "tax_id", "alt_parcelnumb1", "alt_parcelnumb2", "alt_parcelnumb3",
    "usecode", "usedesc", "zoning", "zoning_description", "struct", "structno",
    "yearbuilt", "year_built_effective_date", "numstories", "numunits", "numrooms",
    "num_bath", "num_bath_partial", "num_bedrooms", "structstyle", "parvaltype",
    "improvval", "landval", "parval", "agval", "saleprice", "saledate", "taxamt",
    "taxyear", "last_ownership_transfer_date", "owntype", "owner", "unmodified_owner",
    "ownfrst", "ownlast", "owner2", "owner3", "owner4", "previous_owner", "mailadd",
    "mail_address2", "careof", "mail_addno", "mail_addpref", "mail_addstr",
    "mail_addsttyp", "mail_addstsuf", "mail_unit", "mail_city", "mail_state2",
    "mail_zip", "mail_country", "mail_urbanization", "original_mailing_address",
    "address", "address2", "saddno", "saddpref", "saddstr", "saddsttyp", "saddstsuf",
    "sunit", "scity", "original_address", "city", "county", "state2", "szip",
    "szip5", "urbanization", "location_name", "address_source", "legaldesc", "plat",
    "book", "page", "block", "lot", "neighborhood", "neighborhood_code",
    "subdivision", "lat_x", "lon_x", "qoz", "qoz_tract", "census_tract",
    "census_block", "census_blockgroup", "census_zcta", "ll_last_refresh",
    "sourceurl", "recrdareatx", "recrdareano", "area_building",
    "area_building_definition", "deeded_acres", "gisacre", "sqft", "ll_gisacre",
    "ll_gissqft", "plss_township", "plss_section", "plss_range", "reviseddate",
    "path", "ll_stable_id", "ll_uuid", "ll_stack_uuid", "ll_updated_at",
    "parcel_no", "parcels_address", "lot_number", "parcels_block", "subcode",
    "condo_unit", "gis_sqft", "shapestare", "shapestlen", "strap", "statuscd",
    "designcode", "designcodedscr", "qualitycode", "qualitycodedscr", "bldgclass",
    "bldgclassdscr", "constcode", "constcodedscr", "compcode", "effectiveyear",
    "bsmtsf", "bsmttype", "bsmttypedscr", "carstoragesf", "carstoragetype",
    "carstoragetypedscr", "ac", "acdscr", "heating", "heatingdscr", "extwallprim",
    "extwalldscrprim", "extwallsec", "extwalldscrsec", "intwall", "intwalldscr",
    "roof_cover", "roof_coverdscr", "mainfloorsf", "nbrbedroom", "nbrroomsnobath",
    "nbrthreeqtrbaths", "nbrfullbaths", "nbrhalfbaths", "landunitvalue",
    "landunittype", "status_cd", "sub_code", "building_num", "role_cd", "pct_own",
    "taxarea", "mill_levy", "waterfee", "bldacutalval", "landacutalval",
    "xfactualval", "totalactualval", "xfassessedval", "deednum", "deed_type",
    "sales_cd", "OwnerOccupied", "calculated_build_year",
    "calculated_roof_age", "input_lat", "input_lon", "ok",
    "error", "latitude", "longitude", "year", "month", "day", "sunshine",
    "segment_count", "azimuth1", "areaSqMeters1", "azimuth2", "areaSqMeters2",
    "azimuth3", "areaSqMeters3", "azimuth4", "areaSqMeters4", "azimuth5",
    "areaSqMeters5", "azimuth6", "areaSqMeters6", "azimuth7", "areaSqMeters7",
    "azimuth8", "areaSqMeters8", "azimuth9", "areaSqMeters9", "azimuth10",
    "areaSqMeters10", "azimuth11", "areaSqMeters11", "azimuth12", "areaSqMeters12",
    "azimuth13", "areaSqMeters13", "azimuth14", "areaSqMeters14", "azimuth15",
    "areaSqMeters15", "azimuth16", "areaSqMeters16", "azimuth17", "areaSqMeters17",
    "azimuth18", "areaSqMeters18", "azimuth19", "areaSqMeters19", "azimuth20",
    "areaSqMeters20", "azimuth21", "areaSqMeters21", "azimuth22", "areaSqMeters22",
    "azimuth23", "areaSqMeters23", "azimuth24", "areaSqMeters24", "azimuth25",
    "areaSqMeters25", "lat_y", "lon_y", "solar_panels"
]

# sunshine	segment_count

filtered_columns = [
    "original_index", "index","roof_orientation", "saleprice", "saledate",
    "owner","owner_1","owner_2", "mailadd",
    "city", "county", "state2",
    "szip5", "subdivision_formatted", "area_building",
    "roof_coverdscr", "calculated_build_year",
    "latitude", "longitude",
    "numstories", "numrooms",
    "num_bath", "num_bath_partial", "num_bedrooms",
    "solar_panels", "solar_score"
]


final = pd.read_csv("/Users/jeffs/Projects/SolarProject/data/working/"+location+"_Regrid_joined_with_API.csv")

final = final[final['result_manual_check'] != 'Rejected']
final = final[final['solar_panels'] == 'No']


# final = final[final['sunshine'] >= 1600]

cols_to_upper = ["city", "county"]

final[cols_to_upper] = final[cols_to_upper].apply(
    lambda col: col.astype(str).str.upper()
)

final["index"] = final["county"].astype(str) + "_" + final["state2"].astype(str) + "_" + final["original_index"].astype(str)



#Naming formatting

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
    # keep common suffixes / org tokens as uppercase if you want
    if u in {"LLC", "INC", "CORP", "TRUST", "LP", "LLP", "PLLC"}:
        return u
    return t.capitalize()

def format_owner1_person(s: str) -> str:
    """
    Owner 1 assumed: LAST FIRST MIDDLE...
    -> 'Last, First Middle...'
    """
    if pd.isna(s) or str(s).strip() == "":
        return pd.NA
    parts = str(s).strip().split()
    parts = [title_token(p) for p in parts]
    if len(parts) >= 2:
        return f"{parts[0]}, {' '.join(parts[1:])}"
    return parts[0]

def owner2_has_last_name(owner2_raw: str) -> bool:
    """
    Owner 2 assumed: FIRST [MIDDLE...] [LAST?]
    Heuristic:
      - 1 token => no last
      - 2 tokens => last name present unless 2nd token is an initial
      - 3+ tokens => last name present unless last token is an initial
    """
    if pd.isna(owner2_raw) or str(owner2_raw).strip() == "":
        return False
    toks = str(owner2_raw).strip().split()
    if len(toks) == 1:
        return False
    last = toks[-1].strip(".")
    if len(last) == 1:  # trailing initial
        return False
    if len(toks) == 2:
        # e.g. "ANNA S" -> no last
        return len(toks[1].strip(".")) != 1
    return True

def format_owner2_person(owner2_raw: str, owner1_last: str) -> str:
    """
    Owner 2 assumed: FIRST [MIDDLE...] [LAST?]
    If no last, inherit owner1_last.
    Output: 'Last, First Middle...'
    """
    if pd.isna(owner2_raw) or str(owner2_raw).strip() == "":
        return pd.NA

    toks = str(owner2_raw).strip().split()

    if not owner2_has_last_name(owner2_raw):
        # append inherited last name
        toks = toks + [owner1_last]

    # Now treat last token as last name, rest as first/middle
    last = title_token(toks[-1])
    first_middle = [title_token(t) for t in toks[:-1]]
    return f"{last}, {' '.join(first_middle)}" if first_middle else last

def parse_owner(owner_raw: str):
    """
    Returns (owner_1, owner_2) formatted per the rules.
    """
    if pd.isna(owner_raw) or str(owner_raw).strip() == "":
        return (pd.NA, pd.NA)

    s = str(owner_raw).strip()

    # Rule 1: legal entities bypass parsing
    if is_legal_entity(s):
        return (s, pd.NA)

    # Split only on " & " (with spaces)
    if " & " in s:
        owner1_raw, owner2_raw = s.split(" & ", 1)
        owner1_raw = owner1_raw.strip()
        owner2_raw = owner2_raw.strip()
    else:
        owner1_raw, owner2_raw = s, None

    # Owner 1
    owner1_last = owner1_raw.split()[0] if owner1_raw else ""
    owner1_fmt = format_owner1_person(owner1_raw)

    # Owner 2
    owner2_fmt = (
        format_owner2_person(owner2_raw, owner1_last) if owner2_raw else pd.NA
    )

    return (owner1_fmt, owner2_fmt)

# Apply to dataframe
final[["owner_1", "owner_2"]] = final["owner"].apply(lambda x: pd.Series(parse_owner(x)))



#Subdivision formatting

removeList = ['Parcel','Addition','Pud','Ot','&','LG','FLG','Filing','Phase','PATIO HOMES','Patio','PH','Sub','-','Rep','(replat)','replat','replat of','ii','iii','1st','2nd','3rd','4th','5th','6th','7th','8th','9th','10th','0','1','2','3','4','5','6','7','8','9','10','11','12','13','14','15','16','17','18','19','20','A','B','C','D','E','F','G','H','I','J','K']

def format_subdivision(name):
    if pd.isna(name):
        return name
    
    parts = name.strip().split()

    # limit length
    parts = parts[:3]

    # remove unwanted tokens
    parts = [
        p for p in parts
        if p.upper() not in {r.upper() for r in removeList}
    ]

    # normalize casing
    parts = [p.capitalize() for p in parts]

    # remove trailing "Of"
    if parts and parts[-1] == 'Of':
        parts.pop()

    return " ".join(parts)

final["subdivision_formatted"] = final["subdivision"].apply(format_subdivision)


final = final[filtered_columns]

final['solar_score'] = (final['solar_score']/final['solar_score'].max()) * 100

final = final.rename(
    columns={
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
)


print(len(final))

final.to_csv("/Users/jeffs/Projects/SolarProject/data/final/"+location+"_Final_Data.csv", index=False)