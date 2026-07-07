# Skyfire 只读 API(登录/summary/热力图)实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** FastAPI 三端点(POST /v1/login 微信一键登录、GET /v1/summary 日期×朝霞晚霞全量数据、GET /v1/heatmap 平滑热力图 PNG)+ `skyfire serve` 命令,供 Taro 小程序消费(小程序是下一个计划)。

**Architecture:** 新模块 api.py(HTTP 层,app 工厂可测)/heatgrid.py(逐格规则分+平滑渲染)/wechatconf.py(凭证加载);store 加 users token;gridmap.fetch_cloud_grid 扩展降水层。spec: `docs/superpowers/specs/2026-07-07-skyfire-miniapp-api-design.md`。

**Tech Stack:** Python 3.12(venv `skyfire/.venv`)、FastAPI+uvicorn(新依赖)、pytest+TestClient、numpy+PIL(已有)、httpx MockTransport 打桩微信/Open-Meteo。

**工作目录:** 命令在 `/Users/feitong/photo-app/skyfire` 下执行;测试用 `.venv/bin/pytest`。

---

### Task 0: 开分支 + 装依赖

**Files:**
- Modify: `skyfire/pyproject.toml:10-19`(dependencies)

- [ ] **Step 1: 开分支**

```bash
cd /Users/feitong/photo-app && git checkout -b feat/skyfire-api main
```

- [ ] **Step 2: pyproject dependencies 列表追加两行**(在 `"satpy>=0.50",` 之后)

```toml
    "fastapi>=0.115",
    "uvicorn>=0.30",
```

- [ ] **Step 3: 安装并验证**

```bash
cd skyfire && .venv/bin/pip install -e . -q && .venv/bin/python -c "import fastapi, uvicorn; print('ok')"
```

Expected: `ok`

- [ ] **Step 4: 全量测试不回归**

Run: `.venv/bin/pytest -q`
Expected: 199 passed

- [ ] **Step 5: Commit**

```bash
git add skyfire/pyproject.toml
git commit -m "build(skyfire): 加 fastapi/uvicorn 依赖"
```

---

### Task 1: wechatconf 凭证加载 + users 表 token 列

**Files:**
- Create: `skyfire/src/skyfire/wechatconf.py`
- Create: `skyfire/config/wechat.example.yaml`
- Modify: `skyfire/src/skyfire/store.py`(init_db 加列;新增 set_user_token/user_by_token)
- Modify: `skyfire/.gitignore` 或仓库根 `.gitignore`(确认 `config/*.local.yaml` 已忽略;notify.local.yaml 已被忽略则同模式自动覆盖,验证即可)
- Test: `skyfire/tests/test_wechatconf.py`、`skyfire/tests/test_store.py`

- [ ] **Step 1: 写失败测试**

新建 `tests/test_wechatconf.py`:

```python
import pytest

from skyfire.wechatconf import load_wechat_config


def test_missing_file_returns_none(tmp_path):
    assert load_wechat_config(tmp_path / "nope.yaml") is None


def test_loads_credentials(tmp_path):
    p = tmp_path / "wechat.local.yaml"
    p.write_text("app_id: wx123\napp_secret: abc\n", encoding="utf-8")
    cfg = load_wechat_config(p)
    assert cfg == {"app_id": "wx123", "app_secret": "abc"}


def test_incomplete_raises(tmp_path):
    p = tmp_path / "wechat.local.yaml"
    p.write_text("app_id: wx123\n", encoding="utf-8")
    with pytest.raises(ValueError):
        load_wechat_config(p)
```

`tests/test_store.py` 追加:

```python
def test_user_token_roundtrip(tmp_path):
    conn = store.connect(tmp_path / "t.db")
    store.init_db(conn)
    store.set_user_token(conn, "openid-1", "hash-a")
    store.set_user_token(conn, "openid-1", "hash-b")   # 重登覆盖
    assert store.user_by_token(conn, "hash-a") is None
    u = store.user_by_token(conn, "hash-b")
    assert u["openid"] == "openid-1"
    assert store.user_by_token(conn, "nope") is None
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/bin/pytest tests/test_wechatconf.py tests/test_store.py -v -k "wechat or token"`
Expected: FAIL(模块/函数不存在)

