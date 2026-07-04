# Skyfire Plan D:卫星云图学习管道(AWS Himawari 归档 + 预报云图 + 经验笔记)实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 21 条冷启动案例变成"可看图分析"的学习材料:每案例回填真实卫星云图(可见光+红外,来自 AWS Himawari L1b 归档)+ 历史通道剖面(救活 G_channel)+ 预报云图网格,并新增 `analyze` 命令沉淀"为什么这天 X 分"的经验笔记进库、接入 RAG。

**Architecture:** 新模块 `himawari_hsd`(AWS 桶定位/GEOS 投影选段/下载解压缓存)+ `render`(satpy 解码 HSD → 裁北京框 → BT/反射率转灰度 PNG)替代已 404 的 NICT 红外源,backfill 与 nowcast 统一走 AWS;`gridmap` 用 Open-Meteo 网格采样渲染高/中/低云预报图;`analyze` 组装案例卡 + Claude 多模态解释,笔记存 `case_notes` 表并注入相似案例检索。**打分公式 v2 重构刻意不在本计划**——按用户方法论,先攒图和笔记、证据驱动,之后再动 firecloud。

**Tech Stack:** Python 3.12(skyfire/.venv,uv 管理)、satpy(新依赖,ahi_hsd reader)、httpx、numpy、Pillow、typer、pytest。领域依据:`docs/superpowers/knowledge/2026-07-05-firecloud-domain-knowledge.md`(§2 通道门槛、§5 判读、§8 笔记格式)。

**背景事实(已实测验证,2026-07-05):**
- NICT `INFRARED_FULL` 产品 404(真彩仍 200);NICT 无多年归档 → 历史帧全 0 的根因。
- AWS 公开桶 `noaa-himawari9`(2022-12-13 后)/ `noaa-himawari8`(更早,实测 2020-09-01 有档)含 `AHI-L1b-FLDK/`,10 分钟一槽,每波段横切 10 段:`HS_H09_YYYYMMDD_HHMM_B13_FLDK_R20_S0210.DAT.bz2`。B13(10.4µm 红外)R20 段约 2.8MB,B03(0.64µm 可见)R05 段约 22MB。
- 北京裁剪框 (lon 109–124, lat 35–45) 经 GEOS 投影计算整框落在**段 2**(见 Task 1 数学)→ 每帧只需下 1 段。
- 回测基线:Spearman ρ=0.026;通道因子历史数据全空是头号病因。

**约定:** 所有命令在 `/Users/feitong/photo-app/skyfire` 下执行;`PYTEST=.venv/bin/pytest`。commit 信息按仓库惯例中文 `feat(skyfire): ...`。

---

## 文件结构

| 文件 | 职责 |
|---|---|
| Create `src/skyfire/himawari_hsd.py` | AWS 归档:桶选择(H8/H9)、GEOS 投影 v 分数与段选择、HSD key 构造、下载+bz2 解压缓存、`fetch_case_frames` 组装 |
| Create `src/skyfire/render.py` | 渲染:BT→灰度、反射率→灰度(纯函数);satpy Scene 封装 `render_band`(HSD 段→裁剪→PNG);`load_b13_region`(nowcast 用,返回数组+中心像素) |
| Create `src/skyfire/gridmap.py` | 预报云图:网格点生成、Open-Meteo 网格采样(预报/历史)、PIL 三联热图渲染 |
| Create `src/skyfire/analyze.py` | 案例卡组装(markdown,§8 格式) |
| Modify `src/skyfire/openmeteo.py` | 新增 `fetch_channel_profile_range`(历史通道剖面)、`fetch_aod_range`(历史 AOD,尽力) |
| Modify `src/skyfire/backfill.py` | 帧改走 AWS(ir+vis);通道剖面/AOD 喂真数据重算规则分 |
| Modify `src/skyfire/cli.py` | `nowcast` 切 AWS B13;新增 `cloudmap`、`analyze` 命令 |
| Modify `src/skyfire/store.py` | `case_notes` 表 + 帧去重唯一索引;`add_case_note/get_case_notes/case_by_key`;`cases_with_snapshot` 带最新笔记 |
| Modify `src/skyfire/llm.py` | 新增 `explain`(多模态解释"为什么 X 分");`build_content` 相似案例带笔记 |
| Modify `src/skyfire/himawari.py` | 注释标注 NICT infrared 已失效(代码保留 truecolor) |
| Modify `pyproject.toml` | 依赖加 `satpy` |
| Test | `tests/test_himawari_hsd.py`、`tests/test_render.py`、`tests/test_gridmap.py`、`tests/test_analyze.py`;修改 `tests/test_openmeteo.py`、`tests/test_backfill.py`(如有)、`tests/test_store.py`(如有)、`tests/test_llm.py` |

---

### Task 1: GEOS 投影选段 + AWS key 构造(纯函数)

**Files:**
- Create: `src/skyfire/himawari_hsd.py`
- Test: `tests/test_himawari_hsd.py`

北京框为什么是段 2:GEOS 正算(CGMS 标准,椭球)得扫描角 y,全盘半幅角 Y_MAX = 5,500,000m / 35,785,863m ≈ 0.153685 rad;v = (Y_MAX − y)/(2·Y_MAX)。北京 40°N/116.4°E → v≈0.150;lat 45 → v≈0.118、lat 35 → v≈0.185,±0.008 裕量后均在 [0.1, 0.2) → 段 2。

- [ ] **Step 1: 写失败测试**

```python
# tests/test_himawari_hsd.py
from datetime import datetime, timezone

from skyfire.himawari_hsd import (
    BAND_RES, CROP_BBOX, bucket_for, hsd_key, sat_code, segments_for, v_fraction,
)


def test_v_fraction_equator_center():
    assert abs(v_fraction(0.0, 140.7) - 0.5) < 0.002


def test_v_fraction_north_is_upper():
    assert v_fraction(40.0, 116.4) < v_fraction(36.0, 116.4) < 0.5


def test_beijing_crop_bbox_falls_in_segment_2():
    lon_min, lat_min, lon_max, lat_max = CROP_BBOX
    assert segments_for(lat_min, lat_max, (lon_min + lon_max) / 2) == [2]


def test_bucket_for_h9_h8_cutover():
    assert bucket_for(datetime(2023, 1, 1, tzinfo=timezone.utc)) == "noaa-himawari9"
    assert bucket_for(datetime(2021, 6, 18, tzinfo=timezone.utc)) == "noaa-himawari8"


def test_hsd_key_pattern():
    ts = datetime(2026, 5, 6, 10, 0, tzinfo=timezone.utc)
    key = hsd_key(ts, "B13", 2, sat="H09")
    assert key == ("AHI-L1b-FLDK/2026/05/06/1000/"
                   "HS_H09_20260506_1000_B13_FLDK_R20_S0210.DAT.bz2")
    assert BAND_RES["B03"] == "R05"
    assert sat_code("noaa-himawari8") == "H08"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/bin/pytest tests/test_himawari_hsd.py -v`
Expected: FAIL,`ModuleNotFoundError: No module named 'skyfire.himawari_hsd'`

- [ ] **Step 3: 最小实现**

```python
# src/skyfire/himawari_hsd.py
"""Himawari HSD 历史/准实时归档(AWS 公开桶,spec 5.4 数据源升级)。

NICT 瓦片服务无多年归档且 INFRARED_FULL 已 404(2026-07 实测);
AWS noaa-himawari8/9 桶存全盘 L1b,10 分钟一槽,按纬度横切 10 段。
北京裁剪框整框落在段 2 → 每帧只下 1 段(B13 约 2.8MB / B03 约 22MB)。
"""
import math
from datetime import datetime, timezone

# GEOS 投影常数(CGMS;单位 km,SAT_H 为地心距)
R_EQ, R_POL, SAT_H = 6378.137, 6356.7523, 42164.0
SUB_LON = 140.7
Y_MAX = 5_500_000.0 / 35_785_863.0   # 全盘半幅扫描角(rad)
N_SEGMENTS = 10
H9_START = datetime(2022, 12, 13, tzinfo=timezone.utc)  # H9 接替 H8 运行

BAND_RES = {"B03": "R05", "B13": "R20"}   # 可见光 0.5km / 红外 2km
# 北京学习框:西含 400km 通道走廊,整框位于段 2(见计划 Task 1 数学)
CROP_BBOX = (109.0, 35.0, 124.0, 45.0)    # lon_min, lat_min, lon_max, lat_max


def _geos_y_angle(lat: float, lon: float) -> float:
    """纬经度 → GEOS 扫描角 y(rad,北正)。CGMS 正算,椭球。"""
    c_lat = math.atan((R_POL ** 2 / R_EQ ** 2) * math.tan(math.radians(lat)))
    r_l = R_POL / math.sqrt(1 - (1 - R_POL ** 2 / R_EQ ** 2) * math.cos(c_lat) ** 2)
    dlon = math.radians(lon - SUB_LON)
    r1 = SAT_H - r_l * math.cos(c_lat) * math.cos(dlon)
    r2 = -r_l * math.cos(c_lat) * math.sin(dlon)
    r3 = r_l * math.sin(c_lat)
    rn = math.sqrt(r1 * r1 + r2 * r2 + r3 * r3)
    return math.asin(r3 / rn)


def v_fraction(lat: float, lon: float) -> float:
    """全盘图像内自顶向下的行比例(0=北缘, 1=南缘)。"""
    return (Y_MAX - _geos_y_angle(lat, lon)) / (2 * Y_MAX)


def segments_for(lat_min: float, lat_max: float, lon: float,
                 margin: float = 0.008) -> list[int]:
    """覆盖纬度带的 HSD 段号(1-10,自北向南)。margin 抵消投影近似误差。"""
    vs = (v_fraction(lat_max, lon), v_fraction(lat_min, lon))
    lo, hi = min(vs) - margin, max(vs) + margin
    s0 = max(1, int(lo * N_SEGMENTS) + 1)
    s1 = min(N_SEGMENTS, int(hi * N_SEGMENTS) + 1)
    return list(range(s0, s1 + 1))


def bucket_for(ts: datetime) -> str:
    return "noaa-himawari9" if ts >= H9_START else "noaa-himawari8"


def sat_code(bucket: str) -> str:
    return "H09" if bucket.endswith("9") else "H08"


def hsd_key(ts: datetime, band: str, segment: int, *, sat: str) -> str:
    return (f"AHI-L1b-FLDK/{ts:%Y/%m/%d/%H%M}/"
            f"HS_{sat}_{ts:%Y%m%d_%H%M}_{band}_FLDK_{BAND_RES[band]}_"
            f"S{segment:02d}{N_SEGMENTS}.DAT.bz2")
```

