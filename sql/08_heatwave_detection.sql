-- Business question: Which specific days did a state's demand spike far
-- above its own recent normal — candidate heatwave-driven demand events?
-- Expected output shape: a small subset of the ~65,000 rows (outlier
-- days only), columns: state_name, report_date, peak_demand_mw,
-- trailing_90d_mean_mw, trailing_90d_stddev_mw, is_outlier.
-- Key technique: window AVG()/STDDEV() over a trailing 90-row frame to
-- build a per-state, self-referential "mean + 2 sigma" outlier threshold.
--
-- The trailing window is the 90 days BEFORE today (89 PRECEDING AND
-- 1 PRECEDING), deliberately excluding the current row — including
-- today's own spike in its own baseline would inflate the mean/stddev
-- and make the spike look less extreme than it is.

WITH windowed AS (
    SELECT
        ds.state_name,
        f.report_date,
        f.peak_demand_mw,
        AVG(f.peak_demand_mw) OVER (
            PARTITION BY f.state_id
            ORDER BY f.report_date
            ROWS BETWEEN 90 PRECEDING AND 1 PRECEDING
        ) AS trailing_90d_mean_mw,
        STDDEV(f.peak_demand_mw) OVER (
            PARTITION BY f.state_id
            ORDER BY f.report_date
            ROWS BETWEEN 90 PRECEDING AND 1 PRECEDING
        ) AS trailing_90d_stddev_mw
    FROM fact_state_daily f
    JOIN dim_state ds ON ds.state_id = f.state_id
),
flagged AS (
    SELECT
        state_name,
        report_date,
        peak_demand_mw,
        ROUND(trailing_90d_mean_mw, 1) AS trailing_90d_mean_mw,
        ROUND(trailing_90d_stddev_mw, 1) AS trailing_90d_stddev_mw,
        CASE
            WHEN peak_demand_mw > trailing_90d_mean_mw + 2 * trailing_90d_stddev_mw
            THEN TRUE ELSE FALSE
        END AS is_outlier
    FROM windowed
    WHERE trailing_90d_mean_mw IS NOT NULL
)
SELECT *
FROM flagged
WHERE is_outlier
ORDER BY state_name, report_date;
