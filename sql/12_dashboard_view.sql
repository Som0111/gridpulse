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
--
-- WHY states_reporting_energy / is_complete_day: on a handful of dates
-- almost every state's energy_met_mu is NULL in the source data, but
-- 1-2 states still have a value (sometimes a real-looking nonzero
-- number). SUM() ignores NULLs rather than propagating them, so a
-- national total built by summing this view's rows for a date produces
-- a tiny but non-NULL number instead of an obvious gap — this is what
-- caused the false crash-to-zero spikes in the Power BI trend chart.
-- See docs/data-dictionary.md "Completeness threshold" section for the
-- 12 known bad dates and the >=30/34 threshold justification.
-- states_reporting_energy is a per-report_date window count (same value
-- repeated on every state's row for that date, by design — it's a
-- date-level fact denormalized onto the state-level grain so DAX
-- measures and any consumer can filter on it without a second query).

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
    dd.fin_year,
    COUNT(f.energy_met_mu) OVER (PARTITION BY f.report_date) AS states_reporting_energy,
    COUNT(f.energy_met_mu) OVER (PARTITION BY f.report_date) >= 30 AS is_complete_day
FROM fact_state_daily f
JOIN dim_state ds ON ds.state_id = f.state_id
JOIN dim_date dd ON dd.date_id = f.report_date
LEFT JOIN fact_weather_daily w
    ON w.state_id = f.state_id AND w.report_date = f.report_date;
