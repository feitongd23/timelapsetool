# Skyfire Plan C-2:后端预测闭环(百分数检查点 + 反馈学习)实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** tick 全自动跑出每日 C1/C2/C3 百分数预测(概率%/质量%)并推送;`feedback` 一条命令闭合案例并触发 LLM 复盘写经验笔记;无 key 全链路降级不断,`catchup` 补齐;回测出百分数 vs 实际的相关性与命中率。

**Architecture:** 免费层(Open-Meteo 预报 + AWS 卫星实测/外推 + 规则分)每 tick 都算;LLM(Haiku 日常/Sonnet 疑难)只在检查点或 15pp 门控时调用。预测版本化落 `predictions` 表(轨迹保留)。反馈闭合案例后用既有 analyze/llm.explain 通路做"预测轨迹 vs 实际"复盘,笔记进 RAG(Task 11 已通)。

**Tech Stack:** Python 3.12(skyfire/.venv)、httpx、typer、既有模块(engine/consensus/drift/cloudiness/render/himawari_hsd/store/llm/rag/report/schedule)。Spec:`docs/superpowers/specs/2026-07-05-skyfire-prediction-loop-design.md`。

**关键既有接口(已核,勿凭记忆改)**:
- `sun_window(lat,lon,tz,day,event) -> SunWindow(.peak 本地 aware, .azimuth_deg)`
- `compute_prediction(conn,client,city,city_key,event,day,run_llm) -> PredictionResult(index,confidence,spread,per_model,blocked_points,channel_factor,aod,channel_empty,peak,azimuth,llm)`(会归档快照+case)
- `latest_slot(client,now,max_back=6)`、`download_segments(client,ts,"B13",segs,cache)`、`segments_for`、`CROP_BBOX`、`round_down_10min`、`observer_cloudiness(client,peak_utc,event,lat,lon)`、`fetch_case_frames(client,peak_utc,frames_dir,*,prefix,event,lat,lon,azimuth_deg)`
- `load_b13_region(dats,bbox,lat,lon) -> HsdFrame(gray,center_px,km_px)`、`box_cloudiness(gray,center,half)`、`estimate_shift(prev,curr)->(dy,dx)`
- `store`: `cases_with_snapshot(...)->[{case_id,date,actual_score,payload,note}]`、`case_by_key`、`add_case_note/get_case_notes`、`get_frames`、`upsert_case`、`set_actual_score`、`set_sat_cloud`
- `llm`: `MODEL="claude-opus-4-8"`、`interpret`、`explain(card_md,frame_paths,client=None)->str|None`、内部 JSON 解析模式 `re.search(r"\{.*\}", text, re.DOTALL)`
- `rag.factor_vector(payload)`、`rag.similar_cases_from(cases,target,k=3)`
- `report.format_report(PredictionResult)`、`push.push(title,body,cfg)->bool`、`notifyconf.load_notify_config(path)->dict|None`
- `backtest.spearman(xs,ys)`(<3 样本或秩零方差抛 ValueError)
- cli: `_open_db/_parse_date/_make_client/DEFAULT_*`;tick 现走 `due_events`+`was_pushed`(本计划改造 tick,notify/predict 命令保持不动)

**约定**:在 `/Users/feitong/photo-app/skyfire` 下执行;`.venv/bin/pytest`;分支 `feat/skyfire-plan-c2`(从当前 feat/skyfire-plan-d2 继续或先合 main 由执行时决定,不新开 worktree);commit 中文,body 末行 `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`。

---

## 文件结构

| 文件 | 职责 |
|---|---|
| Modify `src/skyfire/store.py` | `predictions` 表(部分唯一索引保 c1/c2/c3 幂等)+ `add_prediction/latest_prediction/has_checkpoint/predictions_for/closed_cases_without_llm_note/pending_predictions` |
| Create `src/skyfire/percent.py` | 免费层 → 概率%/质量% 基线换算(纯函数,公式可解释) |
| Modify `src/skyfire/drift.py` | `projected_box_cloudiness`(观测点云量半拉格朗日外推) |
| Create `src/skyfire/checkpoints.py` | 检查点窗口判定(c1/c2/c3,晚霞/朝霞)+ 门控阈值(纯函数) |
| Modify `src/skyfire/llm.py` | `MODEL_FAST/MODEL_DEEP` + `predict_pct`(JSON 百分数输出,失败 None) |
| Modify `src/skyfire/engine.py` | `run_checkpoint`(免费层组装 + 卫星实测/外推 + 可选 LLM + 落 predictions;门控模式) |
| Modify `src/skyfire/report.py` | `format_pct_report`(百分数推送文案) |
| Modify `src/skyfire/cli.py` | tick 改造为检查点驱动;新增 `checkpoint`(手动/调试)、`feedback`、`catchup` 命令;`backtest --pct` |
| Modify `src/skyfire/backtest.py` | `pct_report`(相关性 + 命中率) |
| Test | `tests/test_percent.py`、`tests/test_checkpoints.py`(新);`tests/test_store.py`(若无则建)、`tests/test_drift.py`、`tests/test_llm.py`、`tests/test_engine.py`、`tests/test_report.py`、`tests/test_backtest.py`、`tests/test_cli.py` 增改 |

---

### Task 1: predictions 表 + store 助手

**Files:** Modify `src/skyfire/store.py`;Test `tests/test_store.py`(不存在则创建)

- [ ] **Step 1: 写失败测试**(创建或追加 `tests/test_store.py`)

```python
from skyfire import store


def _conn():
    c = store.connect(":memory:")
    store.init_db(c)
    return c


def test_prediction_roundtrip_and_latest():
    c = _conn()
    store.add_prediction(c, "2026-07-06", "beijing", "sunset_glow", "c1",
                         probability_pct=60, quality_pct=55, confidence="medium",
                         rule_score=4.2, sat_cloud_pct=None, trend=None,
                         llm_status="pending", reasoning=None, risks=None)
    store.add_prediction(c, "2026-07-06", "beijing", "sunset_glow", "c2",
                         probability_pct=72, quality_pct=64, confidence="high",
                         rule_score=5.0, sat_cloud_pct=48.0, trend="now=48%→burn=52%",
                         llm_status="done", reasoning="通道通", risks="低云")
    latest = store.latest_prediction(c, "2026-07-06", "beijing", "sunset_glow")
    assert latest["checkpoint"] == "c2" and latest["probability_pct"] == 72
    traj = store.predictions_for(c, "2026-07-06", "beijing", "sunset_glow")
    assert [p["checkpoint"] for p in traj] == ["c1", "c2"]


def test_checkpoint_idempotent_but_gated_repeatable():
    c = _conn()
    kw = dict(probability_pct=50, quality_pct=50, confidence="low",
              rule_score=3.0, sat_cloud_pct=None, trend=None,
              llm_status="pending", reasoning=None, risks=None)
    store.add_prediction(c, "2026-07-06", "beijing", "sunset_glow", "c1", **kw)
    assert store.has_checkpoint(c, "2026-07-06", "beijing", "sunset_glow", "c1")
    import pytest, sqlite3
    with pytest.raises(sqlite3.IntegrityError):
        store.add_prediction(c, "2026-07-06", "beijing", "sunset_glow", "c1", **kw)
    # gated 可多次
    store.add_prediction(c, "2026-07-06", "beijing", "sunset_glow", "gated", **kw)
    store.add_prediction(c, "2026-07-06", "beijing", "sunset_glow", "gated", **kw)
    assert len(store.predictions_for(c, "2026-07-06", "beijing", "sunset_glow")) == 3


def test_pending_and_unnoted_queries():
    c = _conn()
    kw = dict(probability_pct=50, quality_pct=50, confidence="low",
              rule_score=3.0, sat_cloud_pct=None, trend=None,
              llm_status="pending", reasoning=None, risks=None)
    store.add_prediction(c, "2026-07-06", "beijing", "sunset_glow", "c1", **kw)
    assert len(store.pending_predictions(c)) == 1
    cid = store.upsert_case(c, "2026-07-01", "beijing", "sunset_glow",
                            rule_score=1.0, confidence="low", source="feedback")
    store.set_actual_score(c, cid, 8.0)
    assert [x["id"] for x in store.closed_cases_without_llm_note(c)] == [cid]
    store.add_case_note(c, cid, "llm", "复盘")
    assert store.closed_cases_without_llm_note(c) == []
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/bin/pytest tests/test_store.py -v`
Expected: FAIL,`AttributeError: ... has no attribute 'add_prediction'`

