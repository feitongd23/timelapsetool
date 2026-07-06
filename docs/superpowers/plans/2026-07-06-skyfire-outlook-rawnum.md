# Skyfire 明日展望 + LLM 喂原始数字 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 每晚朝霞C1时刻双跑合推"明日展望"(明日日出+日落,每模式概率/质量/原始云量/降水),所有检查点的 LLM payload 喂各模式燃烧时刻原始预报数字,修 iso_hour 截断 bug,新增 `skyfire latest` 只读查询命令。

**Architecture:** 复用现有 run_checkpoint/predict_pct 全链路。outlook 是新 checkpoint 类型(行为=C1 基线只用预报);predictions 表迁移(CHECK 加 outlook + per_model_json 列);tick 在朝霞 c1 分支双跑合成一条推送。spec: `docs/superpowers/specs/2026-07-06-skyfire-outlook-rawnum-design.md`。

**Tech Stack:** Python 3.12(venv 在 `skyfire/.venv`),pytest,typer CLI,sqlite3,httpx MockTransport 测试。

**工作目录:** 所有命令在 `/Users/feitong/photo-app/skyfire` 下执行;测试命令用 `.venv/bin/pytest`。

---

### Task 0: 开分支

- [ ] **Step 1: 从 main 开特性分支**

```bash
cd /Users/feitong/photo-app && git checkout -b feat/skyfire-outlook main
```

---

### Task 1: nearest_iso_hour(修峰值截断 bug)

**Files:**
- Modify: `skyfire/src/skyfire/suntimes.py`
- Modify: `skyfire/src/skyfire/engine.py:56`
- Modify: `skyfire/src/skyfire/backfill.py:73`
- Test: `skyfire/tests/test_suntimes.py`

- [ ] **Step 1: 写失败测试**(追加到 `tests/test_suntimes.py`)

```python
from datetime import datetime

from skyfire.suntimes import nearest_iso_hour


def test_nearest_iso_hour_keeps_hour_before_half():
    assert nearest_iso_hour(datetime(2026, 7, 6, 4, 29)) == "2026-07-06T04:00"


def test_nearest_iso_hour_rounds_up_from_half():
    # 修 bug:04:47 峰值此前被截断到 04:00 取数
    assert nearest_iso_hour(datetime(2026, 7, 6, 4, 47)) == "2026-07-06T05:00"


def test_nearest_iso_hour_crosses_midnight():
    assert nearest_iso_hour(datetime(2026, 7, 6, 23, 47)) == "2026-07-07T00:00"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/bin/pytest tests/test_suntimes.py -v -k nearest`
Expected: FAIL, `ImportError: cannot import name 'nearest_iso_hour'`

- [ ] **Step 3: 实现**(`suntimes.py`,首行 import 改为 `from datetime import date, datetime, timedelta`,文件末尾追加)

```python
def nearest_iso_hour(dt: datetime) -> str:
    """就近取整到小时的 ISO 串(04:47→05:00)。

    预报按整点给数;此前用 strftime 截断,峰值 xx:30 之后取数偏差近一小时。
    """
    if dt.minute >= 30:
        dt = dt + timedelta(hours=1)
    return dt.strftime("%Y-%m-%dT%H:00")
```

- [ ] **Step 4: 两处调用点换用**

`engine.py`:import 行 `from skyfire.suntimes import sun_window` 改为 `from skyfire.suntimes import nearest_iso_hour, sun_window`;第 56 行 `iso_hour = win.peak.strftime("%Y-%m-%dT%H:00")` 改为 `iso_hour = nearest_iso_hour(win.peak)`。

`backfill.py`:第 73 行同样改为 `iso_hour = nearest_iso_hour(win.peak)`,并在其 import 区加 `from skyfire.suntimes import nearest_iso_hour`(若已 import sun_window 则并入同一行)。

- [ ] **Step 5: 跑相关测试确认全过**

Run: `.venv/bin/pytest tests/test_suntimes.py tests/test_engine.py tests/test_backfill.py -v`
Expected: 全 PASS(fake transport 提供全天 24h 整点数据,取整不影响现有断言)

- [ ] **Step 6: Commit**

```bash
git add skyfire/src/skyfire/suntimes.py skyfire/src/skyfire/engine.py skyfire/src/skyfire/backfill.py skyfire/tests/test_suntimes.py
git commit -m "fix(skyfire): iso_hour 就近取整,修峰值 xx:30 后取数偏一小时"
```

---

### Task 2: compute_prediction 提取 per_model_raw

**Files:**
- Modify: `skyfire/src/skyfire/engine.py`(PredictionResult + compute_prediction)
- Test: `skyfire/tests/test_engine.py`

- [ ] **Step 1: 写失败测试**(追加到 `tests/test_engine.py`)

```python
def test_compute_prediction_collects_per_model_raw(tmp_path):
    from datetime import date
    conn = store.connect(tmp_path / "t.db")
    store.init_db(conn)
    city = load_cities(CONFIG)["beijing"]
    client = httpx.Client(transport=_fake_transport())
    r = compute_prediction(conn, client, city, "beijing", "sunset_glow",
                           date(2026, 7, 3), run_llm=False)
    # fake transport:每模式 high=50 mid=15 low=10 precip=0
    assert set(r.per_model_raw) == set(MODELS)
    assert r.per_model_raw["gfs_seamless"] == {
        "cloud_high": 50, "cloud_mid": 15, "cloud_low": 10, "precipitation": 0}
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/bin/pytest tests/test_engine.py::test_compute_prediction_collects_per_model_raw -v`
Expected: FAIL, `AttributeError: 'PredictionResult' object has no attribute 'per_model_raw'`

