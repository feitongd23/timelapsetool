from datetime import date as date_type

import httpx

import skyfire.engine as engine_mod
from skyfire import store
from skyfire.config import City, load_cities
from skyfire.engine import PredictionResult, compute_prediction, run_checkpoint
from skyfire.openmeteo import AIR_QUALITY_URL, MODELS
from pathlib import Path

CONFIG = Path(__file__).parent.parent / "config" / "cities.yaml"


def _fake_transport():
    def handler(request: httpx.Request) -> httpx.Response:
        times = [f"2026-07-03T{h:02d}:00" for h in range(24)] + \
                [f"2026-07-04T{h:02d}:00" for h in range(24)]
        n = len(times)
        if request.url.host == httpx.URL(AIR_QUALITY_URL).host:
            return httpx.Response(200, json={"hourly": {
                "time": times, "aerosol_optical_depth": [0.2] * n}})
        if "," in str(request.url.params.get("latitude", "")):
            count = str(request.url.params["latitude"]).count(",") + 1
            loc = {"hourly": {"time": times, "cloud_cover": [15] * n,
                              "cloud_cover_low": [5] * n}}
            return httpx.Response(200, json=[loc] * count)
        hourly = {"time": times}
        for m in MODELS:
            for var, val in [("cloud_cover", 60), ("cloud_cover_low", 10),
                             ("cloud_cover_mid", 15), ("cloud_cover_high", 50),
                             ("relative_humidity_2m", 70), ("wind_speed_10m", 2.5),
                             ("temperature_2m", 30), ("dew_point_2m", 22),
                             ("precipitation", 0)]:
                hourly[f"{var}_{m}"] = [val] * n
        return httpx.Response(200, json={"hourly": hourly})
    return httpx.MockTransport(handler)


def test_compute_prediction_returns_result_and_persists(tmp_path):
    from datetime import date
    conn = store.connect(tmp_path / "t.db")
    store.init_db(conn)
    city = load_cities(CONFIG)["beijing"]
    client = httpx.Client(transport=_fake_transport())
    r = compute_prediction(conn, client, city, "beijing", "sunset_glow",
                           date(2026, 7, 3), run_llm=False)
    assert isinstance(r, PredictionResult)
    assert r.city_name == "北京" and r.event == "sunset_glow"
    assert 0 <= r.index <= 10
    assert r.confidence in ("high", "medium", "low", "degraded")
    assert set(r.per_model) == set(MODELS)
    assert r.llm is None  # run_llm=False
    case = conn.execute("SELECT rule_score FROM cases WHERE city='beijing'").fetchone()
    assert case[0] == r.index
    snaps = store.get_snapshots(conn, conn.execute("SELECT id FROM cases").fetchone()[0])
    assert {s["model"] for s in snaps} == set(MODELS)


def test_compute_prediction_raises_on_all_models_missing(tmp_path):
    from datetime import date
    import pytest
    conn = store.connect(tmp_path / "t.db")
    store.init_db(conn)
    city = load_cities(CONFIG)["beijing"]

    def empty(request):
        times = ["2026-07-03T19:00"]
        if request.url.host == httpx.URL(AIR_QUALITY_URL).host:
            return httpx.Response(200, json={"hourly": {"time": times,
                                                        "aerosol_optical_depth": [0.2]}})
        if "," in str(request.url.params.get("latitude", "")):
            return httpx.Response(200, json=[{"hourly": {"time": times,
                "cloud_cover": [15], "cloud_cover_low": [5]}}] * 8)
        return httpx.Response(200, json={"hourly": {"time": times}})

    client = httpx.Client(transport=httpx.MockTransport(empty))
    with pytest.raises(ValueError):
        compute_prediction(conn, client, city, "beijing", "sunset_glow",
                           date(2026, 7, 3), run_llm=False)


def test_compute_prediction_collects_per_model_raw(tmp_path):
    from datetime import date
    conn = store.connect(tmp_path / "t.db")
    store.init_db(conn)
    city = load_cities(CONFIG)["beijing"]
    client = httpx.Client(transport=_fake_transport())
    r = compute_prediction(conn, client, city, "beijing", "sunset_glow",
                           date(2026, 7, 3), run_llm=False)
    # fake transport:每模式 high=50 mid=15 low=10 precip=0
    assert set(r.per_model_raw) == set(MODELS)
    assert r.per_model_raw["gfs_seamless"] == {
        "cloud_high": 50, "cloud_mid": 15, "cloud_low": 10, "precipitation": 0}