- [ ] **Step 4: 跑测试确认通过**

Run: `.venv/bin/pytest tests/test_himawari_hsd.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add skyfire/src/skyfire/himawari_hsd.py skyfire/tests/test_himawari_hsd.py
git commit -m "feat(skyfire): AWS Himawari HSD 定位纯函数(GEOS 选段/桶切换/key 构造)"
```

---

### Task 2: HSD 段下载 + bz2 解压缓存

**Files:**
- Modify: `src/skyfire/himawari_hsd.py`
- Test: `tests/test_himawari_hsd.py`

- [ ] **Step 1: 写失败测试**(追加到 `tests/test_himawari_hsd.py`)

```python
import bz2

import httpx

from skyfire.himawari_hsd import download_segments


def _mock_client(store: dict) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        store.setdefault("urls", []).append(str(request.url))
        if "noaa-himawari9" in str(request.url) and store.get("h9_404"):
            return httpx.Response(404)
        return httpx.Response(200, content=bz2.compress(b"FAKE_HSD_DATA"))
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_download_segments_decompresses_and_caches(tmp_path):
    store = {}
    ts = datetime(2026, 5, 6, 10, 0, tzinfo=timezone.utc)
    paths = download_segments(_mock_client(store), ts, "B13", [2], tmp_path)
    assert len(paths) == 1
    assert paths[0].name == "HS_H09_20260506_1000_B13_FLDK_R20_S0210.DAT"
    assert paths[0].read_bytes() == b"FAKE_HSD_DATA"
    # 再次调用命中缓存,不再发请求
    n = len(store["urls"])
    download_segments(_mock_client(store), ts, "B13", [2], tmp_path)
    assert len(store["urls"]) == n


def test_download_segments_falls_back_to_other_bucket(tmp_path):
    store = {"h9_404": True}
    ts = datetime(2026, 5, 6, 10, 0, tzinfo=timezone.utc)  # 按日期主选 H9
    paths = download_segments(_mock_client(store), ts, "B13", [2], tmp_path)
    assert len(paths) == 1
    assert "noaa-himawari8" in store["urls"][-1]          # 回退到 H8
    assert paths[0].name.startswith("HS_H08_")


def test_download_segments_both_missing_returns_empty(tmp_path):
    def handler(request):
        return httpx.Response(404)
    client = httpx.Client(transport=httpx.MockTransport(handler))
    ts = datetime(2026, 5, 6, 10, 0, tzinfo=timezone.utc)
    assert download_segments(client, ts, "B13", [2], tmp_path) == []
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/bin/pytest tests/test_himawari_hsd.py -v -k download`
Expected: FAIL,`ImportError: cannot import name 'download_segments'`

- [ ] **Step 3: 实现**(追加到 `src/skyfire/himawari_hsd.py`)

```python
import bz2
from pathlib import Path

import httpx

S3_BASE = "https://{bucket}.s3.amazonaws.com/{key}"


def _try_bucket(client: httpx.Client, bucket: str, ts: datetime, band: str,
                segments: list[int], cache_dir: Path) -> list[Path] | None:
    """在单个桶下齐所有段;任何段 404 → 返回 None(让上层换桶)。"""
    sat = sat_code(bucket)
    out: list[Path] = []
    for seg in segments:
        key = hsd_key(ts, band, seg, sat=sat)
        dat = cache_dir / Path(key).name.removesuffix(".bz2")
        if not dat.exists():
            resp = client.get(S3_BASE.format(bucket=bucket, key=key))
            if resp.status_code != 200:
                return None
            dat.parent.mkdir(parents=True, exist_ok=True)
            dat.write_bytes(bz2.decompress(resp.content))
        out.append(dat)
    return out


def download_segments(client: httpx.Client, ts: datetime, band: str,
                      segments: list[int], cache_dir: Path) -> list[Path]:
    """下载并解压一个时刻的 HSD 段(幂等缓存)。两桶都缺 → []。"""
    cache_dir = Path(cache_dir)
    primary = bucket_for(ts)
    other = "noaa-himawari8" if primary.endswith("9") else "noaa-himawari9"
    for bucket in (primary, other):
        got = _try_bucket(client, bucket, ts, band, segments, cache_dir)
        if got is not None:
            return got
    return []
```

注意:缓存命中判断在 `_try_bucket` 内逐段进行,两颗星文件名不同(H08/H09),回退桶不会误命中主桶缓存。

- [ ] **Step 4: 跑测试确认通过**

Run: `.venv/bin/pytest tests/test_himawari_hsd.py -v`
Expected: 8 passed

- [ ] **Step 5: Commit**

```bash
git add skyfire/src/skyfire/himawari_hsd.py skyfire/tests/test_himawari_hsd.py
git commit -m "feat(skyfire): HSD 段下载+bz2 解压缓存(双桶回退,幂等)"
```

---

### Task 3: 渲染纯函数(BT/反射率 → 灰度)

**Files:**
- Create: `src/skyfire/render.py`
- Test: `tests/test_render.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_render.py
import numpy as np

from skyfire.render import bt_to_gray, refl_to_gray


def test_bt_to_gray_cold_is_white():
    bt = np.array([[180.0, 310.0], [245.0, np.nan]])
    g = bt_to_gray(bt)
    assert g.dtype == np.uint8
    assert g[0, 0] == 255          # 极冷云顶 → 白
    assert g[0, 1] == 0            # 暖地表 → 黑
    assert 100 <= g[1, 0] <= 155   # 中间温度 → 中灰
    assert g[1, 1] == 0            # NaN(缺测/盘外)→ 黑


def test_bt_to_gray_clips_outside_range():
    g = bt_to_gray(np.array([[150.0, 340.0]]))
    assert g[0, 0] == 255 and g[0, 1] == 0


def test_refl_to_gray_sqrt_stretch():
    r = np.array([[0.0, 25.0, 100.0, np.nan]])
    g = refl_to_gray(r)
    assert g.dtype == np.uint8
    assert g[0, 0] == 0
    assert g[0, 2] == 255
    assert abs(int(g[0, 1]) - 127) <= 2   # sqrt(0.25)=0.5 → ~127
    assert g[0, 3] == 0
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/bin/pytest tests/test_render.py -v`
Expected: FAIL,`ModuleNotFoundError: No module named 'skyfire.render'`

- [ ] **Step 3: 实现**

```python
# src/skyfire/render.py
"""HSD 波段 → 学习用灰度 PNG。

判读口径(knowledge §5):红外 BT 越冷越白(高云亮、低云暗灰);
可见光反射率 sqrt 拉伸看纹理。NaN(盘外/缺测)→ 黑。
"""
import numpy as np

BT_MIN, BT_MAX = 180.0, 310.0   # K:平展到 0-255


def bt_to_gray(bt: np.ndarray) -> np.ndarray:
    """亮温(K)→ uint8 灰度,冷=白。"""
    g = (BT_MAX - bt) / (BT_MAX - BT_MIN)
    g = np.nan_to_num(np.clip(g, 0.0, 1.0), nan=0.0)
    return (g * 255).astype(np.uint8)


def refl_to_gray(refl: np.ndarray) -> np.ndarray:
    """反射率(%)→ uint8 灰度,sqrt 拉伸增强暗部纹理(晨昏可见光弱光)。"""
    g = np.sqrt(np.clip(refl, 0.0, 100.0) / 100.0)
    g = np.nan_to_num(g, nan=0.0)
    return (g * 255).astype(np.uint8)
```

- [ ] **Step 4: 跑测试确认通过**

Run: `.venv/bin/pytest tests/test_render.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add skyfire/src/skyfire/render.py skyfire/tests/test_render.py
git commit -m "feat(skyfire): BT/反射率→灰度渲染纯函数(冷=白,sqrt 拉伸)"
```

---

### Task 4: 安装 satpy + Scene 封装(HSD → 裁剪 → PNG / nowcast 区域数组)

**Files:**
- Modify: `pyproject.toml`、`src/skyfire/render.py`
- Test: `tests/test_render.py`

- [ ] **Step 1: 安装 satpy 并固化依赖**

`pyproject.toml` 的 `dependencies` 列表末尾加一行:

```toml
    "satpy>=0.50",
```

Run: `uv pip install --python .venv/bin/python satpy && .venv/bin/python -c "import satpy; print(satpy.__version__)"`
Expected: 打印版本号(拉入 xarray/dask/pyresample 等,约 1-2 分钟)

- [ ] **Step 2: 写失败测试**(追加到 `tests/test_render.py`;monkeypatch 假 Scene,不依赖真 HSD 文件)