- [ ] **Step 3: 实现**——SCHEMA 中 `case_notes` 表之后、`idx_frames_dedup` 索引之前插入:

```sql
CREATE TABLE IF NOT EXISTS predictions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  date TEXT NOT NULL,
  city TEXT NOT NULL,
  event TEXT NOT NULL,
  checkpoint TEXT NOT NULL CHECK(checkpoint IN ('c1','c2','c3','gated','manual')),
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
  created_at TEXT DEFAULT (datetime('now'))
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_pred_checkpoint
  ON predictions(date, city, event, checkpoint)
  WHERE checkpoint IN ('c1','c2','c3');
```

store.py 末尾追加:

```python
_PRED_KEYS = ("id", "date", "city", "event", "checkpoint", "probability_pct",
              "quality_pct", "confidence", "rule_score", "sat_cloud_pct",
              "trend", "llm_status", "reasoning", "risks", "created_at")


def add_prediction(conn, date: str, city: str, event: str, checkpoint: str, *,
                   probability_pct: float, quality_pct: float,
                   confidence: str | None, rule_score: float | None,
                   sat_cloud_pct: float | None, trend: str | None,
                   llm_status: str, reasoning: str | None, risks: str | None) -> int:
    cur = conn.execute(
        """INSERT INTO predictions (date, city, event, checkpoint,
             probability_pct, quality_pct, confidence, rule_score,
             sat_cloud_pct, trend, llm_status, reasoning, risks)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (date, city, event, checkpoint, probability_pct, quality_pct,
         confidence, rule_score, sat_cloud_pct, trend, llm_status,
         reasoning, risks))
    conn.commit()
    return cur.lastrowid


def _pred_rows(rows) -> list[dict]:
    return [dict(zip(_PRED_KEYS, r)) for r in rows]


def predictions_for(conn, date: str, city: str, event: str) -> list[dict]:
    rows = conn.execute(
        f"SELECT {','.join(_PRED_KEYS)} FROM predictions"
        " WHERE date=? AND city=? AND event=? ORDER BY id",
        (date, city, event)).fetchall()
    return _pred_rows(rows)


def latest_prediction(conn, date: str, city: str, event: str) -> dict | None:
    rows = predictions_for(conn, date, city, event)
    return rows[-1] if rows else None


def has_checkpoint(conn, date: str, city: str, event: str, checkpoint: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM predictions WHERE date=? AND city=? AND event=? AND checkpoint=?",
        (date, city, event, checkpoint)).fetchone() is not None


def pending_predictions(conn) -> list[dict]:
    rows = conn.execute(
        f"SELECT {','.join(_PRED_KEYS)} FROM predictions"
        " WHERE llm_status='pending' ORDER BY id").fetchall()
    return _pred_rows(rows)


def set_prediction_llm(conn, pred_id: int, status: str,
                       reasoning: str | None = None, risks: str | None = None,
                       probability_pct: float | None = None,
                       quality_pct: float | None = None) -> None:
    row = conn.execute("SELECT probability_pct, quality_pct FROM predictions"
                       " WHERE id=?", (pred_id,)).fetchone()
    p = probability_pct if probability_pct is not None else row[0]
    q = quality_pct if quality_pct is not None else row[1]
    conn.execute(
        """UPDATE predictions SET llm_status=?, reasoning=?, risks=?,
             probability_pct=?, quality_pct=? WHERE id=?""",
        (status, reasoning, risks, p, q, pred_id))
    conn.commit()


def closed_cases_without_llm_note(conn) -> list[dict]:
    """已闭环(有实际分)但还没有 LLM 复盘笔记的案例(catchup 用)。"""
    rows = conn.execute(
        """SELECT id, date, city, event, actual_score FROM cases
           WHERE actual_score IS NOT NULL
             AND NOT EXISTS (SELECT 1 FROM case_notes
                             WHERE case_id=cases.id AND author='llm')
           ORDER BY date""").fetchall()
    return [dict(zip(("id", "date", "city", "event", "actual_score"), r))
            for r in rows]
```

注意:老库迁移——`CREATE TABLE IF NOT EXISTS` + `CREATE UNIQUE INDEX IF NOT EXISTS` 由 `init_db` 的 executescript 自动补建,无需 ALTER。

- [ ] **Step 4: 跑测试确认通过**

Run: `.venv/bin/pytest tests/test_store.py -v` → 3 passed;`.venv/bin/pytest -q` 全绿。

- [ ] **Step 5: Commit**

```bash
git add skyfire/src/skyfire/store.py skyfire/tests/test_store.py
git commit -m "feat(skyfire): predictions 表与版本化预测轨迹(检查点幂等/gated 可重复)"
```

---

### Task 2: 百分数基线换算(percent.py)

**Files:** Create `src/skyfire/percent.py`;Test `tests/test_percent.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_percent.py
from skyfire.percent import baseline_percent


def test_quality_is_rule_times_ten_clamped():
    prob, qual = baseline_percent(4.2, "high", None, None)
    assert qual == 42
    _, q2 = baseline_percent(11.0, "high", None, None)
    assert q2 == 100


def test_confidence_scales_probability():
    p_high, _ = baseline_percent(6.0, "high", None, None)
    p_low, _ = baseline_percent(6.0, "low", None, None)
    assert p_high == 60 and p_low == 42        # 60*0.7


def test_cloud_sweet_zone_bonus_and_cap():
    p_sweet, _ = baseline_percent(6.0, "high", None, 50.0)   # 甜区 → +15
    assert p_sweet == 75
    p_none, _ = baseline_percent(6.0, "high", None, 8.0)     # 没画布 → 封顶 20
    assert p_none == 20
    p_full, _ = baseline_percent(6.0, "high", None, 95.0)    # 满盖 → 封顶 20
    assert p_full == 20


def test_projected_beats_measured_and_bounds():
    # 外推值优先于实测;缺两者不加不减
    p, _ = baseline_percent(6.0, "high", 8.0, 50.0)
    assert p == 75                                            # 用外推 50(甜区)
    p2, q2 = baseline_percent(0.0, "degraded", None, None)
    assert p2 == 0 and q2 == 0
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/bin/pytest tests/test_percent.py -v` → ModuleNotFoundError

- [ ] **Step 3: 实现**

```python
# src/skyfire/percent.py
"""免费层 → 概率%/质量% 基线(spec §3;初版简单可解释,回测迭代)。

质量% = 规则分×10;概率% = 质量% × 一致性系数,再按燃烧时刻云量修正:
甜区(30-70)+15;<15 或 >90(没画布/满盖)封顶 20。云量取外推值,
缺则实测,再缺不修正(knowledge §3.2:燃烧时刻云量以卫星实测/外推为准)。
"""

_CONF_FACTOR = {"high": 1.0, "medium": 0.85, "low": 0.7, "degraded": 0.6}


def _clamp(v: float) -> int:
    return int(round(max(0.0, min(100.0, v))))


def baseline_percent(rule_score: float, confidence: str,
                     sat_cloud_pct: float | None,
                     projected_cloud_pct: float | None) -> tuple[int, int]:
    quality = _clamp(rule_score * 10)
    prob = quality * _CONF_FACTOR.get(confidence, 0.6)
    cloud = projected_cloud_pct if projected_cloud_pct is not None else sat_cloud_pct
    if cloud is not None:
        if cloud < 15 or cloud > 90:
            prob = min(prob, 20.0)
        elif 30 <= cloud <= 70:
            prob += 15
    return _clamp(prob), quality
```

- [ ] **Step 4: 跑测试确认通过** → 4 passed;全量绿。

- [ ] **Step 5: Commit**

```bash
git add skyfire/src/skyfire/percent.py skyfire/tests/test_percent.py
git commit -m "feat(skyfire): 免费层百分数基线(规则分×一致性×燃烧时刻云量修正)"
```

---

### Task 3: 观测点云量外推(drift.projected_box_cloudiness)

**Files:** Modify `src/skyfire/drift.py`;Test `tests/test_drift.py`(读现有文件,追加)

- [ ] **Step 1: 写失败测试**(追加)

```python
import numpy as np

from skyfire.drift import projected_box_cloudiness


def test_projected_box_cloudiness_samples_upstream():
    gray = np.zeros((100, 100), dtype=np.uint8)
    gray[40:60, 10:30] = 255          # 云块在西边(上游)
    center = (50, 50)
    # 云每帧向东移 dx=+10:3 帧后云到 center → 回溯采样 (50-30, 50)=(20,50) 命中云块
    val = projected_box_cloudiness(gray, center, (0, 10), 3, half=8)
    assert val > 80
    # 不外推(0 帧)→ center 现在没云
    assert projected_box_cloudiness(gray, center, (0, 10), 0, half=8) < 10
```

