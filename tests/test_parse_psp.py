"""Tests for parse_psp.py against synthetic fixtures.

WHY synthetic, not real files: report.grid-india.in has been down
throughout this project — see the warning at the top of src/parse_psp.py.
These tests prove the parsing LOGIC (anchor search, column identification,
state-name normalization, validation) is correct against realistic
structures; they do NOT prove the real report matches these assumptions.

WHY the true-xlrd-binary code path is tested via monkeypatch rather than a
real .xls fixture: writing a legitimate legacy binary .xls requires xlwt,
which isn't installed and isn't otherwise needed by this project — see
tests/fixtures/make_fixtures.py's docstring. Monkeypatching
pandas.read_excel to raise (simulating "this isn't a real binary xls")
lets us verify the read_html FALLBACK path is reached correctly; the
fixtures themselves (genuine HTML-disguised-as-.xls files) already cover
that fallback path directly without any mocking, since pandas.read_excel
genuinely fails on them and read_html genuinely succeeds — no monkeypatch
needed for that half. The monkeypatch below is only for confirming the
xlrd-success path also works when it doesn't fail.
"""

from pathlib import Path

import pandas as pd
import pytest

from src.parse_psp import (
    STATE_NAME_MAP,
    find_columns,
    find_header_row,
    parse_date_from_filename,
    parse_one_file,
    read_raw_table,
    validate_against_all_india,
)

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_date_from_filename():
    assert parse_date_from_filename(Path("01.06.25_NLDC_PSP.xls")) == pd.Timestamp("2025-06-01").date()


def test_parse_date_from_filename_rejects_bad_name():
    with pytest.raises(ValueError):
        parse_date_from_filename(Path("not_a_report.xls"))


def test_normal_file_parses_all_states_and_correct_values():
    """Fixture 1: normal, well-formed report."""
    state_df, region_df = parse_one_file(FIXTURES / "01.06.25_NLDC_PSP.xls")

    assert len(state_df) == 5
    assert set(state_df["state"]) == {"Andhra Pradesh", "Bihar", "Delhi", "Punjab", "Odisha"}

    odisha = state_df[state_df["state"] == "Odisha"].iloc[0]
    assert odisha["energy_met_mu"] == 90.0
    assert odisha["peak_met_mw"] == 4200
    # peak_demand_mw derived as peak_met_mw + peak_shortage_mw (4200 + 10)
    assert odisha["peak_demand_mw"] == 4210

    assert set(region_df["region"]) == {"NR", "All India"}


def test_shifted_header_row_still_found_by_search():
    """Fixture 2: same data as fixture 1, but the header is pushed down by
    3 extra banner/blank rows. WHY this test matters: if the parser ever
    regresses to a hardcoded row index, this is the test that catches it."""
    state_df, _ = parse_one_file(FIXTURES / "02.06.25_NLDC_PSP.xls")
    assert len(state_df) == 5
    assert set(state_df["state"]) == {"Andhra Pradesh", "Bihar", "Delhi", "Punjab", "Odisha"}


def test_state_name_variants_normalized():
    """Fixture 3: legacy spellings (Orissa, Pondicherry) must map through
    STATE_NAME_MAP to the canonical names used elsewhere in the schema."""
    state_df, _ = parse_one_file(FIXTURES / "03.06.25_NLDC_PSP.xls")
    names = set(state_df["state"])
    assert "Odisha" in names
    assert "Orissa" not in names
    assert "Puducherry" in names
    assert "Pondicherry" not in names


def test_state_name_map_has_expected_entries():
    assert STATE_NAME_MAP["Orissa"] == "Odisha"
    assert STATE_NAME_MAP["Pondicherry"] == "Puducherry"


def test_validation_flags_deviation_over_5_percent():
    """Fixture 4: state sum is deliberately ~44% off the All India row."""
    state_df, region_df = parse_one_file(FIXTURES / "04.06.25_NLDC_PSP.xls")
    warnings = validate_against_all_india(state_df, region_df)
    assert len(warnings) == 1
    assert "deviates" in warnings[0]


def test_validation_silent_when_within_5_percent():
    state_df, region_df = parse_one_file(FIXTURES / "01.06.25_NLDC_PSP.xls")
    assert validate_against_all_india(state_df, region_df) == []


def test_find_header_row_rejects_banner_substring_match():
    """WHY: a banner row like "...Power Supply Position of States..."
    contains "state" as a substring but must NOT be mistaken for the
    header row — find_header_row requires an exact cell match, not a
    substring match. Confirms fixture 2 (which has this exact kind of
    banner) is correctly skipped over."""
    raw = read_raw_table(FIXTURES / "02.06.25_NLDC_PSP.xls")
    header_idx = find_header_row(raw)
    header_text = raw.iloc[header_idx].astype(str).str.strip().str.lower()
    assert (header_text == "state").any()
    # the banner rows (0, 2) must NOT have been picked
    assert header_idx not in (0, 2)


def test_read_raw_table_uses_xlrd_result_when_read_excel_succeeds(monkeypatch):
    """Monkeypatch pandas.read_excel to return a real grid (simulating a
    genuine binary .xls opened successfully via the xlrd engine) and
    confirm read_raw_table returns it directly, WITHOUT falling back to
    read_html. This is the only reasonable way to test the xlrd-success
    branch without a true binary .xls fixture (see module docstring)."""
    import src.parse_psp as parse_psp_module

    fake_grid = pd.DataFrame([["State", "Energy Met(MU)"], ["Delhi", 81.0]])
    monkeypatch.setattr(parse_psp_module.pd, "read_excel", lambda *a, **kw: fake_grid)

    result = read_raw_table(Path("irrelevant_path.xls"))
    pd.testing.assert_frame_equal(result, fake_grid)


def test_find_columns_maps_all_expected_fields():
    raw = read_raw_table(FIXTURES / "01.06.25_NLDC_PSP.xls")
    header_idx = find_header_row(raw)
    columns = find_columns(raw.iloc[header_idx])
    assert set(columns.keys()) == {
        "state",
        "energy_met_mu",
        "energy_shortage_mu",
        "peak_met_mw",
        "peak_shortage_mw",
    }
