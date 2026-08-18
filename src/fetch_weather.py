"""Fetch daily temperature history from Open-Meteo and load it into
fact_weather_daily.

WHY this exists: weather (specifically temperature) is the second data
source that lets Phase 3's analyses (cooling-load regression, heatwave
correlation) explain *why* demand spikes, not just *that* it spiked.

WHY 8 cities as state proxies, not all 34 states: Open-Meteo needs a
lat/lon per point, and daily state-level temperature isn't published
anywhere free — one representative city per major state is the standard
approximation used for this kind of demand-weather analysis.
"""

import argparse
import sys
import time
from pathlib import Path

import pandas as pd
import requests
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

sys.path.insert(0, str(Path(__file__).parent))
from load_db import apply_schema

ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
START_DATE = "2020-01-01"
END_DATE = "2025-03-31"

# WHY these ids are hardcoded and flagged UNVERIFIED: dim_state.state_id is
# a SERIAL assigned when load_db.py first seeded the table, in the exact
# insertion order of its STATE_REGION dict. These values are read off that
# same order (NR block, then WR, then SR, then ER, then NER) rather than
# looked up live, because the DB was unreachable (port 5432 blocked on this
# network) when this file was written. They are NOT confirmed against the
# real database yet.
#
# UNVERIFIED — CONFIRM AGAINST DB before trusting this mapping:
#   Delhi=2, Uttar Pradesh=8 (from the NR block: Chandigarh=1, Delhi=2,
#     Haryana=3, Himachal Pradesh=4, J&K and Ladakh=5, Punjab=6,
#     Rajasthan=7, Uttar Pradesh=8, Uttarakhand=9)
#   Gujarat=14, Maharashtra=16 (from the WR block starting at 10:
#     Chhattisgarh=10, Dadra and Nagar Haveli=11, Daman and Diu=12, Goa=13,
#     Gujarat=14, Madhya Pradesh=15, Maharashtra=16)
#   Karnataka=18, Tamil Nadu=21 (from the SR block starting at 17:
#     Andhra Pradesh=17, Karnataka=18, Kerala=19, Puducherry=20,
#     Tamil Nadu=21, Telangana=22)
#   Odisha=25, West Bengal=27 (from the ER block starting at 23:
#     Bihar=23, Jharkhand=24, Odisha=25, Sikkim=26, West Bengal=27)
#
# load_weather() re-verifies every (state_id, state_name) pair against the
# live dim_state table before writing a single row, and raises loudly if
# any of these guesses is wrong — so a bad guess here fails the run
# instead of silently loading weather for the wrong state.
CITY_COORDS = {
    "Delhi": {"lat": 28.6139, "lon": 77.2090, "state_id": 2, "state_name": "Delhi"},
    "Mumbai": {"lat": 19.0760, "lon": 72.8777, "state_id": 16, "state_name": "Maharashtra"},
    "Chennai": {"lat": 13.0827, "lon": 80.2707, "state_id": 21, "state_name": "Tamil Nadu"},
    "Kolkata": {"lat": 22.5726, "lon": 88.3639, "state_id": 27, "state_name": "West Bengal"},
    "Bengaluru": {"lat": 12.9716, "lon": 77.5946, "state_id": 18, "state_name": "Karnataka"},
    "Ahmedabad": {"lat": 23.0225, "lon": 72.5714, "state_id": 14, "state_name": "Gujarat"},
    "Lucknow": {"lat": 26.8467, "lon": 80.9462, "state_id": 8, "state_name": "Uttar Pradesh"},
    "Bhubaneswar": {"lat": 20.2961, "lon": 85.8245, "state_id": 25, "state_name": "Odisha"},
}

FAILED_LOG = Path("data/raw/weather_fetch_failures.txt")


