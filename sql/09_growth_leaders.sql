-- Business question: Which states have grown fastest in electricity
-- consumption, financial-year over financial-year?
-- Expected output shape: ~34 rows (one per state with enough history),
-- columns: state_name, fy_pairs_used, avg_yoy_growth_pct.
--
-- Approach: build one row per (state, financial year) total, keeping only
-- FYs with >=350 reported days (excludes the partial first FY 2019-2020,
-- which only has Jan-Mar 2020 and would otherwise look like a huge
-- fake "drop" the following year). Self-join each FY to the next FY for
-- the same state to get FY-over-FY growth, then average those growth
-- rates per state as an approximate multi-year CAGR.

WITH annual AS (
    SELECT
        ds.state_id,
        ds.state_name,
        dd.fin_year,
        split_part(dd.fin_year, '-', 1)::int AS fy_start_year,
        SUM(f.energy_met_mu) AS total_energy_mu,
        COUNT(*) AS days_reported
    FROM fact_state_daily f
    JOIN dim_state ds ON ds.state_id = f.state_id
    JOIN dim_date dd ON dd.date_id = f.report_date
    GROUP BY ds.state_id, ds.state_name, dd.fin_year
),
complete_years AS (
    SELECT * FROM annual WHERE days_reported >= 350
),
fy_pairs AS (
    SELECT
        a.state_name,
        a.fin_year AS from_fy,
        b.fin_year AS to_fy,
        a.total_energy_mu AS from_total,
        b.total_energy_mu AS to_total,
        100.0 * (b.total_energy_mu - a.total_energy_mu) / NULLIF(a.total_energy_mu, 0) AS yoy_growth_pct
    FROM complete_years a
    JOIN complete_years b
        ON b.state_id = a.state_id
        AND b.fy_start_year = a.fy_start_year + 1
)
SELECT
    state_name,
    COUNT(*) AS fy_pairs_used,
    ROUND(AVG(yoy_growth_pct), 2) AS avg_yoy_growth_pct
FROM fy_pairs
GROUP BY state_name
ORDER BY avg_yoy_growth_pct DESC;
