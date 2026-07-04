# Skyfire Plan B:实况层 + 冷启动回填 + Claude 经验层 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 Plan A 的 CLI 预测核心之上,加入 Himawari-9 卫星实况层(帧获取/云量提取/外推/权重融合)、经验库冷启动回填(CSV 清单 → 历史预报+历史卫星帧),以及 Claude 相似案例检索与多模态解读。

**Architecture:** 三条线依次叠加,每条完成后 CLI 都可独立演示:(1) `skyfire nowcast` 拉 NICT Himawari 瓦片、算云量代理、相邻帧 FFT 相位相关外推、按时效权重与规则分融合;(2) `skyfire backfill --csv` 把用户清单变成完整案例(Open-Meteo historical-forecast-api 快照 + NICT 历史帧);(3) `skyfire predict` 接 Claude(claude-opus-4-8,多模态看卫星帧,检索 top-3 相似案例),无凭证/失败时静默降级为纯规则分(spec 8)。纯函数(cloudiness/drift/nowcast/rag)与 IO(himawari/backfill/llm)严格分离。

**Tech Stack:** 在 Plan A 基础上新增 numpy(FFT/图像数组)、Pillow(PNG 解码拼接)、anthropic(官方 SDK)。测试仍用 pytest + httpx.MockTransport;图像测试用 numpy 构造合成图。

**已验证的外部事实(2026-07-04):**
- NICT 端点在线且已切 Himawari-9:`https://himawari8-dl.nict.go.jp/himawari8/img/D531106/latest.json` 返回 `{"date":"2026-07-04 02:10:00","file":"PI_H09_..."}`(UTC,10 分钟节奏);瓦片 URL 模式 `{base}/{product}/{level}d/550/{YYYY}/{MM}/{DD}/{HHMMSS}_{x}_{y}.png`,真彩产品 `D531106`,红外产品 `INFRARED_FULL`,历史时刻同模式可取(冷启动复用)。
- Open-Meteo 历史预报存档:`https://historical-forecast-api.open-meteo.com/v1/forecast`,参数与预报 API 相同(含 `models`、分层云量),加 `start_date`/`end_date`,覆盖约 2022 年起。空气质量 API 同样支持 `start_date`/`end_date`。
- Claude:Python SDK `anthropic`,模型 `claude-opus-4-8`($5/$25 每 MTok),`thinking={"type":"adaptive"}`,图片用 base64 content block;零参 `Anthropic()` 自动解析 `ANTHROPIC_API_KEY`/`ANTHROPIC_AUTH_TOKEN`/`ant auth login` 档案——**不要因 env 未设就报错**,调用失败才降级。

**Spec:** docs/superpowers/specs/2026-07-03-skyfire-predictor-design.md(5.4 实况层、6.1 冷启动、5.5 经验层、8 降级、9 验收)

## File Structure

```
skyfire/src/skyfire/
├── himawari.py        # NICT:latest 时刻、经纬度→瓦片投影、区域拼图下载、帧龄
├── cloudiness.py      # 灰度云量代理、走廊像素采样(纯 numpy)
├── drift.py           # FFT 相位相关位移 + 半拉格朗日回溯外推(纯 numpy)
├── nowcast.py         # 时效权重曲线、实况分、融合与帧龄降级(纯函数)
├── backfill.py        # CSV 解析 + 历史预报/AOD/通道/卫星帧回填编排
├── rag.py             # 因子向量提取 + 相似案例检索(零依赖)
├── llm.py             # Claude 多模态解读(anthropic SDK),失败返回 None
├── openmeteo.py       # 【改】抽 _parse_models;fetch_* 加 base_url/extra_params
├── store.py           # 【改】satellite_frames/llm_score/因子查询 helpers
└── cli.py             # 【改】新命令 nowcast/backfill;predict 接 LLM
tests/  test_himawari.py test_cloudiness.py test_drift.py test_nowcast.py
        test_backfill.py test_rag.py test_llm.py (+ 扩展 test_openmeteo/store/cli)
skyfire/data/frames/   # 卫星帧 PNG 落盘目录(已被 .gitignore 的 data/ 覆盖)
```

**环境注意(执行者必读):** venv 在 `skyfire/.venv`(Python 3.12,uv 安装于 `/Users/feitong/.local/share/uv/.../python3.12`);跑测试用 `cd /Users/feitong/photo-app/skyfire && .venv/bin/pytest -v`;绝不 `git add -A`;测试与规格矛盾时报 BLOCKED,不得自行改断言或发明逻辑。Plan A 完成时全量 37 tests passed。

---

### Task 1: 依赖升级 + Himawari 投影与时刻发现

**Files:**
- Modify: `skyfire/pyproject.toml`(dependencies 加三项)
- Create: `skyfire/src/skyfire/himawari.py`
- Test: `skyfire/tests/test_himawari.py`

- [ ] **Step 1: 改 pyproject 并重装**

`skyfire/pyproject.toml` 的 `dependencies` 改为:

```toml
dependencies = [
    "httpx>=0.27",
    "astral>=3.2",
    "PyYAML>=6.0",
    "typer>=0.12",
    "numpy>=1.26",
    "Pillow>=10.0",
    "anthropic>=0.40",
]
```

Run: `cd /Users/feitong/photo-app/skyfire && .venv/bin/pip install -e ".[dev]"`
Expected: 安装成功;`.venv/bin/pytest -q` 仍 37 passed。

- [ ] **Step 2: 写失败测试**

`skyfire/tests/test_himawari.py`:

```python
from datetime import datetime, timezone

import httpx

from skyfire.himawari import (
    frame_age_minutes,
    latest_frame_time,
    lonlat_to_fraction,
    round_down_10min,
    tile_for,
    tile_url,
)


def test_lonlat_to_fraction_beijing():
    u, v = lonlat_to_fraction(39.9042, 116.4074)
    # 北京在 140.7°E 星下点西北方:图像左半(u<0.5)、上部(v<0.5)
    assert 0.30 <= u <= 0.38
    assert 0.14 <= v <= 0.22


def test_tile_for_beijing_level4():
    tx, ty = tile_for(39.9042, 116.4074, level=4)
    assert (tx, ty) == (1, 0)


def test_tile_url_pattern():
    ts = datetime(2026, 7, 4, 2, 10, 0, tzinfo=timezone.utc)
    url = tile_url("truecolor", ts, level=4, tx=1, ty=0)
    assert url == ("https://himawari8-dl.nict.go.jp/himawari8/img/"
                   "D531106/4d/550/2026/07/04/021000_1_0.png")
    ir = tile_url("infrared", ts, level=4, tx=1, ty=0)
    assert "/INFRARED_FULL/" in ir


def test_round_down_10min():
    ts = datetime(2026, 7, 4, 2, 17, 42, tzinfo=timezone.utc)
    assert round_down_10min(ts) == datetime(2026, 7, 4, 2, 10, 0, tzinfo=timezone.utc)


def test_latest_frame_time_parses_utc():
    def handler(request):
        return httpx.Response(200, json={"date": "2026-07-04 02:10:00",
                                         "file": "PI_H09_20260704_0210_TRC_FLDK_R10_PGPFD.png"})
    client = httpx.Client(transport=httpx.MockTransport(handler))
    ts = latest_frame_time(client)
    assert ts == datetime(2026, 7, 4, 2, 10, 0, tzinfo=timezone.utc)


def test_frame_age_minutes():
    ts = datetime(2026, 7, 4, 2, 10, 0, tzinfo=timezone.utc)
    now = datetime(2026, 7, 4, 2, 45, 0, tzinfo=timezone.utc)
    assert frame_age_minutes(ts, now) == 35.0
```

- [ ] **Step 3: 运行确认失败**

Run: `cd /Users/feitong/photo-app/skyfire && .venv/bin/pytest tests/test_himawari.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'skyfire.himawari'`

- [ ] **Step 4: 实现**

`skyfire/src/skyfire/himawari.py`:

```python
"""Himawari-9 实况帧获取(NICT 公开瓦片服务,spec 5.4)。

投影用正射近似(星下点 140.7°E):对瓦片选择与区域裁剪足够精确
(中纬度中盘区域误差远小于一个瓦片);不用于精确逐像素定位。
"""
import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import httpx

NICT_BASE = "https://himawari8-dl.nict.go.jp/himawari8/img"
PRODUCTS = {"truecolor": "D531106", "infrared": "INFRARED_FULL"}
SUB_LON = 140.7
TILE_PX = 550
EARTH_DIAMETER_KM = 12742.0


def lonlat_to_fraction(lat: float, lon: float) -> tuple[float, float]:
    """经纬度 → 全盘图像内的 (u, v) 比例坐标,u 向东、v 向下。"""
    lam = math.radians(lon - SUB_LON)
    phi = math.radians(lat)
    x = math.cos(phi) * math.sin(lam)
    y = math.sin(phi)
    return (1 + x) / 2, (1 - y) / 2


def tile_for(lat: float, lon: float, level: int = 4) -> tuple[int, int]:
    u, v = lonlat_to_fraction(lat, lon)
    return min(int(u * level), level - 1), min(int(v * level), level - 1)


def tile_url(product: str, ts: datetime, level: int, tx: int, ty: int) -> str:
    return (f"{NICT_BASE}/{PRODUCTS[product]}/{level}d/{TILE_PX}/"
            f"{ts:%Y/%m/%d/%H%M%S}_{tx}_{ty}.png")


def round_down_10min(ts: datetime) -> datetime:
    return ts.replace(minute=ts.minute - ts.minute % 10, second=0, microsecond=0)


def latest_frame_time(client: httpx.Client) -> datetime:
    resp = client.get(f"{NICT_BASE}/{PRODUCTS['truecolor']}/latest.json")
    resp.raise_for_status()
    return datetime.strptime(resp.json()["date"], "%Y-%m-%d %H:%M:%S").replace(
        tzinfo=timezone.utc)


def frame_age_minutes(ts: datetime, now: datetime) -> float:
    return (now - ts).total_seconds() / 60.0


def km_per_px(level: int) -> float:
    """全盘直径 ≈ 地球直径;每像素公里数。"""
    return EARTH_DIAMETER_KM / (level * TILE_PX)
```

