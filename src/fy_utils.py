"""Indian financial-year folder logic for Grid-India report URLs."""

from datetime import date


def fy_folder(d: date) -> str:
    """Return the Indian financial-year folder for a date, e.g. "2024-2025".

    WHY: Grid-India stores reports in folders keyed by financial year (1 April
    to 31 March), not calendar year, so every downstream URL builder needs this.
    """
    start_year = d.year if d.month >= 4 else d.year - 1
    return f"{start_year}-{start_year + 1}"
