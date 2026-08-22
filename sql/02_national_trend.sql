-- Business question: How is national energy demand trending month over
-- month, and how does each month compare to the same month a year ago?
-- Expected output shape: ~63 rows (one per calendar month, Jan 2020 to
-- Mar 2025), columns: month, national_energy_met_mu, prior_year_mu,
-- yoy_growth_pct.
-- Key technique: LAG(value, 12) OVER (ORDER BY month) to pull the same
-- calendar month from 12 rows back (one year prior), for same-period YoY %.

WITH monthly AS (
    SELECT
        date_trunc('month', report_date)::date AS month,
        SUM(energy_met_mu) AS national_energy_met_mu
    FROM fact_state_daily
    GROUP BY 1
)
SELECT
    month,
    national_energy_met_mu,
    LAG(national_energy_met_mu, 12) OVER (ORDER BY month) AS prior_year_mu,
    ROUND(
        100.0 * (
            national_energy_met_mu - LAG(national_energy_met_mu, 12) OVER (ORDER BY month)
        ) / NULLIF(LAG(national_energy_met_mu, 12) OVER (ORDER BY month), 0),
        2
    ) AS yoy_growth_pct
FROM monthly
ORDER BY month;
