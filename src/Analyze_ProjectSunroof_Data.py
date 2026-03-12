"""
Step 1: Enrich Sunroof API output with roof orientation and solar scoring.

Takes the raw API output and computes qualifying roof segments
(East/South/West facing, min area, min sunshine) and a solar_score.
All ok=True homes are kept — no homes are dropped.
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
    """Find roof segments matching azimuth criteria (any area, E/S/W facing)."""
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

        if min_az <= az <= max_az:
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
    """Enrich API output with roof orientation and solar scoring.

    All ok=True homes are kept. Homes without qualifying segments
    get empty roof_orientation and solar_score=0.

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

    has_segments = df["roof_orientations_list"].str.len() > 0
    has_qualifying = has_segments & (df["matching_segments"].apply(
        lambda segs: any(
            v >= MIN_AREA for seg in segs for k, v in seg.items() if k.startswith("areaSqMeters")
        )
    ))
    print(f"Properties with E/S/W segments: {has_segments.sum()}")
    print(f"  Of which >= {MIN_AREA} sqm (qualifying): {has_qualifying.sum()}")
    print(f"Properties with no E/S/W segments: {(~has_segments).sum()}")

    # Calculate metrics for matched segments (0 for homes without)
    df["matching_segment_count"] = df["matching_segments"].apply(len)

    df["matching_segment_sum"] = pd.to_numeric(df["matching_segments"].apply(
        lambda segments: sum(
            v for seg in segments for k, v in seg.items() if k.startswith("areaSqMeters")
        )
    ), errors="coerce").fillna(0).round(2)

    df["matching_segment_max"] = pd.to_numeric(df["matching_segments"].apply(
        lambda segments: max(
            v for seg in segments for k, v in seg.items() if k.startswith("areaSqMeters")
        ) if len(segments) > 0 else 0
    ), errors="coerce").fillna(0).round(2)

    # Filter by center distance (prevents sheds/outbuildings from being scored as the roof)
    if "center_distance_m" in df.columns:
        before = len(df)
        df = df[df["center_distance_m"] <= 8.5]
        print(f"After center_distance filter (<= 8.5m): {len(df)} ({before - len(df)} removed)")

    # Sunshine stats (no filtering)
    has_sunshine = df['sunshine'] >= MIN_SOLAR if 'sunshine' in df.columns else pd.Series(False, index=df.index)
    print(f"Properties with sunshine >= {MIN_SOLAR}: {has_sunshine.sum()}")

    # Calculate solar score with area scaling
    # Tier 1: E/S/W segments >= MIN_AREA → full score
    # Tier 2: E/S/W segments < MIN_AREA → score scaled by area/MIN_AREA
    # Tier 3: No E/S/W segments → floor value of 10
    # Tier 4: No Sunroof data (not in this df) → stays NULL
    FLOOR_SCORE = 10.0
    df["solar_score"] = np.nan

    for idx, segments in df["matching_segments"].items():
        if len(segments) == 0:
            # Tier 3: Sunroof data exists but no E/S/W segments
            df.loc[idx, "solar_score"] = FLOOR_SCORE
            continue
        segment_count = df.loc[idx]['segment_count']
        score_sum = []

        for segment in segments:
            current_segment = segment["segment"]
            segment_azimuth = float(segment["azimuth" + str(current_segment)])
            segment_area = float(segment["areaSqMeters" + str(current_segment)])
            quant_avg = json.loads(segment['quantileStats' + str(current_segment)])['Avg']

            azimuth_score = ((180 - (segment_azimuth - 180)) / 180) - 1

            if azimuth_score > 0:  # east
                modified_azimuth_score = (1 - abs(azimuth_score * 1.2))
            else:  # west
                modified_azimuth_score = (1 - abs(azimuth_score * 0.8))

            base_score = (quant_avg / 1800) * 100 + modified_azimuth_score * 150 - (segment_count ** 2) / 15

            # Area scaling: full credit at MIN_AREA, proportionally less below
            area_factor = min(1.0, segment_area / MIN_AREA)
            score_sum.append(base_score * area_factor)

        if score_sum:
            df.loc[idx, "solar_score"] = max(score_sum)

    df['solar_score'] = pd.to_numeric(df['solar_score'], errors="coerce").round(2)

    # Summary statistics
    print(f"\n=== FINAL SUMMARY ===")
    print(f"Total properties in output: {len(df)}")
    print(f"  With E/S/W segments: {has_segments.sum()}")
    print(f"  With qualifying segments (>= {MIN_AREA} sqm): {has_qualifying.sum()}")
    print(f"  With solar_score > {FLOOR_SCORE}: {(df['solar_score'] > FLOOR_SCORE).sum()}")
    print(f"  At floor score ({FLOOR_SCORE}): {(df['solar_score'] == FLOOR_SCORE).sum()}")
    print("\nBreakdown by orientation combinations:")
    orientation_counts = df[df["roof_orientation"] != ""]["roof_orientation"].value_counts()
    for orientation, count in orientation_counts.items():
        print(f"  {orientation}: {count}")

    # Save result — keep all homes
    df.to_csv(output_path, index=False)
    print(f"\nResults saved to: {output_path}")
    return df


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
