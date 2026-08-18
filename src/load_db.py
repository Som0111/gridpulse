"""Load staged PSP data into the Neon Postgres star schema.

WHY this exists: staging CSVs (from parse_kaggle_backfill.py, later
parse_psp.py) are tidy but flat. This applies the schema, seeds the
dimension tables, and upserts fact rows so re-running a load for the
same date never creates duplicates (idempotent by design via the
fact table's composite primary key + ON CONFLICT DO UPDATE).
"""

import argparse
import sys
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

sys.path.insert(0, str(Path(__file__).parent))
from fy_utils import fy_folder

SCHEMA_PATH = Path("sql/00_schema.sql")
STAGING_PATH = Path("data/staging/state_daily.csv")

# WHY hardcoded, not inferred: Grid-India's own NR/WR/SR/ER/NER grouping is
# an operational fact (which regional load despatch centre a state belongs
# to), not something derivable from the data itself. Keys must exactly match
# the 34 states already validated in parse_kaggle_backfill.py's staging
# output — the loader asserts this rather than silently accepting drift.
STATE_REGION = {
    # Northern Region (NR)
    "Chandigarh": ("NR", True),
    "Delhi": ("NR", True),
    "Haryana": ("NR", False),
    "Himachal Pradesh": ("NR", False),
    "Jammu and Kashmir and Ladakh": ("NR", True),
    "Punjab": ("NR", False),
    "Rajasthan": ("NR", False),
    "Uttar Pradesh": ("NR", False),
    "Uttarakhand": ("NR", False),
    # Western Region (WR)
    "Chhattisgarh": ("WR", False),
    "Dadra and Nagar Haveli": ("WR", True),
    "Daman and Diu": ("WR", True),
    "Goa": ("WR", False),
    "Gujarat": ("WR", False),
    "Madhya Pradesh": ("WR", False),
    "Maharashtra": ("WR", False),
    # Southern Region (SR)
    "Andhra Pradesh": ("SR", False),
    "Karnataka": ("SR", False),
    "Kerala": ("SR", False),
    "Puducherry": ("SR", True),
    "Tamil Nadu": ("SR", False),
    "Telangana": ("SR", False),
    # Eastern Region (ER)
    "Bihar": ("ER", False),
    "Jharkhand": ("ER", False),
    "Odisha": ("ER", False),
    "Sikkim": ("ER", False),
    "West Bengal": ("ER", False),
    # North Eastern Region (NER)
    "Arunachal Pradesh": ("NER", False),
    "Assam": ("NER", False),
    "Manipur": ("NER", False),
    "Meghalaya": ("NER", False),
    "Mizoram": ("NER", False),
    "Nagaland": ("NER", False),
    "Tripura": ("NER", False),
}


def season_for_month(month: int) -> str:
    """Map a calendar month to the project's 3-season rule.

    WHY: Mar-Jun Summer / Jul-Sep Monsoon / Oct-Feb Winter is the rule fixed
    by the Build Manual, not a general climate definition — every downstream
    seasonal analysis assumes this exact split.
    """
    if month in (3, 4, 5, 6):
        return "Summer"
    if month in (7, 8, 9):
        return "Monsoon"
    return "Winter"  # 10, 11, 12, 1, 2


def apply_schema(conn) -> None:
    sql_text = SCHEMA_PATH.read_text(encoding="utf-8")
    for statement in sql_text.split(";"):
        statement = statement.strip()
        if statement:
            conn.execute(text(statement))


def seed_dim_state(conn, states_in_staging: set[str]) -> None:
    """WHY assert: a state slipping through without a region mapping means
    it silently gets no rows loaded (FK join would just drop it) — better
    to fail loudly here than debug a missing state weeks later."""
    missing = states_in_staging - STATE_REGION.keys()
    if missing:
        raise ValueError(f"States in staging with no STATE_REGION mapping: {missing}")

    rows = [
        {"state_name": name, "region_code": region, "is_ut": is_ut}
        for name, (region, is_ut) in STATE_REGION.items()
    ]
    conn.execute(
        text(
            """
            INSERT INTO dim_state (state_name, region_code, is_ut)
            VALUES (:state_name, :region_code, :is_ut)
            ON CONFLICT (state_name) DO UPDATE SET
                region_code = EXCLUDED.region_code,
                is_ut = EXCLUDED.is_ut
            """
        ),
        rows,
    )


