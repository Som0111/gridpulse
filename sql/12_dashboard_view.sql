-- Business question: none directly — this is a plumbing view, not an
-- analysis query. It flattens the star schema into one wide table so
-- Power BI (and any other BI tool) can import a single source instead of
-- modeling 4 tables' relationships itself.
-- Expected output shape: one row per (state, report_date) present in
-- fact_state_daily — ~65,178 rows, columns: report_date, state_name,
-- region_code, energy_met_mu, energy_shortage_mu, peak_demand_mw,
-- peak_met_mw, tmean_c, is_weekend, season, fin_year.
--
-- WHY LEFT JOIN to fact_weather_daily: weather is only loaded for 8
-- proxy-city states, not all 34 — an INNER JOIN would silently drop the
-- other 26 states from the whole dashboard. tmean_c is simply NULL for
-- states without a weather proxy, which Power BI handles natively.

CREATE OR REPLACE VIEW v_dashboard_daily AS
SELECT
    f.report_date,
    ds.state_name,
    ds.region_code,
    f.energy_met_mu,
    f.energy_shortage_mu,
    f.peak_demand_mw,
    f.peak_met_mw,
    w.tmean_c,
    dd.is_weekend,
    dd.season,
    dd.fin_year
FROM fact_state_daily f
JOIN dim_state ds ON ds.state_id = f.state_id
JOIN dim_date dd ON dd.date_id = f.report_date
LEFT JOIN fact_weather_daily w
    ON w.state_id = f.state_id AND w.report_date = f.report_date;