- [ ] **Step 3: 实现**

`engine.py` 顶部 import 改为 `from dataclasses import dataclass, field`。PredictionResult 末尾(`llm: LlmResult | None` 之后)加带默认值字段(放末尾避免破坏既有关键字构造):

```python
    # 各模式燃烧时刻原始预报(喂 LLM 看分歧;值可为 None)
    per_model_raw: dict[str, dict] = field(default_factory=dict)
```

compute_prediction 的模式循环改为(第 63-75 行区域):

```python
    per_model: dict[str, float] = {}
    per_model_raw: dict[str, dict] = {}
    details = {}
    for fc in forecasts:
        h = fc.at(iso_hour)
        if h is None:
            continue
        per_model_raw[fc.model] = {
            "cloud_high": h.cloud_high, "cloud_mid": h.cloud_mid,
            "cloud_low": h.cloud_low, "precipitation": h.precipitation}
        if h.cloud_high is None:
            continue
        r = fire_cloud_score(FireCloudInputs(
            cloud_high=h.cloud_high, cloud_mid=h.cloud_mid or 0,
            cloud_low=h.cloud_low or 0, precipitation=h.precipitation or 0,
            aod=aod, channel=channel,
        ))
        per_model[fc.model] = r.score
        details[fc.model] = r
```

return 的 PredictionResult 构造加 `per_model_raw=per_model_raw`。

- [ ] **Step 4: 跑测试确认通过**

Run: `.venv/bin/pytest tests/test_engine.py -v`
Expected: 全 PASS

- [ ] **Step 5: Commit**

```bash
git add skyfire/src/skyfire/engine.py skyfire/tests/test_engine.py
git commit -m "feat(skyfire): PredictionResult 携带各模式燃烧时刻原始预报 per_model_raw"
```

---

### Task 3: store 迁移(CHECK 加 outlook + per_model_json 列)

**Files:**
- Modify: `skyfire/src/skyfire/store.py`(SCHEMA、init_db、add_prediction、_PRED_KEYS)
- Test: `skyfire/tests/test_store.py`

- [ ] **Step 1: 写失败测试**(追加到 `tests/test_store.py`;注意文件顶部已有 `from skyfire import store`,若无 `import sqlite3` 则补)

```python
_OLD_PREDICTIONS_SCHEMA = """
CREATE TABLE predictions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  date TEXT NOT NULL, city TEXT NOT NULL, event TEXT NOT NULL,
  checkpoint TEXT NOT NULL CHECK(checkpoint IN ('c1','c2','c3','gated','manual')),
  probability_pct REAL NOT NULL, quality_pct REAL NOT NULL,
  confidence TEXT, rule_score REAL, sat_cloud_pct REAL, trend TEXT,
  llm_status TEXT NOT NULL DEFAULT 'pending'
    CHECK(llm_status IN ('done','pending','skipped')),
  reasoning TEXT, risks TEXT,
  created_at TEXT DEFAULT (datetime('now'))
);
CREATE UNIQUE INDEX idx_pred_checkpoint
  ON predictions(date, city, event, checkpoint)
  WHERE checkpoint IN ('c1','c2','c3');
"""


def test_predictions_migration_from_old_schema(tmp_path):
    import sqlite3
    db = tmp_path / "old.db"
    raw = sqlite3.connect(db)
    raw.executescript(_OLD_PREDICTIONS_SCHEMA)
    raw.execute(
        """INSERT INTO predictions (date, city, event, checkpoint,
             probability_pct, quality_pct, llm_status)
           VALUES ('2026-07-05','beijing','sunset_glow','c1',50,50,'done')""")
    raw.commit(); raw.close()

    conn = store.connect(db)
    store.init_db(conn)          # 触发迁移
    # 老数据保留
    rows = store.predictions_for(conn, "2026-07-05", "beijing", "sunset_glow")
    assert len(rows) == 1 and rows[0]["checkpoint"] == "c1"
    # outlook 可写入,per_model_json 落库读回
    store.add_prediction(conn, "2026-07-06", "beijing", "sunset_glow", "outlook",
                         probability_pct=60, quality_pct=55, confidence="high",
                         rule_score=5.5, sat_cloud_pct=None, trend=None,
                         llm_status="pending", reasoning=None, risks=None,
                         per_model_json='{"gfs_seamless": {"prob": 60}}')
    row = store.latest_prediction(conn, "2026-07-06", "beijing", "sunset_glow")
    assert row["checkpoint"] == "outlook"
    assert row["per_model_json"] == '{"gfs_seamless": {"prob": 60}}'
    # 幂等:重复 init_db 不报错不丢数据
    store.init_db(conn)
    assert len(store.predictions_for(conn, "2026-07-05", "beijing",
                                     "sunset_glow")) == 1


def test_outlook_unique_per_day(tmp_path):
    import sqlite3, pytest
    conn = store.connect(tmp_path / "t.db")
    store.init_db(conn)
    kw = dict(probability_pct=60, quality_pct=55, confidence="high",
              rule_score=5.5, sat_cloud_pct=None, trend=None,
              llm_status="pending", reasoning=None, risks=None)
    store.add_prediction(conn, "2026-07-06", "beijing", "sunset_glow", "outlook", **kw)
    with pytest.raises(sqlite3.IntegrityError):
        store.add_prediction(conn, "2026-07-06", "beijing", "sunset_glow", "outlook", **kw)
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/bin/pytest tests/test_store.py -v -k "migration or outlook"`
Expected: FAIL(add_prediction 不认识 per_model_json 参数 / CHECK 拒绝 outlook)

