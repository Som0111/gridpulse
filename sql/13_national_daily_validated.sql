-- Business question: none directly — this is a plumbing view, not an
-- analysis query. It's the completeness-validated version of "sum
-- energy_met_mu across all states, per date" that every national trend
-- chart / notebook series should use instead of a raw SUM ... GROUP BY.
-- Expected output shape: one row per report_date (1,917 rows), columns:
-- report_date, national_energy_met_mu (NULL on incomplete days),
-- states_reporting.
-- Key technique: CASE WHEN COUNT(...) >= 30 THEN SUM(...) END — the
-- omitted ELSE means an incomplete day returns SQL NULL, not a number.
--
-- WHY this exists: see sql/12_dashboard_view.sql's is_complete_day
-- comment and docs/data-dictionary.md's "Completeness threshold"
-- section. A plain SUM(energy_met_mu) GROUP BY report_date silently
-- turns "almost every state is missing" into a tiny but real-looking
-- number instead of an obvious gap, because SQL's SUM ignores NULLs.
-- This view makes that judgment call explicit and inspectable instead
-- of leaving each chart/query to (not) handle it independently.
--
-- Threshold: >=30 of 34 states must have a non-null energy_met_mu for a
-- day's national total to be trusted; below that, national_energy_met_mu
-- is NULL rather than a misleading small number. 30/34 (~88%) was chosen
-- by inspecting the real distribution of states_reporting across all
-- 1,917 days: it sits at a sharp natural cliff — 1,873 days (97.7%) have
-- 30-34 states reporting, while only 44 days (2.3%) fall below 30, and
-- those 44 are themselves concentrated at the extreme low end (29 days
-- have 0-2 states reporting). There is no meaningful population of days
-- sitting just below 30 that this threshold wrongly excludes.

CREATE OR REPLACE VIEW v_national_daily AS
SELECT
    report_date,
    CASE WHEN COUNT(energy_met_mu) >= 30 THEN SUM(energy_met_mu) END AS national_energy_met_mu,
    COUNT(energy_met_mu) AS states_reporting
FROM fact_state_daily
GROUP BY report_date;
