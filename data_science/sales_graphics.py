#!/usr/bin/env python3
"""
Generate sales-ready graphics for pitch presentations and website.

Produces visuals that demonstrate:
- Lift & capture value (5/10/20% targeting efficiency)
- Model predictive ability
- Solar market state and adoption trends
"""

from datetime import datetime
from pathlib import Path

import os
os.environ.setdefault("MPLCONFIGDIR", str(Path(__file__).resolve().parent / ".mplconfig"))
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = PROJECT_ROOT / "data_science" / "output" / "sales_graphics"
METRICS_PATH = PROJECT_ROOT / "data_science" / "output" / "walk_forward" / "walk_forward_metrics.csv"
PERMITS_PATH = PROJECT_ROOT / "data" / "working" / "parsed_permits_by_year.csv"

# Sales-friendly color palette
ACCENT = "#f59e0b"  # Amber - primary CTA
ACCENT_DARK = "#d97706"
NEUTRAL = "#374151"
LIGHT = "#f3f4f6"
SUCCESS = "#059669"
CHART_BLUE = "#3b82f6"
CHART_GREEN = "#10b981"
CHART_ORANGE = "#f59e0b"


def setup_style(ax, title="", ylabel=""):
    """Apply clean, professional styling."""
    ax.set_facecolor("white")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    if title:
        ax.set_title(title, fontsize=14, fontweight=600, color=NEUTRAL, pad=12)
    if ylabel:
        ax.set_ylabel(ylabel, fontsize=11, color=NEUTRAL)
    ax.tick_params(colors=NEUTRAL)
    ax.grid(True, alpha=0.2, linestyle="-")


def chart_1_lift_value(hybrid_df: pd.DataFrame) -> None:
    """Lift vs random: 'Target top 10% = 3–4x more adopters than random outreach'."""
    fig, ax = plt.subplots(figsize=(10, 6))
    years = hybrid_df["install_year"].values
    x = np.arange(len(years))
    w = 0.25

    ax.bar(x - w, hybrid_df["lift_5pct"], width=w, label="Top 5%", color=CHART_ORANGE, alpha=0.9)
    ax.bar(x, hybrid_df["lift_10pct"], width=w, label="Top 10%", color=ACCENT, alpha=1)
    ax.bar(x + w, hybrid_df["lift_20pct"], width=w, label="Top 20%", color=ACCENT_DARK, alpha=0.9)

    ax.axhline(1, color=NEUTRAL, linestyle="--", alpha=0.5, linewidth=1, label="Random (1x)")
    ax.set_xticks(x)
    ax.set_xticklabels(years.astype(int))
    ax.set_xlabel("Install Year", fontsize=11, color=NEUTRAL)
    ax.set_ylabel("Lift (vs random outreach)", fontsize=11, color=NEUTRAL)
    ax.set_ylim(bottom=0)
    ax.legend(loc="upper right", frameon=True, fancybox=True)
    setup_style(ax, title="Targeting Efficiency: Our Model vs Random Outreach")
    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / "1_lift_vs_random.png", dpi=150, bbox_inches="tight", facecolor="white")
    plt.close()
    print("Saved: 1_lift_vs_random.png")


def chart_2_capture_efficiency(hybrid_df: pd.DataFrame) -> None:
    """Capture: 'Contact 10% of homes, reach 30–50% of adopters'."""
    fig, ax = plt.subplots(figsize=(10, 6))
    years = hybrid_df["install_year"].values
    x = np.arange(len(years))
    w = 0.25

    caps_5 = hybrid_df["capture_5pct"].values * 100
    caps_10 = hybrid_df["capture_10pct"].values * 100
    caps_20 = hybrid_df["capture_20pct"].values * 100

    ax.bar(x - w, caps_5, width=w, label="Top 5% (contact 5% of homes)", color=CHART_ORANGE, alpha=0.9)
    ax.bar(x, caps_10, width=w, label="Top 10% (contact 10% of homes)", color=ACCENT, alpha=1)
    ax.bar(x + w, caps_20, width=w, label="Top 20% (contact 20% of homes)", color=ACCENT_DARK, alpha=0.9)

    ax.axhline(5, color=NEUTRAL, linestyle="--", alpha=0.4, linewidth=1)
    ax.axhline(10, color=NEUTRAL, linestyle="--", alpha=0.4, linewidth=1)
    ax.axhline(20, color=NEUTRAL, linestyle="--", alpha=0.4, linewidth=1)
    ax.set_xticks(x)
    ax.set_xticklabels(years.astype(int))
    ax.set_xlabel("Install Year", fontsize=11, color=NEUTRAL)
    ax.set_ylabel("% of Solar Adopters Reached", fontsize=11, color=NEUTRAL)
    ax.set_ylim(0, 70)
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"{x:.0f}%"))
    ax.legend(loc="upper right", frameon=True, fancybox=True)
    setup_style(ax, title="Reach More Adopters with Less Outreach")
    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / "2_capture_efficiency.png", dpi=150, bbox_inches="tight", facecolor="white")
    plt.close()
    print("Saved: 2_capture_efficiency.png")


