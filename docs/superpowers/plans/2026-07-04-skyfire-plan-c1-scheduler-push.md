# Skyfire Plan C-1:定时任务 + 手机推送 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 skyfire 每天在日落/日出前置窗口自动跑预测,把报告推到手机(Bark 或 Server酱),无需人工盯命令行。

**Architecture:** 抽一个可复用的 `compute_prediction`(供 CLI `predict` 与新 `notify`/`tick` 共用,消除重复);报告格式化与推送适配器各自独立纯模块;调度用 launchd 每 30 分钟调 `skyfire tick`,由 `due_events` 按当日太阳窗前置窗口判断该推哪些,`notifications` 表做每日幂等去重。推送失败静默不阻塞(spec 8 一贯风格)。

**Tech Stack:** 沿用 Plan A/B 栈(Python 3.12、httpx、typer、PyYAML、sqlite3);新增无第三方依赖。测试用 httpx.MockTransport,不打真实推送服务。

**已验证的外部事实:**
- Bark:`GET https://api.day.app/{key}/{title}/{body}`(title/body 需 URL 编码),返回 JSON `{"code":200,...}`。
- Server酱³:`POST https://sctapi.ftqq.com/{sendkey}.send`,表单/JSON 带 `title`、`desp`(desp 支持 Markdown 换行),返回 JSON `{"code":0,...}`。

**依赖基线:** Plan A/B 已合入 main,全量 76 tests passed。CLI 现有命令 predict/cloudsea/backtest/init-db/backfill/nowcast。predict 现在把"算分→落库→LLM→echo"耦合在一个函数里(cli.py:70-163),本计划 Task 4 抽出可复用核心。store.init_db 用 `CREATE TABLE IF NOT EXISTS`(store.py:63-65),新增表安全。

**环境注意(执行者必读):** venv 在 `skyfire/.venv`(Python 3.12,uv 装于 `/Users/feitong/.local/share/uv/.../python3.12`);跑测试 `cd /Users/feitong/photo-app/skyfire && .venv/bin/pytest -v`;绝不 `git add -A`;测试与规格矛盾报 BLOCKED,不得自行改断言或发明逻辑。

## File Structure

```
skyfire/src/skyfire/
├── store.py           # 【改】追加 notifications 表 + was_pushed/mark_pushed
├── push.py            # 手机推送适配器(Bark + Server酱,httpx 可注入,失败静默)
├── notifyconf.py      # 推送配置加载(gitignored YAML:provider + key)
├── engine.py          # PredictionResult + compute_prediction(predict/notify 共用)
├── report.py          # format_report(result) → (title, body) 纯函数
├── schedule.py        # due_events(cities, now, lead_min) 打点判断(纯函数)
└── cli.py             # 【改】predict 复用 engine;新增 notify / tick 命令
skyfire/config/
└── notify.example.yaml  # 配置样例(真实 notify.local.yaml 被 gitignore)
skyfire/deploy/
└── com.skyfire.tick.plist.example  # launchd 模板
skyfire/.gitignore     # 【改】加 config/notify.local.yaml
tests/  test_push.py test_notifyconf.py test_engine.py test_report.py
        test_schedule.py (+ 扩展 test_store.py / test_cli.py)
```

---

### Task 1: notifications 去重表 + store helpers

**Files:**
- Modify: `skyfire/src/skyfire/store.py`(SCHEMA 追加表 + 两函数)
- Test: `skyfire/tests/test_store.py`(追加)

- [ ] **Step 1: 追加失败测试**——在 `skyfire/tests/test_store.py` 末尾追加:

```python
def test_notifications_dedup(tmp_path):
    conn = _db(tmp_path)
    assert store.was_pushed(conn, "2026-07-04", "beijing", "sunset_glow") is False
    store.mark_pushed(conn, "2026-07-04", "beijing", "sunset_glow")
    assert store.was_pushed(conn, "2026-07-04", "beijing", "sunset_glow") is True
    # 不同日期/城市/天象互不影响
    assert store.was_pushed(conn, "2026-07-05", "beijing", "sunset_glow") is False
    assert store.was_pushed(conn, "2026-07-04", "shanghai", "sunset_glow") is False
    # 重复 mark 幂等(不抛异常)
    store.mark_pushed(conn, "2026-07-04", "beijing", "sunset_glow")
    assert store.was_pushed(conn, "2026-07-04", "beijing", "sunset_glow") is True
```

- [ ] **Step 2: 运行确认失败**

Run: `cd /Users/feitong/photo-app/skyfire && .venv/bin/pytest tests/test_store.py::test_notifications_dedup -v`
Expected: FAIL — `AttributeError: module 'skyfire.store' has no attribute 'was_pushed'`

- [ ] **Step 3: 实现**

在 `store.py` 的 `SCHEMA` 字符串末尾(`users` 表 CREATE 之后、`"""` 之前)追加:

```sql
CREATE TABLE IF NOT EXISTS notifications (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  date TEXT NOT NULL,
  city TEXT NOT NULL,
  event TEXT NOT NULL,
  pushed_at TEXT DEFAULT (datetime('now')),
  UNIQUE(date, city, event)
);
```

在 store.py 末尾追加两函数:

```python
def was_pushed(conn, date: str, city: str, event: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM notifications WHERE date=? AND city=? AND event=?",
        (date, city, event),
    ).fetchone()
    return row is not None


def mark_pushed(conn, date: str, city: str, event: str) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO notifications (date, city, event) VALUES (?, ?, ?)",
        (date, city, event),
    )
    conn.commit()
```

- [ ] **Step 4: 运行确认通过**

Run: `cd /Users/feitong/photo-app/skyfire && .venv/bin/pytest tests/test_store.py -v`
Expected: PASS(既有 store 测试 + 新 1 测全绿)。全量 `.venv/bin/pytest -q` 应 77 passed。

- [ ] **Step 5: 提交**

```bash
cd /Users/feitong/photo-app
git add skyfire/src/skyfire/store.py skyfire/tests/test_store.py
git commit -m "feat(skyfire): notifications 去重表 + was_pushed/mark_pushed"
```

---

### Task 2: 手机推送适配器

**Files:**
- Create: `skyfire/src/skyfire/push.py`
- Test: `skyfire/tests/test_push.py`

- [ ] **Step 1: 写失败测试**——`skyfire/tests/test_push.py`:

```python
import httpx

from skyfire.push import push


def _client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_push_bark_hits_key_url_and_encodes():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        return httpx.Response(200, json={"code": 200, "message": "success"})

    ok = push("晚霞 7.5 分", "北京今晚值得出动", {"provider": "bark", "key": "ABC123"},
              client=_client(handler))
    assert ok is True
    assert seen["url"].startswith("https://api.day.app/ABC123/")
    # 中文经 URL 编码(不出现原始汉字)
    assert "晚霞" not in seen["url"]
    assert "%" in seen["url"]


def test_push_serverchan_posts_title_desp():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["body"] = request.content.decode()
        return httpx.Response(200, json={"code": 0, "message": "success"})

    ok = push("朝霞 3 分", "东边通道堵", {"provider": "serverchan", "key": "SCT999"},
              client=_client(handler))
    assert ok is True
    assert seen["url"] == "https://sctapi.ftqq.com/SCT999.send"
    assert "title=" in seen["body"] and "desp=" in seen["body"]


def test_push_returns_false_on_http_error_not_raise():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    assert push("t", "b", {"provider": "bark", "key": "K"}, client=_client(handler)) is False


def test_push_returns_false_on_provider_error_code():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"code": 400, "message": "bad key"})

    assert push("t", "b", {"provider": "bark", "key": "K"}, client=_client(handler)) is False


def test_push_unknown_provider_returns_false():
    assert push("t", "b", {"provider": "carrier_pigeon", "key": "K"}, client=None) is False
```

- [ ] **Step 2: 运行确认失败**

Run: `cd /Users/feitong/photo-app/skyfire && .venv/bin/pytest tests/test_push.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'skyfire.push'`

- [ ] **Step 3: 实现**——`skyfire/src/skyfire/push.py`:

```python
"""手机推送适配器(spec 7 推送渠道:自用阶段手机推送服务)。

支持 Bark 与 Server酱³,配置选一。任何失败(未知 provider/网络/服务端错误码)
→ 返回 False,绝不抛异常(spec 8:推送失败不阻塞预测)。
"""
from urllib.parse import quote

import httpx

BARK_BASE = "https://api.day.app"
SERVERCHAN_BASE = "https://sctapi.ftqq.com"


def push(title: str, body: str, config: dict, client: httpx.Client | None = None) -> bool:
    provider = config.get("provider")
    key = config.get("key", "")
    owns_client = client is None
    if client is None:
        client = httpx.Client(timeout=15)
    try:
        if provider == "bark":
            # safe='' 连 '/' 也编码:报告正文含 "7.5/10" 等,否则 Bark 会把 '/' 当路径段
            resp = client.get(
                f"{BARK_BASE}/{key}/{quote(title, safe='')}/{quote(body, safe='')}")
            resp.raise_for_status()
            return resp.json().get("code") == 200
        if provider == "serverchan":
            resp = client.post(f"{SERVERCHAN_BASE}/{key}.send",
                               data={"title": title, "desp": body})
            resp.raise_for_status()
            return resp.json().get("code") == 0
        return False
    except Exception:
        return False
    finally:
        if owns_client:
            client.close()
```

- [ ] **Step 4: 运行确认通过**

Run: `cd /Users/feitong/photo-app/skyfire && .venv/bin/pytest tests/test_push.py -v`
Expected: PASS (5 passed)。全量 `.venv/bin/pytest -q` 应 82 passed。

- [ ] **Step 5: 提交**

```bash
cd /Users/feitong/photo-app
git add skyfire/src/skyfire/push.py skyfire/tests/test_push.py
git commit -m "feat(skyfire): Bark/Server酱 手机推送适配器(失败静默)"
```

---

### Task 3: 推送配置加载 + gitignore

**Files:**
- Create: `skyfire/src/skyfire/notifyconf.py`
- Create: `skyfire/config/notify.example.yaml`
- Modify: `skyfire/.gitignore`
- Test: `skyfire/tests/test_notifyconf.py`

- [ ] **Step 1: 写失败测试**——`skyfire/tests/test_notifyconf.py`:

```python
import pytest

from skyfire.notifyconf import load_notify_config


def test_load_valid(tmp_path):
    p = tmp_path / "notify.yaml"
    p.write_text("provider: bark\nkey: ABC123\nlead_minutes: 150\n", encoding="utf-8")
    cfg = load_notify_config(p)
    assert cfg == {"provider": "bark", "key": "ABC123", "lead_minutes": 150}


def test_load_defaults_lead_minutes(tmp_path):
    p = tmp_path / "notify.yaml"
    p.write_text("provider: serverchan\nkey: SCT9\n", encoding="utf-8")
    cfg = load_notify_config(p)
    assert cfg["lead_minutes"] == 120   # 默认日落/日出前 2 小时


def test_load_missing_file_returns_none(tmp_path):
    assert load_notify_config(tmp_path / "nope.yaml") is None


def test_load_rejects_bad_provider(tmp_path):
    p = tmp_path / "notify.yaml"
    p.write_text("provider: telegram\nkey: X\n", encoding="utf-8")
    with pytest.raises(ValueError, match="provider"):
        load_notify_config(p)
```

- [ ] **Step 2: 运行确认失败**

Run: `cd /Users/feitong/photo-app/skyfire && .venv/bin/pytest tests/test_notifyconf.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'skyfire.notifyconf'`

- [ ] **Step 3: 实现**

`skyfire/src/skyfire/notifyconf.py`:

```python
"""推送配置加载(gitignored 本地文件,含密钥)。"""
from pathlib import Path

import yaml

VALID_PROVIDERS = ("bark", "serverchan")
DEFAULT_LEAD_MINUTES = 120


def load_notify_config(path: Path) -> dict | None:
    """读取推送配置。文件不存在返回 None(视为未配置,静默跳过推送)。"""
    if not Path(path).exists():
        return None
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    provider = data.get("provider")
    if provider not in VALID_PROVIDERS:
        raise ValueError(f"未知 provider {provider!r},可用: {', '.join(VALID_PROVIDERS)}")
    return {"provider": provider, "key": str(data.get("key", "")),
            "lead_minutes": int(data.get("lead_minutes", DEFAULT_LEAD_MINUTES))}
```

`skyfire/config/notify.example.yaml`:

```yaml
# 复制为 notify.local.yaml 并填入真实密钥(该文件已 gitignore)
provider: bark        # bark | serverchan
key: YOUR_KEY_HERE    # Bark 的 device key,或 Server酱 的 sendkey
lead_minutes: 120     # 日落/日出前多少分钟推送(默认 120)
```

在 `skyfire/.gitignore` 末尾追加一行:

```
config/notify.local.yaml
```

- [ ] **Step 4: 运行确认通过**

Run: `cd /Users/feitong/photo-app/skyfire && .venv/bin/pytest tests/test_notifyconf.py -v`
Expected: PASS (4 passed)。全量 `.venv/bin/pytest -q` 应 86 passed。

- [ ] **Step 5: 提交**

```bash
cd /Users/feitong/photo-app
git add skyfire/src/skyfire/notifyconf.py skyfire/config/notify.example.yaml skyfire/.gitignore skyfire/tests/test_notifyconf.py
git commit -m "feat(skyfire): 推送配置加载 + 样例 + gitignore 本地密钥"
```

---

### Task 4: engine——可复用预测计算 + 重构 predict

**Files:**
- Create: `skyfire/src/skyfire/engine.py`
- Modify: `skyfire/src/skyfire/cli.py`(predict 改为复用 engine)
- Test: `skyfire/tests/test_engine.py`

**说明:** 现有 `predict`(cli.py:70-163)把"算分→落库→LLM"和"echo"耦合。本任务抽出 `compute_prediction` 返回结构化结果,predict 改为"调 compute → 用原样 echo 串输出"。**predict 的 echo 文案与既有 cli 测试断言必须完全不变**(test_predict_prints_card_and_saves_case 等);LLM 由 engine 内部完成并回填 result.llm。

- [ ] **Step 1: 写失败测试**——`skyfire/tests/test_engine.py`(复用 test_cli 的 fake transport 思路,内联一份):

```python
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
    # 落库:案例 + 快照
    case = conn.execute("SELECT rule_score FROM cases WHERE city='beijing'").fetchone()
    assert case[0] == r.index
    snaps = store.get_snapshots(conn, conn.execute("SELECT id FROM cases").fetchone()[0])
    assert {s["model"] for s in snaps} == set(MODELS)


def test_compute_prediction_raises_on_all_models_missing(tmp_path):
    from datetime import date
    conn = store.connect(tmp_path / "t.db")
    store.init_db(conn)
    city = load_cities(CONFIG)["beijing"]

    def empty(request):  # 预报缺 cloud_cover_high → 全模式无分
        times = ["2026-07-03T19:00"]
        if request.url.host == httpx.URL(AIR_QUALITY_URL).host:
            return httpx.Response(200, json={"hourly": {"time": times,
                                                        "aerosol_optical_depth": [0.2]}})
        if "," in str(request.url.params.get("latitude", "")):
            return httpx.Response(200, json=[{"hourly": {"time": times,
                "cloud_cover": [15], "cloud_cover_low": [5]}}] * 8)
        return httpx.Response(200, json={"hourly": {"time": times}})

    client = httpx.Client(transport=httpx.MockTransport(empty))
    import pytest
    with pytest.raises(store.NoForecastData if hasattr(store, "NoForecastData") else ValueError):
        compute_prediction(conn, client, city, "beijing", "sunset_glow",
                           date(2026, 7, 3), run_llm=False)
```

**注意:** 上面第二个测试的异常类型用 `ValueError`(下方实现里 compute_prediction 全模式无数据时 `raise ValueError("所有模式数据缺失")`)。把测试里 `store.NoForecastData if ... else ValueError` 简化为直接 `pytest.raises(ValueError)`——实现者请在写测试时就用 `ValueError`,不要引入自定义异常类。

- [ ] **Step 2: 运行确认失败**

Run: `cd /Users/feitong/photo-app/skyfire && .venv/bin/pytest tests/test_engine.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'skyfire.engine'`

- [ ] **Step 3: 实现 engine.py**

`skyfire/src/skyfire/engine.py`:

```python
"""可复用的预测计算(predict / notify / tick 共用,消除重复)。

compute_prediction:算分 + 落库 + 可选 LLM,返回结构化结果供上层 echo/格式化/推送。
HTTP 失败向上抛 httpx.HTTPError;全模式无数据抛 ValueError——由调用方决定如何呈现。
"""
from dataclasses import dataclass
from datetime import date, datetime

import httpx

from skyfire import store
from skyfire.config import City
from skyfire.consensus import consensus
from skyfire.geo import channel_points
from skyfire.llm import LlmResult, interpret
from skyfire.openmeteo import fetch_aod_at, fetch_channel_profile, fetch_point_forecast
from skyfire.rag import factor_vector, similar_cases_from
from skyfire.scoring.firecloud import FireCloudInputs, fire_cloud_score
from skyfire.suntimes import sun_window


@dataclass
class PredictionResult:
    city_name: str
    event: str
    day: date
    index: float
    confidence: str
    spread: float
    per_model: dict[str, float]
    blocked_points: int
    channel_factor: float
    aod: float | None
    channel_empty: bool
    peak: datetime
    azimuth: float
    llm: LlmResult | None


def compute_prediction(conn, client: httpx.Client, city: City, city_key: str,
                       event: str, day: date, run_llm: bool = True) -> PredictionResult:
    win = sun_window(city.lat, city.lon, city.timezone, day, event)
    iso_hour = win.peak.strftime("%Y-%m-%dT%H:00")
    geo_pts = channel_points(city.lat, city.lon, win.azimuth_deg)
    forecasts = fetch_point_forecast(client, city.lat, city.lon, city.timezone)
    aod = fetch_aod_at(client, city.lat, city.lon, city.timezone, iso_hour)
    channel = fetch_channel_profile(client, geo_pts, city.timezone, iso_hour)
    channel_empty = all(p.cloud_low is None and p.cloud_total is None for p in channel)

    per_model: dict[str, float] = {}
    details = {}
    for fc in forecasts:
        h = fc.at(iso_hour)
        if h is None or h.cloud_high is None:
            continue
        r = fire_cloud_score(FireCloudInputs(
            cloud_high=h.cloud_high, cloud_mid=h.cloud_mid or 0,
            cloud_low=h.cloud_low or 0, precipitation=h.precipitation or 0,
            aod=aod, channel=channel,
        ))
        per_model[fc.model] = r.score
        details[fc.model] = r
    if not per_model:
        raise ValueError("所有模式数据缺失")

    cons = consensus(per_model)
    first = next(iter(details.values()))
    case_id = store.upsert_case(conn, str(day), city_key, event,
                                rule_score=cons.index, confidence=cons.confidence,
                                source="auto")
    for fc in forecasts:
        h = fc.at(iso_hour)
        if h is None:
            continue
        store.add_snapshot(conn, case_id, fc.model, {
            "hour": iso_hour, "cloud_high": h.cloud_high, "cloud_mid": h.cloud_mid,
            "cloud_low": h.cloud_low, "cloud_cover": h.cloud_cover,
            "rh_2m": h.rh_2m, "precipitation": h.precipitation, "aod": aod,
            "channel": [{"km": p.dist_km, "low": p.cloud_low, "total": p.cloud_total}
                        for p in channel],
            "azimuth": round(win.azimuth_deg, 1),
        })

    llm_result = None
    if run_llm:
        gfs = next((fc for fc in forecasts if fc.model == "gfs_seamless"), forecasts[0])
        h0 = gfs.at(iso_hour)
        today = {"date": str(day), "event": event, "rule_score": cons.index,
                 "confidence": cons.confidence,
                 "payload": {"cloud_high": h0.cloud_high if h0 else None,
                             "cloud_mid": h0.cloud_mid if h0 else None,
                             "cloud_low": h0.cloud_low if h0 else None,
                             "rh_2m": h0.rh_2m if h0 else None, "aod": aod,
                             "channel": [{"km": p.dist_km, "low": p.cloud_low,
                                          "total": p.cloud_total} for p in channel],
                             "hour": iso_hour}}
        cases = store.cases_with_snapshot(conn, city_key, event, model="gfs_seamless")
        cases = [x for x in cases if x["case_id"] != case_id]
        similar = similar_cases_from(cases, factor_vector(today["payload"]), k=3)
        frames = [__import__("pathlib").Path(f["path"]) for f in store.get_frames(conn, case_id)
                  if __import__("pathlib").Path(f["path"]).exists()]
        llm_result = interpret(today, similar, frames)
        if llm_result is not None:
            store.set_llm_score(conn, case_id, llm_result.llm_score)

    return PredictionResult(
        city_name=city.name, event=event, day=day, index=cons.index,
        confidence=cons.confidence, spread=cons.spread, per_model=cons.per_model,
        blocked_points=first.blocked_points, channel_factor=first.channel_factor,
        aod=aod, channel_empty=channel_empty, peak=win.peak, azimuth=win.azimuth_deg,
        llm=llm_result)
```

**清理 `__import__("pathlib")` 写法:** 上面为压缩示意用了 `__import__`,实现者请在 engine.py 顶部正常 `from pathlib import Path`,并把两处 `__import__("pathlib").Path` 改成 `Path`。

- [ ] **Step 4: 重构 cli.py 的 predict 复用 engine**

把 predict 函数体(cli.py:79-162,从 `"""火烧云指数..."""` 之后到函数结束)替换为:

```python
    """火烧云指数:多模式评分 + 一致性置信度,并归档快照。"""
    cities = load_cities(config)
    if city not in cities:
        typer.echo(f"错误:未知城市 {city!r},可用: {', '.join(cities)}", err=True)
        raise typer.Exit(1)
    c = cities[city]
    day = _parse_date(date, date_type.today())
    conn = _open_db(db)
    client = _make_client()
    try:
        r = compute_prediction(conn, client, c, city, event, day, run_llm=not no_llm)
    except httpx.HTTPError as e:
        typer.echo(f"错误:Open-Meteo 请求失败({e.__class__.__name__}: {e}),请稍后重试", err=True)
        raise typer.Exit(1)
    except ValueError:
        typer.echo("错误:所有模式数据缺失,无法出分", err=True)
        raise typer.Exit(1)

    event_zh = "晚霞" if event == "sunset_glow" else "朝霞"
    typer.echo(f"⚡ {day} {event_zh} — {r.city_name}")
    typer.echo(f"火烧云指数: {r.index}/10  置信度: {CONF_ZH[r.confidence]}  分歧: {r.spread}")
    typer.echo("  " + "  ".join(f"{m.split('_')[0].upper()} {s}" for m, s in r.per_model.items()))
    if r.channel_empty:
        typer.echo("警告: 通道数据缺失,评分未含通道透光校验(置信度参考价值打折)")
    typer.echo(f"通道: {r.blocked_points} 点受阻 (系数 {r.channel_factor})  AOD: {r.aod}")
    typer.echo(f"{'日落' if event == 'sunset_glow' else '日出'}: {r.peak.strftime('%H:%M')}  方位 {r.azimuth:.0f}°")
    if not no_llm:
        if r.llm is not None:
            typer.echo(f"AI 修正分: {r.llm.llm_score}/10  {r.llm.analysis}")
            typer.echo(f"风险: {r.llm.risks}")
        else:
            typer.echo("AI 解读暂缺(无凭证或调用失败),以上为纯规则分")
```

并在 cli.py 顶部 import 区加 `from skyfire.engine import compute_prediction`。

**删除死代码 `_run_llm`:** 重构后 predict 不再调 `cli._run_llm`(LLM 逻辑已移入 engine),而 `_run_llm` 仅被旧 predict 与即将替换的 test_predict_no_llm_flag_skips_llm 使用——两者都在本任务改掉。先用 `grep -n "_run_llm" src/skyfire/cli.py tests/` 确认无其他引用,然后删除 cli.py 中整个 `_run_llm` 函数定义。若 grep 发现别处仍引用,则保留并在报告中说明(报 DONE_WITH_CONCERNS)。删除后一并检查 `_run_llm` 曾用到但现在无处引用的 import(rag/llm_mod/Path 等)是否仍被 cli 其他命令(nowcast/backfill)使用——nowcast 用 store/himawari/cloudiness/drift/nowcast,不用 rag/llm_mod;故 cli.py 里的 `from skyfire import rag`、`from skyfire import llm as llm_mod` 若删 `_run_llm` 后无引用,一并删除(engine.py 自己 import 这些)。用 `.venv/bin/python -m pyflakes src/skyfire/cli.py` 确认无未使用 import。

