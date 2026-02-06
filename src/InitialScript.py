import pandas as pd
from datetime import datetime
import SunroofBatchAPI

"""
This script is reading in the Regrid data and then applying filters to it before calling the Google Sunroof API for the defined row range.

NOTE - the data adds on to the existing csv_output file. So that can cause problems if this code changes anything. Sometimes it's best to delete the output file and recreate from scratch.
"""

location = 'Boulder_CO'

csv_path = '/Users/jeffs/Projects/SolarProject/data/raw/BoulderColorado_Full_Paid_WorkingCopy.csv'
csv_output = '/Users/jeffs/Projects/SolarProject/data/working/'+location+'_Python_SunroofAPI_Output.csv'


df = pd.read_csv(csv_path)

df = df.reset_index(names='original_index')



#Filters applied to data
allowed_designs = [
    "1 Story - Ranch",
    "2-3 Story",
    "Split-level",
    "Bi-level",
    "PATIO HOMES",
    "MODULAR",
    "A-Frame",
]

df = df[
    (df["usedesc"] == "SINGLE FAM.RES.-LAND") &
    (df["zoning_description"].str.contains("residential", case=False, na=False)) &
    (df["designcodedscr"].isin(allowed_designs)) &
    (df["sales_cd"] == "Q") &
    (df["mainfloorsf"] >= 800) &
    (df["saleprice"] >= 250000)
]


print("Home Type Filters: ",len(df))


df['OwnerOccupied'] = (
    df['mailadd'].astype(str).str[:6] == df['address'].astype(str).str[:6]
)
df = df[df["OwnerOccupied"] == True]

print("Owner Occupied Filters: ",len(df))


#Creating data, but not currently using as filters
df['calculated_build_year'] = (
    df[['yearbuilt', 'year_built_effective_date']]
    .apply(pd.to_numeric, errors='coerce')
    .max(axis=1)
)

df = df[df["calculated_build_year"] >= 1960]

current_year = datetime.now().year

df['calculated_roof_age'] = current_year - df['calculated_build_year']


df.to_csv('/Users/jeffs/Projects/SolarProject/data/working/'+location+'_Primary_Regrid_Filter_Output.csv', index=False)

print("Dataset Total: ",len(df))

print(df.head(10))

max_calls = 200
call_counter = 0
chunk_size = 50
start_row = 0 #set the start row to right where you left off, not +1 (ie: 200 calls, start at 200)

while call_counter < max_calls:
    remaining = max_calls - call_counter
    current_chunk = min(chunk_size, remaining)

    subset = df.iloc[start_row : start_row + current_chunk]

    if subset.empty:
        break

    SunroofBatchAPI.run(
        subset,
        csv_output,
        resume=True
    )

    start_row += current_chunk
    call_counter += len(subset)