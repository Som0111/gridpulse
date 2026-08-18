# GridPulse — Power BI DAX Measures

Ready-to-paste formulas for the Measures table (Phase 4, Step 28).

**Model source — updated 2026-08-18:** import `v_dashboard_daily` (Get Data →
PostgreSQL → `v_dashboard_daily`), not `fact_state_daily` directly. The view
already carries `state_name`/`region_code` flattened in, plus the
`is_complete_day` flag every measure below that touches `energy_met_mu` or
`energy_shortage_mu` needs — see "Completeness threshold" below. Still
import `dim_date` separately and relate `v_dashboard_daily[report_date] ->
dim_date[date_id]` (many-to-one, single direction), with `dim_date` marked
as the official date table — `SAMEPERIODLASTYEAR`/`DATESINPERIOD` still need
that real relationship regardless of which fact table feeds it.

## Completeness threshold — why several measures below use CALCULATE + a filter

12 known dates have 33-35 of 34 states reporting `NULL` for `energy_met_mu`
in the source data (see `docs/data-dictionary.md`). A plain `SUM()` ignores
those NULLs and returns a tiny but real-looking number instead of an
obvious gap — this is exactly what caused false crash-to-zero spikes in the
National Pulse trend chart. `v_dashboard_daily[is_complete_day]` is `TRUE`
only when ≥30 of 34 states reported that date; every measure summing
`energy_met_mu` or `energy_shortage_mu` across states must gate on it so an
incomplete day returns blank instead of a misleading small number. `MAX()`-
based measures (like Peak Demand) don't have this problem — a max isn't
diluted by missing states the way a sum is — so they're left ungated.

## Total Energy Met

Sums energy actually supplied (in MU) across whatever states/dates are in
the current filter context — the base building block most other measures
and every KPI card reference. Gated on `is_complete_day` so the 12 known
bad dates return blank instead of a fake near-zero total (see above).

```dax
Total Energy Met =
CALCULATE(
    SUM(v_dashboard_daily[energy_met_mu]),
    v_dashboard_daily[is_complete_day] = TRUE
)
```

## Peak Demand (Max)

The highest single-day peak demand (MW) within the current filter context —
answers "what's the worst peak we've seen for this state/region/period?"
Not gated on `is_complete_day`: a MAX isn't diluted by other states being
missing the way a SUM is, so this is safe as a plain MAX.

```dax
Peak Demand (Max) = MAX(v_dashboard_daily[peak_demand_mw])
```

## Energy YoY %

Compares Total Energy Met in the current period to the same period one year
earlier, as a percentage change — the headline growth number for the
National Pulse page. `SAMEPERIODLASTYEAR` requires `dim_date` to be a
continuous, gap-free calendar marked as the date table, or this silently
returns blank instead of erroring.

```dax
Energy YoY % =
VAR CurrentEnergy = [Total Energy Met]
VAR PriorYearEnergy =
    CALCULATE(
        [Total Energy Met],
        SAMEPERIODLASTYEAR(dim_date[date_id])
    )
RETURN
    DIVIDE(CurrentEnergy - PriorYearEnergy, PriorYearEnergy)
```

Inherits the completeness gate automatically via `[Total Energy Met]` — no
separate change needed here.

## Shortage Rate %

What fraction of total energy demand went unmet, as a percentage — the
headline stress indicator: energy shortage as a share of what was actually
delivered plus what was short. Same vulnerability as Total Energy Met (both
terms are sums across states for a date), so gated the same way.

```dax
Shortage Rate % =
VAR CompleteRows = FILTER(v_dashboard_daily, v_dashboard_daily[is_complete_day] = TRUE)
VAR TotalShortage = SUMX(CompleteRows, v_dashboard_daily[energy_shortage_mu])
VAR TotalMet = SUMX(CompleteRows, v_dashboard_daily[energy_met_mu])
RETURN
    DIVIDE(TotalShortage, TotalMet + TotalShortage)
```

## Peak-to-Avg Ratio

How "peaky" a state's demand is — peak demand divided by average daily
demand converted to the same MW basis. A high ratio means the grid is sized
for a peak it rarely draws — the exact metric behind the battery-storage
candidate list from `sql/10_peak_vs_energy.sql`.

```dax
Peak-to-Avg Ratio =
VAR AvgDemandMW = DIVIDE([Total Energy Met] * 1000, 24 * DISTINCTCOUNT(v_dashboard_daily[report_date]))
RETURN
    DIVIDE([Peak Demand (Max)], AvgDemandMW)
```

Inherits the completeness gate via `[Total Energy Met]`. Note `DISTINCTCOUNT(report_date)`
still counts incomplete days too (it's just counting calendar days present,
not summing a value) — that's correct, since the denominator here should be
the number of days being averaged over, not filtered by completeness.

## 30-Day Rolling Average

Smooths daily noise into a trailing 30-day average of energy met — the line
used on the National Pulse trend chart so day-to-day spikes don't dominate
the visual.

```dax
30-Day Rolling Average =
AVERAGEX(
    DATESINPERIOD(dim_date[date_id], MAX(dim_date[date_id]), -30, DAY),
    [Total Energy Met]
)
```

Inherits the completeness gate via `[Total Energy Met]` — an incomplete day
in the 30-day window contributes blank rather than a fake low value, so
`AVERAGEX` correctly excludes it from the average instead of dragging it down.