- [ ] **Step 3: 实现 wechatconf.py**

```python
"""微信小程序凭证加载(gitignored 本地文件,含 AppSecret)。"""
from pathlib import Path

import yaml


def load_wechat_config(path: Path) -> dict | None:
    """读取微信凭证。文件不存在返回 None(视为未配置,login 返回 503)。"""
    if not Path(path).exists():
        return None
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    app_id, app_secret = data.get("app_id"), data.get("app_secret")
    if not app_id or not app_secret:
        raise ValueError("wechat 配置需同时含 app_id 与 app_secret")
    return {"app_id": str(app_id), "app_secret": str(app_secret)}
```

`config/wechat.example.yaml`:

```yaml
# cp wechat.example.yaml wechat.local.yaml 并填入小程序凭证(mp.weixin.qq.com)
app_id: wx0000000000000000
app_secret: 请填小程序AppSecret
```

- [ ] **Step 4: 实现 store 侧**

init_db 中 cases 的 ALTER 块之后(`_migrate_predictions(conn)` 之前)加:

```python
    ucols = [r[1] for r in conn.execute("PRAGMA table_info(users)").fetchall()]
    if "token_hash" not in ucols:
        conn.execute("ALTER TABLE users ADD COLUMN token_hash TEXT")
```

store.py 末尾(recent_predictions 之后)加:

```python
def set_user_token(conn, openid: str, token_hash: str) -> int:
    """微信登录:openid 落库并绑定新会话 token(重登覆盖旧 token)。"""
    _write(conn,
           """INSERT INTO users (openid, token_hash) VALUES (?, ?)
              ON CONFLICT(openid) DO UPDATE SET token_hash=excluded.token_hash""",
           (openid, token_hash))
    row = conn.execute("SELECT id FROM users WHERE openid=?", (openid,)).fetchone()
    return row[0]


def user_by_token(conn, token_hash: str) -> dict | None:
    row = conn.execute("SELECT id, openid FROM users WHERE token_hash=?",
                       (token_hash,)).fetchone()
    return None if row is None else {"id": row[0], "openid": row[1]}
```

- [ ] **Step 5: 验证 gitignore 已覆盖 local yaml**

Run: `git -C /Users/feitong/photo-app check-ignore skyfire/config/wechat.local.yaml && echo IGNORED`
Expected: 输出 IGNORED(notify.local.yaml 同模式已被忽略;若未忽略,在 skyfire/.gitignore 加一行 `config/*.local.yaml`)

- [ ] **Step 6: 跑测试确认通过 + 全量**

Run: `.venv/bin/pytest tests/test_wechatconf.py tests/test_store.py -v` 然后 `.venv/bin/pytest -q`
Expected: 全 PASS;全量 203(199+4)

- [ ] **Step 7: Commit**

```bash
git add skyfire/src/skyfire/wechatconf.py skyfire/config/wechat.example.yaml skyfire/src/skyfire/store.py skyfire/tests/test_wechatconf.py skyfire/tests/test_store.py
git commit -m "feat(skyfire): 微信凭证配置加载 + users 表会话 token(重登覆盖)"
```

---

### Task 2: gridmap 降水层 + heatgrid 逐格打分

**Files:**
- Modify: `skyfire/src/skyfire/gridmap.py:33-64`(fetch_cloud_grid 加 with_precip)
- Create: `skyfire/src/skyfire/heatgrid.py`
- Test: `skyfire/tests/test_gridmap.py`、`skyfire/tests/test_heatgrid.py`

- [ ] **Step 1: 写失败测试**

`tests/test_gridmap.py` 追加(该文件已有 fetch_cloud_grid 的 MockTransport 测试可参考取样式):

```python
def test_fetch_cloud_grid_with_precip(monkeypatch):
    import httpx
    times = [f"2026-07-08T{h:02d}:00" for h in range(24)]

    def handler(request):
        n = str(request.url.params["latitude"]).count(",") + 1
        assert "precipitation" in request.url.params["hourly"]
        loc = {"hourly": {"time": times,
                          "cloud_cover_high": [50] * 24,
                          "cloud_cover_mid": [20] * 24,
                          "cloud_cover_low": [10] * 24,
                          "precipitation": [0.3] * 24}}
        return httpx.Response(200, json=[loc] * n)

    from skyfire.gridmap import fetch_cloud_grid, grid_points
    pts = grid_points((110.0, 36.0, 112.0, 38.0), 1.0)   # 3x3
    client = httpx.Client(transport=httpx.MockTransport(handler))
    grid = fetch_cloud_grid(client, pts, 3, 3, "Asia/Shanghai",
                            "2026-07-08T19:00", with_precip=True)
    assert grid["precip"][0][0] == 0.3 and grid["high"][2][2] == 50
```

