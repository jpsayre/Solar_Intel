# See canvas for full script
# This file generates an HTML listing page from images + CSV

"""
Generate an HTML "listing-style" page from:
- images in: data/images/
- CSV in:     data/final/<your_file>.csv

Assumptions (easy to change):
- Each image filename (without extension) is the "image_name"
  Example: data/images/12345.png  -> image_name = "12345"
- The CSV has a column named "original_index" that matches image_name
  Example: original_index == "12345"
- You choose which CSV columns to show in the listing by editing DISPLAY_COLUMNS below.
"""

from __future__ import annotations

import os
import html
# pathlib no longer needed
from typing import List, Dict, Optional

import pandas as pd

# ----------------------------
# USER SETTINGS (edit these)
# ----------------------------
CSV_PATH = "/Users/jeffs/Projects/SolarProject/data/final/Boulder_CO_Final_Data.csv"
IMAGES_DIR = "/Users/jeffs/Projects/SolarProject/data/images"
OUTPUT_HTML = "/Users/jeffs/Projects/SolarProject/data/final/listings.html"

JOIN_KEY_CSV = "original_index"

DISPLAY_COLUMNS: List[Dict[str, str]] = [
    {"col": "address", "label": "Address"},
    {"col": "solar_score", "label": "Solar Score"},
    {"col": "roof_area_m2", "label": "Roof area (m²)"},
    {"col": "azimuth_deg", "label": "Azimuth (°)"},
    {"col": "sunshine_quantile", "label": "Sunshine quantile"},
]

HEADLINE_COLUMN = "mailadd"   # set to None to disable
CHIP_COLUMNS: List[str] = ["solar_score", "sqft"]
MAX_ITEMS: Optional[int] = None

# ----------------------------
# Helpers
# ----------------------------

def safe_text(x) -> str:
    """Escape for HTML; treat NaNs as blank."""
    if pd.isna(x):
        return ""
    return html.escape(str(x))


def format_value(col: str, x) -> str:
    """Human-friendly formatting for common fields (edit as you like)."""
    if pd.isna(x):
        return ""

    # Normalize strings
    if isinstance(x, str):
        x_str = x.strip()
    else:
        x_str = str(x)

    # Column-specific formatting
    if col.lower() in {"saleprice", "last_sale_price", "lastsaleprice"}:
        try:
            n = float(x)
            return f"${n:,.0f}"
        except Exception:
            return x_str

    if col.lower() in {"sqft", "square_footage"}:
        try:
            n = float(x)
            return f"{n:,.0f} sq ft"
        except Exception:
            return x_str

    if col.lower() in {"owneroccupied", "owner_occupied"}:
        # Handles 1/0, True/False, "Y"/"N", etc.
        v = str(x).strip().lower()
        if v in {"1", "true", "t", "y", "yes"}:
            return "Yes"
        if v in {"0", "false", "f", "n", "no"}:
            return "No"
        return x_str

    if col.lower() in {"calculated_build_year", "build_year", "year_built"}:
        try:
            return str(int(float(x)))
        except Exception:
            return x_str

    # Default: keep as-is
    return x_str


# image_name is derived directly from filename string now


def build_listing_html(
    image_rel_path: str,
    row: pd.Series,
    display_columns: List[Dict[str, str]],
    headline_column: Optional[str],
    chip_columns: List[str],
) -> str:
    headline = safe_text(row[headline_column]) if headline_column and headline_column in row else ""

    chips = []
    for c in chip_columns:
        if c in row and not pd.isna(row[c]):
            chips.append(f'<span class="chip">{safe_text(c.replace("_", " ").title())}: {safe_text(format_value(c, row[c]))}</span>')

    chips_html = f'<div class="chips">{"".join(chips)}</div>' if chips else ""

    kv_rows = []
    for item in display_columns:
        col = item["col"]
        label = item.get("label", col)
        if col in row and not pd.isna(row[col]):
            kv_rows.append(f"""
            <div class=\"kv\">
              <div class=\"k\">{label}</div>
              <div class=\"v\">{safe_text(format_value(col, row[col]))}</div>
            </div>
            """)

    return f"""
    <article class=\"card\">
      <div class=\"imgwrap\">
        <img src=\"{image_rel_path}\" loading=\"lazy\" />
      </div>
      <div class=\"content\">
        {f"<h2>{headline}</h2>" if headline else ""}
        {chips_html}
        <div class=\"kvgrid\">
          {"".join(kv_rows)}
        </div>
      </div>
    </article>
    """


# ----------------------------
# Main
# ----------------------------

