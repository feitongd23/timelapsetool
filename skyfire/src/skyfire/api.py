"""小程序只读 API(spec docs/superpowers/specs/2026-07-07-skyfire-miniapp-api-design.md)。

app 工厂可测;鉴权=微信登录换发的会话 token(X-Session 头,自用从宽)。
"""
import hashlib
import json
import secrets
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from skyfire import store
from skyfire.config import load_cities
from skyfire.gridmap import DEFAULT_BBOX, DEFAULT_STEP, fetch_cloud_grid, grid_points
from skyfire.heatgrid import render_heatmap_png, score_grids
from skyfire.report import _prob_word, _qual_word
from skyfire.suntimes import nearest_iso_hour, sun_window
from skyfire.wechatconf import load_wechat_config

_JSCODE_URL = "https://api.weixin.qq.com/sns/jscode2session"


class LoginBody(BaseModel):
    code: str


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _now_local(tz: str) -> datetime:
    return datetime.now(ZoneInfo(tz))


_HEATMAP_CACHE: dict[tuple, tuple[float, bytes]] = {}
_HEATMAP_TTL = 1800.0


def create_app(db_path: Path, config_path: Path, wechat_path: Path) -> FastAPI:
    app = FastAPI(title="skyfire api")
    app.add_middleware(CORSMiddleware, allow_origins=["*"],
                       allow_methods=["*"], allow_headers=["*"])
    app.state.db_path = db_path
    app.state.cities = load_cities(config_path)
    app.state.wechat_path = wechat_path
    app.state.wx_client = httpx.Client(timeout=10)
    init_conn = store.connect(db_path)
    store.init_db(init_conn)
    init_conn.close()

    def conn():
        c = store.connect(app.state.db_path)
        try:
            yield c
        finally:
            c.close()

    def require_session(x_session: str | None = Header(None), c=Depends(conn)):
        if not x_session or store.user_by_token(c, _hash(x_session)) is None:
            raise HTTPException(401, "未登录或会话失效")

    @app.post("/v1/login")
    def login(body: LoginBody, c=Depends(conn)):
        cfg = load_wechat_config(app.state.wechat_path)
        if cfg is None:
            raise HTTPException(503, "微信凭证未配置(config/wechat.local.yaml)")
        try:
            r = app.state.wx_client.get(_JSCODE_URL, params={
                "appid": cfg["app_id"], "secret": cfg["app_secret"],
                "js_code": body.code, "grant_type": "authorization_code"})
            data = r.json()
        except (httpx.HTTPError, ValueError) as e:
            raise HTTPException(503, f"微信接口调用失败: {e.__class__.__name__}")
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
        ct = app.state.cities[city]
        now = _now_local(ct.timezone)
        dates = []
        for offset, day_label in ((0, "今天"), (1, "明天")):
            day = (now + timedelta(days=offset)).date()
            events = []
            for event in ("sunrise_glow", "sunset_glow"):
                win = sun_window(ct.lat, ct.lon, ct.timezone, day, event)
                rows = store.predictions_for(c, str(day), city, event)
                latest = rows[-1] if rows else None
                if latest is not None:
                    latest = {
                        "checkpoint": latest["checkpoint"],
                        "probability_pct": latest["probability_pct"],
                        "quality_pct": latest["quality_pct"],
                        "prob_word": _prob_word(latest["probability_pct"]),
                        "qual_word": _qual_word(latest["quality_pct"]),
                        "confidence": latest["confidence"],
                        "llm_status": latest["llm_status"],
                        "reasoning": latest["reasoning"],
                        "risks": latest["risks"],
                        "created_at": latest["created_at"],
                    }
                per_model = {}
                if rows and rows[-1].get("per_model_json"):
                    per_model = json.loads(rows[-1]["per_model_json"])
                best = (f"{win.peak:%H:%M}-{win.peak + timedelta(minutes=15):%H:%M}"
                        if event == "sunset_glow" else
                        f"{win.peak - timedelta(minutes=15):%H:%M}-{win.peak:%H:%M}")
                events.append({
                    "event": event,
                    "status": "ended" if now > win.peak else "upcoming",
                    "peak": f"{win.peak:%H:%M}", "best_window": best,
                    "latest": latest,
                    "trajectory": [{"checkpoint": r["checkpoint"],
                                    "probability_pct": r["probability_pct"],
                                    "quality_pct": r["quality_pct"],
                                    "created_at": r["created_at"]} for r in rows],
                    "per_model": per_model,
                })
            dates.append({"date": str(day),
                          "label": f"{day_label} {day.month}月{day.day}日",
                          "events": events})
        return {"city": city, "city_name": ct.name,
                "updated_at": now.isoformat(timespec="seconds"),
                "dates": dates}

    @app.get("/v1/heatmap", dependencies=[Depends(require_session)])
    def heatmap(city: str = "beijing", event: str = "sunset_glow",
                date: str = "", kind: str = "prob", c=Depends(conn)):
        if city not in app.state.cities:
            raise HTTPException(422, f"未知城市 {city!r}")
        if event not in ("sunrise_glow", "sunset_glow"):
            raise HTTPException(422, f"未知天象 {event!r}")
        if kind not in ("prob", "quality"):
            raise HTTPException(422, f"kind 需为 prob|quality,收到 {kind!r}")
        ct = app.state.cities[city]
        try:
            day = datetime.strptime(date, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(422, f"date 需为 YYYY-MM-DD,收到 {date!r}")
        key = (city, event, str(day), kind)
        hit = _HEATMAP_CACHE.get(key)
        if hit and time.monotonic() < hit[0]:
            return Response(hit[1], media_type="image/png")
        win = sun_window(ct.lat, ct.lon, ct.timezone, day, event)
        pts = grid_points(DEFAULT_BBOX, DEFAULT_STEP)
        n_cols = len({lon for _, lon in pts})
        n_rows = len(pts) // n_cols
        latest = store.latest_prediction(c, str(day), city, event)
        confidence = (latest or {}).get("confidence") or "medium"
        try:
            cloud = fetch_cloud_grid(httpx.Client(timeout=30), pts, n_rows,
                                     n_cols, ct.timezone,
                                     nearest_iso_hour(win.peak),
                                     with_precip=True)
        except httpx.HTTPError as e:
            raise HTTPException(503, f"网格数据拉取失败: {e.__class__.__name__}")
        grids = score_grids(cloud, confidence)
        lon0, lat0, lon1, lat1 = DEFAULT_BBOX
        marker = ((lat1 - ct.lat) / DEFAULT_STEP, (ct.lon - lon0) / DEFAULT_STEP)
        png = render_heatmap_png(grids[kind], kind, marker_rc=marker)
        _HEATMAP_CACHE[key] = (time.monotonic() + _HEATMAP_TTL, png)
        return Response(png, media_type="image/png")

    return app
