"""
Local web UI to view solar classification images (yes_solar / no_solar) in a grid.
Data from Boulder_CO_Regrid_joined_with_API.csv, sorted by solar_score (highest first).
Switch toggles solar_panels Yes|No and moves image; Reject/Promoted/Demoted update CSV.

Run: python src/view_solar_classifications.py
Then open http://127.0.0.1:5000 in your browser.

Requires: pip install flask pandas
"""

import re
import shutil
from pathlib import Path

import pandas as pd
from flask import Flask, jsonify, render_template, request, send_from_directory

app = Flask(__name__, template_folder="templates")

# Project root (parent of src/)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
YES_SOLAR_DIR = PROJECT_ROOT / "data" / "images" / "yes_solar"
NO_SOLAR_DIR = PROJECT_ROOT / "data" / "images" / "no_solar"
CSV_PATH = PROJECT_ROOT / "data" / "working" / "Boulder_CO_Regrid_joined_with_API.csv"
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp"}

# Match trailing number before extension, e.g. BOULDER_CO_14.png -> 14
INDEX_FROM_FILENAME = re.compile(r"_(\d+)\.[^.]+$", re.IGNORECASE)


def get_original_index_from_image_name(image_name: str) -> int | None:
    """Extract original_index from image filename (e.g. BOULDER_CO_14.png -> 14)."""
    m = INDEX_FROM_FILENAME.search(image_name)
    return int(m.group(1)) if m else None