- [ ] **Step 3: 实现**

`store.py` SCHEMA 中 predictions 建表语句改为(仅 CHECK 与新列两处变化):

```sql
CREATE TABLE IF NOT EXISTS predictions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  date TEXT NOT NULL,
  city TEXT NOT NULL,
  event TEXT NOT NULL,
  checkpoint TEXT NOT NULL CHECK(checkpoint IN ('c1','c2','c3','gated','manual','outlook')),
  probability_pct REAL NOT NULL,
  quality_pct REAL NOT NULL,
  confidence TEXT,
  rule_score REAL,
  sat_cloud_pct REAL,
  trend TEXT,
  llm_status TEXT NOT NULL DEFAULT 'pending'
    CHECK(llm_status IN ('done','pending','skipped')),
  reasoning TEXT,
  risks TEXT,
  per_model_json TEXT,
  created_at TEXT DEFAULT (datetime('now'))
);
```

唯一索引 WHERE 子句改为 `WHERE checkpoint IN ('c1','c2','c3','outlook')`。

init_db 改为:

```python
def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    cols = [r[1] for r in conn.execute("PRAGMA table_info(cases)").fetchall()]
    if "sat_cloud_pct" not in cols:
        conn.execute("ALTER TABLE cases ADD COLUMN sat_cloud_pct REAL")
    _migrate_predictions(conn)
    conn.commit()


def _migrate_predictions(conn: sqlite3.Connection) -> None:
    """老库升级:CHECK 加 outlook 需重建表(SQLite 不能改 CHECK);幂等。"""
    sql = conn.execute("SELECT sql FROM sqlite_master WHERE type='table'"
                       " AND name='predictions'").fetchone()
    if sql and "'outlook'" not in sql[0]:
        conn.executescript("""
        ALTER TABLE predictions RENAME TO predictions_old;
        CREATE TABLE predictions (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          date TEXT NOT NULL,
          city TEXT NOT NULL,
          event TEXT NOT NULL,
          checkpoint TEXT NOT NULL CHECK(checkpoint IN ('c1','c2','c3','gated','manual','outlook')),
          probability_pct REAL NOT NULL,
          quality_pct REAL NOT NULL,
          confidence TEXT,
          rule_score REAL,
          sat_cloud_pct REAL,
          trend TEXT,
          llm_status TEXT NOT NULL DEFAULT 'pending'
            CHECK(llm_status IN ('done','pending','skipped')),
          reasoning TEXT,
          risks TEXT,
          per_model_json TEXT,
          created_at TEXT DEFAULT (datetime('now'))
        );
        INSERT INTO predictions (id, date, city, event, checkpoint,
            probability_pct, quality_pct, confidence, rule_score, sat_cloud_pct,
            trend, llm_status, reasoning, risks, created_at)
          SELECT id, date, city, event, checkpoint, probability_pct, quality_pct,
                 confidence, rule_score, sat_cloud_pct, trend, llm_status,
                 reasoning, risks, created_at
          FROM predictions_old;
        DROP TABLE predictions_old;
        DROP INDEX IF EXISTS idx_pred_checkpoint;
        CREATE UNIQUE INDEX idx_pred_checkpoint
          ON predictions(date, city, event, checkpoint)
          WHERE checkpoint IN ('c1','c2','c3','outlook');
        """)
    cols = [r[1] for r in conn.execute("PRAGMA table_info(predictions)").fetchall()]
    if "per_model_json" not in cols:
        conn.execute("ALTER TABLE predictions ADD COLUMN per_model_json TEXT")
```

`_PRED_KEYS` 在 `"risks"` 与 `"created_at"` 之间插入 `"per_model_json"`:

```python
_PRED_KEYS = ("id", "date", "city", "event", "checkpoint", "probability_pct",
              "quality_pct", "confidence", "rule_score", "sat_cloud_pct",
              "trend", "llm_status", "reasoning", "risks", "per_model_json",
              "created_at")
```

`add_prediction` 签名加 `per_model_json: str | None = None`,INSERT 列表加该列(13 个问号变 14 个):

```python
def add_prediction(conn, date: str, city: str, event: str, checkpoint: str, *,
                   probability_pct: float, quality_pct: float,
                   confidence: str | None, rule_score: float | None,
                   sat_cloud_pct: float | None, trend: str | None,
                   llm_status: str, reasoning: str | None, risks: str | None,
                   per_model_json: str | None = None) -> int:
    cur = conn.execute(
        """INSERT INTO predictions (date, city, event, checkpoint,
             probability_pct, quality_pct, confidence, rule_score,
             sat_cloud_pct, trend, llm_status, reasoning, risks, per_model_json)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (date, city, event, checkpoint, probability_pct, quality_pct,
         confidence, rule_score, sat_cloud_pct, trend, llm_status,
         reasoning, risks, per_model_json))
    conn.commit()
    return cur.lastrowid
```

- [ ] **Step 4: 跑测试确认通过**