新建 `tests/test_heatgrid.py`:

```python
from skyfire.heatgrid import render_heatmap_png, score_grids


def _cloud(v_high, v_mid, v_low, precip=0.0, rows=3, cols=3):
    mk = lambda v: [[v] * cols for _ in range(rows)]
    return {"high": mk(v_high), "mid": mk(v_mid), "low": mk(v_low),
            "precip": mk(precip)}


def test_score_grids_sweet_spot_beats_overcast():
    sweet = score_grids(_cloud(50, 10, 5), "high")
    overcast = score_grids(_cloud(100, 80, 60), "high")
    assert sweet["prob"][0][0] > overcast["prob"][0][0]
    assert sweet["quality"][0][0] > overcast["quality"][0][0]
    assert 0 <= sweet["prob"][0][0] <= 100


def test_score_grids_none_cell_scores_zero():
    cloud = _cloud(50, 10, 5)
    cloud["high"][1][1] = None
    g = score_grids(cloud, "medium")
    assert g["prob"][1][1] == 0 and g["quality"][1][1] == 0


def test_render_heatmap_png_smooth_bytes():
    values = [[10, 40, 80], [20, 60, 90], [10, 30, 50]]
    png = render_heatmap_png(values, "prob", marker_rc=(1.2, 1.5))
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    from io import BytesIO
    from PIL import Image
    img = Image.open(BytesIO(png))
    assert img.size == (624, 432) and img.mode == "RGB"
    # 平滑性抽查:相邻两列像素不应出现瓦片式硬跳变(插值后为渐变)
    a, b = img.getpixel((300, 216)), img.getpixel((302, 216))
    assert max(abs(a[i] - b[i]) for i in range(3)) < 40


def test_render_heatmap_png_quality_uses_purple():
    values = [[90] * 3] * 3
    png_q = render_heatmap_png(values, "quality", marker_rc=None)
    png_p = render_heatmap_png(values, "prob", marker_rc=None)
    assert png_q != png_p
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/bin/pytest tests/test_gridmap.py tests/test_heatgrid.py -v -k "precip or score or heatmap"`
Expected: FAIL(with_precip 参数/heatgrid 模块不存在)

- [ ] **Step 3: 实现 gridmap 扩展**

fetch_cloud_grid 签名加 `with_precip: bool = False`,函数内:

```python
    layers = LAYERS + ("precip",) if with_precip else LAYERS
    values: dict[str, list] = {k: [] for k in layers}
```

hourly 参数按需拼接:

```python
            "hourly": "cloud_cover_high,cloud_cover_mid,cloud_cover_low"
                      + (",precipitation" if with_precip else ""),
```

循环取值处,LAYERS 部分照旧,追加:

```python
            if with_precip:
                col = hourly.get("precipitation")
                values["precip"].append(col[idx] if idx is not None and col else None)
```

返回的 dict 推导把 `LAYERS` 换成 `layers`。

- [ ] **Step 4: 实现 heatgrid.py**

