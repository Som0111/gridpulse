-- Business question: What is each state's 30-day rolling maximum peak
-- demand, day by day? (Feeds the Peak Stress dashboard page and
-- heatwave-style analyses.)
-- Expected output shape: one row per (state, report_date) — roughly
-- 65,000 rows for the full backfill, columns: state_name, report_date,
-- peak_demand_mw, rolling_30d_max_mw.
-- Key technique: MAX() OVER (PARTITION BY state_id ORDER BY report_date
-- ROWS BETWEEN 29 PRECEDING AND CURRENT ROW) — a 30-row rolling max.
--
-- WHY ROWS, not RANGE: ROWS BETWEEN 29 PRECEDING AND CURRENT ROW counts
-- the 30 most recent *physical rows* for that state, regardless of any
-- gaps in report_date. RANGE would instead define the window by the
-- *value* of report_date (e.g. "dates within 29 days"), so a missing
-- report day would silently shrink the row count inside the same date
-- span, or a gap could pull in fewer than 30 real observations without
-- it being obvious from the output. Since this dataset already has known
-- date gaps (see docs/data-dictionary.md), ROWS keeps "30-day rolling
-- max" meaning "max of the last 30 *reports*", which is the honest
-- definition given imperfect coverage — RANGE would quietly change
-- meaning on every gap.

SELECT
    ds.state_name,
    f.report_date,
    f.peak_demand_mw,
    MAX(f.peak_demand_mw) OVER (
        PARTITION BY f.state_id
        ORDER BY f.report_date
        ROWS BETWEEN 29 PRECEDING AND CURRENT ROW
    ) AS rolling_30d_max_mw
FROM fact_state_daily f
JOIN dim_state ds ON ds.state_id = f.state_id
ORDER BY ds.state_name, f.report_date;