```python
from pathlib import Path
from types import SimpleNamespace

from PIL import Image

import skyfire.render as render_mod
from skyfire.render import load_b13_region, render_band


class _FakeArea:
    def get_xy_from_lonlat(self, lon, lat):
        return 320, 240                     # (col, row)


class _FakeScene:
    created = []

    def __init__(self, reader=None, filenames=None):
        _FakeScene.created.append({"reader": reader, "filenames": filenames})
        self._data = {}

    def load(self, names, calibration=None):
        import numpy as np
        for n in names:
            values = (np.full((480, 640), 220.0) if n == "B13"
                      else np.full((480, 640), 36.0))
            self._data[n] = SimpleNamespace(values=values,
                                            attrs={"area": _FakeArea()})

    def crop(self, ll_bbox=None):
        return self

    def __getitem__(self, name):
        return self._data[name]


def test_render_band_writes_png(tmp_path, monkeypatch):
    monkeypatch.setattr(render_mod, "_scene_cls", lambda: _FakeScene)
    out = tmp_path / "frame.png"
    render_band([Path("seg.DAT")], "B13", (109, 35, 124, 45), out, max_px=400)
    img = Image.open(out)
    assert img.mode == "L"
    assert max(img.size) <= 400            # 下采样生效
    assert _FakeScene.created[-1]["reader"] == "ahi_hsd"


def test_load_b13_region_returns_gray_and_center(tmp_path, monkeypatch):
    monkeypatch.setattr(render_mod, "_scene_cls", lambda: _FakeScene)
    frame = load_b13_region([Path("seg.DAT")], (109, 35, 124, 45), 39.9, 116.4)
    assert frame.gray.shape == (480, 640)
    assert frame.gray[0, 0] == render_mod.bt_to_gray(
        __import__("numpy").array([[220.0]]))[0, 0]
    assert frame.center_px == (320, 240)
    assert frame.km_px == 2.0
```

- [ ] **Step 3: 跑测试确认失败**

Run: `.venv/bin/pytest tests/test_render.py -v -k "render_band or b13_region"`
Expected: FAIL,`ImportError: cannot import name 'render_band'`

- [ ] **Step 4: 实现**(追加到 `src/skyfire/render.py`)

```python
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

_CALIBRATION = {"B13": "brightness_temperature", "B03": "reflectance"}
_TO_GRAY = {"B13": bt_to_gray, "B03": refl_to_gray}


def _scene_cls():
    """延迟导入 satpy(重依赖);测试中被 monkeypatch。"""
    from satpy import Scene
    return Scene


def _load_cropped(dat_paths: list[Path], band: str, bbox: tuple) -> "object":
    scn = _scene_cls()(reader="ahi_hsd", filenames=[str(p) for p in dat_paths])
    scn.load([band], calibration=_CALIBRATION[band])
    return scn.crop(ll_bbox=bbox)[band]


def render_band(dat_paths: list[Path], band: str, bbox: tuple,
                out_png: Path, max_px: int = 1400) -> Path:
    """HSD 段 → 裁剪 bbox → 灰度 PNG(超宽则等比下采样)。"""
    data = _load_cropped(dat_paths, band, bbox)
    img = Image.fromarray(_TO_GRAY[band](data.values), mode="L")
    if max(img.size) > max_px:
        img.thumbnail((max_px, max_px))
    out_png = Path(out_png)
    out_png.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_png)
    return out_png


@dataclass
class HsdFrame:
    gray: "object"               # np.ndarray uint8,云顶越冷越亮
    center_px: tuple[int, int]   # 目标点 (x, y) 像素坐标
    km_px: float                 # 名义分辨率 km/px(B13=2.0)


def load_b13_region(dat_paths: list[Path], bbox: tuple,
                    lat: float, lon: float) -> HsdFrame:
    """nowcast 用:B13 裁剪数组 + 目标点像素坐标(接 cloudiness/drift)。"""
    data = _load_cropped(dat_paths, "B13", bbox)
    x, y = data.attrs["area"].get_xy_from_lonlat(lon, lat)
    return HsdFrame(gray=bt_to_gray(data.values), center_px=(int(x), int(y)),
                    km_px=2.0)
```

- [ ] **Step 5: 跑测试确认通过 + 全量回归**

Run: `.venv/bin/pytest tests/test_render.py -v && .venv/bin/pytest -q`
Expected: test_render 5 passed;全量 100+ passed(satpy 安装不破坏现有)

- [ ] **Step 6: Commit**

```bash
git add skyfire/pyproject.toml skyfire/src/skyfire/render.py skyfire/tests/test_render.py
git commit -m "feat(skyfire): satpy 场景封装(HSD→裁剪→PNG;nowcast 区域数组)"
```

---

### Task 5: `fetch_case_frames` 组装(下载 × 渲染 → 案例帧序列)

**Files:**
- Modify: `src/skyfire/himawari_hsd.py`
- Test: `tests/test_himawari_hsd.py`

帧策略(knowledge §5.4 连帧看趋势):红外 B13 取 peak−{0,30,60,90}min(默认 4 帧,全天可用);可见光 B03 取 peak−{30,90}min(2 帧,峰值时刻太阳过低弱光,取稍早帧看纹理)。

- [ ] **Step 1: 写失败测试**(追加到 `tests/test_himawari_hsd.py`)

```python
from pathlib import Path

import skyfire.himawari_hsd as hsd_mod
from skyfire.himawari_hsd import fetch_case_frames


def test_fetch_case_frames_orchestration(tmp_path, monkeypatch):
    calls = {"download": [], "render": []}

    def fake_download(client, ts, band, segments, cache_dir):
        calls["download"].append((ts, band, tuple(segments)))
        if band == "B03" and ts.minute == 30:      # 模拟单帧缺档
            return []
        return [Path(f"seg_{band}_{ts:%H%M}.DAT")]

    def fake_render(dat_paths, band, bbox, out_png, max_px=1400):
        calls["render"].append((band, str(out_png)))
        Path(out_png).parent.mkdir(parents=True, exist_ok=True)
        Path(out_png).write_bytes(b"png")
        return Path(out_png)

    monkeypatch.setattr(hsd_mod, "download_segments", fake_download)
    monkeypatch.setattr(hsd_mod, "render_band", fake_render)

    peak = datetime(2026, 5, 6, 10, 47, tzinfo=timezone.utc)
    frames = fetch_case_frames(object(), peak, tmp_path,
                               prefix="beijing_2026-05-06_sunset_glow")
    # ir 4 帧全出;vis 应 2 帧,其中 10:30 的缺档被跳过 → 共 5
    assert len(frames) == 5
    bands = [b for _, b, _ in frames]
    assert bands.count("ir") == 4 and bands.count("vis") == 1
    ts0, _, p0 = frames[0]
    assert ts0.minute % 10 == 0                       # 槽对齐
    assert p0.name.startswith("beijing_2026-05-06_sunset_glow_")
    # 段选择来自 CROP_BBOX(段 2)
    assert calls["download"][0][2] == (2,)
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/bin/pytest tests/test_himawari_hsd.py -v -k case_frames`
Expected: FAIL,`ImportError: cannot import name 'fetch_case_frames'`

- [ ] **Step 3: 实现**(追加到 `src/skyfire/himawari_hsd.py`)

```python
from datetime import timedelta

from skyfire.render import render_band

IR_OFFSETS_MIN = (0, 30, 60, 90)    # B13:峰值往前 4 帧看趋势
VIS_OFFSETS_MIN = (30, 90)          # B03:峰值时刻太阳过低,取稍早帧
_BANDS = {"ir": ("B13", IR_OFFSETS_MIN), "vis": ("B03", VIS_OFFSETS_MIN)}


def round_down_10min(ts: datetime) -> datetime:
    return ts.replace(minute=ts.minute - ts.minute % 10, second=0, microsecond=0)


def fetch_case_frames(client, peak_utc: datetime, frames_dir: Path, *,
                      prefix: str, bbox: tuple = CROP_BBOX,
                      hsd_cache: Path | None = None,
                      ) -> list[tuple[datetime, str, Path]]:
    """一个案例的学习帧序列:下载 HSD 段 → 渲染 PNG。

    返回 [(ts, "ir"|"vis", png_path)];单帧缺档跳过不失败(尽力语义)。
    """
    frames_dir = Path(frames_dir)
    cache = Path(hsd_cache) if hsd_cache else frames_dir / "hsd_cache"
    lon_mid = (bbox[0] + bbox[2]) / 2
    segs = segments_for(bbox[1], bbox[3], lon_mid)
    out: list[tuple[datetime, str, Path]] = []
    for channel, (band, offsets) in _BANDS.items():
        for off in offsets:
            ts = round_down_10min(peak_utc - timedelta(minutes=off))
            dats = download_segments(client, ts, band, segs, cache)
            if not dats:
                continue
            png = frames_dir / f"{prefix}_{ts:%H%M}_{channel}.png"
            render_band(dats, band, bbox, png)
            out.append((ts, channel, png))
    return out
```

- [ ] **Step 4: 跑测试确认通过**

Run: `.venv/bin/pytest tests/test_himawari_hsd.py -v`
Expected: 9 passed

- [ ] **Step 5: Commit**

```bash
git add skyfire/src/skyfire/himawari_hsd.py skyfire/tests/test_himawari_hsd.py
git commit -m "feat(skyfire): fetch_case_frames 案例帧组装(ir×4+vis×2,缺档跳过)"
```

---

### Task 6: 历史通道剖面 + 历史 AOD(openmeteo)

**Files:**
- Modify: `src/skyfire/openmeteo.py`
- Test: `tests/test_openmeteo.py`

- [ ] **Step 1: 写失败测试**(追加到 `tests/test_openmeteo.py`)

