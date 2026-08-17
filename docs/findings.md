# GridPulse — Findings

Findings below are drawn from real query output against the live Neon database
(65,178 rows, 34 states, 2020-01-01 to 2025-03-31, backfilled from the Kaggle
fallback dataset — see `docs/data-dictionary.md`). Each cites the exact query
and numbers produced.

## 1. Dadra and Nagar Haveli is India's peakiest grid — and a persistent
   shortage state

**Finding:** `sql/10_peak_vs_energy.sql` ranks Dadra and Nagar Haveli with the
lowest load factor in the country — **0.436** (average demand 325.3 MW against
an average peak of 747.0 MW). It also appears in `sql/05_shortage_hotspots.sql`
with **12 quarters** flagged above the 15%-of-days shortage threshold — more
than all but 4 other states.

**Why it matters:** a load factor this low means the grid is built and paid
for to serve a peak that's rarely actually drawn — the definition of a state
where battery storage or demand-response would deliver outsized value per MW
invested, since storage can shave exactly the narrow peak this state is
paying to provision for.

**Recommended action:** Dadra and Nagar Haveli should be a first-wave
candidate for battery storage / demand-response procurement — it combines
the worst load factor in the dataset with a genuinely recurring (not
one-off) shortage pattern, meaning the peak-stress problem is real and
ongoing, not a modeling artifact.

## 2. Jammu and Kashmir and Ladakh has had shortage in 20 of the last 21
   quarters

**Finding:** `sql/05_shortage_hotspots.sql` flags Jammu and Kashmir and Ladakh
in **20 of the 21 quarters** in the dataset's full date range (2020 Q1 through
2025 Q1) — the most quarters of any state, well above the 15% threshold in
nearly every one.

**Why it matters:** this isn't a seasonal spike or a single bad year — it's
the closest thing in the data to a structural, near-permanent shortage
condition. Where most flagged states show up in a handful of stressed
quarters, this region is essentially always above threshold.

**Recommended action:** this state warrants a dedicated root-cause look
(transmission constraint vs. generation shortfall vs. terrain/access
factors) rather than the generic storage/demand-response prescription that
fits most other hotspot states — its shortage pattern is different in kind,
not just degree, from the rest of the list.

## 3. Goa is growing electricity demand faster than any other state

**Finding:** `sql/09_growth_leaders.sql` ranks Goa first by average
FY-over-FY energy-met growth at **+12.41%** per year, averaged across all 4
complete adjacent financial-year pairs (FY2020-21 through FY2024-25) — ahead
of Arunachal Pradesh (+10.90%) and Odisha (+10.38%).

**Why it matters:** sustained double-digit annual growth compounds fast — at
this rate, Goa's demand roughly doubles every 6 years. A state growing this
quickly is the one most likely to outrun its existing capacity planning
first, well before slower-growing large states like Maharashtra (the
largest consumer overall at 12.47% of national energy met per
`sql/03_state_ranking.sql`, but not a growth outlier).

**Recommended action:** Goa's capacity and grid-infrastructure planning
should be reviewed against this growth rate specifically, rather than
benchmarked against national averages — a linear capacity plan will
under-provision a compounding-growth state like this one within a few
years.

## Data-quality note (from `sql/11_coverage_audit.sql`)

Row-level date coverage is complete: **all 34 states have a fact row for
every one of the 1,917 days** in range (0.0% missing on every state, not
just on average). This is a distinct signal from the ~5-9% per-column
*value* nulls already documented in `docs/data-dictionary.md` — the source
consistently reports a row per state per day, it just sometimes leaves the
numeric fields blank within that row. Worth stating explicitly since the two
kinds of "missing data" would otherwise get conflated.