def _fake_pr(index=5.0, confidence="high"):
    from datetime import datetime, timezone
    return PredictionResult(
        city_name="北京", event="sunset_glow", day=date_type(2026, 7, 6),
        index=index, confidence=confidence, spread=1.0,
        per_model={"gfs_seamless": index}, blocked_points=0, channel_factor=1.0,
        aod=0.3, channel_empty=False,
        peak=datetime(2026, 7, 6, 19, 40, tzinfo=timezone.utc), azimuth=295.0,
        per_model_raw={"gfs_seamless": {"cloud_high": 80, "cloud_mid": 20,
                                        "cloud_low": 10, "precipitation": 0.0}},
        llm=None)


def _fake_meta(overcast=False):
    return {"overcast": overcast, "max_bt": 296.0, "raw_pct": 48.0,
            "upstream_overcast": False, "visible_attached": False,
            "frame_time": "2026-07-06T10:00+00:00"}


def _setup(monkeypatch, llm_result):
    monkeypatch.setattr(engine_mod, "compute_prediction",
                        lambda *a, **k: _fake_pr())
    monkeypatch.setattr(engine_mod, "observe_burn_clouds",
                        lambda *a, **k: (48.0, 52.0, "now=48%→burn=52%", [],
                                         _fake_meta()))
    monkeypatch.setattr(engine_mod, "predict_pct", lambda *a, **k: llm_result)
    conn = store.connect(":memory:")
    store.init_db(conn)
    city = City(key="beijing", name="北京", lat=39.9, lon=116.4,
                timezone="Asia/Shanghai")
    return conn, city


def test_run_checkpoint_llm_done(monkeypatch):
    llm = {"probability_pct": 72.0, "quality_pct": 64.0, "reasoning": "通",
           "risks": "低云", "confidence": "high"}
    conn, city = _setup(monkeypatch, llm)
    rec = run_checkpoint(conn, object(), city, "beijing", "sunset_glow",
                         date_type(2026, 7, 6), "c2")
    assert rec["probability_pct"] == 72 and rec["llm_status"] == "done"
    assert store.has_checkpoint(conn, "2026-07-06", "beijing", "sunset_glow", "c2")


def test_run_checkpoint_no_llm_pending(monkeypatch):
    conn, city = _setup(monkeypatch, None)      # LLM 失败/无 key
    rec = run_checkpoint(conn, object(), city, "beijing", "sunset_glow",
                         date_type(2026, 7, 6), "c1")
    assert rec["llm_status"] == "pending"
    # C1 远期首报:实况参考权重封顶 0.3。纯预报 (50,50) 与实况耦合
    # (63,55)(甜区门控乘法后)按 0.3 混合
    assert rec["probability_pct"] == 54 and rec["quality_pct"] == 52
    assert rec["per_model_pct"] == {"gfs_seamless": (54, 52)}


def test_run_checkpoint_c3_uses_satellite_extrapolation(monkeypatch):
    conn, city = _setup(monkeypatch, None)
    rec = run_checkpoint(conn, object(), city, "beijing", "sunset_glow",
                         date_type(2026, 7, 6), "c3")
    # C3 临近(峰值已过=按≤1.5h档):实况权重 0.6,预测与实况强制并用。
    # (50,50)×0.4 + (63,55)×0.6 = (58,53)
    assert rec["probability_pct"] == 58 and rec["quality_pct"] == 53
    assert rec["per_model_pct"] == {"gfs_seamless": (58, 53)}


def test_run_checkpoint_gated_skips_small_delta(monkeypatch):
    conn, city = _setup(monkeypatch, None)
    run_checkpoint(conn, object(), city, "beijing", "sunset_glow",
                   date_type(2026, 7, 6), "c2")            # 落一版 prob=75(含云量修正)
    rec = run_checkpoint(conn, object(), city, "beijing", "sunset_glow",
                         date_type(2026, 7, 6), "gated", gate=True)
    assert rec is None                                      # Δ=0 < 15pp,不落库
    assert len(store.predictions_for(conn, "2026-07-06", "beijing",
                                     "sunset_glow")) == 1


def test_run_checkpoint_outlook_baseline_ignores_satellite(monkeypatch):
    conn, city = _setup(monkeypatch, None)
    rec = run_checkpoint(conn, object(), city, "beijing", "sunset_glow",
                         date_type(2026, 7, 6), "outlook")
    # 同 C1:远期参考权重 0.3 → 混合 (54,52)
    assert rec["probability_pct"] == 54 and rec["quality_pct"] == 52
    assert rec["checkpoint"] == "outlook"
    assert store.has_checkpoint(conn, "2026-07-06", "beijing", "sunset_glow",
                                "outlook")


