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


def test_heatmap_model_param_serves_model_file(tmp_path):
    # EC/GFS 双模式图(2026-07-09):model 参数选文件,缺时回退旧版合成图
    from skyfire.maps import map_path
    app, _ = _make_app(tmp_path, _wx_transport())
    maps_dir = app.state.maps_dir
    maps_dir.mkdir(parents=True, exist_ok=True)
    map_path(maps_dir, "beijing", "2026-07-08", "sunset_glow", "prob",
             "gfs").write_bytes(b"\x89PNG\r\n\x1a\nGFS!")
    map_path(maps_dir, "beijing", "2026-07-08", "sunset_glow",
             "prob").write_bytes(b"\x89PNG\r\n\x1a\nOLD!")
    client = TestClient(app)
    token = client.post("/v1/login", json={"code": "abc"}).json()["token"]
    base = ("/v1/heatmap?city=beijing&event=sunset_glow"
            "&date=2026-07-08&kind=prob")
    r = client.get(base + "&model=gfs", headers={"X-Session": token})
    assert r.status_code == 200 and r.content.endswith(b"GFS!")
    # ec 文件不存在 → 回退旧版合成图(平滑过渡)
    r = client.get(base + "&model=ec", headers={"X-Session": token})
    assert r.status_code == 200 and r.content.endswith(b"OLD!")
    r = client.get(base + "&model=nope", headers={"X-Session": token})
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


def _ext_transport(embassy_ok=True):
    """mock 外呼:Open-Meteo 天气/空气、美使馆、Nominatim。"""
    def handler(request):
        host = request.url.host
        if "dosairnowdata" in host:
            if not embassy_ok:
                return httpx.Response(500)
            return httpx.Response(200, json=[
                {"stationName": "Beijing", "aqi": 62, "conc": 17.2,
                 "localTimeStamp": "2026-07-09 19:00:00"}])
        if "air-quality" in host:
            return httpx.Response(200, json={"hourly": {
                "time": ["2026-07-09T18:00", "2026-07-09T19:00"],
                "pm2_5": [14.0, 16.0]}})
        if "nominatim" in host:
            return httpx.Response(200, json={"address": {
                "suburb": "望京", "district": "朝阳区"}})
        # 预报端点(逐小时天气)。日期须相对今天:写死日期会在真实时钟越过
        # 序列尾部时让"未来8小时"不足8条(2026-07-10 傍晚实爆的时间炸弹)
        from datetime import date, timedelta
        d0, d1 = date.today(), date.today() + timedelta(days=1)
        times = [f"{d0}T{h:02d}:00" for h in range(24)] + \
                [f"{d1}T{h:02d}:00" for h in range(24)]
        n = len(times)
        return httpx.Response(200, json={"hourly": {
            "time": times, "temperature_2m": [30.4] * n,
            "weather_code": [2] * n, "cloud_cover": [55] * n,
            "precipitation": [0.0] * n}})
    return httpx.MockTransport(handler)


def test_hourly_endpoint_shapes_hours(tmp_path):
    app, _ = _make_app(tmp_path, _wx_transport())
    app.state.ext_client = httpx.Client(transport=_ext_transport())
    client = TestClient(app)
    token = client.post("/v1/login", json={"code": "abc"}).json()["token"]
    r = client.get("/v1/hourly?lat=39.99&lon=116.47",
                   headers={"X-Session": token})
    assert r.status_code == 200
    hours = r.json()["hours"]
    assert len(hours) == 8
    assert {"hour", "temp", "text", "cloud", "precip"} <= set(hours[0])
    assert hours[0]["temp"] == 30 and hours[0]["text"] == "多云"


