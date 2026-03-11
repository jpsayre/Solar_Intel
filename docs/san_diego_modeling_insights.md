# San Diego Modeling Session — Insights & Decisions (2026-03-09)

## Walk-Forward Model Architecture

### Removed Strap-Based Train/Test Split
The original pipeline held out 20% of homes (straps) for testing within each walk-forward fold. This was unnecessary — in a pure walk-forward design, the temporal separation IS the validation:
- **Train**: all homes in prior years (expanding or rolling window)
- **Test**: all homes in the prediction year

No need to withhold homes. Every home trains on the past and is tested on the future.

### Per-Year Feature Selection (Restored)
Initially switched to one-time feature selection for speed. Reverted to per-year selection so the model can adapt as data evolves — early years pick up different signals than later years when neighbor contagion is stronger.

---

## Feature Selection Improvements

### Problem: Age Feature Domination
`calculated_roof_age` consistently scored importance=1.0, and 8-10 of 25 selected features were age proxies (yearbuilt, calculated_build_year, census_vs_property_age, time_since_build_bin_* one-hot bins). These are all measuring the same thing — building age — but the correlation filter didn't catch the one-hot bins (they're mutually exclusive, not correlated with each other).

### Solution: Three-Layer Feature Filtering

**1. Feature Group Caps (max 2 per group)**
Defined three conceptual groups with a maximum of 2 features each:
- `building_age`: calculated_roof_age, calculated_build_year, yearbuilt, census_vs_property_age, median_year_built, all time_since_build_bin_*, recent_build
- `sale_recency`: time_since_sale, recent_purchase, all time_since_sale_bin_*
- `neighbor_contagion`: all count_*mi, last_year_neighbors_*, closest_fifty_percentage, solar_neighbor_momentum, and interaction terms

This forces diversification — once 2 age features are selected, the remaining slots go to genuinely different signals.

**2. Correlation Dedup (r > 0.80)**
After group caps, any remaining feature with |r| > 0.80 against an already-selected feature is skipped. Catches things like calculated_build_year vs yearbuilt (r=0.99).

**3. Minimum Prevalence Filter (2%)**
Features with <2% non-zero rows are dropped before selection. Prevents rare/broken features from entering the model. Catches sparse permit features that don't have enough signal to learn from.

### Result
Feature selection went from 8-10 age features + 3-4 sale features to exactly 2+2+2 from capped groups, freeing ~10 slots for permits, census, economics, and mortgage data.

---

## Leakage Investigation: calculated_roof_age

**Concern**: `calculated_roof_age` is the #1 feature with importance=1.0. Is it leaking information via roof replacements done for solar installation?

**Finding: No leakage.**
- Only 33 out of 2,151 solar homes (1.5%) had ANY roof permit
- 28 of those 33 roof permits were in the SAME year as solar (not the feature year before)
- `calculated_roof_age` equals `year - calculated_build_year` for 94.4% of rows
- It's just building age with a different name — not leaky, just redundant

---

## Temporal-Only Diagnostic (Key Finding)

Ran the model with ONLY time-varying features (no static home characteristics like yearbuilt, sqft, saleprice, census demographics). Purpose: determine how much signal comes from temporal dynamics vs. static home profiles.

### Results: Neighbor Contagion IS the Signal

| Year | Full Model ROC | Temporal-Only ROC | Full Lift@5% | Temporal Lift@5% |
|------|---------------|-------------------|-------------|-----------------|
| 2022 | 0.9741 | 0.9256 | 16.26x | 6.16x |
| 2023 | 0.9596 | 0.9699 | 12.96x | 14.23x |
| 2024 | 0.9801 | 0.9777 | 17.13x | 16.48x |
| 2025 | 0.9632 | 0.9819 | 15.10x | 17.76x |

**Key insight**: In later years (2023+), the temporal-only model performs EQUALLY WELL or BETTER than the full model. The static features (income, home age, census) add almost nothing once you have the neighbor contagion signal.

The dominant temporal features:
1. `closest_fifty_percentage` — % of 50 nearest homes with solar
2. `count_1mi` / `last_year_neighbors_w_solar_1mi` — solar density within 1 mile
3. `battery` — energy-conscious homeowner signal
4. `electrical_service_upgrade` — possible solar prep
5. `likely_mortgage_rate` — macro timing

