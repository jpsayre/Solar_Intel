"""
Marker-image classifier (OpenAI Vision)

- Reads marker images (e.g., {original_index}_marker.png) from MARKER_IMAGES_DIR
- Calls OpenAI Vision and extracts solar_panels = Yes/No
- Writes/updates: data/working/image_classification_tests.csv
  Adds/updates columns: original_index, image_name, marker (Yes/No), bbox (kept if exists)

Does NOT move any files.

Requires: OPEN_AI_API_KEY environment variable.
Install:  pip install openai pandas
"""

from __future__ import annotations

import base64
import json
import os
import random
import re
import time
from pathlib import Path

import pandas as pd
from openai import APIConnectionError, APIStatusError, APITimeoutError, OpenAI, RateLimitError

# --------------------
# Configuration
# --------------------

# Where your marker images were saved by your downloader script
MARKER_IMAGES_DIR = "data/images/test/marker"

OUTPUT_CSV = "data/working/image_classification_tests.csv"

MAX_IMAGES = 200  # int for testing; None = no limit

REQUEST_DELAY = 2.5  # delay between images to avoid rate limits
MAX_RETRIES = 10
RETRY_BASE_SECONDS = 2.0
MIN_RATE_LIMIT_WAIT = 2.0  # never wait less than this on 429 (avoids rapid re-hits)
RETRY_JITTER_MAX = 1.5  # add up to this many seconds random jitter to retry waits
API_TIMEOUT_SECONDS = 90.0

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp"}

PROMPT_MARKER = """
Look at the home indicated by the red marker, consider this home only (and its detached garage if it has one).
Ignore other homes.
Baseline assumption: No solar panels unless you are extremely confident.

Task:
- Determine whether solar panels are installed on the home.

Respond with ONLY valid JSON in this exact schema:
{
  "solar_panels": "Yes|No",
  "solar_confidence": 0.0
}

Rules:
- solar_panels must be "Yes" or "No"
- solar_confidence must be a float 0..1
- No text outside JSON
""".strip()


# --------------------
# Helpers
# --------------------

def get_api_key() -> str:
    key = os.getenv("OPEN_AI_API_KEY")
    if not key:
        raise SystemExit("OPEN_AI_API_KEY environment variable is not set")
    return key


def encode_image(path: Path) -> str:
    return base64.standard_b64encode(path.read_bytes()).decode("utf-8")


def get_mime_type(path: Path) -> str:
    ext = path.suffix.lower()
    return {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".webp": "image/webp",
    }.get(ext, "image/png")


def parse_json_response(text: str) -> dict:
    defaults = {"solar_panels": "No", "solar_confidence": 0.0}

    if not text or not text.strip():
        return defaults.copy()

    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned)

    try:
        data = json.loads(cleaned)
        solar = str(data.get("solar_panels", "No")).strip()
        if solar not in {"Yes", "No"}:
            solar = "No"

        def clamp01(x) -> float:
            try:
                v = float(x)
                return min(max(v, 0.0), 1.0)
            except Exception:
                return 0.0

        return {"solar_panels": solar, "solar_confidence": clamp01(data.get("solar_confidence", 0.0))}
    except Exception:
        return defaults.copy()


def _parse_retry_after_ms(error_message: str) -> float | None:
    match = re.search(r"try again in (\d+)ms", error_message or "", re.IGNORECASE)
    if match:
        return max(MIN_RATE_LIMIT_WAIT, int(match.group(1)) / 1000.0)
    return None


def _retry_wait(attempt: int, is_rate_limit: bool = False, parsed_wait: float | None = None) -> float:
    """Compute wait time with exponential backoff and jitter. Returns seconds."""
    if is_rate_limit and parsed_wait is not None:
        base = max(MIN_RATE_LIMIT_WAIT, parsed_wait)
    else:
        base = RETRY_BASE_SECONDS ** attempt
    wait = min(float(base), 60.0)
    jitter = random.uniform(0, RETRY_JITTER_MAX)
    return wait + jitter


def get_original_index_from_marker_filename(p: Path) -> int | None:
    """
    Expect filenames like:
      10657_marker.png
    but also tries to find any digits.
    """
    stem = p.stem  # e.g. "10657_marker"
    m = re.match(r"^(\d+)_marker$", stem)
    if m:
        return int(m.group(1))
    m2 = re.search(r"\d+", p.name)
    return int(m2.group(0)) if m2 else None


