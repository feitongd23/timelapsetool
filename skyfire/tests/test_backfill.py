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


def test_parse_csv_rejects_missing_score_column(tmp_path):
    # 缺 score 列的短行应给友好的 ValueError,而非裸 TypeError
    p = tmp_path / "short.csv"
    p.write_text("date,city,event,score\n2026-05-12,beijing,sunset_glow\n", encoding="utf-8")
    with pytest.raises(ValueError, match="必须是数字"):
        parse_csv(p)


import io

import httpx
import numpy as np
from PIL import Image

from skyfire import store
from skyfire.backfill import backfill_row
from skyfire.config import load_cities
from skyfire.openmeteo import HISTORICAL_FORECAST_URL, MODELS
from pathlib import Path

CONFIG = Path(__file__).parent.parent / "config" / "cities.yaml"


def _hist_payload(day: str):
    times = [f"{day}T{h:02d}:00" for h in range(24)]
    n = len(times)
    hourly = {"time": times}
    for m in MODELS:
        for var, val in [("cloud_cover", 60), ("cloud_cover_low", 10),
                         ("cloud_cover_mid", 15), ("cloud_cover_high", 48),
                         ("relative_humidity_2m", 70), ("wind_speed_10m", 2.5),
                         ("temperature_2m", 30), ("dew_point_2m", 22),
                         ("precipitation", 0)]:
            hourly[f"{var}_{m}"] = [val] * n
    return {"hourly": hourly}


def _fake_transport(day: str, tile_status=200):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == httpx.URL(HISTORICAL_FORECAST_URL).host:
            return httpx.Response(200, json=_hist_payload(day))
        if request.url.path.endswith(".png"):
            if tile_status != 200:
                return httpx.Response(tile_status)
            img = Image.fromarray(np.full((550, 550), 90, dtype=np.uint8), mode="L")
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            return httpx.Response(200, content=buf.getvalue())
        return httpx.Response(404)

    return httpx.MockTransport(handler)


def test_backfill_row_creates_closed_case(tmp_path):
    conn = store.connect(tmp_path / "t.db")
    store.init_db(conn)
    client = httpx.Client(transport=_fake_transport("2026-05-12"))
    row = BackfillRow(date="2026-05-12", city="beijing", event="sunset_glow", score=9.0)
    city = load_cities(CONFIG)["beijing"]
    result = backfill_row(conn, client, row, city, frames_dir=tmp_path / "frames",
                          n_frames=2)
    assert result.case_id > 0
    got = conn.execute(
        "SELECT rule_score, actual_score, source FROM cases WHERE id=?",
        (result.case_id,)).fetchone()
    assert got[1] == 9.0 and got[2] == "cold_start"
    assert got[0] is not None            # 用历史快照重算了规则分
    snaps = store.get_snapshots(conn, result.case_id)
    assert {s["model"] for s in snaps} == set(MODELS)
    frames = store.get_frames(conn, result.case_id)
    assert len(frames) == 2
    assert (tmp_path / "frames").exists()


def test_backfill_row_survives_missing_satellite(tmp_path):
    conn = store.connect(tmp_path / "t.db")
    store.init_db(conn)
    client = httpx.Client(transport=_fake_transport("2026-05-12", tile_status=404))
    row = BackfillRow(date="2026-05-12", city="beijing", event="sunset_glow", score=7.0)
    city = load_cities(CONFIG)["beijing"]
    result = backfill_row(conn, client, row, city, frames_dir=tmp_path / "frames",
                          n_frames=2)
    # 卫星缺档不阻塞:案例照建,帧数为 0(spec 8 降级思路)
    assert result.case_id > 0
    assert store.get_frames(conn, result.case_id) == []