```python
import httpx

from skyfire.geo import GeoPoint
from skyfire.openmeteo import fetch_aod_range, fetch_channel_profile_range


def test_fetch_channel_profile_range_hits_historical_endpoint():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["host"] = request.url.host
        seen["params"] = dict(request.url.params)
        loc = {"hourly": {"time": ["2026-05-06T18:00", "2026-05-06T19:00"],
                          "cloud_cover": [70, 80], "cloud_cover_low": [10, 20]}}
        return httpx.Response(200, json=[loc, loc])

    client = httpx.Client(transport=httpx.MockTransport(handler))
    pts = [GeoPoint(lat=40.0, lon=115.0, dist_km=100),
           GeoPoint(lat=40.1, lon=114.0, dist_km=200)]
    prof = fetch_channel_profile_range(client, pts, "Asia/Shanghai",
                                       "2026-05-06T19:00", "2026-05-06")
    assert seen["host"] == "historical-forecast-api.open-meteo.com"
    assert seen["params"]["start_date"] == "2026-05-06"
    assert [p.dist_km for p in prof] == [100, 200]
    assert prof[0].cloud_low == 20 and prof[0].cloud_total == 80


def test_fetch_aod_range_returns_value_or_none():
    def handler(request: httpx.Request) -> httpx.Response:
        assert dict(request.url.params)["start_date"] == "2026-05-06"
        return httpx.Response(200, json={"hourly": {
            "time": ["2026-05-06T19:00"], "aerosol_optical_depth": [0.42]}})
    client = httpx.Client(transport=httpx.MockTransport(handler))
    assert fetch_aod_range(client, 39.9, 116.4, "Asia/Shanghai",
                           "2026-05-06T19:00", "2026-05-06") == 0.42

    def handler_err(request):
        return httpx.Response(400)   # CAMS 存档边界外(<2022-07-29)
    client = httpx.Client(transport=httpx.MockTransport(handler_err))
    assert fetch_aod_range(client, 39.9, 116.4, "Asia/Shanghai",
                           "2020-09-01T18:00", "2020-09-01") is None
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/bin/pytest tests/test_openmeteo.py -v -k "range"`
Expected: FAIL,`ImportError: cannot import name 'fetch_channel_profile_range'`

- [ ] **Step 3: 实现**(追加到 `src/skyfire/openmeteo.py`)

```python
def fetch_channel_profile_range(
    client: httpx.Client, points: list[GeoPoint], tz: str, iso_hour: str,
    date: str, model: str = "gfs_seamless",
) -> list[ChannelPoint]:
    """历史通道剖面(冷启动回填用):同 fetch_channel_profile,走历史存档端点。

    救活 G_channel 硬门槛(knowledge §2-A):回填案例此前 channel=[] 恒中性。
    """
    resp = client.get(HISTORICAL_FORECAST_URL, params={
        "latitude": ",".join(str(round(p.lat, 3)) for p in points),
        "longitude": ",".join(str(round(p.lon, 3)) for p in points),
        "timezone": tz, "hourly": "cloud_cover,cloud_cover_low",
        "models": model, "start_date": date, "end_date": date,
    })
    resp.raise_for_status()
    data = resp.json()
    locations = data if isinstance(data, list) else [data]
    profile = []
    for geo, loc in zip(points, locations):
        hourly = loc["hourly"]
        low = total = None
        for i, t in enumerate(hourly["time"]):
            if t == iso_hour:
                total = hourly["cloud_cover"][i]
                low = hourly["cloud_cover_low"][i]
                break
        profile.append(ChannelPoint(dist_km=geo.dist_km, cloud_low=low, cloud_total=total))
    return profile


def fetch_aod_range(client: httpx.Client, lat: float, lon: float, tz: str,
                    iso_hour: str, date: str) -> float | None:
    """历史 AOD(尽力):CAMS 存档约 2022-07-29 起,边界外/失败返回 None。"""
    try:
        resp = client.get(AIR_QUALITY_URL, params={
            "latitude": lat, "longitude": lon, "timezone": tz,
            "hourly": "aerosol_optical_depth",
            "start_date": date, "end_date": date,
        })
        resp.raise_for_status()
        hourly = resp.json()["hourly"]
        for t, v in zip(hourly["time"], hourly["aerosol_optical_depth"]):
            if t == iso_hour:
                return v
    except (httpx.HTTPError, KeyError, ValueError):
        return None
    return None
```

- [ ] **Step 4: 跑测试确认通过**

Run: `.venv/bin/pytest tests/test_openmeteo.py -v`
Expected: 全部 passed(原有 + 新 2)

- [ ] **Step 5: Commit**

```bash
git add skyfire/src/skyfire/openmeteo.py skyfire/tests/test_openmeteo.py
git commit -m "feat(skyfire): 历史通道剖面+历史AOD 采集(救活回填 G_channel)"
```

---

### Task 7: backfill 接真数据(AWS 帧 + 通道 + AOD)+ 帧去重

**Files:**
- Modify: `src/skyfire/backfill.py`、`src/skyfire/store.py`、`src/skyfire/cli.py`(backfill 命令 help)
- Test: `tests/test_backfill.py`(存在则改,不存在则建)、`tests/test_store.py`(同)

- [ ] **Step 1: 写失败测试**(建/改 `tests/test_backfill.py`;先看现有文件,有同名测试则更新)

```python
# tests/test_backfill.py 中新增/替换
from datetime import datetime, timezone
from pathlib import Path

import httpx

import skyfire.backfill as backfill_mod
from skyfire import store
from skyfire.backfill import BackfillRow, backfill_row
from skyfire.config import City
from skyfire.models import ChannelPoint


def _forecast_payload():
    return {"hourly": {
        "time": ["2026-05-06T19:00"], "cloud_cover": [80], "cloud_cover_low": [0],
        "cloud_cover_mid": [20], "cloud_cover_high": [90],
        "relative_humidity_2m": [50], "wind_speed_10m": [3],
        "temperature_2m": [20], "dew_point_2m": [10], "precipitation": [0]}}


def test_backfill_row_feeds_channel_aod_and_aws_frames(tmp_path, monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_forecast_payload())
    client = httpx.Client(transport=httpx.MockTransport(handler))

    monkeypatch.setattr(backfill_mod, "fetch_channel_profile_range",
                        lambda *a, **k: [ChannelPoint(dist_km=200, cloud_low=90,
                                                      cloud_total=95)])
    monkeypatch.setattr(backfill_mod, "fetch_aod_range", lambda *a, **k: 0.5)
    fake_ts = datetime(2026, 5, 6, 10, 40, tzinfo=timezone.utc)

    def fake_frames(client, peak_utc, frames_dir, *, prefix, **kw):
        p = Path(frames_dir) / f"{prefix}_1040_ir.png"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"png")
        return [(fake_ts, "ir", p)]

    monkeypatch.setattr(backfill_mod, "fetch_case_frames", fake_frames)

    conn = store.connect(":memory:")
    store.init_db(conn)
    row = BackfillRow(date="2026-05-06", city="beijing", event="sunset_glow", score=10)
    city = City(key="beijing", name="北京", lat=39.9, lon=116.4,
                timezone="Asia/Shanghai")
    r = backfill_row(conn, client, row, city, frames_dir=tmp_path)

    assert r.n_frames == 1
    snaps = store.get_snapshots(conn, r.case_id)
    payload = snaps[0]["payload"]
    assert payload["aod"] == 0.5
    assert payload["channel"] == [{"km": 200, "low": 90, "total": 95}]
    frames = store.get_frames(conn, r.case_id)
    assert frames[0]["channel"] == "ir"
    # 通道全堵 → channel_factor 0.1 → 规则分被压低(不再恒中性)
    case = conn.execute("SELECT rule_score FROM cases WHERE id=?",
                        (r.case_id,)).fetchone()
    assert case[0] is not None and case[0] < 2.0


def test_backfill_row_rerun_does_not_duplicate_frames(tmp_path, monkeypatch):
    def handler(request):
        return httpx.Response(200, json=_forecast_payload())
    client = httpx.Client(transport=httpx.MockTransport(handler))
    monkeypatch.setattr(backfill_mod, "fetch_channel_profile_range", lambda *a, **k: [])
    monkeypatch.setattr(backfill_mod, "fetch_aod_range", lambda *a, **k: None)
    fake_ts = datetime(2026, 5, 6, 10, 40, tzinfo=timezone.utc)

    def fake_frames(client, peak_utc, frames_dir, *, prefix, **kw):
        p = Path(frames_dir) / f"{prefix}_1040_ir.png"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"png")
        return [(fake_ts, "ir", p)]

    monkeypatch.setattr(backfill_mod, "fetch_case_frames", fake_frames)
    conn = store.connect(":memory:")
    store.init_db(conn)
    row = BackfillRow(date="2026-05-06", city="beijing", event="sunset_glow", score=10)
    city = City(key="beijing", name="北京", lat=39.9, lon=116.4,
                timezone="Asia/Shanghai")
    r1 = backfill_row(conn, client, row, city, frames_dir=tmp_path)
    r2 = backfill_row(conn, client, row, city, frames_dir=tmp_path)
    assert len(store.get_frames(conn, r2.case_id)) == 1   # 幂等,不重复
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/bin/pytest tests/test_backfill.py -v -k "channel_aod or duplicate"`
Expected: FAIL(`fetch_channel_profile_range` 不在 backfill 命名空间 / 帧重复)

- [ ] **Step 3: store 加帧唯一索引**(`src/skyfire/store.py`)

SCHEMA 字符串末尾(`notifications` 表定义后)追加:

```sql
CREATE UNIQUE INDEX IF NOT EXISTS idx_frames_dedup
  ON satellite_frames(case_id, ts, channel);
```

`add_satellite_frame` 的 INSERT 改为:

```python
def add_satellite_frame(conn, case_id: int, ts: str, channel: str, path: str) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO satellite_frames (case_id, ts, channel, path)"
        " VALUES (?, ?, ?, ?)",
        (case_id, ts, channel, path),
    )
    conn.commit()
```

