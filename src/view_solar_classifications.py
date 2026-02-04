"""
Local web UI to view solar classification images (yes_solar / no_solar) in a grid.
Switch button moves an image to the other folder and marks 'switched' in the CSV.

Run: python src/view_solar_classifications.py
Then open http://127.0.0.1:5000 in your browser.

Requires: pip install flask pandas
"""

import shutil
from pathlib import Path

import pandas as pd
from flask import Flask, jsonify, render_template, request, send_from_directory

app = Flask(__name__, template_folder="templates")

# Project root (parent of src/)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
YES_SOLAR_DIR = PROJECT_ROOT / "data" / "images" / "yes_solar"
NO_SOLAR_DIR = PROJECT_ROOT / "data" / "images" / "no_solar"
CSV_PATH = PROJECT_ROOT / "data" / "working" / "solar_panel_classifications.csv"
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp"}


def get_image_list(folder: str) -> list[str]:
    """Return sorted list of image filenames in the given folder (yes_solar or no_solar)."""
    if folder == "yes_solar":
        base = YES_SOLAR_DIR
    else:
        base = NO_SOLAR_DIR
    if not base.exists():
        return []
    return sorted(
        p.name
        for p in base.iterdir()
        if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS
    )


def update_csv_visual_check(image_name: str, value: str = "switched") -> None:
    """Set visual_check to value for the row where image_name matches; add column if needed."""
    if not CSV_PATH.exists():
        return
    df = pd.read_csv(CSV_PATH)
    if "visual_check" not in df.columns:
        df["visual_check"] = ""
    mask = df["image_name"] == image_name
    if mask.any():
        df.loc[mask, "visual_check"] = value
    else:
        # Append a row so the CSV stays a record of visually switched images
        other_folder = "no_solar"  # arbitrary; we don't have classification here
        new_row = {"image_name": image_name, "classification": "", "visual_check": value}
        if "index" in df.columns:
            new_row["index"] = len(df)
        df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
    df.to_csv(CSV_PATH, index=False)


@app.route("/")
def index():
    folder = request.args.get("folder", "yes_solar")
    if folder not in ("yes_solar", "no_solar"):
        folder = "yes_solar"
    return render_template("view_solar.html", folder=folder)


@app.route("/api/images")
def api_images():
    folder = request.args.get("folder", "yes_solar")
    if folder not in ("yes_solar", "no_solar"):
        folder = "yes_solar"
    names = get_image_list(folder)
    return jsonify({"folder": folder, "images": names})


@app.route("/api/switch", methods=["POST"])
def api_switch():
    data = request.get_json() or {}
    image_name = data.get("image_name")
    from_folder = data.get("from_folder")
    if not image_name or from_folder not in ("yes_solar", "no_solar"):
        return jsonify({"ok": False, "error": "missing image_name or from_folder"}), 400

    if from_folder == "yes_solar":
        src_dir, dest_dir = YES_SOLAR_DIR, NO_SOLAR_DIR
    else:
        src_dir, dest_dir = NO_SOLAR_DIR, YES_SOLAR_DIR

    src_path = src_dir / image_name
    if not src_path.is_file():
        return jsonify({"ok": False, "error": "file not found"}), 404

    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / image_name
    try:
        update_csv_visual_check(image_name, "switched")
        shutil.move(str(src_path), str(dest_path))
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

    return jsonify({"ok": True, "image_name": image_name})


@app.route("/api/reject", methods=["POST"])
def api_reject():
    """Write 'rejected' in visual_check for this image; do not move the file."""
    data = request.get_json() or {}
    image_name = data.get("image_name")
    if not image_name:
        return jsonify({"ok": False, "error": "missing image_name"}), 400
    try:
        update_csv_visual_check(image_name, "rejected")
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500
    return jsonify({"ok": True, "image_name": image_name})


@app.route("/images/<folder>/<path:filename>")
def serve_image(folder: str, filename: str):
    if folder == "yes_solar":
        directory = YES_SOLAR_DIR
    elif folder == "no_solar":
        directory = NO_SOLAR_DIR
    else:
        return "", 404
    return send_from_directory(directory, filename)


if __name__ == "__main__":
    print("Open http://127.0.0.1:5000 in your browser.")
    app.run(host="127.0.0.1", port=5000, debug=True)
