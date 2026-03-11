
### AI you are forbidden from executing this script ###

"""
Simple email enrichment via People Data Labs Person Enrichment API.

Reads an input CSV with a single owner field and addresses. Uses
parse_owner_names to split into 1 or 2 people, then calls PDL for each.
Writes results to a separate output file.

Usage:
    export PDL_API_KEY="your_key_here"
    python src/enrich_emails_simple.py
"""

from __future__ import annotations

import os
import sys
import time

import pandas as pd
import requests
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(__file__))
from parse_owner_names import parse_owner_name

load_dotenv()

# ── CONFIGURATION ────────────────────────────────────────────────────────────
INPUT_CSV = "/Users/jeffs/Documents/BryansHomes.csv"
OUTPUT_CSV = "/Users/jeffs/Projects/SolarProject/data/final/email_enrichment_results.csv"
API_CALL_LIMIT = 50
OWNER_COL = "owner"         #parses out owners                                                                                      
ADDRESS_COL = "mailadd"                                      
CITY_COL = "mail_city"                                                                                            
STATE_COL = "mail_state2"                                                                                       
ZIP_COL = "mail_zip"  
# ─────────────────────────────────────────────────────────────────────────────

PDL_API_URL = "https://api.peopledatalabs.com/v5/person/enrich"
RATE_LIMIT_DELAY = 0.5  # seconds between calls


def get_api_key() -> str:
    key = os.environ.get("PDL_API_KEY", "")
    if not key:
        print("Error: PDL_API_KEY not set. Export it or add to .env")
        sys.exit(1)
    return key


def lookup_emails(api_key: str, first_name: str, last_name: str,
                  address: str, city: str, state: str, zip_code: str) -> list[str]:
    """Call PDL and return a list of email addresses (personal first, then work)."""
    params = {
        "api_key": api_key,
        "first_name": first_name,
        "last_name": last_name,
        "street_address": address,
        "locality": city,
        "region": state,
        "postal_code": str(zip_code)[:5] if zip_code else "",
        "min_likelihood": 2,
    }
    params = {k: v for k, v in params.items() if v and str(v) != "nan"}

    try:
        resp = requests.get(PDL_API_URL, params=params, timeout=15)
        if resp.status_code == 200:
            data = resp.json().get("data", {})
            emails = data.get("emails", [])
            personal = [e["address"] for e in emails if e.get("type") == "personal"]
            work = [e["address"] for e in emails if e.get("type") != "personal"]
            return personal + work
        elif resp.status_code == 404:
            return []
        elif resp.status_code == 429:
            print("  Rate limited, waiting 10s...")
            time.sleep(10)
            return lookup_emails(api_key, first_name, last_name,
                                 address, city, state, zip_code)
        else:
            print(f"  API error {resp.status_code}: {resp.text[:200]}")
            return []
    except requests.RequestException as e:
        print(f"  Request failed: {e}")
        return []


def main():
    df = pd.read_csv(INPUT_CSV)
    print(f"Loaded {len(df)} rows from {INPUT_CSV}")

    # Load existing output to skip already-enriched rows
    if os.path.exists(OUTPUT_CSV):
        out_df = pd.read_csv(OUTPUT_CSV)
        already_done = set(out_df.index.tolist())
        print(f"Found {len(already_done)} already-enriched rows in {OUTPUT_CSV}")
    else:
        out_df = df.copy()
        for col in ["owner_1_name", "owner_1_email_1", "owner_1_email_2",
                     "owner_2_name", "owner_2_email_1", "owner_2_email_2"]:
            out_df[col] = ""
        already_done = set()

    api_key = get_api_key()

    # Find rows that still need enrichment
    needs_enrichment = [
        i for i in range(len(df))
        if i not in already_done or not out_df.at[i, "owner_1_name"]
    ]

    print(f"{len(needs_enrichment)} rows need enrichment, limit is {API_CALL_LIMIT} API calls")

    api_calls = 0

    for idx in needs_enrichment:
        if api_calls >= API_CALL_LIMIT:
            print(f"\nReached API call limit ({API_CALL_LIMIT}). "
                  f"Re-run to continue from where you left off.")
            break

        row = df.loc[idx]
        owner_raw = str(row.get(OWNER_COL, ""))
        address = str(row.get(ADDRESS_COL, ""))
        city = str(row.get(CITY_COL, ""))
        state = str(row.get(STATE_COL, ""))
        zip_code = str(row.get(ZIP_COL, ""))

        # Parse the single owner field into 1 or 2 people
        parsed_names = parse_owner_name(owner_raw)

        if not parsed_names:
            print(f"[--] Row {idx}: couldn't parse '{owner_raw}', skipping")
            continue

        # ── Owner 1 ──────────────────────────────────────────────
        name1 = parsed_names[0]
        out_df.at[idx, "owner_1_name"] = f"{name1.first_name} {name1.last_name}"

        if name1.first_name and name1.last_name:
            print(f"[{api_calls+1}/{API_CALL_LIMIT}] Row {idx}: "
                  f"{name1.first_name} {name1.last_name} — "
                  f"{address}, {city} {state} {zip_code}")

            emails = lookup_emails(api_key, name1.first_name, name1.last_name,
                                   address, city, state, zip_code)
            api_calls += 1

            if emails:
                out_df.at[idx, "owner_1_email_1"] = emails[0]
                if len(emails) > 1:
                    out_df.at[idx, "owner_1_email_2"] = emails[1]
                print(f"  -> {emails[0]}" + (f", {emails[1]}" if len(emails) > 1 else ""))
            else:
                print(f"  -> no match")

            time.sleep(RATE_LIMIT_DELAY)

        # ── Owner 2 (if exists) ──────────────────────────────────
        if len(parsed_names) < 2 or api_calls >= API_CALL_LIMIT:
            continue

        name2 = parsed_names[1]
        out_df.at[idx, "owner_2_name"] = f"{name2.first_name} {name2.last_name}"

        if name2.first_name and name2.last_name:
            print(f"[{api_calls+1}/{API_CALL_LIMIT}] Row {idx}: "
                  f"{name2.first_name} {name2.last_name} (owner 2)")

            emails = lookup_emails(api_key, name2.first_name, name2.last_name,
                                   address, city, state, zip_code)
            api_calls += 1

            if emails:
                out_df.at[idx, "owner_2_email_1"] = emails[0]
                if len(emails) > 1:
                    out_df.at[idx, "owner_2_email_2"] = emails[1]
                print(f"  -> {emails[0]}" + (f", {emails[1]}" if len(emails) > 1 else ""))
            else:
                print(f"  -> no match")

            time.sleep(RATE_LIMIT_DELAY)

    # Save to output file
    out_df.to_csv(OUTPUT_CSV, index=False)

    # Summary
    has_email = (out_df["owner_1_email_1"].notna() & (out_df["owner_1_email_1"] != "")).sum()
    print(f"\nDone. {api_calls} API calls used.")
    print(f"{has_email} / {len(out_df)} rows have at least one email.")
    print(f"Results saved to {OUTPUT_CSV}")


if __name__ == "__main__":
    main()
