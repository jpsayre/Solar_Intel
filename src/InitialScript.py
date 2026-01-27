import pandas as pd
from datetime import datetime
import SunroofBatchAPI

"""
This script is reading in the Regrid data and then applying filters to it before calling the Google Sunroof API for the defined row range.

NOTE - the data adds on to the existing file. So that can cause problems if this code changes anything. Sometimes it's best to delete the output file and recreate from scratch.
"""

location = 'Boulder_CO'

csv_path = '~/Projects/data/raw/BoulderColorado_Full_Paid_WorkingCopy.csv'
csv_output = '~/Projects/data/working/'+location+'_Python_SunroofAPI_Output.csv'


df = pd.read_csv(csv_path)

df = df.reset_index(names='original_index')


#Filters applied to data
df = df[df["zoning_description"] == 'Residential Single Family']

df = df[df["saleprice"]>=300000]

df['OwnerOccupied'] = (
    df['mailadd'].astype(str).str[:6] == df['address'].astype(str).str[:6]
)
df = df[df["OwnerOccupied"] == True]


#Creating data, but not currently using as filters
df['calculated_build_year'] = (
    df[['yearbuilt', 'year_built_effective_date']]
    .apply(pd.to_numeric, errors='coerce')
    .max(axis=1)
)

current_year = datetime.now().year

df['calculated_roof_age'] = current_year - df['calculated_build_year']

df['PotentialRoofAge'] = df['calculated_roof_age'] % 30


df.to_csv('~/Projects/data/working/'+location+'Primary_Regrid_Filter_Output.csv', index=False)

print(len(df))



max_calls = 500
call_counter = 0
chunk_size = 50
start_row = 0

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