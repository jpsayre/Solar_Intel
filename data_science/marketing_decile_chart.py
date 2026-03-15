#!/usr/bin/env python3
"""Generate a clean marketing chart: Gradient Boosting capture by decile."""

import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
from pathlib import Path

OUTPUT_DIR = Path(__file__).resolve().parent / "output" / "Boulder_CO" / "walk_forward"
DATA_PATH = OUTPUT_DIR / "walk_forward_decile_lift.csv"

df = pd.read_csv(DATA_PATH)

# Filter: Gradient Boosting only, exclude 2026
gb = df[(df["model"] == "Gradient Boosting") & (df["install_year"] < 2026)]

# Average capture_pct across all years per decile
avg = gb.groupby("decile")["capture_pct"].mean()

year_min = int(gb["install_year"].min())
year_max = int(gb["install_year"].max())

AMBER_500 = "#f59e0b"
AMBER_600 = "#d97706"

fig, ax = plt.subplots(figsize=(10, 5.5))
fig.patch.set_facecolor("white")
ax.set_facecolor("white")

bars = ax.bar(
    avg.index, avg.values,
    width=0.65,
    color=AMBER_500,
    edgecolor=AMBER_600,
    linewidth=0.8,
    zorder=3,
)

# Value labels on top of each bar
for bar, val in zip(bars, avg.values):
    ax.text(
        bar.get_x() + bar.get_width() / 2,
        bar.get_height() + 0.003,
        f"{val:.0%}",
        ha="center", va="bottom",
        fontsize=10, fontweight="600", color="#374151",
    )


ax.axhline(0.10, color="#9ca3af", linestyle="--", linewidth=1.2, zorder=2)

ax.set_xlabel("")
ax.set_ylabel("Solar Installations Captured", fontsize=12, fontweight="500", color="#374151", labelpad=10)

ax.set_xticks(range(1, 11))
ax.set_xticklabels([f"{i*10}%" for i in range(1, 11)], fontsize=10, color="#6b7280")
ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{x:.0%}"))
ax.tick_params(axis="y", labelsize=10, colors="#6b7280")

ax.set_axisbelow(True)

# Clean up spines
for spine in ["top", "right"]:
    ax.spines[spine].set_visible(False)
for spine in ["bottom", "left"]:
    ax.spines[spine].set_color("#e5e7eb")

plt.tight_layout(rect=[0, 0, 1, 0.88])

# Centered title block above the axes
fig.text(0.5, 0.96, "Home Ranking Deciles",
         ha="center", fontsize=16, fontweight="700", color="#111827")
fig.text(0.5, 0.915, f"Our model\u2019s solar install ranking ability (avg: {year_min}\u2013{year_max})",
         ha="center", fontsize=11, color="#6b7280", style="italic")
out_path = OUTPUT_DIR / "marketing_capture_by_decile.png"
plt.savefig(out_path, dpi=200, bbox_inches="tight", facecolor="white")
plt.close()
print(f"Saved: {out_path}")