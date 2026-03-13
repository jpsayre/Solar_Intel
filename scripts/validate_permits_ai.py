#!/usr/bin/env python3
"""
AI cross-check for permit classification.

Takes a stratified sample of classified permits, asks GPT-4o-mini to
independently classify each one from its raw text, and flags disagreements
with the rule-based system.

Usage:
    python scripts/validate_permits_ai.py --config boulder_co
    python scripts/validate_permits_ai.py --config boulder_co --sample-size 50
    python scripts/validate_permits_ai.py --config boulder_co --other-only

Requires: OPEN_AI_API_KEY environment variable.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

try:
    from dotenv import load_dotenv
    load_dotenv(PROJECT_ROOT / ".env")
except ImportError:
    pass

PERMIT_TYPES = [
    "solar", "battery", "ev_charger", "heat_pump", "generator",
    "roof", "hvac", "electrical", "water_heater", "construction",
    "remodel", "envelope", "pool", "other",
]

SYSTEM_PROMPT = """You are a permit classification expert. Given a building permit's category, description, and valuation, classify it into exactly one of these types:

- solar: Solar PV panel installation (NOT solar thermal/water heating)
- battery: Battery storage (Powerwall, energy storage)
- ev_charger: Electric vehicle charger installation
- heat_pump: Heat pump HVAC system (NOT heat pump water heater)
- generator: Backup generator
- roof: Roof replacement or re-roof
- hvac: Air conditioning, furnace, or evaporative cooler (NOT heat pump)
- electrical: Electrical service/panel upgrade
- water_heater: Any water heater (gas, electric, solar thermal, tankless)
- construction: New construction, addition, ADU
- remodel: Kitchen/bathroom remodel, renovation, basement finish
- envelope: Windows, doors, insulation, air sealing, siding
- pool: Pool, hot tub, spa
- other: Anything that doesn't fit above (fencing, demolition, sewer, fireplace, deck, etc.)