注意:旧库已有重复行会导致建唯一索引失败;当前库 frames 表为空(2026-07-05 已清),`CREATE UNIQUE INDEX IF NOT EXISTS` 在 `init_db` 时对旧库自动补建。

- [ ] **Step 4: 改写 `backfill_row`**(`src/skyfire/backfill.py`)

imports 区变更:删 `from skyfire.himawari import fetch_region, round_down_10min` 与 `from PIL import Image`,新增:

```python
from skyfire.geo import channel_points
from skyfire.himawari_hsd import fetch_case_frames
from skyfire.openmeteo import (fetch_aod_range, fetch_channel_profile_range,
                               fetch_point_forecast_range)
```

`backfill_row` 全函数替换为:

```python
def backfill_row(conn, client: httpx.Client, row: BackfillRow, city: City,
                 frames_dir, n_frames: int = 4) -> BackfillResult:
    """单条清单 → 完整案例:历史快照 + 真实通道/AOD + AWS 卫星帧。

    通道剖面与 AOD 走历史存档(尽力,失败→中性);帧走 AWS HSD 归档
    (ir×4 + vis×2,单帧缺档跳过)。幂等:重跑覆盖快照分、帧去重。
    """
    day = date_type.fromisoformat(row.date)
    win = sun_window(city.lat, city.lon, city.timezone, day,
                     "sunrise_glow" if row.event == "cloud_sea" else row.event)
    iso_hour = win.peak.strftime("%Y-%m-%dT%H:00")

    pts = channel_points(city.lat, city.lon, win.azimuth_deg)
    try:
        channel = fetch_channel_profile_range(client, pts, city.timezone,
                                              iso_hour, row.date)
    except httpx.HTTPError:
        channel = []                       # 存档边界外:退回"缺数据不罚"
    aod = fetch_aod_range(client, city.lat, city.lon, city.timezone,
                          iso_hour, row.date)

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
            aod=aod, channel=channel,
        ))
        per_model[fc.model] = r.score
    rule = consensus(per_model).index if per_model else None
    conf = consensus(per_model).confidence if per_model else None

    case_id = store.upsert_case(conn, row.date, row.city, row.event,
                                rule_score=rule, confidence=conf, source="cold_start")
    store.set_actual_score(conn, case_id, row.score)
    channel_json = [{"km": p.dist_km, "low": p.cloud_low, "total": p.cloud_total}
                    for p in channel]
    for fc in forecasts:
        h = fc.at(iso_hour)
        if h is None:
            continue
        store.add_snapshot(conn, case_id, fc.model, {
            "hour": iso_hour, "cloud_high": h.cloud_high, "cloud_mid": h.cloud_mid,
            "cloud_low": h.cloud_low, "cloud_cover": h.cloud_cover,
            "rh_2m": h.rh_2m, "precipitation": h.precipitation, "aod": aod,
            "channel": channel_json, "azimuth": round(win.azimuth_deg, 1),
        })

    frames_dir = Path(frames_dir)
    frames_dir.mkdir(parents=True, exist_ok=True)
    peak_utc = win.peak.astimezone(timezone.utc)
    prefix = f"{row.city}_{row.date}_{row.event}"
    saved = 0
    frames = fetch_case_frames(client, peak_utc, frames_dir, prefix=prefix)
    for ts, ch, path in frames:
        store.add_satellite_frame(conn, case_id, ts.isoformat(), ch, str(path))
        saved += 1
    return BackfillResult(case_id=case_id, n_frames=saved, n_models=len(per_model))
```

同步小改:`cli.py` backfill 命令的 `frames` 选项默认与 help 改为 `frames: int = typer.Option(4, help="每案例红外帧数(另含可见光 2 帧)")`(参数仍传入 `n_frames`,当前实现固定 offsets,保留参数为兼容,不再使用可留 TODO 注释删除:直接删掉 `--frames` 选项与 `n_frames` 形参更干净——采用后者:CLI 去掉 `frames` 选项,`backfill_row` 去掉 `n_frames` 形参)。

注意快照重跑幂等:`add_snapshot` 是纯 INSERT,重跑会累积多份快照(`cases_with_snapshot` 取 MAX(id) 无碍,但体积涨)。本任务顺手修:`backfill_row` 在写快照前执行
```python
conn.execute("DELETE FROM forecast_snapshots WHERE case_id=?", (case_id,))
```
(冷启动快照本就该反映最近一次回填)。

- [ ] **Step 5: 跑测试确认通过 + 全量回归**

Run: `.venv/bin/pytest tests/test_backfill.py -v && .venv/bin/pytest -q`
Expected: 新测试 passed;全量绿(若 test_smoke / 其他测试引用了 backfill 旧签名或 NICT,按同思路更新断言)

- [ ] **Step 6: Commit**

```bash
git add skyfire/src/skyfire/backfill.py skyfire/src/skyfire/store.py skyfire/src/skyfire/cli.py skyfire/tests/
git commit -m "feat(skyfire): backfill 喂真通道/AOD+AWS 卫星帧,快照与帧幂等"
```

---

### Task 8: nowcast 切 AWS B13(修 NICT 红外 404)

**Files:**
- Modify: `src/skyfire/himawari_hsd.py`(`latest_slot`)、`src/skyfire/cli.py`(nowcast 命令)、`src/skyfire/himawari.py`(注释)
- Test: `tests/test_himawari_hsd.py`

- [ ] **Step 1: 写失败测试**(追加到 `tests/test_himawari_hsd.py`)

```python
from skyfire.himawari_hsd import latest_slot


def test_latest_slot_scans_back_until_found():
    ok_ts = {"20260704_1340"}

    def handler(request: httpx.Request) -> httpx.Response:
        if any(k in str(request.url) for k in ok_ts):
            return httpx.Response(200, content=bz2.compress(b"D"))
        return httpx.Response(404)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    now = datetime(2026, 7, 4, 14, 5, tzinfo=timezone.utc)
    ts = latest_slot(client, now, max_back=8)
    assert ts == datetime(2026, 7, 4, 13, 40, tzinfo=timezone.utc)


def test_latest_slot_none_when_nothing_recent():
    client = httpx.Client(transport=httpx.MockTransport(
        lambda request: httpx.Response(404)))
    now = datetime(2026, 7, 4, 14, 5, tzinfo=timezone.utc)
    assert latest_slot(client, now, max_back=3) is None
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/bin/pytest tests/test_himawari_hsd.py -v -k latest_slot`
Expected: FAIL,`ImportError: cannot import name 'latest_slot'`

- [ ] **Step 3: 实现 `latest_slot`**(追加到 `src/skyfire/himawari_hsd.py`)

```python
def latest_slot(client: httpx.Client, now: datetime,
                max_back: int = 6) -> datetime | None:
    """最近一个有 B13 数据的 10 分钟槽(AWS 落档延迟数分钟,向前回扫)。

    以 HEAD 代价试探段文件是否存在(GET 到即缓存复用,成本可接受:2.8MB)。
    """
    lon_mid = (CROP_BBOX[0] + CROP_BBOX[2]) / 2
    segs = segments_for(CROP_BBOX[1], CROP_BBOX[3], lon_mid)
    ts = round_down_10min(now)
    for _ in range(max_back):
        bucket = bucket_for(ts)
        key = hsd_key(ts, "B13", segs[0], sat=sat_code(bucket))
        resp = client.head(S3_BASE.format(bucket=bucket, key=key))
        if resp.status_code == 200:
            return ts
        ts -= timedelta(minutes=10)
    return None
```

等一下——测试用的 MockTransport handler 对 HEAD 同样生效(httpx MockTransport 不区分 method,handler 收到 request 可看 method)。测试断言按 URL 匹配即可,无需改。

- [ ] **Step 4: 改 `cli.py` nowcast 命令**

imports:删 `from skyfire.himawari import (fetch_region, frame_age_minutes, km_per_px, latest_frame_time, round_down_10min)`,新增:

```python
from skyfire.himawari import frame_age_minutes
from skyfire.himawari_hsd import (CROP_BBOX, download_segments, latest_slot,
                                  round_down_10min, segments_for)
from skyfire.render import load_b13_region
```

nowcast 函数中卫星获取段(原 `try: ts1 = latest_frame_time(...) ... frame0 = fetch_region(...)` 到融合前)替换为:

```python
    client = _make_client()
    cache = frames_dir / "hsd_cache"
    lon_mid = (CROP_BBOX[0] + CROP_BBOX[2]) / 2
    segs = segments_for(CROP_BBOX[1], CROP_BBOX[3], lon_mid)
    try:
        ts1 = latest_slot(client, now)
        if ts1 is None:
            raise httpx.HTTPError("近 1 小时无卫星档")
        dats1 = download_segments(client, ts1, "B13", segs, cache)
        ts0 = round_down_10min(ts1 - timedelta(minutes=10))
        dats0 = download_segments(client, ts0, "B13", segs, cache)
    except httpx.HTTPError as e:
        typer.echo(f"错误:卫星数据请求失败({e.__class__.__name__}: {e}),"
                   f"以规则分为准", err=True)
        raise typer.Exit(1)
    if not dats1:
        typer.echo(f"🛰  {today} {event} 实况修正 — {c.name}")
        typer.echo("卫星帧全缺(归档未落/超出覆盖),不参与融合,以规则分为准", err=True)
        typer.echo(f"综合分: {rule_score}/10(规则分 {rule_score})")
        return
    frame1 = load_b13_region(dats1, CROP_BBOX, c.lat, c.lon)
    age = frame_age_minutes(ts1, now)
    local = box_cloudiness(frame1.gray, frame1.center_px, half=40)
    step_px = max(1, round(100 / frame1.km_px))
    if dats0:
        frame0 = load_b13_region(dats0, CROP_BBOX, c.lat, c.lon)
        shift = estimate_shift(frame0.gray, frame1.gray)
    else:
        shift = (0, 0)
```

