import hashlib
from pathlib import Path

import httpx
from fastapi.testclient import TestClient

from skyfire import store
from skyfire.api import create_app

CONFIG = Path(__file__).parent.parent / "config" / "cities.yaml"


def _wx_transport(openid="oABC123456", errcode=None):
    def handler(request):
        assert request.url.host == "api.weixin.qq.com"
        if errcode is not None:
            return httpx.Response(200, json={"errcode": errcode, "errmsg": "invalid code"})
        return httpx.Response(200, json={"openid": openid, "session_key": "sk"})
    return httpx.MockTransport(handler)


def _make_app(tmp_path, wx_transport=None, wechat_yaml="app_id: wx1\napp_secret: s1\n"):
    db = tmp_path / "api.db"
    conn = store.connect(db); store.init_db(conn); conn.close()
    wechat = tmp_path / "wechat.local.yaml"
    if wechat_yaml is not None:
        wechat.write_text(wechat_yaml, encoding="utf-8")
    app = create_app(db_path=db, config_path=CONFIG, wechat_path=wechat,
                     maps_dir=tmp_path / "maps")
    if wx_transport is not None:
        app.state.wx_client = httpx.Client(transport=wx_transport)
    return app, db


def test_login_issues_token_and_persists_user(tmp_path):
    app, db = _make_app(tmp_path, _wx_transport())
    client = TestClient(app)
    r = client.post("/v1/login", json={"code": "abc"})
    assert r.status_code == 200
    token = r.json()["token"]
    assert len(token) > 20 and r.json()["openid_suffix"] == "3456"
    conn = store.connect(db)
    h = hashlib.sha256(token.encode()).hexdigest()
    assert store.user_by_token(conn, h)["openid"] == "oABC123456"


def test_login_wechat_error_401(tmp_path):
    app, _ = _make_app(tmp_path, _wx_transport(errcode=40029))
    r = TestClient(app).post("/v1/login", json={"code": "bad"})
    assert r.status_code == 401


def test_login_wechat_unreachable_503(tmp_path):
    def boom(request):
        raise httpx.ConnectTimeout("wx down")
    app, _ = _make_app(tmp_path, httpx.MockTransport(boom))
    r = TestClient(app).post("/v1/login", json={"code": "abc"})
    assert r.status_code == 503
    assert "微信接口调用失败" in r.json()["detail"]


def test_create_app_initializes_fresh_db(tmp_path):
    wechat = tmp_path / "wechat.local.yaml"
    wechat.write_text("app_id: wx1\napp_secret: s1\n", encoding="utf-8")
    app = create_app(db_path=tmp_path / "brand-new.db",   # 未 init 的新库
                     config_path=CONFIG, wechat_path=wechat)
    app.state.wx_client = httpx.Client(transport=_wx_transport())
    r = TestClient(app).post("/v1/login", json={"code": "abc"})
    assert r.status_code == 200            # 不再 no such table


def test_login_missing_credentials_503(tmp_path):
    app, _ = _make_app(tmp_path, wechat_yaml=None)
    r = TestClient(app).post("/v1/login", json={"code": "abc"})
    assert r.status_code == 503


def test_protected_endpoint_requires_token(tmp_path):
    app, _ = _make_app(tmp_path, _wx_transport())
    client = TestClient(app)
    assert client.get("/v1/summary?city=beijing").status_code == 401
    token = client.post("/v1/login", json={"code": "abc"}).json()["token"]
    r = client.get("/v1/summary?city=beijing", headers={"X-Session": token})
    assert r.status_code == 200


def _seed_predictions(db, date_s="2026-07-07"):
    import json
    conn = store.connect(db)
    kw = dict(quality_pct=30, confidence="high", rule_score=4.0,
              sat_cloud_pct=None, trend=None, llm_status="pending",
              reasoning=None, risks=None)
    store.add_prediction(conn, date_s, "beijing", "sunset_glow", "outlook",
                         probability_pct=38, **kw)
    pm = json.dumps({"gfs_seamless": {"prob": 55, "qual": 48, "cloud_high": 80,
                                      "cloud_mid": 30, "cloud_low": 12,
                                      "precipitation": 0.0}})
    store.add_prediction(conn, date_s, "beijing", "sunset_glow", "c2",
                         probability_pct=62, quality_pct=55, confidence="high",
                         rule_score=5.5, sat_cloud_pct=40.0, trend="现在40%",
                         llm_status="done", reasoning="画布成片", risks="低云",
                         per_model_json=pm)
    conn.close()


