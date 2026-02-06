"""
Analyze satellite images with OpenAI Vision to classify:
- Solar panels present (Yes/No) + confidence
- Apparent roof condition (Good/Poor/Unknown) + confidence
- Overall image quality (Good/Blurry/Other) + confidence

Reads images from:  data/images/unprocessed
Moves each to:      data/images/yes_solar  or  data/images/no_solar
Merges results into:  data/working/Boulder_CO_Regrid_joined_with_API.csv
  (matches rows by original_index; only updates rows for images processed this run)

Requires: OPEN_AI_API_KEY environment variable.
Install:  pip install openai pandas
"""

from __future__ import annotations

import base64
import json
import os
import re
import shutil
import time
from pathlib import Path

import pandas as pd
from openai import APIStatusError, OpenAI

# --- Configuration ---
IMAGES_DIR = "data/images/unprocessed"
YES_SOLAR_DIR = "data/images/yes_solar"
NO_SOLAR_DIR = "data/images/no_solar"
MERGE_TARGET_CSV = "data/working/Boulder_CO_Regrid_joined_with_API.csv"
MAX_IMAGES = None  # Set to an integer (e.g. 5) to limit for testing; None = no limit

# Classification columns added/updated in the merge target (by original_index)
CLASSIFICATION_COLUMNS = [
    "image_name",
    "solar",
    "solar_confidence",
    "roof_condition",
    "roof_confidence",
    "image_quality",
    "image_quality_confidence",
]

# Rate limiting: delay between requests (seconds) to stay under TPM; retries on 429
REQUEST_DELAY = 1.0  # ~60 req/min; increase if you still hit limits
MAX_RETRIES = 8  # exponential backoff attempts on rate limit
RETRY_BASE_SECONDS = 2.0  # first wait 2s, then 4s, 8s, ...

# Supported image extensions
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp"}

PROMPT = """
Look at the home in the center of this image.

Determine:
- Whether solar panels are installed on the roof
- The apparent roof condition from overhead imagery
- The overall image quality

Respond with ONLY valid JSON matching this exact schema:

{
  "solar": "Yes|No",
  "solar_confidence": 0.0,
  "roof_condition": "Good|Poor|Unknown",
  "roof_confidence": 0.0,
  "image_quality": "Good|Blurry|Other",
  "image_quality_confidence": 0.0
}

Rules:
- Use Unknown when the image does not clearly support a determination (roof condition only)
- Confidence values must be floats between 0 and 1
- Do not include any text outside the JSON
""".strip()


def get_api_key() -> str:
    key = os.getenv("OPEN_AI_API_KEY")
    if not key:
        raise SystemExit(
            "OpenAI API key not found. Set OPEN_AI_API_KEY "
            "(and export it in your shell config so this script can see it)."
        )
    return key


def encode_image(path: Path) -> str:
    with open(path, "rb") as f:
        return base64.standard_b64encode(f.read()).decode("utf-8")


def get_original_index_from_image_name(image_path: Path) -> int | None:
    """Derive original_index from image filename (e.g. BOULDER_CO_42.png -> 42)."""
    stem = image_path.stem
    parts = stem.split("_")
    if parts:
        try:
            return int(parts[-1])
        except ValueError:
            pass
    match = re.search(r"\d+", image_path.name)
    if match:
        return int(match.group(0))
    return None


def get_mime_type(path: Path) -> str:
    ext = path.suffix.lower()
    mime = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".webp": "image/webp",
    }
    return mime.get(ext, "image/png")


def _parse_retry_after_ms(error_message: str) -> float | None:
    """If the API says 'try again in Xms', return X as seconds else None."""
    match = re.search(r"try again in (\d+)ms", error_message or "", re.IGNORECASE)
    if match:
        return max(0.5, int(match.group(1)) / 1000.0)
    return None


def parse_json_response(text: str) -> dict:
    """
    Parse the model response into a normalized dict with guaranteed keys/values.
    Falls back safely if parsing/validation fails.
    """
    defaults = {
        "solar": "No",
        "solar_confidence": 0.0,
        "roof_condition": "Unknown",
        "roof_confidence": 0.0,
        "image_quality": "Other",
        "image_quality_confidence": 0.0,
    }

    if not text or not text.strip():
        return defaults.copy()

    # Some models occasionally wrap JSON in code fences—strip if present.
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned)

    try:
        data = json.loads(cleaned)

        # Validate categorical fields
        solar = data.get("solar", defaults["solar"])
        solar = str(solar).strip()
        if solar not in {"Yes", "No"}:
            solar = defaults["solar"]

        roof_condition = data.get("roof_condition", defaults["roof_condition"])
        roof_condition = str(roof_condition).strip()
        if roof_condition not in {"Good", "Poor", "Unknown"}:
            roof_condition = defaults["roof_condition"]

        image_quality = data.get("image_quality", defaults["image_quality"])
        image_quality = str(image_quality).strip()
        if image_quality not in {"Good", "Blurry", "Other"}:
            image_quality = defaults["image_quality"]

        # Validate numeric confidences
        def _clamp01(x) -> float:
            try:
                v = float(x)
                return min(max(v, 0.0), 1.0)
            except Exception:
                return 0.0

        out = {
            "solar": solar,
            "solar_confidence": _clamp01(data.get("solar_confidence", 0.0)),
            "roof_condition": roof_condition,
            "roof_confidence": _clamp01(data.get("roof_confidence", 0.0)),
            "image_quality": image_quality,
            "image_quality_confidence": _clamp01(data.get("image_quality_confidence", 0.0)),
        }
        return out

    except Exception:
        return defaults.copy()