def seed_dim_date(conn, min_date, max_date) -> None:
    dates = pd.date_range(min_date, max_date, freq="D")
    rows = [
        {
            "date_id": d.date(),
            "year": d.year,
            "month": d.month,
            "day": d.day,
            "day_of_week": d.weekday(),
            "is_weekend": d.weekday() >= 5,
            "fin_year": fy_folder(d.date()),
            "season": season_for_month(d.month),
        }
        for d in dates
    ]
    conn.execute(
        text(
            """
            INSERT INTO dim_date (date_id, year, month, day, day_of_week, is_weekend, fin_year, season)
            VALUES (:date_id, :year, :month, :day, :day_of_week, :is_weekend, :fin_year, :season)
            ON CONFLICT (date_id) DO UPDATE SET
                year = EXCLUDED.year, month = EXCLUDED.month, day = EXCLUDED.day,
                day_of_week = EXCLUDED.day_of_week, is_weekend = EXCLUDED.is_weekend,
                fin_year = EXCLUDED.fin_year, season = EXCLUDED.season
            """
        ),
        rows,
    )


def load_facts(engine, conn, df: pd.DataFrame) -> int:
    """Batch-load via a real staging table, then one set-based upsert.

    WHY not row-by-row: 65k+ rows one at a time over the network to Neon
    would take many minutes; a single INSERT...SELECT...ON CONFLICT is one
    round trip for the whole batch.
    """
    df.to_sql("stg_state_daily", engine, if_exists="replace", index=False, method="multi", chunksize=1000)

    result = conn.execute(
        text(
            """
            INSERT INTO fact_state_daily
                (report_date, state_id, energy_met_mu, energy_shortage_mu, peak_demand_mw, peak_met_mw)
            SELECT s.report_date, d.state_id, s.energy_met_mu, s.energy_shortage_mu, s.peak_demand_mw, s.peak_met_mw
            FROM stg_state_daily s
            JOIN dim_state d ON d.state_name = s.state
            ON CONFLICT (report_date, state_id) DO UPDATE SET
                energy_met_mu = EXCLUDED.energy_met_mu,
                energy_shortage_mu = EXCLUDED.energy_shortage_mu,
                peak_demand_mw = EXCLUDED.peak_demand_mw,
                peak_met_mw = EXCLUDED.peak_met_mw,
                loaded_at = now()
            """
        )
    )
    return result.rowcount


def print_summary(conn) -> None:
    total = conn.execute(text("SELECT COUNT(*) FROM fact_state_daily")).scalar()
    min_max = conn.execute(text("SELECT MIN(report_date), MAX(report_date) FROM fact_state_daily")).one()
    print(f"\ntotal rows in fact_state_daily: {total}")
    print(f"date range in fact table: {min_max[0]} to {min_max[1]}")

    print("per-region row counts:")
    region_rows = conn.execute(
        text(
            """
            SELECT ds.region_code, COUNT(*)
            FROM fact_state_daily f
            JOIN dim_state ds ON ds.state_id = f.state_id
            GROUP BY ds.region_code
            ORDER BY ds.region_code
            """
        )
    ).all()
    for region, count in region_rows:
        print(f"  {region}: {count}")


def main(since: str | None) -> int:
    """Returns the number of rows upserted this run.

    WHY it returns a count (rather than just printing, as before): Phase 5's
    daily_update.py needs to detect a real bug (report downloaded and
    parsed, but somehow 0 rows loaded) vs. a normal run — it can't tell the
    difference by scraping stdout.
    """
    load_dotenv()
    import os

    engine = create_engine(os.environ["DATABASE_URL"], pool_pre_ping=True)

    df = pd.read_csv(STAGING_PATH, parse_dates=["report_date"])
    if since:
        df = df[df["report_date"] >= pd.Timestamp(since)]

    if df.empty:
        # WHY this guard: without it, df["report_date"].min()/.max() below
        # would be NaT and crash seed_dim_date — an empty --since window
        # (e.g. staging wasn't updated with today's row yet) should be a
        # clean "0 rows" result, not a crash.
        print("no staging rows match --since filter; nothing to load")
        return 0

    df["report_date"] = df["report_date"].dt.date

    with engine.begin() as conn:
        apply_schema(conn)
        seed_dim_state(conn, set(df["state"].unique()))
        seed_dim_date(conn, df["report_date"].min(), df["report_date"].max())
        upserted = load_facts(engine, conn, df)
        print(f"rows upserted this run: {upserted}")
        print_summary(conn)

    return upserted


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Load staged PSP data into Neon Postgres.")
    parser.add_argument("--since", help="YYYY-MM-DD, load only dates on/after this")
    args = parser.parse_args()
    main(args.since)