- [ ] **Step 2: 跑测试确认失败** → ImportError

- [ ] **Step 3: 实现**(追加到 drift.py)

```python
def projected_box_cloudiness(gray: np.ndarray, center: tuple[int, int],
                             shift_per_frame: tuple[int, int],
                             frames_ahead: int, half: int = 40) -> float:
    """燃烧时刻观测点上空云量外推:半拉格朗日回溯上游采样(同 corridor 思路)。"""
    dy, dx = shift_per_frame
    cx, cy = center
    return box_cloudiness(gray, (cx - dx * frames_ahead, cy - dy * frames_ahead), half)
```

- [ ] **Step 4: 跑测试确认通过**;全量绿。

- [ ] **Step 5: Commit**

```bash
git add skyfire/src/skyfire/drift.py skyfire/tests/test_drift.py
git commit -m "feat(skyfire): 观测点云量外推(回溯上游采样到燃烧时刻)"
```

---

### Task 4: 检查点窗口 + 门控(checkpoints.py)

**Files:** Create `src/skyfire/checkpoints.py`;Test `tests/test_checkpoints.py`

窗口定义(spec §2):c1 晚霞=当日 11:00 起 2h 窗;c1 朝霞=**前一日 20:00** 起 2h 窗(预测次日清晨);c2=[peak−135min, peak−75min);c3=[peak−55min, peak−20min)。门控阈值 15pp。

- [ ] **Step 1: 写失败测试**

```python
# tests/test_checkpoints.py
from datetime import datetime
from zoneinfo import ZoneInfo

from skyfire.checkpoints import due_checkpoint, gate_exceeded

TZ = ZoneInfo("Asia/Shanghai")


def _t(h, m, d=6):
    return datetime(2026, 7, d, h, m, tzinfo=TZ)


PEAK_SUNSET = _t(19, 40)            # 当日日落
PEAK_SUNRISE = _t(4, 50, d=7)       # 次日日出


def test_sunset_checkpoints():
    assert due_checkpoint(_t(11, 10), PEAK_SUNSET, "sunset_glow") == "c1"
    assert due_checkpoint(_t(13, 30), PEAK_SUNSET, "sunset_glow") is None
    assert due_checkpoint(_t(17, 40), PEAK_SUNSET, "sunset_glow") == "c2"   # peak-2h
    assert due_checkpoint(_t(19, 5), PEAK_SUNSET, "sunset_glow") == "c3"    # peak-35m
    assert due_checkpoint(_t(19, 30), PEAK_SUNSET, "sunset_glow") is None   # <20m
    assert due_checkpoint(_t(9, 0), PEAK_SUNSET, "sunset_glow") is None


def test_sunrise_c1_previous_evening():
    assert due_checkpoint(_t(20, 30, d=6), PEAK_SUNRISE, "sunrise_glow") == "c1"
    assert due_checkpoint(_t(19, 0, d=6), PEAK_SUNRISE, "sunrise_glow") is None
    assert due_checkpoint(_t(3, 0, d=7), PEAK_SUNRISE, "sunrise_glow") == "c2"
    assert due_checkpoint(_t(4, 10, d=7), PEAK_SUNRISE, "sunrise_glow") == "c3"


def test_gate_exceeded():
    assert gate_exceeded(60, 80)          # |Δ|=20 > 15
    assert not gate_exceeded(60, 70)
    assert not gate_exceeded(None, 70)    # 无历史 → 不门控(等检查点)
```

- [ ] **Step 2: 跑测试确认失败** → ModuleNotFoundError

- [ ] **Step 3: 实现**

```python
# src/skyfire/checkpoints.py
"""检查点窗口判定与门控(spec §2)。纯函数,不碰网络/DB。

c1 早间展望(朝霞在前一晚)/ c2 T-2h / c3 T-40min;之间由门控
(概率摆动 > GATE_PP)决定是否加跑 LLM。窗口内是否已跑由调用方
用 store.has_checkpoint 判重。
"""
from datetime import datetime, timedelta

GATE_PP = 15.0
_C1_WINDOW_H = 2

C2_START, C2_END = 135, 75    # peak 前分钟数区间 [start, end)
C3_START, C3_END = 55, 20


def _c1_start(peak_local: datetime, event: str) -> datetime:
    if event == "sunset_glow":
        return peak_local.replace(hour=11, minute=0, second=0, microsecond=0)
    prev = peak_local - timedelta(days=1)
    return prev.replace(hour=20, minute=0, second=0, microsecond=0)


def due_checkpoint(now_local: datetime, peak_local: datetime,
                   event: str) -> str | None:
    c1 = _c1_start(peak_local, event)
    if c1 <= now_local < c1 + timedelta(hours=_C1_WINDOW_H):
        return "c1"
    to_peak = (peak_local - now_local).total_seconds() / 60
    if C2_END < to_peak <= C2_START:
        return "c2"
    if C3_END < to_peak <= C3_START:
        return "c3"
    return None


def gate_exceeded(prev_prob: float | None, new_prob: float,
                  threshold: float = GATE_PP) -> bool:
    if prev_prob is None:
        return False
    return abs(new_prob - prev_prob) > threshold
```

- [ ] **Step 4: 跑测试确认通过** → 3 passed;全量绿。

- [ ] **Step 5: Commit**

```bash
git add skyfire/src/skyfire/checkpoints.py skyfire/tests/test_checkpoints.py
git commit -m "feat(skyfire): 检查点窗口判定(c1/c2/c3 晚霞朝霞)与 15pp 门控"
```

---

### Task 5: llm.predict_pct(百分数 JSON 输出,模型分层)

**Files:** Modify `src/skyfire/llm.py`;Test `tests/test_llm.py`

- [ ] **Step 1: 写失败测试**(追加;复用文件里已有的 `_FakeClient` 造型——先读现有测试,其 fake 构造函数直接收文本)

```python
from skyfire.llm import MODEL_DEEP, MODEL_FAST, predict_pct


def test_predict_pct_parses_json():
    text = ('{"probability_pct": 72, "quality_pct": 64,'
            ' "reasoning": "通道通+画布甜区", "risks": "低云带",'
            ' "confidence": "high"}')
    r = predict_pct({"rule_score": 5.0}, [], [], client=_FakeClient(text))
    assert r == {"probability_pct": 72.0, "quality_pct": 64.0,
                 "reasoning": "通道通+画布甜区", "risks": "低云带",
                 "confidence": "high"}


def test_predict_pct_rejects_out_of_range_and_failures():
    bad = '{"probability_pct": 140, "quality_pct": 50, "reasoning": "", "risks": "", "confidence": "low"}'
    assert predict_pct({}, [], [], client=_FakeClient(bad)) is None

    class _Boom:
        def __getattr__(self, name):
            raise RuntimeError
    assert predict_pct({}, [], [], client=_Boom()) is None


def test_model_tiers_exist():
    assert MODEL_FAST.startswith("claude-haiku")
    assert MODEL_DEEP.startswith("claude-sonnet")
```

(若现有 `_FakeClient` 签名不同,按其真实造型适配调用——不许改弱断言。)

- [ ] **Step 2: 跑测试确认失败** → ImportError

- [ ] **Step 3: 实现**(追加到 llm.py)

