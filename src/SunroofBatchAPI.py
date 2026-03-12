import json
import time
import requests
import pandas as pd
import os

API_URL = "https://solar.googleapis.com/v1/buildingInsights:findClosest"
GEOCODE_URL = "https://maps.googleapis.com/maps/api/geocode/json"

# Additional columns read from input CSV and stored in output
PASSTHROUGH_COLUMNS = ["mailadd", "city", "state2", "area_building", "manual_solar_panels"]
# Roof area shortfall: retry if sum(areaSqMeters) < area_building (converted to m²) * AREA_THRESHOLD
AREA_THRESHOLD = 0.7
# area_building is in sq ft; areaSqMeters are in sq m. 1 sq ft = this many sq m.
SQFT_TO_SQM = 0.09290304

import math


def haversine_m(lat1, lon1, lat2, lon2):
    R = 6371000.0  # meters
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)

    a = (
        math.sin(dphi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    )
    return 2 * R * math.asin(math.sqrt(a))


def get_building_insights(lat: float, lon: float, session: requests.Session, api_key: str):
    params = {
        "location.latitude": lat,
        "location.longitude": lon,
        "requiredQuality": "MEDIUM",
        "key": api_key,
    }
    response = session.get(API_URL, params=params, timeout=30)
    response.raise_for_status()
    return response.json()


def get_lat_lon_from_address(address: str, session: requests.Session, api_key: str):
    """Geocode an address string and return (lat, lon) or (None, None) on failure."""
    if not address or not str(address).strip():
        return None, None
    # Use comma-separated "Street, City, State" format per Geocoding API examples
    address_clean = address.strip()
    params = {"address": address_clean, "key": api_key}
    try:
        response = session.get(GEOCODE_URL, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()
        status = data.get("status", "")
        if status != "OK" or not data.get("results"):
            error_msg = data.get("error_message", "")
            print(f"    Geocode API response: status={status!r}" + (f", error_message={error_msg!r}" if error_msg else ""))
            return None, None
        loc = data["results"][0].get("geometry", {}).get("location", {})
        lat = loc.get("lat")
        lon = loc.get("lng")
        return (lat, lon) if lat is not None and lon is not None else (None, None)
    except requests.RequestException as e:
        print(f"    Geocode API request failed: {e}")
        return None, None
    except (KeyError, IndexError, TypeError) as e:
        print(f"    Geocode API parse error: {e}")
        return None, None


def sum_area_sq_meters(result: dict, max_segments: int = None) -> float:
    """Sum every areaSqMeters{i} in the result (all roof segments)."""
    total = 0.0
    for key, v in result.items():
        if key is not None and isinstance(key, str) and key.startswith("areaSqMeters") and v is not None:
            try:
                total += float(v)
            except (TypeError, ValueError):
                pass
    return total


def flatten_building_insights(data: dict, max_segments: int = 25) -> dict:
    """Flatten the API response into a single, CSV-friendly row.

    Produces:
      - latitude/longitude from response center
      - imagery date (year/month/day)
      - sunshine + segment_count
      - For up to max_segments roof segments (sorted by area desc):
        azimuth{i}, areaSqMeters{i}, sunshineQuantiles{i} (JSON list, 11 values),
        quantileStats{i} (JSON dict with Max, Min, Avg),
        center{i} (JSON dict with lat/lon), boundingBox{i} (JSON dict with sw/ne)
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
        combined[f"sunshineQuantiles{i}"] = None
        combined[f"quantileStats{i}"] = None
        combined[f"center{i}"] = None
        combined[f"boundingBox{i}"] = None

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

        # Sunshine quantiles as JSON list (11 values from API)
        sunshine_quantiles = (stats.get("sunshineQuantiles") or [])[:11]
        if sunshine_quantiles:
            combined[f"sunshineQuantiles{i}"] = json.dumps(sunshine_quantiles)
            # Summary stats: Max, Min, Avg
            q_vals = [float(v) for v in sunshine_quantiles if v is not None]
            if q_vals:
                combined[f"quantileStats{i}"] = json.dumps({
                    "Max": round(max(q_vals), 2),
                    "Min": round(min(q_vals), 2),
                    "Avg": round(sum(q_vals) / len(q_vals), 2),
                })

        # Segment center as JSON dict {lat, lon}
        seg_center = seg.get("center") or {}
        c_lat, c_lon = seg_center.get("latitude"), seg_center.get("longitude")
        if c_lat is not None and c_lon is not None:
            combined[f"center{i}"] = json.dumps({"lat": c_lat, "lon": c_lon})

        # Bounding box as JSON dict {sw: {lat, lon}, ne: {lat, lon}}
        bbox = seg.get("boundingBox") or {}
        sw = bbox.get("sw") or {}
        ne = bbox.get("ne") or {}
        sw_lat, sw_lon = sw.get("latitude"), sw.get("longitude")
        ne_lat, ne_lon = ne.get("latitude"), ne.get("longitude")
        if any(x is not None for x in (sw_lat, sw_lon, ne_lat, ne_lon)):
            combined[f"boundingBox{i}"] = json.dumps({
                "sw": {"lat": sw_lat, "lon": sw_lon},
                "ne": {"lat": ne_lat, "lon": ne_lon},
            })

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


def fetch_with_retries(
    lat,
    lon,
    session,
    api_key,
    max_retries=5,
    max_segments: int = 25,
    max_distance_m: float = 15,
):
    delay = 1.0
    last_err = None

    for _ in range(max_retries):
        try:
            payload = get_building_insights(lat, lon, session, api_key)

            center = payload.get("center") or {}
            c_lat = center.get("latitude")
            c_lon = center.get("longitude")

            if c_lat is None or c_lon is None:
                return fetch_err("Missing building center", max_segments=max_segments)

            dist_m = haversine_m(lat, lon, c_lat, c_lon)

            if dist_m > max_distance_m:
                return fetch_err(
                    f"Closest building too far ({dist_m:.1f} m)",
                    max_segments=max_segments,
                )

            row = fetch_ok(payload, max_segments=max_segments)
            row["center_distance_m"] = dist_m
            return row
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
    checkpoint_every: int = 10,
    resume: bool = True,
    max_segments: int = 25,
    max_distance_m = 15,
    input_id_cols: list[str] = None,
    max_new_calls: int | None = None,
):
    """Run API calls sequentially and persist results incrementally.

    Inputs
    - subset: DataFrame that MUST contain columns 'lat' and 'lon' and may contain one or more ID/index columns (e.g. filtered_index, original_index). Optional columns 'mailadd', 'city', 'state2', 'area_building' are read and stored in the output; if present, they are used to retry via geocoding when the building is too far or roof area is below 80% of area_building (area_building in sq ft is converted to sq m for comparison with API areas).
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
    maps_api_key = os.getenv("GOOGLE_MAPS_API_KEY")

    file_exists = os.path.exists(csv_output)
    total_rows = len(subset)
    print(f"Starting run: output={csv_output}, rows={total_rows}, resume={resume}")

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
            *PASSTHROUGH_COLUMNS,
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
            "center_distance_m",
        ]
        for i in range(1, max_segments + 1):
            fieldnames.append(f"azimuth{i}")
            fieldnames.append(f"areaSqMeters{i}")
            fieldnames.append(f"sunshineQuantiles{i}")
            fieldnames.append(f"quantileStats{i}")
            fieldnames.append(f"center{i}")
            fieldnames.append(f"boundingBox{i}")

    # Build a set of already-processed (input_lat, input_lon) pairs so we can resume.
    processed = set()

    # Default ID columns if not provided (needed for resume + writing)
    if input_id_cols is None:
        input_id_cols = ["original_index"]
    if resume and os.path.exists(csv_output):
        try:
            with open(csv_output, "r", newline="", encoding="utf-8") as rf:
                reader = csv.DictReader(rf)
                for row in reader:
                    # Only skip successful rows — failed rows get retried
                    if row.get("ok", "").lower() != "true":
                        continue
                    in_ids = tuple(row.get(c) for c in input_id_cols)
                    processed.add((*in_ids, row.get("input_lat"), row.get("input_lon")))
        except Exception:
            processed = set()

    # Open in append mode; write header only if the file is new.
    with open(csv_output, "a", newline="", encoding="utf-8") as f, requests.Session() as session:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not os.path.exists(csv_output) or (os.path.getsize(csv_output) == 0):
            writer.writeheader()
            f.flush()

        written_since_flush = 0
        row_index = 0
        written_this_run = 0
        skipped_count = 0

        for _, r in subset.iterrows():
            row_index += 1
            in_lat, in_lon = r["lat"], r["lon"]
            in_ids = {col: r.get(col, None) for col in input_id_cols}
            row_label = f"row {row_index}/{total_rows} (idx={list(in_ids.values())[:1]})"

            # Skip rows already written to disk (resume mode)
            # Convert to strings to match csv.DictReader output in processed set
            if resume and (*(str(v) for v in in_ids.values()), str(in_lat), str(in_lon)) in processed:
                skipped_count += 1
                continue

            # Print skip summary when transitioning from skips to new calls
            if skipped_count > 0:
                print(f"  Skipped {skipped_count} already-processed rows")
                skipped_count = 0

            # Check limit on actual new API calls
            if max_new_calls is not None and written_this_run >= max_new_calls:
                print(f"  Reached --limit of {max_new_calls} new API calls, stopping")
                break

            print(f"  {row_label}: Calling Solar API (lat={in_lat}, lon={in_lon})...")
            result = fetch_with_retries(
                in_lat,
                in_lon,
                session,
                api_key,
                max_segments=max_segments,
                max_distance_m=max_distance_m
            )
            if result.get("ok"):
                print(f"  {row_label}: Solar API ok (center_distance_m={result.get('center_distance_m')}, segment_count={result.get('segment_count')})")
            else:
                print(f"  {row_label}: Solar API error: {result.get('error')}")

            # Optional retry via geocoded address if: "Closest building too far" or area shortfall
            area_building_raw = r.get("area_building")
            try:
                area_building = float(area_building_raw) if area_building_raw is not None and str(area_building_raw).strip() != "" else None
            except (TypeError, ValueError):
                area_building = None

            sum_area = sum_area_sq_meters(result, max_segments)
            # area_building is sq ft; convert to sq m for comparison with sum(areaSqMeters)
            area_building_sq_m = (area_building * SQFT_TO_SQM) if area_building is not None else None
            err_msg = (result.get("error") or "") if isinstance(result.get("error"), str) else ""
            is_too_far_error = not result.get("ok") and err_msg.startswith("Closest building too far")
            is_area_shortfall = result.get("ok") and area_building_sq_m is not None and sum_area < (area_building_sq_m * AREA_THRESHOLD)

            if (is_too_far_error or is_area_shortfall):
                reason = "Closest building too far" if is_too_far_error else f"area shortfall (sum={sum_area:.1f} m² < {area_building_sq_m * AREA_THRESHOLD:.1f} m² threshold)"
                print(f"  {row_label}: Retry trigger: {reason}")
                mailadd = (r.get("mailadd") or "")
                city = (r.get("city") or "")
                state2 = (r.get("state2") or "")
                if mailadd or city or state2:
                    # Format as "Street, City, State" for Geocoding API
                    address = ", ".join(str(x).strip() for x in [mailadd, city, state2] if x)
                    if not maps_api_key:
                        print(f"  {row_label}: GOOGLE_MAPS_API_KEY not set; skipping geocode retry")
                    else:
                        print(f"  {row_label}: Geocoding address: {address}")
                        geo_lat, geo_lon = get_lat_lon_from_address(address, session, maps_api_key)
                        if geo_lat is not None and geo_lon is not None:
                            print(f"  {row_label}: Geocode result: lat={geo_lat}, lon={geo_lon}")
                            time.sleep(0.2)  # brief pause before retry
                            result2 = fetch_with_retries(
                                geo_lat,
                                geo_lon,
                                session,
                                api_key,
                                max_segments=max_segments,
                                max_distance_m=max_distance_m,
                            )
                            sum_area2 = sum_area_sq_meters(result2, max_segments)
                            if result2.get("ok"):
                                if is_area_shortfall:
                                    if area_building_sq_m is not None and sum_area2 >= (area_building_sq_m * AREA_THRESHOLD):
                                        result = result2
                                        print(f"  {row_label}: Using retry result (area ok: sum={sum_area2:.1f})")
                                    else:
                                        print(f"  {row_label}: Retry ok but area still short (sum={sum_area2:.1f}); keeping original")
                                else:
                                    result = result2
                                    print(f"  {row_label}: Using retry result (building found)")
                            else:
                                print(f"  {row_label}: Retry Solar API error: {result2.get('error')}; keeping original result")
                        else:
                            print(f"  {row_label}: Geocode failed for address: {address}")
                else:
                    print(f"  {row_label}: No mailadd/city/state2; skipping geocode retry")

            out_row = {**in_ids, "input_lat": in_lat, "input_lon": in_lon, **result}
            for col in PASSTHROUGH_COLUMNS:
                if col in fieldnames:
                    out_row[col] = r.get(col, None)
            out_row = {k: out_row.get(k) for k in fieldnames}  # enforce schema

            writer.writerow(out_row)
            written_since_flush += 1
            written_this_run += 1
            processed.add((*in_ids.values(), in_lat, in_lon))
            print(f"  {row_label}: Wrote (ok={out_row.get('ok')})")

            # Periodically flush to disk so progress is durable
            if written_since_flush >= checkpoint_every:
                f.flush()
                print(f"  Flushed to disk ({written_since_flush} rows)")
                written_since_flush = 0

        if skipped_count > 0:
            print(f"  Skipped {skipped_count} already-processed rows")
        f.flush()
    print(f"Done. Wrote {written_this_run} new rows, skipped {len(processed)} existing. Output: {csv_output}")

    return written_this_run