Run: `.venv/bin/pytest tests/test_store.py tests/test_cli.py -v`
Expected: 全 PASS(_PRED_KEYS 变更会影响 predictions_for 的 SELECT,顺序一致即可)

- [ ] **Step 5: Commit**

```bash
git add skyfire/src/skyfire/store.py skyfire/tests/test_store.py
git commit -m "feat(skyfire): predictions 表迁移——checkpoint 支持 outlook,新增 per_model_json 列(幂等重建)"
```

---

### Task 4: run_checkpoint 接线(payload/rec/落库 + outlook 基线)+ 提示词

**Files:**
- Modify: `skyfire/src/skyfire/engine.py`(run_checkpoint)
- Modify: `skyfire/src/skyfire/llm.py`(_PREDICT_SYSTEM)
- Test: `skyfire/tests/test_engine.py`、`skyfire/tests/test_llm.py`

- [ ] **Step 1: 更新既有 fake + 写失败测试**

`tests/test_engine.py` 的 `_fake_pr` 构造中(`llm=None` 之前)加一行:

```python
        per_model_raw={"gfs_seamless": {"cloud_high": 80, "cloud_mid": 20,
                                        "cloud_low": 10, "precipitation": 0.0}},
```

追加测试:

```python
def test_run_checkpoint_outlook_baseline_ignores_satellite(monkeypatch):
    conn, city = _setup(monkeypatch, None)
    rec = run_checkpoint(conn, object(), city, "beijing", "sunset_glow",
                         date_type(2026, 7, 6), "outlook")
    # 同 C1:外推 52 不参与 → rule 5.0 high → prob 50
    assert rec["probability_pct"] == 50 and rec["quality_pct"] == 50
    assert rec["checkpoint"] == "outlook"
    assert store.has_checkpoint(conn, "2026-07-06", "beijing", "sunset_glow",
                                "outlook")


def test_run_checkpoint_payload_rec_and_db_carry_raw(monkeypatch):
    captured = {}

    def fake_predict(payload, similar, frames, model=None):
        captured.update(payload)
        return None

    monkeypatch.setattr(engine_mod, "compute_prediction",
                        lambda *a, **k: _fake_pr())
    monkeypatch.setattr(engine_mod, "observe_burn_clouds",
                        lambda *a, **k: (48.0, 52.0, "now=48%→burn=52%", []))
    monkeypatch.setattr(engine_mod, "predict_pct", fake_predict)
    conn = store.connect(":memory:")
    store.init_db(conn)
    city = City(key="beijing", name="北京", lat=39.9, lon=116.4,
                timezone="Asia/Shanghai")
    rec = run_checkpoint(conn, object(), city, "beijing", "sunset_glow",
                         date_type(2026, 7, 6), "c2")
    # LLM payload 看得到各模式原始数字
    assert captured["per_model_raw"]["gfs_seamless"]["cloud_high"] == 80
    # rec 携带原始数字(推送格式化用)
    assert rec["per_model_raw"]["gfs_seamless"]["precipitation"] == 0.0
    # per_model_json 落库:概率/质量 + 原始数字合体
    import json
    row = store.latest_prediction(conn, "2026-07-06", "beijing", "sunset_glow")
    pmj = json.loads(row["per_model_json"])
    assert pmj["gfs_seamless"]["prob"] == 65 and pmj["gfs_seamless"]["cloud_high"] == 80
```

`tests/test_llm.py` 追加:

```python
def test_predict_system_mentions_per_model_raw():
    from skyfire.llm import _PREDICT_SYSTEM
    assert "per_model_raw" in _PREDICT_SYSTEM
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/bin/pytest tests/test_engine.py tests/test_llm.py -v -k "outlook or raw or per_model"`
Expected: FAIL(payload 无 per_model_raw;outlook 走了卫星外推 prob=65;提示词无 per_model_raw)

- [ ] **Step 3: 实现 engine.py**

顶部加 `import json`(与现有 import 并列)。run_checkpoint 中三处修改:

① cloud_args 判定(约第 184 行)改为:

```python
    # C1/outlook 距燃烧数小时以上:短时外推冒充不了届时云况
    # (knowledge §3.2:远期信预报当底子,临近才信实测外推),
    # 基线只用预报驱动的规则分;C2/C3/gated 临近才引入卫星外推修正。
    cloud_args = (None, None) if checkpoint in ("c1", "outlook") \
        else (sat_now, burn_pct)
```

② payload dict(约第 198 行)在 `"per_model": r.per_model,` 后加一项:

```python
               "per_model_raw": r.per_model_raw,
```

③ 落库与返回(约第 218 行起)改为:

```python
    per_model_json = json.dumps(
        {m: {"prob": p, "qual": q, **r.per_model_raw.get(m, {})}
         for m, (p, q) in per_model_pct.items()}, ensure_ascii=False)
    pred_id = store.add_prediction(
        conn, str(day), city_key, event, checkpoint,
        probability_pct=rec["probability_pct"], quality_pct=rec["quality_pct"],
        confidence=rec["confidence"], rule_score=r.index,
        sat_cloud_pct=sat_now, trend=trend, llm_status=rec["llm_status"],
        reasoning=rec["reasoning"], risks=rec["risks"],
        per_model_json=per_model_json)
    return {**rec, "id": pred_id, "date": str(day), "city": city_key,
            "event": event, "checkpoint": checkpoint, "rule_score": r.index,
            "sat_cloud_pct": sat_now, "trend": trend, "peak": r.peak,
            "per_model_pct": per_model_pct, "per_model_raw": r.per_model_raw,
            "aod": r.aod, "city_name": city.name}
```