```python
"""热力图:网格逐格规则分 + 平滑(无分块无锯齿)PNG 渲染(spec §2 heatmap)。

概率图暖色(米→琥珀→红)、质量图紫色系;双三次插值放大,无瓦片边界。
"""
from io import BytesIO

import numpy as np
from PIL import Image, ImageDraw

from skyfire.percent import baseline_percent
from skyfire.scoring.firecloud import FireCloudInputs, fire_cloud_score

_SCALE = 48                       # 13x9 格 → 624x432 px
_STOPS = {
    "prob": [(0xFA, 0xEE, 0xDA), (0xFA, 0xC7, 0x75), (0xEF, 0x9F, 0x27),
             (0xBA, 0x75, 0x17), (0xE2, 0x4B, 0x4A)],
    "quality": [(0xEE, 0xED, 0xFE), (0xCE, 0xCB, 0xF6), (0xAF, 0xA9, 0xEC),
                (0x7F, 0x77, 0xDD), (0x53, 0x4A, 0xB7)],
}


def score_grids(cloud: dict, confidence: str) -> dict[str, list[list[int]]]:
    """逐格 firecloud 规则分 → 概率%/质量% 两张数值网格。

    概率端经 baseline_percent(含格点云量甜区修正,cloud=该格总云近似
    high+mid+low 截断 100);channel/aod 无格点数据,置中性。缺数据格记 0。
    """
    rows, cols = len(cloud["high"]), len(cloud["high"][0])
    prob = [[0] * cols for _ in range(rows)]
    quality = [[0] * cols for _ in range(rows)]
    for r in range(rows):
        for c in range(cols):
            h, m, low = cloud["high"][r][c], cloud["mid"][r][c], cloud["low"][r][c]
            if h is None:
                continue
            p = (cloud.get("precip") or [[0] * cols] * rows)[r][c] or 0
            score = fire_cloud_score(FireCloudInputs(
                cloud_high=h, cloud_mid=m or 0, cloud_low=low or 0,
                precipitation=p, aod=None, channel=[])).score
            total = min(100.0, (h or 0) + (m or 0) + (low or 0))
            pr, qu = baseline_percent(score, confidence, None, total)
            prob[r][c], quality[r][c] = pr, qu
    return {"prob": prob, "quality": quality}


def render_heatmap_png(values: list[list[int]], kind: str,
                       marker_rc: tuple[float, float] | None) -> bytes:
    """数值网格(0-100)→ 平滑渐变 PNG bytes。

    双三次插值放大(无分块无锯齿,用户 2026-07-07 拍板)→ 色带 LUT 上色
    → 可选城市点标(双圈,marker_rc 为小数行列坐标)。
    """
    arr = np.asarray(values, dtype=np.float32)
    rows, cols = arr.shape
    small = Image.fromarray(np.clip(arr, 0, 100).astype(np.uint8), mode="L")
    big = small.resize((cols * _SCALE, rows * _SCALE), Image.BICUBIC)
    v = np.asarray(big, dtype=np.float32) / 100.0
    stops = np.asarray(_STOPS[kind], dtype=np.float32)
    pos = np.linspace(0.0, 1.0, len(stops))
    rgb = np.stack([np.interp(v, pos, stops[:, i]) for i in range(3)], axis=-1)
    img = Image.fromarray(rgb.astype(np.uint8), mode="RGB")
    if marker_rc is not None:
        d = ImageDraw.Draw(img)
        y, x = marker_rc[0] * _SCALE, marker_rc[1] * _SCALE
        d.ellipse([x - 7, y - 7, x + 7, y + 7], outline=(28, 39, 51), width=3)
        d.ellipse([x - 2, y - 2, x + 2, y + 2], fill=(28, 39, 51))
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
```

- [ ] **Step 5: 跑测试确认通过 + 全量**

Run: `.venv/bin/pytest tests/test_gridmap.py tests/test_heatgrid.py -v` 然后 `.venv/bin/pytest -q`
Expected: 全 PASS;全量 208(203+5)

- [ ] **Step 6: Commit**

```bash
git add skyfire/src/skyfire/gridmap.py skyfire/src/skyfire/heatgrid.py skyfire/tests/test_gridmap.py skyfire/tests/test_heatgrid.py
git commit -m "feat(skyfire): heatgrid 逐格规则分+平滑热力图渲染;gridmap 网格拉取支持降水层"
```

---

### Task 3: api.py 骨架 + POST /v1/login + 鉴权依赖

**Files:**
- Create: `skyfire/src/skyfire/api.py`
- Test: `skyfire/tests/test_api.py`

- [ ] **Step 1: 写失败测试**(新建 `tests/test_api.py`)

```python
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
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/bin/pytest tests/test_api.py -v`
Expected: FAIL, `ImportError: cannot import name 'create_app'`

- [ ] **Step 3: 实现 api.py 骨架+login+鉴权**(summary 本任务先返回占位空 dates,Task 4 填充)

```python
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
```

- [ ] **Step 4: 跑测试确认通过 + 全量**

