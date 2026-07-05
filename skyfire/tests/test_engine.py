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


def _fake_pr(index=5.0, confidence="high"):
    from datetime import datetime, timezone
    return PredictionResult(
        city_name="北京", event="sunset_glow", day=date_type(2026, 7, 6),
        index=index, confidence=confidence, spread=1.0,
        per_model={"gfs_seamless": index}, blocked_points=0, channel_factor=1.0,
        aod=0.3, channel_empty=False,
        peak=datetime(2026, 7, 6, 19, 40, tzinfo=timezone.utc), azimuth=295.0,
        llm=None)


def _setup(monkeypatch, llm_result):
    monkeypatch.setattr(engine_mod, "compute_prediction",
                        lambda *a, **k: _fake_pr())
    monkeypatch.setattr(engine_mod, "observe_burn_clouds",
                        lambda *a, **k: (48.0, 52.0, "now=48%→burn=52%", []))
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
    # C1 早间展望:短时外推冒充不了届时云况 → 基线只用预报(不加云量修正)
    # rule 5.0 high → qual 50, prob 50(外推 52 不参与)
    assert rec["probability_pct"] == 50 and rec["quality_pct"] == 50
    assert rec["per_model_pct"] == {"gfs_seamless": (50, 50)}


def test_run_checkpoint_c3_uses_satellite_extrapolation(monkeypatch):
    conn, city = _setup(monkeypatch, None)
    rec = run_checkpoint(conn, object(), city, "beijing", "sunset_glow",
                         date_type(2026, 7, 6), "c3")
    # C3 临近:外推 52% 落甜区 → prob 50+15=65
    assert rec["probability_pct"] == 65 and rec["quality_pct"] == 50
    assert rec["per_model_pct"] == {"gfs_seamless": (65, 50)}


def test_run_checkpoint_gated_skips_small_delta(monkeypatch):
    conn, city = _setup(monkeypatch, None)
    run_checkpoint(conn, object(), city, "beijing", "sunset_glow",
                   date_type(2026, 7, 6), "c1")            # 落一版 prob=65
    rec = run_checkpoint(conn, object(), city, "beijing", "sunset_glow",
                         date_type(2026, 7, 6), "gated", gate=True)
    assert rec is None                                      # Δ=0 < 15pp,不落库
    assert len(store.predictions_for(conn, "2026-07-06", "beijing",
                                     "sunset_glow")) == 1
