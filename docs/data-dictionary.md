# GridPulse — Data Dictionary

## Status

**Pending:** Build Manual Phase 1.1, Steps 8-10 (manually inspecting the PSP report source in a
browser, comparing XLS/PDF for a date, and inspecting 4 files from different years) have not
been done yet — `report.grid-india.in` and `posoco.in` were both unreachable (DNS NXDOMAIN /
502 Bad Gateway) when this was attempted on 2026-08-17, confirmed as a genuine outage on
Grid-India's end (checked from two independent networks, not a local block).

The downloader (`src/download_psp.py`) was built against the URL pattern documented in the
Build Manual and confirmed via web search against real indexed URLs
(e.g. `https://report.grid-india.in/ReportData/Daily%20Report/PSP%20Report/2025-2026/May%202025/03.05.25_NLDC_PSP.pdf`),
but the actual file contents (sheet layout, header rows, column names, units) have not been
inspected firsthand. **This section must be filled in once the source is reachable again and
before the parser (`parse_psp.py`) is built** — the parser depends on knowing exactly where each
number lives in the sheet.

## URL pattern (confirmed against search-indexed live URLs)

```
https://report.grid-india.in/ReportData/Daily Report/PSP Report/{FY}/{Month YYYY}/{DD.MM.YY}_NLDC_PSP.{xls|pdf}
```

- `{FY}` — Indian financial year folder, e.g. `2024-2025` (1 April to 31 March). See `src/fy_utils.py::fy_folder`.
- `{Month YYYY}` — full month name + calendar year of the report date itself, e.g. `May 2025`.
- `{DD.MM.YY}` — report date, day/month/2-digit-year.
- Path segments contain literal spaces — must be percent-encoded per-segment (see `build_urls` in `src/download_psp.py`).

## Columns / fields (TO FILL IN once source is reachable)

| Field | Sheet location | Unit | Notes |
|---|---|---|---|
| energy_met | *pending* | MU (million units) | |
| peak_demand | *pending* | MW | |
| peak_met | *pending* | MW | |
| energy_shortage | *pending* | MU | |
| region groupings | *pending* | — | NR / WR / SR / ER / NER |

## Format drift across years (TO FILL IN)

Record anything that changed between report years here as it's discovered — sheet names,
header row position, extra/renamed columns, state-name variants (e.g. Orissa -> Odisha).