def chart_3_market_adoption(permits_df: pd.DataFrame) -> None:
    """Solar adoption growth over time - market state."""
    by_year = permits_df.groupby("year").agg(
        total_homes=("strap", "nunique"),
        new_installs=("solar_next_year", lambda x: (x == 1).sum()),
        cumulative_solar=("solar_pv", "sum"),
    ).reset_index()
    by_year = by_year[by_year["year"] <= 2024]  # Exclude incomplete years

    fig, ax1 = plt.subplots(figsize=(10, 6))
    years = by_year["year"].values
    x = np.arange(len(years))

    ax1.bar(x, by_year["new_installs"], color=CHART_BLUE, alpha=0.7, label="New solar installs (year)")
    ax1.set_xlabel("Year", fontsize=11, color=NEUTRAL)
    ax1.set_ylabel("New Solar Installations", fontsize=11, color=CHART_BLUE)
    ax1.tick_params(axis="y", labelcolor=CHART_BLUE)
    ax1.set_ylim(bottom=0)

    ax2 = ax1.twinx()
    ax2.plot(x, by_year["cumulative_solar"], color=SUCCESS, linewidth=2.5, marker="o", markersize=6, label="Cumulative solar homes")
    ax2.set_ylabel("Cumulative Homes with Solar", fontsize=11, color=SUCCESS)
    ax2.tick_params(axis="y", labelcolor=SUCCESS)
    ax2.set_ylim(bottom=0)

    ax1.set_xticks(x)
    ax1.set_xticklabels(years.astype(int))
    setup_style(ax1, title="Solar Market Growth: Adoption Over Time")
    ax1.legend(loc="upper left")
    ax2.legend(loc="upper right")
    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / "3_market_adoption.png", dpi=150, bbox_inches="tight", facecolor="white")
    plt.close()
    print("Saved: 3_market_adoption.png")


def chart_4_value_proposition(hybrid_df: pd.DataFrame) -> None:
    """Single-panel value prop: Contact 10% → Capture ~40%."""
    avg_cap_10 = hybrid_df["capture_10pct"].mean() * 100
    avg_lift_10 = hybrid_df["lift_10pct"].mean()

    fig, ax = plt.subplots(figsize=(8, 5))
    ax.axis("off")

    # Value callouts
    ax.text(0.5, 0.75, "Contact 10% of homes", ha="center", fontsize=22, fontweight=700, color=NEUTRAL)
    ax.text(0.5, 0.65, "→", ha="center", fontsize=28, color=ACCENT)
    ax.text(0.5, 0.55, f"Reach {avg_cap_10:.0f}% of adopters", ha="center", fontsize=22, fontweight=700, color=ACCENT)
    ax.text(0.5, 0.40, f"({avg_lift_10:.1f}x better than random outreach)", ha="center", fontsize=14, color=NEUTRAL, style="italic")
    ax.text(0.5, 0.20, "Our AI model ranks homes by likelihood to adopt solar.", ha="center", fontsize=12, color=NEUTRAL)
    ax.text(0.5, 0.12, "Target the top 10% and 4x your conversion efficiency.", ha="center", fontsize=12, color=NEUTRAL)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / "4_value_proposition.png", dpi=150, bbox_inches="tight", facecolor="white")
    plt.close()
    print("Saved: 4_value_proposition.png")


def chart_5_roi_comparison(hybrid_df: pd.DataFrame) -> None:
    """Side-by-side: Random vs Model - contacts needed to reach 100 adopters."""
    # To reach 100 adopters with 2% baseline: random needs 5000 contacts (100/0.02), model top 10% needs ~1250 (100/0.08)
    # Simplified: show "contacts per adopter" - random = 1/baseline, model = 1/(baseline*lift)
    recent = hybrid_df[hybrid_df["install_year"] >= 2020]
    avg_baseline = recent["baseline_adoption_rate"].mean()
    avg_lift_10 = recent["lift_10pct"].mean()
    avg_cap_10 = recent["capture_10pct"].mean()

    contacts_random = 1 / avg_baseline if avg_baseline > 0 else 0
    contacts_model = 1 / (avg_baseline * avg_lift_10) if avg_baseline > 0 else 0
    reduction = (1 - contacts_model / contacts_random) * 100

    fig, ax = plt.subplots(figsize=(8, 5))
    categories = ["Random outreach", "Our model (top 10%)"]
    contacts = [contacts_random, contacts_model]
    colors = [NEUTRAL, ACCENT]
    bars = ax.bar(categories, contacts, color=colors, alpha=0.9)
    ax.set_ylabel("Contacts needed per adopter", fontsize=11, color=NEUTRAL)
    ax.set_ylim(bottom=0)
    for bar, val in zip(bars, contacts):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 20, f"{val:,.0f}", ha="center", fontsize=12, fontweight=600)
    ax.text(0.5, 0.95, f"~{reduction:.0f}% fewer contacts to reach the same number of adopters", ha="center", transform=ax.transAxes, fontsize=12, color=SUCCESS, fontweight=600)
    setup_style(ax, title="Efficiency: Contacts Per Solar Adopter")
    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / "5_roi_contacts_per_adopter.png", dpi=150, bbox_inches="tight", facecolor="white")
    plt.close()
    print("Saved: 5_roi_contacts_per_adopter.png")


