import httpx

from skyfire import store
from skyfire.config import load_cities
from skyfire.engine import PredictionResult, compute_prediction
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
