"""One-off generator for tests/fixtures/*.xls synthetic PSP report files.

WHY these are HTML tables saved with a .xls extension rather than true
binary .xls: this is itself a documented real-world PSP report quirk
(parse_psp.py's read_raw_table falls back to pandas.read_html for exactly
this case), and it's the only .xls-like format this environment can
generate without adding a new dependency (xlwt, for legacy binary .xls
writing, isn't installed and isn't otherwise needed by the project).
The true-xlrd-binary code path is instead covered in test_parse_psp.py by
monkeypatching pandas.read_excel — see that file's comment.

Run this once to (re)generate the fixtures; not part of the pipeline.
"""

from pathlib import Path

import pandas as pd

FIXTURES_DIR = Path(__file__).parent


def write_fixture(name: str, rows: list[list]) -> None:
    df = pd.DataFrame(rows)
    html = df.to_html(index=False, header=False)
    (FIXTURES_DIR / name).write_text(html, encoding="utf-8")


BANNER = ["GRID-INDIA — Daily Power Supply Position Report", "", "", ""]
BLANK = ["", "", "", ""]
HEADER = ["State", "Energy Met(MU)", "Energy Shortage(MU)", "Max.Demand Met(MW)", "Shortage during Max.Demand(MW)"]

NORMAL_STATE_ROWS = [
    ["Andhra Pradesh", 170.1, 0, 8561, 0],
    ["Bihar", 82.0, 0, 4656, 0],
    ["Delhi", 81.0, 0, 4108, 0],
    ["Punjab", 200.0, 0, 9000, 0],
    ["Odisha", 90.0, 0.1, 4200, 10],
]
NORMAL_REGION_ROWS = [
    ["NR", 361.1, 0, 17108, 0],
    ["All India", 623.1, 0.1, 30525, 10],
]

# WHY these filenames follow DD.MM.YY_NLDC_PSP exactly: that's the pattern
# parse_date_from_filename requires (matching download_psp.py's naming),
# so fixtures must use it directly rather than a descriptive name.

# Fixture 1 (01.06.25): normal, well-formed, header at a small fixed offset.
write_fixture(
    "01.06.25_NLDC_PSP.xls",
    [HEADER, *NORMAL_STATE_ROWS, *NORMAL_REGION_ROWS],
)

# Fixture 2 (02.06.25): same data, but header pushed down by extra
# banner/blank rows — proves the parser locates the header by search, not
# a hardcoded index.
write_fixture(
    "02.06.25_NLDC_PSP.xls",
    [BANNER, BLANK, BANNER, HEADER, *NORMAL_STATE_ROWS, *NORMAL_REGION_ROWS],
)

# Fixture 3: legacy/variant state name spellings that STATE_NAME_MAP must
# normalize (Orissa -> Odisha, Pondicherry -> Puducherry).
VARIANT_STATE_ROWS = [
    ["Andhra Pradesh", 170.1, 0, 8561, 0],
    ["Orissa", 90.0, 0.1, 4200, 10],
    ["Pondicherry", 4.9, 0, 300, 0],
]
VARIANT_REGION_ROWS = [
    ["All India", 264.9 + 0.1, 0.1, 13061, 10],
]
write_fixture(
    "03.06.25_NLDC_PSP.xls",
    [HEADER, *VARIANT_STATE_ROWS, *VARIANT_REGION_ROWS],
)

# Fixture 4 (04.06.25): state sum deliberately deviates >5% from the All
# India row — should trigger validate_against_all_india's warning.
write_fixture(
    "04.06.25_NLDC_PSP.xls",
    [HEADER, *NORMAL_STATE_ROWS, ["All India", 900.0, 0.1, 30525, 10]],
)

print("wrote fixtures:", [p.name for p in FIXTURES_DIR.glob("*.xls")])
