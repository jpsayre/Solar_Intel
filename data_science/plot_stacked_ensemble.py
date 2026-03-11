"""Generate plots for Stacked Ensemble lift & capture at 2%, 5%, 10% by year."""

import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
from pathlib import Path

OUT_DIR = Path(__file__).resolve().parent / "output" / "walk_forward"

# Load metrics
df = pd.read_csv(OUT_DIR / "walk_forward_summary.csv")
se = df[(df["model"] == "Stacked Ensemble") & (df["install_year"].between(2013, 2025))].copy()
se = se.sort_values("install_year")

years = se["install_year"].values

# ── 1. Lift at 2%, 5%, 10% by year with baseline adoption rate ───────────────
fig, ax = plt.subplots(figsize=(12, 6))
colors = {"2%": "#e74c3c", "5%": "#f39c12", "10%": "#2ecc71"}
for pct, col in [("2%", "lift_2pct"), ("5%", "lift_5pct"), ("10%", "lift_10pct")]:
    vals = se[col].values
    ax.plot(years, vals, "o-", label=f"Top {pct} lift", color=colors[pct], linewidth=2, markersize=7)
    avg = vals.mean()
    ax.axhline(avg, color=colors[pct], linestyle="--", alpha=0.4, linewidth=1)
    ax.text(years[-1] + 0.3, avg, f"avg {avg:.1f}x", color=colors[pct], fontsize=9, va="center")

ax.axhline(1.0, color="gray", linestyle=":", alpha=0.5)

# Add baseline adoption rate on secondary axis
ax2 = ax.twinx()
base_rates = se["baseline_adoption_rate"].values * 100
ax2.plot(years, base_rates, "o--", color="#7f8c8d", linewidth=1.5, markersize=6, label="Baseline adoption rate")
ax2.set_ylabel("Baseline Adoption Rate (%)", fontsize=11, color="#7f8c8d")
ax2.tick_params(axis="y", labelcolor="#7f8c8d")
ax2.yaxis.set_major_formatter(mticker.PercentFormatter())

ax.set_xlabel("Install Year (Test Fold)", fontsize=12)
ax.set_ylabel("Lift (x)", fontsize=12)
ax.set_title("Stacked Ensemble — Lift at Top 2%, 5%, 10% by Year", fontsize=14, fontweight="bold")

# Combine legends from both axes
lines1, labels1 = ax.get_legend_handles_labels()
lines2, labels2 = ax2.get_legend_handles_labels()
ax.legend(lines1 + lines2, labels1 + labels2, fontsize=10, loc="upper left")

ax.set_xticks(years)
ax.set_xticklabels(years, rotation=45)
ax.grid(True, alpha=0.3)
fig.tight_layout()
fig.savefig(OUT_DIR / "stacked_ensemble_lift_by_year.png", dpi=150)
print(f"Saved: stacked_ensemble_lift_by_year.png")

# ── 2. Capture at 2%, 5%, 10% by year ───────────────────────────────────────
fig, ax = plt.subplots(figsize=(12, 6))
for pct, col in [("2%", "capture_2pct"), ("5%", "capture_5pct"), ("10%", "capture_10pct")]:
    vals = se[col].values * 100  # convert to %
    ax.plot(years, vals, "s-", label=f"Top {pct} capture", color=colors[pct], linewidth=2, markersize=7)
    avg = vals.mean()
    ax.axhline(avg, color=colors[pct], linestyle="--", alpha=0.4, linewidth=1)
    ax.text(years[-1] + 0.3, avg, f"avg {avg:.0f}%", color=colors[pct], fontsize=9, va="center")

ax.yaxis.set_major_formatter(mticker.PercentFormatter())
ax.set_xlabel("Install Year (Test Fold)", fontsize=12)
ax.set_ylabel("Capture Rate (%)", fontsize=12)
ax.set_title("Stacked Ensemble — Capture Rate at Top 2%, 5%, 10% by Year", fontsize=14, fontweight="bold")
ax.legend(fontsize=11)
ax.set_xticks(years)
ax.set_xticklabels(years, rotation=45)
ax.grid(True, alpha=0.3)
fig.tight_layout()
fig.savefig(OUT_DIR / "stacked_ensemble_capture_by_year.png", dpi=150)
print(f"Saved: stacked_ensemble_capture_by_year.png")

# ── 3. Combined lift + ROC-AUC dual-axis ────────────────────────────────────
fig, ax1 = plt.subplots(figsize=(12, 6))
ax2 = ax1.twinx()