其后 `extrapolated_corridor(frame1.gray, frame1.center_px, ...)`、存帧 `Image.fromarray(frame1.gray, mode="L").save(path)`、`store.add_satellite_frame(conn, case_id, ts1.isoformat(), "ir", str(path))`(channel 由 `"infrared"` 统一改为 `"ir"`)保持原逻辑。原 `frame1.gray.max() == 0` 分支删除(缺档已由 `not dats1` 覆盖)。`km_per_px(frame1.level)` 调用点已被 `frame1.km_px` 替代。

`src/skyfire/himawari.py` 顶部 docstring 追加一行:

```python
# 注意(2026-07):NICT INFRARED_FULL 产品已 404,红外一律走 himawari_hsd(AWS);
# 本模块仅 truecolor 快看与 latest.json 仍可用。
```

- [ ] **Step 5: 跑全量回归**

Run: `.venv/bin/pytest -q`
Expected: 全绿(nowcast 的 CLI 测试如有 NICT mock,按新函数路径更新 monkeypatch 目标为 `skyfire.cli.latest_slot` / `skyfire.cli.download_segments` / `skyfire.cli.load_b13_region`)

- [ ] **Step 6: Commit**

```bash
git add skyfire/src/skyfire/himawari_hsd.py skyfire/src/skyfire/cli.py skyfire/src/skyfire/himawari.py skyfire/tests/
git commit -m "fix(skyfire): nowcast 红外切 AWS HSD(NICT INFRARED_FULL 已 404)"
```

---

### Task 9: 预报云图网格(gridmap + cloudmap 命令)

**Files:**
- Create: `src/skyfire/gridmap.py`
- Modify: `src/skyfire/cli.py`
- Test: `tests/test_gridmap.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_gridmap.py
import httpx
from PIL import Image

from skyfire.gridmap import fetch_cloud_grid, grid_points, render_grid_png

BBOX = (110.0, 36.0, 122.0, 44.0)   # lon0, lat0, lon1, lat1


def test_grid_points_row_major_north_first():
    pts = grid_points(BBOX, step=2.0)
    lats = sorted({lat for lat, _ in pts}, reverse=True)
    assert lats[0] == 44.0 and lats[-1] == 36.0
    assert len(pts) == 5 * 7           # lat 44..36 step2 ×5, lon 110..122 step2 ×7


def test_fetch_cloud_grid_shapes_and_endpoint():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["host"] = request.url.host
        n = len(dict(request.url.params)["latitude"].split(","))
        loc = {"hourly": {"time": ["2026-05-06T19:00"],
                          "cloud_cover_high": [80], "cloud_cover_mid": [40],
                          "cloud_cover_low": [5]}}
        return httpx.Response(200, json=[loc] * n)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    pts = grid_points(BBOX, step=2.0)
    grid = fetch_cloud_grid(client, pts, 5, 7, "Asia/Shanghai",
                            "2026-05-06T19:00", date="2026-05-06")
    assert seen["host"] == "historical-forecast-api.open-meteo.com"
    assert set(grid) == {"high", "mid", "low"}
    assert len(grid["high"]) == 5 and len(grid["high"][0]) == 7
    assert grid["high"][0][0] == 80 and grid["low"][0][0] == 5


def test_render_grid_png_triple_panel(tmp_path):
    grid = {k: [[v] * 7 for _ in range(5)]
            for k, v in (("high", 80), ("mid", 40), ("low", 5))}
    out = render_grid_png(grid, tmp_path / "clouds.png", label="2026-05-06 19:00")
    img = Image.open(out)
    assert img.width > img.height * 2      # 三联横排
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/bin/pytest tests/test_gridmap.py -v`
Expected: FAIL,`ModuleNotFoundError: No module named 'skyfire.gridmap'`

- [ ] **Step 3: 实现**

```python
# src/skyfire/gridmap.py
"""预报云图网格(knowledge §6:预报的空间形态,弥补点预报盲区)。

Open-Meteo 网格采样(多点一次请求)→ 高/中/低云三联灰度热图。
亮=云多。看图口径:高云板块+破口(画布)、西侧低云(堵通道)。
"""
from pathlib import Path

import httpx
from PIL import Image, ImageDraw

from skyfire.openmeteo import FORECAST_URL, HISTORICAL_FORECAST_URL

LAYERS = ("high", "mid", "low")
DEFAULT_BBOX = (110.0, 36.0, 122.0, 44.0)
DEFAULT_STEP = 1.0
CELL_PX = 26
_CHUNK = 100          # 单请求坐标上限(保守)


def grid_points(bbox: tuple, step: float) -> list[tuple[float, float]]:
    """行主序(北→南,西→东)的 (lat, lon) 网格点。"""
    lon0, lat0, lon1, lat1 = bbox
    lats, lons = [], []
    v = lat1
    while v >= lat0 - 1e-9:
        lats.append(round(v, 3)); v -= step
    u = lon0
    while u <= lon1 + 1e-9:
        lons.append(round(u, 3)); u += step
    return [(lat, lon) for lat in lats for lon in lons]


def fetch_cloud_grid(client: httpx.Client, pts: list[tuple[float, float]],
                     n_rows: int, n_cols: int, tz: str, iso_hour: str,
                     date: str | None = None, model: str = "gfs_seamless",
                     ) -> dict[str, list[list[float | None]]]:
    """峰值小时的高/中/低云网格。date=None 走预报端点,否则走历史存档。"""
    values: dict[str, list] = {k: [] for k in LAYERS}
    for i in range(0, len(pts), _CHUNK):
        chunk = pts[i:i + _CHUNK]
        params = {
            "latitude": ",".join(str(p[0]) for p in chunk),
            "longitude": ",".join(str(p[1]) for p in chunk),
            "timezone": tz, "models": model,
            "hourly": "cloud_cover_high,cloud_cover_mid,cloud_cover_low",
        }
        if date is None:
            url = FORECAST_URL
            params["forecast_days"] = 3
        else:
            url = HISTORICAL_FORECAST_URL
            params.update(start_date=date, end_date=date)
        resp = client.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()
        locations = data if isinstance(data, list) else [data]
        for loc in locations:
            hourly = loc["hourly"]
            idx = next((j for j, t in enumerate(hourly["time"]) if t == iso_hour), None)
            for layer in LAYERS:
                col = hourly.get(f"cloud_cover_{layer}")
                values[layer].append(col[idx] if idx is not None and col else None)
    return {layer: [values[layer][r * n_cols:(r + 1) * n_cols]
                    for r in range(n_rows)] for layer in LAYERS}


def _panel(grid: list[list[float | None]], title: str) -> Image.Image:
    rows, cols = len(grid), len(grid[0])
    img = Image.new("L", (cols * CELL_PX, rows * CELL_PX + 18), 0)
    d = ImageDraw.Draw(img)
    for r, row in enumerate(grid):
        for c, v in enumerate(row):
            shade = 32 if v is None else int(round(v * 2.55))
            d.rectangle([c * CELL_PX, 18 + r * CELL_PX,
                         (c + 1) * CELL_PX - 1, 18 + (r + 1) * CELL_PX - 1],
                        fill=shade)
    d.text((4, 3), title, fill=255)
    return img


def render_grid_png(grid: dict, out_png: Path, *, label: str) -> Path:
    """高/中/低三联横排热图(北在上、西在左;亮=云多)。"""
    panels = [_panel(grid[layer], f"{layer.upper()}  {label}") for layer in LAYERS]
    w = sum(p.width for p in panels) + 8 * (len(panels) - 1)
    h = max(p.height for p in panels)
    canvas = Image.new("L", (w, h), 12)
    x = 0
    for p in panels:
        canvas.paste(p, (x, 0)); x += p.width + 8
    out_png = Path(out_png)
    out_png.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out_png)
    return out_png
```

- [ ] **Step 4: 跑测试确认通过**

Run: `.venv/bin/pytest tests/test_gridmap.py -v`
Expected: 3 passed

- [ ] **Step 5: 加 `cloudmap` CLI 命令**(`src/skyfire/cli.py`,`backtest` 命令后插入)

```python
DEFAULT_GRIDMAPS = Path(__file__).parent.parent.parent / "data" / "gridmaps"


@app.command()
def cloudmap(
    city: str = typer.Option("beijing"),
    event: str = typer.Option("sunset_glow", help="sunset_glow | sunrise_glow"),
    date: str = typer.Option(None, help="YYYY-MM-DD,默认今天;过去日期走历史存档"),
    config: Path = typer.Option(DEFAULT_CONFIG),
    out_dir: Path = typer.Option(DEFAULT_GRIDMAPS),
):
    """预报云图:峰值小时高/中/低云三联热图(亮=云多,西=左)。"""
    from skyfire.gridmap import (DEFAULT_BBOX, DEFAULT_STEP, fetch_cloud_grid,
                                 grid_points, render_grid_png)
    cities = load_cities(config)
    if city not in cities:
        typer.echo(f"错误:未知城市 {city!r},可用: {', '.join(cities)}", err=True)
        raise typer.Exit(1)
    c = cities[city]
    day = _parse_date(date, date_type.today())
    win = sun_window(c.lat, c.lon, c.timezone, day, event)
    iso_hour = win.peak.strftime("%Y-%m-%dT%H:00")
    pts = grid_points(DEFAULT_BBOX, DEFAULT_STEP)
    n_cols = len({lon for _, lon in pts})
    n_rows = len(pts) // n_cols
    client = _make_client()
    hist = day < date_type.today()
    try:
        grid = fetch_cloud_grid(client, pts, n_rows, n_cols, c.timezone, iso_hour,
                                date=str(day) if hist else None)
    except httpx.HTTPError as e:
        typer.echo(f"错误:Open-Meteo 请求失败({e.__class__.__name__}: {e})", err=True)
        raise typer.Exit(1)
    out = render_grid_png(grid, out_dir / f"{city}_{day}_{event}_clouds.png",
                          label=f"{day} {win.peak:%H:%M}")
    typer.echo(f"预报云图: {out}")
```

