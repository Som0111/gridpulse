"""Single entry point for the daily automated GridPulse update.

WHY this exists: GitHub Actions calls exactly this one script (Phase 5).
It downloads yesterday's report, parses it, and loads it — and, critically,
distinguishes an EXPECTED failure (the source site is down — exit 0, don't
turn the workflow red for something outside our control) from a REAL bug
(the pipeline ran but silently loaded nothing — exit 1, this must be
noticed).

WHY yesterday's date, not today's: Grid-India publishes each day's report
the following morning; "today's" report usually doesn't exist yet when
this runs at 11:00 IST.
"""

import json
import sys
from datetime import date, timedelta
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent))
from download_psp import USER_AGENT, download_one
import load_db

STATE_PATH = Path("data/raw/automation_state.json")


def load_state() -> dict:
    """WHY a state file: GitHub Actions runs are stateless between
    invocations — nothing in memory survives from one day's run to the
    next — so "how many times in a row has this failed" has to live on
    disk (committed... actually just persisted in the runner's checkout,
    see note in daily.yml) rather than in a variable."""
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    return {"consecutive_zero_row_loads": 0}


def save_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state), encoding="utf-8")


def main() -> int:
    yesterday = date.today() - timedelta(days=1)
    print(f"daily_update: target date = {yesterday}")

    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    path, status = download_one(session, yesterday)

    if status == "failed":
        print(
            f"WARNING: could not download a report for {yesterday} "
            f"(site down, 404, or timeout). Treating this as an expected "
            f"external outage, not a pipeline bug — exiting 0 so the "
            f"workflow doesn't go red for something outside our control."
        )
        return 0

    print(f"{status} report for {yesterday}: {path}")

    # WHY this import is deliberately lazy (inside the function, only
    # reached after a successful download) rather than at module level:
    # src/parse_psp.py (Phase 1.3) has not been built yet, because
    # report.grid-india.in has been down since this project started —
    # there has been nothing to build/test a live parser against. A
    # top-level `from parse_psp import ...` would crash THIS script on
    # every single run, including the expected-failure path above, which
    # defeats the entire point of failing softly on a known outage. Doing
    # the import here means: today, downloads keep failing, so this line
    # never executes and the script behaves correctly. The moment a
    # download actually succeeds, this import runs for real — if
    # parse_psp.py still doesn't exist by then, that's a genuine gap, so
    # it fails loudly (exit 1) instead of silently skipping the load.
    try:
        from parse_psp import parse_file
    except ImportError as exc:
        print(
            f"ERROR: downloaded {path} but src/parse_psp.py doesn't exist "
            f"yet (Phase 1.3 was never completed — the live site has been "
            f"down this whole project). Cannot parse or load. Build "
            f"parse_psp.py before this code path can succeed. ({exc})"
        )
        return 1

    # Contract expected of parse_psp.parse_file: takes the downloaded
    # file's path, parses it, and appends/updates
    # data/staging/state_daily.csv in the same tidy 6-column shape
    # parse_kaggle_backfill.py already produces (report_date, state,
    # energy_met_mu, energy_shortage_mu, peak_demand_mw, peak_met_mw) —
    # see docs/data-dictionary.md's "Next step once report.grid-india.in
    # recovers" note.
    parse_file(path)

    upserted = load_db.main(since=yesterday.isoformat())

    state = load_state()
    if upserted == 0:
        state["consecutive_zero_row_loads"] = state.get("consecutive_zero_row_loads", 0) + 1
        save_state(state)
        if state["consecutive_zero_row_loads"] >= 2:
            print(
                f"ERROR: 0 rows loaded for {state['consecutive_zero_row_loads']} "
                f"consecutive tracked attempts. The report downloaded and "
                f"(supposedly) parsed successfully, but nothing loaded into "
                f"Neon — this is a real bug, not an expected outage. Failing loudly."
            )
            return 1
        print(
            f"WARNING: 0 rows loaded for {yesterday}. First occurrence — "
            f"tolerated once. Will fail loudly if this repeats next run."
        )
        return 0

    state["consecutive_zero_row_loads"] = 0
    save_state(state)
    print(f"OK: {upserted} row(s) loaded for {yesterday}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
