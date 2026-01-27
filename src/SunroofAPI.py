#API Call to Google Project Sunroof

import requests
import os

api_key = os.getenv("GOOGLE_SOLAR_API_KEY")

if not api_key:
    raise RuntimeError("API key not found")


def get_building_insights(lat: float, lon: float):
    """
    Call Google Solar API buildingInsights:findClosest endpoint.

    Parameters
    ----------
    lat : float
        Latitude of the location
    lon : float
        Longitude of the location
    api_key : str
        Google API key

    Returns
    -------
    dict
        Parsed JSON response from the API
    """
    url = "https://solar.googleapis.com/v1/buildingInsights:findClosest"
    params = {
        "location.latitude": lat,
        "location.longitude": lon,
        "requiredQuality": "LOW",
        "key": api_key
    }

    response = requests.get(url, params=params, timeout=30)
    response.raise_for_status()  # raises HTTPError for non-200 responses

    data = response.json()
    
    max_segments = 25

    segments = data["solarPotential"].get("roofSegmentStats", []) or []

    combined = {
        "latitude": data["center"]["latitude"],
        "longitude": data["center"]["longitude"],
        "year": data["imageryDate"]["year"],
        "month": data["imageryDate"]["month"],
        "day": data["imageryDate"]["day"],
        "sunshine": data["solarPotential"].get("maxSunshineHoursPerYear"),
        "segment_count": len(segments),
    }

    # Initialize columns for consistency
    for i in range(1, max_segments + 1):
        combined[f"azimuth{i}"] = None
        combined[f"areaSqMeters{i}"] = None

    # Fill what exists (optionally sort by area desc first)
    segments_sorted = sorted(
        segments,
        key=lambda s: (s.get("stats", {}) or {}).get("areaMeters2", 0) or 0,
        reverse=True
    )

    for i, seg in enumerate(segments_sorted[:max_segments], start=1):
        stats = seg.get("stats", {}) or {}
        combined[f"azimuth{i}"] = seg.get("azimuthDegrees")
        combined[f"areaSqMeters{i}"] = stats.get("areaMeters2")

    # print(combined)
    return combined