- [ ] **Step 6: 跑全量回归**

Run: `.venv/bin/pytest -q`
Expected: 全绿

- [ ] **Step 7: Commit**

```bash
git add skyfire/src/skyfire/gridmap.py skyfire/src/skyfire/cli.py skyfire/tests/test_gridmap.py
git commit -m "feat(skyfire): 预报云图网格三联热图 + cloudmap 命令"
```

---

### Task 10: case_notes 表 + 案例卡 + `analyze` 命令

**Files:**
- Modify: `src/skyfire/store.py`、`src/skyfire/llm.py`、`src/skyfire/cli.py`
- Create: `src/skyfire/analyze.py`
- Test: `tests/test_analyze.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_analyze.py
from skyfire import store
from skyfire.analyze import build_case_card


def _mk_case(conn):
    cid = store.upsert_case(conn, "2026-05-06", "beijing", "sunset_glow",
                            rule_score=2.0, confidence="low", source="cold_start")
    store.set_actual_score(conn, cid, 10.0)
    store.add_snapshot(conn, cid, "gfs_seamless", {
        "hour": "2026-05-06T19:00", "cloud_high": 100, "cloud_mid": 17,
        "cloud_low": 0, "rh_2m": 40, "precipitation": 0, "aod": 0.3,
        "channel": [{"km": 200, "low": 10, "total": 30}], "azimuth": 295.6})
    return cid


def test_case_notes_roundtrip():
    conn = store.connect(":memory:")
    store.init_db(conn)
    cid = _mk_case(conn)
    store.add_case_note(conn, cid, "llm", "通道通畅+高云破口 → 大烧")
    store.add_case_note(conn, cid, "user", "实际是雨后初晴,西侧裂开")
    notes = store.get_case_notes(conn, cid)
    assert [n["author"] for n in notes] == ["llm", "user"]
    assert "雨后初晴" in notes[1]["text"]


def test_case_by_key():
    conn = store.connect(":memory:")
    store.init_db(conn)
    cid = _mk_case(conn)
    case = store.case_by_key(conn, "2026-05-06", "beijing", "sunset_glow")
    assert case["id"] == cid and case["actual_score"] == 10.0
    assert store.case_by_key(conn, "1999-01-01", "beijing", "sunset_glow") is None


def test_build_case_card_contains_domain_sections():
    conn = store.connect(":memory:")
    store.init_db(conn)
    cid = _mk_case(conn)
    case = store.case_by_key(conn, "2026-05-06", "beijing", "sunset_glow")
    card = build_case_card(case, store.get_snapshots(conn, cid),
                           store.get_frames(conn, cid),
                           store.get_case_notes(conn, cid))
    assert "2026-05-06" in card and "实际 10.0" in card
    for section in ("通道", "云幕", "大气", "卫星形态", "结论"):
        assert section in card
    assert "200km low=10" in card        # 通道剖面进卡片
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/bin/pytest tests/test_analyze.py -v`
Expected: FAIL,`ImportError: cannot import name 'add_case_note'`

- [ ] **Step 3: store 实现**(`src/skyfire/store.py`)

SCHEMA 追加(唯一索引语句之前):

```sql
CREATE TABLE IF NOT EXISTS case_notes (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  case_id INTEGER NOT NULL REFERENCES cases(id),
  author TEXT NOT NULL CHECK(author IN ('user','llm')),
  text TEXT NOT NULL,
  created_at TEXT DEFAULT (datetime('now'))
);
```

文件末尾追加:

```python
def add_case_note(conn, case_id: int, author: str, text: str) -> None:
    conn.execute(
        "INSERT INTO case_notes (case_id, author, text) VALUES (?, ?, ?)",
        (case_id, author, text),
    )
    conn.commit()


def get_case_notes(conn, case_id: int) -> list[dict]:
    rows = conn.execute(
        "SELECT author, text, created_at FROM case_notes WHERE case_id=? ORDER BY id",
        (case_id,),
    ).fetchall()
    return [{"author": a, "text": t, "created_at": ct} for a, t, ct in rows]


def case_by_key(conn, date: str, city: str, event: str) -> dict | None:
    row = conn.execute(
        """SELECT id, date, city, event, rule_score, llm_score, actual_score,
                  confidence FROM cases WHERE date=? AND city=? AND event=?""",
        (date, city, event),
    ).fetchone()
    if row is None:
        return None
    keys = ("id", "date", "city", "event", "rule_score", "llm_score",
            "actual_score", "confidence")
    return dict(zip(keys, row))
```

- [ ] **Step 4: 案例卡实现**(`src/skyfire/analyze.py`)

```python
# src/skyfire/analyze.py
"""案例学习卡(knowledge §8):把一条闭环案例组装成可判读的 markdown。

五段固定骨架(通道/云幕/大气/卫星形态/结论)是经验笔记的口径,
LLM 或用户沿骨架填"为什么是这个分"。
"""


def _channel_line(payload: dict) -> str:
    ch = payload.get("channel") or []
    if not ch:
        return "(无剖面数据)"
    return "  ".join(f"{p['km']:.0f}km low={p['low']} total={p['total']}"
                     for p in ch if p.get("low") is not None)


def build_case_card(case: dict, snapshots: list[dict], frames: list[dict],
                    notes: list[dict]) -> str:
    payload = snapshots[-1]["payload"] if snapshots else {}
    lines = [
        f"# 案例 {case['date']} {case['city']} {case['event']}",
        f"实际 {case['actual_score']} 分 | 规则 {case['rule_score']}"
        f" | 置信 {case['confidence']}",
        "",
        f"## 通道(方位 {payload.get('azimuth', '?')}°)",
        _channel_line(payload),
        "",
        "## 云幕(点预报)",
        f"高云 {payload.get('cloud_high')}%  中云 {payload.get('cloud_mid')}%"
        f"  低云 {payload.get('cloud_low')}%",
        "",
        "## 大气",
        f"AOD {payload.get('aod')}  地表RH {payload.get('rh_2m')}%"
        f"  降水 {payload.get('precipitation')}mm",
        "",
        "## 卫星形态",
    ]
    if frames:
        lines += [f"- {f['ts']} [{f['channel']}] {f['path']}" for f in frames]
    else:
        lines.append("(无卫星帧)")
    lines += ["", "## 结论(为什么是这个分)"]
    if notes:
        lines += [f"- [{n['author']}] {n['text']}" for n in notes]
    else:
        lines.append("(待分析)")
    return "\n".join(lines)
```

- [ ] **Step 5: 跑测试确认通过**

Run: `.venv/bin/pytest tests/test_analyze.py -v`
Expected: 3 passed

- [ ] **Step 6: `llm.explain` + CLI `analyze`**

`src/skyfire/llm.py` 末尾追加(测试:`tests/test_llm.py` 加一条,见下):

```python
_EXPLAIN_SYSTEM = (
    "你是资深火烧云预报员。给你一条已知实际得分的历史案例卡与当天卫星云图"
    "(红外:云顶越冷越亮;可见光:看纹理)。请解释为什么这天是这个分,"
    "按五段输出:通道/云幕/大气/卫星形态/结论。判读口径:透光通道是否被"
    "低云堵、云幕是否中高云带破口、空气是否通透、正在降水否决但雨后初晴是"
    "利好。若预报与实际背离,点名哪一因子骗了预报。只输出这五段中文,"
    "每段一两句。"
)


def explain(card_md: str, frame_paths: list[Path], client=None) -> str | None:
    """案例复盘解读(analyze 命令用);失败静默 → None(spec 8)。"""
    try:
        if client is None:
            import anthropic
            client = anthropic.Anthropic()
        content: list[dict] = [{"type": "text", "text": card_md}]
        for p in frame_paths[:6]:
            data = base64.standard_b64encode(Path(p).read_bytes()).decode()
            content.append({"type": "image",
                            "source": {"type": "base64", "media_type": "image/png",
                                       "data": data}})
        resp = client.messages.create(
            model=MODEL, max_tokens=2000, thinking={"type": "adaptive"},
            system=_EXPLAIN_SYSTEM,
            messages=[{"role": "user", "content": content}],
        )
        text = next((b.text for b in resp.content if b.type == "text"), "")
        return text.strip() or None
    except Exception:
        return None
```

`tests/test_llm.py` 追加:

```python
from skyfire.llm import explain


class _FakeMsg:
    def __init__(self, text):
        from types import SimpleNamespace
        self.content = [SimpleNamespace(type="text", text=text)]


class _FakeClient:
    def __init__(self, text):
        self._text = text
        from types import SimpleNamespace
        self.messages = SimpleNamespace(create=lambda **kw: _FakeMsg(self._text))


def test_explain_returns_text():
    assert explain("卡片", [], client=_FakeClient("通道:通畅…")) == "通道:通畅…"


def test_explain_swallow_failure():
    class Boom:
        def __getattr__(self, name):
            raise RuntimeError
    assert explain("卡片", [], client=Boom()) is None
```

`src/skyfire/cli.py` 追加命令(`cloudmap` 后):

