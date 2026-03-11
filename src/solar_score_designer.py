"""
Local web UI to view no_solar images sorted by solar score (highest first).

- Loads data from data/working/Boulder_CO_Filtered_API_Output.csv
- Lists images from data/images/no_solar (matched by original_index = last part of
  image name, e.g. BoulderCO_1014.png -> 1014)
- Refresh loads the latest CSV and sorts images by solar_score, highest to lowest.

Run: python src/solar_score_designer.py
Then open http://127.0.0.1:5001 in your browser.

Requires: pip install flask pandas
"""

import re
from pathlib import Path

import pandas as pd
from flask import Flask, jsonify, render_template, request, send_from_directory

from flask_auth import register_admin_auth

app = Flask(__name__, template_folder=Path(__file__).resolve().parent / "templates")
register_admin_auth(app)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CSV_PATH = PROJECT_ROOT / "data" / "working" / "Boulder_CO_Filtered_API_Output.csv"
NO_SOLAR_DIR = PROJECT_ROOT / "data" / "images" / "no_solar"
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp"}

# Match trailing number before extension, e.g. BoulderCO_1014.png -> 1014
INDEX_FROM_FILENAME = re.compile(r"_(\d+)\.[^.]+$", re.IGNORECASE)


def get_image_index(filename: str) -> int | None:
    """Extract original_index from image filename (e.g. BoulderCO_1014.png -> 1014)."""
    m = INDEX_FROM_FILENAME.search(filename)
    return int(m.group(1)) if m else None


def get_images_with_index() -> list[tuple[str, int]]:
    """Return list of (filename, original_index) for images in no_solar."""
    if not NO_SOLAR_DIR.exists():
        return []
    out = []
    for p in NO_SOLAR_DIR.iterdir():
        if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS:
            idx = get_image_index(p.name)
            if idx is not None:
                out.append((p.name, idx))
    return out


def load_data():
    """Load CSV and list of (image_name, original_index) for no_solar."""
    if not CSV_PATH.exists():
        return None, []
    df = pd.read_csv(CSV_PATH)
    images = get_images_with_index()
    return df, images


def get_sorted_results():
    """Load CSV and images, return list of {original_index, score, image_name} sorted by solar_score descending."""
    df, images = load_data()
    if df is None:
        return None, f"CSV not found: {CSV_PATH}"

    index_to_image = {idx: name for name, idx in images}
    df_by_index = df.set_index("original_index")
    if "solar_score" not in df.columns:
        return None, "CSV has no 'solar_score' column"

    def _to_json_val(v, default=""):
        """Convert a pandas/CSV value to a JSON-serializable Python type."""
        if v is None or (isinstance(v, float) and pd.isna(v)):
            return default
        if hasattr(v, "item"):  # numpy scalar
            try:
                return v.item()
            except (ValueError, AttributeError):
                pass
        if isinstance(v, (int, float, str, bool)):
            return v
        return str(v)

    results = []
    for orig_index in index_to_image:
        if orig_index not in df_by_index.index:
            continue
        row = df_by_index.loc[orig_index]
        try:
            score = float(row.get("solar_score") or 0)
        except (TypeError, ValueError):
            score = 0.0
        results.append(
            {
                "original_index": int(orig_index),
                "score": round(score, 4),
                "image_name": index_to_image[orig_index],
                "sunshine": _to_json_val(row.get("sunshine")),
                "segment_count": _to_json_val(row.get("segment_count")),
                "roof_orientation": _to_json_val(row.get("roof_orientation")),
                "matching_segment_count": _to_json_val(row.get("matching_segment_count")),
                "matching_segments": _to_json_val(row.get("matching_segments")),
            }
        )

    results.sort(key=lambda x: (-x["score"], x["original_index"]))
    return results, None


@app.route("/")
def index():
    return render_template("solar_score_designer.html")


@app.route("/api/refresh")
def api_refresh():
    """Load latest CSV and return images sorted by solar_score (highest first)."""
    try:
        results, error = get_sorted_results()
        if error:
            return jsonify({"ok": False, "error": error}), 404
        return jsonify({"ok": True, "results": results})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/images/no_solar/<path:filename>")
def serve_image(filename: str):
    return send_from_directory(NO_SOLAR_DIR, filename)


if __name__ == "__main__":
    print("Solar Score Designer: open http://127.0.0.1:5001 in your browser.")
    app.run(host="127.0.0.1", port=5001, debug=True)
