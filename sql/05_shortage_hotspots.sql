-- Business question: Which states have persistent (not one-off) energy
-- shortage problems, quarter by quarter?
-- Expected output shape: a handful of rows (states x quarters that clear
-- the threshold) out of ~34 states x ~21 quarters = ~714 possible rows,
-- columns: state_name, quarter, days_in_quarter, shortage_days,
-- pct_days_with_shortage.
-- Key technique: COUNT(*) FILTER (WHERE ...) to count shortage-days
-- alongside total days in one pass, then HAVING to filter to states/
-- quarters clearing the persistence threshold.
--
-- Threshold justification: a quarter has ~90 days. Flagging at >=15% of
-- days (~13+ days) distinguishes a recurring structural issue from a
-- one-off event (e.g. a single equipment failure causing shortage for
-- 2-3 days). 15% is strict enough to exclude noise but loose enough to
-- surface states with a real recurring pattern rather than only the most
-- extreme crisis states — chosen deliberately looser than "50%+" so this
-- query is useful for early-warning, not just disaster reporting.

WITH quarterly AS (
    SELECT
        ds.state_name,
        date_trunc('quarter', f.report_date)::date AS quarter,
        COUNT(*) AS days_in_quarter,
        COUNT(*) FILTER (WHERE f.energy_shortage_mu > 0) AS shortage_days
    FROM fact_state_daily f
    JOIN dim_state ds ON ds.state_id = f.state_id
    GROUP BY ds.state_name, date_trunc('quarter', f.report_date)
)
SELECT
    state_name,
    quarter,
    days_in_quarter,
    shortage_days,
    ROUND(100.0 * shortage_days / days_in_quarter, 1) AS pct_days_with_shortage
FROM quarterly
GROUP BY state_name, quarter, days_in_quarter, shortage_days
HAVING 100.0 * shortage_days / days_in_quarter >= 15.0
ORDER BY pct_days_with_shortage DESC, state_name, quarter;
