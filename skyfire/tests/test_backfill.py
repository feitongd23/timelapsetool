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


from datetime import datetime, timezone
from pathlib import Path

import httpx

import skyfire.backfill as backfill_mod
from skyfire import store
from skyfire.backfill import BackfillRow, backfill_row
from skyfire.config import City
from skyfire.models import ChannelPoint


def _forecast_payload():
    # fetch_point_forecast_range 默认请求 MODELS(4 模式),_parse_models 在
    # len(models)>1 时按 "{var}_{model}" 取列,故各模式列需分别给出。
    from skyfire.openmeteo import MODELS
    # cloud_high=50, cloud_mid=20 → canvas_score=60 落在 40-70 有效区间(canvas=10.0),
    # 不再被 >70 衰减支归零;这样规则分由 channel_factor 驱动,通道门槛断言才有意义。
    hourly = {"time": ["2026-05-06T19:00"]}
    for m in MODELS:
        for var, val in [("cloud_cover", 80), ("cloud_cover_low", 0),
                         ("cloud_cover_mid", 20), ("cloud_cover_high", 50),
                         ("relative_humidity_2m", 50), ("wind_speed_10m", 3),
                         ("temperature_2m", 20), ("dew_point_2m", 10),
                         ("precipitation", 0)]:
            hourly[f"{var}_{m}"] = [val]
    return {"hourly": hourly}


def test_backfill_row_feeds_channel_aod_and_aws_frames(tmp_path, monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_forecast_payload())
    client = httpx.Client(transport=httpx.MockTransport(handler))

    monkeypatch.setattr(backfill_mod, "fetch_channel_profile_range",
                        lambda *a, **k: [ChannelPoint(dist_km=200, cloud_low=90,
                                                      cloud_total=95)])
    monkeypatch.setattr(backfill_mod, "fetch_aod_range", lambda *a, **k: 0.5)
    fake_ts = datetime(2026, 5, 6, 10, 40, tzinfo=timezone.utc)

    def fake_frames(client, peak_utc, frames_dir, *, prefix, **kw):
        p = Path(frames_dir) / f"{prefix}_1040_ir.png"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"png")
        return [(fake_ts, "ir", p)]

    monkeypatch.setattr(backfill_mod, "fetch_case_frames", fake_frames)

    conn = store.connect(":memory:")
    store.init_db(conn)
    row = BackfillRow(date="2026-05-06", city="beijing", event="sunset_glow", score=10)
    city = City(key="beijing", name="北京", lat=39.9, lon=116.4,
                timezone="Asia/Shanghai")
    r = backfill_row(conn, client, row, city, frames_dir=tmp_path)

    assert r.n_frames == 1
    snaps = store.get_snapshots(conn, r.case_id)
    payload = snaps[0]["payload"]
    assert payload["aod"] == 0.5
    assert payload["channel"] == [{"km": 200, "low": 90, "total": 95}]
    frames = store.get_frames(conn, r.case_id)
    assert frames[0]["channel"] == "ir"
    # 通道全堵(low=90>60)→ channel_factor 0.1 → 规则分被压到 ~0.8
    # (canvas=10.0 * 0.1 * 1.0 * aerosol(0.5→0.85))。与全通对照见下一条测试。
    case = conn.execute("SELECT rule_score FROM cases WHERE id=?",
                        (r.case_id,)).fetchone()
    assert case[0] is not None and case[0] < 2.0


def test_backfill_row_open_channel_scores_high(tmp_path, monkeypatch):
    """对照:同一画布,通道全通(low/total 远低于阈值)→ 规则分高。

    与全堵那条形成对比,证明分差来自 G_channel 门槛而非画布归零。
    """
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_forecast_payload())
    client = httpx.Client(transport=httpx.MockTransport(handler))

    monkeypatch.setattr(backfill_mod, "fetch_channel_profile_range",
                        lambda *a, **k: [ChannelPoint(dist_km=200, cloud_low=5,
                                                      cloud_total=10)])
    monkeypatch.setattr(backfill_mod, "fetch_aod_range", lambda *a, **k: 0.5)
    monkeypatch.setattr(backfill_mod, "fetch_case_frames", lambda *a, **k: [])

    conn = store.connect(":memory:")
    store.init_db(conn)
    row = BackfillRow(date="2026-05-06", city="beijing", event="sunset_glow", score=10)
    city = City(key="beijing", name="北京", lat=39.9, lon=116.4,
                timezone="Asia/Shanghai")
    r = backfill_row(conn, client, row, city, frames_dir=tmp_path)

    # 通道全通 → channel_factor 1.0 → 规则分 ~8.5(canvas 10.0 * 1.0 * aerosol 0.85)
    case = conn.execute("SELECT rule_score FROM cases WHERE id=?",
                        (r.case_id,)).fetchone()
    assert case[0] is not None and case[0] > 5.0


def test_backfill_row_rerun_does_not_duplicate_frames(tmp_path, monkeypatch):
    def handler(request):
        return httpx.Response(200, json=_forecast_payload())
    client = httpx.Client(transport=httpx.MockTransport(handler))
    monkeypatch.setattr(backfill_mod, "fetch_channel_profile_range", lambda *a, **k: [])
    monkeypatch.setattr(backfill_mod, "fetch_aod_range", lambda *a, **k: None)
    fake_ts = datetime(2026, 5, 6, 10, 40, tzinfo=timezone.utc)

    def fake_frames(client, peak_utc, frames_dir, *, prefix, **kw):
        p = Path(frames_dir) / f"{prefix}_1040_ir.png"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"png")
        return [(fake_ts, "ir", p)]

    monkeypatch.setattr(backfill_mod, "fetch_case_frames", fake_frames)
    conn = store.connect(":memory:")
    store.init_db(conn)
    row = BackfillRow(date="2026-05-06", city="beijing", event="sunset_glow", score=10)
    city = City(key="beijing", name="北京", lat=39.9, lon=116.4,
                timezone="Asia/Shanghai")
    r1 = backfill_row(conn, client, row, city, frames_dir=tmp_path)
    r2 = backfill_row(conn, client, row, city, frames_dir=tmp_path)
    assert len(store.get_frames(conn, r2.case_id)) == 1   # 幂等,不重复
