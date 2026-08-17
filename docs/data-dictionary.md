# GridPulse — Data Dictionary

## Backfill source note (2026-08-17)

Historical backfill (2020-01-01 to 2025-03-31) uses the documented Kaggle fallback dataset
because `report.grid-india.in` has been unreachable for multiple days (DNS NXDOMAIN + broken
pages, confirmed across networks — a genuine outage, not a local block).

- **Dataset:** [`preygle/indian-power-demand-and-shortage-data-2020-2025`](https://www.kaggle.com/datasets/preygle/indian-power-demand-and-shortage-data-2020-2025)
  on Kaggle, sourced from the same Grid-India/POSOCO PSP reports.
- **License: MIT** (as shown on the dataset's Kaggle page at download time — note this
  corrects an earlier assumption that it was CC BY 4.0).
- **Coverage:** 2020-01-01 through 2025-03-31, 65,178 tidy rows across 34 states after
  cleaning (see below).
- **Parser:** `src/parse_kaggle_backfill.py` -> writes `data/staging/state_daily.csv` in the
  same tidy shape (`report_date, state, energy_met_mu, energy_shortage_mu, peak_demand_mw,
  peak_met_mw`) that the live parser (`parse_psp.py`, not yet built) will also produce, so
  live rows can append onto the same table without reshaping.

**Field mapping — 4 of 5 target columns are direct, 1 is derived:**

| Target field | Kaggle source column | Notes |
|---|---|---|
| `report_date` | `Date` | direct |
| `state` | `State` | normalized via STATE_NAME_MAP, see below |
| `energy_met_mu` | `Energy Met` | direct |
| `energy_shortage_mu` | `Energy Shortage` | direct |
| `peak_met_mw` | `Max Demand Met` | direct — this is peak *met*, not peak *demand* |
| `peak_demand_mw` | **derived**: `Max Demand Met + Shortage During Peak` | dataset has no direct "peak demand" column; reconstructed as met + shortfall (shortage = demand that couldn't be met). **Limitation:** Derived as Max Demand Met + Shortage During Peak. Exact on ~91% of rows (zero recorded shortage); on the ~9% of rows with nonzero shortage, error can reach several hundred MW at the tail (95th percentile ≈550 MW, worst case ≈3,311 MW). This means peak-stress estimates on the most severe shortage days carry the most uncertainty — precisely the days this project's headline findings focus on. |

Unused columns present in the source but not carried into staging: `Drawl Schedule`,
`OD(+) / UD(-)`, `Max OD` (over/under-drawal figures — not part of the current 5-field
schema; revisit if a future analysis needs them).

**Format drift found in this dataset (state-name normalization, `STATE_NAME_MAP` in
`parse_kaggle_backfill.py`):** `HP`->Himachal Pradesh, `MP`->Madhya Pradesh, `ER
Odisha`->Odisha, `NR UP`->Uttar Pradesh, `SR Karnataka`->Karnataka, `NER
Meghalaya`->Meghalaya, `WR Maharashtra`->Maharashtra, `DD`->Daman and Diu,
`DNH`->Dadra and Nagar Haveli, `J&K(UT) & Ladakh(UT)`->Jammu and Kashmir and Ladakh (two UTs
merged into a single row in the source — noted as a limitation, not split).

**Excluded rows — not states/UTs, kept out of `dim_state`-bound data:** `DVC` (Damodar
Valley Corporation, a utility spanning West Bengal/Jharkhand, not a state) and `Essar
steel` (a private bulk consumer). 3,834 rows excluded for this reason; visible in the
parser's validation report, not silently dropped.

**Known gaps:** ~5-9% nulls per numeric column in the raw source (real gaps, not a parsing
bug) — `energy_met_mu` 3,153 nulls, `energy_shortage_mu` 3,143, `peak_demand_mw` /
`peak_met_mw` 4,195 each, out of 65,178 rows.

**Next step once `report.grid-india.in` recovers:** backfill live data from 2025-04-01
onward (where Kaggle coverage ends) using `download_psp.py` + `parse_psp.py`, then the live
source takes over entirely for the daily automated update (Phase 5). The live parser must
produce the exact same 6-column tidy shape as this backfill so the two sources union
cleanly in `fact_state_daily`.

## Status

**Pending:** Build Manual Phase 1.1, Steps 8-10 (manually inspecting the PSP report source in a
browser, comparing XLS/PDF for a date, and inspecting 4 files from different years) have not
been done yet — `report.grid-india.in` and `posoco.in` were both unreachable (DNS NXDOMAIN /
502 Bad Gateway) when this was attempted on 2026-08-17, confirmed as a genuine outage on
Grid-India's end (checked from two independent networks, not a local block).

The downloader (`src/download_psp.py`) was built against the URL pattern documented in the
Build Manual and confirmed via web search against real indexed URLs
(e.g. `https://report.grid-india.in/ReportData/Daily%20Report/PSP%20Report/2025-2026/May%202025/03.05.25_NLDC_PSP.pdf`),
but the actual file contents (sheet layout, header rows, column names, units) have not been
inspected firsthand. **This section must be filled in once the source is reachable again and
before the parser (`parse_psp.py`) is built** — the parser depends on knowing exactly where each
number lives in the sheet.

## URL pattern (confirmed against search-indexed live URLs)

```
https://report.grid-india.in/ReportData/Daily Report/PSP Report/{FY}/{Month YYYY}/{DD.MM.YY}_NLDC_PSP.{xls|pdf}
```

- `{FY}` — Indian financial year folder, e.g. `2024-2025` (1 April to 31 March). See `src/fy_utils.py::fy_folder`.
- `{Month YYYY}` — full month name + calendar year of the report date itself, e.g. `May 2025`.
- `{DD.MM.YY}` — report date, day/month/2-digit-year.
- Path segments contain literal spaces — must be percent-encoded per-segment (see `build_urls` in `src/download_psp.py`).

## Columns / fields (TO FILL IN once source is reachable)

| Field | Sheet location | Unit | Notes |
|---|---|---|---|
| energy_met | *pending* | MU (million units) | |
| peak_demand | *pending* | MW | |
| peak_met | *pending* | MW | |
| energy_shortage | *pending* | MU | |
| region groupings | *pending* | — | NR / WR / SR / ER / NER |

## Format drift across years (TO FILL IN)

Record anything that changed between report years here as it's discovered — sheet names,
header row position, extra/renamed columns, state-name variants (e.g. Orissa -> Odisha).