```python
MODEL_FAST = "claude-haiku-4-5-20251001"   # 日常检查点
MODEL_DEEP = "claude-sonnet-5"             # 疑难升级(spec §4)

_PREDICT_SYSTEM = (
    "你是资深火烧云预报员。给你免费层数据(多模式预报/规则分/卫星实测与"
    "外推云量/趋势)、相似历史案例及经验笔记、当天判读云图。判读口径:"
    "透光通道是否被低云堵(高云盖顶不算堵)、云幕是否连贯成片的中高云带破口"
    "(零碎小块不算画布)、燃烧时刻云量以卫星实测/外推为准(预报数字只当"
    "趋势底子)、空气与湿度压色、雨后初晴利好。只输出 JSON:"
    '{"probability_pct": 0-100, "quality_pct": 0-100,'
    ' "reasoning": 两三句中文, "risks": 一句最大风险,'
    ' "confidence": "high|medium|low"}'
)


def predict_pct(payload: dict, similar: list[dict], frame_paths: list[Path],
                model: str = MODEL_FAST, client=None) -> dict | None:
    """检查点预测:免费层+案例+云图 → 百分数 JSON。失败静默 None(spec 8)。"""
    try:
        if client is None:
            import anthropic
            client = anthropic.Anthropic()
        lines = [f"免费层数据: {json.dumps(payload, ensure_ascii=False)}",
                 "历史相似案例(含经验笔记):"]
        for c in similar:
            lines.append(f"- {c['date']} 实际 {c['actual_score']} 分"
                         f" 因子 {json.dumps(c.get('payload', {}), ensure_ascii=False)}")
            if c.get("note"):
                lines.append(f"  经验笔记: {c['note'][:120]}")
        if not similar:
            lines.append("- (暂无)")
        content: list[dict] = [{"type": "text", "text": "\n".join(lines)}]
        for p in frame_paths[:6]:
            data = base64.standard_b64encode(Path(p).read_bytes()).decode()
            content.append({"type": "image",
                            "source": {"type": "base64", "media_type": "image/png",
                                       "data": data}})
        resp = client.messages.create(
            model=model, max_tokens=1500, thinking={"type": "adaptive"},
            system=_PREDICT_SYSTEM,
            messages=[{"role": "user", "content": content}])
        text = next((b.text for b in resp.content if b.type == "text"), "")
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if not m:
            return None
        d = json.loads(m.group(0))
        prob, qual = float(d["probability_pct"]), float(d["quality_pct"])
        if not (0 <= prob <= 100 and 0 <= qual <= 100):
            return None
        return {"probability_pct": prob, "quality_pct": qual,
                "reasoning": str(d.get("reasoning", "")),
                "risks": str(d.get("risks", "")),
                "confidence": str(d.get("confidence", "medium"))}
    except Exception:
        return None
```

- [ ] **Step 4: 跑测试确认通过**;全量绿。

- [ ] **Step 5: Commit**

```bash
git add skyfire/src/skyfire/llm.py skyfire/tests/test_llm.py
git commit -m "feat(skyfire): predict_pct 百分数预测调用(Haiku 日常/Sonnet 疑难)"
```

---

### Task 6: engine.run_checkpoint(免费层组装 + LLM + 落库 + 门控)

**Files:** Modify `src/skyfire/engine.py`;Test `tests/test_engine.py`(追加)

- [ ] **Step 1: 写失败测试**(追加;engine 现有测试用 monkeypatch 风格,沿用)

```python
from datetime import date as date_type

import skyfire.engine as engine_mod
from skyfire import store
from skyfire.config import City
from skyfire.engine import PredictionResult, run_checkpoint


def _fake_pr(index=5.0, confidence="high"):
    from datetime import datetime, timezone
    return PredictionResult(
        city_name="北京", event="sunset_glow", day=date_type(2026, 7, 6),
        index=index, confidence=confidence, spread=1.0,
        per_model={"gfs_seamless": index}, blocked_points=0, channel_factor=1.0,
        aod=0.3, channel_empty=False,
        peak=datetime(2026, 7, 6, 19, 40, tzinfo=timezone.utc), azimuth=295.0,
        llm=None)


def _setup(monkeypatch, llm_result):
    monkeypatch.setattr(engine_mod, "compute_prediction",
                        lambda *a, **k: _fake_pr())
    monkeypatch.setattr(engine_mod, "observe_burn_clouds",
                        lambda *a, **k: (48.0, 52.0, "now=48%→burn=52%", []))
    monkeypatch.setattr(engine_mod, "predict_pct", lambda *a, **k: llm_result)
    conn = store.connect(":memory:")
    store.init_db(conn)
    city = City(key="beijing", name="北京", lat=39.9, lon=116.4,
                timezone="Asia/Shanghai")
    return conn, city


def test_run_checkpoint_llm_done(monkeypatch):
    llm = {"probability_pct": 72.0, "quality_pct": 64.0, "reasoning": "通",
           "risks": "低云", "confidence": "high"}
    conn, city = _setup(monkeypatch, llm)
    rec = run_checkpoint(conn, object(), city, "beijing", "sunset_glow",
                         date_type(2026, 7, 6), "c2")
    assert rec["probability_pct"] == 72 and rec["llm_status"] == "done"
    assert store.has_checkpoint(conn, "2026-07-06", "beijing", "sunset_glow", "c2")


def test_run_checkpoint_no_llm_pending(monkeypatch):
    conn, city = _setup(monkeypatch, None)      # LLM 失败/无 key
    rec = run_checkpoint(conn, object(), city, "beijing", "sunset_glow",
                         date_type(2026, 7, 6), "c1")
    assert rec["llm_status"] == "pending"
    # 免费层基线:rule 5.0 high → qual 50;外推 52 甜区 → prob 50+15=65
    assert rec["probability_pct"] == 65 and rec["quality_pct"] == 50


def test_run_checkpoint_gated_skips_small_delta(monkeypatch):
    conn, city = _setup(monkeypatch, None)
    run_checkpoint(conn, object(), city, "beijing", "sunset_glow",
                   date_type(2026, 7, 6), "c1")            # 落一版 prob=65
    rec = run_checkpoint(conn, object(), city, "beijing", "sunset_glow",
                         date_type(2026, 7, 6), "gated", gate=True)
    assert rec is None                                      # Δ=0 < 15pp,不落库
    assert len(store.predictions_for(conn, "2026-07-06", "beijing",
                                     "sunset_glow")) == 1
```

- [ ] **Step 2: 跑测试确认失败** → ImportError run_checkpoint

- [ ] **Step 3: 实现**(追加到 engine.py;新增 imports:`from skyfire.checkpoints import gate_exceeded`、`from skyfire.percent import baseline_percent`、`from skyfire.llm import predict_pct`、`from skyfire.himawari_hsd import CROP_BBOX, download_segments, latest_slot, round_down_10min, segments_for`、`from skyfire.render import load_b13_region, render_annotated`、`from skyfire.cloudiness import box_cloudiness`、`from skyfire.drift import estimate_shift, projected_box_cloudiness`、`from skyfire.rag import factor_vector, similar_cases_from` 已有、`from datetime import timedelta, timezone` 补全)

