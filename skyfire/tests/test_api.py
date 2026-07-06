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
    app = create_app(db_path=db, config_path=CONFIG, wechat_path=wechat)
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