def analyze_image(client: OpenAI, image_path: Path) -> dict:
    b64 = encode_image(image_path)
    mime = get_mime_type(image_path)
    data_uri = f"data:{mime};base64,{b64}"

    last_error = None
    for attempt in range(MAX_RETRIES):
        try:
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": PROMPT},
                            {"type": "image_url", "image_url": {"url": data_uri}},
                        ],
                    }
                ],
                max_tokens=200,
            )

            raw = (response.choices[0].message.content or "").strip()
            return parse_json_response(raw)

        except APIStatusError as e:
            last_error = e
            if e.status_code != 429:
                raise
            msg = str(getattr(e, "body", e))
            wait = _parse_retry_after_ms(msg) or (RETRY_BASE_SECONDS ** attempt)
            wait = min(wait, 60.0)  # cap at 60s
            if attempt < MAX_RETRIES - 1:
                print(f" rate limited, retry in {wait:.1f}s...", end=" ", flush=True)
                time.sleep(wait)
            else:
                raise

    assert last_error is not None
    raise last_error


def main() -> None:
    project_root = Path(__file__).resolve().parent.parent
    images_dir = project_root / IMAGES_DIR
    yes_dir = project_root / YES_SOLAR_DIR
    no_dir = project_root / NO_SOLAR_DIR
    merge_path = project_root / MERGE_TARGET_CSV

    if not images_dir.exists():
        raise SystemExit(f"Images directory not found: {images_dir}")
    if not merge_path.exists():
        raise SystemExit(
            f"Merge target CSV not found: {merge_path}. "
            "Required for iterative merge by original_index."
        )

    image_paths = sorted(
        p for p in images_dir.iterdir()
        if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS
    )

    if not image_paths:
        raise SystemExit(f"No images found in {images_dir}")

    if MAX_IMAGES is not None:
        image_paths = image_paths[:MAX_IMAGES]
        print(f"Limited to {MAX_IMAGES} images for testing.")

    total = len(image_paths)
    print(f"Analyzing {total} images...")

    yes_dir.mkdir(parents=True, exist_ok=True)
    no_dir.mkdir(parents=True, exist_ok=True)

    api_key = get_api_key()
    client = OpenAI(api_key=api_key)

    rows: list[dict] = []
    for i, path in enumerate(image_paths, 1):
        name = path.name
        print(f"[{i}/{total}] {name}...", end=" ", flush=True)

        try:
            result = analyze_image(client, path)

            dest_dir = yes_dir if result["solar"] == "Yes" else no_dir
            dest = dest_dir / name
            shutil.move(str(path), str(dest))

            original_index = get_original_index_from_image_name(path)
            if original_index is None:
                original_index = i - 1
            rows.append({
                "original_index": original_index,
                "image_name": name,
                **result,
            })

            print(
                f'{result["solar"]} (c={result["solar_confidence"]:.2f}) | '
                f'Roof:{result["roof_condition"]} (c={result["roof_confidence"]:.2f}) | '
                f'Img:{result["image_quality"]} (c={result["image_quality_confidence"]:.2f})'
            )

            if i < total and REQUEST_DELAY > 0:
                time.sleep(REQUEST_DELAY)

        except Exception as e:
            print(f"ERROR: {e}")
            original_index = get_original_index_from_image_name(path)
            if original_index is None:
                original_index = i - 1
            rows.append({
                "original_index": original_index,
                "image_name": name,
                "solar": "",
                "solar_confidence": "",
                "roof_condition": "",
                "roof_confidence": "",
                "image_quality": "",
                "image_quality_confidence": "",
            })

    if not rows:
        print("Done. No rows to merge.")
        return

    # Load merge target and ensure original_index is comparable (int)
    df_master = pd.read_csv(merge_path)
    if "original_index" not in df_master.columns:
        raise SystemExit(
            f"Merge target {merge_path} must have column 'original_index'."
        )
    # Normalize original_index for matching (int; CSV may have read as float)
    df_master["original_index"] = pd.to_numeric(
        df_master["original_index"], errors="coerce"
    )
    df_master["original_index"] = df_master["original_index"].astype("Int64")

    # Add classification columns if missing (leave existing values for other rows)
    for col in CLASSIFICATION_COLUMNS:
        if col not in df_master.columns:
            df_master[col] = pd.NA

    # Update only rows whose original_index we processed this run
    df_new = pd.DataFrame(rows)
    for _, r in df_new.iterrows():
        idx = int(r["original_index"])
        mask = df_master["original_index"] == idx
        if not mask.any():
            print(f"  Warning: original_index {idx} not found in merge target, skipping.")
            continue
        for col in CLASSIFICATION_COLUMNS:
            if col in r:
                df_master.loc[mask, col] = r[col]

    df_master.to_csv(merge_path, index=False)
    print(
        f"Done. Merged {len(rows)} results into {merge_path} "
        f"(updated rows for original_index: {sorted(df_new['original_index'].tolist())})"
    )


if __name__ == "__main__":
    main()