- [ ] **Step 5: 运行确认通过(engine 测试 + cli 既有测试无回归)**

Run: `cd /Users/feitong/photo-app/skyfire && .venv/bin/pytest tests/test_engine.py tests/test_cli.py -v`
Expected: PASS(engine 2 测 + cli 既有测试全绿——尤其 test_predict_prints_card_and_saves_case / test_predict_rejects_bad_date / test_predict_rejects_unknown_city / test_predict_no_llm_flag_skips_llm 无回归)。

**注意 test_predict_no_llm_flag_skips_llm:** 该测试 monkeypatch `cli._run_llm` 做 spy。重构后 predict 不再调 `cli._run_llm`(LLM 移进 engine.compute_prediction 内部),故该 spy 测试会失效。**这是预期的行为变更**——重构后 predict 通过 `run_llm=not no_llm` 传参控制。执行者需同步更新该测试为:monkeypatch `cli.compute_prediction` 记录收到的 `run_llm` 实参,断言 `--no-llm` 时为 False、默认 True。改写如下(替换 test_cli.py 中原 test_predict_no_llm_flag_skips_llm 整个函数):

```python
def test_predict_no_llm_flag_controls_run_llm(tmp_path, monkeypatch):
    import skyfire.cli as cli
    from skyfire.engine import PredictionResult
    from datetime import date, datetime
    seen = {}

    def _fake_compute(conn, client, c, city, event, day, run_llm=True):
        seen["run_llm"] = run_llm
        return PredictionResult(city_name="北京", event=event, day=day, index=5.0,
                                confidence="high", spread=0.0,
                                per_model={"gfs_seamless": 5.0}, blocked_points=0,
                                channel_factor=1.0, aod=0.2, channel_empty=False,
                                peak=datetime(2026, 7, 3, 19, 46), azimuth=300.0, llm=None)

    monkeypatch.setattr(cli, "_make_client",
                        lambda: httpx.Client(transport=_fake_transport()))
    monkeypatch.setattr(cli, "compute_prediction", _fake_compute)
    db = tmp_path / "sky.db"
    r1 = runner.invoke(app, ["predict", "--city", "beijing", "--event", "sunset_glow",
                             "--date", "2026-07-03", "--db", str(db), "--no-llm"])
    assert r1.exit_code == 0, r1.output
    assert seen["run_llm"] is False
    r2 = runner.invoke(app, ["predict", "--city", "beijing", "--event", "sunset_glow",
                             "--date", "2026-07-03", "--db", str(db)])
    assert r2.exit_code == 0, r2.output
    assert seen["run_llm"] is True
```

- [ ] **Step 6: 全量确认无回归**

Run: `cd /Users/feitong/photo-app/skyfire && .venv/bin/pytest -q`
Expected: PASS(约 88 passed:86 + engine 2;test_cli 数量不变——删 1 加 1)。

- [ ] **Step 7: 提交**

```bash
cd /Users/feitong/photo-app
git add skyfire/src/skyfire/engine.py skyfire/src/skyfire/cli.py skyfire/tests/test_engine.py skyfire/tests/test_cli.py
git commit -m "refactor(skyfire): 抽 compute_prediction,predict 复用;LLM 移入 engine"
```

---

### Task 5: 报告格式化

**Files:**
- Create: `skyfire/src/skyfire/report.py`
- Test: `skyfire/tests/test_report.py`

- [ ] **Step 1: 写失败测试**——`skyfire/tests/test_report.py`:

```python
from datetime import date, datetime

from skyfire.engine import PredictionResult
from skyfire.llm import LlmResult
from skyfire.report import format_report


def _result(**kw):
    base = dict(city_name="北京", event="sunset_glow", day=date(2026, 7, 3),
                index=7.5, confidence="high", spread=0.9,
                per_model={"ecmwf_ifs025": 7.8, "gfs_seamless": 7.2},
                blocked_points=1, channel_factor=0.82, aod=0.3, channel_empty=False,
                peak=datetime(2026, 7, 3, 19, 46), azimuth=301.0, llm=None)
    base.update(kw)
    return PredictionResult(**base)


def test_format_report_title_has_score_and_event():
    title, body = format_report(_result())
    assert "7.5" in title
    assert "晚霞" in title and "北京" in title


def test_format_report_body_has_key_facts():
    title, body = format_report(_result())
    assert "19:46" in body          # 日落时刻
    assert "置信度" in body
    assert "301" in body            # 方位角


def test_format_report_includes_llm_when_present():
    title, body = format_report(_result(llm=LlmResult(
        llm_score=6.5, analysis="通道有低云,较 5-12 那次略差", risks="西侧低云")))
    assert "6.5" in body and "通道有低云" in body


def test_format_report_sunrise_label():
    title, _ = format_report(_result(event="sunrise_glow"))
    assert "朝霞" in title
```

- [ ] **Step 2: 运行确认失败**

Run: `cd /Users/feitong/photo-app/skyfire && .venv/bin/pytest tests/test_report.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'skyfire.report'`

- [ ] **Step 3: 实现**——`skyfire/src/skyfire/report.py`:

```python
"""预测结果 → 推送标题/正文(纯函数,供 notify/tick 用)。"""
from skyfire.engine import PredictionResult

_CONF_ZH = {"high": "高", "medium": "中", "low": "低(模式打架)", "degraded": "降级(数据不全)"}


def format_report(r: PredictionResult) -> tuple[str, str]:
    event_zh = "晚霞" if r.event == "sunset_glow" else "朝霞"
    when_zh = "日落" if r.event == "sunset_glow" else "日出"
    title = f"{event_zh} {r.index}/10 — {r.city_name}"
    lines = [
        f"{r.day} {r.city_name}{event_zh}火烧云指数 {r.index}/10",
        f"置信度: {_CONF_ZH.get(r.confidence, r.confidence)}  模式分歧: {r.spread}",
        "  " + "  ".join(f"{m.split('_')[0].upper()} {s}" for m, s in r.per_model.items()),
        f"通道: {r.blocked_points} 点受阻(系数 {r.channel_factor})  AOD: {r.aod}",
        f"{when_zh}: {r.peak.strftime('%H:%M')}  方位 {r.azimuth:.0f}°",
    ]
    if r.channel_empty:
        lines.append("⚠️ 通道数据缺失,置信度参考价值打折")
    if r.llm is not None:
        lines.append(f"AI 修正分: {r.llm.llm_score}/10  {r.llm.analysis}")
        lines.append(f"风险: {r.llm.risks}")
    return title, "\n".join(lines)
```

