# GridPulse — Power BI DAX Measures

Ready-to-paste formulas for the Measures table (Phase 4, Step 28). Model
source: `fact_state_daily` + `dim_state` + `dim_date`, standard star-schema
relationships (`fact_state_daily[state_id] -> dim_state[state_id]`,
`fact_state_daily[report_date] -> dim_date[date_id]`, many-to-one, single
direction), `dim_date` marked as the official date table. No extra view
import needed — the completeness fix below is implemented entirely in DAX.

## Completeness threshold — why several measures below gate on states_reporting

12 known dates have 33-35 of 34 states reporting `NULL` for `energy_met_mu`
in the source data (see `docs/data-dictionary.md`). A plain `SUM()` ignores
those NULLs and returns a tiny but real-looking number instead of an
obvious gap — this is exactly what caused false crash-to-zero spikes in the
National Pulse trend chart.

**Implementation note (2026-08-18):** the fix was originally written as a
Postgres view (`v_dashboard_daily[is_complete_day]`, see
`sql/12_dashboard_view.sql`), but importing a new table was too disruptive
to the existing Power BI model. The measures below replicate the same
`>=30 of 34 states reporting` threshold directly in DAX instead, using only
`fact_state_daily`, `dim_state`, and `dim_date` — no new import required.

The pattern: `SUMX(VALUES(dim_date[date_id]), ...)` walks one date at a
time. Inside the loop, `StatesReporting` is always counted across **all 34
states** — `ALL(dim_state)` strips out any state/region slicer active on
the report page, so the completeness check itself is never accidentally
computed against a filtered-down subset of states. The actual day total
still respects whatever state filter *is* active (so a state-page visual
correctly shows only that state's numbers). `IF(StatesReporting >= 30,
DayTotal)` returns blank — not 0 — with no `ELSE`, so incomplete days drop
out of the sum entirely rather than contributing a misleading small number.
`MAX()`-based measures (like Peak Demand) don't have this problem — a max
isn't diluted by missing states the way a sum is — so they're left ungated.

## Total Energy Met MU

Sums energy actually supplied (in MU) across whatever states/dates are in
the current filter context — the base building block most other measures
and every KPI card reference. Gated on `states_reporting >= 30` so the 12
known bad dates return blank instead of a fake near-zero total.

```dax
Total Energy Met MU =
SUMX(
    VALUES(dim_date[date_id]),
    VAR StatesReporting =
        CALCULATE(
            COUNTROWS(fact_state_daily),
            NOT ISBLANK(fact_state_daily[energy_met_mu]),
            ALL(dim_state)
        )
    VAR DayTotal =
        CALCULATE(
            SUM(fact_state_daily[energy_met_mu])
        )
    RETURN
        IF(StatesReporting >= 30, DayTotal)
)
```

## Peak Demand (Max)

The highest single-day peak demand (MW) within the current filter context —
answers "what's the worst peak we've seen for this state/region/period?"
Not gated: a MAX isn't diluted by other states being missing the way a SUM
is, so this is safe as a plain MAX.

```dax
Peak Demand (Max) = MAX(fact_state_daily[peak_demand_mw])
```

## Energy YoY %

Compares Total Energy Met MU in the current period to the same period one
year earlier, as a percentage change — the headline growth number for the
National Pulse page. `SAMEPERIODLASTYEAR` requires `dim_date` to be a
continuous, gap-free calendar marked as the date table, or this silently
returns blank instead of erroring.

```dax
Energy YoY % =
VAR CurrentEnergy = [Total Energy Met MU]
VAR PriorYearEnergy =
    CALCULATE(
        [Total Energy Met MU],
        SAMEPERIODLASTYEAR(dim_date[date_id])
    )
RETURN
    DIVIDE(CurrentEnergy - PriorYearEnergy, PriorYearEnergy)
```

Inherits the completeness gate automatically via `[Total Energy Met MU]` —
no separate change needed here.

## Shortage Rate %

What fraction of total energy demand went unmet, as a percentage — the
headline stress indicator: energy shortage as a share of what was actually
delivered plus what was short. Same vulnerability as Total Energy Met MU
(both terms are sums across states for a date), so gated the same way —
reuses `[Total Energy Met MU]` for the "met" side rather than recomputing
the gate a second time.

```dax
Shortage Rate % =
VAR GatedShortage =
    SUMX(
        VALUES(dim_date[date_id]),
        VAR StatesReporting =
            CALCULATE(
                COUNTROWS(fact_state_daily),
                NOT ISBLANK(fact_state_daily[energy_met_mu]),
                ALL(dim_state)
            )
        VAR DayShortage =
            CALCULATE(
                SUM(fact_state_daily[energy_shortage_mu])
            )
        RETURN
            IF(StatesReporting >= 30, DayShortage)
    )
RETURN
    DIVIDE(GatedShortage, [Total Energy Met MU] + GatedShortage)
```

## Peak-to-Avg Ratio

How "peaky" a state's demand is — peak demand divided by average daily
demand converted to the same MW basis. A high ratio means the grid is sized
for a peak it rarely draws — the exact metric behind the battery-storage
candidate list from `sql/10_peak_vs_energy.sql`.

```dax
Peak-to-Avg Ratio =
VAR AvgDemandMW = DIVIDE([Total Energy Met MU] * 1000, 24 * DISTINCTCOUNT(fact_state_daily[report_date]))
RETURN
    DIVIDE([Peak Demand (Max)], AvgDemandMW)
```

Inherits the completeness gate via `[Total Energy Met MU]`. Note
`DISTINCTCOUNT(report_date)` still counts incomplete days too (it's just
counting calendar days present, not summing a value) — that's correct,
since the denominator here should be the number of days being averaged
over, not filtered by completeness.

## 30-Day Rolling Average

Smooths daily noise into a trailing 30-day average of energy met — the line
used on the National Pulse trend chart so day-to-day spikes don't dominate
the visual.

```dax
30-Day Rolling Average =
AVERAGEX(
    DATESINPERIOD(dim_date[date_id], MAX(dim_date[date_id]), -30, DAY),
    [Total Energy Met MU]
)
```

Inherits the completeness gate via `[Total Energy Met MU]` — an incomplete
day in the 30-day window contributes blank rather than a fake low value, so
`AVERAGEX` correctly excludes it from the average instead of dragging it down.

## Calculated columns

Unlike the measures above, a Shape Map visual's Location field needs a
plain column (categorical field to bind shapes to), not a measure —
these are added on `dim_state` in Power BI's Data view (Table tools ->
New column), not the Measures table.

### Map Display Name

**Display-only alias for the State Explorer choropleth.** `dashboards/india_states.json`
(see `docs/data-dictionary.md`) predates the 2019 Jammu & Kashmir/Ladakh split, so it only
has a `"Jammu and Kashmir"` shape — no separate Ladakh shape exists. `dim_state[state_name]`
has these merged into one row, `"Jammu and Kashmir and Ladakh"`, which won't string-match
the map's shape. This column exists ONLY so the Shape Map visual has something that matches;
every other visual, slicer, and measure should keep using `dim_state[state_name]` directly,
never this column — it exists in exactly one place for exactly one purpose.

```dax
Map Display Name =
IF(
    dim_state[state_name] = "Jammu and Kashmir and Ladakh",
    "Jammu and Kashmir",
    dim_state[state_name]
)
```

**Usage:** set the State Explorer Shape Map visual's Location field to `Map Display Name`
instead of `state_name`. Every other page/visual keeps using `state_name` unchanged — the
underlying data is not altered, only this one visual's shape-matching key.
