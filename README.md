# GridPulse ⚡

> India electricity demand & duck-curve analytics — an automated pipeline from a live government
> data source (with a documented, tested fallback) through a Postgres star schema, SQL analysis,
> statistical modeling, and a Power BI dashboard.

[![daily-grid-update](https://github.com/Som0111/gridpulse/actions/workflows/daily.yml/badge.svg)](https://github.com/Som0111/gridpulse/actions/workflows/daily.yml)
[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue)](https://www.python.org/)
[![PostgreSQL on Neon](https://img.shields.io/badge/postgresql-neon-green)](https://neon.tech/)

---

## What it does

GridPulse ingests daily Power Supply Position (PSP) data for all 34 Indian states/UTs, loads it
into a cloud Postgres star schema, runs a layer of window-function SQL analyses plus a Python
statistics notebook, visualizes it in Power BI, and is wired for a daily automated refresh via
GitHub Actions — including a soft-fail path for when the upstream source is unreachable, which it
has been for the entire build of this project (see [Data source](#data-source--the-outage-story)).

**Key numbers, as actually measured against this project's real data and models — not
aspirational:**

- **65,178 rows** loaded into `fact_state_daily` (34 states × 1,917 days, 2020-01-01 to 2025-03-31)
- **10 numbered SQL analysis queries** (`sql/02`–`11`) plus 2 supporting views for Power BI and a
  data-quality fix (`sql/12`–`13`) — 12 SQL files total beyond the schema
- **SARIMAX 30-day forecast: 2.49% MAPE** on the clean holdout (raw MAPE was 93.30%, but that
  number was dominated by a single known source-data gap day — see [Statistical
  analysis](#statistical-analysis) for why both numbers are reported, not just the flattering one)
- **OLS regression: R² = 0.368** — Delhi's demand above a 24°C cooling threshold, +4.87 MU per °C
- **Hypothesis test: p = 0.1362** — fail to reject H₀; **not** statistically significant evidence
  that evening-peak stress rose FY2023-24 → FY2024-25 across 31 states. Reported honestly as a
  null result, not massaged into a positive finding.

---

## Key findings

From `docs/findings.md`, each tied to a specific SQL query and real numbers:

1. **Dadra and Nagar Haveli** has the lowest load factor in the dataset (0.436) *and* shows up in
   12 of the shortage-hotspot quarters — a state whose grid is sized for a peak it rarely draws,
   and where that peak stress is real and recurring, not a modeling artifact. Top candidate for
   battery storage / demand-response investment.
2. **Jammu and Kashmir and Ladakh** had energy shortage in **20 of the last 21 quarters** — the
   most persistent shortage pattern of any state, closer to a structural condition than a seasonal
   spike.
3. **Goa** is the fastest-growing state by energy consumption, averaging **+12.41% YoY** across 4
   complete financial-year pairs — a compounding growth rate that will outrun linear capacity
   planning within a few years.

---

## Architecture

```
Grid-India PSP reports (daily XLS/HTML)  ──╮
                                            │  download_psp.py + parse_psp.py
Kaggle backfill dataset (MIT license) ─────┤  (fallback used for 2020-01-01 → 2025-03-31,
                                            │   see "Data source" below)
                                            ▼
                              data/staging/state_daily.csv (tidy, 6-column shape)
                                            │
                                            │  load_db.py (idempotent upsert)
                                            ▼
                      Neon PostgreSQL — star schema
        dim_state · dim_date · fact_state_daily · fact_weather_daily
                            │                          │
                            ▼                          ▼
              12 SQL files (/sql)          Power BI (dashboards/gridpulse.pbix)
        + notebooks/analysis.ipynb          — 6 DAX measures, Shape Map, 4 pages
        (STL, OLS, hypothesis test,
         SARIMAX)
                            │
                            ▼
          GitHub Actions daily cron (.github/workflows/daily.yml)
          → src/daily_update.py → download → parse → load, one date at a time
          soft-fails on source outage, fails loudly on 2 consecutive 0-row loads
```

---

## Tech stack

| Layer | Technology | Why |
|---|---|---|
| Ingestion | `requests`, `pandas`, `xlrd`, `openpyxl` | anchor-search XLS/HTML parsing tolerant of report format drift |
| Fallback source | Kaggle (`preygle/indian-power-demand-and-shortage-data-2020-2025`, MIT) | documented, tested fallback for the live-site outage |
| Storage | PostgreSQL on Neon | cloud-hosted so both GitHub Actions and Power BI can reach it |
| Database access | `SQLAlchemy`, `psycopg2-binary` | idempotent `INSERT ... ON CONFLICT DO UPDATE` upserts throughout |
| Analysis (SQL) | window functions, CTEs, `FILTER`, `generate_series` | 12 files in `/sql`, each with a business-question + technique header |
| Analysis (Python) | `statsmodels` (STL, SARIMAX, OLS), `scipy.stats` | `notebooks/analysis.ipynb`, restart-and-run-all clean |
| Weather | Open-Meteo archive API, 8 proxy cities | free, no key, `fact_weather_daily` |
| Visualization | Power BI Desktop (`dashboards/gridpulse.pbix`) | Shape Map choropleth, 6 DAX measures |
| Automation | GitHub Actions (`daily.yml`), `actions/cache` | daily cron + manual trigger, soft-fail vs. loud-fail logic, cache-based state persistence |
| Tests | `pytest` | 16 tests, `tests/test_fy.py` + `tests/test_parse_psp.py` |

---

## Schema

```
dim_state (34 rows)              dim_date (1,917 rows)
  state_id PK                      date_id PK
  state_name                       year, month, day, day_of_week
  region_code (NR/WR/SR/ER/NER)    is_weekend, fin_year, season
  is_ut
        \                              /
         fact_state_daily (65,178 rows)         fact_weather_daily (15,336 rows)
           report_date, state_id  (composite PK)  report_date, state_id (composite PK)
           energy_met_mu, energy_shortage_mu      tmax_c, tmin_c, tmean_c
           peak_demand_mw, peak_met_mw             (8 proxy cities only, NULL elsewhere)
```

Plus two views: `v_dashboard_daily` (flattened join for Power BI import) and
`v_national_daily` (completeness-gated national total — see below).

---

## SQL analysis layer (`/sql`)

| # | File | Business question | Key technique |
|---|---|---|---|
| 00 | `00_schema.sql` | — (schema) | Composite PK for idempotent upserts |
| 02 | `national_trend.sql` | Monthly national trend + YoY % | `LAG(value, 12) OVER (ORDER BY month)` |
| 03 | `state_ranking.sql` | Top-10 states, % share of national | `RANK()` + window `SUM() OVER ()` |
| 04 | `rolling_peaks.sql` | 30-day rolling max peak demand | `MAX() OVER (... ROWS BETWEEN 29 PRECEDING)` |
| 05 | `shortage_hotspots.sql` | Persistent shortage states, by quarter | `COUNT(*) FILTER (WHERE ...)` + `HAVING` |
| 06 | `weekend_effect.sql` | Weekday vs weekend demand, by region | `CASE` bucketing + self-join |
| 07 | `seasonal_profile.sql` | Summer/monsoon/winter demand, per state | `AVG(...) FILTER (WHERE season = ...)` pivot |
| 08 | `heatwave_detection.sql` | Demand spikes vs. trailing normal | window `AVG()`/`STDDEV()`, mean + 2σ |
| 09 | `growth_leaders.sql` | Fastest-growing states, FY CAGR | per-FY CTE, self-joined on adjacent years |
| 10 | `peak_vs_energy.sql` | "Peakiest" states — storage candidates | unit-normalized load-factor ratio |
| 11 | `coverage_audit.sql` | Missing report-days per state | `generate_series` + `LEFT JOIN` |
| 12 | `dashboard_view.sql` | — (Power BI plumbing view) | `LEFT JOIN` + window completeness flag |
| 13 | `national_daily_validated.sql` | — (data-quality plumbing view) | `CASE WHEN COUNT >= 30 THEN SUM END` |

`sql/11` is numbered last (written last) but is meant to be **read first** — it's the
data-quality check that should be trusted before any of the others.

### A real bug found and fixed: the completeness threshold

The Power BI national trend chart showed sharp false crash-to-zero spikes on 12 specific dates.
Root cause: on those dates, 33-35 of 34 states have `NULL` `energy_met_mu` in the source data, but
1-2 states still report a value (sometimes literally `0.0`). SQL's `SUM()` ignores `NULL`s rather
than propagating them, so the "national total" for that day became a tiny, real-looking number
instead of an obvious gap. Fixed with a `>= 30 of 34 states reporting` completeness threshold —
justified by inspecting the actual distribution (97.7% of days have 30-34 states reporting; the
44 days below that threshold are themselves concentrated at 0-2 states, not a gray zone) —
implemented both in SQL (`sql/12`, `sql/13`) and, since importing a new table into the existing
Power BI model was too disruptive, replicated directly in DAX (`docs/dax-measures.md`) using
`SUMX` + `ALL(dim_state)` so the completeness check always runs against all 34 states regardless
of any state-level slicer filter active on the report page. Full writeup:
`docs/data-dictionary.md`.

---

## Statistical analysis (`notebooks/analysis.ipynb`)

Reads live from Neon (not CSV), restart-and-run-all clean, 24 cells, 0 errors. Four analyses,
each with a BEFORE (question) and AFTER (bolded finding) markdown cell:

**1. Seasonality decomposition (STL, period=7)** — national demand trend is +273 MU/year;
Sunday is the lowest-demand day of the week, Friday the highest.

**2. Temperature-demand regression (OLS)** — Delhi, days above a 24°C cooling threshold:
R² = 0.368, slope = 4.87 MU/°C. A real but moderate relationship — temperature explains about
37% of variance above the threshold, not the whole story.

**3. Hypothesis test — is evening-peak stress rising?** H₀: no change in mean peak-to-average
ratio, FY2023-24 vs FY2024-25. Shapiro-Wilk showed non-normal differences, so a Wilcoxon
signed-rank test was used (not a t-test): statistic = 305.0, **p = 0.1362**. Since p > 0.05, we
**fail to reject H₀** — not statistically significant evidence of rising peak stress. Reported as
a genuine null result, per the project rule of never writing "proves," only "is/isn't consistent
with."

**4. SARIMAX(1,1,1)×(1,0,1,7) forecast, 30-day holdout** — raw MAPE 93.30%, but traced back to a
single source-data gap day (2025-03-06, where only 1 of 34 states reported a value — the same
completeness-threshold issue documented above). Excluding that one day: **MAPE = 2.49%** over the
remaining 29 days, a genuinely strong result for a deliberately simple model. Both numbers are
reported, with the root cause traced and confirmed against the raw source rows, rather than
silently dropping the inconvenient one.

---

## Power BI dashboard (`dashboards/gridpulse.pbix`)

- **Model:** `fact_state_daily` + `dim_state` + `dim_date`, star schema, `dim_date` marked as the
  official date table.
- **6 DAX measures** (`docs/dax-measures.md`): Total Energy Met MU, Peak Demand (Max), Energy
  YoY %, Shortage Rate %, Peak-to-Avg Ratio, 30-Day Rolling Average — all gated on the
  completeness threshold where they sum across states.
- **State Explorer choropleth:** `dashboards/india_states.json`, an MIT-licensed India-states
  TopoJSON (`geohacker/india`, converted from GeoJSON and simplified 18.8 MB → 155 KB). One known
  cartographic limitation: the map predates the 2019 Jammu & Kashmir/Ladakh split, so it has only
  a `"Jammu and Kashmir"` shape; `dim_state` merges these into one row. Resolved with a
  **display-only** DAX calculated column (`Map Display Name`) used solely by the Shape Map's
  Location field — the underlying data and every other visual keep using the real `state_name`.

---

## Automation (`.github/workflows/daily.yml`)

Cron `30 5 * * *` (05:30 UTC = 11:00 IST, after report publication) + `workflow_dispatch` for
manual runs. `src/daily_update.py` is the single entry point:

1. Downloads yesterday's report.
2. **If the download fails** (site down, 404, timeout): logs a warning, **exits 0**. This is
   deliberate — the source has had a genuine, confirmed outage (DNS `NXDOMAIN`, verified via
   Google's public DoH resolver, not a local network issue) for this entire project, and a
   scheduled job shouldn't go red for something outside the pipeline's control.
3. **If the download succeeds but 0 rows load, twice in a row**: fails loudly (exit 1) — tracked
   via `data/raw/automation_state.json`, persisted between stateless Actions runs using
   `actions/cache` keyed on `github.run_id` with a stable `restore-keys` prefix (a literal fixed
   cache key would silently stop updating after the first run, since `actions/cache` skips
   re-saving on an exact key match).

`requirements.txt` was rebuilt from the project's actual imports (17 packages) after an earlier
version — a raw `pip freeze` of the whole system Python environment — broke the Actions runner
with a Windows-only `pywin32` dependency; the rebuilt file was verified by installing into a
fresh, isolated virtual environment before being trusted again.

---

## Data source & the outage story

`report.grid-india.in`, the live Grid-India PSP report source, has been unreachable for the
entire duration of this project — confirmed via DNS lookups from multiple independent networks
and Google's public DNS-over-HTTPS API (genuine `NXDOMAIN`, not a local block or IP filtering).

**Historical backfill (2020-01-01 to 2025-03-31, 65,178 rows)** uses the documented Kaggle
fallback: [`preygle/indian-power-demand-and-shortage-data-2020-2025`](https://www.kaggle.com/datasets/preygle/indian-power-demand-and-shortage-data-2020-2025)
(MIT license), sourced from the same underlying PSP reports. 4 of 5 target fields map directly;
`peak_demand_mw` is derived (`Max Demand Met + Shortage During Peak`, since no direct column
exists) — exact on ~91% of rows, with quantified tail error documented in
`docs/data-dictionary.md`.

**`src/parse_psp.py`**, the live-report parser, is built and tested (11 passing tests against
synthetic fixtures modeling anchor-search header detection, shifted headers, state-name variants,
and the sum-vs-national-total validation check) but **not yet validated against a real report
file**, since one has never been reachable. This is flagged prominently in the file's own
docstring — it must be checked against a real file the day the site recovers, before being
trusted in production.

---

## How to run locally

```bash
# System Python 3.12, no virtual environment (project convention)
pip install -r requirements.txt

# .env (never committed):
# DATABASE_URL=postgresql://user:pass@ep-xxx.neon.tech/neondb?sslmode=require

# One-time backfill (only needed once; already done in Neon)
python src/parse_kaggle_backfill.py
python src/load_db.py

# Weather backfill
python src/fetch_weather.py

# Run the SQL analysis layer against Neon, or open notebooks/analysis.ipynb

# Run tests
pytest tests/ -v

# Daily update (what GitHub Actions runs)
python src/daily_update.py
```

---

## Project structure

```
gridpulse/
├── src/
│   ├── fy_utils.py            # Indian financial-year folder logic (tested)
│   ├── download_psp.py        # live PSP report downloader
│   ├── parse_psp.py           # live report parser (built, untested against a real file — see above)
│   ├── parse_kaggle_backfill.py  # Kaggle fallback parser (used for the 65k-row backfill)
│   ├── load_db.py             # idempotent Neon loader
│   ├── fetch_weather.py       # Open-Meteo → fact_weather_daily
│   └── daily_update.py        # Phase 5 entry point (soft-fail / loud-fail logic)
├── sql/                       # 00_schema + 12 numbered files, business-question headers
├── notebooks/analysis.ipynb   # STL, OLS, hypothesis test, SARIMAX
├── dashboards/
│   ├── gridpulse.pbix
│   └── india_states.json      # MIT-licensed TopoJSON (geohacker/india)
├── data/                      # gitignored: raw/ + staging/
├── docs/                      # data-dictionary, findings, dax-measures, build notes
├── tests/                     # 16 tests: test_fy.py + test_parse_psp.py (+ fixtures/)
├── .github/workflows/daily.yml
├── CLAUDE.md · requirements.txt · .env (local only, gitignored)
```

---

## What this project demonstrates

- End-to-end pipeline design under a real, unplanned failure mode (source outage from day one) —
  including a documented fallback, not just a happy-path build.
- Idempotent loading (composite primary keys + `ON CONFLICT DO UPDATE`, verified with an
  explicit double-run test showing identical row counts).
- SQL window functions, CTEs, `FILTER`, self-joins, `generate_series` — 12 files, each with a
  stated business question and technique.
- Honest statistics: a non-significant hypothesis test reported as a null result, not hidden or
  reframed; a 93% MAPE traced to its root cause and reported alongside the corrected 2.49%
  rather than silently substituted.
- A real bug found in production (NULL-dilution causing false chart spikes), root-caused,
  quantified against the actual data distribution, and fixed in two places (SQL + DAX) with the
  reasoning documented in both.
- Production-style automation: soft-fail vs. loud-fail distinction, state persisted correctly
  across stateless CI runs, a dependency-bloat incident caught and fixed with a real
  fresh-virtual-environment test before re-trusting the file.
