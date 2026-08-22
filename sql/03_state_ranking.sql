-- Business question: Which 10 states consume the most electricity overall,
-- and what share of national demand does each represent?
-- Expected output shape: 10 rows, columns: rank, state_name,
-- total_energy_met_mu, pct_share_national.
-- Key technique: RANK() OVER (ORDER BY total DESC) for the ranking, plus
-- a window SUM() OVER () (no PARTITION BY) to get the grand total for a
-- percent-of-whole share, both in one pass without a self-join.

WITH state_totals AS (
    SELECT
        ds.state_name,
        SUM(f.energy_met_mu) AS total_energy_met_mu
    FROM fact_state_daily f
    JOIN dim_state ds ON ds.state_id = f.state_id
    GROUP BY ds.state_name
)
SELECT
    RANK() OVER (ORDER BY total_energy_met_mu DESC) AS rank,
    state_name,
    total_energy_met_mu,
    ROUND(
        100.0 * total_energy_met_mu / SUM(total_energy_met_mu) OVER (),
        2
    ) AS pct_share_national
FROM state_totals
ORDER BY rank
LIMIT 10;
