"""
Local web UI to view permit yes_solar images across unprocessed, no_solar, yes_solar folders.
Image list from data/working/permit_yes_solar.csv. Searches all three folders for each image.

Run: python src/view_solar_classifications_permit.py
Then open http://127.0.0.1:5001 in your browser.

Requires: pip install flask
"""

import shutil
from pathlib import Path

from flask import Flask, jsonify, render_template, request, send_from_directory

app = Flask(__name__, template_folder="templates")

# Project root (parent of src/)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
IMAGE_DIRS = {
    "unprocessed": PROJECT_ROOT / "data" / "images" / "unprocessed",
    "no_solar": PROJECT_ROOT / "data" / "images" / "no_solar",
    "yes_solar": PROJECT_ROOT / "data" / "images" / "yes_solar",
}
PERMIT_CSV_PATH = PROJECT_ROOT / "data" / "working" / "permit_yes_solar.csv"
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp"}


def _load_permit_filenames() -> list[str]:
    """Load list of image filenames from permit_yes_solar.csv (one per line, no header)."""
    if not PERMIT_CSV_PATH.exists():
        return []
    text = PERMIT_CSV_PATH.read_text(encoding="utf-8-sig").strip()
    lines = text.splitlines()
    return [line.strip() for line in lines if line.strip()]


def _build_folder_lookup() -> dict[str, tuple[str, Path]]:
    """
    Build lowercase filename -> (actual_filename, folder) for all images in the three folders.
    Handles case-insensitive matching (e.g. BOULDER_CO_1.PNG matches BOULDER_CO_1.png).
    """
    lookup: dict[str, tuple[str, Path]] = {}
    for folder, base_dir in IMAGE_DIRS.items():
        if not base_dir.exists():
            continue
        for p in base_dir.iterdir():
            if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS:
                key = p.name.lower()
                if key not in lookup:
                    lookup[key] = (p.name, base_dir)
    return lookup


def get_image_list() -> list[dict]:
    """
    Return list of images from permit_yes_solar.csv that exist in unprocessed, no_solar, or yes_solar.
    Preserves CSV order. Each item: image_name, folder, image_index, total_images.
    """
    permit_names = _load_permit_filenames()
    if not permit_names:
        return []
    lookup = _build_folder_lookup()
    results = []
    for name_in_csv in permit_names:
        key = name_in_csv.lower()
        if key not in lookup:
            continue
        actual_name, base_dir = lookup[key]
        folder = base_dir.name
        results.append({
            "image_name": actual_name,
            "folder": folder,
        })
    n = len(results)
    for i, r in enumerate(results):
        r["image_index"] = i + 1
        r["total_images"] = n
    return results


@app.route("/")
def index():
    return render_template("view_solar_permit.html")


@app.route("/api/images")
def api_images():
    page = max(1, int(request.args.get("page", 1)))
    per_page = min(2000, max(1, int(request.args.get("per_page", 1000))))
    items = get_image_list()
    total_count = len(items)
    start = (page - 1) * per_page
    page_items = items[start : start + per_page]
    for i, item in enumerate(page_items):
        item["image_index"] = start + i + 1
        item["total_images"] = total_count
    return jsonify({
        "images": page_items,
        "total_count": total_count,
        "page": page,
        "per_page": per_page,
    })


@app.route("/api/switch", methods=["POST"])
def api_switch():
    """Move image from one folder to another (yes_solar <-> no_solar <-> unprocessed)."""
    data = request.get_json() or {}
    image_name = data.get("image_name")
    from_folder = data.get("from_folder")
    to_folder = data.get("to_folder")
    if not image_name or from_folder not in IMAGE_DIRS:
        return jsonify({"ok": False, "error": "missing image_name or from_folder"}), 400
    if to_folder and to_folder not in IMAGE_DIRS:
        return jsonify({"ok": False, "error": "invalid to_folder"}), 400

    src_dir = IMAGE_DIRS[from_folder]
    if not src_dir.exists():
        return jsonify({"ok": False, "error": "source folder not found"}), 500

    # Find actual file (case-insensitive)
    src_path = None
    for p in src_dir.iterdir():
        if p.is_file() and p.name.lower() == image_name.lower():
            src_path = p
            break
    if not src_path or not src_path.is_file():
        return jsonify({"ok": False, "error": "file not found"}), 404

    # Default: yes_solar <-> no_solar swap
    if not to_folder:
        to_folder = "no_solar" if from_folder == "yes_solar" else "yes_solar"
    dest_dir = IMAGE_DIRS[to_folder]
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / src_path.name
    try:
        shutil.move(str(src_path), str(dest_path))
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500
    return jsonify({"ok": True, "image_name": src_path.name, "folder": to_folder})


@app.route("/images/<folder>/<path:filename>")
def serve_image(folder: str, filename: str):
    if folder not in IMAGE_DIRS:
        return "", 404
    directory = IMAGE_DIRS[folder]
    if not directory.exists():
        return "", 404
    # Serve with case-insensitive filename match
    for p in directory.iterdir():
        if p.is_file() and p.name.lower() == filename.lower():
            return send_from_directory(directory, p.name)
    return "", 404


if __name__ == "__main__":
    print("Open http://127.0.0.1:5001 in your browser.")
    app.run(host="127.0.0.1", port=5001, debug=True)
