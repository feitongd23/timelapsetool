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
    from skyfire.openmeteo import HISTORICAL_FORECAST_URL, MODELS as _MODELS

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == httpx.URL(HISTORICAL_FORECAST_URL).host:
            times = [f"2026-05-12T{h:02d}:00" for h in range(24)]
            if "," in str(request.url.params.get("latitude", "")):
                # 通道剖面:多地点、单模式、无后缀列
                count = str(request.url.params["latitude"]).count(",") + 1
                loc = {"hourly": {"time": times, "cloud_cover": [30] * 24,
                                  "cloud_cover_low": [10] * 24}}
                return httpx.Response(200, json=[loc] * count)
            hourly = {"time": times}
            for m in _MODELS:
                for var, val in [("cloud_cover", 60), ("cloud_cover_low", 10),
                                 ("cloud_cover_mid", 15), ("cloud_cover_high", 48),
                                 ("relative_humidity_2m", 70), ("wind_speed_10m", 2.5),
                                 ("temperature_2m", 30), ("dew_point_2m", 22),
                                 ("precipitation", 0)]:
                    hourly[f"{var}_{m}"] = [val] * 24
            return httpx.Response(200, json={"hourly": hourly})
        return httpx.Response(404)  # AOD/AWS HSD 段等:缺档尽力跳过

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
    """卫星段全缺(归档未落)→ nowcast 退回纯规则分,不写融合分(spec 8)。"""
    from datetime import datetime, timedelta, timezone
    import skyfire.cli as cli
    from skyfire import store
    from skyfire.suntimes import SunWindow

    # 固定一个 2 小时后的窗口,避开真实时钟导致的"窗口已过"分支
    peak = datetime.now(timezone.utc).astimezone() + timedelta(hours=2)
    monkeypatch.setattr(cli, "sun_window", lambda *a, **k: SunWindow(
        event="sunset_glow", peak=peak, window_start=peak, window_end=peak,
        azimuth_deg=300.0))

    monkeypatch.setattr(cli, "_make_client", lambda: httpx.Client())
    monkeypatch.setattr(cli, "latest_slot",
                        lambda client, now: datetime(2026, 7, 4, 10, 0, tzinfo=timezone.utc))
    monkeypatch.setattr(cli, "download_segments", lambda *a, **k: [])  # 段全缺

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


def test_notify_pushes_and_marks(tmp_path, monkeypatch):
    import skyfire.cli as cli
    from skyfire.engine import PredictionResult
    from datetime import date, datetime
    from skyfire import store

    pushed = {}

    def _fake_compute(conn, client, c, city, event, day, run_llm=True):
        return PredictionResult(city_name="北京", event=event, day=day, index=7.5,
                                confidence="high", spread=0.9,
                                per_model={"gfs_seamless": 7.5}, blocked_points=1,
                                channel_factor=0.8, aod=0.3, channel_empty=False,
                                peak=datetime(2026, 7, 4, 19, 46), azimuth=301.0, llm=None)

    def _fake_push(title, body, cfg, client=None):
        pushed["title"] = title
        pushed["body"] = body
        return True

    monkeypatch.setattr(cli, "_make_client", lambda: None)
    monkeypatch.setattr(cli, "compute_prediction", _fake_compute)
    monkeypatch.setattr(cli, "push", _fake_push)

    ncfg = tmp_path / "notify.yaml"
    ncfg.write_text("provider: bark\nkey: K\n", encoding="utf-8")
    db = tmp_path / "sky.db"
    result = runner.invoke(app, ["notify", "--city", "beijing", "--event", "sunset_glow",
                                 "--db", str(db), "--notify-config", str(ncfg)])
    assert result.exit_code == 0, result.output
    assert "7.5" in pushed["title"] and "晚霞" in pushed["title"]
    conn = store.connect(db)
    today = str(date.today())
    assert store.was_pushed(conn, today, "beijing", "sunset_glow") is True


def test_notify_no_config_reports_and_exits(tmp_path, monkeypatch):
    import skyfire.cli as cli
    monkeypatch.setattr(cli, "_make_client", lambda: None)
    result = runner.invoke(app, ["notify", "--city", "beijing", "--event", "sunset_glow",
                                 "--db", str(tmp_path / "d.db"),
                                 "--notify-config", str(tmp_path / "nope.yaml")])
    assert result.exit_code != 0
    assert "未配置" in result.output


def test_tick_no_config_silent_exit(tmp_path, monkeypatch):
    import skyfire.cli as cli
    monkeypatch.setattr(cli, "load_notify_config", lambda p: None)
    db = tmp_path / "sky.db"
    result = runner.invoke(app, ["tick", "--db", str(db),
                                 "--notify-config", str(tmp_path / "nope.yaml")])
    assert result.exit_code == 0
    assert result.output == ""


