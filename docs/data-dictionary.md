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

## Completeness threshold for national daily aggregates (2026-08-18)

**Discovered:** the Power BI national trend chart showed several sharp false crash-to-zero
spikes (mid-2020, early/mid-2022, mid-2023, mid-2024, near 2025). Traced to 12 specific
dates where 33-35 of the 34 states have a NULL `energy_met_mu` in the raw source, but 1-2
states still carry a value — on 8 of the 12 dates that surviving value is itself a literal
`0.0`. Because SQL/pandas `SUM()` ignores NULLs rather than propagating them, summing
`energy_met_mu` across states for these dates produces a tiny but non-NULL "real-looking"
number (0 to 251 MU, vs. a typical day's ~2,500-4,000+ MU) instead of an obvious gap —
invisible to a simple null-filter, but a glaring false spike in any trend chart. Confirmed
this originates in the raw Kaggle CSV itself (all 36 rows present for these dates, just
almost all NULL), not introduced by our parser or loader.

**The 12 known bad dates:** 2020-02-29, 2020-07-12, 2020-07-19, 2020-08-15, 2020-08-18,
2021-10-09, 2022-06-11, 2022-06-19, 2023-01-19, 2023-07-23, 2024-04-17, 2025-03-06.

**Unconfirmed hypothesis:** Himachal Pradesh is the one state that "survives" on every
single one of these 12 dates (joined by Madhya Pradesh on 3 of them). This is suspicious
enough to flag but has not been investigated further — possibly HP/MP occupy a position
(alphabetical, or in whatever batch process produced the Kaggle author's original scrape)
that made their rows resilient to whatever caused the rest of that day's batch to fail.
Not confirmed; out of scope to dig into the Kaggle dataset's own scraping code.

**Threshold rule:** a day's national total is only trusted if **at least 30 of 34 states**
(~88%) have a non-null `energy_met_mu`; below that, the national total is `NULL`, not a
misleading small number. 30/34 was chosen by inspecting the real distribution of
`states_reporting` across all 1,917 days, not picked arbitrarily: 1,873 days (97.7%) have
30-34 states reporting, while only 44 days (2.3%) fall below 30 — and those 44 are
themselves concentrated at the extreme low end (29 of the 44 have 0-2 states reporting).
There's a sharp natural cliff at 30, not a gray zone the threshold cuts through.

**Where implemented:**
- `sql/12_dashboard_view.sql` — `v_dashboard_daily` now carries `states_reporting_energy`
  (a per-`report_date` count, same value on every state's row for that date) and
  `is_complete_day` (boolean, `states_reporting_energy >= 30`), so any Power BI measure or
  downstream query can filter on it.
- `sql/13_national_daily_validated.sql` — `v_national_daily`, a pre-aggregated national
  daily total with the threshold already applied (`NULL` on incomplete days). This is what
  the Power BI National Pulse trend chart and any future daily national-total query should
  read from, instead of a raw `SUM(energy_met_mu) GROUP BY report_date`.
- Verified against Neon: all 12 known bad dates now return `NULL` national totals instead
  of the fake small numbers; total nulled days = 44, matching the distribution above exactly.

**Not yet applied:** monthly/other coarser aggregates (e.g. `sql/02_national_trend.sql`)
still use a plain `SUM()`. At monthly grain a single bad day dilutes into ~30 days of real
data (a few percent understatement, not a visible false spike), so this was judged out of
scope for this fix — flagged here in case a future pass wants the same treatment there.

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