Run: `.venv/bin/pytest tests/test_api.py -v` 然后 `.venv/bin/pytest -q`
Expected: 全 PASS;全量 212(208+4)

- [ ] **Step 5: Commit**

```bash
git add skyfire/src/skyfire/api.py skyfire/tests/test_api.py
git commit -m "feat(skyfire): api 骨架——微信一键登录换会话token + X-Session 鉴权 + CORS"
```

---

### Task 4: GET /v1/summary(日期×朝霞晚霞全量)

**Files:**
- Modify: `skyfire/src/skyfire/api.py`
- Test: `skyfire/tests/test_api.py`

- [ ] **Step 1: 写失败测试**(追加 test_api.py;时间判定用 monkeypatch 注入 now)

```python
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
    assert sunset["latest"]["prob_word"] == "值得留意"
    assert [t["checkpoint"] for t in sunset["trajectory"]] == ["outlook", "c2"]
    assert sunset["per_model"]["gfs_seamless"]["cloud_high"] == 80
    assert sunrise["latest"] is None               # 没喂朝霞数据
    assert data["dates"][1]["label"].startswith("明天")
    assert "peak" in sunset and "-" in sunset["best_window"]
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/bin/pytest tests/test_api.py::test_summary_shape_dates_events_status -v`
Expected: FAIL(dates 为空占位)

- [ ] **Step 3: 实现**

api.py 顶部 import 补:

```python
import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from skyfire.report import _prob_word, _qual_word
from skyfire.suntimes import sun_window
```

模块级(create_app 之外,便于测试打桩):

```python
def _now_local(tz: str) -> datetime:
    return datetime.now(ZoneInfo(tz))
```

create_app 内 summary 实现替换占位:

```python
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
```

- [ ] **Step 4: 跑测试确认通过 + 全量**

Run: `.venv/bin/pytest tests/test_api.py -v` 然后 `.venv/bin/pytest -q`
Expected: 全 PASS;全量 213(212+1)

- [ ] **Step 5: Commit**

```bash
git add skyfire/src/skyfire/api.py skyfire/tests/test_api.py
git commit -m "feat(skyfire): /v1/summary——今天明天×朝霞晚霞,ended判定/轨迹/per_model/口径词后端统一"
```

---

### Task 5: GET /v1/heatmap(平滑 PNG + 30min 缓存)

**Files:**
- Modify: `skyfire/src/skyfire/api.py`
- Test: `skyfire/tests/test_api.py`

- [ ] **Step 1: 写失败测试**(追加 test_api.py)

```python
def _stub_cloud_grid(calls):
    def fake(client, pts, n_rows, n_cols, tz, iso_hour, date=None,
             model="gfs_seamless", with_precip=False):
        calls.append(iso_hour)
        mk = lambda v: [[v] * n_cols for _ in range(n_rows)]
        return {"high": mk(60), "mid": mk(15), "low": mk(5), "precip": mk(0.0)}
    return fake


def test_heatmap_png_and_cache(tmp_path, monkeypatch):
    import skyfire.api as api_mod
    app, db = _make_app(tmp_path, _wx_transport())
    calls = []
    monkeypatch.setattr(api_mod, "fetch_cloud_grid", _stub_cloud_grid(calls))
    api_mod._HEATMAP_CACHE.clear()
    client = TestClient(app)
    token = client.post("/v1/login", json={"code": "abc"}).json()["token"]
    hdr = {"X-Session": token}
    url = "/v1/heatmap?city=beijing&event=sunset_glow&date=2026-07-07&kind=prob"
    r = client.get(url, headers=hdr)
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/png"
    assert r.content[:8] == b"\x89PNG\r\n\x1a\n"
    r2 = client.get(url, headers=hdr)
    assert r2.status_code == 200 and len(calls) == 1     # 缓存命中,不再拉网格
    client.get(url.replace("kind=prob", "kind=quality"), headers=hdr)
    assert len(calls) == 2                                # kind 不同重新算


def test_heatmap_bad_kind_422(tmp_path):
    app, _ = _make_app(tmp_path, _wx_transport())
    client = TestClient(app)
    token = client.post("/v1/login", json={"code": "abc"}).json()["token"]
    r = client.get("/v1/heatmap?city=beijing&event=sunset_glow"
                   "&date=2026-07-07&kind=nope", headers={"X-Session": token})
    assert r.status_code == 422


def test_heatmap_upstream_failure_503(tmp_path, monkeypatch):
    import httpx as _hx
    import skyfire.api as api_mod

    def boom(*a, **k):
        raise _hx.ConnectError("net down")

    app, _ = _make_app(tmp_path, _wx_transport())
    monkeypatch.setattr(api_mod, "fetch_cloud_grid", boom)
    api_mod._HEATMAP_CACHE.clear()
    client = TestClient(app)
    token = client.post("/v1/login", json={"code": "abc"}).json()["token"]
    r = client.get("/v1/heatmap?city=beijing&event=sunset_glow"
                   "&date=2026-07-07&kind=prob", headers={"X-Session": token})
    assert r.status_code == 503
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/bin/pytest tests/test_api.py -v -k heatmap`
Expected: FAIL(端点不存在)