```python
def observe_burn_clouds(client, peak_utc, event: str, lat: float, lon: float,
                        frames_dir: Path,
                        ) -> tuple[float | None, float | None, str | None, list[Path]]:
    """实况层:当前实测云量、外推到燃烧时刻云量、趋势文本、判读图路径。

    尽力语义:卫星缺 → (None, None, None, [])。
    """
    try:
        from datetime import datetime as _dt
        now = _dt.now(timezone.utc)
        ts1 = latest_slot(client, now)
        if ts1 is None:
            return None, None, None, []
        segs = segments_for(CROP_BBOX[1], CROP_BBOX[3],
                            (CROP_BBOX[0] + CROP_BBOX[2]) / 2)
        cache = Path(frames_dir) / "hsd_cache"
        dats1 = download_segments(client, ts1, "B13", segs, cache)
        if not dats1:
            return None, None, None, []
        f1 = load_b13_region(dats1, CROP_BBOX, lat, lon)
        now_pct = box_cloudiness(f1.gray, f1.center_px, half=40)
        ts0 = round_down_10min(ts1 - timedelta(minutes=10))
        dats0 = download_segments(client, ts0, "B13", segs, cache)
        frames_ahead = max(0.0, (peak_utc - ts1).total_seconds() / 600)
        if dats0:
            f0 = load_b13_region(dats0, CROP_BBOX, lat, lon)
            shift = estimate_shift(f0.gray, f1.gray)
        else:
            shift = (0, 0)
        burn_pct = projected_box_cloudiness(f1.gray, f1.center_px, shift,
                                            round(frames_ahead), half=40)
        png = Path(frames_dir) / "live" / f"live_{ts1:%Y%m%d_%H%M}.png"
        from skyfire.suntimes import sun_window as _sw  # 方位角已由调用方传入更好;此处仅存图
        render_annotated(dats1, "B13", CROP_BBOX, png, lat=lat, lon=lon,
                         azimuth_deg=270.0 if event == "sunset_glow" else 90.0)
        trend = f"now={now_pct:.0f}%→burn={burn_pct:.0f}%"
        return round(now_pct, 1), round(burn_pct, 1), trend, [png]
    except (httpx.HTTPError, OSError):
        return None, None, None, []


def run_checkpoint(conn, client, city: City, city_key: str, event: str,
                   day, checkpoint: str, *, gate: bool = False,
                   frames_dir: Path = Path("data/frames"),
                   model: str | None = None) -> dict | None:
    """一个检查点:免费层 → (门控)→ LLM → 落 predictions,返回记录。

    gate=True 时先算免费层基线,与最新一版比较,|Δ概率|≤15pp → 返回 None
    (不落库不调 LLM)。LLM 失败/无 key → 基线落库 llm_status='pending'。
    """
    r = compute_prediction(conn, client, city, city_key, event, day,
                           run_llm=False)
    peak_utc = r.peak.astimezone(timezone.utc)
    sat_now, burn_pct, trend, live_frames = observe_burn_clouds(
        client, peak_utc, event, city.lat, city.lon, frames_dir)
    prob, qual = baseline_percent(r.index, r.confidence, sat_now, burn_pct)

    if gate:
        last = store.latest_prediction(conn, str(day), city_key, event)
        if not gate_exceeded(last["probability_pct"] if last else None, prob):
            return None

    payload = {"date": str(day), "event": event, "checkpoint": checkpoint,
               "rule_score": r.index, "confidence": r.confidence,
               "per_model": r.per_model, "aod": r.aod,
               "sat_cloud_now": sat_now, "burn_cloud_projected": burn_pct,
               "trend": trend, "baseline_prob": prob, "baseline_quality": qual}
    cases = store.cases_with_snapshot(conn, city_key, event, model="gfs_seamless")
    similar = similar_cases_from(cases, factor_vector(payload), k=3)
    llm_r = predict_pct(payload, similar, live_frames,
                        model=model or _pick_model())
    if llm_r is not None:
        rec = dict(probability_pct=llm_r["probability_pct"],
                   quality_pct=llm_r["quality_pct"],
                   confidence=llm_r["confidence"], llm_status="done",
                   reasoning=llm_r["reasoning"], risks=llm_r["risks"])
    else:
        rec = dict(probability_pct=prob, quality_pct=qual,
                   confidence=r.confidence, llm_status="pending",
                   reasoning=None, risks=None)
    pred_id = store.add_prediction(
        conn, str(day), city_key, event, checkpoint,
        probability_pct=rec["probability_pct"], quality_pct=rec["quality_pct"],
        confidence=rec["confidence"], rule_score=r.index,
        sat_cloud_pct=sat_now, trend=trend, llm_status=rec["llm_status"],
        reasoning=rec["reasoning"], risks=rec["risks"])
    return {**rec, "id": pred_id, "date": str(day), "city": city_key,
            "event": event, "checkpoint": checkpoint, "rule_score": r.index,
            "sat_cloud_pct": sat_now, "trend": trend, "peak": r.peak,
            "city_name": city.name}


def _pick_model() -> str:
    from skyfire.llm import MODEL_FAST
    return MODEL_FAST
```

注意:`observe_burn_clouds` 里 azimuth 用粗值(西/东)仅供 live 图标注;测试全程 monkeypatch 该函数,不触网络。`factor_vector` 对缺失字段中性处理,payload 键不齐无妨。

- [ ] **Step 4: 跑测试确认通过** → 3 passed;全量绿。

- [ ] **Step 5: Commit**

```bash
git add skyfire/src/skyfire/engine.py skyfire/tests/test_engine.py
git commit -m "feat(skyfire): run_checkpoint 检查点预测(免费层+实况外推+LLM+门控+落库)"
```

---

### Task 7: 百分数推送文案 + tick 检查点化 + checkpoint 手动命令

**Files:** Modify `src/skyfire/report.py`、`src/skyfire/cli.py`;Test `tests/test_report.py`、`tests/test_cli.py`

- [ ] **Step 1: 写失败测试**

`tests/test_report.py` 追加:

```python
from skyfire.report import format_pct_report


def test_format_pct_report():
    rec = {"date": "2026-07-06", "event": "sunset_glow", "checkpoint": "c2",
           "probability_pct": 72.0, "quality_pct": 64.0, "confidence": "high",
           "rule_score": 5.0, "sat_cloud_pct": 48.0,
           "trend": "now=48%→burn=52%", "llm_status": "done",
           "reasoning": "通道通", "risks": "低云带", "city_name": "北京"}
    title, body = format_pct_report(rec)
    assert "概率72%" in title and "质量64%" in title and "北京" in title
    assert "C2" in body and "now=48%→burn=52%" in body and "通道通" in body


def test_format_pct_report_pending():
    rec = {"date": "2026-07-06", "event": "sunrise_glow", "checkpoint": "c1",
           "probability_pct": 40.0, "quality_pct": 35.0, "confidence": "low",
           "rule_score": 3.5, "sat_cloud_pct": None, "trend": None,
           "llm_status": "pending", "reasoning": None, "risks": None,
           "city_name": "北京"}
    title, body = format_pct_report(rec)
    assert "朝霞" in title and "AI 解读待补" in body
```

`tests/test_cli.py` 追加(读现有 tick 测试的 monkeypatch 风格后适配;关键断言如下):

```python
def test_tick_runs_due_checkpoint_and_pushes(tmp_path, monkeypatch):
    import skyfire.cli as cli
    pushed = []
    monkeypatch.setattr(cli, "load_notify_config",
                        lambda p: {"provider": "bark", "key": "k"})
    monkeypatch.setattr(cli, "push", lambda t, b, cfg: pushed.append(t) or True)
    monkeypatch.setattr(cli, "due_checkpoint", lambda now, peak, ev:
                        "c1" if ev == "sunset_glow" else None)
    rec = {"probability_pct": 65.0, "quality_pct": 50.0, "confidence": "high",
           "llm_status": "pending", "reasoning": None, "risks": None,
           "date": "2026-07-06", "event": "sunset_glow", "checkpoint": "c1",
           "rule_score": 5.0, "sat_cloud_pct": None, "trend": None,
           "city_name": "北京"}
    calls = []
    monkeypatch.setattr(cli, "run_checkpoint",
                        lambda *a, **k: calls.append((a, k)) or rec)
    from typer.testing import CliRunner
    db = tmp_path / "t.db"
    result = CliRunner().invoke(cli.app, ["tick", "--db", str(db)])
    assert result.exit_code == 0
    assert len(pushed) == 1 and "概率65%" in pushed[0]
    # gated 检查:非检查点时刻应以 gate=True 调 run_checkpoint(本调用 c1,不验 gated)


def test_tick_skips_already_run_checkpoint(tmp_path, monkeypatch):
    import skyfire.cli as cli
    from skyfire import store
    monkeypatch.setattr(cli, "load_notify_config",
                        lambda p: {"provider": "bark", "key": "k"})
    monkeypatch.setattr(cli, "push", lambda t, b, cfg: True)
    monkeypatch.setattr(cli, "due_checkpoint", lambda now, peak, ev:
                        "c1" if ev == "sunset_glow" else None)
    called = []
    monkeypatch.setattr(cli, "run_checkpoint", lambda *a, **k: called.append(1))
    db = tmp_path / "t.db"
    conn = store.connect(db); store.init_db(conn)
    from datetime import date as _d
    today = str(_d.today())
    store.add_prediction(conn, today, "beijing", "sunset_glow", "c1",
                         probability_pct=50, quality_pct=50, confidence="low",
                         rule_score=3.0, sat_cloud_pct=None, trend=None,
                         llm_status="pending", reasoning=None, risks=None)
    from typer.testing import CliRunner
    result = CliRunner().invoke(cli.app, ["tick", "--db", str(db)])
    assert result.exit_code == 0 and called == []   # 幂等:已跑过不重跑
```

注意:tick 用"事件当日"(峰值所在的本地日期)作 predictions.date——朝霞 c1 在前一晚跑,date 记**次日**。测试一(c1 sunset)date=今天成立;若 tick 实现取 `str(win.peak.astimezone(城市时区).date())`,两测试均按今天日落走,一致。

- [ ] **Step 2: 跑测试确认失败**

- [ ] **Step 3: 实现 report.format_pct_report**(追加 report.py)

```python
def format_pct_report(rec: dict) -> tuple[str, str]:
    """百分数检查点 → 推送标题/正文(spec §3)。rec 为 run_checkpoint 返回。"""
    event_zh = "晚霞" if rec["event"] == "sunset_glow" else "朝霞"
    title = (f"{event_zh} 概率{rec['probability_pct']:.0f}%"
             f" 质量{rec['quality_pct']:.0f}% — {rec['city_name']}")
    lines = [
        f"{rec['date']} {rec['city_name']}{event_zh}"
        f"[{rec['checkpoint'].upper()}] 概率 {rec['probability_pct']:.0f}%"
        f" 质量 {rec['quality_pct']:.0f}%",
        f"置信: {_CONF_ZH.get(rec['confidence'], rec['confidence'])}"
        f"  规则分 {rec['rule_score']}",
    ]
    if rec.get("trend"):
        lines.append(f"云量趋势: {rec['trend']}")
    if rec.get("llm_status") == "done":
        lines.append(f"解读: {rec['reasoning']}")
        lines.append(f"风险: {rec['risks']}")
    else:
        lines.append("AI 解读待补(无凭证或调用失败),以上为免费层基线")
    return title, "\n".join(lines)
```

