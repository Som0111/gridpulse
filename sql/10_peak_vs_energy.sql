-- Business question: Which states are "peakiest" — i.e. their grid is
-- sized for a peak far above their average draw — and therefore the best
-- candidates for battery storage / demand-response investment?
-- Expected output shape: ~34 rows (one per state), columns: state_name,
-- avg_peak_met_mw, avg_demand_mw (energy converted to an average-MW
-- basis), load_factor.
-- Key technique: unit-normalize energy (MU/day) to an average-MW basis
-- (energy_mu * 1000 / 24) so it's directly comparable to peak_met_mw on
-- the same scale — the load_factor ratio only means something once both
-- sides are in MW.
--
-- Business interpretation: load_factor = average demand / peak demand.
-- A load factor near 1.0 means the state draws close to its peak all the
-- time (efficient, flat usage — little benefit from storage). A LOW load
-- factor means the grid is built to serve a peak that's rarely needed —
-- classic battery-storage territory, since storage can shave the peak
-- and discharge into the flatter average load, avoiding the cost of
-- infrastructure sized for a peak used only briefly each day.
-- energy_met_mu is in MU/day (1 MU = 1 GWh); converting to an average-MW
-- basis: avg_demand_mw = (energy_met_mu * 1000) / 24, so it's on the same
-- MW scale as peak_met_mw and the ratio is meaningful.

SELECT
    ds.state_name,
    ROUND(AVG(f.peak_met_mw), 1) AS avg_peak_met_mw,
    ROUND(AVG(f.energy_met_mu) * 1000 / 24, 1) AS avg_demand_mw,
    ROUND(
        (AVG(f.energy_met_mu) * 1000 / 24) / NULLIF(AVG(f.peak_met_mw), 0),
        3
    ) AS load_factor
FROM fact_state_daily f
JOIN dim_state ds ON ds.state_id = f.state_id
GROUP BY ds.state_name
ORDER BY load_factor ASC;