- [ ] **Step 4: 运行确认通过**

Run: `cd /Users/feitong/photo-app/skyfire && .venv/bin/pytest tests/test_report.py -v`
Expected: PASS (4 passed)。全量应约 92 passed。

- [ ] **Step 5: 提交**

```bash
cd /Users/feitong/photo-app
git add skyfire/src/skyfire/report.py skyfire/tests/test_report.py
git commit -m "feat(skyfire): 预测结果格式化为推送标题/正文"
```

---

### Task 6: 调度打点判断

**Files:**
- Create: `skyfire/src/skyfire/schedule.py`
- Test: `skyfire/tests/test_schedule.py`

**说明:** `due_events` 是纯函数——给定当前 UTC 时刻、城市字典、前置分钟数,返回"现在落在窗口前置区间内"的 (city_key, event) 列表。tick 命令(Task 7)再用 `store.was_pushed` 过滤已推的。窗口前置区间定义:`0 <= (peak - now) <= lead_minutes`(即日落/日出前 lead_minutes 到日落/日出本身之间),这样 launchd 每 30 分钟一打点,进入区间的首个 tick 即触发,配合 DB 去重保证每日每天象只推一次。

- [ ] **Step 1: 写失败测试**——`skyfire/tests/test_schedule.py`:

```python
from datetime import datetime, timezone
from pathlib import Path

from skyfire.config import load_cities
from skyfire.schedule import due_events

CONFIG = Path(__file__).parent.parent / "config" / "cities.yaml"


def test_due_events_inside_sunset_lead_window():
    cities = load_cities(CONFIG)
    # 北京 2026-06-21 日落约 19:46 CST = 11:46 UTC;取前 2 小时窗口内的 10:30 UTC
    now = datetime(2026, 6, 21, 10, 30, tzinfo=timezone.utc)
    due = due_events(cities, now, lead_minutes=120)
    assert ("beijing", "sunset_glow") in due


def test_due_events_before_window_empty():
    cities = load_cities(CONFIG)
    # 距日落还有 5 小时(06:46 UTC),不在前 2 小时窗口
    now = datetime(2026, 6, 21, 6, 46, tzinfo=timezone.utc)
    due = due_events(cities, now, lead_minutes=120)
    assert ("beijing", "sunset_glow") not in due


def test_due_events_after_peak_empty():
    cities = load_cities(CONFIG)
    # 日落后(12:30 UTC = 20:30 CST),已过峰值
    now = datetime(2026, 6, 21, 12, 30, tzinfo=timezone.utc)
    due = due_events(cities, now, lead_minutes=120)
    assert ("beijing", "sunset_glow") not in due


def test_due_events_matches_sunrise_window():
    cities = load_cities(CONFIG)
    # 北京 2026-06-21 日出约 04:46 CST = 2026-06-20 20:46 UTC;前 2 小时 = 19:30 UTC
    now = datetime(2026, 6, 20, 19, 30, tzinfo=timezone.utc)
    due = due_events(cities, now, lead_minutes=120)
    assert ("beijing", "sunrise_glow") in due
```

- [ ] **Step 2: 运行确认失败**

Run: `cd /Users/feitong/photo-app/skyfire && .venv/bin/pytest tests/test_schedule.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'skyfire.schedule'`

- [ ] **Step 3: 实现**——`skyfire/src/skyfire/schedule.py`:

```python
"""调度打点:判断当前时刻该推哪些城市×天象(spec 5.4 临近/推送窗口)。

纯函数,不碰 DB;去重由调用方用 store.was_pushed 完成。
对每个城市各算今日与明日的日落/日出峰值,取"现在到峰值 <= lead 且 >= 0"者。
跨 UTC 日界的日出用两天候选覆盖。
"""
from datetime import datetime, timedelta, timezone

from skyfire.config import City
from skyfire.suntimes import sun_window

EVENTS = ("sunset_glow", "sunrise_glow")


def due_events(cities: dict[str, City], now: datetime,
               lead_minutes: int = 120) -> list[tuple[str, str]]:
    now_utc = now.astimezone(timezone.utc)
    due: list[tuple[str, str]] = []
    for key, c in cities.items():
        for event in EVENTS:
            # 候选:以城市本地时区的今日与明日各算一次,覆盖 UTC 日界
            for day_offset in (0, 1):
                local_day = (now_utc.astimezone(_tz(c)) + timedelta(days=day_offset)).date()
                win = sun_window(c.lat, c.lon, c.timezone, local_day, event)
                peak_utc = win.peak.astimezone(timezone.utc)
                delta_min = (peak_utc - now_utc).total_seconds() / 60
                if 0 <= delta_min <= lead_minutes:
                    due.append((key, event))
                    break
    return due


def _tz(c: City):
    from zoneinfo import ZoneInfo
    return ZoneInfo(c.timezone)
```

- [ ] **Step 4: 运行确认通过**

Run: `cd /Users/feitong/photo-app/skyfire && .venv/bin/pytest tests/test_schedule.py -v`
Expected: PASS (4 passed)。全量应约 96 passed。

- [ ] **Step 5: 提交**

```bash
cd /Users/feitong/photo-app
git add skyfire/src/skyfire/schedule.py skyfire/tests/test_schedule.py
git commit -m "feat(skyfire): 调度打点判断(日落/日出前置窗口)"
```

---

### Task 7: notify / tick CLI 命令 + launchd 模板

**Files:**
- Modify: `skyfire/src/skyfire/cli.py`(新增 notify / tick 命令 + 默认路径)
- Create: `skyfire/deploy/com.skyfire.tick.plist.example`
- Test: `skyfire/tests/test_cli.py`(追加)

- [ ] **Step 1: 追加失败测试**——在 test_cli.py 末尾追加:

```python
def test_notify_pushes_and_marks(tmp_path, monkeypatch):
    import skyfire.cli as cli
    from skyfire.engine import PredictionResult
    from datetime import date, datetime
    from skyfire import store

    pushed = {}

    def _fake_compute(conn, client, c, city, event, day, run_llm=True):
        return PredictionResult(city_name="北京", event=event, day=day, index=7.5,
                                confidence="high", spread=0.9,
                                per_model={"gfs_seamless": 7.5}, blocked_points=1,
                                channel_factor=0.8, aod=0.3, channel_empty=False,
                                peak=datetime(2026, 7, 4, 19, 46), azimuth=301.0, llm=None)

    def _fake_push(title, body, cfg, client=None):
        pushed["title"] = title
        pushed["body"] = body
        return True

    monkeypatch.setattr(cli, "_make_client", lambda: None)
    monkeypatch.setattr(cli, "compute_prediction", _fake_compute)
    monkeypatch.setattr(cli, "push", _fake_push)

    ncfg = tmp_path / "notify.yaml"
    ncfg.write_text("provider: bark\nkey: K\n", encoding="utf-8")
    db = tmp_path / "sky.db"
    result = runner.invoke(app, ["notify", "--city", "beijing", "--event", "sunset_glow",
                                 "--db", str(db), "--notify-config", str(ncfg)])
    assert result.exit_code == 0, result.output
    assert "7.5" in pushed["title"] and "晚霞" in pushed["title"]
    # 落库去重标记
    conn = store.connect(db)
    today = str(date.today())
    assert store.was_pushed(conn, today, "beijing", "sunset_glow") is True


def test_notify_no_config_reports_and_exits(tmp_path, monkeypatch):
    import skyfire.cli as cli
    monkeypatch.setattr(cli, "_make_client", lambda: None)
    result = runner.invoke(app, ["notify", "--city", "beijing", "--event", "sunset_glow",
                                 "--db", str(tmp_path / "d.db"),
                                 "--notify-config", str(tmp_path / "nope.yaml")])
    assert result.exit_code != 0
    assert "未配置" in result.output


def test_tick_pushes_due_and_dedups(tmp_path, monkeypatch):
    import skyfire.cli as cli
    from skyfire.engine import PredictionResult
    from datetime import datetime
    from skyfire import store

    calls = {"push": 0}

    def _fake_compute(conn, client, c, city, event, day, run_llm=True):
        return PredictionResult(city_name="北京", event=event, day=day, index=6.0,
                                confidence="high", spread=0.0,
                                per_model={"gfs_seamless": 6.0}, blocked_points=0,
                                channel_factor=1.0, aod=0.2, channel_empty=False,
                                peak=datetime(2026, 7, 4, 19, 46), azimuth=300.0, llm=None)

    monkeypatch.setattr(cli, "_make_client", lambda: None)
    monkeypatch.setattr(cli, "compute_prediction", _fake_compute)
    monkeypatch.setattr(cli, "push", lambda *a, **k: calls.__setitem__("push", calls["push"] + 1) or True)
    # due_events 固定返回一个到期项,避开真实时钟
    monkeypatch.setattr(cli, "due_events", lambda cities, now, lead_minutes: [("beijing", "sunset_glow")])

    ncfg = tmp_path / "notify.yaml"
    ncfg.write_text("provider: bark\nkey: K\n", encoding="utf-8")
    db = tmp_path / "sky.db"
    r1 = runner.invoke(app, ["tick", "--db", str(db), "--notify-config", str(ncfg)])
    assert r1.exit_code == 0, r1.output
    assert calls["push"] == 1
    # 第二次 tick:已推,应去重不再推
    r2 = runner.invoke(app, ["tick", "--db", str(db), "--notify-config", str(ncfg)])
    assert r2.exit_code == 0
    assert calls["push"] == 1  # 未增加
```

- [ ] **Step 2: 运行确认失败**

Run: `cd /Users/feitong/photo-app/skyfire && .venv/bin/pytest tests/test_cli.py -v`
Expected: FAIL — `No such command 'notify'` / `'tick'`。

- [ ] **Step 3: 实现 cli.py 新命令**

在 cli.py 顶部 import 区追加:

```python
from datetime import datetime, timezone
from skyfire.notifyconf import load_notify_config, DEFAULT_LEAD_MINUTES
from skyfire.push import push
from skyfire.report import format_report
from skyfire.schedule import due_events
```

模块级默认路径旁加:

```python
DEFAULT_NOTIFY = Path(__file__).parent.parent.parent / "config" / "notify.local.yaml"
```

追加两命令:

```python
@app.command()
def notify(
    city: str = typer.Option("beijing"),
    event: str = typer.Option("sunset_glow", help="sunset_glow | sunrise_glow"),
    config: Path = typer.Option(DEFAULT_CONFIG),
    db: Path = typer.Option(DEFAULT_DB),
    notify_config: Path = typer.Option(DEFAULT_NOTIFY),
):
    """算一次预测并推送到手机(手动触发一次)。"""
    ncfg = load_notify_config(notify_config)
    if ncfg is None:
        typer.echo(f"错误:推送未配置({notify_config});复制 config/notify.example.yaml "
                   f"为 notify.local.yaml 并填密钥", err=True)
        raise typer.Exit(1)
    cities = load_cities(config)
    if city not in cities:
        typer.echo(f"错误:未知城市 {city!r},可用: {', '.join(cities)}", err=True)
        raise typer.Exit(1)
    conn = _open_db(db)
    client = _make_client()
    try:
        r = compute_prediction(conn, client, cities[city], city, event,
                               date_type.today(), run_llm=True)
    except (httpx.HTTPError, ValueError) as e:
        typer.echo(f"错误:预测失败({e.__class__.__name__}),未推送", err=True)
        raise typer.Exit(1)
    title, body = format_report(r)
    ok = push(title, body, ncfg)
    store.mark_pushed(conn, str(date_type.today()), city, event)
    typer.echo(f"{'✓ 已推送' if ok else '✗ 推送失败(已记录预测)'}: {title}")


@app.command()
def tick(
    config: Path = typer.Option(DEFAULT_CONFIG),
    db: Path = typer.Option(DEFAULT_DB),
    notify_config: Path = typer.Option(DEFAULT_NOTIFY),
):
    """调度入口:到点的城市×天象自动预测+推送(launchd 每 30 分钟调一次)。"""
    ncfg = load_notify_config(notify_config)
    if ncfg is None:
        return  # 未配置推送:静默退出(launchd 频繁调用,不刷错误)
    cities = load_cities(config)
    conn = _open_db(db)
    now = datetime.now(timezone.utc)
    lead = ncfg.get("lead_minutes", DEFAULT_LEAD_MINUTES)
    for city, event in due_events(cities, now, lead_minutes=lead):
        today = str(now.astimezone().date())
        if store.was_pushed(conn, today, city, event):
            continue
        client = _make_client()
        try:
            r = compute_prediction(conn, client, cities[city], city, event,
                                   date_type.today(), run_llm=True)
        except (httpx.HTTPError, ValueError):
            continue  # 单城失败不影响其他(spec 8)
        title, body = format_report(r)
        push(title, body, ncfg)
        store.mark_pushed(conn, today, city, event)
        typer.echo(f"✓ {city} {event}: {title}")
```

