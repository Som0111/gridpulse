# GridPulse — Power BI DAX Measures

Ready-to-paste formulas for the Measures table (Phase 4, Step 28). Assumes the
model has `dim_date` marked as the official date table and standard
star-schema relationships: `fact_state_daily[state_id] -> dim_state[state_id]`
and `fact_state_daily[report_date] -> dim_date[date_id]` (many-to-one, single
direction).

## Total Energy Met

Sums energy actually supplied (in MU) across whatever states/dates are in
the current filter context — the base building block most other measures
and every KPI card reference.

```dax
Total Energy Met = SUM(fact_state_daily[energy_met_mu])
```

## Peak Demand (Max)

The highest single-day peak demand (MW) within the current filter context —
answers "what's the worst peak we've seen for this state/region/period?"

```dax
Peak Demand (Max) = MAX(fact_state_daily[peak_demand_mw])
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

## Shortage Rate %

What fraction of total energy demand went unmet, as a percentage — the
headline stress indicator: energy shortage as a share of what was actually
delivered plus what was short.

```dax
Shortage Rate % =
DIVIDE(
    SUM(fact_state_daily[energy_shortage_mu]),
    SUM(fact_state_daily[energy_met_mu]) + SUM(fact_state_daily[energy_shortage_mu])
)
```

## Peak-to-Avg Ratio

How "peaky" a state's demand is — peak demand divided by average daily
demand converted to the same MW basis. A high ratio means the grid is sized
for a peak it rarely draws — the exact metric behind the battery-storage
candidate list from `sql/10_peak_vs_energy.sql`.

```dax
Peak-to-Avg Ratio =
VAR AvgDemandMW = DIVIDE([Total Energy Met] * 1000, 24 * DISTINCTCOUNT(fact_state_daily[report_date]))
RETURN
    DIVIDE([Peak Demand (Max)], AvgDemandMW)
```

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