def _ensure_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Ensure solar_panels and result_manual_check exist."""
    if "solar_panels" not in df.columns:
        df["solar_panels"] = ""
    if "result_manual_check" not in df.columns:
        df["result_manual_check"] = ""
    return df


def get_image_list() -> list[dict]:
    """
    Return list of images from both folders, with solar_score from CSV,
    sorted by solar_score descending. Each item: image_name, solar_score, folder, original_index.
    """
    if not CSV_PATH.exists():
        return []
    df = pd.read_csv(CSV_PATH)
    df = _ensure_columns(df)
    if "solar_score" not in df.columns:
        return []
    df["original_index"] = pd.to_numeric(df["original_index"], errors="coerce")

    # Collect (image_name, folder, original_index) from both folders
    entries = []
    for folder, base_dir in [("yes_solar", YES_SOLAR_DIR), ("no_solar", NO_SOLAR_DIR)]:
        if not base_dir.exists():
            continue
        for p in base_dir.iterdir():
            if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS:
                idx = get_original_index_from_image_name(p.name)
                if idx is not None:
                    entries.append((p.name, folder, int(idx)))

    # Build index -> (image_name, folder); if same index in both folders, prefer yes_solar
    index_to_info = {}
    for name, folder, idx in entries:
        if idx not in index_to_info:
            index_to_info[idx] = (name, folder)
        elif folder == "yes_solar":
            index_to_info[idx] = (name, folder)

    # Get scores and sort; skip rows already marked Ok so we only show unchecked images
    results = []
    for idx, (name, folder) in index_to_info.items():
        row = df.loc[df["original_index"] == idx]
        if row.empty:
            continue
        row = row.iloc[0]
        check_val = str(row.get("result_manual_check") or "").strip()
        if check_val.lower() == "ok":
            continue
        try:
            score = float(row.get("solar_score") or 0)
        except (TypeError, ValueError):
            score = 0.0
        try:
            lat = float(row.get("lat") or row.get("latitude") or 0)
        except (TypeError, ValueError):
            lat = None
        try:
            lon = float(row.get("lon") or row.get("longitude") or 0)
        except (TypeError, ValueError):
            lon = None
        results.append({
            "image_name": name,
            "solar_score": round(score, 4),
            "folder": folder,
            "original_index": idx,
            "lat": lat,
            "lon": lon,
        })
    results.sort(key=lambda x: (-x["solar_score"], x["original_index"]))
    return results


def update_csv_row(original_index: int, **kwargs) -> bool:
    """Update row(s) in CSV where original_index matches. Creates columns if needed."""
    if not CSV_PATH.exists():
        return False
    df = pd.read_csv(CSV_PATH)
    df = _ensure_columns(df)
    df["original_index"] = pd.to_numeric(df["original_index"], errors="coerce")
    mask = df["original_index"] == original_index
    if not mask.any():
        return False
    for col, val in kwargs.items():
        if col not in df.columns:
            df[col] = ""
        df.loc[mask, col] = val
    df.to_csv(CSV_PATH, index=False)
    return True


@app.route("/")
def index():
    folder = request.args.get("folder", "yes_solar")
    if folder not in ("yes_solar", "no_solar"):
        folder = "yes_solar"
    return render_template("view_solar.html", folder=folder)


@app.route("/api/images")
def api_images():
    folder = request.args.get("folder")
    items = get_image_list()
    if folder in ("yes_solar", "no_solar"):
        items = [x for x in items if x["folder"] == folder]
    return jsonify({"images": items, "folder": folder or "all"})


@app.route("/api/switch", methods=["POST"])
def api_switch():
    data = request.get_json() or {}
    image_name = data.get("image_name")
    from_folder = data.get("from_folder")
    if not image_name or from_folder not in ("yes_solar", "no_solar"):
        return jsonify({"ok": False, "error": "missing image_name or from_folder"}), 400

    original_index = get_original_index_from_image_name(image_name)
    if original_index is None:
        return jsonify({"ok": False, "error": "could not get original_index from image name"}), 400

    if from_folder == "yes_solar":
        src_dir, dest_dir = YES_SOLAR_DIR, NO_SOLAR_DIR
        new_solar_panels = "No"
    else:
        src_dir, dest_dir = NO_SOLAR_DIR, YES_SOLAR_DIR
        new_solar_panels = "Yes"

    src_path = src_dir / image_name
    if not src_path.is_file():
        return jsonify({"ok": False, "error": "file not found"}), 404

    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / image_name
    try:
        update_csv_row(
            original_index,
            solar_panels=new_solar_panels,
            result_manual_check="Switched",
        )
        shutil.move(str(src_path), str(dest_path))
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

    return jsonify({"ok": True, "image_name": image_name, "folder": "no_solar" if from_folder == "yes_solar" else "yes_solar"})


@app.route("/api/reject", methods=["POST"])
def api_reject():
    """Set result_manual_check to Rejected for this image; do not move the file."""
    data = request.get_json() or {}
    image_name = data.get("image_name")
    if not image_name:
        return jsonify({"ok": False, "error": "missing image_name"}), 400
    original_index = get_original_index_from_image_name(image_name)
    if original_index is None:
        return jsonify({"ok": False, "error": "could not get original_index from image name"}), 400
    try:
        update_csv_row(original_index, result_manual_check="Rejected")
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500
    return jsonify({"ok": True, "image_name": image_name})


@app.route("/api/ok", methods=["POST"])
def api_ok():
    """Set result_manual_check to Ok for this image; it will then be excluded from the list."""
    data = request.get_json() or {}
    image_name = data.get("image_name")
    if not image_name:
        return jsonify({"ok": False, "error": "missing image_name"}), 400
    original_index = get_original_index_from_image_name(image_name)
    if original_index is None:
        return jsonify({"ok": False, "error": "could not get original_index from image name"}), 400
    try:
        update_csv_row(original_index, result_manual_check="Ok")
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500
    return jsonify({"ok": True, "image_name": image_name})


@app.route("/api/promote", methods=["POST"])
def api_promote():
    """Increase solar_score by 10% for this image; return new score and updated list order."""
    data = request.get_json() or {}
    image_name = data.get("image_name")
    if not image_name:
        return jsonify({"ok": False, "error": "missing image_name"}), 400
    original_index = get_original_index_from_image_name(image_name)
    if original_index is None:
        return jsonify({"ok": False, "error": "could not get original_index from image name"}), 400
    if not CSV_PATH.exists():
        return jsonify({"ok": False, "error": "CSV not found"}), 500
    df = pd.read_csv(CSV_PATH)
    df = _ensure_columns(df)
    df["original_index"] = pd.to_numeric(df["original_index"], errors="coerce")
    mask = df["original_index"] == original_index
    if not mask.any():
        return jsonify({"ok": False, "error": "row not found"}), 404
    row = df.loc[mask].iloc[0]
    try:
        old_score = float(row.get("solar_score") or 0)
    except (TypeError, ValueError):
        old_score = 0.0
    new_score = round(old_score * 1.10, 4)
    df.loc[mask, "solar_score"] = new_score
    df.to_csv(CSV_PATH, index=False)
    return jsonify({"ok": True, "image_name": image_name, "solar_score": new_score})


@app.route("/api/demote", methods=["POST"])
def api_demote():
    """Decrease solar_score by 10% for this image; return new score."""
    data = request.get_json() or {}
    image_name = data.get("image_name")
    if not image_name:
        return jsonify({"ok": False, "error": "missing image_name"}), 400
    original_index = get_original_index_from_image_name(image_name)
    if original_index is None:
        return jsonify({"ok": False, "error": "could not get original_index from image name"}), 400
    if not CSV_PATH.exists():
        return jsonify({"ok": False, "error": "CSV not found"}), 500
    df = pd.read_csv(CSV_PATH)
    df = _ensure_columns(df)
    df["original_index"] = pd.to_numeric(df["original_index"], errors="coerce")
    mask = df["original_index"] == original_index
    if not mask.any():
        return jsonify({"ok": False, "error": "row not found"}), 404
    row = df.loc[mask].iloc[0]
    try:
        old_score = float(row.get("solar_score") or 0)
    except (TypeError, ValueError):
        old_score = 0.0
    new_score = round(old_score * 0.90, 4)
    df.loc[mask, "solar_score"] = new_score
    df.to_csv(CSV_PATH, index=False)
    return jsonify({"ok": True, "image_name": image_name, "solar_score": new_score})


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
