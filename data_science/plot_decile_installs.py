#!/usr/bin/env python3
"""
Plot solar installations by model-score decile.

Shows that higher-scored deciles capture disproportionately more solar adopters,
aggregated across all walk-forward validation years.
"""

import os
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", str(Path(__file__).resolve().parent / ".mplconfig"))
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DECILE_PATH = PROJECT_ROOT / "data_science" / "output" / "walk_forward" / "walk_forward_decile_lift.csv"
OUTPUT_DIR = PROJECT_ROOT / "data_science" / "output" / "walk_forward"

MODEL = "Gradient Boosting"  # best single model on recent data


def main():
    df = pd.read_csv(DECILE_PATH)

    # --- Chart 1: Aggregated across all years for the best model ---
    m = df[df["model"] == MODEL].copy()
    agg = m.groupby("decile").agg(
        total_installs=("captured", "sum"),
        total_homes=("n", "sum"),
    ).reset_index()
    agg["adoption_rate"] = agg["total_installs"] / agg["total_homes"] * 100

    fig, ax1 = plt.subplots(figsize=(10, 6))

    bars = ax1.bar(
        agg["decile"], agg["total_installs"],
        color=plt.cm.RdYlBu_r(np.linspace(0.15, 0.85, 10)),
        edgecolor="white", linewidth=0.8, zorder=3,
    )
    ax1.set_xlabel("Model Score Decile (1 = highest scored)", fontsize=12)
    ax1.set_ylabel("Solar Installations", fontsize=12, color="#333")
    ax1.set_xticks(range(1, 11))
    ax1.set_xticklabels([f"D{i}" for i in range(1, 11)])
    ax1.grid(axis="y", alpha=0.3, zorder=0)

    # Add count labels on bars
    for bar, val in zip(bars, agg["total_installs"]):
        ax1.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 2,
                 str(int(val)), ha="center", va="bottom", fontsize=10, fontweight="bold")

    # Overlay adoption rate line
    ax2 = ax1.twinx()
    ax2.plot(agg["decile"], agg["adoption_rate"], "ko-", linewidth=2, markersize=6, zorder=4)
    ax2.set_ylabel("Adoption Rate (%)", fontsize=12, color="#333")

    total = agg["total_installs"].sum()
    top2 = agg.loc[agg["decile"] <= 2, "total_installs"].sum()
    top2_pct = top2 / total * 100

    ax1.set_title(
        f"Solar Installations by Score Decile — {MODEL}\n"
        f"Walk-Forward Validation 2013–2025  |  Top 2 deciles capture {top2_pct:.0f}% of installs",
        fontsize=13, fontweight="bold", pad=12,
    )

    fig.tight_layout()
    out = OUTPUT_DIR / "decile_installs_aggregated.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    print(f"Saved: {out}")
    plt.close(fig)

    # --- Chart 2: By year heatmap ---
    pivot = m.pivot_table(index="install_year", columns="decile", values="captured", aggfunc="sum")
    pivot = pivot.reindex(columns=range(1, 11))

    fig, ax = plt.subplots(figsize=(12, 7))
    im = ax.imshow(pivot.values, aspect="auto", cmap="YlOrRd", interpolation="nearest")

    ax.set_xticks(range(10))
    ax.set_xticklabels([f"D{i}" for i in range(1, 11)])
    ax.set_yticks(range(len(pivot.index)))
    ax.set_yticklabels(pivot.index.astype(int))
    ax.set_xlabel("Model Score Decile (1 = highest scored)", fontsize=12)
    ax.set_ylabel("Install Year", fontsize=12)

    # Annotate cells
    for i in range(pivot.shape[0]):
        for j in range(pivot.shape[1]):
            val = pivot.values[i, j]
            if np.isnan(val):
                continue
            color = "white" if val > pivot.values.max() * 0.6 else "black"
            ax.text(j, i, f"{int(val)}", ha="center", va="center",
                    fontsize=9, fontweight="bold", color=color)

    ax.set_title(
        f"Solar Installations by Decile & Year — {MODEL}\n"
        "Walk-Forward Out-of-Sample Validation",
        fontsize=13, fontweight="bold", pad=12,
    )

    cbar = fig.colorbar(im, ax=ax, shrink=0.8, pad=0.02)
    cbar.set_label("Installations", fontsize=11)

    fig.tight_layout()
    out2 = OUTPUT_DIR / "decile_installs_by_year.png"
    fig.savefig(out2, dpi=150, bbox_inches="tight")
    print(f"Saved: {out2}")
    plt.close(fig)

    # Print summary table
    print(f"\n{'Decile':<8} {'Installs':>10} {'Homes':>8} {'Rate':>8} {'% of Total':>12}")
    print("-" * 50)
    for _, row in agg.iterrows():
        pct = row["total_installs"] / total * 100
        print(f"D{int(row['decile']):<7} {int(row['total_installs']):>10} {int(row['total_homes']):>8} {row['adoption_rate']:>7.2f}% {pct:>11.1f}%")
    print("-" * 50)
    print(f"{'Total':<8} {int(total):>10}")


if __name__ == "__main__":
    main()