def fetch_city(city: str, coords: dict, since: str | None) -> pd.DataFrame | None:
    """Call Open-Meteo for one city. Return None (and log) on failure —
    never raise, so one bad city doesn't kill the whole run."""
    params = {
        "latitude": coords["lat"],
        "longitude": coords["lon"],
        "start_date": since or START_DATE,
        "end_date": END_DATE,
        "daily": "temperature_2m_max,temperature_2m_min,temperature_2m_mean",
        "timezone": "Asia/Kolkata",
    }
    try:
        resp = requests.get(ARCHIVE_URL, params=params, timeout=30)
        resp.raise_for_status()
        daily = resp.json()["daily"]
        return pd.DataFrame(
            {
                "report_date": pd.to_datetime(daily["time"]).date,
                "state_id": coords["state_id"],
                "tmax_c": daily["temperature_2m_max"],
                "tmin_c": daily["temperature_2m_min"],
                "tmean_c": daily["temperature_2m_mean"],
            }
        )
    except (requests.RequestException, KeyError) as exc:
        FAILED_LOG.parent.mkdir(parents=True, exist_ok=True)
        with FAILED_LOG.open("a", encoding="utf-8") as f:
            f.write(f"{city}: {exc}\n")
        print(f"FAILED  {city}: {exc}")
        return None


def fetch_all(since: str | None) -> pd.DataFrame:
    frames = []
    for city, coords in CITY_COORDS.items():
        print(f"fetching {city} ({coords['state_name']})...")
        df = fetch_city(city, coords, since)
        if df is not None:
            frames.append(df)
        time.sleep(1)  # be a polite API citizen even though no key is required
    if not frames:
        raise RuntimeError("Every city failed to fetch — aborting, nothing to load.")
    return pd.concat(frames, ignore_index=True)


def verify_state_ids(conn) -> None:
    """WHY: CITY_COORDS' state_ids are unverified guesses (see comment
    above). This confirms every (state_id, state_name) pair actually
    matches the live dim_state table before any row is written, so a
    wrong guess fails loudly instead of loading weather onto the wrong
    state."""
    rows = conn.execute(text("SELECT state_id, state_name FROM dim_state")).all()
    live = {state_id: state_name for state_id, state_name in rows}

    mismatches = []
    for city, coords in CITY_COORDS.items():
        actual = live.get(coords["state_id"])
        if actual != coords["state_name"]:
            mismatches.append(
                f"{city}: assumed state_id {coords['state_id']} = "
                f"'{coords['state_name']}', but dim_state has '{actual}'"
            )
    if mismatches:
        raise ValueError(
            "CITY_COORDS state_id guesses don't match dim_state — fix before loading:\n"
            + "\n".join(mismatches)
        )
    print("state_id mapping verified against dim_state — all 8 cities correct.")


def load_weather(engine, conn, df: pd.DataFrame) -> int:
    df.to_sql("stg_weather_daily", engine, if_exists="replace", index=False, method="multi", chunksize=1000)
    result = conn.execute(
        text(
            """
            INSERT INTO fact_weather_daily (report_date, state_id, tmax_c, tmin_c, tmean_c)
            SELECT report_date, state_id, tmax_c, tmin_c, tmean_c
            FROM stg_weather_daily
            ON CONFLICT (report_date, state_id) DO UPDATE SET
                tmax_c = EXCLUDED.tmax_c,
                tmin_c = EXCLUDED.tmin_c,
                tmean_c = EXCLUDED.tmean_c,
                loaded_at = now()
            """
        )
    )
    return result.rowcount


def main(since: str | None) -> None:
    load_dotenv()
    import os

    engine = create_engine(os.environ["DATABASE_URL"], pool_pre_ping=True)
    df = fetch_all(since)

    with engine.begin() as conn:
        apply_schema(conn)
        verify_state_ids(conn)
        upserted = load_weather(engine, conn, df)

    print(f"\nrows upserted: {upserted}")
    print(f"date range: {df['report_date'].min()} to {df['report_date'].max()}")
    print(f"cities fetched: {df['state_id'].nunique()} / {len(CITY_COORDS)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch and load Open-Meteo weather history.")
    parser.add_argument("--since", help="YYYY-MM-DD, fetch/load only dates on/after this")
    args = parser.parse_args()
    main(args.since)