def main() -> None:
    df = pd.read_csv(CSV_PATH)
    df[JOIN_KEY_CSV] = df[JOIN_KEY_CSV].astype(str)
    df = df.set_index(JOIN_KEY_CSV)

    cards = []

        # Iterate using full absolute paths (no Path / glob)
    for fname in sorted(os.listdir(IMAGES_DIR)):
        img_path = os.path.join(IMAGES_DIR, fname)

        if not os.path.isfile(img_path):
            continue

        print("[DEBUG] Found image file:", img_path)
        print("        Exists on disk?", os.path.exists(img_path))

        key, _ = os.path.splitext(fname)
        if key not in df.index:
            continue

        # Use absolute path directly in HTML
        src = f"file://{img_path}"
        print("[DEBUG] Image src written to HTML:", src)

        cards.append(
            build_listing_html(
                src,
                df.loc[key],
                DISPLAY_COLUMNS,
                HEADLINE_COLUMN,
                CHIP_COLUMNS,
            )
        )

        if MAX_ITEMS and len(cards) >= MAX_ITEMS:
            break

    os.makedirs(os.path.dirname(OUTPUT_HTML), exist_ok=True)
    with open(OUTPUT_HTML, "w", encoding="utf-8") as f:
        f.write("""
<!doctype html>
<html lang="en">
  <head>
    <meta charset=\"utf-8\">
    <title>Listings</title>
    <style>
      :root {
        --bg: #f6f7fb;
        --card: #ffffff;
        --text: #1b2430;
        --muted: #5b6b7c;
        --border: rgba(27, 36, 48, 0.12);
        --shadow: 0 10px 30px rgba(27, 36, 48, 0.10);
        --chip: rgba(17, 24, 39, 0.06);
      }

      * { box-sizing: border-box; }

      body {
        margin: 0;
        background: var(--bg);
        color: var(--text);
        font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial;
      }

      header {
        max-width: 1100px;
        margin: 0 auto;
        padding: 28px 18px 10px;
      }

      header h1 {
        margin: 0 0 6px;
        font-size: 26px;
        letter-spacing: 0.2px;
      }

      header p {
        margin: 0;
        color: var(--muted);
        font-size: 14px;
        line-height: 1.4;
      }

      main {
        max-width: 1100px;
        margin: 0 auto;
        padding: 14px 18px 40px;
        display: grid;
        grid-template-columns: 1fr;
        gap: 14px;
      }

      .card {
        display: grid;
        grid-template-columns: 360px 1fr;
        gap: 0;
        background: var(--card);
        border: 1px solid var(--border);
        border-radius: 16px;
        box-shadow: var(--shadow);
        overflow: hidden;
      }

      .imgwrap {
        background: rgba(17, 24, 39, 0.03);
        border-right: 1px solid var(--border);
        min-height: 260px;
      }

      img {
        width: 100%;
        height: 100%;
        object-fit: cover;
        display: block;
      }

      .content {
        padding: 16px 16px 14px;
      }

      .content h2 {
        margin: 0 0 10px;
        font-size: 18px;
        line-height: 1.25;
      }

      .chips {
        display: flex;
        flex-wrap: wrap;
        gap: 8px;
        margin: 0 0 12px;
      }

      .chip {
        display: inline-block;
        padding: 6px 10px;
        border-radius: 999px;
        background: var(--chip);
        border: 1px solid var(--border);
        color: var(--text);
        font-size: 12px;
        white-space: nowrap;
      }

      .kvgrid {
        display: grid;
        grid-template-columns: 1fr;
        gap: 10px;
      }

      .kv {
        display: grid;
        grid-template-columns: 170px 1fr;
        gap: 12px;
        padding: 10px 12px;
        border: 1px solid var(--border);
        border-radius: 12px;
        background: rgba(17, 24, 39, 0.02);
      }

      .k {
        color: var(--muted);
        font-size: 12px;
        text-transform: uppercase;
        letter-spacing: 0.6px;
      }

      .v {
        font-size: 13px;
        color: var(--text);
        word-break: break-word;
      }

      @media (max-width: 860px) {
        .card { grid-template-columns: 1fr; }
        .imgwrap { border-right: 0; border-bottom: 1px solid var(--border); min-height: 220px; }
        .kv { grid-template-columns: 1fr; }
      }
    </style>
  </head>
  <body>
    <header>
      <h1>Solar Intelligence Report</h1>
        <h3>Every home listed here meets the following criteria*:</h3>
        <ul>
            <li>Single Family Home</li>
            <li>Owner Occupied</li>
            <li>No or Minimal Shade Concerns</li>
            <li>No existing solar panel installation</li>
            <li>South facing roof segment a minimum of 30 m2 (323 ft2).</li>
        </ul>
        <p>*As of date of Google Maps satellite imagery</p>
    </header>
    <main>
    """ + "".join(cards) + """
    </main>
  </body>
</html>
""")


if __name__ == "__main__":
    main()
