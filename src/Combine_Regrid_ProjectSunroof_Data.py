#Step 2

import os
import pandas as pd
import numpy as np

"""
This script is merging the Regrid data with the filtered Project Sunroof data.

"""
location = 'Boulder_CO'

# --- Load ---
# A = pd.read_csv("/Users/jeffs/Library/Mobile Documents/com~apple~CloudDocs/Boulder_HighlyQualifiedFilter.csv")
A = pd.read_csv('/Users/jeffs/Projects/SolarProject/data/working/'+location+'_Primary_Regrid_Filter_Output.csv')
B = pd.read_csv("/Users/jeffs/Projects/SolarProject/data/working/"+location+"_Filtered_API_Output.csv")

# Inner join (A on left; only matched rows kept)
merged = A.merge(
    B,
    how="inner",
    on="original_index",

)

# --- Save ---
output_path = "/Users/jeffs/Projects/SolarProject/data/working/"+location+"_Regrid_joined_with_API.csv"
if os.path.exists(output_path):
    existing = pd.read_csv(output_path)
    existing_ids = set(existing["original_index"].astype(str))
    # Only add rows that are not already in the joined file (preserves downstream-filled columns)
    new_rows = merged[~merged["original_index"].astype(str).isin(existing_ids)]
    to_write = pd.concat([existing, new_rows], ignore_index=True)
else:
    to_write = merged
to_write.to_csv(output_path, index=False)


#This saves the file with indexs and lat long to be used by the n8n solar panel classifier workflow
# Lat_Long = merged[["original_index","lat","lon"]]

# Lat_Long["solar_panels"] = ''

# Lat_Long.to_csv("/Users/jeffs/Projects/SolarProject/data/working/"+location+"_Lat_Long_For_Solar_Classification.csv", index=False)
