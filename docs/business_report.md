# GridPulse — Business Report

Based entirely on real query output against the live Neon database (65,178 rows, 34
states/UTs, 2020-01-01 to 2025-03-31) and the statistical analyses in
`notebooks/analysis.ipynb`. Every number below is cited to its source query or notebook
cell — nothing here is illustrative or rounded for effect.

## 1. Dadra and Nagar Haveli combines the worst load factor in the country with a
   persistent shortage pattern

**Finding:** `sql/10_peak_vs_energy.sql` ranks Dadra and Nagar Haveli with the lowest
load factor of any state — **0.436** (average demand 325.3 MW against an average peak
of 747.0 MW). It also appears in `sql/05_shortage_hotspots.sql` with **12 quarters**
flagged above the 15%-of-days shortage threshold, more than all but 4 other states.

**Why it matters:** a load factor this low means the grid is built and paid for to
serve a peak that's rarely actually drawn — exactly the profile where battery storage
or demand-response delivers outsized value per MW invested, since storage can shave
the narrow peak this state is already provisioning for.

**Recommended action:** prioritize Dadra and Nagar Haveli as a first-wave candidate
for battery storage / demand-response procurement. The combination of worst-in-dataset
load factor and a recurring (not one-off) shortage pattern means the peak-stress
problem is real and ongoing, not a modeling artifact.

## 2. Jammu and Kashmir and Ladakh shows a near-permanent shortage condition

**Finding:** `sql/05_shortage_hotspots.sql` flags Jammu and Kashmir and Ladakh in
**20 of the 21 quarters** in the dataset's full date range (2020 Q1 through 2025 Q1) —
the most of any state, above the 15% threshold in nearly every quarter measured.

**Why it matters:** this isn't a seasonal spike or a bad year — it's the closest thing
in the data to a structural, near-permanent shortage condition. Most other flagged
states show up in a handful of stressed quarters; this region is essentially always
above threshold.

**Recommended action:** commission a dedicated root-cause review (transmission
constraint vs. generation shortfall vs. terrain/access factors) rather than applying
the generic storage/demand-response prescription that fits most other hotspot states —
the pattern here is different in kind, not just degree.

## 3. Goa is growing electricity demand faster than any other state

**Finding:** `sql/09_growth_leaders.sql` ranks Goa first by average FY-over-FY
energy-met growth at **+12.41% per year**, averaged across all 4 complete adjacent
financial-year pairs (FY2020-21 through FY2024-25) — ahead of Arunachal Pradesh
(+10.90%) and Odisha (+10.38%).

**Why it matters:** sustained double-digit annual growth compounds fast — at this
rate, Goa's demand roughly doubles every 6 years. A state growing this quickly is the
one most likely to outrun its existing capacity planning first, well before
slower-growing large states like Maharashtra (the largest consumer overall at 12.47%
of national energy met per `sql/03_state_ranking.sql`, but not a growth outlier).

**Recommended action:** review Goa's capacity and grid-infrastructure plans against
this specific growth rate, not national averages — a linear capacity plan will
under-provision a compounding-growth state like this one within a few years.

## 4. Delhi's demand is meaningfully, but not purely, temperature-driven

**Finding:** the notebook's OLS regression (`notebooks/analysis.ipynb`) on days above a
24°C cooling threshold shows Delhi's demand rising **4.87 MU for every additional
degree Celsius**, with **R² = 0.368** — temperature explains about 37% of day-to-day
demand variance above the threshold.

**Why it matters:** a real, quantified cooling-load relationship supports
demand-response and cooling-load management planning, but an R² of 0.368 means the
majority of variance comes from something else (day-of-week, long-term growth trend,
industrial load) — treating temperature as the dominant driver would overstate how
predictable a heatwave-driven spike really is.

**Recommended action:** use the 4.87 MU/°C figure as one input to summer
demand-response planning, not the sole driver — pair it with the day-of-week and
growth-trend patterns already surfaced (see below) rather than building a
forecast on temperature alone.

## 5. A deliberately simple forecast model is accurate enough for capacity-planning
   decision support — once a known data-quality issue is accounted for

**Finding:** the notebook's SARIMAX(1,1,1)×(1,0,1,7) 30-day forecast has a raw holdout
MAPE of 93.30% — but that number is dominated by a single source-data gap day
(2025-03-06, where only 1 of 34 states reported a non-null value). Excluding that one
day, **MAPE = 2.49%** over the remaining 29 days.

**Why it matters:** the 93.30% figure alone would (wrongly) suggest the forecast is
unusable; the 2.49% figure alone would (misleadingly) hide a real, recurring
data-quality issue. Both numbers, with the root cause traced back to the raw source
rows, tell the true story: the model is genuinely strong, and the source data has a
known, quantifiable gap pattern (12 dates identified in
`docs/data-dictionary.md`) that any consumer of this data — this forecast, the Power
BI dashboard, or a future analyst — needs to account for.

**Recommended action:** the forecast is trustworthy enough for 30-day capacity
planning use once the completeness-threshold fix (already implemented in
`sql/13_national_daily_validated.sql` and the Power BI DAX layer) is applied
upstream of any planning process that consumes this forecast.

## 6. No statistically significant evidence that evening-peak stress rose year over
   year — an honest negative result

**Finding:** the notebook's hypothesis test (H₀: no change in mean peak-to-average
demand ratio, FY2023-24 vs. FY2024-25, tested via Wilcoxon signed-rank across 31
states after a Shapiro-Wilk test showed non-normal differences) returned a test
statistic of 305.0 and **p = 0.1362**. Since p > 0.05, the test **fails to reject
H₀**.

**Why it matters:** it would be easy to assume evening-peak stress is worsening
year over year — several of the findings above point toward specific stressed
states — but at the national, cross-state level, this specific FY-over-FY comparison
does not provide statistically significant evidence of that broader trend. Reporting
this honestly, rather than omitting or reframing it, matters because a business report
that only shows confirming results isn't trustworthy.

**Recommended action:** treat the state-specific findings above (Dadra and Nagar
Haveli, Jammu and Kashmir and Ladakh) as targeted, evidence-backed priorities in their
own right — but do not extrapolate them into a claim of a nationwide worsening trend
without stronger evidence than this test provides. A repeat of this test with another
year or two of data would meaningfully sharpen the answer either way.
