"""Download Grid-India daily PSP (Power Supply Position) reports.

WHY this exists: PSP reports are the raw source for the whole GridPulse
pipeline. This module fetches them for a date range and saves them
untouched to data/raw/ — later steps (parse_psp.py) never re-download,
they only read what's already here.
"""

import argparse
import time
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import quote

import requests

from fy_utils import fy_folder

BASE_URL = "https://report.grid-india.in/ReportData"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
SLEEP_SECONDS = 3
MAX_RETRIES = 2
RAW_DIR = Path("data/raw")


def build_urls(d: date) -> list[str]:
    """Return candidate report URLs for a date, .xls first then .pdf.

    WHY: the report path has literal spaces (e.g. "Daily Report"), so each
    path segment must be percent-encoded individually rather than the whole
    URL at once, or the encoding of '/' would break the path structure.
    """
    fy = fy_folder(d)
    month_folder = d.strftime("%B %Y")
    filename_stem = d.strftime("%d.%m.%y") + "_NLDC_PSP"

    def encoded_path(*segments: str) -> str:
        return "/".join(quote(seg) for seg in segments)

    urls = []
    for ext in ("xls", "pdf"):
        path = encoded_path(
            "Daily Report", "PSP Report", fy, month_folder, f"{filename_stem}.{ext}"
        )
        urls.append(f"{BASE_URL}/{path}")
    return urls


def date_range(start: date, end: date):
    """Yield each date from start to end, inclusive."""
    current = start
    while current <= end:
        yield current
        current += timedelta(days=1)


def fetch_one(session: requests.Session, url: str) -> requests.Response | None:
    """Try one URL, retrying MAX_RETRIES times on network errors. Return None on failure."""
    for attempt in range(MAX_RETRIES + 1):
        try:
            resp = session.get(url, timeout=30)
            if resp.status_code == 200:
                return resp
            return None  # 404 etc — not a network error, don't retry
        except requests.RequestException:
            if attempt == MAX_RETRIES:
                return None
            time.sleep(SLEEP_SECONDS)
    return None


def download_range(start: date, end: date) -> None:
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})

    failed_path = RAW_DIR / "failed_dates.txt"
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    downloaded = skipped = failed = 0

    for d in date_range(start, end):
        year_dir = RAW_DIR / str(d.year)
        urls = build_urls(d)

        # Skip if either extension already exists on disk.
        existing = next(
            (year_dir / Path(u).name for u in urls if (year_dir / Path(u).name).exists()),
            None,
        )
        if existing:
            print(f"skip  {d}  (already have {existing.name})")
            skipped += 1
            continue

        saved = False
        for url in urls:
            resp = fetch_one(session, url)
            time.sleep(SLEEP_SECONDS)
            if resp is not None:
                year_dir.mkdir(parents=True, exist_ok=True)
                dest = year_dir / Path(url).name
                dest.write_bytes(resp.content)
                print(f"OK    {d}  -> {dest}")
                downloaded += 1
                saved = True
                break

        if not saved:
            print(f"FAIL  {d}  (no format available)")
            with failed_path.open("a", encoding="utf-8") as f:
                f.write(f"{d.isoformat()}\n")
            failed += 1

    print(f"\nSummary: downloaded={downloaded} skipped={skipped} failed={failed}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Download Grid-India daily PSP reports.")
    parser.add_argument("--start", required=True, help="YYYY-MM-DD")
    parser.add_argument("--end", required=True, help="YYYY-MM-DD")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    start_date = date.fromisoformat(args.start)
    end_date = date.fromisoformat(args.end)
    download_range(start_date, end_date)
