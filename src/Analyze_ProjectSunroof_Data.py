#Step 1

#This script takes the output from calling the Google Project Sunroof API and then further filters the matches based on how good the roof is for solar


import pandas as pd
import numpy as np
import json

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
MIN_AREA = 35
#Limit of roof segments to analyze (25 should almost always be enough)
MAX_INDEX = 25
#Minimum solar potential score of the home as defined by Google
#I think I should allow the user to set the amount of shade they will accept (this should be a bare minimum)
MIN_SOLAR = 1300


def find_matching_segments(row, min_az, max_az):
    """Find roof segments matching azimuth and area criteria"""
    matches = []

    for i in range(0, MAX_INDEX + 1):
        az_col = f"azimuth{i}"
        area_col = f"areaSqMeters{i}"
        quant_col = f"quantileStats{i}"
        # sun_quant_col = f"sunshineQuantiles{i}"

        # Skip if either column is missing
        if az_col not in row or area_col not in row:
            continue

        az = row[az_col]
        area = row[area_col]
        quant = row[quant_col]
        # sun_quant = row[sun_quant_col]

        # Skip null / non-numeric values
        if pd.isna(az) or pd.isna(area):
            continue

        if min_az <= az <= max_az and area >= MIN_AREA:
            matches.append({
                "segment": i,
                az_col: float(az),
                area_col: float(area),
                quant_col: quant,
                # sun_quant_col: (sun_quant
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
filtered_df["solar_score"] = 0.0  # initialize

for idx, segments in filtered_df["matching_segments"].items():

    # print(filtered_df.loc[idx]['segment_count'])
    segment_count = filtered_df.loc[idx]['segment_count']
    # print("Seg count: ",segment_count)

    score_sum = []

    for segment in segments:
        current_segment = segment["segment"]
        segment_area = float(segment["areaSqMeters" + str(current_segment)])
        segment_azimuth = float(segment["azimuth" + str(current_segment)])
        quant_avg = json.loads(segment['quantileStats' + str(current_segment)])['Avg']

        print(segment)
        
        azimuth_score = ((180 - (segment_azimuth - 180)) / 180) - 1

        #east facing > 0
        #west facing < 0

        #I'm multiplying by .5 because orientation is not as important as the quant's avg sunlight
        if azimuth_score > 0: #east
            modified_azimuth_score = (1 - abs(2*azimuth_score**2)) * .5
            
        else: #west
            modified_azimuth_score = (1 - abs(azimuth_score)) * .5

        # print(azimuth_score)
        print(modified_azimuth_score)
        # print((quant_avg/1800) * modified_azimuth_score * 100)
        score_sum.append((quant_avg/1800) * modified_azimuth_score * 100 - segment_count*.5) #segment_area

            # break

 
    total = max(score_sum)

    filtered_df.loc[idx, "solar_score"] = total

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
filtered_df = filtered_df[filtered_df['center_distance_m'] <=8.5]
filtered_df.to_csv(output_path, index=False)
print(f"\nResults saved to: {output_path}")