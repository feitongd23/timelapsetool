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


def test_predict_no_llm_flag_skips_llm(tmp_path, monkeypatch):
    import skyfire.cli as cli
    monkeypatch.setattr(cli, "_make_client",
                        lambda: httpx.Client(transport=_fake_transport()))
    called = {"llm": False}

    def _spy(*a, **kw):
        called["llm"] = True
        return None

    monkeypatch.setattr(cli, "_run_llm", _spy)
    db = tmp_path / "sky.db"
    result = runner.invoke(app, ["predict", "--city", "beijing", "--event", "sunset_glow",
                                 "--date", "2026-07-03", "--db", str(db), "--no-llm"])
    assert result.exit_code == 0, result.output
    assert called["llm"] is False
    # 默认(不带 --no-llm)会调用
    result2 = runner.invoke(app, ["predict", "--city", "beijing", "--event", "sunset_glow",
                                  "--date", "2026-07-03", "--db", str(db)])
    assert result2.exit_code == 0, result2.output
    assert called["llm"] is True