Respond with ONLY valid JSON:
{"permit_type": "...", "confidence": "high|medium|low", "reasoning": "brief explanation"}"""


def _list_available_configs() -> list[str]:
    configs_dir = PROJECT_ROOT / "configs"
    if not configs_dir.exists():
        return []
    return sorted(p.stem for p in configs_dir.glob("*.py") if not p.name.startswith("_"))


def sample_permits(df: pd.DataFrame, sample_size: int, other_only: bool) -> pd.DataFrame:
    """Stratified sample: N per permit_type + extra from 'other'.

    For multi-type permits (comma-separated), a permit is sampled under each
    type it belongs to. Deduplication ensures each permit appears only once.
    """
    if other_only:
        others = df[df["permit_type"].str.strip() == "other"]
        n = min(sample_size * 5, len(others))
        return others.sample(n=n, random_state=42)

    samples = []
    for ptype in PERMIT_TYPES:
        # Match permits that contain this type (exact word within comma-separated list)
        subset = df[df["permit_type"].str.split(",").apply(
            lambda types: ptype in [t.strip() for t in types]
        )]
        if len(subset) == 0:
            continue
        n = min(sample_size, len(subset))
        samples.append(subset.sample(n=n, random_state=42))

    combined = pd.concat(samples, ignore_index=True)
    return combined.drop_duplicates(subset=["strap", "permit_num"])


def classify_with_ai(client, row: dict) -> dict:
    """Send one permit to GPT-4o-mini for classification."""
    cat = str(row.get("permit_category", "")).strip() or "(none)"
    desc = str(row.get("description", "")).strip() or "(no description)"
    val = row.get("estimated_value")
    val_str = f"${val:,.0f}" if pd.notna(val) else "unknown"

    user_msg = f"Permit category: {cat}\nDescription: {desc}\nValuation: {val_str}"

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ],
        temperature=0,
        max_tokens=150,
    )

    text = response.choices[0].message.content.strip()
    try:
        result = json.loads(text)
        # Validate permit_type
        if result.get("permit_type") not in PERMIT_TYPES:
            result["permit_type"] = "other"
        return result
    except json.JSONDecodeError:
        return {"permit_type": "other", "confidence": "low", "reasoning": f"JSON parse error: {text[:100]}"}


def main():
    available = _list_available_configs()
    parser = argparse.ArgumentParser(
        description="AI cross-check for permit classification",
        epilog=f"Available configs: {', '.join(available)}" if available else "",
    )
    parser.add_argument("--config", required=True,
                        help=f"County config name ({', '.join(available)})")
    parser.add_argument("--sample-size", type=int, default=20,
                        help="Permits per type to sample (default 20)")
    parser.add_argument("--other-only", action="store_true",
                        help="Only check 'other' permits (fastest way to find missing patterns)")
    args = parser.parse_args()

    key = os.getenv("OPEN_AI_API_KEY")
    if not key:
        print("ERROR: Set OPEN_AI_API_KEY environment variable")
        sys.exit(1)

    from openai import OpenAI
    client = OpenAI(api_key=key)

    from pipeline_config import load_config
    config = load_config(args.config)

    # Load and filter to regrid-matched straps
    permits_path = config.parsed_permits_path
    regrid_path = config.regrid_filtered_path
    if not permits_path.exists() or not regrid_path.exists():
        print(f"ERROR: Run parse_permits.py and the pipeline first")
        sys.exit(1)

    permits = pd.read_csv(permits_path, low_memory=False)
    regrid = pd.read_csv(regrid_path, low_memory=False, usecols=["strap"])
    permits["strap"] = permits["strap"].astype(str)
    regrid["strap"] = regrid["strap"].astype(str)
    regrid_straps = set(regrid["strap"].unique())
    permits = permits[permits["strap"].isin(regrid_straps)].copy()

    print(f"AI Cross-Check: {config.county_id}")
    print(f"Permits (regrid-matched): {len(permits):,}")

    # Sample
    sample = sample_permits(permits, args.sample_size, args.other_only)
    print(f"Sample size: {len(sample)}")
    print()

    # Classify each
    results = []
    for i, (_, row) in enumerate(sample.iterrows()):
        ai_result = classify_with_ai(client, row)
        results.append({
            "strap": row["strap"],
            "permit_num": row.get("permit_num"),
            "permit_category": row.get("permit_category"),
            "description": row.get("description"),
            "estimated_value": row.get("estimated_value"),
            "rule_type": row["permit_type"],
            "ai_type": ai_result["permit_type"],
            "ai_confidence": ai_result.get("confidence", ""),
            "ai_reasoning": ai_result.get("reasoning", ""),
            # AI returns a single type; agree if it's in the rule's comma-separated set
            "agrees": ai_result["permit_type"] in [t.strip() for t in row["permit_type"].split(",")],
        })
        if (i + 1) % 50 == 0:
            print(f"  Processed {i+1}/{len(sample)}...")

    results_df = pd.DataFrame(results)

    # Save CSV
    validation_dir = config.data_dir / "validation"
    validation_dir.mkdir(parents=True, exist_ok=True)
    output_path = validation_dir / "ai_review.csv"
    results_df.to_csv(output_path, index=False)

    # --- Report ---
    n_agree = results_df["agrees"].sum()
    n_total = len(results_df)
    print(f"\n{'='*70}")
    print(f"RESULTS")
    print(f"{'='*70}")
    print(f"\n  Overall agreement: {n_agree}/{n_total} ({n_agree/n_total*100:.1f}%)")

    # Per-type agreement
    print(f"\n  {'Type':<20} {'Sampled':>8} {'Agree':>8} {'Rate':>8}")
    print(f"  {'-'*20} {'-'*8} {'-'*8} {'-'*8}")
    for ptype in sorted(results_df["rule_type"].unique()):
        subset = results_df[results_df["rule_type"] == ptype]
        agree = subset["agrees"].sum()
        rate = agree / len(subset) * 100
        print(f"  {ptype:<20} {len(subset):>8} {agree:>8} {rate:>7.0f}%")

    # Disagreements
    disagreements = results_df[~results_df["agrees"]]
    if len(disagreements) > 0:
        print(f"\n  {'='*60}")
        print(f"  DISAGREEMENTS ({len(disagreements)})")
        print(f"  {'='*60}")

        # Group by (rule_type, ai_type)
        pair_counts = disagreements.groupby(["rule_type", "ai_type"]).size().sort_values(ascending=False)
        print(f"\n  Disagreement patterns (rule -> AI):")
        for (rule, ai), count in pair_counts.items():
            print(f"    {count:>4}x  {rule} -> {ai}")

        # High-confidence disagreements
        high_conf = disagreements[disagreements["ai_confidence"] == "high"]
        if len(high_conf) > 0:
            print(f"\n  ** {len(high_conf)} HIGH-CONFIDENCE disagreements (review first):")
            for _, row in high_conf.iterrows():
                desc = str(row["description"])[:80] if pd.notna(row["description"]) else "(no desc)"
                print(f"    rule={row['rule_type']}, ai={row['ai_type']}: {desc}")
                print(f"      AI reasoning: {row['ai_reasoning']}")
        else:
            print(f"\n  No high-confidence disagreements")

        # Missed patterns (rule=other, AI disagrees)
        missed = disagreements[disagreements["rule_type"].str.strip() == "other"]
        if len(missed) > 0:
            print(f"\n  Potential MISSED PATTERNS (rule=other, AI says otherwise): {len(missed)}")
            ai_type_counts = missed["ai_type"].value_counts()
            for ai_type, count in ai_type_counts.items():
                print(f"    {count}x AI says '{ai_type}'")
    else:
        print(f"\n  No disagreements — perfect agreement!")

    print(f"\n  Full results saved to: {output_path}")
    print()


if __name__ == "__main__":
    main()