- [ ] **Step 5: 运行确认通过**

Run: `cd /Users/feitong/photo-app/skyfire && .venv/bin/pytest tests/test_himawari.py -v`
Expected: PASS (6 passed)。全量应 43 passed。

- [ ] **Step 6: 提交**

```bash
cd /Users/feitong/photo-app
git add skyfire/pyproject.toml skyfire/src/skyfire/himawari.py skyfire/tests/test_himawari.py
git commit -m "feat(skyfire): Himawari 投影/瓦片 URL/时刻发现 + numpy/Pillow/anthropic 依赖"
```

---

### Task 2: 区域拼图下载(RegionFrame)

**Files:**
- Modify: `skyfire/src/skyfire/himawari.py`(追加)
- Test: `skyfire/tests/test_himawari.py`(追加)

- [ ] **Step 1: 追加失败测试**(用 PIL 生成假瓦片,MockTransport 分发)

在 `skyfire/tests/test_himawari.py` 末尾追加:

```python
import io

import numpy as np
from PIL import Image

from skyfire.himawari import RegionFrame, fetch_region


def _png_bytes(value: int) -> bytes:
    img = Image.fromarray(np.full((550, 550), value, dtype=np.uint8), mode="L")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def test_fetch_region_stitches_grid_and_locates_center():
    def handler(request: httpx.Request) -> httpx.Response:
        # 用瓦片 x 坐标做灰度值,便于断言拼接顺序
        tx = int(request.url.path.rsplit("_", 2)[1])
        return httpx.Response(200, content=_png_bytes(tx * 40))

    client = httpx.Client(transport=httpx.MockTransport(handler))
    ts = datetime(2026, 7, 4, 2, 10, 0, tzinfo=timezone.utc)
    frame = fetch_region(client, "infrared", ts, 39.9042, 116.4074, level=8, grid=3)
    assert isinstance(frame, RegionFrame)
    assert frame.gray.shape == (3 * 550, 3 * 550)
    # 北京在 8d 的瓦片 (2, 1);3x3 网格起点 (1, 0)
    assert frame.origin_tile == (1, 0)
    # 左列灰度 40(tx=1)、中列 80(tx=2)、右列 120(tx=3)
    assert frame.gray[0, 0] == 40 and frame.gray[0, 800] == 80 and frame.gray[0, 1200] == 120
    # 中心像素应落在中间那块瓦片内
    cx, cy = frame.center_px
    assert 550 <= cx < 1100


def test_fetch_region_missing_tile_fills_zero():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    ts = datetime(2026, 7, 4, 2, 10, 0, tzinfo=timezone.utc)
    frame = fetch_region(client, "infrared", ts, 39.9042, 116.4074, level=8, grid=3)
    assert frame.gray.max() == 0  # 全缺帧不抛异常,拼出全零图,由上层按帧龄/内容降级
```

- [ ] **Step 2: 运行确认失败**

Run: `cd /Users/feitong/photo-app/skyfire && .venv/bin/pytest tests/test_himawari.py -v`
Expected: FAIL — `ImportError: cannot import name 'RegionFrame'`

- [ ] **Step 3: 实现(追加到 himawari.py)**

```python
import io

import numpy as np
from PIL import Image


@dataclass
class RegionFrame:
    ts: datetime
    product: str
    level: int
    gray: "np.ndarray"          # (grid*550, grid*550) uint8
    origin_tile: tuple[int, int]  # 拼图左上角瓦片 (tx, ty)
    center_px: tuple[int, int]    # 目标经纬度在拼图内的像素坐标 (x, y)


def fetch_region(client: httpx.Client, product: str, ts: datetime,
                 lat: float, lon: float, level: int = 8, grid: int = 3) -> RegionFrame:
    """下载以目标点所在瓦片为中心的 grid×grid 拼图,灰度化。缺瓦片补零。"""
    ctx, cty = tile_for(lat, lon, level)
    half = grid // 2
    tx0 = min(max(ctx - half, 0), level - grid)
    ty0 = min(max(cty - half, 0), level - grid)
    canvas = np.zeros((grid * TILE_PX, grid * TILE_PX), dtype=np.uint8)
    for iy in range(grid):
        for ix in range(grid):
            resp = client.get(tile_url(product, ts, level, tx0 + ix, ty0 + iy))
            if resp.status_code != 200:
                continue
            img = Image.open(io.BytesIO(resp.content)).convert("L")
            canvas[iy * TILE_PX:(iy + 1) * TILE_PX,
                   ix * TILE_PX:(ix + 1) * TILE_PX] = np.asarray(img)
    u, v = lonlat_to_fraction(lat, lon)
    cx = int(u * level * TILE_PX) - tx0 * TILE_PX
    cy = int(v * level * TILE_PX) - ty0 * TILE_PX
    return RegionFrame(ts=ts, product=product, level=level, gray=canvas,
                       origin_tile=(tx0, ty0), center_px=(cx, cy))
```

- [ ] **Step 4: 运行确认通过**

Run: `cd /Users/feitong/photo-app/skyfire && .venv/bin/pytest tests/test_himawari.py -v`
Expected: PASS (8 passed)。

- [ ] **Step 5: 提交**

```bash
cd /Users/feitong/photo-app
git add skyfire/src/skyfire/himawari.py skyfire/tests/test_himawari.py
git commit -m "feat(skyfire): Himawari 区域拼图下载(RegionFrame,缺瓦片补零)"
```

---

### Task 3: 云量代理与走廊采样

**Files:**
- Create: `skyfire/src/skyfire/cloudiness.py`
- Test: `skyfire/tests/test_cloudiness.py`

- [ ] **Step 1: 写失败测试**

`skyfire/tests/test_cloudiness.py`:

```python
import numpy as np

from skyfire.cloudiness import box_cloudiness, corridor_centers, corridor_cloudiness


def test_box_cloudiness_bright_is_cloudy():
    img = np.zeros((400, 400), dtype=np.uint8)
    img[100:200, 100:200] = 255  # 一块亮云
    assert box_cloudiness(img, (150, 150), half=40) > 90
    assert box_cloudiness(img, (300, 300), half=40) < 5


def test_box_cloudiness_clips_at_edges():
    img = np.full((100, 100), 128, dtype=np.uint8)
    v = box_cloudiness(img, (0, 0), half=30)  # 超出边界不抛异常
    assert 45 <= v <= 55


def test_corridor_centers_direction():
    # 方位角 270°(正西):x 递减,y 不变
    pts = corridor_centers((500, 500), azimuth_deg=270, step_px=50, n=4)
    assert len(pts) == 4
    assert pts[0] == (450, 500) and pts[3] == (300, 500)
    # 方位角 0°(正北):y 递减(图像上方为北)
    pts_n = corridor_centers((500, 500), azimuth_deg=0, step_px=50, n=2)
    assert pts_n[0] == (500, 450)


def test_corridor_cloudiness_averages_boxes():
    img = np.zeros((600, 1200), dtype=np.uint8)
    img[:, 0:600] = 255  # 西半边全云
    vals = corridor_cloudiness(img, (760, 300), azimuth_deg=270, step_px=100, n=4, half=30)
    assert len(vals) == 4
    assert vals[0] < 10          # (660,300) 仍在暗区(分界 x=600 以东,框不跨界)
    assert vals[-1] > 90         # (360,300) 深入亮区
```

- [ ] **Step 2: 运行确认失败**

Run: `cd /Users/feitong/photo-app/skyfire && .venv/bin/pytest tests/test_cloudiness.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: 实现**

`skyfire/src/skyfire/cloudiness.py`:

```python
"""从红外灰度图提取云量代理(spec 5.4 实况量)。

红外通道里云顶冷→亮:亮度均值/255*100 作为云量百分比代理。
这是有意的粗代理(无法分高低云),用于实况校验与外推,阈值可回测调。
坐标约定:图像 x 向东、y 向下(北在上);方位角自北顺时针。
"""
import math

import numpy as np


def box_cloudiness(gray: np.ndarray, center: tuple[int, int], half: int = 30) -> float:
    cx, cy = center
    x0, x1 = max(cx - half, 0), min(cx + half, gray.shape[1])
    y0, y1 = max(cy - half, 0), min(cy + half, gray.shape[0])
    if x0 >= x1 or y0 >= y1:
        return 0.0
    return float(gray[y0:y1, x0:x1].mean() / 255.0 * 100.0)


def corridor_centers(origin: tuple[int, int], azimuth_deg: float,
                     step_px: int, n: int) -> list[tuple[int, int]]:
    """沿方位角方向的采样中心序列(第 1 个点在 1*step 处)。"""
    rad = math.radians(azimuth_deg)
    dx, dy = math.sin(rad), -math.cos(rad)
    return [(round(origin[0] + dx * step_px * k), round(origin[1] + dy * step_px * k))
            for k in range(1, n + 1)]


def corridor_cloudiness(gray: np.ndarray, origin: tuple[int, int], azimuth_deg: float,
                        step_px: int, n: int, half: int = 30) -> list[float]:
    return [box_cloudiness(gray, c, half) for c in corridor_centers(origin, azimuth_deg, step_px, n)]
