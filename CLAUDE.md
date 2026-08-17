# GridPulse — Project rules for Claude Code

## What this is
Portfolio data-analyst project: ingest Grid-India (POSOCO) daily PSP reports,
store in Neon Postgres (star schema), analyze with SQL + Python, visualize in
Power BI, refresh daily via GitHub Actions.

## Hard rules
- Python 3.12, system Python, no virtual environment. Windows paths.
- Secrets ONLY via .env / os.environ. Never hardcode the DB URL.
- All DB writes must be idempotent (ON CONFLICT DO UPDATE). Re-running a load
  for the same date must never create duplicates.
- Downloads: 3-second sleep between requests, standard browser User-Agent,
  retry failed dates into data/raw/failed_dates.txt instead of crashing.
- Keep functions small and explained. I am learning — add a short docstring
  to every function saying WHY it exists, not just what it does.
- SQL analysis queries live in /sql, numbered (01_xxx.sql), each with a
  comment header: business question, expected output shape.
- Never delete rows in data/raw. Raw files are immutable evidence.

## Style
- pandas for parsing, SQLAlchemy for DB, no ORM models.
- Prefer boring readable code over clever code.
