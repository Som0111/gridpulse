"""Parse the Kaggle historical backfill dataset into GridPulse's staging schema.

WHY this exists: Grid-India's live report site (report.grid-india.in) has been
unreachable for multiple days (confirmed DNS failures, not a network block).
This is the documented fallback: backfill history from a Kaggle dataset
sourced from the same POSOCO PSP reports, in the same tidy shape
download_psp.py + parse_psp.py will eventually produce, so live rows append
cleanly onto the same staging table later.

Source dataset: preygle/indian-power-demand-and-shortage-data-2020-2025
(Kaggle, license: MIT). Actual columns found on inspection:
Date, State, Max Demand Met, Shortage During Peak, Energy Met,
Drawl Schedule, OD(+) / UD(-), Max OD, Energy Shortage.

Field mapping (4 of 5 target columns are direct, 1 is derived):
  report_date        <- Date
  state               <- State (after STATE_NAME_MAP normalization)
  energy_met_mu       <- Energy Met
  energy_shortage_mu  <- Energy Shortage
  peak_met_mw         <- Max Demand Met
  peak_demand_mw      <- Max Demand Met + Shortage During Peak
                         (dataset has no direct "peak demand" column; this
                         reconstructs it as met + shortfall, since shortage
                         is defined as demand that could not be met)
"""

from pathlib import Path

import pandas as pd

RAW_PATH = Path("data/raw/kaggle_backfill/India_Elec_data_(Jan2020-Mar2025).csv")
STAGING_PATH = Path("data/staging/state_daily.csv")

# WHY: source data has abbreviations, region-prefixed names, and casing drift
# across the same real-world state — normalize once here so downstream joins
# to dim_state never see a duplicate state under two spellings.
STATE_NAME_MAP = {
    "HP": "Himachal Pradesh",
    "MP": "Madhya Pradesh",
    "ER Odisha": "Odisha",
    "NR UP": "Uttar Pradesh",
    "SR Karnataka": "Karnataka",
    "NER Meghalaya": "Meghalaya",
    "WR Maharashtra": "Maharashtra",
    "DD": "Daman and Diu",
    "DNH": "Dadra and Nagar Haveli",
    "J&K(UT) & Ladakh(UT)": "Jammu and Kashmir and Ladakh",
}

# WHY: these "State" values are not states or UTs — a utility (DVC spans
# West Bengal/Jharkhand) and a private bulk consumer (Essar steel). Loading
# them into dim_state would corrupt state-level analysis, so they're kept
# out of the tidy output and reported separately instead of silently dropped.
NON_STATE_ENTITIES = {"DVC", "Essar steel"}


def load_and_clean() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Read the raw Kaggle CSV and return (tidy_state_daily, excluded_rows).

    WHY split into two frames: excluded non-state rows must be visible in the
    validation report, never just vanish from the row count silently.
    """
    raw = pd.read_csv(RAW_PATH)

    raw["State"] = raw["State"].str.strip()
    excluded = raw[raw["State"].isin(NON_STATE_ENTITIES)].copy()
    kept = raw[~raw["State"].isin(NON_STATE_ENTITIES)].copy()

    kept["state"] = kept["State"].replace(STATE_NAME_MAP)
    kept["report_date"] = pd.to_datetime(kept["Date"]).dt.date

    kept["energy_met_mu"] = pd.to_numeric(kept["Energy Met"], errors="coerce")
    kept["energy_shortage_mu"] = pd.to_numeric(kept["Energy Shortage"], errors="coerce")
    kept["peak_met_mw"] = pd.to_numeric(kept["Max Demand Met"], errors="coerce")
    shortage_during_peak = pd.to_numeric(kept["Shortage During Peak"], errors="coerce")
    kept["peak_demand_mw"] = kept["peak_met_mw"] + shortage_during_peak.fillna(0)

    tidy = kept[
        [
            "report_date",
            "state",
            "energy_met_mu",
            "energy_shortage_mu",
            "peak_demand_mw",
            "peak_met_mw",
        ]
    ].drop_duplicates(subset=["report_date", "state"], keep="last")

    return tidy, excluded


def print_validation_report(tidy: pd.DataFrame, excluded: pd.DataFrame) -> None:
    print(f"rows written: {len(tidy)}")
    print(f"date range: {tidy['report_date'].min()} to {tidy['report_date'].max()}")
    print(f"states covered ({tidy['state'].nunique()}): {sorted(tidy['state'].unique())}")
    print("null counts per column:")
    print(tidy.isnull().sum().to_string())
    print(
        f"\nexcluded non-state rows: {len(excluded)} "
        f"({sorted(excluded['State'].unique())})"
    )


if __name__ == "__main__":
    STAGING_PATH.parent.mkdir(parents=True, exist_ok=True)
    tidy_df, excluded_df = load_and_clean()
    tidy_df.to_csv(STAGING_PATH, index=False)
    print_validation_report(tidy_df, excluded_df)
    print(f"\nWrote {STAGING_PATH}")
