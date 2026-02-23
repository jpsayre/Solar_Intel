#!/usr/bin/env python3
"""
Regenerate hybrid model charts from saved walk_forward_metrics.csv.

Run this after walk_forward_modeling.py has produced walk_forward_metrics.csv.
No need to re-run the full modeling script to update charts.
"""

from datetime import datetime
from pathlib import Path

import os
os.environ.setdefault("MPLCONFIGDIR", str(Path(__file__).resolve().parent / ".mplconfig"))
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = PROJECT_ROOT / "data_science" / "output" / "walk_forward"
METRICS_PATH = OUTPUT_DIR / "walk_forward_metrics.csv"

HYBRID_NAME = "GB+Ensemble Hybrid (70/30)"
HYBRID_COLOR = "#f59e0b"


def main() -> None:
    if not METRICS_PATH.exists():
        print(f"Error: {METRICS_PATH} not found. Run walk_forward_modeling.py first.")
        return

    results_df = pd.read_csv(METRICS_PATH)
    hybrid_df = results_df[
        (results_df["model"] == HYBRID_NAME) & (results_df["install_year"] < 2026)
    ].sort_values("install_year")

    if len(hybrid_df) == 0:
        print(f"No data for {HYBRID_NAME} (excluding 2026).")
        return

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    for pct, lift_col, cap_col in [
        (20, "lift_20pct", "capture_20pct"),
        (10, "lift_10pct", "capture_10pct"),
        (5, "lift_5pct", "capture_5pct"),
    ]:
        if lift_col in results_df.columns:
            fig, ax = plt.subplots(figsize=(10, 5))
            ax.plot(hybrid_df["install_year"], hybrid_df[lift_col], "-o", color=HYBRID_COLOR, markersize=8)
            ax.set_ylim(bottom=0)
            ax.set_xlabel("Install Year")
            ax.set_ylabel(f"Top {pct}% Lift (vs baseline)")
            ax.set_title(f"Top {pct}% Lift by Install Year")
            ax.grid(True, alpha=0.3)
            plt.tight_layout()
            plt.savefig(OUTPUT_DIR / f"hybrid_top{pct}pct_lift_by_year_{ts}.png", dpi=150)
            plt.close()
            print(f"Saved: {OUTPUT_DIR / f'hybrid_top{pct}pct_lift_by_year_{ts}.png'}")

        if cap_col in results_df.columns:
            fig, ax = plt.subplots(figsize=(10, 5))
            ax.plot(hybrid_df["install_year"], hybrid_df[cap_col], "-o", color=HYBRID_COLOR, markersize=8)
            ax.set_ylim(bottom=0)
            ax.set_xlabel("Install Year")
            ax.set_ylabel(f"Top {pct}% Capture (% of positives)")
            ax.set_title(f"Top {pct}% Capture by Install Year")
            ax.grid(True, alpha=0.3)
            ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"{x:.0%}"))
            plt.tight_layout()
            plt.savefig(OUTPUT_DIR / f"hybrid_top{pct}pct_capture_by_year_{ts}.png", dpi=150)
            plt.close()
            print(f"Saved: {OUTPUT_DIR / f'hybrid_top{pct}pct_capture_by_year_{ts}.png'}")


if __name__ == "__main__":
    main()
