"""Parse live Grid-India PSP report files into the tidy staging schema.

============================================================================
NOT YET VALIDATED AGAINST A REAL FILE.
============================================================================
This parser is built against documented format notes and synthetic test
fixtures, NOT yet validated against a real live report file, since
report.grid-india.in has been down throughout this project. MUST be
validated against a real file the day the site recovers, before trusting
it for production use.

Specifically: docs/data-dictionary.md's "Columns / fields" section is
still marked *pending* — there is no actual manual inspection of a real
report's sheet layout to build against. The column-name keywords below
(ANCHOR_STATE, COL_KEYWORDS) are a best-effort reconstruction from (a) the
Build Manual's Phase 1 description of what the report contains
(state-wise energy met, peak demand/peak met, shortage, NR/WR/SR/ER/NER
region rows), and (b) the column names the Kaggle backfill dataset
actually confirmed (Max Demand Met, Shortage During Peak, Energy Met,
Energy Shortage) — reasonable since that dataset was itself scraped from
these same PSP reports, but still a guess, not a confirmed inspection.
The header-row anchor-search logic is written to be robust to reasonable
variation for exactly this reason.

WHY this exists: report_psp.py's XLS/PDF downloads are opaque binary/HTML
blobs until parsed. This turns them into the same tidy 6-column shape
parse_kaggle_backfill.py already produces (report_date, state,
energy_met_mu, energy_shortage_mu, peak_demand_mw, peak_met_mw), so live
data appends cleanly onto the same fact_state_daily rows as the backfill.
"""

import re
from pathlib import Path

import pandas as pd

RAW_DIR = Path("data/raw")
STAGING_PATH = Path("data/staging/state_daily.csv")
REGION_STAGING_PATH = Path("data/staging/region_daily.csv")
PARSE_FAILURES_PATH = Path("data/staging/parse_failures.txt")

# WHY a fresh map here rather than importing parse_kaggle_backfill's: the
# Kaggle CSV had abbreviations (HP, MP, region-prefixed names like "ER
# Odisha") specific to that scrape. The real report is expected to already
# use full state names, so the variants worth normalizing are different —
# spelling/legacy-name drift, not abbreviations. Same technique
# (dict-based lookup, applied after strip/whitespace-normalize), different
# contents, because the source format differs.
STATE_NAME_MAP = {
    "Orissa": "Odisha",
    "Pondicherry": "Puducherry",
    "Uttaranchal": "Uttarakhand",
    "NCT of Delhi": "Delhi",
    "Delhi (UT)": "Delhi",
    "J&K": "Jammu and Kashmir and Ladakh",
    "Jammu & Kashmir": "Jammu and Kashmir and Ladakh",
    "Chattisgarh": "Chhattisgarh",
}

# WHY region/all-India rows are handled separately from state rows: they
# aren't states, and loading them into dim_state-bound data would corrupt
# state-level analysis (same reasoning as excluding DVC/Essar steel in
# parse_kaggle_backfill.py) — but they're still useful, so kept in a
# separate region_daily.csv rather than silently dropped.
REGION_CODES = {"NR", "WR", "SR", "ER", "NER"}
ALL_INDIA_LABELS = {"all india", "total", "all-india", "india"}

# Anchor cell that marks the header row: a cell whose *entire* stripped
# text equals this (case-insensitive) — deliberately an equality check,
# not a substring search, so a banner line like "Power Supply Position of
# States" (which contains "State" as a substring) doesn't get mistaken for
# the real header row.
ANCHOR_STATE = "state"

# Keyword sets used to identify each data column from the header row, once
# found. Each column's header must contain ALL keywords in its tuple
# (case-insensitive substring match) — e.g. the peak-shortage column is
# whichever header contains both "shortage" and "peak" (or "demand").
COL_KEYWORDS = {
    "energy_met_mu": ("energy", "met"),
    "energy_shortage_mu": ("energy", "shortage"),
    "peak_met_mw": ("demand", "met"),
    "peak_shortage_mw": ("shortage",),  # matched last, after the more specific ones above
}

FILENAME_DATE_RE = re.compile(r"(\d{2})\.(\d{2})\.(\d{2})_NLDC_PSP")


def parse_date_from_filename(path: Path):
    """Extract the report date from a filename like 03.05.25_NLDC_PSP.xls.

    WHY from the filename, not the sheet content: download_psp.py already
    names files by their report date (see build_urls), and that's a much
    more reliable source than hunting for a date string inside the sheet,
    which format-drifts more than filenames do.
    """
    match = FILENAME_DATE_RE.search(path.name)
    if not match:
        raise ValueError(f"filename {path.name} doesn't match DD.MM.YY_NLDC_PSP pattern")
    day, month, year_2digit = match.groups()
    year = 2000 + int(year_2digit)
    return pd.Timestamp(year=year, month=int(month), day=int(day)).date()