- [ ] **Step 3: 实现**

api.py 顶部 import 补:

```python
import time

from fastapi import Response

from skyfire.gridmap import DEFAULT_BBOX, DEFAULT_STEP, fetch_cloud_grid, grid_points
from skyfire.heatgrid import render_heatmap_png, score_grids
from skyfire.suntimes import nearest_iso_hour
```

模块级:

```python
_HEATMAP_CACHE: dict[tuple, tuple[float, bytes]] = {}
_HEATMAP_TTL = 1800.0
```

create_app 内新增端点:

```python
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
```

- [ ] **Step 4: 跑测试确认通过 + 全量**

Run: `.venv/bin/pytest tests/test_api.py -v` 然后 `.venv/bin/pytest -q`
Expected: 全 PASS;全量 216(213+3)

- [ ] **Step 5: Commit**

```bash
git add skyfire/src/skyfire/api.py skyfire/tests/test_api.py
git commit -m "feat(skyfire): /v1/heatmap——逐格规则分平滑PNG(prob暖色/quality紫),30min内存缓存,503降级"
```

---

### Task 6: skyfire serve 命令

**Files:**
- Modify: `skyfire/src/skyfire/cli.py`(latest 命令之后)
- Test: `skyfire/tests/test_cli.py`

- [ ] **Step 1: 写失败测试**(追加 test_cli.py)

```python
def test_serve_invokes_uvicorn(monkeypatch, tmp_path):
    import skyfire.cli as cli
    captured = {}

    def fake_run(app, host, port):
        captured.update(host=host, port=port, app=app)

    monkeypatch.setattr("uvicorn.run", fake_run)
    result = runner.invoke(app, ["serve", "--db", str(tmp_path / "t.db"),
                                 "--port", "8123"])
    assert result.exit_code == 0
    assert captured["port"] == 8123 and captured["host"] == "0.0.0.0"
    assert captured["app"].title == "skyfire api"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/bin/pytest tests/test_cli.py -k serve -v`
Expected: FAIL(命令不存在)

- [ ] **Step 3: 实现**(cli.py,latest 命令之后;DEFAULT_WECHAT 常量放 DEFAULT_NOTIFY 旁)

常量区(现有 DEFAULT_NOTIFY 附近)加:

```python
DEFAULT_WECHAT = Path(__file__).parent.parent.parent / "config" / "wechat.local.yaml"
```

命令:

```python
@app.command()
def serve(
    host: str = typer.Option("0.0.0.0", help="0.0.0.0=局域网可访问"),
    port: int = typer.Option(8000),
    config: Path = typer.Option(DEFAULT_CONFIG),
    db: Path = typer.Option(DEFAULT_DB),
    wechat_config: Path = typer.Option(DEFAULT_WECHAT),
):
    """起小程序只读 API(uvicorn;自用局域网,鉴权=微信登录token)。"""
    import uvicorn

    from skyfire.api import create_app
    api = create_app(db_path=db, config_path=config, wechat_path=wechat_config)
    typer.echo(f"skyfire api → http://{host}:{port}(开发者工具用 127.0.0.1,"
               f"真机用本机局域网 IP)")
    uvicorn.run(api, host=host, port=port)
```

- [ ] **Step 4: 跑测试确认通过 + 全量**

