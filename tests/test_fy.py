"""Tests for fy_utils.fy_folder covering FY-boundary edge cases."""

from datetime import date

from src.fy_utils import fy_folder


def test_april_1_starts_new_fy():
    assert fy_folder(date(2024, 4, 1)) == "2024-2025"


def test_march_31_ends_previous_fy():
    assert fy_folder(date(2025, 3, 31)) == "2024-2025"


def test_mid_year_date():
    assert fy_folder(date(2024, 9, 15)) == "2024-2025"


def test_december_31_still_in_same_fy():
    assert fy_folder(date(2024, 12, 31)) == "2024-2025"


def test_january_1_still_in_previous_calendar_years_fy():
    assert fy_folder(date(2025, 1, 1)) == "2024-2025"