def read_raw_table(path: Path) -> pd.DataFrame:
    """Read a report file as a raw (headerless) grid of cells.

    WHY try xlrd first, then fall back to read_html: most .xls files are
    genuine legacy Excel binaries (xlrd engine), but some government sites
    serve an HTML <table> with a .xls extension — pandas.read_excel raises
    on those, so read_html is the fallback rather than the primary path.
    """
    try:
        return pd.read_excel(path, sheet_name=0, header=None, engine="xlrd")
    except Exception:
        tables = pd.read_html(path, header=None)
        if not tables:
            raise ValueError(f"{path}: read_html found no tables")
        return tables[0]


def find_header_row(raw: pd.DataFrame) -> int:
    """Search for the row whose cells include one that IS (not just
    contains) "state", case-insensitive — see ANCHOR_STATE comment above.
    Never assume a fixed row number; report layout drifts across years.
    """
    for row_idx in range(len(raw)):
        row_values = raw.iloc[row_idx].astype(str).str.strip().str.lower()
        if (row_values == ANCHOR_STATE).any():
            return row_idx
    raise ValueError('no header row found: no cell exactly matches "State"')


def find_columns(header_row: pd.Series) -> dict[str, int]:
    """Map each target field to a column index by keyword search on the
    header row text. WHY keyword sets checked in COL_KEYWORDS' insertion
    order: "peak_shortage_mw" only needs "shortage", which would also
    match the energy-shortage column if checked first — matching the more
    specific energy_shortage_mu keywords ("energy","shortage") before the
    looser peak_shortage_mw keyword ("shortage") avoids that collision.
    """
    header_text = header_row.astype(str).str.strip().str.lower()
    state_col = next(i for i, v in header_text.items() if v == ANCHOR_STATE)

    found: dict[str, int] = {"state": state_col}
    used_cols: set[int] = {state_col}
    for field, keywords in COL_KEYWORDS.items():
        match = next(
            (
                i
                for i, v in header_text.items()
                if i not in used_cols and all(k in v for k in keywords)
            ),
            None,
        )
        if match is not None:
            found[field] = match
            used_cols.add(match)
    return found