- [ ] **Step 4: 实现 llm.py 提示词**

`_PREDICT_SYSTEM` 中 `"不用专业缩写。"` 之后插入一句:

```
"免费层数据中的 per_model_raw 是各气象模式对燃烧时刻高/中/低云量%与降水mm"
"的原始预报——用它判断模式间分歧;任一模式报降水时提高雨险警惕。"
```

(保持现有字符串拼接风格,作为相邻字符串字面量插入。)

- [ ] **Step 5: 跑测试确认通过**

Run: `.venv/bin/pytest tests/test_engine.py tests/test_llm.py -v`
Expected: 全 PASS

- [ ] **Step 6: Commit**

```bash
git add skyfire/src/skyfire/engine.py skyfire/src/skyfire/llm.py skyfire/tests/test_engine.py skyfire/tests/test_llm.py
git commit -m "feat(skyfire): 检查点 payload/rec/落库携带 per_model_raw;outlook 基线只用预报;提示词补语义"
```

---

### Task 5: format_outlook_report 推送格式

**Files:**
- Modify: `skyfire/src/skyfire/report.py`
- Test: `skyfire/tests/test_report.py`

- [ ] **Step 1: 写失败测试**(追加到 `tests/test_report.py`)

```python
from datetime import datetime
from zoneinfo import ZoneInfo

from skyfire.report import format_outlook_report

_TZ = ZoneInfo("Asia/Shanghai")


def _outlook_rec(event, prob, qual, hour, minute):
    return {"probability_pct": prob, "quality_pct": qual, "confidence": "high",
            "llm_status": "done", "reasoning": "高云画布可期", "risks": "低云",
            "event": event, "rule_score": 5.5, "aod": 0.3,
            "peak": datetime(2026, 7, 7, hour, minute, tzinfo=_TZ),
            "city_name": "北京",
            "per_model_pct": {"ecmwf_ifs025": (35, 40), "gfs_seamless": (20, 30)},
            "per_model_raw": {
                "ecmwf_ifs025": {"cloud_high": 80, "cloud_mid": 20,
                                 "cloud_low": 10, "precipitation": 0.0},
                "gfs_seamless": {"cloud_high": 100, "cloud_mid": 40,
                                 "cloud_low": 30, "precipitation": 5.0}}}


def test_format_outlook_report_two_sections():
    sunrise = _outlook_rec("sunrise_glow", 35, 40, 4, 50)
    sunset = _outlook_rec("sunset_glow", 60, 55, 19, 46)
    title, body = format_outlook_report(sunrise, sunset)
    assert title == "明日展望 朝霞35% 晚霞60% — 北京"
    assert "明日朝霞 日出 04:50" in body and "明日晚霞 日落 19:46" in body
    assert "EC 35/40 · 高80 中20 低10 · 无雨" in body
    assert "GFS 20/30 · 高100 中40 低30 · 雨5.0mm" in body
    assert "解读: 高云画布可期" in body


def test_format_outlook_report_missing_side():
    sunset = _outlook_rec("sunset_glow", 60, 55, 19, 46)
    title, body = format_outlook_report(None, sunset)
    assert "朝霞—%" in title and "晚霞60%" in title
    assert "明日朝霞: 数据缺失,稍后自动重试" in body
    assert "明日晚霞 日落 19:46" in body


def test_format_outlook_report_raw_none_shows_dash():
    sunset = _outlook_rec("sunset_glow", 60, 55, 19, 46)
    sunset["per_model_raw"]["ecmwf_ifs025"]["cloud_high"] = None
    _, body = format_outlook_report(None, sunset)
    assert "EC 35/40 · 高— 中20 低10 · 无雨" in body
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/bin/pytest tests/test_report.py -v -k outlook`
Expected: FAIL, `ImportError: cannot import name 'format_outlook_report'`

- [ ] **Step 3: 实现**(`report.py` 末尾追加)