```

- [ ] **Step 4: 运行确认通过**

Run: `cd /Users/feitong/photo-app/skyfire && .venv/bin/pytest tests/test_cloudiness.py -v`
Expected: PASS (4 passed)。

- [ ] **Step 5: 提交**

```bash
cd /Users/feitong/photo-app
git add skyfire/src/skyfire/cloudiness.py skyfire/tests/test_cloudiness.py
git commit -m "feat(skyfire): 红外云量代理与走廊采样"
```

---

### Task 4: 相位相关位移与半拉格朗日外推

**Files:**
- Create: `skyfire/src/skyfire/drift.py`
- Test: `skyfire/tests/test_drift.py`

- [ ] **Step 1: 写失败测试**

`skyfire/tests/test_drift.py`:

```python
import numpy as np

from skyfire.drift import estimate_shift, extrapolated_corridor


def _cloud_field(seed=7):
    rng = np.random.default_rng(seed)
    base = rng.random((256, 256))
    # 平滑成云块状,避免纯噪声
    from numpy.fft import fft2, ifft2, fftfreq
    fy = fftfreq(256)[:, None]
    fx = fftfreq(256)[None, :]
    lowpass = np.exp(-((fx ** 2 + fy ** 2) * 800))
    smooth = np.real(ifft2(fft2(base) * lowpass))
    smooth = (smooth - smooth.min()) / (smooth.max() - smooth.min())
    return (smooth * 255).astype(np.uint8)


def test_estimate_shift_recovers_known_roll():
    prev = _cloud_field()
    curr = np.roll(prev, (5, 12), axis=(0, 1))  # 向下 5、向右 12
    dy, dx = estimate_shift(prev, curr)
    assert (dy, dx) == (5, 12)


def test_estimate_shift_negative():
    prev = _cloud_field()
    curr = np.roll(prev, (-8, -3), axis=(0, 1))
    assert estimate_shift(prev, curr) == (-8, -3)


def test_extrapolated_corridor_backtracks_upstream():
    # 云整体向东移(dx>0):走廊未来的云 = 现在走廊西侧(上游)的云
    img = np.zeros((400, 400), dtype=np.uint8)
    img[:, 0:120] = 255  # 西侧亮云带
    # 走廊向西(方位 270°),当前走廊在 x=200..80 → 部分亮
    now = extrapolated_corridor(img, (280, 200), azimuth_deg=270, step_px=40, n=4,
                                shift_per_frame=(0, 0), frames_ahead=0)
    fut = extrapolated_corridor(img, (280, 200), azimuth_deg=270, step_px=40, n=4,
                                shift_per_frame=(0, 20), frames_ahead=6)  # 每帧东移 20px
    # 回溯采样点整体西移 120px → 更深入亮云带 → 预测云量高于当前
    assert sum(fut) > sum(now)
```

- [ ] **Step 2: 运行确认失败**

Run: `cd /Users/feitong/photo-app/skyfire && .venv/bin/pytest tests/test_drift.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: 实现**

`skyfire/src/skyfire/drift.py`:

```python
"""云区移动估计与外推(spec 5.4)。

estimate_shift:FFT 相位相关求两帧整体位移(dy, dx),curr ≈ roll(prev, (dy, dx))。
extrapolated_corridor:半拉格朗日回溯——窗口时刻将位于走廊上空的气块,
当前位于下风向上游 shift*frames 处;把采样点反向平移后在当前帧上采样。
"""
import numpy as np

from skyfire.cloudiness import box_cloudiness, corridor_centers


def estimate_shift(prev: np.ndarray, curr: np.ndarray) -> tuple[int, int]:
    fa = np.fft.fft2(curr.astype(np.float64))
    fb = np.fft.fft2(prev.astype(np.float64))
    cross = fa * np.conj(fb)
    cross /= np.abs(cross) + 1e-12
    corr = np.abs(np.fft.ifft2(cross))
    peak = np.unravel_index(int(np.argmax(corr)), corr.shape)
    shifts = []
    for p, size in zip(peak, corr.shape):
        shifts.append(p - size if p > size // 2 else p)
    return shifts[0], shifts[1]  # (dy, dx)


def extrapolated_corridor(gray: np.ndarray, origin: tuple[int, int], azimuth_deg: float,
                          step_px: int, n: int, shift_per_frame: tuple[int, int],
                          frames_ahead: int, half: int = 30) -> list[float]:
    dy, dx = shift_per_frame
    offset_x = -dx * frames_ahead
    offset_y = -dy * frames_ahead
    centers = corridor_centers(origin, azimuth_deg, step_px, n)
    return [box_cloudiness(gray, (cx + offset_x, cy + offset_y), half)
            for cx, cy in centers]
```

- [ ] **Step 4: 运行确认通过**

Run: `cd /Users/feitong/photo-app/skyfire && .venv/bin/pytest tests/test_drift.py -v`
Expected: PASS (3 passed)。

- [ ] **Step 5: 提交**

```bash
cd /Users/feitong/photo-app
git add skyfire/src/skyfire/drift.py skyfire/tests/test_drift.py
git commit -m "feat(skyfire): FFT 相位相关位移估计与半拉格朗日走廊外推"
```

---

### Task 5: 实况分、权重曲线与融合

**Files:**
- Create: `skyfire/src/skyfire/nowcast.py`
- Test: `skyfire/tests/test_nowcast.py`

- [ ] **Step 1: 写失败测试**

`skyfire/tests/test_nowcast.py`:

```python
import pytest

from skyfire.nowcast import FusedScore, fuse, obs_score, obs_weight


def test_obs_weight_curve():
    assert obs_weight(400) == pytest.approx(0.3)     # T-6h 之外封顶 0.3
    assert obs_weight(360) == pytest.approx(0.3)
    assert obs_weight(240) == pytest.approx(0.45)    # 线性上升
    assert obs_weight(120) == pytest.approx(0.6)
    assert obs_weight(60) == pytest.approx(0.85)     # T-1h 起实况主导
    assert obs_weight(10) == pytest.approx(0.85)


def test_obs_score_canvas_and_corridor():
    good = obs_score(local_cloudiness=50, corridor_pred=[10, 15, 5, 20])
    bad_blocked = obs_score(local_cloudiness=50, corridor_pred=[90, 95, 92, 88])
    bad_clear = obs_score(local_cloudiness=2, corridor_pred=[10, 5, 5, 10])
    assert good >= 7.0
    assert bad_blocked <= 2.5
    assert bad_clear <= 2.0


def test_fuse_weights_and_degrade():
    r = fuse(rule_score=8.0, observed=2.0, minutes_to_window=60, frame_age_min=20)
    assert r.score == pytest.approx(8.0 * 0.15 + 2.0 * 0.85, abs=0.05)
    assert not r.degraded
    stale = fuse(rule_score=8.0, observed=2.0, minutes_to_window=60, frame_age_min=45)
    assert stale.degraded and stale.score == 8.0  # 帧龄超 40 分钟:不拿旧图冒充实况(spec 5.4)
```

- [ ] **Step 2: 运行确认失败**

Run: `cd /Users/feitong/photo-app/skyfire && .venv/bin/pytest tests/test_nowcast.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: 实现**

`skyfire/src/skyfire/nowcast.py`:

```python
"""实况层评分与融合(spec 5.4:权重曲线 + 帧龄降级)。"""
from dataclasses import dataclass

MAX_FRAME_AGE_MIN = 40.0


@dataclass
class FusedScore:
    score: float          # 0-10 综合分
    obs: float            # 实况分
    weight: float         # 实况权重
    degraded: bool        # 帧龄超限 → 退回纯规则分


def obs_weight(minutes_to_window: float) -> float:
    """T-6h 30% → T-2h 60% → T-1h 起 85%(线性插值,spec 5.4)。"""
    m = minutes_to_window
    if m >= 360:
        return 0.3
    if m >= 120:
        return 0.3 + (360 - m) / 240 * 0.3
    if m >= 60:
        return 0.6 + (120 - m) / 60 * 0.25
    return 0.85


def obs_score(local_cloudiness: float, corridor_pred: list[float]) -> float:
    """实况分(0-10):本地有画布云 + 外推后走廊透光。

    红外代理无法分高低云,画布项刻意宽容;走廊项是主判据。阈值待回测校准。
    """
    if local_cloudiness < 5:
        canvas = 0.5
    elif local_cloudiness <= 80:
        canvas = 10.0
    else:
        canvas = 4.0
    if not corridor_pred:
        return round(canvas, 1)
    blocked = sum(1 for v in corridor_pred if v > 60) / len(corridor_pred)
    factor = max(0.1, 1 - 1.8 * blocked)
    return round(canvas * factor, 1)


def fuse(rule_score: float, observed: float, minutes_to_window: float,
         frame_age_min: float) -> FusedScore:
    if frame_age_min > MAX_FRAME_AGE_MIN:
        return FusedScore(score=rule_score, obs=observed, weight=0.0, degraded=True)
    w = obs_weight(minutes_to_window)
    return FusedScore(score=round(rule_score * (1 - w) + observed * w, 1),
                      obs=observed, weight=w, degraded=False)
```

- [ ] **Step 4: 运行确认通过**

Run: `cd /Users/feitong/photo-app/skyfire && .venv/bin/pytest tests/test_nowcast.py -v`
Expected: PASS (3 passed)。

- [ ] **Step 5: 提交**

```bash
cd /Users/feitong/photo-app
git add skyfire/src/skyfire/nowcast.py skyfire/tests/test_nowcast.py
git commit -m "feat(skyfire): 实况分/权重曲线/融合与帧龄降级"
```

---

### Task 6: store 扩展(卫星帧 / llm_score / 快照查询)

**Files:**
- Modify: `skyfire/src/skyfire/store.py`(追加函数,不改 schema——六表已建全)
- Test: `skyfire/tests/test_store.py`(追加)

- [ ] **Step 1: 追加失败测试**

在 `skyfire/tests/test_store.py` 末尾追加:

```python
def test_satellite_frames_roundtrip(tmp_path):
    conn = _db(tmp_path)
    cid = store.upsert_case(conn, "2026-07-04", "beijing", "sunset_glow",
                            rule_score=7.0, confidence="high", source="auto")
    store.add_satellite_frame(conn, cid, "2026-07-04T10:10:00+00:00", "infrared",
                              "data/frames/x.png")
    frames = store.get_frames(conn, cid)
    assert frames == [{"ts": "2026-07-04T10:10:00+00:00", "channel": "infrared",
                       "path": "data/frames/x.png"}]


