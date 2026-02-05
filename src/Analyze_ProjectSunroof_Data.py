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
MIN_SOLAR = 1000


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
# Solar score formula:
# - Multiple segments: weighted average area × normalized sunshine - segment penalty
# - Single segment: max area × normalized sunshine
# filtered_df['solar_score'] = np.where(
#     filtered_df["matching_segment_count"] > 1,
#     # Multi-segment: (sunshine/1900) × weighted_avg_area - count_penalty
#     filtered_df['sunshine']/1900 * (
#         (filtered_df["matching_segment_sum"] - filtered_df["matching_segment_max"]) / 
#         (filtered_df["matching_segment_count"] - 1) + 
#         filtered_df["matching_segment_max"]
#     ) - filtered_df["matching_segment_count"] * 15,
#     # Single segment: (sunshine/1900) × max_area
#     filtered_df['sunshine']/1900 * filtered_df["matching_segment_max"]
# ) 

"""
Now that I do multiple orientations, I need to rework solar score. The ideal is a big, simple, sunny, south facing roof.

Normalize it all on a 100 scale

[{'segment': 1, 'azimuth1': 155.14464, 'areaSqMeters1': 165.13486}, {'segment': 3, 'azimuth3': 245.03754, 'areaSqMeters3': 96.33909}]

sunshine * (SUM(segment area * ((180 - abs(azimuth-180))/180) - segment count * 10)

sunshine scaler | perfect south is full score (180), the more off the more of a penalty (scales the segment area score) | subtract for roof complexity
"""


filtered_df["solar_score"] = 0.0  # initialize

for idx, segments in filtered_df["matching_segments"].items():

    # print(filtered_df.loc[idx])
    score_sum = []

    for segment in segments:
        current_segment = segment["segment"]
        segment_area = float(segment["areaSqMeters" + str(current_segment)])
        segment_azimuth = float(segment["azimuth" + str(current_segment)])
        quant_avg = json.loads(segment['quantileStats' + str(current_segment)])['Avg']

        print(segment)
        # print(quant_avg)
        # print(type(quant_avg))

        if segment_area > 40 and abs(segment_azimuth - 180) < 15 and quant_avg > 1500:
            score_sum.append(999)
            #code for perfect score

        # elif segment_area > 35 and abs(segment_azimuth - 180) < 20 and quant_avg > 1350:
        #     score_sum.append(888)
        #     #code for next best

        else:
            azimuth_score = ((180 - (segment_azimuth - 180)) / 180) - 1

            #east facing > 0
            #west facing < 0

            if azimuth_score > 0: #east
                modified_azimuth_score = 1 - abs(2*azimuth_score**2)
                
            else: #west
                modified_azimuth_score = 1 - abs(azimuth_score)

            print(azimuth_score)
            print(modified_azimuth_score)
            print((quant_avg/1900) * modified_azimuth_score * 100)
            score_sum.append((quant_avg/1900) * modified_azimuth_score * 100) #segment_area

            # break

    print(score_sum)
    # if 888 in score_sum:
    #     total = 90
    if 999 in score_sum:
        total = 100
    else:
        total = max(score_sum)

    filtered_df.loc[idx, "solar_score"] = total #- (filtered_df.loc[idx, "segment_count"])
    #     (filtered_df.loc[idx, "sunshine"] / 2000) * (total - filtered_df.loc[idx, "segment_count"] * 5)
    # )


# for i in filtered_df['matching_segments']:

#     score_sum = []

#     for segment in i:
#         print(segment)
#         current_segment = segment['segment']
#         segment_area = segment['areaSqMeters'+str(current_segment)]
#         segment_azimuth = segment['azimuth'+str(current_segment)]
        
#         if segment_area > 50 and abs(segment_azimuth-180) < 10:
        
#             score_sum.append(1000)

#             break

        
#         azimuth_score = ((180-(segment['azimuth'+str(current_segment)]-180))/180)-1
#         print('Azimuth Score: ',azimuth_score)

#         if azimuth_score > 0:
#             #this penalizes east facing roofs) 
#             modified_azimuth_score = 1 - abs(azimuth_score*1.5)

#         if azimuth_score <= 0:
#             #this gives full score to any south or west facing roof
#             modified_azimuth_score = 1 - abs(azimuth_score)

#         print('Modified Score: ', modified_azimuth_score)

        
#         print(segment_area)
#         segment_score = modified_azimuth_score * segment_area
#         print('Segment Score: ',segment_score)

#         score_sum.append(segment_score)

#     print('SCORE SUM:', sum(score_sum))
#     filtered_df['solar_score'] = (filtered_df['sunshine']/2000) * (sum(score_sum) - filtered_df["segment_count"] * 5)

    # print(i)

# filtered_df['solar_score'] = np.where(
#     filtered_df["matching_segment_count"] > 1,
#     # Multi-segment: (sunshine/1900) × weighted_avg_area - count_penalty
#     filtered_df['sunshine']/1900 * (
#         (filtered_df["matching_segment_sum"] - filtered_df["matching_segment_max"]) / 
#         (filtered_df["matching_segment_count"] - 1) + 
#         filtered_df["matching_segment_max"]
#     ) - filtered_df["matching_segment_count"] * 15,
#     # Single segment: (sunshine/1900) × max_area
#     filtered_df['sunshine']/1900 * filtered_df["matching_segment_max"]
# ) 




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