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
EAST_MIN_AZ = 80
EAST_MAX_AZ = 140
SOUTH_MIN_AZ = 140
SOUTH_MAX_AZ = 220
WEST_MIN_AZ = 220
WEST_MAX_AZ = 280
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


def get_all_orientations(row):
    """Check all orientations and return list of matching orientations with their segments"""
    orientations = []
    all_matching_segments = []
    
    # Check East
    east_segments = find_matching_segments(row, EAST_MIN_AZ, EAST_MAX_AZ)
    if len(east_segments) > 0:
        orientations.append("East")
        all_matching_segments.extend(east_segments)
    
    # Check South
    south_segments = find_matching_segments(row, SOUTH_MIN_AZ, SOUTH_MAX_AZ)
    if len(south_segments) > 0:
        orientations.append("South")
        all_matching_segments.extend(south_segments)
    
    # Check West
    west_segments = find_matching_segments(row, WEST_MIN_AZ, WEST_MAX_AZ)
    if len(west_segments) > 0:
        orientations.append("West")
        all_matching_segments.extend(west_segments)
    
    return orientations, all_matching_segments


# Check all orientations for each property
print("\nChecking for all qualifying roof segments...")
df[["roof_orientations_list", "matching_segments"]] = df.apply(
    lambda row: pd.Series(get_all_orientations(row)), axis=1
)

# Create roof_orientation column as comma-separated string
df["roof_orientation"] = df["roof_orientations_list"].apply(
    lambda x: ", ".join(x) if len(x) > 0 else ""
)

# Filter to properties with at least one matching orientation
filtered_df = df[df["roof_orientations_list"].str.len() > 0].copy()
print(f"Properties with qualifying segments: {len(filtered_df)}")


# Calculate metrics for matched segments
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
    ) if len(segments) > 0 else 0
), errors="coerce").round(2)


# Filter by solar quantity
filtered_df = filtered_df[filtered_df['sunshine'] >= MIN_SOLAR]
print(f"After sunshine filter (>= {MIN_SOLAR}): {len(filtered_df)}")


# Calculate solar score
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


# Summary statistics
print("\n=== FINAL SUMMARY ===")
print(f"Total properties in final output: {len(filtered_df)}")
print("\nBreakdown by orientation combinations:")
orientation_counts = filtered_df["roof_orientation"].value_counts()
for orientation, count in orientation_counts.items():
    print(f"  {orientation}: {count}")


# Save result
output_path = "/Users/jeffs/Projects/SolarProject/data/working/"+location+"_Filtered_API_Output.csv"
filtered_df.to_csv(output_path, index=False)
print(f"\nResults saved to: {output_path}")