def test_set_llm_score(tmp_path):
    conn = _db(tmp_path)
    cid = store.upsert_case(conn, "2026-07-04", "beijing", "sunset_glow",
                            rule_score=7.0, confidence="high", source="auto")
    store.set_llm_score(conn, cid, 6.5)
    row = conn.execute("SELECT llm_score FROM cases WHERE id=?", (cid,)).fetchone()
    assert row[0] == 6.5


def test_cases_with_snapshot_for_rag(tmp_path):
    conn = _db(tmp_path)
    cid = store.upsert_case(conn, "2026-07-01", "beijing", "sunset_glow",
                            rule_score=8.0, confidence="high", source="cold_start")
    store.set_actual_score(conn, cid, 9.0)
    store.add_snapshot(conn, cid, "gfs_seamless", {"cloud_high": 48, "cloud_mid": 10})
    rows = store.cases_with_snapshot(conn, "beijing", "sunset_glow", model="gfs_seamless")
    assert len(rows) == 1
    assert rows[0]["actual_score"] == 9.0
    assert rows[0]["payload"]["cloud_high"] == 48
    # 未打分案例不参与检索
    cid2 = store.upsert_case(conn, "2026-07-02", "beijing", "sunset_glow",
                             rule_score=3.0, confidence="high", source="auto")
    store.add_snapshot(conn, cid2, "gfs_seamless", {"cloud_high": 5})
    assert len(store.cases_with_snapshot(conn, "beijing", "sunset_glow",
                                         model="gfs_seamless")) == 1
```

- [ ] **Step 2: 运行确认失败**

Run: `cd /Users/feitong/photo-app/skyfire && .venv/bin/pytest tests/test_store.py -v`
Expected: FAIL — `AttributeError: ... 'add_satellite_frame'`

- [ ] **Step 3: 实现(追加到 store.py 末尾)**

```python
def add_satellite_frame(conn, case_id: int, ts: str, channel: str, path: str) -> None:
    conn.execute(
        "INSERT INTO satellite_frames (case_id, ts, channel, path) VALUES (?, ?, ?, ?)",
        (case_id, ts, channel, path),
    )
    conn.commit()


def get_frames(conn, case_id: int) -> list[dict]:
    rows = conn.execute(
        "SELECT ts, channel, path FROM satellite_frames WHERE case_id=? ORDER BY ts",
        (case_id,),
    ).fetchall()
    return [{"ts": t, "channel": c, "path": p} for t, c, p in rows]


def set_llm_score(conn, case_id: int, score: float) -> None:
    conn.execute("UPDATE cases SET llm_score=? WHERE id=?", (score, case_id))
    conn.commit()


def cases_with_snapshot(conn, city: str, event: str, *, model: str) -> list[dict]:
    """已闭环案例 + 指定模式的最新快照(相似案例检索用,spec 5.5)。"""
    rows = conn.execute(
        """SELECT c.id, c.date, c.actual_score, s.payload
           FROM cases c JOIN forecast_snapshots s ON s.case_id = c.id
           WHERE c.city=? AND c.event=? AND c.actual_score IS NOT NULL AND s.model=?
             AND s.id = (SELECT MAX(id) FROM forecast_snapshots
                         WHERE case_id=c.id AND model=?)
           ORDER BY c.date""",
        (city, event, model, model),
    ).fetchall()
    return [{"case_id": i, "date": d, "actual_score": a, "payload": json.loads(p)}
            for i, d, a, p in rows]
```

- [ ] **Step 4: 运行确认通过**

Run: `cd /Users/feitong/photo-app/skyfire && .venv/bin/pytest tests/test_store.py -v`
Expected: PASS (7 passed)。

- [ ] **Step 5: 提交**

```bash
cd /Users/feitong/photo-app
git add skyfire/src/skyfire/store.py skyfire/tests/test_store.py
git commit -m "feat(skyfire): store 扩展——卫星帧/llm_score/RAG 快照查询"
```

---

### Task 7: openmeteo 重构(历史 API 复用)

**Files:**
- Modify: `skyfire/src/skyfire/openmeteo.py`
- Test: `skyfire/tests/test_openmeteo.py`(追加;既有 4 测不得改动)

- [ ] **Step 1: 追加失败测试**

在 `skyfire/tests/test_openmeteo.py` 末尾追加:

```python
from skyfire.openmeteo import HISTORICAL_FORECAST_URL, fetch_point_forecast_range


def test_fetch_point_forecast_range_hits_historical_url_with_dates():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["host"] = request.url.host
        seen["params"] = dict(request.url.params)
        return httpx.Response(200, json=_multi_model_payload())

    client = httpx.Client(transport=httpx.MockTransport(handler))
    forecasts = fetch_point_forecast_range(client, 39.9, 116.4, "Asia/Shanghai",
                                           "2026-05-12", "2026-05-12")
    assert seen["host"] == httpx.URL(HISTORICAL_FORECAST_URL).host
    assert seen["params"]["start_date"] == "2026-05-12"
    assert seen["params"]["end_date"] == "2026-05-12"
    assert [f.model for f in forecasts] == list(MODELS)
    assert forecasts[0].at("2026-07-03T19:00").cloud_high == 48
```

- [ ] **Step 2: 运行确认失败**

Run: `cd /Users/feitong/photo-app/skyfire && .venv/bin/pytest tests/test_openmeteo.py -v`
Expected: FAIL — `ImportError: cannot import name 'HISTORICAL_FORECAST_URL'`

- [ ] **Step 3: 实现(重构 openmeteo.py)**

在常量区追加:

```python
HISTORICAL_FORECAST_URL = "https://historical-forecast-api.open-meteo.com/v1/forecast"
```

把 `fetch_point_forecast` 中"解析响应 → list[ModelForecast]"的部分抽成私有函数,并新增 range 版本(**保持 fetch_point_forecast 现有签名与行为不变**):

```python
def _parse_models(data: dict, models: tuple[str, ...]) -> list[ModelForecast]:
    hourly = data["hourly"]
    times = hourly["time"]
    result = []
    for m in models:
        suffix = f"_{m}" if len(models) > 1 else ""
        columns = {
            field: _series(hourly, var, suffix, len(times))
            for var, field in _FIELD_BY_VAR.items()
        }
        points = [
            HourlyPoint(time=t, **{f: columns[f][i] for f in columns})
            for i, t in enumerate(times)
        ]
        result.append(ModelForecast(model=m, hourly=points))
    return result


def fetch_point_forecast_range(
    client: httpx.Client, lat: float, lon: float, tz: str,
    start_date: str, end_date: str, models: tuple[str, ...] = MODELS,
) -> list[ModelForecast]:
    """历史预报存档(冷启动回填用,spec 6.1):同一解析,不同端点+日期窗。"""
    resp = client.get(HISTORICAL_FORECAST_URL, params={
        "latitude": lat, "longitude": lon, "timezone": tz,
        "hourly": ",".join(HOURLY_VARS), "models": ",".join(models),
        "wind_speed_unit": "ms", "start_date": start_date, "end_date": end_date,
    })
    resp.raise_for_status()
    return _parse_models(resp.json(), models)
```

`fetch_point_forecast` 主体改为调用 `_parse_models(resp.json(), models)`(其余不动)。

- [ ] **Step 4: 运行确认通过(含既有测试无回归)**

Run: `cd /Users/feitong/photo-app/skyfire && .venv/bin/pytest tests/test_openmeteo.py -v`
Expected: PASS (5 passed)。全量无回归。

- [ ] **Step 5: 提交**

```bash
cd /Users/feitong/photo-app
git add skyfire/src/skyfire/openmeteo.py skyfire/tests/test_openmeteo.py
git commit -m "refactor(skyfire): 抽 _parse_models,新增历史预报 range 接口"
```

---

### Task 8: backfill——CSV 解析与校验

**Files:**
- Create: `skyfire/src/skyfire/backfill.py`
- Test: `skyfire/tests/test_backfill.py`

- [ ] **Step 1: 写失败测试**

`skyfire/tests/test_backfill.py`:

```python
import pytest

from skyfire.backfill import BackfillRow, parse_csv


def test_parse_csv_valid(tmp_path):
    p = tmp_path / "cases.csv"
    p.write_text(
        "date,city,event,score\n"
        "2026-05-12,beijing,sunset_glow,9\n"
        "2026-05-20,beijing,sunrise_glow,2.5\n",
        encoding="utf-8",
    )
    rows = parse_csv(p)
    assert rows == [
        BackfillRow(date="2026-05-12", city="beijing", event="sunset_glow", score=9.0),
        BackfillRow(date="2026-05-20", city="beijing", event="sunrise_glow", score=2.5),
    ]


def test_parse_csv_rejects_bad_event(tmp_path):
    p = tmp_path / "bad.csv"
    p.write_text("date,city,event,score\n2026-05-12,beijing,rainbow,9\n", encoding="utf-8")
    with pytest.raises(ValueError, match="rainbow"):
        parse_csv(p)


def test_parse_csv_rejects_bad_date_and_score(tmp_path):
    p = tmp_path / "bad2.csv"
    p.write_text("date,city,event,score\n05/12/2026,beijing,sunset_glow,9\n", encoding="utf-8")
    with pytest.raises(ValueError, match="日期"):
        parse_csv(p)
    p.write_text("date,city,event,score\n2026-05-12,beijing,sunset_glow,11\n", encoding="utf-8")
    with pytest.raises(ValueError, match="0-10"):
        parse_csv(p)


