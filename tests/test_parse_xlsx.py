from pathlib import Path
import pytest
from src.parse_xlsx import parse, CANONICAL_SHEET

FIXTURE = Path(__file__).parent.parent / "fixtures" / "TS_Price_List_T2_April_2026.xlsx"


@pytest.mark.skipif(not FIXTURE.exists(), reason="fixture xlsx not present")
def test_canonical_sheet_readable():
    rows = parse(FIXTURE)
    # TODO: once parse() is implemented, assert len(rows) == 517
    assert isinstance(rows, list)


def test_canonical_sheet_name_constant():
    assert CANONICAL_SHEET == "All Part Numbers"
