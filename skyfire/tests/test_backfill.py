import pytest

from skyfire.backfill import BackfillRow, parse_csv


def test_parse_csv_valid(tmp_path):
    p = tmp_path / "cases.csv"
    p.write_text(
        "date,city,event,score\n"
        "2026-05-12,beijing,sunset_glow,9\n"
        "2026-05-20,beijing,sunrise_glow,2.5\n",
        encoding="utf-8",
    )
    rows = parse_csv(p)
    assert rows == [
        BackfillRow(date="2026-05-12", city="beijing", event="sunset_glow", score=9.0),
        BackfillRow(date="2026-05-20", city="beijing", event="sunrise_glow", score=2.5),
    ]


def test_parse_csv_rejects_bad_event(tmp_path):
    p = tmp_path / "bad.csv"
    p.write_text("date,city,event,score\n2026-05-12,beijing,rainbow,9\n", encoding="utf-8")
    with pytest.raises(ValueError, match="rainbow"):
        parse_csv(p)


def test_parse_csv_rejects_bad_date_and_score(tmp_path):
    p = tmp_path / "bad2.csv"
    p.write_text("date,city,event,score\n05/12/2026,beijing,sunset_glow,9\n", encoding="utf-8")
    with pytest.raises(ValueError, match="日期"):
        parse_csv(p)
    p.write_text("date,city,event,score\n2026-05-12,beijing,sunset_glow,11\n", encoding="utf-8")
    with pytest.raises(ValueError, match="0-10"):
        parse_csv(p)