def test_parse_csv_rejects_missing_score_column(tmp_path):
    # 缺 score 列的短行应给友好的 ValueError,而非裸 TypeError
    p = tmp_path / "short.csv"
    p.write_text("date,city,event,score\n2026-05-12,beijing,sunset_glow\n", encoding="utf-8")
    with pytest.raises(ValueError, match="必须是数字"):
        parse_csv(p)
```

- [ ] **Step 2: 运行确认失败**

Run: `cd /Users/feitong/photo-app/skyfire && .venv/bin/pytest tests/test_backfill.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: 实现**

`skyfire/src/skyfire/backfill.py`:

```python
"""经验库冷启动回填(spec 6.1):CSV 清单 → 历史预报快照 + 历史卫星帧。"""
import csv
from dataclasses import dataclass
from datetime import date as date_type
from pathlib import Path

VALID_EVENTS = ("sunrise_glow", "sunset_glow", "cloud_sea")


@dataclass
class BackfillRow:
    date: str
    city: str
    event: str
    score: float


def parse_csv(path: Path) -> list[BackfillRow]:
    rows: list[BackfillRow] = []
    with open(path, newline="", encoding="utf-8") as f:
        for i, rec in enumerate(csv.DictReader(f), start=2):
            date_s = (rec.get("date") or "").strip()
            try:
                date_type.fromisoformat(date_s)
            except ValueError:
                raise ValueError(f"第 {i} 行:日期格式应为 YYYY-MM-DD,收到 {date_s!r}")
            event = (rec.get("event") or "").strip()
            if event not in VALID_EVENTS:
                raise ValueError(f"第 {i} 行:未知天象 {event!r},可用: {', '.join(VALID_EVENTS)}")
            try:
                score = float((rec.get("score") or "").strip())
            except ValueError:
                raise ValueError(f"第 {i} 行:score 必须是数字")
            if not 0 <= score <= 10:
                raise ValueError(f"第 {i} 行:score 必须在 0-10,收到 {score}")
            rows.append(BackfillRow(date=date_s, city=(rec.get("city") or "").strip(),
                                    event=event, score=score))
    return rows
```

- [ ] **Step 4: 运行确认通过**

Run: `cd /Users/feitong/photo-app/skyfire && .venv/bin/pytest tests/test_backfill.py -v`
Expected: PASS (3 passed)。

- [ ] **Step 5: 提交**

```bash
cd /Users/feitong/photo-app
git add skyfire/src/skyfire/backfill.py skyfire/tests/test_backfill.py
git commit -m "feat(skyfire): 冷启动 CSV 解析与校验"
```

---

### Task 9: backfill——单行案例回填编排

**Files:**
- Modify: `skyfire/src/skyfire/backfill.py`(追加)
- Test: `skyfire/tests/test_backfill.py`(追加)

- [ ] **Step 1: 追加失败测试**(全 mock:历史预报 + NICT 帧)

在 `skyfire/tests/test_backfill.py` 末尾追加:

```python
import io

import httpx
import numpy as np
from PIL import Image

from skyfire import store
from skyfire.backfill import backfill_row
from skyfire.config import load_cities
from skyfire.openmeteo import HISTORICAL_FORECAST_URL, MODELS
from pathlib import Path

CONFIG = Path(__file__).parent.parent / "config" / "cities.yaml"


def _hist_payload(day: str):
    times = [f"{day}T{h:02d}:00" for h in range(24)]
    n = len(times)
    hourly = {"time": times}
    for m in MODELS:
        for var, val in [("cloud_cover", 60), ("cloud_cover_low", 10),
                         ("cloud_cover_mid", 15), ("cloud_cover_high", 48),
                         ("relative_humidity_2m", 70), ("wind_speed_10m", 2.5),
                         ("temperature_2m", 30), ("dew_point_2m", 22),
                         ("precipitation", 0)]:
            hourly[f"{var}_{m}"] = [val] * n
    return {"hourly": hourly}


def _fake_transport(day: str, tile_status=200):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == httpx.URL(HISTORICAL_FORECAST_URL).host:
            return httpx.Response(200, json=_hist_payload(day))
        if request.url.path.endswith(".png"):
            if tile_status != 200:
                return httpx.Response(tile_status)
            img = Image.fromarray(np.full((550, 550), 90, dtype=np.uint8), mode="L")
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            return httpx.Response(200, content=buf.getvalue())
        return httpx.Response(404)

    return httpx.MockTransport(handler)


def test_backfill_row_creates_closed_case(tmp_path):
    conn = store.connect(tmp_path / "t.db")
    store.init_db(conn)
    client = httpx.Client(transport=_fake_transport("2026-05-12"))
    row = BackfillRow(date="2026-05-12", city="beijing", event="sunset_glow", score=9.0)
    city = load_cities(CONFIG)["beijing"]
    result = backfill_row(conn, client, row, city, frames_dir=tmp_path / "frames",
                          n_frames=2)
    assert result.case_id > 0
    got = conn.execute(
        "SELECT rule_score, actual_score, source FROM cases WHERE id=?",
        (result.case_id,)).fetchone()
    assert got[1] == 9.0 and got[2] == "cold_start"
    assert got[0] is not None            # 用历史快照重算了规则分
    snaps = store.get_snapshots(conn, result.case_id)
    assert {s["model"] for s in snaps} == set(MODELS)
    frames = store.get_frames(conn, result.case_id)
    assert len(frames) == 2
    assert (tmp_path / "frames").exists()


def test_backfill_row_survives_missing_satellite(tmp_path):
    conn = store.connect(tmp_path / "t.db")
    store.init_db(conn)
    client = httpx.Client(transport=_fake_transport("2026-05-12", tile_status=404))
    row = BackfillRow(date="2026-05-12", city="beijing", event="sunset_glow", score=7.0)
    city = load_cities(CONFIG)["beijing"]
    result = backfill_row(conn, client, row, city, frames_dir=tmp_path / "frames",
                          n_frames=2)
    # 卫星缺档不阻塞:案例照建,帧数为 0(spec 8 降级思路)
    assert result.case_id > 0
    assert store.get_frames(conn, result.case_id) == []
```

- [ ] **Step 2: 运行确认失败**

Run: `cd /Users/feitong/photo-app/skyfire && .venv/bin/pytest tests/test_backfill.py -v`
Expected: FAIL — `ImportError: cannot import name 'backfill_row'`

- [ ] **Step 3: 实现(追加到 backfill.py)**

```python
from dataclasses import dataclass, field
from datetime import date as _date, timedelta, timezone

import httpx
import numpy as np
from PIL import Image

from skyfire import store
from skyfire.config import City
from skyfire.himawari import fetch_region, round_down_10min
from skyfire.openmeteo import fetch_point_forecast_range
from skyfire.scoring.firecloud import FireCloudInputs, fire_cloud_score
from skyfire.consensus import consensus
from skyfire.suntimes import sun_window


@dataclass
class BackfillResult:
    case_id: int
    n_frames: int
    n_models: int


def backfill_row(conn, client: httpx.Client, row: BackfillRow, city: City,
                 frames_dir, n_frames: int = 3) -> BackfillResult:
    """单条清单 → 完整案例:历史多模式快照 + 规则分重算 + 卫星帧(尽力)。

    冷启动无通道剖面与 AOD(历史点阵回填成本高,留观)——规则分以
    canvas/本地因子为主,channel=[] 走 firecloud 的"缺数据不罚"路径;
    检索层(rag)对缺失字段做中性处理。
    """
    day = _date.fromisoformat(row.date)
    # cloud_sea 属日出前后的天象,取 sunrise 窗回填
    win = sun_window(city.lat, city.lon, city.timezone, day,
                     "sunrise_glow" if row.event == "cloud_sea" else row.event)
    iso_hour = win.peak.strftime("%Y-%m-%dT%H:00")

    forecasts = fetch_point_forecast_range(client, city.lat, city.lon, city.timezone,
                                           row.date, row.date)
    per_model: dict[str, float] = {}
    for fc in forecasts:
        h = fc.at(iso_hour)
        if h is None or h.cloud_high is None:
            continue
        r = fire_cloud_score(FireCloudInputs(
            cloud_high=h.cloud_high, cloud_mid=h.cloud_mid or 0,
            cloud_low=h.cloud_low or 0, precipitation=h.precipitation or 0,
            aod=None, channel=[],
        ))
        per_model[fc.model] = r.score
    rule = consensus(per_model).index if per_model else None
    conf = consensus(per_model).confidence if per_model else None

    case_id = store.upsert_case(conn, row.date, row.city, row.event,
                                rule_score=rule, confidence=conf, source="cold_start")
    store.set_actual_score(conn, case_id, row.score)
    for fc in forecasts:
        h = fc.at(iso_hour)
        if h is None:
            continue
        store.add_snapshot(conn, case_id, fc.model, {
            "hour": iso_hour, "cloud_high": h.cloud_high, "cloud_mid": h.cloud_mid,
            "cloud_low": h.cloud_low, "cloud_cover": h.cloud_cover,
            "rh_2m": h.rh_2m, "precipitation": h.precipitation, "aod": None,
            "channel": [], "azimuth": round(win.azimuth_deg, 1),
        })

    frames_dir = Path(frames_dir)
    frames_dir.mkdir(parents=True, exist_ok=True)
    peak_utc = win.peak.astimezone(timezone.utc)
    saved = 0
    for k in range(n_frames):
        ts = round_down_10min(peak_utc - timedelta(minutes=30 * k))
        try:
            frame = fetch_region(client, "infrared", ts, city.lat, city.lon)
        except httpx.HTTPError:
            continue
        if frame.gray.max() == 0:
            continue  # 全缺瓦片视为无档
        path = frames_dir / f"{row.city}_{row.date}_{row.event}_{ts:%H%M}.png"
        Image.fromarray(frame.gray, mode="L").save(path)
        store.add_satellite_frame(conn, case_id, ts.isoformat(), "infrared", str(path))
        saved += 1
    return BackfillResult(case_id=case_id, n_frames=saved, n_models=len(per_model))
```