def test_summary_shape_dates_events_status(tmp_path, monkeypatch):
    from datetime import datetime
    from zoneinfo import ZoneInfo
    import skyfire.api as api_mod
    app, db = _make_app(tmp_path, _wx_transport())
    _seed_predictions(db)
    # 固定"现在"= 2026-07-07 12:00 北京(朝霞已过、晚霞未到)
    monkeypatch.setattr(api_mod, "_now_local", lambda tz: datetime(
        2026, 7, 7, 12, 0, tzinfo=ZoneInfo(tz)))
    client = TestClient(app)
    token = client.post("/v1/login", json={"code": "abc"}).json()["token"]
    data = client.get("/v1/summary?city=beijing",
                      headers={"X-Session": token}).json()
    assert data["city_name"] == "北京" and len(data["dates"]) == 2
    d0 = data["dates"][0]
    assert d0["date"] == "2026-07-07" and d0["label"].startswith("今天")
    assert [e["event"] for e in d0["events"]] == ["sunrise_glow", "sunset_glow"]
    sunrise, sunset = d0["events"]
    assert sunrise["status"] == "ended"            # 12:00 > 日出峰值
    assert sunset["status"] == "upcoming"
    assert sunset["latest"]["probability_pct"] == 62
    assert sunset["latest"]["prob_word"] == "机会较大"  # _prob_word(62): report.py 现行口径 <80 档
    assert [t["checkpoint"] for t in sunset["trajectory"]] == ["outlook", "c2"]
    assert sunset["per_model"]["gfs_seamless"]["cloud_high"] == 80
    assert sunrise["latest"] is None               # 没喂朝霞数据
    assert data["dates"][1]["label"].startswith("明天")
    assert "peak" in sunset and "-" in sunset["best_window"]


def test_heatmap_serves_precomputed_png(tmp_path):
    # 地图=后台预生成存盘,API 直取(不实时算)
    from skyfire.maps import map_path
    app, _ = _make_app(tmp_path, _wx_transport())
    maps_dir = app.state.maps_dir
    p = map_path(maps_dir, "beijing", "2026-07-08", "sunset_glow", "prob")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"\x89PNG\r\n\x1a\nFAKE")
    client = TestClient(app)
    token = client.post("/v1/login", json={"code": "abc"}).json()["token"]
    r = client.get("/v1/heatmap?city=beijing&event=sunset_glow"
                   "&date=2026-07-08&kind=prob", headers={"X-Session": token})
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/png"
    assert r.content[:8] == b"\x89PNG\r\n\x1a\n"


def test_heatmap_missing_returns_404(tmp_path):
    # 尚未生成(未到模式更新/超预报覆盖)→ 404,前端显示占位
    app, _ = _make_app(tmp_path, _wx_transport())
    client = TestClient(app)
    token = client.post("/v1/login", json={"code": "abc"}).json()["token"]
    r = client.get("/v1/heatmap?city=beijing&event=sunset_glow"
                   "&date=2026-07-08&kind=prob", headers={"X-Session": token})
    assert r.status_code == 404


def test_heatmap_bad_kind_422(tmp_path):
    app, _ = _make_app(tmp_path, _wx_transport())
    client = TestClient(app)
    token = client.post("/v1/login", json={"code": "abc"}).json()["token"]
    r = client.get("/v1/heatmap?city=beijing&event=sunset_glow"
                   "&date=2026-07-07&kind=nope", headers={"X-Session": token})
    assert r.status_code == 422


def _stub_location(monkeypatch, center_q, loc_q):
    """打桩 score_location:中心与用户位置各返回给定质量(prob=qual+5)。"""
    import skyfire.api as api_mod
    calls = []

    def fake(client, lat, lon, tz, event, day, skill_rows=None):
        calls.append((round(lat, 3), round(lon, 3)))
        q = loc_q if (abs(lat - 39.9042) > 0.01 or abs(lon - 116.4074) > 0.01) else center_q
        return {"probability_pct": q + 5, "quality_pct": q,
                "rule_score": q / 10, "confidence": "medium"}
    monkeypatch.setattr(api_mod, "score_location", fake)
    return calls


def test_local_anchors_to_center_prediction(tmp_path, monkeypatch):
    from skyfire import store
    app, db = _make_app(tmp_path, _wx_transport())
    # 中心已有 LLM 精修预测 质量60
    conn = store.connect(db)
    store.add_prediction(conn, "2026-07-08", "beijing", "sunset_glow", "c2",
                         probability_pct=62, quality_pct=60, confidence="high",
                         rule_score=5.5, sat_cloud_pct=None, trend=None,
                         llm_status="done", reasoning="x", risks="y")
    conn.close()
    # 用户位置物理分比中心高10(50 vs 40)→ 锚定后 = 60 + 10 = 70
    _stub_location(monkeypatch, center_q=40, loc_q=50)
    client = TestClient(app)
    token = client.post("/v1/login", json={"code": "abc"}).json()["token"]
    r = client.get("/v1/local?event=sunset_glow&date=2026-07-08"
                   "&lat=40.4&lon=116.8", headers={"X-Session": token})
    assert r.status_code == 200
    d = r.json()
    assert d["quality_pct"] == 70 and d["delta_quality"] == 10   # 中心60 + 位置差10
    assert d["level"] == "中烧"


def test_local_bad_coords_422(tmp_path, monkeypatch):
    app, _ = _make_app(tmp_path, _wx_transport())
    client = TestClient(app)
    token = client.post("/v1/login", json={"code": "abc"}).json()["token"]
    r = client.get("/v1/local?event=sunset_glow&date=2026-07-08&lat=5&lon=10",
                   headers={"X-Session": token})
    assert r.status_code == 422