- [ ] **Step 4: 改造 cli.tick + 新增 checkpoint 命令**

cli.py imports 增:`from skyfire.checkpoints import due_checkpoint`、`from skyfire.engine import compute_prediction, run_checkpoint`(合并现有行)、`from skyfire.report import format_pct_report, format_report`。

`tick` 函数体替换为:

```python
    ncfg = load_notify_config(notify_config)
    if ncfg is None:
        return  # 未配置推送:静默退出(launchd 频繁调用,不刷错误)
    cities = load_cities(config)
    conn = _open_db(db)
    now = datetime.now(timezone.utc)
    for city_key, c in cities.items():
        from zoneinfo import ZoneInfo
        now_local = now.astimezone(ZoneInfo(c.timezone))
        for event in ("sunset_glow", "sunrise_glow"):
            for day_offset in (0, 1):
                day = (now_local + timedelta(days=day_offset)).date()
                win = sun_window(c.lat, c.lon, c.timezone, day, event)
                cp = due_checkpoint(now_local, win.peak, event)
                pred_date = str(win.peak.date())
                client = _make_client()
                try:
                    if cp is not None:
                        if store.has_checkpoint(conn, pred_date, city_key,
                                                event, cp):
                            continue
                        rec = run_checkpoint(conn, client, c, city_key, event,
                                             win.peak.date(), cp)
                    else:
                        # 检查点之间:c1 之后到峰值前,免费层门控
                        c1_done = store.has_checkpoint(conn, pred_date,
                                                       city_key, event, "c1")
                        to_peak = (win.peak - now_local).total_seconds() / 60
                        if not (c1_done and 0 < to_peak):
                            continue
                        rec = run_checkpoint(conn, client, c, city_key, event,
                                             win.peak.date(), "gated", gate=True)
                    if rec is None:
                        continue
                    title, body = format_pct_report(rec)
                    push(title, body, ncfg)
                    typer.echo(f"✓ {city_key} {event} [{rec['checkpoint']}]"
                               f" {title}")
                except (httpx.HTTPError, ValueError):
                    continue  # 单城失败不影响其他(spec 8)
                break  # 该 event 已按其中一天处理,不再看另一天
```

新增手动命令(便于调试与 E2E):

```python
@app.command()
def checkpoint(
    cp: str = typer.Option("manual", help="c1|c2|c3|gated|manual"),
    city: str = typer.Option("beijing"),
    event: str = typer.Option("sunset_glow"),
    date: str = typer.Option(None, help="YYYY-MM-DD,默认今天"),
    config: Path = typer.Option(DEFAULT_CONFIG),
    db: Path = typer.Option(DEFAULT_DB),
):
    """手动跑一个预测检查点(调试/补跑)。"""
    cities = load_cities(config)
    if city not in cities:
        typer.echo(f"错误:未知城市 {city!r}", err=True)
        raise typer.Exit(1)
    day = _parse_date(date, date_type.today())
    conn = _open_db(db)
    rec = run_checkpoint(conn, _make_client(), cities[city], city, event,
                         day, cp)
    if rec is None:
        typer.echo("门控未触发,无更新")
        return
    title, body = format_pct_report(rec)
    typer.echo(title)
    typer.echo(body)
```

旧 tick 的 `due_events`/`was_pushed`/`format_report` 流程被替换;`from skyfire.schedule import due_events` 与 `DEFAULT_LEAD_MINUTES` 导入若不再被用则删(notify 命令仍用 `format_report`,保留)。**旧 tick 测试**(若有 `test_tick_*`)按新流程改写或由上面两条新测试替代——保留等价覆盖(配置缺失静默退出的测试若存在,保持)。

- [ ] **Step 5: 跑测试确认通过**;全量绿(修任何 tick 旧测试,如实报告改动)。

- [ ] **Step 6: Commit**

```bash
git add skyfire/src/skyfire/report.py skyfire/src/skyfire/cli.py skyfire/tests/
git commit -m "feat(skyfire): tick 检查点化(c1/c2/c3+门控)与百分数推送,checkpoint 手动命令"
```

---

### Task 8: feedback 命令(闭案例 + 照片 + 触发复盘)

**Files:** Modify `src/skyfire/cli.py`、`src/skyfire/analyze.py`;Test `tests/test_cli.py`、`tests/test_analyze.py`

- [ ] **Step 1: 写失败测试**

`tests/test_analyze.py` 追加(预测轨迹进案例卡):

```python
def test_case_card_appends_prediction_trajectory():
    conn = store.connect(":memory:")
    store.init_db(conn)
    cid = _mk_case(conn)
    store.add_prediction(conn, "2026-05-06", "beijing", "sunset_glow", "c1",
                         probability_pct=40, quality_pct=35, confidence="low",
                         rule_score=3.5, sat_cloud_pct=None, trend=None,
                         llm_status="pending", reasoning=None, risks=None)
    store.add_prediction(conn, "2026-05-06", "beijing", "sunset_glow", "c3",
                         probability_pct=80, quality_pct=75, confidence="high",
                         rule_score=5.0, sat_cloud_pct=54.0, trend="now=54%→burn=50%",
                         llm_status="done", reasoning="通道通", risks="-")
    from skyfire.analyze import format_trajectory
    txt = format_trajectory(store.predictions_for(conn, "2026-05-06",
                                                  "beijing", "sunset_glow"))
    assert "C1 概率40% 质量35%" in txt and "C3 概率80% 质量75%" in txt
```

`tests/test_cli.py` 追加:

```python
def test_feedback_closes_case_saves_photo_and_triggers_retro(tmp_path, monkeypatch):
    import skyfire.cli as cli
    from skyfire import store
    db = tmp_path / "t.db"
    conn = store.connect(db); store.init_db(conn)
    store.upsert_case(conn, "2026-07-06", "beijing", "sunset_glow",
                      rule_score=5.0, confidence="high", source="auto")
    photo = tmp_path / "shot.jpg"; photo.write_bytes(b"jpg")
    monkeypatch.setattr(cli, "explain", lambda card, paths: "复盘:预测偏低,通道其实开")
    monkeypatch.setattr(cli, "_ensure_case_frames", lambda *a, **k: 0)
    from typer.testing import CliRunner
    result = CliRunner().invoke(cli.app, [
        "feedback", "--date", "2026-07-06", "--score", "9",
        "--photo", str(photo), "--db", str(db),
        "--photos-dir", str(tmp_path / "photos")])
    assert result.exit_code == 0
    case = store.case_by_key(conn, "2026-07-06", "beijing", "sunset_glow")
    assert case["actual_score"] == 9.0
    notes = store.get_case_notes(conn, case["id"])
    assert notes and notes[-1]["author"] == "llm"
    saved = list((tmp_path / "photos").glob("*"))
    assert len(saved) == 1
    row = conn.execute("SELECT path FROM photos WHERE case_id=?",
                       (case["id"],)).fetchone()
    assert row and str(tmp_path / "photos") in row[0]


def test_feedback_no_llm_leaves_pending(tmp_path, monkeypatch):
    import skyfire.cli as cli
    from skyfire import store
    db = tmp_path / "t.db"
    conn = store.connect(db); store.init_db(conn)
    monkeypatch.setattr(cli, "explain", lambda card, paths: None)   # 无 key
    monkeypatch.setattr(cli, "_ensure_case_frames", lambda *a, **k: 0)
    from typer.testing import CliRunner
    result = CliRunner().invoke(cli.app, [
        "feedback", "--date", "2026-07-06", "--wrong", "--db", str(db)])
    assert result.exit_code == 0
    assert "待补" in result.output
    case = store.case_by_key(conn, "2026-07-06", "beijing", "sunset_glow")
    assert case is not None                     # 案例被创建
    assert store.get_case_notes(conn, case["id"]) == []   # 笔记 pending(无)
```

- [ ] **Step 2: 跑测试确认失败**

- [ ] **Step 3: 实现**

`analyze.py` 追加:

```python
def format_trajectory(preds: list[dict]) -> str:
    """预测轨迹 → 复盘输入文本(哪版对哪版错,教训在轨迹里)。"""
    if not preds:
        return "(当日无预测记录)"
    lines = ["## 预测轨迹"]
    for p in preds:
        lines.append(
            f"- {p['checkpoint'].upper()} 概率{p['probability_pct']:.0f}%"
            f" 质量{p['quality_pct']:.0f}% 规则分{p['rule_score']}"
            f" 实测云量{p['sat_cloud_pct']}% 趋势{p['trend']}"
            f" [{p['llm_status']}]")
    return "\n".join(lines)
```

`cli.py` 追加(imports 增 `import shutil`、`from skyfire.analyze import build_case_card, format_trajectory`、`from skyfire.llm import explain`、`from skyfire.himawari_hsd import fetch_case_frames, observer_cloudiness` 已在或合并):

```python
DEFAULT_PHOTOS = Path(__file__).parent.parent.parent / "data" / "photos"


def _ensure_case_frames(conn, client, case_id: int, city, city_key: str,
                        event: str, day) -> int:
    """反馈闭环:该案例还没有卫星帧则回填(尽力),返回新增帧数。"""
    if store.get_frames(conn, case_id):
        return 0
    win = sun_window(city.lat, city.lon, city.timezone, day, 
                     "sunrise_glow" if event == "cloud_sea" else event)
    peak_utc = win.peak.astimezone(timezone.utc)
    prefix = f"{city_key}_{day}_{event}"
    saved = 0
    for ts, ch, path in fetch_case_frames(
            client, peak_utc, DEFAULT_FRAMES, prefix=prefix, event=event,
            lat=city.lat, lon=city.lon, azimuth_deg=win.azimuth_deg):
        store.add_satellite_frame(conn, case_id, ts.isoformat(), ch, str(path))
        saved += 1
    pct = observer_cloudiness(client, peak_utc, event, city.lat, city.lon)
    if pct is not None:
        store.set_sat_cloud(conn, case_id, pct)
    return saved


@app.command()
def feedback(
    date: str = typer.Option(..., help="案例日期 YYYY-MM-DD"),
    city: str = typer.Option("beijing"),
    event: str = typer.Option("sunset_glow"),
    score: float = typer.Option(None, help="实际得分 0-10"),
    photo: Path = typer.Option(None, help="实拍照片路径"),
    wrong: bool = typer.Option(False, "--wrong", help="仅标记'预报不准'"),
    config: Path = typer.Option(DEFAULT_CONFIG),
    db: Path = typer.Option(DEFAULT_DB),
    photos_dir: Path = typer.Option(DEFAULT_PHOTOS),
):
    """反馈闭环:落实际得分/照片 → 自动复盘写经验笔记(spec §5)。"""
    if score is None and photo is None and not wrong:
        typer.echo("错误:至少给 --score / --photo / --wrong 之一", err=True)
        raise typer.Exit(1)
    cities = load_cities(config)
    if city not in cities:
        typer.echo(f"错误:未知城市 {city!r}", err=True)
        raise typer.Exit(1)
    c = cities[city]
    day = _parse_date(date, None)
    conn = _open_db(db)
    case = store.case_by_key(conn, date, city, event)
    if case is None:
        cid = store.upsert_case(conn, date, city, event, rule_score=None,
                                confidence=None, source="feedback")
    else:
        cid = case["id"]
    if score is not None:
        store.set_actual_score(conn, cid, score)
    photo_saved = None
    if photo is not None:
        photos_dir.mkdir(parents=True, exist_ok=True)
        photo_saved = photos_dir / f"{city}_{date}_{event}{photo.suffix}"
        shutil.copy(photo, photo_saved)
        conn.execute("INSERT INTO photos (case_id, score, path) VALUES (?,?,?)",
                     (cid, score, str(photo_saved)))
        conn.commit()
    typer.echo(f"✓ 已记录反馈: {date} {event}"
               + (f" 实际 {score} 分" if score is not None else " (预报不准)"))

    client = _make_client()
    n = _ensure_case_frames(conn, client, cid, c, city, event, day)
    if n:
        typer.echo(f"✓ 已补当日卫星帧 {n} 张")
    case = store.case_by_key(conn, date, city, event)
    card = build_case_card(case, store.get_snapshots(conn, cid),
                           store.get_frames(conn, cid),
                           store.get_case_notes(conn, cid))
    card += "\n\n" + format_trajectory(store.predictions_for(conn, date,
                                                             city, event))
    if wrong and score is None:
        card += "\n\n(用户反馈:预报不准,实际得分未知)"
    paths = [Path(f["path"]) for f in store.get_frames(conn, cid)
             if Path(f["path"]).exists()]
    if photo_saved is not None:
        paths.append(photo_saved)
    result = explain(card, paths)
    if result is None:
        typer.echo("AI 复盘待补(无凭证或调用失败),稍后 skyfire catchup 补跑")
        return
    store.add_case_note(conn, cid, "llm", result)
    typer.echo("===== AI 复盘 =====\n" + result)
```

- [ ] **Step 4: 跑测试确认通过**;全量绿。

- [ ] **Step 5: Commit**

```bash
git add skyfire/src/skyfire/cli.py skyfire/src/skyfire/analyze.py skyfire/tests/
git commit -m "feat(skyfire): feedback 反馈闭环(闭案例+照片+预测轨迹复盘入笔记)"
```

---

### Task 9: catchup 命令(补跑 pending)

**Files:** Modify `src/skyfire/cli.py`;Test `tests/test_cli.py`

语义(spec §4 落地):①已闭环但无 LLM 笔记的案例 → 补复盘;②`llm_status='pending'` 的预测:**当日**的重跑最新检查点补数,**过期**的标 `skipped`(时过境迁,输入已不可复现,如实记录降级)。

- [ ] **Step 1: 写失败测试**(追加 tests/test_cli.py)

```python
def test_catchup_retro_notes_and_prediction_pending(tmp_path, monkeypatch):
    import skyfire.cli as cli
    from skyfire import store
    db = tmp_path / "t.db"
    conn = store.connect(db); store.init_db(conn)
    # 1) 闭环无笔记案例
    cid = store.upsert_case(conn, "2026-07-01", "beijing", "sunset_glow",
                            rule_score=2.0, confidence="low", source="cold_start")
    store.set_actual_score(conn, cid, 9.0)
    # 2) 过期 pending 预测
    store.add_prediction(conn, "2026-07-01", "beijing", "sunset_glow", "c1",
                         probability_pct=30, quality_pct=25, confidence="low",
                         rule_score=2.0, sat_cloud_pct=None, trend=None,
                         llm_status="pending", reasoning=None, risks=None)
    monkeypatch.setattr(cli, "explain", lambda card, paths: "补跑复盘")
    from typer.testing import CliRunner
    result = CliRunner().invoke(cli.app, ["catchup", "--db", str(db)])
    assert result.exit_code == 0
    assert store.get_case_notes(conn, cid)[-1]["text"] == "补跑复盘"
    preds = store.predictions_for(conn, "2026-07-01", "beijing", "sunset_glow")
    assert preds[0]["llm_status"] == "skipped"     # 过期 → skipped
    assert store.pending_predictions(conn) == []
```

- [ ] **Step 2: 跑测试确认失败**

- [ ] **Step 3: 实现**(cli.py 追加)

```python
@app.command()
def catchup(
    config: Path = typer.Option(DEFAULT_CONFIG),
    db: Path = typer.Option(DEFAULT_DB),
):
    """补跑 pending:闭环案例的复盘笔记;过期 pending 预测标 skipped(spec §4)。"""
    conn = _open_db(db)
    done = 0
    for case in store.closed_cases_without_llm_note(conn):
        cid = case["id"]
        full = store.case_by_key(conn, case["date"], case["city"], case["event"])
        card = build_case_card(full, store.get_snapshots(conn, cid),
                               store.get_frames(conn, cid),
                               store.get_case_notes(conn, cid))
        card += "\n\n" + format_trajectory(
            store.predictions_for(conn, case["date"], case["city"], case["event"]))
        paths = [Path(f["path"]) for f in store.get_frames(conn, cid)
                 if Path(f["path"]).exists()]
        result = explain(card, paths)
        if result is None:
            typer.echo(f"跳过 {case['date']} {case['event']}(LLM 不可用)")
            continue
        store.add_case_note(conn, cid, "llm", result)
        done += 1
        typer.echo(f"✓ 复盘 {case['date']} {case['event']}")
    today = str(date_type.today())
    for p in store.pending_predictions(conn):
        if p["date"] < today:
            store.set_prediction_llm(conn, p["id"], "skipped")
            typer.echo(f"· {p['date']} {p['event']} [{p['checkpoint']}]"
                       f" 过期 pending → skipped")
    typer.echo(f"完成:补复盘 {done} 条")
```

