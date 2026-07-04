import httpx
from typer.testing import CliRunner

from skyfire.cli import app
from skyfire.openmeteo import AIR_QUALITY_URL, MODELS

runner = CliRunner()


def _fake_transport():
    """按 URL 分发假响应;时间轴造 48h 覆盖任意窗口小时。"""
    def handler(request: httpx.Request) -> httpx.Response:
        times = [f"2026-07-03T{h:02d}:00" for h in range(24)] + \
                [f"2026-07-04T{h:02d}:00" for h in range(24)]
        n = len(times)
        if request.url.host == httpx.URL(AIR_QUALITY_URL).host:
            return httpx.Response(200, json={"hourly": {
                "time": times, "aerosol_optical_depth": [0.2] * n}})
        if "," in str(request.url.params.get("latitude", "")):  # 通道多点
            count = str(request.url.params["latitude"]).count(",") + 1
            loc = {"hourly": {"time": times, "cloud_cover": [15] * n,
                              "cloud_cover_low": [5] * n}}
            return httpx.Response(200, json=[loc] * count)
        hourly = {"time": times}
        for m in MODELS:  # 本地多模式
            for var, val in [("cloud_cover", 60), ("cloud_cover_low", 10),
                             ("cloud_cover_mid", 15), ("cloud_cover_high", 50),
                             ("relative_humidity_2m", 70), ("wind_speed_10m", 2.5),
                             ("temperature_2m", 30), ("dew_point_2m", 22),
                             ("precipitation", 0)]:
                hourly[f"{var}_{m}"] = [val] * n
        return httpx.Response(200, json={"hourly": hourly})

    return httpx.MockTransport(handler)


def test_predict_prints_card_and_saves_case(tmp_path, monkeypatch):
    import skyfire.cli as cli
    monkeypatch.setattr(cli, "_make_client", lambda: httpx.Client(transport=_fake_transport()))
    db = tmp_path / "sky.db"
    result = runner.invoke(app, ["predict", "--city", "beijing", "--event", "sunset_glow",
                                 "--date", "2026-07-03", "--db", str(db)])
    assert result.exit_code == 0, result.output
    assert "火烧云指数" in result.output
    assert "置信度" in result.output
    # 案例落库
    from skyfire import store
    conn = store.connect(db)
    row = conn.execute("SELECT city, event, rule_score FROM cases").fetchone()
    assert row[0] == "beijing" and row[1] == "sunset_glow" and row[2] is not None


def test_backtest_needs_scored_cases(tmp_path):
    db = tmp_path / "sky.db"
    result = runner.invoke(app, ["backtest", "--city", "beijing", "--db", str(db)])
    assert result.exit_code != 0
    assert "案例不足" in result.output


def test_predict_rejects_bad_date(tmp_path):
    db = tmp_path / "sky.db"
    result = runner.invoke(app, ["predict", "--date", "07/03/2026", "--db", str(db)])
    assert result.exit_code != 0
    assert "YYYY-MM-DD" in result.output


def test_predict_rejects_unknown_city(tmp_path):
    db = tmp_path / "sky.db"
    result = runner.invoke(app, ["predict", "--city", "atlantis", "--db", str(db)])
    assert result.exit_code != 0
    assert "未知城市" in result.output


def test_backfill_command(tmp_path, monkeypatch):
    import io
    import numpy as np
    from PIL import Image
    from skyfire.openmeteo import HISTORICAL_FORECAST_URL, MODELS as _MODELS

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == httpx.URL(HISTORICAL_FORECAST_URL).host:
            times = [f"2026-05-12T{h:02d}:00" for h in range(24)]
            hourly = {"time": times}
            for m in _MODELS:
                for var, val in [("cloud_cover", 60), ("cloud_cover_low", 10),
                                 ("cloud_cover_mid", 15), ("cloud_cover_high", 48),
                                 ("relative_humidity_2m", 70), ("wind_speed_10m", 2.5),
                                 ("temperature_2m", 30), ("dew_point_2m", 22),
                                 ("precipitation", 0)]:
                    hourly[f"{var}_{m}"] = [val] * 24
            return httpx.Response(200, json={"hourly": hourly})
        if request.url.path.endswith(".png"):
            img = Image.fromarray(np.full((550, 550), 90, dtype=np.uint8), mode="L")
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            return httpx.Response(200, content=buf.getvalue())
        return httpx.Response(404)

    import skyfire.cli as cli
    monkeypatch.setattr(cli, "_make_client",
                        lambda: httpx.Client(transport=httpx.MockTransport(handler)))
    csv_path = tmp_path / "cases.csv"
    csv_path.write_text("date,city,event,score\n2026-05-12,beijing,sunset_glow,9\n",
                        encoding="utf-8")
    db = tmp_path / "sky.db"
    result = runner.invoke(app, ["backfill", "--csv", str(csv_path), "--db", str(db),
                                 "--frames-dir", str(tmp_path / "frames")])
    assert result.exit_code == 0, result.output
    assert "1 条" in result.output
    from skyfire import store
    conn = store.connect(db)
    row = conn.execute("SELECT source, actual_score FROM cases").fetchone()
    assert row == ("cold_start", 9.0)