### Implication for Static Feature Concern
The concern was that static features create pseudo-overlap between train/test (same home appears in both with nearly identical features). The temporal-only run shows this is NOT inflating results — the model works just as well without static features.

---

## San Diego Permit Data Quality Issues

### Problem
Many permit features showed r=1.00 correlations (windows_doors, generator, insulation_airseal, ac, pool_hot_tub) — indicating they're all near-zero or constant.

### Root Cause
San Diego permit descriptions are much terser than Boulder's:
- Boulder: "window replacement, insulation upgrade, furnace install"
- San Diego: "No-Plan - Residential - Combination Mech/Elec/Plum"

Also: "AC" in San Diego permits usually means alternating current power ratings in solar permits ("5kW/AC"), not air conditioning.

### Features Effectively Broken in San Diego
| Feature | Matches | Issue |
|---------|---------|-------|
| evaporative_cooler | 0 | Doesn't exist in coastal CA |
| water_heater_electric | 13 | Near-zero |
| water_heater_gas | 29 | Near-zero |
| water_heater_solar_thermal | 8 | Near-zero |
| furnace | 180 | Too sparse |
| insulation_airseal | 192 | SD permits don't detail this |

### Mitigation
The 2% prevalence filter catches these automatically. Features with genuine signal (solar_pv, battery, roof_new_or_replace, electrical_service_upgrade) still clear the threshold. This approach is county-agnostic — broken features get filtered regardless of why they're broken.

---

## Commercial Viability Assessment

### The Core Insight
The model is essentially a sophisticated neighbor-density heatmap. "Homes near other solar homes will go solar" is the dominant signal. This is real, well-documented in academic literature, but not novel.

### What the Numbers Actually Mean
- 0.25% base adoption rate in San Diego
- 16x lift at top 5% = 4% adoption rate in best segment
- 96% of "top picks" still don't adopt
- 100% capture@10% sounds amazing but just means ranking ~250 adopters above the 90th percentile out of 100k homes

### Where the Value Lives
1. **Permit data is the differentiator** — not many competitors parse municipal permit records
2. **Clustering nearby high-ranked homes into canvassing routes** — operational value, not just data
3. **Interactive map** — transforms a CSV into a tool that justifies $9k/county pricing
4. **Roof scoring only top 10-15%** — reduces Sunroof API costs dramatically

### One-Off Product Economics
- Regrid: $150/county
- Sunroof API: limited to top 15% (~15k calls)
- Permit data: free where available (open data portals)
- Build time: 1-2 days/county once pipeline is automated
- Target: 30 counties × $9k = $270k potential revenue

### Most Likely Failure Modes (Pre-Mortem)
1. **Can't find buyers** — solar companies don't answer cold outreach, demos end with "let me think about it"
2. **Product tells them what they already know** — sales managers already know their hot neighborhoods from driving around
3. **Data staleness** — permits lag 3-6 months, neighbor counts reflect last year
4. **Undercut by free tools** — Aurora Solar or similar launches free targeting as a loss leader
5. **Seasonal timing** — solar companies buy in Q1 for spring/summer; launching mid-year misses the window

### Kill Signal
After 3 weeks of outreach: if you can't get demos, demos don't close, or first buyer says "this is what we expected" — kill it.

### Product-Market Fit Signal
A buyer asks "can you do this for our other territories?"

---

## Technical Changes Made (walk_forward_fast.py)

1. Removed strap-based 80/20 split — pure temporal walk-forward
2. Per-year feature selection instead of one-time
3. Feature group caps (max 2 per group: building_age, sale_recency, neighbor_contagion)
4. Correlation dedup (r > 0.80 threshold)
5. Minimum prevalence filter (2% non-zero)
6. `--temporal-only` flag for diagnostic runs (strips static features)
7. Full feature list printed per year with importance scores

## Technical Changes Made (create_parsed_permits_by_year.py)

1. Switched from blocklist to allowlist for Regrid columns (12 clean columns)
2. Roof score skip when <10% coverage
3. Electricity data state validation
4. Skip neighbor computation for years before first solar permit
5. Trim output to exclude empty pre-data years