def test_aqi_embassy_first_then_fallback(tmp_path):
    app, _ = _make_app(tmp_path, _wx_transport())
    client = TestClient(app)
    token = client.post("/v1/login", json={"code": "abc"}).json()["token"]
    hdr = {"X-Session": token}
    # 使馆通 → 用使馆
    app.state.ext_client = httpx.Client(transport=_ext_transport(embassy_ok=True))
    d = client.get("/v1/aqi?lat=39.99&lon=116.47", headers=hdr).json()
    assert d["aqi"] == 62 and d["source"] == "北京美使馆" and d["level"] == "良"
    # 使馆挂 → Open-Meteo PM2.5 换算(16µg → AQI 59 良)
    app.state.ext_cache.clear()
    app.state.ext_client = httpx.Client(transport=_ext_transport(embassy_ok=False))
    d = client.get("/v1/aqi?lat=39.99&lon=116.47", headers=hdr).json()
    assert d["source"] == "CAMS" and d["level"] == "良" and 55 <= d["aqi"] <= 62


def test_report_endpoint_returns_full_row(tmp_path):
    app, db = _make_app(tmp_path, _wx_transport())
    _seed_predictions(db)
    client = TestClient(app)
    token = client.post("/v1/login", json={"code": "abc"}).json()["token"]
    hdr = {"X-Session": token}
    conn = store.connect(db)
    rid = store.predictions_for(conn, "2026-07-07", "beijing",
                                "sunset_glow")[-1]["id"]
    conn.close()
    r = client.get(f"/v1/report?id={rid}", headers=hdr)
    assert r.status_code == 200
    d = r.json()
    assert d["id"] == rid and d["reasoning"] == "画布成片"
    assert d["level"] and d["per_model"]["gfs_seamless"]["cloud_high"] == 80
    assert client.get("/v1/report?id=99999", headers=hdr).status_code == 404


def test_satimg_serves_latest_frame(tmp_path):
    live = tmp_path / "live"
    live.mkdir()
    (live / "live_20260709_1000.png").write_bytes(b"\x89PNG\r\n\x1a\nOLD")
    (live / "live_20260709_1100.png").write_bytes(b"\x89PNG\r\n\x1a\nNEW")
    db = tmp_path / "api.db"
    conn = store.connect(db); store.init_db(conn); conn.close()
    wechat = tmp_path / "wechat.local.yaml"
    wechat.write_text("app_id: wx1\napp_secret: s1\n", encoding="utf-8")
    app = create_app(db_path=db, config_path=CONFIG, wechat_path=wechat,
                     maps_dir=tmp_path / "maps", live_dir=live)
    app.state.wx_client = httpx.Client(transport=_wx_transport())
    client = TestClient(app)
    token = client.post("/v1/login", json={"code": "abc"}).json()["token"]
    r = client.get("/v1/satimg", headers={"X-Session": token})
    assert r.status_code == 200
    assert r.content.endswith(b"NEW")               # 取最新帧
    assert r.headers["x-sat-time"] == "19:00"       # UTC 11:00 → 北京 19:00


def test_phenomena_endpoint_shape(tmp_path, monkeypatch):
    """云海+彩虹端点(2026-07-11):契约与缓存,引擎打桩。"""
    import skyfire.phenomena as ph
    calls = {"n": 0}

    def fake_sea(client, lat, lon, tz, day):
        calls["n"] += 1
        return {"prob": 62, "tier": "香山档", "gates": {"成雾": 1.0},
                "notes": ["前日透雨"], "sunrise": "04:55"}

    monkeypatch.setattr(ph, "forecast_cloudsea", fake_sea)
    monkeypatch.setattr(ph, "forecast_rainbow",
                        lambda *a, **k: {"level": 1, "label": "潜势日",
                                         "window": "16:30-19:39",
                                         "sun_elev": None, "antisolar_az": None,
                                         "bow_top": None,
                                         "double_potential": False,
                                         "notes": []})
    app, _ = _make_app(tmp_path, _wx_transport())
    client = TestClient(app)
    token = client.post("/v1/login", json={"code": "abc"}).json()["token"]
    r = client.get("/v1/phenomena", headers={"X-Session": token})
    assert r.status_code == 200
    d = r.json()
    assert d["cloudsea"]["prob"] == 62 and d["cloudsea"]["tier"] == "香山档"
    assert "date" in d["cloudsea"]
    assert d["rainbow"]["label"] == "潜势日"
    # 二次请求走缓存,引擎不重算
    client.get("/v1/phenomena", headers={"X-Session": token})
    assert calls["n"] == 1