def test_backfill_rejects_bad_csv(tmp_path):
    csv_path = tmp_path / "bad.csv"
    csv_path.write_text("date,city,event,score\n2026-05-12,beijing,rainbow,9\n",
                        encoding="utf-8")
    result = runner.invoke(app, ["backfill", "--csv", str(csv_path),
                                 "--db", str(tmp_path / "d.db"),
                                 "--frames-dir", str(tmp_path / "f")])
    assert result.exit_code != 0
    assert "rainbow" in result.output


def test_predict_no_llm_flag_controls_run_llm(tmp_path, monkeypatch):
    import skyfire.cli as cli
    from skyfire.engine import PredictionResult
    from datetime import date, datetime
    seen = {}

    def _fake_compute(conn, client, c, city, event, day, run_llm=True):
        seen["run_llm"] = run_llm
        return PredictionResult(city_name="北京", event=event, day=day, index=5.0,
                                confidence="high", spread=0.0,
                                per_model={"gfs_seamless": 5.0}, blocked_points=0,
                                channel_factor=1.0, aod=0.2, channel_empty=False,
                                peak=datetime(2026, 7, 3, 19, 46), azimuth=300.0, llm=None)

    monkeypatch.setattr(cli, "_make_client",
                        lambda: httpx.Client(transport=_fake_transport()))
    monkeypatch.setattr(cli, "compute_prediction", _fake_compute)
    db = tmp_path / "sky.db"
    r1 = runner.invoke(app, ["predict", "--city", "beijing", "--event", "sunset_glow",
                             "--date", "2026-07-03", "--db", str(db), "--no-llm"])
    assert r1.exit_code == 0, r1.output
    assert seen["run_llm"] is False
    r2 = runner.invoke(app, ["predict", "--city", "beijing", "--event", "sunset_glow",
                             "--date", "2026-07-03", "--db", str(db)])
    assert r2.exit_code == 0, r2.output
    assert seen["run_llm"] is True


def test_nowcast_degrades_on_missing_satellite(tmp_path, monkeypatch):
    """瓦片全缺(全 404)→ nowcast 退回纯规则分,不写融合分(spec 8)。"""
    from datetime import datetime, timedelta, timezone
    import skyfire.cli as cli
    from skyfire import store
    from skyfire.suntimes import SunWindow

    # 固定一个 2 小时后的窗口,避开真实时钟导致的"窗口已过"分支
    peak = datetime.now(timezone.utc).astimezone() + timedelta(hours=2)
    monkeypatch.setattr(cli, "sun_window", lambda *a, **k: SunWindow(
        event="sunset_glow", peak=peak, window_start=peak, window_end=peak,
        azimuth_deg=300.0))

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("latest.json"):
            ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            return httpx.Response(200, json={"date": ts, "file": "x.png"})
        return httpx.Response(404)  # 所有瓦片缺失

    monkeypatch.setattr(cli, "_make_client",
                        lambda: httpx.Client(transport=httpx.MockTransport(handler)))

    db = tmp_path / "sky.db"
    conn = cli._open_db(db)
    today = str(cli.date_type.today())
    store.upsert_case(conn, today, "beijing", "sunset_glow",
                      rule_score=8.0, confidence="high", source="auto")

    result = runner.invoke(app, ["nowcast", "--city", "beijing", "--event",
                                 "sunset_glow", "--db", str(db),
                                 "--frames-dir", str(tmp_path / "frames")])
    assert result.exit_code == 0, result.output
    assert "卫星帧全缺" in result.output
    # 规则分未被融合分覆盖(仍是 8.0,置信度未变 nowcast)
    row = conn.execute(
        "SELECT rule_score, confidence FROM cases WHERE date=? AND city='beijing' "
        "AND event='sunset_glow'", (today,)).fetchone()
    assert row == (8.0, "high")