```python
def _num(v) -> str:
    return "—" if v is None else f"{v:.0f}"


def _model_lines(rec: dict) -> list[str]:
    lines = ["各模式(概率/质量 · 高中低云% · 降水):"]
    raw_all = rec.get("per_model_raw") or {}
    for m, (p, q) in rec["per_model_pct"].items():
        parts = [f"{m.split('_')[0].upper()} {p:.0f}/{q:.0f}"]
        raw = raw_all.get(m)
        if raw:
            parts.append(f"高{_num(raw.get('cloud_high'))}"
                         f" 中{_num(raw.get('cloud_mid'))}"
                         f" 低{_num(raw.get('cloud_low'))}")
            precip = raw.get("precipitation")
            parts.append(f"雨{precip:.1f}mm" if precip and precip >= 0.1 else "无雨")
        lines.append(" · ".join(parts))
    return lines


def _outlook_section(rec: dict) -> list[str]:
    sunset = rec["event"] == "sunset_glow"
    event_zh = "晚霞" if sunset else "朝霞"
    when = "日落" if sunset else "日出"
    best = "其后约15分钟" if sunset else "其前约15分钟"
    lines = [f"明日{event_zh} {when} {rec['peak'].strftime('%H:%M')}"
             f"(最佳观赏在{best})"]
    lines.append(f"概率 {rec['probability_pct']:.0f}%"
                 f"({_prob_word(rec['probability_pct'])})"
                 f" · 质量 {rec['quality_pct']:.0f}%"
                 f"({_qual_word(rec['quality_pct'])})")
    lines.extend(_model_lines(rec))
    aod = rec.get("aod")
    aod_s = f"{aod}" if aod is not None else "—"
    lines.append(f"空气(气溶胶AOD {aod_s}): {_aod_word(aod)}")
    lines.append(f"可信度: {_CONF_PLAIN.get(rec['confidence'], rec['confidence'])}")
    if rec.get("llm_status") == "done":
        lines.append(f"解读: {rec['reasoning']}")
        lines.append(f"风险: {rec['risks']}")
    else:
        lines.append("AI 解读暂缺,以上为基础数据")
    return lines


def format_outlook_report(rec_sunrise: dict | None,
                          rec_sunset: dict | None) -> tuple[str, str]:
    """每晚明日展望:朝霞+晚霞双节合推;任一边 None 标数据缺失(spec §4)。"""
    some = rec_sunrise or rec_sunset
    p_sr = f"{rec_sunrise['probability_pct']:.0f}%" if rec_sunrise else "—%"
    p_ss = f"{rec_sunset['probability_pct']:.0f}%" if rec_sunset else "—%"
    title = f"明日展望 朝霞{p_sr} 晚霞{p_ss} — {some['city_name']}"
    lines: list[str] = []
    for rec, label in ((rec_sunrise, "明日朝霞"), (rec_sunset, "明日晚霞")):
        if rec is None:
            lines.append(f"{label}: 数据缺失,稍后自动重试")
        else:
            lines.extend(_outlook_section(rec))
        lines.append("")
    return title, "\n".join(lines).rstrip()
```

注意:标题里事件顺序固定"朝霞在前"(展望的叙事顺序=明天先日出后日落),`_outlook_section` 内的时间行不含"明日"以外前缀差异。此实现要求 `_prob_word/_qual_word/_aod_word/_CONF_PLAIN` 已在同文件(现有代码,无需动)。

- [ ] **Step 4: 跑测试确认通过**

Run: `.venv/bin/pytest tests/test_report.py -v`
Expected: 全 PASS

- [ ] **Step 5: Commit**

```bash
git add skyfire/src/skyfire/report.py skyfire/tests/test_report.py
git commit -m "feat(skyfire): format_outlook_report 明日展望双节推送(每模式概率/质量+原始云量+降水)"
```

---

### Task 6: tick 双跑合推

**Files:**
- Modify: `skyfire/src/skyfire/cli.py`(tick 命令,约 427-477 行)
- Test: `skyfire/tests/test_cli.py`

- [ ] **Step 1: 写失败测试**(追加到 `tests/test_cli.py`;沿用文件内既有 runner/app import)

```python
def _outlookable_rec(event, checkpoint, prob=50.0):
    from datetime import datetime as _dt
    from zoneinfo import ZoneInfo as _zi
    return {"probability_pct": prob, "quality_pct": 50.0, "confidence": "high",
            "llm_status": "pending", "reasoning": None, "risks": None,
            "date": "2026-07-07", "event": event, "checkpoint": checkpoint,
            "rule_score": 5.0, "sat_cloud_pct": None, "trend": None,
            "aod": 0.3, "city_name": "北京",
            "peak": _dt(2026, 7, 7, 4, 50, tzinfo=_zi("Asia/Shanghai")),
            "per_model_pct": {"gfs_seamless": (50, 50)},
            "per_model_raw": {"gfs_seamless": {"cloud_high": 50, "cloud_mid": 15,
                                               "cloud_low": 10,
                                               "precipitation": 0.0}}}


def test_tick_sunrise_c1_runs_outlook_and_pushes_combined(tmp_path, monkeypatch):
    import skyfire.cli as cli
    pushed = []
    monkeypatch.setattr(cli, "load_notify_config",
                        lambda p: {"provider": "bark", "key": "k"})
    monkeypatch.setattr(cli, "push", lambda t, b, cfg: pushed.append((t, b)) or True)
    monkeypatch.setattr(cli, "due_checkpoint", lambda now, peak, ev:
                        "c1" if ev == "sunrise_glow" else None)
    calls = []

    def fake_run(conn, client, c, key, event, day, cp, **kw):
        calls.append((event, cp))
        return _outlookable_rec(event, cp)

    monkeypatch.setattr(cli, "run_checkpoint", fake_run)
    result = runner.invoke(app, ["tick", "--db", str(tmp_path / "t.db")])
    assert result.exit_code == 0
    assert ("sunrise_glow", "c1") in calls and ("sunset_glow", "outlook") in calls
    assert len(pushed) == 1                       # 合成一条
    assert pushed[0][0].startswith("明日展望")
    assert "明日朝霞" in pushed[0][1] and "明日晚霞" in pushed[0][1]


def test_tick_outlook_failure_still_pushes_sunrise(tmp_path, monkeypatch):
    import httpx
    import skyfire.cli as cli
    pushed = []
    monkeypatch.setattr(cli, "load_notify_config",
                        lambda p: {"provider": "bark", "key": "k"})
    monkeypatch.setattr(cli, "push", lambda t, b, cfg: pushed.append((t, b)) or True)
    monkeypatch.setattr(cli, "due_checkpoint", lambda now, peak, ev:
                        "c1" if ev == "sunrise_glow" else None)

    def fake_run(conn, client, c, key, event, day, cp, **kw):
        if cp == "outlook":
            raise httpx.ConnectError("boom")
        return _outlookable_rec(event, cp)

    monkeypatch.setattr(cli, "run_checkpoint", fake_run)
    result = runner.invoke(app, ["tick", "--db", str(tmp_path / "t.db")])
    assert result.exit_code == 0
    assert len(pushed) == 1
    assert "晚霞—%" in pushed[0][0]
    assert "明日晚霞: 数据缺失" in pushed[0][1]


def test_tick_sunset_c1_unchanged_single_push(tmp_path, monkeypatch):
    import skyfire.cli as cli
    pushed = []
    monkeypatch.setattr(cli, "load_notify_config",
                        lambda p: {"provider": "bark", "key": "k"})
    monkeypatch.setattr(cli, "push", lambda t, b, cfg: pushed.append(t) or True)
    monkeypatch.setattr(cli, "due_checkpoint", lambda now, peak, ev:
                        "c1" if ev == "sunset_glow" else None)
    calls = []

    def fake_run(conn, client, c, key, event, day, cp, **kw):
        calls.append((event, cp))
        return _outlookable_rec(event, cp)

    monkeypatch.setattr(cli, "run_checkpoint", fake_run)
    result = runner.invoke(app, ["tick", "--db", str(tmp_path / "t.db")])
    assert result.exit_code == 0
    # 晚霞当天 11:00 的 C1 不触发展望,推送保持单事件格式
    assert all(cp != "outlook" for _, cp in calls)
    assert len(pushed) == 1 and not pushed[0].startswith("明日展望")
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/bin/pytest tests/test_cli.py -v -k "outlook or sunset_c1"`
Expected: FAIL(现在 tick 只跑 c1、推单事件格式)

