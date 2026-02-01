"""
Analyze satellite images with OpenAI Vision API to classify whether the home
has solar panels on the roof. Reads images from data/images and writes
results to a CSV (image name + Yes/No classifier).

Requires: OPEN_AI_API_KEY environment variable.
Install: pip install openai
"""

import base64
import os
from pathlib import Path

import pandas as pd
from openai import OpenAI

# --- Configuration ---
IMAGES_DIR = "data/images"
OUTPUT_CSV = "data/working/solar_panel_classifications.csv"
MAX_IMAGES = None  # Set to an integer (e.g. 5) to limit for testing; None = no limit

# Supported image extensions (from download_map_images.py output)
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp"}

PROMPT = (
    "Look at the home in the center of this image. Determine whether or not "
    "it has solar panels installed on the roof. Be careful not to confuse a "
    "skylight for a solar panel. Respond with only: Yes or No"
)


def get_api_key() -> str:
    key = os.getenv("OPEN_AI_API_KEY")
    if not key:
        raise SystemExit(
            "OPEN_AI_API_KEY environment variable is not set. "
            "Set it before running this script."
        )
    return key


def encode_image(path: Path) -> str:
    with open(path, "rb") as f:
        return base64.standard_b64encode(f.read()).decode("utf-8")


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


def parse_yes_no(response_text: str) -> str:
    """Normalize model response to 'Yes' or 'No'."""
    if not response_text:
        return "No"
    text = response_text.strip().lower()
    if text.startswith("yes"):
        return "Yes"
    if text.startswith("no"):
        return "No"
    # Fallback: look for yes/no anywhere
    if "yes" in text and "no" not in text:
        return "Yes"
    if "no" in text:
        return "No"
    return "No"


def analyze_image(client: OpenAI, image_path: Path) -> str:
    b64 = encode_image(image_path)
    mime = get_mime_type(image_path)
    data_uri = f"data:{mime};base64,{b64}"

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": PROMPT},
                    {
                        "type": "image_url",
                        "image_url": {"url": data_uri},
                    },
                ],
            }
        ],
        max_tokens=10,
    )
    raw = (response.choices[0].message.content or "").strip()
    return parse_yes_no(raw)


def main() -> None:
    project_root = Path(__file__).resolve().parent.parent
    images_dir = project_root / IMAGES_DIR
    output_path = project_root / OUTPUT_CSV

    if not images_dir.exists():
        raise SystemExit(f"Images directory not found: {images_dir}")

    image_paths = sorted(
        p for p in images_dir.iterdir()
        if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS
    )

    if not image_paths:
        raise SystemExit(f"No images found in {images_dir}")

    limit = MAX_IMAGES
    if limit is not None:
        image_paths = image_paths[:limit]
        print(f"Limited to {limit} images for testing.")
    total = len(image_paths)
    print(f"Analyzing {total} images...")

    api_key = get_api_key()
    client = OpenAI(api_key=api_key)

    rows = []
    for i, path in enumerate(image_paths, 1):
        name = path.name
        print(f"[{i}/{total}] {name}...", end=" ", flush=True)
        try:
            classifier = analyze_image(client, path)
            rows.append({"image_name": name, "has_solar_panels": classifier})
            print(classifier)
        except Exception as e:
            print(f"ERROR: {e}")
            rows.append({"image_name": name, "has_solar_panels": ""})

    output_path.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(rows)
    df.to_csv(output_path, index=False)
    print(f"Done. Wrote {len(rows)} rows to {output_path}")


if __name__ == "__main__":
    main()
