#Step 4
import pandas as pd

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
    "calculated_roof_age", "PotentialRoofAge", "input_lat", "input_lon", "ok",
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


filtered_columns = [
    "index", "original_index", "zoning_description", "numstories", "numrooms",
    "num_bath", "num_bath_partial", "num_bedrooms", "saleprice", "saledate",
    "owner", "owner_formatted", "mailadd",
    "city", "county", "state2",
    "szip5", "subdivision_formatted", "area_building", "effectiveyear",
    "roof_coverdscr", "calculated_build_year",
    "latitude", "longitude"
]


final = pd.read_csv("/Users/jeffs/Projects/SolarProject/data/working/"+location+"_Semi_Final_Data_w_Solar_Classifier.csv")

final["index"] = final["county"].astype(str) + "_" + final["state2"].astype(str) + "_" + final["original_index"].astype(str)


def format_owner(name):
    if pd.isna(name):
        return name

    parts = name.strip().split()
    parts = [p.capitalize() for p in parts]

    if len(parts) >= 2:
        parts[0] = parts[0] + ","

    return " ".join(parts)

final["owner_formatted"] = final["owner"].apply(format_owner)


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


final.to_csv("/Users/jeffs/Projects/SolarProject/data/final/"+location+"_Final_Data.csv", index=False)