- [ ] **Step 3: 实现**

`cli.py`:import 行 `from skyfire.report import format_pct_report, format_report` 改为 `from skyfire.report import format_outlook_report, format_pct_report, format_report`。

tick 中 `if cp is not None:` 分支(现约 454-459 行)改为:

```python
                    if cp is not None:
                        if store.has_checkpoint(conn, pred_date, city_key,
                                                event, cp):
                            break  # 该检查点已跑过:该 event 已处理,不看另一天
                        rec = run_checkpoint(conn, client, c, city_key, event,
                                             win.peak.date(), cp)
                        # 朝霞 C1 时刻 = 每晚明日展望:同跑明日晚霞 outlook,
                        # 合成一条推送(spec §2 双跑合推,用户拍板)
                        if cp == "c1" and event == "sunrise_glow":
                            rec_outlook = None
                            if not store.has_checkpoint(conn, pred_date,
                                                        city_key, "sunset_glow",
                                                        "outlook"):
                                try:
                                    rec_outlook = run_checkpoint(
                                        conn, client, c, city_key,
                                        "sunset_glow", win.peak.date(),
                                        "outlook")
                                except (httpx.HTTPError, ValueError):
                                    rec_outlook = None  # 缺一半照推,下轮补跑
                            title, body = format_outlook_report(rec,
                                                                rec_outlook)
                            push(title, body, ncfg)
                            typer.echo(f"✓ {city_key} outlook {title}")
                            break
```

(其后原有 `else:` 门控分支、`if rec is None: continue`、`format_pct_report` 推送逻辑保持不变——朝霞 c1 分支已在上面 break,不会落到单事件推送。)

- [ ] **Step 4: 跑测试确认通过(含既有 tick 测试不回归)**

Run: `.venv/bin/pytest tests/test_cli.py -v`
Expected: 全 PASS(`test_tick_runs_due_checkpoint_and_pushes` 用 sunset_glow c1,不走展望分支,不受影响)

- [ ] **Step 5: Commit**

```bash
git add skyfire/src/skyfire/cli.py skyfire/tests/test_cli.py
git commit -m "feat(skyfire): tick 朝霞C1时刻双跑合推明日展望(outlook 判重/单边失败降级)"
```

---

### Task 7: skyfire latest 只读查询命令

**Files:**
- Modify: `skyfire/src/skyfire/store.py`(recent_predictions)
- Modify: `skyfire/src/skyfire/cli.py`(latest 命令)
- Test: `skyfire/tests/test_store.py`、`skyfire/tests/test_cli.py`

- [ ] **Step 1: 写失败测试**

`tests/test_store.py` 追加:

```python
def test_recent_predictions_orders_desc_and_limits(tmp_path):
    conn = store.connect(tmp_path / "t.db")
    store.init_db(conn)
    kw = dict(probability_pct=50, quality_pct=50, confidence="high",
              rule_score=5.0, sat_cloud_pct=None, trend=None,
              llm_status="pending", reasoning=None, risks=None)
    for cp in ("c1", "c2", "c3"):
        store.add_prediction(conn, "2026-07-06", "beijing", "sunset_glow",
                             cp, **kw)
    rows = store.recent_predictions(conn, "beijing", limit=2)
    assert [r["checkpoint"] for r in rows] == ["c3", "c2"]   # 最新在前
```

`tests/test_cli.py` 追加:

