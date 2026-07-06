"""小程序只读 API(spec docs/superpowers/specs/2026-07-07-skyfire-miniapp-api-design.md)。

app 工厂可测;鉴权=微信登录换发的会话 token(X-Session 头,自用从宽)。
"""
import hashlib
import secrets
from pathlib import Path

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from skyfire import store
from skyfire.config import load_cities
from skyfire.wechatconf import load_wechat_config

_JSCODE_URL = "https://api.weixin.qq.com/sns/jscode2session"


class LoginBody(BaseModel):
    code: str


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_app(db_path: Path, config_path: Path, wechat_path: Path) -> FastAPI:
    app = FastAPI(title="skyfire api")
    app.add_middleware(CORSMiddleware, allow_origins=["*"],
                       allow_methods=["*"], allow_headers=["*"])
    app.state.db_path = db_path
    app.state.cities = load_cities(config_path)
    app.state.wechat_path = wechat_path
    app.state.wx_client = httpx.Client(timeout=10)

    def conn():
        c = store.connect(app.state.db_path)
        try:
            yield c
        finally:
            c.close()

    def require_session(x_session: str = Header(None), c=Depends(conn)):
        if not x_session or store.user_by_token(c, _hash(x_session)) is None:
            raise HTTPException(401, "未登录或会话失效")

    @app.post("/v1/login")
    def login(body: LoginBody, c=Depends(conn)):
        cfg = load_wechat_config(app.state.wechat_path)
        if cfg is None:
            raise HTTPException(503, "微信凭证未配置(config/wechat.local.yaml)")
        r = app.state.wx_client.get(_JSCODE_URL, params={
            "appid": cfg["app_id"], "secret": cfg["app_secret"],
            "js_code": body.code, "grant_type": "authorization_code"})
        data = r.json()
        openid = data.get("openid")
        if not openid:
            raise HTTPException(401, f"微信登录失败: {data.get('errmsg', '未知错误')}")
        token = secrets.token_urlsafe(32)
        store.set_user_token(c, openid, _hash(token))
        return {"token": token, "openid_suffix": openid[-4:]}

    @app.get("/v1/summary", dependencies=[Depends(require_session)])
    def summary(city: str = "beijing", c=Depends(conn)):
        if city not in app.state.cities:
            raise HTTPException(422, f"未知城市 {city!r}")
        return {"city": city, "dates": []}      # Task 4 填充

    return app