注意:`cloud_sea` 行的完整云海因子回填(夜间云量序列等)留待后续迭代;本任务对 `cloud_sea` 行按 `sunrise_glow` 窗回填基础快照即可(代码如上)。

- [ ] **Step 4: 运行确认通过**

Run: `cd /Users/feitong/photo-app/skyfire && .venv/bin/pytest tests/test_backfill.py -v`
Expected: PASS (5 passed)。

- [ ] **Step 5: 提交**

```bash
cd /Users/feitong/photo-app
git add skyfire/src/skyfire/backfill.py skyfire/tests/test_backfill.py
git commit -m "feat(skyfire): 单行案例回填(历史快照+规则分重算+卫星帧尽力)"
```

---

### Task 10: rag——因子向量与相似案例检索

**Files:**
- Create: `skyfire/src/skyfire/rag.py`
- Test: `skyfire/tests/test_rag.py`

- [ ] **Step 1: 写失败测试**

`skyfire/tests/test_rag.py`:

```python
from skyfire.rag import factor_vector, similar_cases_from


def test_factor_vector_normalizes_and_defaults():
    v = factor_vector({"cloud_high": 50, "cloud_mid": 20, "cloud_low": 10,
                       "rh_2m": 70, "aod": 0.4, "channel": [], "hour": "2026-05-12T19:00"})
    assert len(v) == 7
    assert v[0] == 0.5           # cloud_high/100
    assert v[4] == 0.4           # aod/1.0(缺失时 0.5 中性)
    v2 = factor_vector({"cloud_high": 50, "hour": "2026-05-12T19:00"})
    assert v2[4] == 0.5          # aod 缺失 → 中性


def test_factor_vector_channel_blocked_fraction():
    payload = {"cloud_high": 50, "hour": "2026-05-12T19:00",
               "channel": [{"km": 100, "low": 90, "total": 95},
                           {"km": 200, "low": 5, "total": 10}]}
    v = factor_vector(payload)
    assert v[5] == 0.5           # 一半采样点被堵


def test_similar_cases_ranked_by_distance():
    target = factor_vector({"cloud_high": 50, "cloud_mid": 10, "cloud_low": 5,
                            "rh_2m": 70, "aod": 0.3, "channel": [],
                            "hour": "2026-07-04T19:00"})
    cases = [
        {"case_id": 1, "date": "2026-07-10", "actual_score": 9.0,
         "payload": {"cloud_high": 55, "cloud_mid": 12, "cloud_low": 6,
                     "rh_2m": 68, "aod": 0.35, "channel": [], "hour": "2026-07-10T19:00"}},
        {"case_id": 2, "date": "2026-01-20", "actual_score": 1.0,
         "payload": {"cloud_high": 0, "cloud_mid": 0, "cloud_low": 90,
                     "rh_2m": 30, "aod": 1.5, "channel": [], "hour": "2026-01-20T17:00"}},
        {"case_id": 3, "date": "2026-06-01", "actual_score": 6.0,
         "payload": {"cloud_high": 45, "cloud_mid": 20, "cloud_low": 10,
                     "rh_2m": 75, "aod": 0.3, "channel": [], "hour": "2026-06-01T19:00"}},
    ]
    top = similar_cases_from(cases, target, k=2)
    assert [c["case_id"] for c in top] == [1, 3]   # 最像的排前
    assert top[0]["distance"] < top[1]["distance"]
```

- [ ] **Step 2: 运行确认失败**

Run: `cd /Users/feitong/photo-app/skyfire && .venv/bin/pytest tests/test_rag.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: 实现**

`skyfire/src/skyfire/rag.py`:

```python
"""相似案例检索(spec 5.5):因子向量 + 欧氏距离,零第三方依赖。"""
import math

_SCALES = {"cloud_high": 100.0, "cloud_mid": 100.0, "cloud_low": 100.0,
           "rh_2m": 100.0, "aod": 1.0}


def factor_vector(payload: dict) -> list[float]:
    """快照 payload → 7 维归一化向量。

    [高云, 中云, 低云, 湿度, AOD, 通道受堵比, 季节(月份余弦)]
    缺失字段取中性值,保证冷启动案例(无 AOD/通道)可比。
    """
    v = []
    for key in ("cloud_high", "cloud_mid", "cloud_low", "rh_2m"):
        raw = payload.get(key)
        v.append((raw if raw is not None else 0.0) / _SCALES[key])
    aod = payload.get("aod")
    v.append(min(aod / _SCALES["aod"], 1.5) if aod is not None else 0.5)
    channel = payload.get("channel") or []
    scored = [p for p in channel if p.get("low") is not None and p.get("total") is not None]
    if scored:
        blocked = sum(1 for p in scored if p["low"] > 60 or p["total"] > 85) / len(scored)
    else:
        blocked = 0.0
    v.append(blocked)
    month = int(str(payload.get("hour", "2026-06-15"))[5:7])
    v.append((math.cos((month - 1) / 12 * 2 * math.pi) + 1) / 2)
    return v


def similar_cases_from(cases: list[dict], target: list[float], k: int = 3) -> list[dict]:
    ranked = []
    for c in cases:
        vec = factor_vector(c["payload"])
        dist = math.sqrt(sum((a - b) ** 2 for a, b in zip(vec, target)))
        ranked.append({**c, "distance": round(dist, 4)})
    ranked.sort(key=lambda c: c["distance"])
    return ranked[:k]
```

- [ ] **Step 4: 运行确认通过**

Run: `cd /Users/feitong/photo-app/skyfire && .venv/bin/pytest tests/test_rag.py -v`
Expected: PASS (3 passed)。

- [ ] **Step 5: 提交**

```bash
cd /Users/feitong/photo-app
git add skyfire/src/skyfire/rag.py skyfire/tests/test_rag.py
git commit -m "feat(skyfire): 因子向量与相似案例检索"
```

---

### Task 11: llm——Claude 多模态解读与降级

**Files:**
- Create: `skyfire/src/skyfire/llm.py`
- Test: `skyfire/tests/test_llm.py`

- [ ] **Step 1: 写失败测试**(注入假 client,不打真实 API)

`skyfire/tests/test_llm.py`:

```python
import json
from types import SimpleNamespace

from skyfire.llm import LlmResult, build_content, interpret


class _FakeMessages:
    def __init__(self, text):
        self._text = text
        self.last_kwargs = None

    def create(self, **kwargs):
        self.last_kwargs = kwargs
        block = SimpleNamespace(type="text", text=self._text)
        return SimpleNamespace(content=[block], stop_reason="end_turn")


class _FakeClient:
    def __init__(self, text):
        self.messages = _FakeMessages(text)


def _today():
    return {"date": "2026-07-04", "event": "sunset_glow", "rule_score": 7.5,
            "confidence": "high",
            "payload": {"cloud_high": 50, "cloud_mid": 10, "cloud_low": 5,
                        "rh_2m": 70, "aod": 0.3, "channel": [],
                        "hour": "2026-07-04T19:00"}}


def test_interpret_parses_json_and_records_request(tmp_path):
    png = tmp_path / "f.png"
    import numpy as np
    from PIL import Image
    Image.fromarray(np.zeros((8, 8), dtype=np.uint8), mode="L").save(png)

    fake = _FakeClient(json.dumps({"llm_score": 6.5, "analysis": "通道有低云",
                                   "risks": "西侧低云可能封口"}))
    result = interpret(_today(), similar=[{"date": "2026-05-12", "actual_score": 9.0,
                                           "distance": 0.1, "payload": {}}],
                       frame_paths=[png], client=fake)
    assert isinstance(result, LlmResult)
    assert result.llm_score == 6.5 and "低云" in result.analysis
    kwargs = fake.messages.last_kwargs
    assert kwargs["model"] == "claude-opus-4-8"
    types = [b["type"] for b in kwargs["messages"][0]["content"]]
    assert "image" in types and "text" in types


def test_interpret_returns_none_on_failure():
    class _Boom:
        class messages:
            @staticmethod
            def create(**kwargs):
                raise RuntimeError("no credentials")

    assert interpret(_today(), similar=[], frame_paths=[], client=_Boom()) is None


def test_interpret_returns_none_on_unparseable():
    fake = _FakeClient("今天大概能烧,大概七分吧")  # 非 JSON
    assert interpret(_today(), similar=[], frame_paths=[], client=fake) is None


def test_build_content_caps_images(tmp_path):
    import numpy as np
    from PIL import Image
    paths = []
    for i in range(5):
        p = tmp_path / f"{i}.png"
        Image.fromarray(np.zeros((8, 8), dtype=np.uint8), mode="L").save(p)
        paths.append(p)
    content = build_content(_today(), [], paths)
    assert sum(1 for b in content if b["type"] == "image") == 3  # 最多 3 帧控成本
```

- [ ] **Step 2: 运行确认失败**

Run: `cd /Users/feitong/photo-app/skyfire && .venv/bin/pytest tests/test_llm.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: 实现**

`skyfire/src/skyfire/llm.py`:

```python
"""Claude 经验层解读(spec 5.5)。

- 模型 claude-opus-4-8,adaptive thinking,多模态直接看卫星帧
- 任何失败(无凭证/网络/解析)→ 返回 None,上层退回纯规则分(spec 8)
- 不要因 ANTHROPIC_API_KEY 未设而预先拒绝:零参 Anthropic() 还会解析
  ANTHROPIC_AUTH_TOKEN 与 `ant auth login` 档案,以实际调用结果为准
"""
import base64
import json
import re
from dataclasses import dataclass
from pathlib import Path

MODEL = "claude-opus-4-8"
MAX_IMAGES = 3

_SYSTEM = (
    "你是火烧云/云海预测助手的资深预报员。规则模型已给出基础分;"
    "你的职责是结合历史相似案例与卫星红外图,给出修正分与简短解读。"
    "只输出 JSON:{\"llm_score\": 0-10 的数字, \"analysis\": 两三句中文解读,"
    "引用最相似案例的日期与结果, \"risks\": 一句最大风险}。不要输出其他文字。"
)


@dataclass
class LlmResult:
    llm_score: float
    analysis: str
    risks: str


def build_content(today: dict, similar: list[dict], frame_paths: list[Path]) -> list[dict]:
    lines = [
        f"日期 {today['date']} 天象 {today['event']} 规则分 {today['rule_score']}"
        f"(置信度 {today['confidence']})",
        f"今日因子: {json.dumps(today['payload'], ensure_ascii=False)}",
        "历史相似案例(按相似度排序):",
    ]
    for c in similar:
        lines.append(f"- {c['date']} 实际 {c['actual_score']} 分 距离 {c['distance']}"
                     f" 因子 {json.dumps(c.get('payload', {}), ensure_ascii=False)}")
    if not similar:
        lines.append("- (暂无闭环案例)")
    content: list[dict] = [{"type": "text", "text": "\n".join(lines)}]
    for p in frame_paths[:MAX_IMAGES]:
        data = base64.standard_b64encode(Path(p).read_bytes()).decode()
        content.append({"type": "image",
                        "source": {"type": "base64", "media_type": "image/png",
                                   "data": data}})
    if frame_paths:
        content.append({"type": "text",
                        "text": "以上为窗口前的红外卫星帧(时间从近到远),云顶越冷越亮。"})
    return content


def interpret(today: dict, similar: list[dict], frame_paths: list[Path],
              client=None) -> LlmResult | None:
    try:
        if client is None:
            import anthropic
            client = anthropic.Anthropic()
        resp = client.messages.create(
            model=MODEL,
            max_tokens=2000,
            thinking={"type": "adaptive"},
            system=_SYSTEM,
            messages=[{"role": "user",
                       "content": build_content(today, similar, frame_paths)}],
        )
        text = next((b.text for b in resp.content if b.type == "text"), "")
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if not m:
            return None
        data = json.loads(m.group(0))
        score = float(data["llm_score"])
        if not 0 <= score <= 10:
            return None
        return LlmResult(llm_score=score, analysis=str(data.get("analysis", "")),
                         risks=str(data.get("risks", "")))
    except Exception:
        return None
```

- [ ] **Step 4: 运行确认通过**

Run: `cd /Users/feitong/photo-app/skyfire && .venv/bin/pytest tests/test_llm.py -v`
Expected: PASS (4 passed)。

- [ ] **Step 5: 提交**

```bash
cd /Users/feitong/photo-app
git add skyfire/src/skyfire/llm.py skyfire/tests/test_llm.py
git commit -m "feat(skyfire): Claude 多模态解读层(失败静默降级)"
```

---

### Task 12: CLI 集成——nowcast / backfill 命令 + predict 接 LLM

**Files:**
- Modify: `skyfire/src/skyfire/cli.py`
- Test: `skyfire/tests/test_cli.py`(追加)

- [ ] **Step 1: 追加失败测试**

在 `skyfire/tests/test_cli.py` 末尾追加:

```python
def test_backfill_command(tmp_path, monkeypatch):
    import io
    import numpy as np
    from PIL import Image
    from skyfire.openmeteo import HISTORICAL_FORECAST_URL, MODELS as _MODELS

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == httpx.URL(HISTORICAL_FORECAST_URL).host:
            times = [f"2026-05-12T{h:02d}:00" for h in range(24)]
            hourly = {"time": times}
            for m in _MODELS:
                for var, val in [("cloud_cover", 60), ("cloud_cover_low", 10),
                                 ("cloud_cover_mid", 15), ("cloud_cover_high", 48),
                                 ("relative_humidity_2m", 70), ("wind_speed_10m", 2.5),
                                 ("temperature_2m", 30), ("dew_point_2m", 22),
                                 ("precipitation", 0)]:
                    hourly[f"{var}_{m}"] = [val] * 24
            return httpx.Response(200, json={"hourly": hourly})
        if request.url.path.endswith(".png"):
            img = Image.fromarray(np.full((550, 550), 90, dtype=np.uint8), mode="L")
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            return httpx.Response(200, content=buf.getvalue())
        return httpx.Response(404)

    import skyfire.cli as cli
    monkeypatch.setattr(cli, "_make_client",
                        lambda: httpx.Client(transport=httpx.MockTransport(handler)))
    csv_path = tmp_path / "cases.csv"
    csv_path.write_text("date,city,event,score\n2026-05-12,beijing,sunset_glow,9\n",
                        encoding="utf-8")
    db = tmp_path / "sky.db"
    result = runner.invoke(app, ["backfill", "--csv", str(csv_path), "--db", str(db),
                                 "--frames-dir", str(tmp_path / "frames")])
    assert result.exit_code == 0, result.output
    assert "1 条" in result.output
    from skyfire import store
    conn = store.connect(db)
    row = conn.execute("SELECT source, actual_score FROM cases").fetchone()
    assert row == ("cold_start", 9.0)


def test_backfill_rejects_bad_csv(tmp_path):
    csv_path = tmp_path / "bad.csv"
    csv_path.write_text("date,city,event,score\n2026-05-12,beijing,rainbow,9\n",
                        encoding="utf-8")
    result = runner.invoke(app, ["backfill", "--csv", str(csv_path),
                                 "--db", str(tmp_path / "d.db"),
                                 "--frames-dir", str(tmp_path / "f")])
    assert result.exit_code != 0
    assert "rainbow" in result.output


def test_predict_no_llm_flag_skips_llm(tmp_path, monkeypatch):
    import skyfire.cli as cli
    monkeypatch.setattr(cli, "_make_client",
                        lambda: httpx.Client(transport=_fake_transport()))
    called = {"llm": False}

    def _spy(*a, **kw):
        called["llm"] = True
        return None

    monkeypatch.setattr(cli, "_run_llm", _spy)
    db = tmp_path / "sky.db"
    result = runner.invoke(app, ["predict", "--city", "beijing", "--event", "sunset_glow",
                                 "--date", "2026-07-03", "--db", str(db), "--no-llm"])
    assert result.exit_code == 0, result.output
    assert called["llm"] is False
    # 默认(不带 --no-llm)会调用
    result2 = runner.invoke(app, ["predict", "--city", "beijing", "--event", "sunset_glow",
                                  "--date", "2026-07-03", "--db", str(db)])
    assert result2.exit_code == 0, result2.output
    assert called["llm"] is True
```

- [ ] **Step 2: 运行确认失败**

Run: `cd /Users/feitong/photo-app/skyfire && .venv/bin/pytest tests/test_cli.py -v`
Expected: FAIL — backfill 命令不存在 / `_run_llm` 属性不存在

- [ ] **Step 3: 实现(修改 cli.py)**

(a) 新增 import:

```python
from datetime import datetime, timezone

from skyfire import llm as llm_mod
from skyfire import rag
from skyfire.backfill import backfill_row, parse_csv
from skyfire.cloudiness import box_cloudiness, corridor_cloudiness
from skyfire.drift import estimate_shift, extrapolated_corridor
from skyfire.himawari import (fetch_region, frame_age_minutes, km_per_px,
                              latest_frame_time, round_down_10min)
from skyfire.nowcast import fuse, obs_score
```

(b) 模块级默认路径旁加:

```python
DEFAULT_FRAMES = Path(__file__).parent.parent.parent / "data" / "frames"
```

(c) `_run_llm` 辅助函数(predict 与测试的接缝;失败返回 None):

```python
def _run_llm(conn, case_id: int, today: dict, city_key: str, event: str):
    cases = store.cases_with_snapshot(conn, city_key, event, model="gfs_seamless")
    cases = [c for c in cases if c["case_id"] != case_id]
    target = rag.factor_vector(today["payload"])
    similar = rag.similar_cases_from(cases, target, k=3)
    frames = [Path(f["path"]) for f in store.get_frames(conn, case_id)
              if Path(f["path"]).exists()]
    result = llm_mod.interpret(today, similar, frames)
    if result is not None:
        store.set_llm_score(conn, case_id, result.llm_score)
    return result, similar
```

(d) `predict` 命令:签名加 `no_llm: bool = typer.Option(False, "--no-llm", help="跳过 Claude 解读")`;在落库(add_snapshot 循环)之后追加:

```python
    if not no_llm:
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
        out = _run_llm(conn, case_id, today, city, event)
        if out and out[0] is not None:
            res, similar = out
            typer.echo(f"AI 修正分: {res.llm_score}/10  {res.analysis}")
            typer.echo(f"风险: {res.risks}")
        else:
            typer.echo("AI 解读暂缺(无凭证或调用失败),以上为纯规则分")
```

注意 `_run_llm` 返回 `(result, similar)` 元组,失败路径返回值里 result 为 None;测试 monkeypatch 直接替换 `_run_llm` 返回 None,故 predict 中需兼容 `out` 为 None 或元组:用 `out and out[0] is not None` 判断(如上)。

(e) `backfill` 命令:

```python
@app.command()
def backfill(
    csv: Path = typer.Option(..., help="清单 CSV: date,city,event,score"),
    config: Path = typer.Option(DEFAULT_CONFIG),
    db: Path = typer.Option(DEFAULT_DB),
    frames_dir: Path = typer.Option(DEFAULT_FRAMES),
    frames: int = typer.Option(3, help="每案例回填卫星帧数"),
):
    """冷启动:清单 → 历史预报快照 + 卫星帧 + 闭环案例(spec 6.1)。"""
    try:
        rows = parse_csv(csv)
    except (ValueError, OSError) as e:
        typer.echo(f"错误:{e}", err=True)
        raise typer.Exit(1)
    cities = load_cities(config)
    conn = _open_db(db)
    client = _make_client()
    ok = 0
    for row in rows:
        if row.city not in cities:
            typer.echo(f"跳过 {row.date}:未知城市 {row.city!r}", err=True)
            continue
        try:
            r = backfill_row(conn, client, row, cities[row.city],
                             frames_dir=frames_dir, n_frames=frames)
        except httpx.HTTPError as e:
            typer.echo(f"跳过 {row.date}:数据源请求失败({e.__class__.__name__})", err=True)
            continue
        typer.echo(f"✓ {row.date} {row.event} 实际 {row.score} 分"
                   f"(快照 {r.n_models} 模式,卫星帧 {r.n_frames})")
        ok += 1
    typer.echo(f"完成:{ok} 条案例入库(共 {len(rows)} 条)")
```

(f) `nowcast` 命令(真实网络路径,单测不覆盖主体——Task 13 端到端验证):

```python
@app.command()
def nowcast(
    city: str = typer.Option("beijing"),
    event: str = typer.Option("sunset_glow", help="sunset_glow | sunrise_glow"),
    config: Path = typer.Option(DEFAULT_CONFIG),
    db: Path = typer.Option(DEFAULT_DB),
    frames_dir: Path = typer.Option(DEFAULT_FRAMES),
):
    """实况层:拉 Himawari 帧 → 云量/外推 → 与今日规则分融合(spec 5.4)。"""
    cities = load_cities(config)
    if city not in cities:
        typer.echo(f"错误:未知城市 {city!r},可用: {', '.join(cities)}", err=True)
        raise typer.Exit(1)
    c = cities[city]
    today = date_type.today()
    win = sun_window(c.lat, c.lon, c.timezone, today, event)
    now = datetime.now(timezone.utc)
    minutes_to = (win.peak.astimezone(timezone.utc) - now).total_seconds() / 60
    if minutes_to < -60:
        typer.echo("今日窗口已过,无需临近修正", err=True)
        raise typer.Exit(1)

    conn = _open_db(db)
    row = conn.execute(
        "SELECT id, rule_score FROM cases WHERE date=? AND city=? AND event=?",
        (str(today), city, event)).fetchone()
    if row is None or row[1] is None:
        typer.echo("错误:今日尚无规则分,先运行 skyfire predict", err=True)
        raise typer.Exit(1)
    case_id, rule_score = row

    client = _make_client()
    try:
        ts1 = latest_frame_time(client)
        frame1 = fetch_region(client, "infrared", ts1, c.lat, c.lon)
        ts0 = round_down_10min(ts1 - timedelta(minutes=10))
        frame0 = fetch_region(client, "infrared", ts0, c.lat, c.lon)
    except httpx.HTTPError as e:
        typer.echo(f"错误:卫星数据请求失败({e.__class__.__name__}: {e}),"
                   f"以规则分为准", err=True)
        raise typer.Exit(1)

    age = frame_age_minutes(ts1, now)
    local = box_cloudiness(frame1.gray, frame1.center_px, half=40)
    step_px = max(1, round(100 / km_per_px(frame1.level)))
    if frame0.gray.max() > 0:
        shift = estimate_shift(frame0.gray, frame1.gray)
    else:
        shift = (0, 0)
    frames_ahead = max(0.0, minutes_to) / 10.0
    corridor_pred = extrapolated_corridor(frame1.gray, frame1.center_px,
                                          win.azimuth_deg, step_px, 4,
                                          shift, round(frames_ahead))
    observed = obs_score(local, corridor_pred)
    fused = fuse(rule_score, observed, minutes_to, age)

    frames_dir.mkdir(parents=True, exist_ok=True)
    path = frames_dir / f"{city}_{today}_{event}_{ts1:%H%M}.png"
    Image.fromarray(frame1.gray, mode="L").save(path)
    store.add_satellite_frame(conn, case_id, ts1.isoformat(), "infrared", str(path))

    typer.echo(f"🛰  {today} {event} 实况修正 — {c.name}")
    typer.echo(f"帧时刻: {ts1:%H:%M}Z  帧龄: {age:.0f} 分钟"
               + ("  ⚠️ 超龄,不参与融合" if fused.degraded else ""))
    typer.echo(f"本地云量代理: {local:.0f}%  走廊外推: "
               + " ".join(f"{v:.0f}%" for v in corridor_pred)
               + f"  位移/帧: {shift}")
    typer.echo(f"实况分: {fused.obs}  权重: {fused.weight:.2f}")
    typer.echo(f"综合分: {fused.score}/10(规则分 {rule_score})")
    store.upsert_case(conn, str(today), city, event,
                      rule_score=fused.score, confidence="nowcast", source="auto")
```

需要的额外 import(`Image` 与 `timedelta`)一并加到 cli.py 顶部:`from datetime import timedelta` 并 `from PIL import Image`。

- [ ] **Step 4: 运行全部测试确认通过**

Run: `cd /Users/feitong/photo-app/skyfire && .venv/bin/pytest -v`
Expected: PASS(Task 1-12 全部新测试 + Plan A 37 条,合计约 66 passed)

- [ ] **Step 5: 提交**

```bash
cd /Users/feitong/photo-app
git add skyfire/src/skyfire/cli.py skyfire/tests/test_cli.py
git commit -m "feat(skyfire): CLI 接入 nowcast/backfill 命令与 predict LLM 解读"
```

---

### Task 13: 端到端真实验证

**Files:** 无新文件——真实 API 冒烟验证(网络失败不算任务失败,记录并重试即可)。

- [ ] **Step 1: 冷启动小样本回填(真实历史 API + NICT 归档)**

先造 3 行样本(执行时请与用户确认或用近 60 天内的日期,历史预报存档与 NICT 归档均覆盖):

```bash
cat > /Users/feitong/photo-app/skyfire/data/sample_cases.csv <<'EOF'
date,city,event,score
2026-05-12,beijing,sunset_glow,8
2026-06-02,beijing,sunset_glow,3
2026-06-20,beijing,sunset_glow,6
EOF
cd /Users/feitong/photo-app/skyfire && .venv/bin/skyfire backfill --csv data/sample_cases.csv
```

Expected: 3 行 `✓`,各含 4 模式快照;卫星帧数 ≥0(NICT 历史瓦片偶发缺档可接受)。

- [ ] **Step 2: 回测首次出真实 ρ**

Run: `.venv/bin/skyfire backtest --city beijing`
Expected: `回测: 3 条闭环案例, Spearman ρ = ...`(数值不设阈值,能算出即验收;样本打分是占位,正式冷启动等用户真实清单)。

- [ ] **Step 3: predict + LLM 解读**

Run: `.venv/bin/skyfire predict --city beijing --event sunset_glow`
Expected: 规则分卡片 + `AI 修正分: x/10 ...`(若无 Anthropic 凭证则输出 `AI 解读暂缺...`——两种结果都算通过,记录实际走了哪条路径)。

- [ ] **Step 4: nowcast 实况修正**

Run: `.venv/bin/skyfire nowcast --city beijing --event sunset_glow`
Expected: 帧时刻/帧龄/本地云量/走廊外推/融合分输出;若窗口已过输出"今日窗口已过"退出码 1 也算通过(按当地时间判断)。检查 `data/frames/` 有 PNG 落盘、db 的 satellite_frames 有行。

- [ ] **Step 5: 全量测试 + 提交收尾**

```bash
cd /Users/feitong/photo-app/skyfire && .venv/bin/pytest -q
cd /Users/feitong/photo-app
git status --short -- skyfire/   # 应只有已 gitignore 的 data/;无未跟踪源码
git log --oneline -3
```

Expected: 全量通过;无遗留未提交源码(sample_cases.csv 在 data/ 下被 gitignore,不入库)。

---

## Self-Review 记录

- **Spec 覆盖**:5.4(帧获取/帧龄监控/云量提取/外推/权重曲线/超龄降级)→ Task 1-5、12(nowcast 命令);6.1(CSV 导入/历史预报存档/卫星归档/负样本靠清单本身)→ Task 7-9、12(backfill 命令);5.5(相似案例检索/Claude 多模态/llm_score 落库)→ Task 10-11、12(predict 集成);spec 8 降级(卫星缺档、LLM 失败、帧龄超限)分布在 Task 2/5/9/11/12。**不在本计划**(Plan C):推送、订阅消息、FastAPI 服务化、客户端;5.4 的"外推准度自验证"统计属持续运营项,依赖真实积累,列入 Plan C 前置任务。
- **占位符扫描**:无 TBD/TODO;所有代码步骤含完整代码。Task 9 中对 `cloud_sea` 窗口的修正说明是明确指令而非占位。
- **类型一致性**:`RegionFrame{ts,product,level,gray,origin_tile,center_px}` 在 Task 2/12 一致;`estimate_shift(prev,curr)->(dy,dx)` 与 `extrapolated_corridor(...,shift_per_frame,frames_ahead)` 在 Task 4/12 一致;`fuse(...)->FusedScore{score,obs,weight,degraded}` 在 Task 5/12 一致;`store.cases_with_snapshot(...)->[{case_id,date,actual_score,payload}]` 在 Task 6/10/12 一致;`interpret(today,similar,frame_paths,client)->LlmResult|None` 在 Task 11/12 一致;`backfill_row(conn,client,row,city,frames_dir,n_frames)->BackfillResult` 在 Task 9/12 一致。
- **已知妥协(记录在案,均有注释)**:红外亮度做云量代理不分高低云(nowcast obs_score 刻意宽容);冷启动不回填 AOD/通道(rag 中性处理);正射投影近似(瓦片级精度足够);`nowcast` 主体逻辑靠 Task 13 真实验证而非单测(网络与时间强耦合,mock 收益低)。
