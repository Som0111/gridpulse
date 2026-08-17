-- sql/00_schema.sql
-- GridPulse star schema. Safe to re-run (IF NOT EXISTS on every table).

CREATE TABLE IF NOT EXISTS dim_state (
  state_id      SERIAL PRIMARY KEY,
  state_name    TEXT UNIQUE NOT NULL,
  region_code   TEXT NOT NULL,          -- NR / WR / SR / ER / NER
  is_ut         BOOLEAN DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS dim_date (
  date_id       DATE PRIMARY KEY,
  year INT, month INT, day INT,
  day_of_week   INT,                    -- 0 = Monday
  is_weekend    BOOLEAN,
  fin_year      TEXT,                   -- '2024-2025'
  season        TEXT                    -- Summer/Monsoon/Winter
);

CREATE TABLE IF NOT EXISTS fact_state_daily (
  report_date        DATE REFERENCES dim_date(date_id),
  state_id           INT  REFERENCES dim_state(state_id),
  energy_met_mu      NUMERIC,
  energy_shortage_mu NUMERIC,
  peak_demand_mw     NUMERIC,
  peak_met_mw        NUMERIC,
  loaded_at          TIMESTAMPTZ DEFAULT now(),
  PRIMARY KEY (report_date, state_id)
);