# Lift@2% on left axis
l2 = se["lift_2pct"].values
ax1.bar(years - 0.15, l2, width=0.3, color="#e74c3c", alpha=0.7, label="Lift @ 2%")
ax1.set_ylabel("Lift @ 2% (x)", fontsize=12, color="#e74c3c")
ax1.tick_params(axis="y", labelcolor="#e74c3c")

# ROC-AUC on right axis
roc = se["roc_auc"].values
ax2.plot(years, roc, "D-", color="#3498db", linewidth=2, markersize=8, label="ROC-AUC")
ax2.set_ylabel("ROC-AUC", fontsize=12, color="#3498db")
ax2.tick_params(axis="y", labelcolor="#3498db")
ax2.set_ylim(0.5, 0.9)

ax1.set_xlabel("Install Year (Test Fold)", fontsize=12)
ax1.set_title("Stacked Ensemble — Lift@2% vs ROC-AUC by Year", fontsize=14, fontweight="bold")
ax1.set_xticks(years)
ax1.set_xticklabels(years, rotation=45)

# Combine legends
lines1, labels1 = ax1.get_legend_handles_labels()
lines2, labels2 = ax2.get_legend_handles_labels()
ax1.legend(lines1 + lines2, labels1 + labels2, loc="upper left", fontsize=11)

ax1.grid(True, alpha=0.3)
fig.tight_layout()
fig.savefig(OUT_DIR / "stacked_ensemble_lift_vs_auc_by_year.png", dpi=150)
print(f"Saved: stacked_ensemble_lift_vs_auc_by_year.png")

# ── 4. Model comparison at 2% tier ──────────────────────────────────────────
models = ["Stacked Ensemble", "Gradient Boosting", "Random Forest", "LightGBM", "Neural Net"]
model_colors = {"Stacked Ensemble": "#e74c3c", "Gradient Boosting": "#2ecc71",
                "Random Forest": "#3498db", "LightGBM": "#9b59b6", "Neural Net": "#f39c12"}

fig, ax = plt.subplots(figsize=(12, 6))
for m in models:
    mdf = df[(df["model"] == m) & (df["install_year"].between(2013, 2025))].sort_values("install_year")
    if len(mdf) > 0:
        ax.plot(mdf["install_year"], mdf["lift_2pct"], "o-", label=m,
                color=model_colors.get(m, "gray"), linewidth=1.5 if m != "Stacked Ensemble" else 2.5,
                alpha=0.5 if m != "Stacked Ensemble" else 1.0, markersize=5 if m != "Stacked Ensemble" else 8)

ax.axhline(1.0, color="gray", linestyle=":", alpha=0.5)
ax.set_xlabel("Install Year (Test Fold)", fontsize=12)
ax.set_ylabel("Lift @ 2% (x)", fontsize=12)
ax.set_title("All Models — Lift at Top 2% by Year", fontsize=14, fontweight="bold")
ax.legend(fontsize=10)
ax.set_xticks(years)
ax.set_xticklabels(years, rotation=45)
ax.grid(True, alpha=0.3)
fig.tight_layout()
fig.savefig(OUT_DIR / "all_models_lift_2pct_by_year.png", dpi=150)
print(f"Saved: all_models_lift_2pct_by_year.png")

# ── Print summary table ─────────────────────────────────────────────────────
print("\n=== Stacked Ensemble Summary ===")
print(f"{'Year':<6} {'ROC-AUC':>8} {'Lift@2%':>8} {'Lift@5%':>8} {'Lift@10%':>9} {'Cap@2%':>7} {'Cap@5%':>7} {'Cap@10%':>8}")
print("-" * 72)
for _, r in se.iterrows():
    print(f"{int(r['install_year']):<6} {r['roc_auc']:>8.3f} {r['lift_2pct']:>8.1f}x {r['lift_5pct']:>8.1f}x {r['lift_10pct']:>9.1f}x {r['capture_2pct']*100:>6.1f}% {r['capture_5pct']*100:>6.1f}% {r['capture_10pct']*100:>7.1f}%")
print("-" * 72)
print(f"{'AVG':<6} {se['roc_auc'].mean():>8.3f} {se['lift_2pct'].mean():>8.1f}x {se['lift_5pct'].mean():>8.1f}x {se['lift_10pct'].mean():>9.1f}x {se['capture_2pct'].mean()*100:>6.1f}% {se['capture_5pct'].mean()*100:>6.1f}% {se['capture_10pct'].mean()*100:>7.1f}%")

plt.close("all")
print("\nDone!")
