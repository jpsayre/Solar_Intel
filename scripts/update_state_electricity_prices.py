#!/usr/bin/env python3
"""
Update state_electricity_prices table in Supabase with monthly electricity costs by US state.

Fetches residential average retail price (cents/kWh) from EIA API v2 retail-sales endpoint,
then upserts into Supabase. Run monthly (e.g. via cron) to keep data current.

Environment variables (set in .env or os env):
  EIA_DEVELOPER_API_KEY   - EIA Open Data API key (free at https://www.eia.gov/opendata/)
  SUPABASE_URL            - Supabase project URL
  SUPABASE_SERVICE_ROLE_KEY - Service role key (bypasses RLS for writes)

Usage:
  python scripts/update_state_electricity_prices.py          # incremental (default)
  python scripts/update_state_electricity_prices.py --full   # full backfill from 2010 (ignores existing data)
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Add project root for imports if needed
PROJECT_ROOT = Path(__file__).resolve().parents[1]

# Step 4: Load env vars from .env or ~/.zshrc (EIA_DEVELOPER_API_KEY, SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
try:
    from dotenv import load_dotenv
    # Try .zshrc first (where many users keep keys), then project .env (overrides)
    load_dotenv(Path.home() / ".zshrc")
    load_dotenv(PROJECT_ROOT / ".env")
except ImportError:
    pass  # dotenv optional; use os env vars directly
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    import requests
except ImportError:
    print("Install requests: pip install requests")
    sys.exit(1)

try:
    from supabase import create_client
except ImportError:
    print("Install supabase: pip install supabase")
    sys.exit(1)

EIA_BASE = "https://api.eia.gov/v2/electricity/retail-sales"
# Only include 2-letter state codes (exclude US, DC, and regional codes like WNC, ESC)
US_STATE_CODES = frozenset(
    "AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY DC".split()
)


# Historical start: EIA retail-sales has data back to ~2001
HISTORICAL_START = "2010-01"

def fetch_eia_prices(api_key: str, start_str: str, end_str: str) -> list[dict]:
    """Fetch residential electricity prices by state from EIA API for the given date range."""
    # EIA: start=last-day-of-prior-month to include first month; end=first-of-month-after-last to include last
    # start_str/end_str are YYYY-MM-DD (first of month). Convert start to prior month's last day.
    start_dt = datetime.strptime(start_str[:7] + "-01", "%Y-%m-%d")  # YYYY-MM-01
    start_eia = (start_dt - timedelta(days=1)).strftime("%Y-%m-%d")
    # end_str is first of month; EIA needs first of next month to include it. Add 1 month.
    end_dt = datetime.strptime(end_str[:7] + "-01", "%Y-%m-%d")
    if end_dt.month == 12:
        end_eia_dt = datetime(end_dt.year + 1, 1, 1)
    else:
        end_eia_dt = datetime(end_dt.year, end_dt.month + 1, 1)
    end_eia = end_eia_dt.strftime("%Y-%m-%d")

    params = {
        "api_key": api_key,
        "data[]": "price",
        "facets[sectorid][]": "RES",
        "frequency": "monthly",
        "start": start_eia,
        "end": end_eia,
        "length": 5000,
        "sort[0][column]": "period",
        "sort[0][direction]": "desc",
    }

    all_data: list[dict] = []
    offset = 0

    while True:
        params["offset"] = offset
        r = requests.get(f"{EIA_BASE}/data", params=params, timeout=30)
        r.raise_for_status()
        j = r.json()

        if "error" in j:
            raise RuntimeError(f"EIA API error: {j['error']}")

        data = j.get("response", {}).get("data", [])
        if not data:
            break

        for row in data:
            state_id = row.get("stateid", "")
            if state_id in US_STATE_CODES:
                period_str = row.get("period", "")
                price_str = row.get("price", "0")
                try:
                    price = float(price_str)
                except (ValueError, TypeError):
                    continue
                if period_str and price > 0:
                    # period is YYYY-MM
                    year, month = int(period_str[:4]), int(period_str[5:7])
                    period_date = f"{year}-{month:02d}-01"
                    all_data.append({
                        "state_code": state_id,
                        "period": period_date,
                        "price_cents_per_kwh": round(price, 4),
                        "sector_id": "RES",
                        "state_name": row.get("stateDescription"),
                    })

        total = int(j.get("response", {}).get("total", 0))
        offset += len(data)
        if offset >= total or len(data) < 5000:
            break

    return all_data


def get_max_period(url: str, service_key: str) -> str | None:
    """Return the most recent period (YYYY-MM-01) in the table, or None if empty."""
    client = create_client(url, service_key)
    result = client.table("state_electricity_prices").select("period").order("period", desc=True).limit(1).execute()
    if result.data and len(result.data) > 0:
        p = result.data[0].get("period")
        if p:
            s = p[:10] if isinstance(p, str) else (p.strftime("%Y-%m-%d") if hasattr(p, "strftime") else str(p)[:10])
            return s[:7] + "-01"  # normalize to YYYY-MM-01
    return None


def upsert_to_supabase(rows: list[dict], url: str, service_key: str) -> int:
    """Upsert rows into state_electricity_prices. Returns count upserted."""
    client = create_client(url, service_key)

    # Supabase upsert: on_conflict on (state_code, period)
    result = client.table("state_electricity_prices").upsert(
        rows,
        on_conflict="state_code,period",
    ).execute()

    return len(rows)


def main() -> int:
    api_key = os.environ.get("EIA_DEVELOPER_API_KEY")
    supabase_url = os.environ.get("SUPABASE_URL")
    supabase_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")

    missing = []
    if not api_key:
        missing.append("EIA_DEVELOPER_API_KEY")
    if not supabase_url:
        missing.append("SUPABASE_URL")
    if not supabase_key:
        missing.append("SUPABASE_SERVICE_ROLE_KEY")

    if missing:
        print(f"Missing env vars: {', '.join(missing)}")
        print("Get EIA key: https://www.eia.gov/opendata/")
        print("Supabase keys: Project Settings → API")
        return 1

    # Incremental: fetch from 2010 on first run, or from month after last stored period
    # Use --full to force full backfill from 2010 (e.g. after clearing table or fixing data)
    force_full = "--full" in sys.argv
    max_period = None if force_full else get_max_period(supabase_url, supabase_key)
    now = datetime.now()
    end_str = datetime(now.year, now.month, 1).strftime("%Y-%m-%d")  # last full month

    if max_period:
        # Next month after max_period
        year, month = int(max_period[:4]), int(max_period[5:7])
        if month == 12:
            start_dt = datetime(year + 1, 1, 1)
        else:
            start_dt = datetime(year, month + 1, 1)
        start_str = start_dt.strftime("%Y-%m-%d")
        if start_str > end_str:
            print("Already up to date (last period covers through last full month).")
            return 0
        print(f"Fetching new data from {start_str[:7]} through {end_str[:7]}...")
    else:
        start_str = HISTORICAL_START + "-01"
        print(f"Initial backfill: fetching from {HISTORICAL_START} through {end_str[:7]}...")

    rows = fetch_eia_prices(api_key, start_str, end_str)
    if not rows:
        print("No data returned from EIA")
        return 1

    print(f"Upserting {len(rows)} rows to Supabase...")
    upsert_to_supabase(rows, supabase_url, supabase_key)
    print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
