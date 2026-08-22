-- sql/00_schema.sql
-- Purpose: the GridPulse star schema — 2 dimension tables (dim_state,
-- dim_date) and 2 fact tables (fact_state_daily, fact_weather_daily).
-- Key technique: CREATE TABLE IF NOT EXISTS on every table (safe to
-- re-run) + composite PRIMARY KEY (report_date, state_id) on both fact
-- tables, which is what makes every loader's ON CONFLICT ... DO UPDATE
-- upsert idempotent by construction — duplicates are impossible, not
-- just avoided by convention.

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

CREATE TABLE IF NOT EXISTS fact_weather_daily (
  report_date   DATE REFERENCES dim_date(date_id),
  state_id      INT  REFERENCES dim_state(state_id),
  tmax_c        NUMERIC,
  tmin_c        NUMERIC,
  tmean_c       NUMERIC,
  loaded_at     TIMESTAMPTZ DEFAULT now(),
  PRIMARY KEY (report_date, state_id)
);