def parse_one_file(path: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Parse a single report file into (state_rows, region_rows), both
    tidy DataFrames for this one report_date."""
    report_date = parse_date_from_filename(path)
    raw = read_raw_table(path)

    header_row_idx = find_header_row(raw)
    columns = find_columns(raw.iloc[header_row_idx])
    data_rows = raw.iloc[header_row_idx + 1 :].reset_index(drop=True)

    def build_row(row) -> dict:
        name = str(row[columns["state"]]).strip()
        return {
            "raw_name": name,
            "report_date": report_date,
            "energy_met_mu": pd.to_numeric(row.get(columns.get("energy_met_mu")), errors="coerce"),
            "energy_shortage_mu": pd.to_numeric(row.get(columns.get("energy_shortage_mu")), errors="coerce"),
            "peak_met_mw": pd.to_numeric(row.get(columns.get("peak_met_mw")), errors="coerce"),
            "peak_shortage_mw": pd.to_numeric(row.get(columns.get("peak_shortage_mw")), errors="coerce"),
        }

    parsed = pd.DataFrame([build_row(r) for _, r in data_rows.iterrows()])
    parsed = parsed[parsed["raw_name"].notna() & (parsed["raw_name"].str.strip() != "")]
    parsed = parsed[parsed["raw_name"].str.lower() != "nan"]

    # WHY derive peak_demand_mw the same way as parse_kaggle_backfill.py:
    # the real report, like the Kaggle dataset scraped from it, is
    # expected to have "demand met" and "shortage during peak" as separate
    # columns, not a direct "peak demand" figure — demand wanted = demand
    # met + demand that couldn't be met. See docs/data-dictionary.md's
    # documented error bounds for this same derivation on the backfill.
    parsed["peak_demand_mw"] = parsed["peak_met_mw"] + parsed["peak_shortage_mw"].fillna(0)

    is_region = parsed["raw_name"].str.upper().isin(REGION_CODES)
    is_all_india = parsed["raw_name"].str.lower().isin(ALL_INDIA_LABELS)

    region_rows = parsed[is_region | is_all_india].copy()
    region_rows["region"] = region_rows["raw_name"]

    state_rows = parsed[~(is_region | is_all_india)].copy()
    state_rows["state"] = state_rows["raw_name"].replace(STATE_NAME_MAP)

    tidy_cols = ["report_date", "energy_met_mu", "energy_shortage_mu", "peak_demand_mw", "peak_met_mw"]
    state_tidy = state_rows[["state", *tidy_cols]]
    region_tidy = region_rows[["region", *tidy_cols]]

    return state_tidy, region_tidy


def validate_against_all_india(state_df: pd.DataFrame, region_df: pd.DataFrame) -> list[str]:
    """WHY: a single-file sanity check — do the state rows roughly sum to
    the all-India total row? A >5% deviation usually means a column got
    misidentified (e.g. picked up the wrong "shortage" column), not a
    real accounting quirk (a few % is normal — see coverage_audit.sql's
    same reasoning for the backfill data)."""
    warnings = []
    all_india = region_df[region_df["region"].str.lower().isin(ALL_INDIA_LABELS)]
    if all_india.empty or state_df.empty:
        return warnings

    state_sum = state_df["energy_met_mu"].sum()
    all_india_total = all_india["energy_met_mu"].iloc[0]
    if all_india_total and abs(state_sum - all_india_total) / all_india_total > 0.05:
        pct = 100 * (state_sum - all_india_total) / all_india_total
        warnings.append(
            f"state sum ({state_sum:.1f}) deviates {pct:+.1f}% from all-India total ({all_india_total:.1f})"
        )
    return warnings


def _merge_into_staging(new_state_df: pd.DataFrame, path: Path) -> pd.DataFrame:
    """Append/update rows into an existing staging CSV, deduped on
    (report_date, state), keeping the newest parse. WHY: both the bulk
    parse_all() CLI and the single-file parse_file() (used by
    daily_update.py) need this same merge behavior, so it's factored out
    rather than duplicated."""
    if path.exists():
        existing = pd.read_csv(path, parse_dates=["report_date"])
        existing["report_date"] = existing["report_date"].dt.date
        combined = pd.concat([existing, new_state_df], ignore_index=True)
    else:
        combined = new_state_df
    combined = combined.drop_duplicates(subset=["report_date", "state"], keep="last")
    combined = combined.sort_values(["report_date", "state"])
    path.parent.mkdir(parents=True, exist_ok=True)
    combined.to_csv(path, index=False)
    return combined


def parse_file(path: Path) -> pd.DataFrame:
    """Single-file entry point used by daily_update.py (Phase 5).

    Parses one downloaded report and merges its rows into
    data/staging/state_daily.csv (creating it if it doesn't exist yet).
    Returns the state rows parsed from THIS file (not the merged total) —
    daily_update.py doesn't currently use the return value, but load_db.py
    reads the merged CSV from disk afterward regardless.
    """
    path = Path(path)
    state_df, region_df = parse_one_file(path)

    warnings = validate_against_all_india(state_df, region_df)
    for w in warnings:
        print(f"WARNING [{path.name}]: {w}")

    _merge_into_staging(state_df, STAGING_PATH)
    if not region_df.empty:
        _merge_into_staging_region(region_df)
    return state_df


def _merge_into_staging_region(new_region_df: pd.DataFrame) -> None:
    if REGION_STAGING_PATH.exists():
        existing = pd.read_csv(REGION_STAGING_PATH, parse_dates=["report_date"])
        existing["report_date"] = existing["report_date"].dt.date
        combined = pd.concat([existing, new_region_df], ignore_index=True)
    else:
        combined = new_region_df
    combined = combined.drop_duplicates(subset=["report_date", "region"], keep="last")
    combined = combined.sort_values(["report_date", "region"])
    REGION_STAGING_PATH.parent.mkdir(parents=True, exist_ok=True)
    combined.to_csv(REGION_STAGING_PATH, index=False)


def parse_all() -> None:
    """Bulk CLI mode: parse every .xls under data/raw/, same validation
    report style as parse_kaggle_backfill.py's console summary."""
    files = sorted(RAW_DIR.glob("**/*.xls"))
    all_state_rows = []
    all_region_rows = []
    failures = []

    for path in files:
        try:
            state_df, region_df = parse_one_file(path)
            for w in validate_against_all_india(state_df, region_df):
                print(f"WARNING [{path.name}]: {w}")
            all_state_rows.append(state_df)
            all_region_rows.append(region_df)
        except Exception as exc:
            failures.append(f"{path}: {exc}")
            print(f"FAILED {path}: {exc}")

    if failures:
        PARSE_FAILURES_PATH.parent.mkdir(parents=True, exist_ok=True)
        with PARSE_FAILURES_PATH.open("a", encoding="utf-8") as f:
            f.write("\n".join(failures) + "\n")

    if not all_state_rows:
        print("no files parsed successfully")
        return

    state_df = pd.concat(all_state_rows, ignore_index=True)
    region_df = pd.concat(all_region_rows, ignore_index=True)

    combined_state = _merge_into_staging(state_df, STAGING_PATH)
    if not region_df.empty:
        _merge_into_staging_region(region_df)

    print(f"\nfiles parsed: {len(files) - len(failures)} / {len(files)}")
    print(f"rows in {STAGING_PATH}: {len(combined_state)}")
    print(f"dates covered: {combined_state['report_date'].min()} to {combined_state['report_date'].max()}")
    print("null counts per column:")
    print(combined_state.isnull().sum().to_string())


if __name__ == "__main__":
    parse_all()
