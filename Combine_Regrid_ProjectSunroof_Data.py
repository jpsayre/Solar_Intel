#Step 2

import pandas as pd
import numpy as np

"""
This script is merging the Regrid data with the filtered Project Sunroof data.

"""

# --- Load ---
# A = pd.read_csv("/Users/jeffs/Library/Mobile Documents/com~apple~CloudDocs/Boulder_HighlyQualifiedFilter.csv")
A = pd.read_csv('/Users/jeffs/Library/Mobile Documents/com~apple~CloudDocs/Primary_Regrid_Filter_Output.csv')
B = pd.read_csv("/Users/jeffs/Downloads/Filtered_API_Output.csv")

# Inner join (A on left; only matched rows kept)
merged = A.merge(
    B,
    how="inner",
    on="original_index",

)

# --- Save ---
merged.to_csv("/Users/jeffs/Downloads/Regrid_joined_with_API.csv", index=False)


#This saves the file with indexs and lat long to be used by the n8n solar panel classifier workflow
n8n_Lat_Long = merged[["original_index","lat","lon"]]

n8n_Lat_Long["solar_panels"] = ''

n8n_Lat_Long.to_csv("/Users/jeffs/Downloads/n8n_Lat_Long.csv", index=False)