def test_run_checkpoint_payload_rec_and_db_carry_raw(monkeypatch):
    captured = {}

    def fake_predict(payload, similar, frames, model=None):
        captured.update(payload)
        return None

    monkeypatch.setattr(engine_mod, "compute_prediction",
                        lambda *a, **k: _fake_pr())
    monkeypatch.setattr(engine_mod, "observe_burn_clouds",
                        lambda *a, **k: (48.0, 52.0, "now=48%→burn=52%", [],
                                         _fake_meta()))
    monkeypatch.setattr(engine_mod, "predict_pct", fake_predict)
    conn = store.connect(":memory:")
    store.init_db(conn)
    city = City(key="beijing", name="北京", lat=39.9, lon=116.4,
                timezone="Asia/Shanghai")
    rec = run_checkpoint(conn, object(), city, "beijing", "sunset_glow",
                         date_type(2026, 7, 6), "c2")
    # LLM payload 看得到各模式原始数字
    assert captured["per_model_raw"]["gfs_seamless"]["cloud_high"] == 80
    # rec 携带原始数字(推送格式化用)
    assert rec["per_model_raw"]["gfs_seamless"]["precipitation"] == 0.0
    # per_model_json 落库:概率/质量 + 原始数字合体
    import json
    row = store.latest_prediction(conn, "2026-07-06", "beijing", "sunset_glow")
    pmj = json.loads(row["per_model_json"])
    # c2(峰值已过=≤1.5h档)实况权重 0.6 → prob 混合为 58
    assert pmj["gfs_seamless"]["prob"] == 58 and pmj["gfs_seamless"]["cloud_high"] == 80


def test_run_checkpoint_injects_seq_and_prev(monkeypatch):
    llm = {"probability_pct": 72.0, "quality_pct": 64.0, "reasoning": "通",
           "risks": "低云", "confidence": "high"}
    conn, city = _setup(monkeypatch, llm)
    rec1 = run_checkpoint(conn, object(), city, "beijing", "sunset_glow",
                          date_type(2026, 7, 6), "c1")
    assert rec1["seq"] == 1 and rec1["prev"] is None
    assert isinstance(rec1["minutes_to_peak"], int)
    rec2 = run_checkpoint(conn, object(), city, "beijing", "sunset_glow",
                          date_type(2026, 7, 6), "c2")
    assert rec2["seq"] == 2
    assert rec2["prev"]["probability_pct"] == 72.0
    assert rec2["prev"]["quality_pct"] == 64.0
    assert rec2["prev"]["checkpoint"] == "c1"
    # created_at 由 sqlite datetime('now') 生成,应能解析出时间差/本地时刻
    assert rec2["prev"]["minutes_ago"] is not None
    assert rec2["prev"]["minutes_ago"] >= 0
    assert rec2["prev"]["time_local"] is not None


def test_run_checkpoint_injects_generated_at_local(monkeypatch):
    conn, city = _setup(monkeypatch, None)
    rec = run_checkpoint(conn, object(), city, "beijing", "sunset_glow",
                         date_type(2026, 7, 6), "c1")
    assert rec["generated_at"].tzinfo is not None
    assert str(rec["generated_at"].tzinfo) == "Asia/Shanghai"


def test_run_checkpoint_manual_far_lead_ignores_satellite(monkeypatch):
    """manual 在远期(3-6h)跑:实况只作 0.3 参考权重,主认定=模式预测
    (用户 2026-07-10:远期可参考实况外推,主要认定标准为四模式预测云图)。"""
    from datetime import datetime, timedelta, timezone
    pr = _fake_pr()
    pr.peak = datetime.now(timezone.utc) + timedelta(hours=5)
    monkeypatch.setattr(engine_mod, "compute_prediction", lambda *a, **k: pr)
    monkeypatch.setattr(engine_mod, "observe_burn_clouds",
                        lambda *a, **k: (48.0, 52.0, "now=48%→burn=52%", [],
                                         _fake_meta()))
    monkeypatch.setattr(engine_mod, "predict_pct", lambda *a, **k: None)
    conn = store.connect(":memory:")
    store.init_db(conn)
    city = City(key="beijing", name="北京", lat=39.9, lon=116.4,
                timezone="Asia/Shanghai")
    rec = run_checkpoint(conn, object(), city, "beijing", "sunset_glow",
                         date_type.today(), "manual")
    # (50,50)×0.7 + (63,55)×0.3 = (54,52):参考但不主导
    assert rec["probability_pct"] == 54 and rec["quality_pct"] == 52
    sheet = {f["name"]: f for f in rec["factor_sheet"]}
    assert sheet["外推纪律"]["status"] == "远期参考"
    assert "主认定=四模式预测云图" in sheet["外推纪律"]["note"]
