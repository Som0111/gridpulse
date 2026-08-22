-- NOTE: numbered 11 for build order (written last), but this is a
-- data-quality check and belongs first in the READ order — run and read
-- this one before trusting any of 02-10.
--
-- Business question: Which states have missing report-days in the
-- backfilled history, and how many?
-- Expected output shape: ~34 rows (one per state), columns: state_name,
-- expected_days, actual_days, missing_days, pct_missing.
-- Key technique: generate_series() to build the full expected calendar,
-- CROSS JOIN with dim_state, then LEFT JOIN to fact_state_daily so
-- missing (state, date) combinations surface as NULL rows to count,
-- rather than silently not existing in the result at all.

WITH date_bounds AS (
    SELECT MIN(report_date) AS min_date, MAX(report_date) AS max_date
    FROM fact_state_daily
),
full_calendar AS (
    SELECT generate_series(min_date, max_date, interval '1 day')::date AS report_date
    FROM date_bounds
),
expected AS (
    SELECT ds.state_id, ds.state_name, fc.report_date
    FROM dim_state ds
    CROSS JOIN full_calendar fc
)
SELECT
    e.state_name,
    COUNT(*) AS expected_days,
    COUNT(f.report_date) AS actual_days,
    COUNT(*) - COUNT(f.report_date) AS missing_days,
    ROUND(100.0 * (COUNT(*) - COUNT(f.report_date)) / COUNT(*), 2) AS pct_missing
FROM expected e
LEFT JOIN fact_state_daily f
    ON f.state_id = e.state_id AND f.report_date = e.report_date
GROUP BY e.state_name
ORDER BY pct_missing DESC;
