"""
Feature logic for permit parsing. Uses both permit_category and description
to classify permits. Designed for predicting solar panel sales.
"""

import pandas as pd

# ============================================================
# CATEGORY PATTERNS (permit_category is a strong signal)
# ============================================================

# Categories that map directly to features (case-insensitive substring match)
CATEGORY_MATCHES = {
    "solar_pv": ["energy efficient system", "solar", "photovoltaic", "pv system"],
    "roof_new_or_replace": ["re-roof", "reroof", "residential re-roof", "commercial re-roof"],
    "ac": ["air conditioner"],
    "water_heater": ["water heater"],  # Base category; subtype from description
    "windows_doors": ["windows or doors", "windows", "doors"],
    "evaporative_cooler": ["evaporative cooler"],
    "pool_hot_tub": ["pool", "hot tub", "spa"],
    "electrical_mechanical": ["electrical/mechanical", "electrical"],
}

# ============================================================
# DESCRIPTION PATTERNS (regex on combined permit_category + description)
# ============================================================

# Use (?:...) for non-capturing groups to avoid pandas str.contains warnings
DESC_PATTERNS = {
    # Solar PV - exclude solar thermal / solar water heater
    "solar_pv": (
        r"\b(?:solar\s*(?:pv|panel|array|system|installation|mount)|pv\s*(?:solar|system|array)|"
        r"photovoltaic|photo\-voltaic|solar\s*electric)\b"
    ),
    # When solar thermal is suspected, solar_pv requires explicit "pv" or "photovoltaic"
    "solar_thermal_suspected": (
        r"solar\s*(?:water|hot\s*water|thermal)\s*heater|solar\s*heater\s*tank|"
        r"solar\s*thermal|solar\s*hot\s*water|solar\s*heating|"
        r"thermal\s*panel|thermal\s*collector|solar\s*thermal\s*panel"
    ),
    "solar_pv_requires_pv": r"\b(?:pv|photovoltaic|photo\-voltaic)\b",

    # Battery / storage
    "battery": r"\b(?:powerwall|battery\s*storage|energy\s*storage|ess|bms)\b",

    # EV charging
    "ev_charger": (
        r"\b(?:ev\s*charger|electric\s*vehicle\s*charger|tesla\s*(?:wall\s*)?connector|"
        r"chargepoint|juicebox|wallbox|level\s*2\s*charg|evse)\b"
    ),

    # Roofing
    "roof_new_or_replace": (
        r"\b(?:roof\s*replace|re\-roof|reroof|roofing|new\s*roof|tear\s*off|"
        r"shingle|underlayment|tear\s*off\s*&?\s*reroof)\b"
    ),

    # Electrical
    "electrical_service_upgrade": (
        r"\b(?:service\s*upgrade|panel\s*upgrade|main\s*panel|meter\s*main|"
        r"new\s*panel|electrical\s*service|200\s*amp|solar\s*ready)\b"
    ),

    # HVAC - separated
    "heat_pump": r"\b(?:heat\s*pump|mini\s*split|minisplit|ductless)\b",
    "ac": r"\b(?:air\s*condition(?:er|ing)|\ba\/c\b|a\.c\.|ac\s*unit|condenser)\b",
    "furnace": r"\b(?:furnace|boiler)\b",

    # Water heater - by type (mutually exclusive where possible)
    "water_heater_electric": (
        r"\b(?:electric\s*water\s*heater|heat\s*pump\s*water\s*heater|"
        r"hpwh|hybrid\s*water\s*heater|electric\s*(?:\d+\s*gal\s*)?water\s*heater)\b"
    ),
    "water_heater_gas": (
        r"\b(?:gas\s*water\s*heater|ng\s*water\s*heater|natural\s*gas\s*water\s*heater|"
        r"propane\s*water\s*heater|\d+\s*gal\s*gas\s*water\s*heater|"
        r"water\s*heater\s*gas)\b"
    ),
    "water_heater_solar_thermal": (
        r"\b(?:solar\s*water\s*heater|solar\s*hot\s*water|solar\s*thermal)\b"
    ),
    "water_heater": r"\b(?:water\s*heater|tankless|on\-demand)\b",  # Generic fallback

    # Envelope
    "windows_doors": r"\b(window(?:s)?|door(?:s)?|patio\s*door|sliding\s*door)\b",
    "insulation_airseal": (
        r"\b(?:insulation|air\s*seal|air\-seal|weatherization|attic\s*insulation)\b"
    ),

    # Other solar-relevant
    "generator": r"\b(?:generator|genset)\b",
    "addition_new_build": (
        r"\b(?:addition|new\s*construction|new\s*build|adu|accessory\s*dwelling)\b"
    ),
    "kitchen_bath_remodel": r"\b(?:kitchen|bath(?:room)?|remodel|renovation)\b",
    "pool_hot_tub": r"\b(pool|hot\s*tub|spa)\b",
    "evaporative_cooler": r"\b(?:evaporative\s*cooler|swamp\s*cooler)\b",
}


def _cat_matches(cat: pd.Series, keywords: list) -> pd.Series:
    """True where permit_category contains any of the keywords (case-insensitive)."""
    cat_lower = cat.str.lower()
    result = pd.Series(False, index=cat.index)
    for kw in keywords:
        result = result | cat_lower.str.contains(kw, regex=False, na=False)
    return result


def _desc_matches(text: pd.Series, pattern: str, exclude: str | None = None) -> pd.Series:
    """True where text matches pattern. If exclude, also require no match on exclude."""
    match = text.str.contains(pattern, regex=True, na=False)
    if exclude:
        match = match & ~text.str.contains(exclude, regex=True, na=False)
    return match