def chart_6_model_performance_summary(hybrid_df: pd.DataFrame) -> None:
    """Clean summary: lift and capture by tier (5/10/20%) - recent years average."""
    recent = hybrid_df[hybrid_df["install_year"] >= 2020]
    tiers = ["Top 5%", "Top 10%", "Top 20%"]
    lifts = [recent["lift_5pct"].mean(), recent["lift_10pct"].mean(), recent["lift_20pct"].mean()]
    captures = [recent["capture_5pct"].mean() * 100, recent["capture_10pct"].mean() * 100, recent["capture_20pct"].mean() * 100]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))
    x = np.arange(len(tiers))
    w = 0.5

    ax1.bar(x, lifts, width=w, color=[CHART_ORANGE, ACCENT, ACCENT_DARK], alpha=0.9)
    ax1.axhline(1, color=NEUTRAL, linestyle="--", alpha=0.5)
    ax1.set_xticks(x)
    ax1.set_xticklabels(tiers)
    ax1.set_ylabel("Lift (vs random)")
    ax1.set_ylim(bottom=0)
    setup_style(ax1, title="Lift by Targeting Tier (2020–2025 avg)")

    ax2.bar(x, captures, width=w, color=[CHART_ORANGE, ACCENT, ACCENT_DARK], alpha=0.9)
    ax2.set_xticks(x)
    ax2.set_xticklabels(tiers)
    ax2.set_ylabel("% of Adopters Reached")
    ax2.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:.0f}%"))
    ax2.set_ylim(0, 60)
    setup_style(ax2, title="Capture by Targeting Tier (2020–2025 avg)")

    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / "6_model_performance_summary.png", dpi=150, bbox_inches="tight", facecolor="white")
    plt.close()
    print("Saved: 6_model_performance_summary.png")


def chart_7_market_penetration(permits_df: pd.DataFrame) -> None:
    """Market penetration: % of homes with solar over time."""
    by_year = permits_df.groupby("year").agg(
        total=("strap", "nunique"),
        with_solar=("solar_pv", "sum"),
    ).reset_index()
    by_year = by_year[by_year["year"] <= 2024]
    by_year["pct_solar"] = by_year["with_solar"] / by_year["total"] * 100

    fig, ax = plt.subplots(figsize=(10, 6))
    ax.fill_between(by_year["year"], by_year["pct_solar"], alpha=0.3, color=SUCCESS)
    ax.plot(by_year["year"], by_year["pct_solar"], color=SUCCESS, linewidth=2.5, marker="o", markersize=8)
    ax.set_xlabel("Year", fontsize=11, color=NEUTRAL)
    ax.set_ylabel("% of Homes with Solar", fontsize=11, color=NEUTRAL)
    ax.set_ylim(0, 20)
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"{x:.1f}%"))
    setup_style(ax, title="Market Penetration: Solar Adoption Rate")
    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / "7_market_penetration.png", dpi=150, bbox_inches="tight", facecolor="white")
    plt.close()
    print("Saved: 7_market_penetration.png")


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Load data
    if not METRICS_PATH.exists():
        print(f"Error: {METRICS_PATH} not found. Run walk_forward_modeling.py first.")
        return

    metrics = pd.read_csv(METRICS_PATH)
    hybrid_df = metrics[
        (metrics["model"] == "GB+Ensemble Hybrid (70/30)") & (metrics["install_year"] < 2026)
    ].sort_values("install_year")

    permits_df = pd.read_csv(PERMITS_PATH) if PERMITS_PATH.exists() else None

    print(f"Generating sales graphics (timestamp: {ts})...")
    print()

    chart_1_lift_value(hybrid_df)
    chart_2_capture_efficiency(hybrid_df)
    chart_4_value_proposition(hybrid_df)
    chart_5_roi_comparison(hybrid_df)
    chart_6_model_performance_summary(hybrid_df)

    if permits_df is not None:
        chart_3_market_adoption(permits_df)
        chart_7_market_penetration(permits_df)
    else:
        print("Skipping market charts (parsed_permits_by_year.csv not found)")

    print()
    print(f"Done. Graphics saved to {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