def analyze_image(client: OpenAI, image_path: Path) -> dict:
    b64 = encode_image(image_path)
    mime = get_mime_type(image_path)
    data_uri = f"data:{mime};base64,{b64}"

    last_error = None
    for attempt in range(MAX_RETRIES):
        try:
            resp = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": PROMPT_MARKER},
                            {"type": "image_url", "image_url": {"url": data_uri}},
                        ],
                    }
                ],
                max_tokens=120,
                timeout=API_TIMEOUT_SECONDS,
            )
            raw = (resp.choices[0].message.content or "").strip()
            return parse_json_response(raw)

        except (APIStatusError, RateLimitError) as e:
            last_error = e
            is_429 = isinstance(e, RateLimitError) or (isinstance(e, APIStatusError) and getattr(e, "status_code", None) == 429)
            if not is_429:
                raise
            msg = str(getattr(e, "body", e) or e)
            parsed = _parse_retry_after_ms(msg)
            wait = _retry_wait(attempt, is_rate_limit=True, parsed_wait=parsed)
            if attempt < MAX_RETRIES - 1:
                print(f" rate limited, retry {attempt + 1}/{MAX_RETRIES} in {wait:.1f}s...", end=" ", flush=True)
                time.sleep(wait)
            else:
                raise

        except (APIConnectionError, APITimeoutError, TimeoutError, ConnectionError, OSError) as e:
            last_error = e
            wait = _retry_wait(attempt, is_rate_limit=False)
            if attempt < MAX_RETRIES - 1:
                print(f" connection/timeout error, retry {attempt + 1}/{MAX_RETRIES} in {wait:.1f}s...", end=" ", flush=True)
                time.sleep(wait)
            else:
                raise

    assert last_error is not None
    raise last_error


def upsert_results(output_csv: Path, rows: list[dict]) -> None:
    """
    rows: [{original_index:int, image_name:str, marker:"Yes|No"}]
    Ensures output has columns: original_index, image_name, bbox, marker
    """
    if output_csv.exists():
        df = pd.read_csv(output_csv)
    else:
        df = pd.DataFrame(columns=["original_index", "image_name", "bbox", "marker"])

    for col in ["original_index", "image_name", "bbox", "marker"]:
        if col not in df.columns:
            df[col] = pd.NA

    # Make sure original_index is numeric
    df["original_index"] = pd.to_numeric(df["original_index"], errors="coerce")

    new_df = pd.DataFrame(rows)
    new_df["original_index"] = pd.to_numeric(new_df["original_index"], errors="coerce")

    # Outer merge then prefer new marker values
    merged = df.merge(new_df, on="original_index", how="outer", suffixes=("", "_new"))

    # image_name: prefer existing, else new
    if "image_name_new" in merged.columns:
        merged["image_name"] = merged["image_name"].combine_first(merged["image_name_new"])
        merged.drop(columns=["image_name_new"], inplace=True)

    # marker: always take new if present
    if "marker_new" in merged.columns:
        merged["marker"] = merged["marker_new"].combine_first(merged["marker"])
        merged.drop(columns=["marker_new"], inplace=True)

    # Ensure bbox column exists even if not used in this run
    if "bbox" not in merged.columns:
        merged["bbox"] = pd.NA

    merged = merged[["original_index", "image_name", "bbox", "marker"]].sort_values("original_index")
    merged.to_csv(output_csv, index=False)


# --------------------
# Main
# --------------------

def main() -> None:
    project_root = Path(__file__).resolve().parent.parent
    images_dir = project_root / MARKER_IMAGES_DIR
    output_csv = project_root / OUTPUT_CSV
    output_csv.parent.mkdir(parents=True, exist_ok=True)

    if not images_dir.exists():
        raise SystemExit(f"Marker images dir not found: {images_dir}")

    paths = [
        p for p in images_dir.iterdir()
        if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS
    ]

    work: list[tuple[int, Path]] = []
    for p in paths:
        idx = get_original_index_from_marker_filename(p)
        if idx is not None:
            work.append((idx, p))

    if not work:
        print("No marker images found to process.")
        return

    work.sort(key=lambda x: x[0])
    if MAX_IMAGES is not None:
        work = work[:MAX_IMAGES]
        print(f"Limited to {MAX_IMAGES} images for testing.")

    api_key = get_api_key()
    client = OpenAI(api_key=api_key, timeout=API_TIMEOUT_SECONDS)

    rows_out: list[dict] = []
    total = len(work)
    for i, (idx, path) in enumerate(work, 1):
        print(f"[{i}/{total}] {path.name}...", end=" ", flush=True)
        try:
            result = analyze_image(client, path)
            solar = result["solar_panels"]
            rows_out.append({"original_index": idx, "image_name": path.name, "marker": solar})
            print(f"marker={solar} (c={result['solar_confidence']:.2f})")
        except Exception as e:
            rows_out.append({"original_index": idx, "image_name": path.name, "marker": pd.NA})
            print(f"ERROR: {e}")

        if i < total and REQUEST_DELAY > 0:
            time.sleep(REQUEST_DELAY)

    upsert_results(output_csv, rows_out)
    print(f"Done. Wrote/updated {output_csv} (updated marker for {len(rows_out)} rows).")


if __name__ == "__main__":
    main()