(当日 pending 预测:tick 的下一个检查点/门控自然会产生新记录,无需在 catchup 里重造——文档如此,YAGNI。)

- [ ] **Step 4: 跑测试确认通过**;全量绿。

- [ ] **Step 5: Commit**

```bash
git add skyfire/src/skyfire/cli.py skyfire/tests/test_cli.py
git commit -m "feat(skyfire): catchup 补跑(闭环案例复盘;过期 pending 标 skipped)"
```

---

### Task 10: 回测百分数报表(backtest --pct)

**Files:** Modify `src/skyfire/backtest.py`、`src/skyfire/cli.py`;Test `tests/test_backtest.py`

- [ ] **Step 1: 写失败测试**(追加)

```python
from skyfire.backtest import pct_report


def test_pct_report_correlation_and_hits():
    rows = [
        {"quality_pct": 80, "probability_pct": 80, "actual_score": 9},
        {"quality_pct": 60, "probability_pct": 70, "actual_score": 8},
        {"quality_pct": 30, "probability_pct": 40, "actual_score": 5},
        {"quality_pct": 10, "probability_pct": 15, "actual_score": 2},
    ]
    r = pct_report(rows)
    assert r["n"] == 4
    assert r["spearman_quality"] > 0.9
    # 命中:prob>=50 视为报烧,actual>=6 视为真烧 → TP=2 FP=0 FN=0 TN=2
    assert r["hit_rate"] == 1.0 and r["precision"] == 1.0 and r["recall"] == 1.0
```

- [ ] **Step 2: 跑测试确认失败**

- [ ] **Step 3: 实现**(backtest.py 追加)

```python
def pct_report(rows: list[dict]) -> dict:
    """终版预测百分数 vs 实际得分:相关性 + 命中率(spec 里程碑 4)。

    报烧 = probability_pct>=50;真烧 = actual_score>=6。
    """
    n = len(rows)
    out = {"n": n, "spearman_quality": None,
           "hit_rate": None, "precision": None, "recall": None}
    if n >= 3:
        try:
            out["spearman_quality"] = spearman(
                [r["quality_pct"] for r in rows],
                [r["actual_score"] for r in rows])
        except ValueError:
            pass
    if n:
        tp = sum(1 for r in rows if r["probability_pct"] >= 50
                 and r["actual_score"] >= 6)
        fp = sum(1 for r in rows if r["probability_pct"] >= 50
                 and r["actual_score"] < 6)
        fn = sum(1 for r in rows if r["probability_pct"] < 50
                 and r["actual_score"] >= 6)
        tn = n - tp - fp - fn
        out["hit_rate"] = (tp + tn) / n
        out["precision"] = tp / (tp + fp) if tp + fp else None
        out["recall"] = tp / (tp + fn) if tp + fn else None
    return out
```

cli.py 的 `backtest` 命令加 `--pct` 分支(签名加 `pct: bool = typer.Option(False, "--pct")`;函数体开头加):

```python
    if pct:
        rows = conn.execute(
            """SELECT p.quality_pct, p.probability_pct, c.actual_score
               FROM cases c JOIN predictions p
                 ON p.date=c.date AND p.city=c.city AND p.event=c.event
               WHERE c.city=? AND c.actual_score IS NOT NULL
                 AND p.id = (SELECT MAX(id) FROM predictions
                             WHERE date=c.date AND city=c.city AND event=c.event)
            """, (city,)).fetchall()
        from skyfire.backtest import pct_report
        r = pct_report([{"quality_pct": q, "probability_pct": pr,
                         "actual_score": a} for q, pr, a in rows])
        typer.echo(f"百分数回测: {r['n']} 条  质量%↔实际 Spearman ρ="
                   f"{r['spearman_quality'] if r['spearman_quality'] is None else round(r['spearman_quality'], 3)}")
        typer.echo(f"命中率 {r['hit_rate']}  精确率 {r['precision']}"
                   f"  召回 {r['recall']}(报烧=概率≥50,真烧=实际≥6)")
        return
```

(注意 `conn = _open_db(db)` 在原命令体已有,`--pct` 分支放它之后。)

- [ ] **Step 4: 跑测试确认通过**;全量绿。

- [ ] **Step 5: Commit**

```bash
git add skyfire/src/skyfire/backtest.py skyfire/src/skyfire/cli.py skyfire/tests/test_backtest.py
git commit -m "feat(skyfire): backtest --pct 百分数回测(相关性+命中率)"
```

---

### Task 11: 真实端到端验证(手动检查点 → 反馈 → catchup)

**Files:** 无代码;真数据验证 + 记录。

- [ ] **Step 1: 手动跑一个真实检查点(免费层,无 key 走 pending)**

```bash
cd /Users/feitong/photo-app/skyfire
.venv/bin/skyfire checkpoint --cp manual --event sunset_glow 2>&1 | grep -vE "RuntimeWarning|return self"
```
Expected: 打出 `晚霞 概率X% 质量Y% — 北京` + 正文含云量趋势 `now=..%→burn=..%` 与"AI 解读待补";db `predictions` 出现一行 `manual/pending`。若时值白天卫星正常,`sat_cloud_pct` 非空。

- [ ] **Step 2: 反馈闭环冒烟(拿历史日子)**

```bash
.venv/bin/skyfire feedback --date 2026-06-26 --event sunrise_glow --score 2 2>&1 | tail -5
```
Expected: `✓ 已记录反馈`;帧已存在不重拉;无 key → `AI 复盘待补...catchup 补跑`。

- [ ] **Step 3: catchup 冒烟**

```bash
.venv/bin/skyfire catchup 2>&1 | tail -5
```
Expected: 无 key 时逐条 `跳过 ...(LLM 不可用)` + 过期 pending 标 skipped;有 key 时写入复盘笔记。

- [ ] **Step 4: tick 干跑(未配推送 → 静默;配了 → 按检查点推)**

```bash
.venv/bin/skyfire tick; echo "exit=$?"
```
Expected: 未配 notify.local.yaml 时静默 exit=0。(配置推送后由 launchd 30min 自动跑,首个真实检查点当天验证。)

- [ ] **Step 5: 回测报表**

```bash
.venv/bin/skyfire backtest --city beijing --pct
```
Expected: 有 predictions×闭环案例交集时输出报表;当前历史案例无预测记录 → `0 条`(如实,轨迹要靠日常运行积累)。

- [ ] **Step 6: 更新记忆 + 提交验证记录**

更新 `skyfire-coldstart-progress.md`:C-2 落地状态、首个真实检查点的输出样例、无 key 降级路径实测、下一步(配 key / 配推送 / 攒预测轨迹后跑 --pct 回测)。

```bash
git add -A && git commit -m "docs(skyfire): Plan C-2 端到端验证记录"
```

---

## Self-Review 结果

- **Spec 覆盖**:§1 分层=Task 2/3/6;§2 检查点+门控+tick=Task 4/7;§3 predictions 表+百分数=Task 1/2;§4 LLM 分层/降级/catchup=Task 5/6/9(prompt caching 未单列任务——初版直接完整 system 文本,缓存优化留待真实账单出现后再做,YAGNI 注明);§5 反馈闭环=Task 8;§6 外推=Task 3/6;§7 降级=各任务内;§8 测试=各任务;里程碑 1-4=Task 7/8/9/10+11。
- **占位符扫描**:无 TBD;Task 7 对旧 tick 测试的适配给了替代测试与说明。
- **类型一致性**:`run_checkpoint` 返回 dict 键与 `format_pct_report`/tick 用法一致(含 city_name/peak);`store.add_prediction` 关键字参数在 Task 1/6/7/9 一致;`observe_burn_clouds` 返回四元组只在 engine 内部使用且测试 monkeypatch 同名;`format_trajectory` 在 Task 8 定义、Task 8/9 使用;`pct_report` 输入行键与 cli SQL 列一致。
- **已知取舍**:①gated 推送每次门控触发都会推(可能一日多推)——按 spec"版本化+推送最新"接受;②catchup 不重造当日 pending 预测(下一检查点自然覆盖);③observe_burn_clouds 的 live 图方位角用粗值(仅标注用),精确方位在 backfill 复盘图中。
