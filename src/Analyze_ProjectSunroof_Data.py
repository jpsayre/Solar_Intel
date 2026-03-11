"""
Step 1: Filter Sunroof API output by roof orientation and solar potential.

Takes the raw API output and filters to properties with qualifying
roof segments (East/South/West facing, min area, min sunshine).
Computes a solar_score for each property.
"""

import pandas as pd
import numpy as np
import json

# Azimuth Angles
EAST_MIN_AZ = 80
EAST_MAX_AZ = 140
SOUTH_MIN_AZ = 140
SOUTH_MAX_AZ = 220
WEST_MIN_AZ = 220
WEST_MAX_AZ = 280
# Minimum roof segment size in meters squared
MIN_AREA = 30
# Limit of roof segments to analyze
MAX_INDEX = 25
# Minimum solar potential score (hours/year)
MIN_SOLAR = 1300


def find_matching_segments(row, min_az, max_az):
    """Find roof segments matching azimuth and area criteria."""
    matches = []

    for i in range(0, MAX_INDEX + 1):
        az_col = f"azimuth{i}"
        area_col = f"areaSqMeters{i}"
        quant_col = f"quantileStats{i}"

        if az_col not in row or area_col not in row:
            continue

        az = row[az_col]
        area = row[area_col]
        quant = row[quant_col]

        if pd.isna(az) or pd.isna(area):
            continue

        if min_az <= az <= max_az and area >= MIN_AREA:
            matches.append({
                "segment": i,
                az_col: float(az),
                area_col: float(area),
                quant_col: quant,
            })

    return matches


def get_all_orientations(row):
    """Check all orientations and return list of matching orientations with their segments."""
    orientations = []
    all_matching_segments = []

    east_segments = find_matching_segments(row, EAST_MIN_AZ, EAST_MAX_AZ)
    if len(east_segments) > 0:
        orientations.append("East")
        all_matching_segments.extend(east_segments)

    south_segments = find_matching_segments(row, SOUTH_MIN_AZ, SOUTH_MAX_AZ)
    if len(south_segments) > 0:
        orientations.append("South")
        all_matching_segments.extend(south_segments)

    west_segments = find_matching_segments(row, WEST_MIN_AZ, WEST_MAX_AZ)
    if len(west_segments) > 0:
        orientations.append("West")
        all_matching_segments.extend(west_segments)

    return orientations, all_matching_segments


def run(config=None):
    """Filter API output by solar potential.

    Args:
        config: CountyConfig object. If None, uses legacy hardcoded paths.
    """
    if config:
        csv_input = str(config.sunroof_api_output_path)
        output_path = str(config.filtered_api_output_path)
        config.ensure_dirs()
    else:
        csv_input = '/Users/jeffs/Projects/SolarProject/data/working/Boulder_CO_Python_SunroofAPI_Output.csv'
        output_path = "/Users/jeffs/Projects/SolarProject/data/working/Boulder_CO_Filtered_API_Output.csv"

    df = pd.read_csv(csv_input)
    print(f"Initial records: {df.shape[0]}")

    df = df[df['ok'] == True]
    print(f"After OK filter: {df.shape[0]}")

    # Check all orientations for each property
    print("\nChecking for all qualifying roof segments...")
    df[["roof_orientations_list", "matching_segments"]] = df.apply(
        lambda row: pd.Series(get_all_orientations(row)), axis=1
    )

    df["roof_orientation"] = df["roof_orientations_list"].apply(
        lambda x: ", ".join(x) if len(x) > 0 else ""
    )

    filtered_df = df[df["roof_orientations_list"].str.len() > 0].copy()
    print(f"Properties with qualifying segments: {len(filtered_df)}")

    # Calculate metrics for matched segments
    filtered_df["matching_segment_count"] = filtered_df["matching_segments"].apply(len)

    filtered_df["matching_segment_sum"] = pd.to_numeric(filtered_df["matching_segments"].apply(
        lambda segments: sum(
            v for seg in segments for k, v in seg.items() if k.startswith("areaSqMeters")
        )
    ), errors="coerce").round(2)

    filtered_df["matching_segment_max"] = pd.to_numeric(filtered_df["matching_segments"].apply(
        lambda segments: max(
            v for seg in segments for k, v in seg.items() if k.startswith("areaSqMeters")
        ) if len(segments) > 0 else 0
    ), errors="coerce").round(2)

    # Filter by solar quantity
    filtered_df = filtered_df[filtered_df['sunshine'] >= MIN_SOLAR]
    print(f"After sunshine filter (>= {MIN_SOLAR}): {len(filtered_df)}")

    # Calculate solar score
    filtered_df["solar_score"] = 0.0

    for idx, segments in filtered_df["matching_segments"].items():
        segment_count = filtered_df.loc[idx]['segment_count']
        score_sum = []

        for segment in segments:
            current_segment = segment["segment"]
            segment_azimuth = float(segment["azimuth" + str(current_segment)])
            quant_avg = json.loads(segment['quantileStats' + str(current_segment)])['Avg']

            azimuth_score = ((180 - (segment_azimuth - 180)) / 180) - 1

            if azimuth_score > 0:  # east
                modified_azimuth_score = (1 - abs(azimuth_score * 1.2))
            else:  # west
                modified_azimuth_score = (1 - abs(azimuth_score * 0.8))

            score_sum.append((quant_avg / 1800) * 100 + modified_azimuth_score * 150 - (segment_count ** 2) / 15)

        total = max(score_sum)
        filtered_df.loc[idx, "solar_score"] = total

    filtered_df['solar_score'] = pd.to_numeric(filtered_df['solar_score'], errors="coerce").round(2)

    # Summary statistics
    print(f"\n=== FINAL SUMMARY ===")
    print(f"Total properties in final output: {len(filtered_df)}")
    print("\nBreakdown by orientation combinations:")
    orientation_counts = filtered_df["roof_orientation"].value_counts()
    for orientation, count in orientation_counts.items():
        print(f"  {orientation}: {count}")

    # Save result
    filtered_df = filtered_df[filtered_df['center_distance_m'] <= 8.5]
    filtered_df.to_csv(output_path, index=False)
    print(f"\nResults saved to: {output_path}")
    return filtered_df


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", help="County config name or path")
    args = parser.parse_args()

    if args.config:
        from pipeline_config import load_config
        run(load_config(args.config))
    else:
        run()