Run: `.venv/bin/pytest tests/test_cli.py -v` 然后 `.venv/bin/pytest -q`
Expected: 全 PASS;全量 217(216+1)

- [ ] **Step 5: Commit**

```bash
git add skyfire/src/skyfire/cli.py skyfire/tests/test_cli.py
git commit -m "feat(skyfire): serve 命令——uvicorn 起小程序只读 API"
```

---

### Task 7: 全量回归 + 真跑冒烟 + 合并

- [ ] **Step 1: 全量测试**

Run: `.venv/bin/pytest -q`
Expected: 217 passed

- [ ] **Step 2: 真跑冒烟**(后台起服务,curl 验证;无微信凭证时 login 应 503——预期,summary/heatmap 用直插 token 验证)

```bash
.venv/bin/skyfire serve --port 8801 &
sleep 2
curl -s -X POST localhost:8801/v1/login -H 'content-type: application/json' -d '{"code":"x"}' | grep -q 503 || curl -s -X POST localhost:8801/v1/login -H 'content-type: application/json' -d '{"code":"x"}'
.venv/bin/python -c "
import hashlib, secrets
from skyfire import store
conn = store.connect('data/skyfire.db')
t = secrets.token_urlsafe(16)
store.set_user_token(conn, 'smoke-openid', hashlib.sha256(t.encode()).hexdigest())
print(t)" > /tmp/skyfire_smoke_token
curl -s "localhost:8801/v1/summary?city=beijing" -H "X-Session: $(cat /tmp/skyfire_smoke_token)" | head -c 400; echo
time curl -s -o /tmp/hm.png "localhost:8801/v1/heatmap?city=beijing&event=sunset_glow&date=$(date +%F)&kind=prob" -H "X-Session: $(cat /tmp/skyfire_smoke_token)" && file /tmp/hm.png
kill %1
```

Expected: summary 返回真数据 JSON(今天/明天各 2 事件);hm.png 为 PNG image data 624x432;第二次 curl 同 URL 秒回(缓存)。冒烟后清理:`sqlite3 data/skyfire.db "DELETE FROM users WHERE openid='smoke-openid';"`

- [ ] **Step 3: 按 superpowers:finishing-a-development-branch 收尾**(merge 到 main、全量测试、push、删分支)

---

## 执行后偏差标注(2026-07-07 终审,惯例同上一批)

- Task 2 计划测试笔误:3×3 网格的尺寸断言应为 144×144(计划误写 13×9 网格的 624×432),平滑性采样坐标 (300,216) 越界,执行时改为跨瓦片边界的 (47,72)/(49,72) 并用 NEAREST 对照实验证明测试有杀伤力(NEAREST 差值 105 vs 阈值 40)。
- Task 4 计划断言笔误:prob 62% 按 report.py 现行口径是"机会较大"(<60 才是"值得留意"),测试期望已改,spec §2 示例同步更正。
- Task 7 预期计数 217 实为 220:审查修复新增 3 测试(wx 不可达 503/新库自建表/缓存写清扫)。
- 终审后小修:heatgrid marker 加 0.5 格居中(原偏西北半格≈55km);缓存清扫 del→pop 防并发 KeyError。
- 携带到小程序计划的注意项:前端"数据陈旧"判断用 latest.created_at(summary 顶层 updated_at 是服务器当前时间,永远新鲜)。

## Self-Review 记录

- Spec 覆盖:§1 架构→Task 0/3/6,§2 login→Task 1/3、summary→Task 4、heatmap→Task 2/5,§4 错误处理→Task 3(401/503)/4(422)/5(422/503),§5 测试→各任务;§3 小程序属下一计划。✓
- 类型一致性:create_app(db_path, config_path, wechat_path) 三处一致;fetch_cloud_grid with_precip 契约 Task 2 定义/Task 5 stub 匹配;score_grids/render_heatmap_png 签名 Task 2 定义/Task 5 调用一致;_HEATMAP_CACHE 模块级供测试清理。✓
- 已知取舍:heatmap 的 confidence 取城市级最新预测(缺则 medium)——spec 原文;marker 双圈无文字(v1 简化,mockup 的"北京"字样留待小程序全屏页叠加);grid 13×9(1° 步长)double 立方插值后视觉平滑,若用户嫌粗 v2 降 step。
