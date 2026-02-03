#Step 2

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
merged.to_csv("/Users/jeffs/Projects/SolarProject/data/working/"+location+"_Regrid_joined_with_API.csv", index=False)


#This saves the file with indexs and lat long to be used by the n8n solar panel classifier workflow
Lat_Long = merged[["original_index","lat","lon"]]

Lat_Long["solar_panels"] = ''

Lat_Long.to_csv("/Users/jeffs/Projects/SolarProject/data/working/"+location+"_Lat_Long_For_Solar_Classification.csv", index=False)