**注意:** `tick` 中 `today` 取 `now.astimezone().date()`(本机时区当日),与 `notify` 的 `date_type.today()` 一致;去重键与 due_events 的候选日一致即可。测试 `test_tick_pushes_due_and_dedups` monkeypatch 了 due_events,故实际日界无关。

- [ ] **Step 4: 创建 launchd 模板**

`skyfire/deploy/com.skyfire.tick.plist.example`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<!-- 安装:改下面两处绝对路径 → 复制到 ~/Library/LaunchAgents/com.skyfire.tick.plist
     → launchctl load ~/Library/LaunchAgents/com.skyfire.tick.plist
     每 30 分钟跑一次 skyfire tick;日志见 /tmp/skyfire.tick.log -->
<plist version="1.0">
<dict>
  <key>Label</key><string>com.skyfire.tick</string>
  <key>ProgramArguments</key>
  <array>
    <string>/Users/feitong/photo-app/skyfire/.venv/bin/skyfire</string>
    <string>tick</string>
  </array>
  <key>StartInterval</key><integer>1800</integer>
  <key>RunAtLoad</key><true/>
  <key>StandardOutPath</key><string>/tmp/skyfire.tick.log</string>
  <key>StandardErrorPath</key><string>/tmp/skyfire.tick.err</string>
</dict>
</plist>
```

- [ ] **Step 5: 运行确认通过**

Run: `cd /Users/feitong/photo-app/skyfire && .venv/bin/pytest tests/test_cli.py -v`
Expected: PASS(既有 cli 测试 + 3 新测试全绿)。全量 `.venv/bin/pytest -q` 应约 99 passed。`.venv/bin/skyfire --help` 应列出 8 命令(含 notify/tick)。

- [ ] **Step 6: 提交**

```bash
cd /Users/feitong/photo-app
git add skyfire/src/skyfire/cli.py skyfire/deploy/com.skyfire.tick.plist.example skyfire/tests/test_cli.py
git commit -m "feat(skyfire): notify/tick 命令 + launchd 模板"
```

---

### Task 8: 端到端真实验证

**Files:** 无新文件——真实推送冒烟(需用户的 Bark/Server酱 key)。

- [ ] **Step 1: 引导配置**

若 `skyfire/config/notify.local.yaml` 不存在,提示用户创建(执行者不要编造 key):

```bash
cp /Users/feitong/photo-app/skyfire/config/notify.example.yaml \
   /Users/feitong/photo-app/skyfire/config/notify.local.yaml
# 用户编辑填入真实 provider + key
```

若用户未提供 key,跳过 Step 2-3,记录"待用户配置",不算任务失败。

- [ ] **Step 2: 真实推送一次**

Run: `cd /Users/feitong/photo-app/skyfire && .venv/bin/skyfire notify --city beijing --event sunset_glow`
Expected: 手机收到一条推送(标题含指数与"晚霞 — 北京");终端打印"✓ 已推送"。若推送服务返回失败,检查 key;网络失败重试一次。

- [ ] **Step 3: tick 幂等验证**

Run: `.venv/bin/skyfire tick` 两次
Expected: 若当前在某天象前置窗口内,第一次推送、第二次因 `was_pushed` 去重不再推;不在窗口则两次都静默无输出(正常)。检查:`sqlite3 data/skyfire.db "SELECT date, city, event FROM notifications;"` 有行。

- [ ] **Step 4: 全量测试 + 收尾提交**

```bash
cd /Users/feitong/photo-app/skyfire && .venv/bin/pytest -q
cd /Users/feitong/photo-app
git status --short -- skyfire/   # 应只有 gitignore 的 data/ 与 config/notify.local.yaml
git log --oneline -3
```

Expected: 全量约 99 passed;无遗留未提交源码(notify.local.yaml 已 gitignore,不入库)。

---

## Self-Review 记录

- **需求覆盖**:可复用预测函数 → Task 4(engine.compute_prediction);推送适配器(Bark+Server酱,配置选一,失败静默)→ Task 2;报告格式化 → Task 5;调度打点(前置窗口+DB 幂等)→ Task 6(due_events)+ Task 1(notifications 表)+ Task 7(tick 去重);notify CLI + launchd 模板 → Task 7;真实端到端 → Task 8。
- **占位符扫描**:无 TBD/TODO;所有代码步骤含完整代码。engine.py 中 `__import__("pathlib")` 已明确要求改为顶部 `from pathlib import Path`。
- **类型一致性**:`PredictionResult` 字段在 Task 4 定义,Task 5(report)/Task 7(notify/tick 测试构造)一致使用;`push(title, body, config, client=None)->bool` 在 Task 2/7 一致;`load_notify_config(path)->dict|None`(键 provider/key/lead_minutes)在 Task 3/7 一致;`due_events(cities, now, lead_minutes)->list[(city,event)]` 在 Task 6/7 一致;`was_pushed/mark_pushed(conn, date, city, event)` 在 Task 1/7 一致;`compute_prediction(conn, client, city, city_key, event, day, run_llm)` 在 Task 4/7 一致。
- **回归风险点**:Task 4 重构 predict 会使旧 `test_predict_no_llm_flag_skips_llm`(spy `_run_llm`)失效——已在 Task 4 Step 5 明确要求替换为 spy `compute_prediction` 的 `run_llm` 实参版本,并说明这是预期行为变更(LLM 移入 engine)。predict 的 echo 文案保持逐字不变,其余 cli 测试无回归。
- **已知妥协**:tick 的 due_events 每次算全部城市×2 天象的太阳窗(北京单城成本可忽略;多城时可缓存,留 Plan C 后续);推送正文为纯文本(Bark/Server酱 都支持,Server酱 的 Markdown 换行未特别优化)。
