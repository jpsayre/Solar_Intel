#Step 1

#This script takes the output from calling the Google Project Sunroof API and then further filters the matches based on how good the roof is for solar


import pandas as pd
import numpy as np

location = 'Boulder_CO'

# Load CSV
csv_input = '/Users/jeffs/Projects/SolarProject/data/working/'+location+'_Python_SunroofAPI_Output.csv'

df = pd.read_csv(csv_input)
print(f"Initial records: {df.shape[0]}")

df = df[df['ok'] == True]
print(f"After OK filter: {df.shape[0]}")

#Azimuth Angles
SOUTH_MIN_AZ = 150
SOUTH_MAX_AZ = 220
WEST_MIN_AZ = 220
WEST_MAX_AZ = 275
#Minimum roof segment size in meters squared
MIN_AREA = 30
#Limit of roof segments to analyze (25 should almost always be enough)
MAX_INDEX = 25
#Minimum solar potential score of the home as defined by Google
MIN_SOLAR = 1700


def find_matching_segments(row, min_az, max_az):
    """Find roof segments matching azimuth and area criteria"""
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

        if min_az <= az <= max_az and area >= MIN_AREA:
            matches.append({
                "segment": i,
                az_col: float(az),
                area_col: float(area)
            })

    return matches


# STEP 1: Check for SOUTH-facing segments
print("\nChecking for south-facing segments...")
df["matching_segments"] = df.apply(lambda row: find_matching_segments(row, SOUTH_MIN_AZ, SOUTH_MAX_AZ), axis=1)
df["has_match"] = df["matching_segments"].str.len() > 0

# Separate south matches from non-matches
south_df = df[df["has_match"]].copy()
south_df["primary_roof_orientation"] = "south"
print(f"Properties with south-facing segments: {len(south_df)}")

remaining_df = df[~df["has_match"]].copy()
print(f"Properties without south-facing segments: {len(remaining_df)}")


# STEP 2: Check remaining properties for WEST-facing segments
print("\nChecking remaining properties for west-facing segments...")
remaining_df["matching_segments"] = remaining_df.apply(lambda row: find_matching_segments(row, WEST_MIN_AZ, WEST_MAX_AZ), axis=1)
remaining_df["has_match"] = remaining_df["matching_segments"].str.len() > 0

west_df = remaining_df[remaining_df["has_match"]].copy()
west_df["primary_roof_orientation"] = "west"
print(f"Properties with west-facing segments: {len(west_df)}")


# STEP 3: Combine south and west matches
filtered_df = pd.concat([south_df, west_df], ignore_index=True)
print(f"\nTotal properties with matching segments: {len(filtered_df)}")


# STEP 4: Calculate metrics for matched segments
# Count of matching segments per row
filtered_df["matching_segment_count"] = filtered_df["matching_segments"].apply(len)

# Sum of matching segment areas per row
filtered_df["matching_segment_sum"] = pd.to_numeric(filtered_df["matching_segments"].apply(
    lambda segments: sum(
        v for seg in segments for k, v in seg.items() if k.startswith("areaSqMeters")
    )
), errors="coerce").round(2)

# Max matching segment area per row
filtered_df["matching_segment_max"] = pd.to_numeric(filtered_df["matching_segments"].apply(
    lambda segments: max(
        v for seg in segments for k, v in seg.items() if k.startswith("areaSqMeters")
    )
), errors="coerce").round(2)


# STEP 5: Filter by solar quantity
filtered_df = filtered_df[filtered_df['sunshine'] >= MIN_SOLAR]
print(f"After sunshine filter (>= {MIN_SOLAR}): {len(filtered_df)}")


# STEP 6: Calculate solar score
# Solar score formula:
# - Multiple segments: weighted average area × normalized sunshine - segment penalty
# - Single segment: max area × normalized sunshine
filtered_df['solar_score'] = np.where(
    filtered_df["matching_segment_count"] > 1,
    # Multi-segment: (sunshine/1900) × weighted_avg_area - count_penalty
    filtered_df['sunshine']/1900 * (
        (filtered_df["matching_segment_sum"] - filtered_df["matching_segment_max"]) / 
        (filtered_df["matching_segment_count"] - 1) + 
        filtered_df["matching_segment_max"]
    ) - filtered_df["matching_segment_count"] * 15,
    # Single segment: (sunshine/1900) × max_area
    filtered_df['sunshine']/1900 * filtered_df["matching_segment_max"]
) 

filtered_df['solar_score'] = pd.to_numeric(filtered_df['solar_score'], errors="coerce").round(2)


# STEP 7: Summary statistics
print("\n=== FINAL SUMMARY ===")
print(f"Total properties in final output: {len(filtered_df)}")
print(f"South-facing: {len(filtered_df[filtered_df['primary_roof_orientation'] == 'south'])}")
print(f"West-facing: {len(filtered_df[filtered_df['primary_roof_orientation'] == 'west'])}")


# Save result
output_path = "/Users/jeffs/Projects/SolarProject/data/working/"+location+"_Filtered_API_Output_Orientation.csv"
filtered_df.to_csv(output_path, index=False)
print(f"\nResults saved to: {output_path}")