```python
def test_latest_prints_recent_predictions(tmp_path):
    from skyfire import store
    db = tmp_path / "t.db"
    conn = store.connect(db); store.init_db(conn)
    store.add_prediction(conn, "2026-07-06", "beijing", "sunset_glow", "c2",
                         probability_pct=28, quality_pct=30, confidence="high",
                         rule_score=5.0, sat_cloud_pct=12.0, trend=None,
                         llm_status="done", reasoning="近程低云堵", risks="雨险",
                         per_model_json=None)
    result = runner.invoke(app, ["latest", "--db", str(db)])
    assert result.exit_code == 0
    assert "2026-07-06" in result.output and "晚霞" in result.output
    assert "[c2]" in result.output and "28%" in result.output
    assert "近程低云堵" in result.output


def test_latest_empty_db(tmp_path):
    result = runner.invoke(app, ["latest", "--db", str(tmp_path / "t.db")])
    assert result.exit_code == 0
    assert "暂无预测记录" in result.output
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/bin/pytest tests/test_store.py::test_recent_predictions_orders_desc_and_limits tests/test_cli.py -v -k "latest or recent"`
Expected: FAIL(recent_predictions/latest 不存在)

- [ ] **Step 3: 实现**

`store.py`(`pending_predictions` 附近追加):

```python
def recent_predictions(conn, city: str, limit: int = 6) -> list[dict]:
    rows = conn.execute(
        f"SELECT {','.join(_PRED_KEYS)} FROM predictions"
        " WHERE city=? ORDER BY id DESC LIMIT ?", (city, limit)).fetchall()
    return _pred_rows(rows)
```

`cli.py` 追加命令(放在 checkpoint 命令之后;文件已有 `_open_db`/`typer` 等依赖):

```python
@app.command()
def latest(
    city: str = typer.Option("beijing"),
    db: Path = typer.Option(DEFAULT_DB),
    limit: int = typer.Option(6, help="显示最近几条"),
):
    """查看最近的预测记录(纯读库,零 API 调用)。"""
    conn = _open_db(db)
    rows = store.recent_predictions(conn, city, limit=limit)
    if not rows:
        typer.echo("暂无预测记录")
        return
    for r in rows:
        event_zh = "晚霞" if r["event"] == "sunset_glow" else "朝霞"
        line = (f"{r['date']} {event_zh} [{r['checkpoint']}]"
                f" 概率{r['probability_pct']:.0f}%"
                f" 质量{r['quality_pct']:.0f}%"
                f" ({r['llm_status']} {r['created_at']})")
        typer.echo(line)
        if r["llm_status"] == "done" and r["reasoning"]:
            typer.echo(f"  解读: {r['reasoning']}")
```

- [ ] **Step 4: 跑测试确认通过**

Run: `.venv/bin/pytest tests/test_store.py tests/test_cli.py -v`
Expected: 全 PASS

- [ ] **Step 5: Commit**

```bash
git add skyfire/src/skyfire/store.py skyfire/src/skyfire/cli.py skyfire/tests/test_store.py skyfire/tests/test_cli.py
git commit -m "feat(skyfire): latest 命令——零成本查看最近预测记录"
```

---

### Task 8: 全量回归 + 真库迁移验证 + 手动 outlook 冒烟

- [ ] **Step 1: 全量测试**

Run: `cd /Users/feitong/photo-app/skyfire && .venv/bin/pytest -q`
Expected: 全 PASS(基线 177 + 新增 ≈15)

- [ ] **Step 2: 真库迁移验证(先备份)**

```bash
cp data/skyfire.db data/skyfire.db.bak-outlook
.venv/bin/python -c "
from skyfire import store
conn = store.connect('data/skyfire.db')
store.init_db(conn)
sql = conn.execute(\"SELECT sql FROM sqlite_master WHERE name='predictions'\").fetchone()[0]
assert 'outlook' in sql and 'per_model_json' in sql, sql
print('迁移 OK,行数:', conn.execute('SELECT COUNT(*) FROM predictions').fetchone()[0])
"
```

Expected: `迁移 OK,行数: 8`(2026-07-05 的既有 8 行保留)

- [ ] **Step 3: 手动 outlook 冒烟(真跑一次,约1分钟,~$0.02)**

```bash
.venv/bin/skyfire checkpoint --cp outlook --event sunset_glow --date <明天日期 YYYY-MM-DD>
.venv/bin/skyfire latest
```

Expected: 打印明日晚霞 outlook 的概率/质量;latest 列出该记录。

- [ ] **Step 4: Commit(如有冒烟产生的小修)后合并回 main**

按 superpowers:finishing-a-development-branch 流程走(merge 到 main、跑测试、push、删分支)。

---

## Self-Review 记录

- Spec 覆盖:§1→Task 1/2/4,§2→Task 4/6,§3→Task 3,§4→Task 5,§5→Task 3/6,§6→各任务测试,latest(会话追加需求)→Task 7。✓
- 类型一致性:per_model_raw 在 PredictionResult(Task 2)、payload/rec(Task 4)、report(Task 5)、cli 测试 fake(Task 6)四处字段名与结构一致;per_model_json 的 prob/qual 键与 Task 3 测试断言一致。✓
- 已知取舍(执行后修正,原文描述有误):tick 半失败(c1 已跑、outlook 失败)**当晚不补跑**——下一轮 tick 在 c1 判重处 break,不会单独补跑 outlook;晚霞信息由次日 11:00 晚霞 C1 自然补上。推送文案已改为真实语义"数据缺失(后续检查点自动补上)"(commit 4c58e47)。Task 5 的模式缩写按 spec §4 示例用 EC/GFS/ICON/CMA 固定映射(计划样例代码的 split 写法与自身测试断言矛盾,执行时已修正)。