```python
@app.command()
def analyze(
    date: str = typer.Option(..., help="案例日期 YYYY-MM-DD"),
    city: str = typer.Option("beijing"),
    event: str = typer.Option("sunset_glow"),
    db: Path = typer.Option(DEFAULT_DB),
    no_llm: bool = typer.Option(False, "--no-llm"),
    save: bool = typer.Option(False, "--save", help="把 LLM 解读存为案例笔记"),
    note: str = typer.Option(None, "--note", help="追加一条用户笔记并退出"),
):
    """案例复盘:案例卡 + 云图 LLM 解读(为什么是这个分),沉淀经验笔记。"""
    from skyfire.analyze import build_case_card
    from skyfire.llm import explain
    conn = _open_db(db)
    case = store.case_by_key(conn, date, city, event)
    if case is None:
        typer.echo(f"错误:无案例 {date} {city} {event}(先 backfill/打分)", err=True)
        raise typer.Exit(1)
    if note:
        store.add_case_note(conn, case["id"], "user", note)
        typer.echo("✓ 已记用户笔记")
        return
    snaps = store.get_snapshots(conn, case["id"])
    frames = store.get_frames(conn, case["id"])
    notes = store.get_case_notes(conn, case["id"])
    card = build_case_card(case, snaps, frames, notes)
    typer.echo(card)
    if no_llm:
        return
    paths = [Path(f["path"]) for f in frames if Path(f["path"]).exists()]
    result = explain(card, paths)
    if result is None:
        typer.echo("\nAI 解读暂缺(无凭证或调用失败)", err=True)
        return
    typer.echo("\n===== AI 复盘 =====\n" + result)
    if save:
        store.add_case_note(conn, case["id"], "llm", result)
        typer.echo("✓ 已存为案例笔记")
```

- [ ] **Step 7: 跑全量回归**

Run: `.venv/bin/pytest -q`
Expected: 全绿

- [ ] **Step 8: Commit**

```bash
git add skyfire/src/skyfire/store.py skyfire/src/skyfire/analyze.py skyfire/src/skyfire/llm.py skyfire/src/skyfire/cli.py skyfire/tests/
git commit -m "feat(skyfire): 案例复盘 analyze 命令 + case_notes 经验笔记"
```

---

### Task 11: 相似案例检索带经验笔记(RAG 闭环)

**Files:**
- Modify: `src/skyfire/store.py`(`cases_with_snapshot`)、`src/skyfire/llm.py`(`build_content`)
- Test: `tests/test_llm.py`、`tests/test_analyze.py`

- [ ] **Step 1: 写失败测试**

`tests/test_analyze.py` 追加:

```python
def test_cases_with_snapshot_carries_latest_note():
    conn = store.connect(":memory:")
    store.init_db(conn)
    cid = _mk_case(conn)
    store.add_case_note(conn, cid, "llm", "第一条")
    store.add_case_note(conn, cid, "user", "西侧通道裂开是关键")
    cases = store.cases_with_snapshot(conn, "beijing", "sunset_glow",
                                      model="gfs_seamless")
    assert cases[0]["note"] == "西侧通道裂开是关键"
```

`tests/test_llm.py` 追加:

```python
from skyfire.llm import build_content


def test_build_content_includes_similar_case_note():
    today = {"date": "2026-07-05", "event": "sunset_glow", "rule_score": 5,
             "confidence": "low", "payload": {}}
    similar = [{"date": "2026-05-06", "actual_score": 10, "distance": 0.1,
                "payload": {}, "note": "西侧通道裂开是关键"}]
    content = build_content(today, similar, [])
    text = content[0]["text"]
    assert "西侧通道裂开是关键" in text
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/bin/pytest tests/test_analyze.py::test_cases_with_snapshot_carries_latest_note tests/test_llm.py::test_build_content_includes_similar_case_note -v`
Expected: FAIL(无 `note` 键 / 文本无笔记)

- [ ] **Step 3: 实现**

`store.cases_with_snapshot` 的 SQL 与返回替换为:

```python
    rows = conn.execute(
        """SELECT c.id, c.date, c.actual_score, s.payload,
                  (SELECT text FROM case_notes WHERE case_id=c.id
                   ORDER BY id DESC LIMIT 1) AS note
           FROM cases c JOIN forecast_snapshots s ON s.case_id = c.id
           WHERE c.city=? AND c.event=? AND c.actual_score IS NOT NULL AND s.model=?
             AND s.id = (SELECT MAX(id) FROM forecast_snapshots
                         WHERE case_id=c.id AND model=?)
           ORDER BY c.date""",
        (city, event, model, model),
    ).fetchall()
    return [{"case_id": i, "date": d, "actual_score": a,
             "payload": json.loads(p), "note": n}
            for i, d, a, p, n in rows]
```

`llm.build_content` 中相似案例循环体改为:

```python
    for c in similar:
        lines.append(f"- {c['date']} 实际 {c['actual_score']} 分 距离 {c['distance']}"
                     f" 因子 {json.dumps(c.get('payload', {}), ensure_ascii=False)}")
        if c.get("note"):
            lines.append(f"  经验笔记: {c['note'][:120]}")
```

- [ ] **Step 4: 跑全量回归**

Run: `.venv/bin/pytest -q`
Expected: 全绿(`engine.py` 里 `similar_cases_from(cases, ...)` 透传 dict,`note` 键自动带过去,无需改 engine/rag)

- [ ] **Step 5: Commit**

```bash
git add skyfire/src/skyfire/store.py skyfire/src/skyfire/llm.py skyfire/tests/
git commit -m "feat(skyfire): 相似案例检索携带经验笔记,预测解读吃到复盘经验"
```

---

### Task 12: 真实端到端验证(不是单测,是拿真数据交卷)

**Files:** 无代码;产出验证记录 + 更新记忆。

- [ ] **Step 1: 单案例冒烟(先烧最贵的不确定性:satpy 真解 HSD)**

```bash
cd /Users/feitong/photo-app/skyfire
.venv/bin/skyfire backfill --csv <(echo "date,city,event,score
2026-05-06,beijing,sunset_glow,10")
```

Expected: `✓ 2026-05-06 sunset_glow 实际 10.0 分(快照 4 模式,卫星帧 6)`;`data/frames/` 出现 `beijing_2026-05-06_sunset_glow_*_ir.png` ×4 与 `*_vis.png` ×2。**打开 PNG 目检**:红外应见云系形态(不是全黑/全白),可见光有纹理。若 satpy 报 reader 错,记录报错原文再修——这是本计划最大技术风险点,单案例先验证。
(注:typer 的 csv 参数接 `<()` 进程替换路径可行;不行则写临时文件。)

- [ ] **Step 2: 全量 21 条回填**

```bash
.venv/bin/skyfire backfill --csv data/coldstart.csv
```

Expected: 21 条 ✓;2022-12 前的日子走 H8 桶;2020-09-01(历史预报存档外)`快照 0 模式` 但**卫星帧照出**(AWS 归档覆盖)。下载量约 1.2GB、耗时约 20-40 分钟。

- [ ] **Step 3: 重跑回测,记录新 ρ**

```bash
.venv/bin/skyfire backtest --city beijing
```

Expected: 打印新 Spearman ρ。**预期通道数据喂进后 ρ 显著抬升(>0.3 即验证 G_channel 价值);若没抬,把逐案例通道剖面打出来对照分析,这本身就是学习材料。**如实记录,不粉饰。

- [ ] **Step 4: 历史预报云图 + 满分日复盘**

```bash
.venv/bin/skyfire cloudmap --date 2026-05-06 --event sunset_glow
.venv/bin/skyfire analyze --date 2026-05-06 --event sunset_glow --save
```

Expected: 三联云图 PNG 落地;analyze 打印案例卡 + AI 复盘五段(无凭证则提示暂缺,卡片仍出)。把 AI 复盘拿给用户校准——**这是用户方法论的第一个闭环:云图 → 分析 → 用户矫正 → 笔记入库**。

- [ ] **Step 5: nowcast 冒烟(验证 AWS 准实时延迟)**

```bash
.venv/bin/skyfire predict --no-llm && .venv/bin/skyfire nowcast
```

Expected: nowcast 不再报 NICT 404;`latest_slot` 找到 ≤60 分钟内的槽。若 AWS 落档延迟长于 60 分钟,记录实测延迟,调 `max_back`。

- [ ] **Step 6: 提交验证记录与收尾**

```bash
git add -A && git commit -m "docs(skyfire): Plan D 端到端验证记录(新回测 ρ + 首个案例复盘)"
```

并更新记忆 `skyfire-coldstart-progress.md`:新 ρ、帧/云图落地情况、用户对首个 AI 复盘的矫正意见、下一步(逐案例 analyze 攒笔记 → 攒够后按笔记证据重构 firecloud v2)。

---

## Self-Review 结果

- **Spec 覆盖**:用户三点诉求——历史云图(Task 1-7)、预报云图(Task 9)、"对着云图分析为什么 X 分"并累计资料(Task 10-11)——各有任务落点;附带修复 NICT 404(Task 8)与通道数据空缺(Task 6-7,ρ=0.026 头号病因)。打分公式重构显式推迟(header 说明),不算缺口。
- **占位符扫描**:无 TBD/TODO 留白;唯一"视情况"步骤是 Task 7 Step 5 与 Task 8 Step 5 对既有测试的适配,已给出 monkeypatch 目标路径。
- **类型一致性**:`fetch_case_frames` 返回 `list[(datetime, str, Path)]`,Task 5/7 一致;`HsdFrame.gray/center_px/km_px` 在 Task 4/8 一致;`ChannelPoint(dist_km, cloud_low, cloud_total)` 与现有 models.py 一致;`store.case_by_key` 返回 dict 键与 Task 10 用法一致;`channel` 存库 JSON 键 `km/low/total` 与现网 engine.py 口径一致。
- **风险点**:satpy 对分段 HSD/裁剪的真实行为(Task 12 Step 1 最先验证);AWS 准实时延迟(Task 12 Step 5);Open-Meteo 多点/网格请求配额(网格已 chunk=100,回填串行)。