def test_tick_runs_due_checkpoint_and_pushes(tmp_path, monkeypatch):
    import skyfire.cli as cli
    pushed = []
    monkeypatch.setattr(cli, "load_notify_config",
                        lambda p: {"provider": "bark", "key": "k"})
    monkeypatch.setattr(cli, "push", lambda t, b, cfg: pushed.append(t) or True)
    monkeypatch.setattr(cli, "due_checkpoint", lambda now, peak, ev:
                        "c1" if ev == "sunset_glow" else None)
    rec = {"probability_pct": 65.0, "quality_pct": 50.0, "confidence": "high",
           "llm_status": "pending", "reasoning": None, "risks": None,
           "date": "2026-07-06", "event": "sunset_glow", "checkpoint": "c1",
           "rule_score": 5.0, "sat_cloud_pct": None, "trend": None,
           "city_name": "北京"}
    calls = []
    monkeypatch.setattr(cli, "run_checkpoint",
                        lambda *a, **k: calls.append((a, k)) or rec)
    db = tmp_path / "t.db"
    result = runner.invoke(app, ["tick", "--db", str(db)])
    assert result.exit_code == 0
    assert len(pushed) == 1 and "概率65%" in pushed[0]


def test_tick_skips_already_run_checkpoint(tmp_path, monkeypatch):
    import skyfire.cli as cli
    from skyfire import store
    monkeypatch.setattr(cli, "load_notify_config",
                        lambda p: {"provider": "bark", "key": "k"})
    monkeypatch.setattr(cli, "push", lambda t, b, cfg: True)
    monkeypatch.setattr(cli, "due_checkpoint", lambda now, peak, ev:
                        "c1" if ev == "sunset_glow" else None)
    called = []
    monkeypatch.setattr(cli, "run_checkpoint", lambda *a, **k: called.append(1))
    db = tmp_path / "t.db"
    conn = store.connect(db); store.init_db(conn)
    from datetime import date as _d
    today = str(_d.today())
    store.add_prediction(conn, today, "beijing", "sunset_glow", "c1",
                         probability_pct=50, quality_pct=50, confidence="low",
                         rule_score=3.0, sat_cloud_pct=None, trend=None,
                         llm_status="pending", reasoning=None, risks=None)
    result = runner.invoke(app, ["tick", "--db", str(db)])
    assert result.exit_code == 0 and called == []   # 幂等:已跑过不重跑


def test_feedback_closes_case_saves_photo_and_triggers_retro(tmp_path, monkeypatch):
    import skyfire.cli as cli
    from skyfire import store
    db = tmp_path / "t.db"
    conn = store.connect(db); store.init_db(conn)
    store.upsert_case(conn, "2026-07-06", "beijing", "sunset_glow",
                      rule_score=5.0, confidence="high", source="auto")
    photo = tmp_path / "shot.jpg"; photo.write_bytes(b"jpg")
    monkeypatch.setattr(cli, "explain", lambda card, paths: "复盘:预测偏低,通道其实开")
    monkeypatch.setattr(cli, "_ensure_case_frames", lambda *a, **k: 0)
    result = runner.invoke(cli.app, [
        "feedback", "--date", "2026-07-06", "--score", "9",
        "--photo", str(photo), "--db", str(db),
        "--photos-dir", str(tmp_path / "photos")])
    assert result.exit_code == 0
    case = store.case_by_key(conn, "2026-07-06", "beijing", "sunset_glow")
    assert case["actual_score"] == 9.0
    notes = store.get_case_notes(conn, case["id"])
    assert notes and notes[-1]["author"] == "llm"
    saved = list((tmp_path / "photos").glob("*"))
    assert len(saved) == 1
    row = conn.execute("SELECT path FROM photos WHERE case_id=?",
                       (case["id"],)).fetchone()
    assert row and str(tmp_path / "photos") in row[0]


def test_feedback_no_llm_leaves_pending(tmp_path, monkeypatch):
    import skyfire.cli as cli
    from skyfire import store
    db = tmp_path / "t.db"
    conn = store.connect(db); store.init_db(conn)
    monkeypatch.setattr(cli, "explain", lambda card, paths: None)   # 无 key
    monkeypatch.setattr(cli, "_ensure_case_frames", lambda *a, **k: 0)
    result = runner.invoke(cli.app, [
        "feedback", "--date", "2026-07-06", "--wrong", "--db", str(db)])
    assert result.exit_code == 0
    assert "待补" in result.output
    case = store.case_by_key(conn, "2026-07-06", "beijing", "sunset_glow")
    assert case is not None                     # 案例被创建
    assert store.get_case_notes(conn, case["id"]) == []   # 笔记 pending(无)