def compute_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute all feature flags from permit data.
    Returns a DataFrame with strap + feature columns (0/1).
    """
    df = df.copy()
    df["strap"] = df["strap"].astype(str)
    df["permit_category"] = df["permit_category"].fillna("").astype(str)
    df["description"] = df["description"].fillna("").astype(str)

    cat = df["permit_category"]
    text = (cat + " " + df["description"]).str.lower()

    features = {}

    # --- Solar PV: category (ENERGY EFFICIENT SYSTEM + solar in desc) or description
    # When solar thermal/water heating is suspected, require explicit "pv" or "photovoltaic"
    # to avoid double-counting thermal systems as PV
    solar_thermal_suspected = text.str.contains(
        DESC_PATTERNS["solar_thermal_suspected"], regex=True, na=False
    )
    has_pv_or_photovoltaic = text.str.contains(
        DESC_PATTERNS["solar_pv_requires_pv"], regex=True, na=False
    )
    solar_pv_raw = (
        _cat_matches(cat, ["energy efficient system"]) & text.str.contains("solar|pv|photovoltaic", regex=True, na=False)
    ) | _desc_matches(text, DESC_PATTERNS["solar_pv"])
    features["solar_pv"] = solar_pv_raw & (
        ~solar_thermal_suspected | has_pv_or_photovoltaic
    )

    # --- Battery
    features["battery"] = _desc_matches(text, DESC_PATTERNS["battery"])

    # --- EV charger
    features["ev_charger"] = _desc_matches(text, DESC_PATTERNS["ev_charger"])

    # If EV charger or battery is detected, remove solar_pv flag
    # (e.g. category="Solar" but description="level 2 charger for EV")
    features["solar_pv"] = features["solar_pv"] & ~features["ev_charger"] & ~features["battery"]

    # --- Roof
    features["roof_new_or_replace"] = (
        _cat_matches(cat, CATEGORY_MATCHES["roof_new_or_replace"])
        | _desc_matches(text, DESC_PATTERNS["roof_new_or_replace"])
    )

    # --- Electrical
    features["electrical_service_upgrade"] = _desc_matches(
        text, DESC_PATTERNS["electrical_service_upgrade"]
    )

    # --- HVAC: heat pump (HVAC only; exclude heat pump water heater)
    hp_pattern = r"\b(?:heat\s*pump|mini\s*split|minisplit|ductless)\b"
    hp_exclude = r"heat\s*pump\s*water\s*heater|hpwh"
    features["heat_pump"] = _desc_matches(text, hp_pattern, hp_exclude)

    # --- AC: category or description
    features["ac"] = _cat_matches(cat, ["air conditioner"]) | _desc_matches(
        text, DESC_PATTERNS["ac"]
    )

    # --- Furnace
    features["furnace"] = (
        _cat_matches(cat, ["heating system"]) & _desc_matches(text, DESC_PATTERNS["furnace"])
    ) | (_desc_matches(text, DESC_PATTERNS["furnace"]) & ~features["heat_pump"])

    # --- Water heater types
    features["water_heater_electric"] = (
        _cat_matches(cat, ["water heater"]) & _desc_matches(text, DESC_PATTERNS["water_heater_electric"])
    ) | _desc_matches(text, DESC_PATTERNS["water_heater_electric"])
    features["water_heater_gas"] = (
        _cat_matches(cat, ["water heater"]) & _desc_matches(text, DESC_PATTERNS["water_heater_gas"])
    ) | _desc_matches(text, DESC_PATTERNS["water_heater_gas"])
    features["water_heater_solar_thermal"] = _desc_matches(
        text, DESC_PATTERNS["water_heater_solar_thermal"]
    )
    # Generic water heater (any water heater permit)
    features["water_heater"] = (
        _cat_matches(cat, ["water heater"]) | _desc_matches(text, DESC_PATTERNS["water_heater"])
    )

    # --- Envelope
    features["windows_doors"] = (
        _cat_matches(cat, CATEGORY_MATCHES["windows_doors"])
        | _desc_matches(text, DESC_PATTERNS["windows_doors"])
    )
    features["insulation_airseal"] = _desc_matches(text, DESC_PATTERNS["insulation_airseal"])

    # --- Other
    features["generator"] = _desc_matches(text, DESC_PATTERNS["generator"])
    features["addition_new_build"] = (
        _cat_matches(cat, ["addition", "new construction"]) | _desc_matches(text, DESC_PATTERNS["addition_new_build"])
    )
    features["kitchen_bath_remodel"] = _desc_matches(text, DESC_PATTERNS["kitchen_bath_remodel"])
    features["pool_hot_tub"] = (
        _cat_matches(cat, ["pool", "hot tub", "spa"]) | _desc_matches(text, DESC_PATTERNS["pool_hot_tub"])
    )
    features["evaporative_cooler"] = (
        _cat_matches(cat, ["evaporative cooler"]) | _desc_matches(text, DESC_PATTERNS["evaporative_cooler"])
    )

    # Build result
    result = pd.DataFrame({k: v.astype(int) for k, v in features.items()})
    result.insert(0, "strap", df["strap"].values)

    return result


def get_feature_names() -> list[str]:
    """Return ordered list of feature names (excluding strap)."""
    return [
        "solar_pv",
        "battery",
        "ev_charger",
        "roof_new_or_replace",
        "electrical_service_upgrade",
        "heat_pump",
        "ac",
        "furnace",
        "water_heater",
        "water_heater_electric",
        "water_heater_gas",
        "water_heater_solar_thermal",
        "windows_doors",
        "insulation_airseal",
        "generator",
        "addition_new_build",
        "kitchen_bath_remodel",
        "pool_hot_tub",
        "evaporative_cooler",
    ]
