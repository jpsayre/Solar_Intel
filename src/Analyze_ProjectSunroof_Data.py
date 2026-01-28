#Step 1

#This script takes the output from calling the Google Project Sunroof API and then further filters the matches based on how good the roof is for solar


import pandas as pd
import numpy as np

# Load CSV
csv_input = '/Users/jeffs/Projects/SolarProject/data/working/Boulder_Python_SunroofAPI_Output_10.csv'

df = pd.read_csv(csv_input)
print(df.shape)

df = df[df['ok'] == True]

#Azimuth Angles
MIN_AZ = 160
MAX_AZ = 200
#Minimum roof segment size in meters squared
MIN_AREA = 30
#Limit of roof segments to analyze (25 should almost always be enough)
MAX_INDEX = 25
#Minimum solar potential score of the home as defined by Google
MIN_SOLAR = 1700




def find_matching_segments(row):
    matches = []

    for i in range(0, MAX_INDEX + 1):
        az_col = f"azimuth{i}"
        area_col = f"areaSqMeters{i}"

        # Skip if either column is missing
        if az_col not in row or area_col not in row:
            continue

        az = row[az_col]
        area = row[area_col]

        # Skip null / non-numeric values
        if pd.isna(az) or pd.isna(area):
            continue

        if MIN_AZ <= az <= MAX_AZ and area >= MIN_AREA:
            matches.append({
                "segment": i,
                az_col: float(az),
                area_col: float(area)
            })

    return matches


# Create new column with matching segment indices
df["matching_segments"] = df.apply(find_matching_segments, axis=1)

filtered_df = df[df["matching_segments"].str.len() > 0]

# Count of matching segments per row
filtered_df["matching_segment_count"] = filtered_df["matching_segments"].apply(len)

# Sum of matching segment areas per row
filtered_df["matching_segment_sum"] = pd.to_numeric(filtered_df["matching_segments"].apply(
    lambda segments: sum(
        v for seg in segments for k, v in seg.items() if k.startswith("areaSqMeters")
    )
)
,errors="coerce").round(2)

# Max matching segment area per row
filtered_df["matching_segment_max"] = pd.to_numeric(filtered_df["matching_segments"].apply(
    lambda segments: max(
        v for seg in segments for k, v in seg.items() if k.startswith("areaSqMeters")
    )
)
,errors="coerce").round(2)


#Filter by solar quantity
filtered_df = filtered_df[filtered_df['sunshine'] >= MIN_SOLAR]

# filtered_df['solar_score'] = pd.to_numeric(filtered_df['sunshine']/1900 * filtered_df["matching_segment_max"] + filtered_df["matching_segment_count"]*10
# ,errors="coerce").round(2)

# filtered_df['solar_score'] = pd.to_numeric(filtered_df['sunshine']/1900 * filtered_df["matching_segment_sum"] - filtered_df["matching_segment_count"]*10
# ,errors="coerce").round(2)

# IF(BL4>1,(BM4-BN4)/(BL4)+BN4, BN4)-BL4*5


#create solar score



filtered_df['solar_score'] = np.where(

filtered_df["matching_segment_count"] > 1,

filtered_df['sunshine']/1900 * ((filtered_df["matching_segment_sum"] - filtered_df["matching_segment_max"])/(filtered_df["matching_segment_count"]-1) + filtered_df["matching_segment_max"]) - filtered_df["matching_segment_count"]*15,

filtered_df['sunshine']/1900 * (filtered_df["matching_segment_max"])

) 

filtered_df['solar_score'] = pd.to_numeric(filtered_df['solar_score'], errors="coerce").round(2)


# if filtered_df["matching_segment_count"] > 1:

#     filtered_df['solar_score'] = pd.to_numeric(filtered_df['sunshine']/1900 * ((filtered_df["matching_segment_sum"] - filtered_df["matching_segment_max"])/filtered_df["matching_segment_count"]-1) - filtered_df["matching_segment_count"]*15, errors="coerce").round(2)

# else:

#     filtered_df['solar_score'] = pd.to_numeric(filtered_df['sunshine']/1900 * (filtered_df["matching_segment_max"]) - filtered_df["matching_segment_count"]*15, errors="coerce").round(2)


# Save result
filtered_df.to_csv("/Users/jeffs/Projects/SolarProject/data/working/Filtered_API_Output_500_score.csv", index=False)
