-- Business question: How does average demand differ across summer,
-- monsoon, and winter, per state — which states are most seasonal?
-- Expected output shape: ~34 rows (one per state), columns: state_name,
-- avg_summer_mw, avg_monsoon_mw, avg_winter_mw, summer_to_winter_ratio.
-- Key technique: AVG(...) FILTER (WHERE season = 'X') to pivot 3 seasons
-- into 3 columns in one pass, instead of 3 separate GROUP BY queries.

SELECT
    ds.state_name,
    ROUND(AVG(f.peak_demand_mw) FILTER (WHERE dd.season = 'Summer'), 1) AS avg_summer_mw,
    ROUND(AVG(f.peak_demand_mw) FILTER (WHERE dd.season = 'Monsoon'), 1) AS avg_monsoon_mw,
    ROUND(AVG(f.peak_demand_mw) FILTER (WHERE dd.season = 'Winter'), 1) AS avg_winter_mw,
    ROUND(
        AVG(f.peak_demand_mw) FILTER (WHERE dd.season = 'Summer')
        / NULLIF(AVG(f.peak_demand_mw) FILTER (WHERE dd.season = 'Winter'), 0),
        2
    ) AS summer_to_winter_ratio
FROM fact_state_daily f
JOIN dim_state ds ON ds.state_id = f.state_id
JOIN dim_date dd ON dd.date_id = f.report_date
GROUP BY ds.state_name
ORDER BY summer_to_winter_ratio DESC NULLS LAST;
