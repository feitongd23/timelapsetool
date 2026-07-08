"""小程序只读 API(spec docs/superpowers/specs/2026-07-07-skyfire-miniapp-api-design.md)。

app 工厂可测;鉴权=微信登录换发的会话 token(X-Session 头,自用从宽)。
"""
import hashlib
import json
import secrets
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from skyfire import store
from skyfire.config import load_cities
from skyfire.engine import score_location
from skyfire.maps import DEFAULT_MAPS_DIR, map_path
from skyfire.report import _burn_level, _prob_word, _qual_word
from skyfire.suntimes import sun_window
from skyfire.wechatconf import load_wechat_config

_JSCODE_URL = "https://api.weixin.qq.com/sns/jscode2session"


class LoginBody(BaseModel):
    code: str


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _now_local(tz: str) -> datetime:
    return datetime.now(ZoneInfo(tz))


def _clamp(v: float) -> int:
    return int(round(max(0.0, min(100.0, v))))




def create_app(db_path: Path, config_path: Path, wechat_path: Path,
               maps_dir: Path = DEFAULT_MAPS_DIR) -> FastAPI:
    app = FastAPI(title="skyfire api")
    app.add_middleware(CORSMiddleware, allow_origins=["*"],
                       allow_methods=["*"], allow_headers=["*"])
    app.state.db_path = db_path
    app.state.cities = load_cities(config_path)
    app.state.wechat_path = wechat_path
    app.state.maps_dir = maps_dir
    app.state.wx_client = httpx.Client(timeout=10)
    init_conn = store.connect(db_path)
    store.init_db(init_conn)
    init_conn.close()

    def conn():
        c = store.connect(app.state.db_path, check_same_thread=False)
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
                date: str = "", kind: str = "prob"):
        """直取后台预生成的全国地图 PNG(不实时算,用户零等待)。

        未生成(尚未到模式更新/超出预报覆盖)→ 404,前端显示占位。
        """
        if city not in app.state.cities:
            raise HTTPException(422, f"未知城市 {city!r}")
        if event not in ("sunrise_glow", "sunset_glow"):
            raise HTTPException(422, f"未知天象 {event!r}")
        if kind not in ("prob", "quality"):
            raise HTTPException(422, f"kind 需为 prob|quality,收到 {kind!r}")
        try:
            day = datetime.strptime(date, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(422, f"date 需为 YYYY-MM-DD,收到 {date!r}")
        p = map_path(app.state.maps_dir, city, str(day), event, kind)
        if not p.exists():
            raise HTTPException(404, "地图生成中(跟随模式更新,稍后重试)")
        return Response(p.read_bytes(), media_type="image/png")

    @app.get("/v1/local", dependencies=[Depends(require_session)])
    def local(event: str, date: str, lat: float, lon: float,
              city: str = "beijing", c=Depends(conn)):
        """按用户 GPS 给位置专属概率/质量。

        位置值 = 中心精修预测(LLM/卫星)+ 本地物理差(该点通道/云与中心之差),
        故与首页大数字口径一致、只按所在地偏移(用户 2026-07-08)。
        """
        if city not in app.state.cities:
            raise HTTPException(422, f"未知城市 {city!r}")
        if event not in ("sunrise_glow", "sunset_glow"):
            raise HTTPException(422, f"未知天象 {event!r}")
        if not (15 <= lat <= 55 and 70 <= lon <= 140):
            raise HTTPException(422, "经纬度超出范围")
        try:
            day = datetime.strptime(date, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(422, f"date 需为 YYYY-MM-DD,收到 {date!r}")
        ct = app.state.cities[city]
        skill = store.get_model_skill(c)
        try:
            with httpx.Client(timeout=20) as client:
                loc = score_location(client, lat, lon, ct.timezone, event, day,
                                     skill_rows=skill)
                center = score_location(client, ct.lat, ct.lon, ct.timezone,
                                        event, day, skill_rows=skill)
        except (httpx.HTTPError, ValueError) as e:
            raise HTTPException(503, f"定位打分失败: {e.__class__.__name__}")
        latest = store.latest_prediction(c, str(day), city, event)
        if latest and latest.get("llm_status") == "done":
            base_q, base_p = latest["quality_pct"], latest["probability_pct"]
        else:  # 无精修基准:直接用中心物理分作锚
            base_q, base_p = center["quality_pct"], center["probability_pct"]
        q = _clamp(base_q + (loc["quality_pct"] - center["quality_pct"]))
        p = _clamp(base_p + (loc["probability_pct"] - center["probability_pct"]))
        return {"probability_pct": p, "quality_pct": q,
                "prob_word": _prob_word(p), "qual_word": _qual_word(q),
                "level": _burn_level(q),
                "delta_quality": q - base_q,   # 相对中心的位置偏移(±)
                "lat": lat, "lon": lon}

    return app
