import time
import requests
import pandas as pd
import os

API_URL = "https://solar.googleapis.com/v1/buildingInsights:findClosest"


def get_building_insights(lat: float, lon: float, session: requests.Session, api_key: str):
    params = {
        "location.latitude": lat,
        "location.longitude": lon,
        "requiredQuality": "LOW",
        "key": api_key,
    }
    response = session.get(API_URL, params=params, timeout=30)
    response.raise_for_status()
    return response.json()


def flatten_building_insights(data: dict, max_segments: int = 25) -> dict:
    """Flatten the API response into a single, CSV-friendly row.

    Produces:
      - latitude/longitude from response center
      - imagery date (year/month/day)
      - sunshine + segment_count
      - azimuth{i}, areaSqMeters{i} for up to max_segments roof segments (sorted by area desc)
    """
    solar = (data.get("solarPotential") or {})
    center = (data.get("center") or {})
    imagery = (data.get("imageryDate") or {})

    segments = solar.get("roofSegmentStats", []) or []

    combined = {
        "latitude": center.get("latitude"),
        "longitude": center.get("longitude"),
        "year": imagery.get("year"),
        "month": imagery.get("month"),
        "day": imagery.get("day"),
        "sunshine": solar.get("maxSunshineHoursPerYear"),
        "segment_count": len(segments),
    }

    # Initialize columns for consistency
    for i in range(1, max_segments + 1):
        combined[f"azimuth{i}"] = None
        combined[f"areaSqMeters{i}"] = None

    # Sort segments by area (desc) so segment 1 is the biggest
    segments_sorted = sorted(
        segments,
        key=lambda s: ((s.get("stats") or {}).get("areaMeters2") or 0),
        reverse=True,
    )

    for i, seg in enumerate(segments_sorted[:max_segments], start=1):
        stats = seg.get("stats", {}) or {}
        combined[f"azimuth{i}"] = seg.get("azimuthDegrees")
        combined[f"areaSqMeters{i}"] = stats.get("areaMeters2")

    return combined


def fetch_ok(payload: dict, max_segments: int) -> dict:
    row = flatten_building_insights(payload, max_segments=max_segments)
    row.update({"ok": True, "error": None})
    return row


def fetch_err(msg: str, max_segments: int) -> dict:
    # Return a row with the expected flattened columns, but empty values.
    row = flatten_building_insights({}, max_segments=max_segments)
    row.update({"ok": False, "error": msg})
    return row


def fetch_with_retries(lat, lon, session, api_key, max_retries=5, max_segments: int = 25):
    delay = 1.0
    last_err = None

    for _ in range(max_retries):
        try:
            payload = get_building_insights(lat, lon, session, api_key)
            return fetch_ok(payload, max_segments=max_segments)
        except requests.HTTPError as e:
            status = getattr(e.response, "status_code", None)
            url = getattr(e.response, "url", "")
            safe_url = url.split("key=")[0] + "key=REDACTED" if "key=" in url else url
            last_err = f"HTTP {status}: {safe_url}"
            # Retry common transient codes / rate limiting
            if status in (429, 500, 502, 503, 504):
                time.sleep(delay)
                delay *= 2
                continue
            return fetch_err(last_err, max_segments=max_segments)
        except requests.RequestException as e:
            last_err = str(e)
            time.sleep(delay)
            delay *= 2

    return fetch_err(f"Retries exhausted: {last_err}", max_segments=max_segments)


def run(
    subset: pd.DataFrame,
    csv_output: str,
    checkpoint_every: int = 100,
    resume: bool = True,
    max_segments: int = 25,
    input_id_cols: list[str] = None,
):
    """Run API calls sequentially and persist results incrementally.

    Inputs
    - subset: DataFrame that MUST contain columns 'lat' and 'lon' and may contain one or more ID/index columns (e.g. filtered_index, original_index)
    - csv_output: path to output CSV

    Behavior
    - Appends each completed row to CSV (plus periodic flush)
    - If csv_output already exists, this function *locks* to the existing header/schema
      (including the existing max_segments) to avoid mixed-column CSV corruption.
    """
    import csv

    api_key = os.getenv("GOOGLE_SOLAR_API_KEY")
    if not api_key:
        raise RuntimeError("GOOGLE_SOLAR_API_KEY not set")

    file_exists = os.path.exists(csv_output)

    # If the output file already exists, reuse its header/schema to prevent mixing runs
    # with different max_segments.
    if file_exists:
        with open(csv_output, "r", newline="", encoding="utf-8") as rf:
            reader = csv.reader(rf)
            existing_header = next(reader, None)
        if existing_header:
            fieldnames = existing_header
            # Infer max_segments from existing header (count azimuth columns)
            inferred = sum(1 for c in fieldnames if c.startswith("azimuth"))
            if inferred > 0:
                max_segments = inferred
        else:
            file_exists = False  # treat as new/empty file

    # If it's a new file, define the schema based on max_segments
    if not file_exists:
        # Default ID columns if not provided
        if input_id_cols is None:
            input_id_cols = ["original_index"]

        fieldnames = [
            *input_id_cols,
            "input_lat",
            "input_lon",
            "ok",
            "error",
            "latitude",
            "longitude",
            "year",
            "month",
            "day",
            "sunshine",
            "segment_count",
        ]
        for i in range(1, max_segments + 1):
            fieldnames.append(f"azimuth{i}")
            fieldnames.append(f"areaSqMeters{i}")

    # Build a set of already-processed (input_lat, input_lon) pairs so we can resume.
    processed = set()

    # Default ID columns if not provided (needed for resume + writing)
    if input_id_cols is None:
        input_id_cols = ["original_index"]
    if resume and os.path.exists(csv_output):
        try:
            processed = set(zip(*(existing[c] for c in input_id_cols), existing["input_lat"], existing["input_lon"]))
            processed = set(zip(existing["input_lat"], existing["input_lon"]))
        except Exception:
            processed = set()

    # Open in append mode; write header only if the file is new.
    with open(csv_output, "a", newline="", encoding="utf-8") as f, requests.Session() as session:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not os.path.exists(csv_output) or (os.path.getsize(csv_output) == 0):
            writer.writeheader()
            f.flush()

        written_since_flush = 0

        for _, r in subset.iterrows():
            in_lat, in_lon = r["lat"], r["lon"]
            in_ids = {col: r.get(col, None) for col in input_id_cols}

            # Skip rows already written to disk (resume mode)
            if resume and (*in_ids.values(), in_lat, in_lon) in processed:
                continue

            result = fetch_with_retries(
                in_lat,
                in_lon,
                session,
                api_key,
                max_segments=max_segments,
            )

            out_row = {**in_ids, "input_lat": in_lat, "input_lon": in_lon, **result}
            out_row = {k: out_row.get(k) for k in fieldnames}  # enforce schema

            writer.writerow(out_row)
            written_since_flush += 1
            processed.add((*in_ids.values(), in_lat, in_lon))

            # Periodically flush to disk so progress is durable
            if written_since_flush >= checkpoint_every:
                f.flush()
                written_since_flush = 0

        f.flush()

    # Return the final dataset for convenience
    return pd.read_csv(csv_output)

