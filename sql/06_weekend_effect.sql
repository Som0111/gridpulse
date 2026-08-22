-- Business question: How much does electricity demand drop on weekends
-- vs weekdays, per region — is there a schedulable maintenance window?
-- Expected output shape: 5 rows (one per region: NR/WR/SR/ER/NER),
-- columns: region_code, avg_weekday_demand_mw, avg_weekend_demand_mw,
-- pct_difference.
-- Key technique: CASE to bucket day_of_week into weekday/weekend, then a
-- self-join of the two bucket averages per region to compute % difference
-- directly in SQL rather than post-processing two separate query results.

WITH bucketed AS (
    SELECT
        ds.region_code,
        CASE WHEN dd.is_weekend THEN 'weekend' ELSE 'weekday' END AS day_bucket,
        f.peak_demand_mw
    FROM fact_state_daily f
    JOIN dim_state ds ON ds.state_id = f.state_id
    JOIN dim_date dd ON dd.date_id = f.report_date
),
region_bucket_avg AS (
    SELECT
        region_code,
        day_bucket,
        AVG(peak_demand_mw) AS avg_demand_mw
    FROM bucketed
    GROUP BY region_code, day_bucket
)
SELECT
    weekday.region_code,
    ROUND(weekday.avg_demand_mw, 1) AS avg_weekday_demand_mw,
    ROUND(weekend.avg_demand_mw, 1) AS avg_weekend_demand_mw,
    ROUND(
        100.0 * (weekend.avg_demand_mw - weekday.avg_demand_mw) / NULLIF(weekday.avg_demand_mw, 0),
        2
    ) AS pct_difference
FROM region_bucket_avg weekday
JOIN region_bucket_avg weekend
    ON weekend.region_code = weekday.region_code
    AND weekday.day_bucket = 'weekday'
    AND weekend.day_bucket = 'weekend'
ORDER BY pct_difference;
