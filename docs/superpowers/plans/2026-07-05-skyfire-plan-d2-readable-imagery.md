# Skyfire Plan D-2:可判读云图(燃烧时刻时序 + 高度伪彩 + 地理标注)实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 Plan D 产出的"不堪判读的灰度帧"升级成"能对着总结经验的云图":①取图时刻对准真正的燃烧时刻(晚霞日落后、朝霞日出前)且红外/可见光分到日落两侧;②红外按云顶温度伪彩上色区分高/中/低云;③叠加北京点标 + 晚霞朝西/朝霞朝东的通道线 + 100–500km 距离环,一眼定位云洞。

**Architecture:** 纯函数优先——`case_frame_times`(时序,himawari_hsd)、`bt_to_rgb`(伪彩,render)、overlay 的几何(marker/corridor 纯函数)独立可测;`render_annotated` 在持有 pyresample area 的渲染期完成标注(saved PNG 不携带地理信息,必须渲染时画);`fetch_case_frames` 透传 event/lat/lon/azimuth,backfill 重回填 126 帧。**分高中低云用已在下的 B13 伪彩,不引入多波段 RGB 的额外下载**(见"设计取舍")。

**Tech Stack:** Python 3.12(skyfire/.venv)、satpy/pyresample(已装)、Pillow、numpy、pytest。领域依据:`docs/superpowers/knowledge/2026-07-05-firecloud-domain-knowledge.md`(§1 燃烧在日落后/日出前、§2-A 通道方向性、§5 红外亮温=云高)。

**设计取舍(为什么伪彩而非多波段 RGB):** 用户 scope 提"satpy Day Cloud Phase/Airmass RGB 分高中低云",但那些合成需额外下 WV/多可见光波段(数据翻数倍)。而"高/中/低"本质是云顶高度,B13(10.4µm)亮温**已经**是云高代理(冷=高)——把它从灰度换成**按温度锚点的伪彩**即可直接区分,零额外下载、老日子一致适用。多波段真 RGB、cartopy 海岸线、SLIDER 最近彩图列入"后置增强",非本计划核心。

**背景事实(已核准 2026-07-05):**
- `pyresample` AreaDefinition 有 `get_array_indices_from_lonlat(lon,lat)->(col,row)`(用它;`get_xy_from_lonlat` 已弃用)。
- CJK 字体:`/System/Library/Fonts/STHeiti Medium.ttc` 存在(PingFang 在本机不在);回退 `Hiragino Sans GB.ttc`,再回退 PIL 默认。
- 现状:`fetch_case_frames(client, peak_utc, frames_dir, *, prefix, bbox=CROP_BBOX, hsd_cache=None)`(himawari_hsd.py:141),用 `IR_OFFSETS_MIN=(0,30,60,90)`/`VIS_OFFSETS_MIN=(30,90)` 两侧都取 peak−offset(**对晚霞是错的**:燃烧在日落后)。backfill.py:122 只传 prefix;`win.azimuth_deg` 在 :75/:114 可用。
- Plan D 已合入 main;当前 126 帧时刻偏早、无标注,本计划末重回填覆盖。

**约定:** 在 `/Users/feitong/photo-app/skyfire` 下跑;`.venv/bin/pytest`。commit 中文 `feat(skyfire): ...`,body 末加 `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`。先建分支 `feat/skyfire-plan-d2`(用户已要求先合并 Plan D,故从 main 起新分支)。

---

## 文件结构

| 文件 | 职责 |
|---|---|
| Modify `src/skyfire/himawari_hsd.py` | `case_frame_times(peak_utc, event)` 事件感知时序;`fetch_case_frames` 透传 event/lat/lon/azimuth,改调 `render_annotated` |
| Modify `src/skyfire/render.py` | `bt_to_rgb`(云顶温度伪彩);`render_annotated`(裁剪→伪彩/灰度→叠标注→PNG) |
| Create `src/skyfire/overlay.py` | `cjk_font`、`marker_xy`、`corridor_marks`(纯几何)、`draw_overlay`(PIL 绘制) |
| Modify `src/skyfire/backfill.py` | `backfill_row` 给 `fetch_case_frames` 传 event(有效天象)/lat/lon/azimuth |
| Test | `tests/test_himawari_hsd.py`、`tests/test_render.py`、`tests/test_overlay.py`(新)、`tests/test_backfill.py` |

---

### Task 1:事件感知取图时序(case_frame_times)

**Files:** Modify `src/skyfire/himawari_hsd.py`;Test `tests/test_himawari_hsd.py`

燃烧时刻(knowledge §1):晚霞最佳在日落后 ~15min,朝霞在日出前 ~15min。红外(热成像不怕黑)取燃烧侧、可见光(要日光看云型)取相反侧。

- [ ] **Step 1: 写失败测试**(追加)

```python
from skyfire.himawari_hsd import case_frame_times


def test_case_frame_times_sunset_ir_after_vis_before():
    peak = datetime(2026, 5, 6, 11, 13, tzinfo=timezone.utc)  # 日落(UTC)
    times = case_frame_times(peak, "sunset_glow")
    base = datetime(2026, 5, 6, 11, 10, tzinfo=timezone.utc)  # round_down_10min(peak)
    ir = [t for t, ch in times if ch == "ir"]
    vis = [t for t, ch in times if ch == "vis"]
    assert len(ir) == 4 and len(vis) == 2
    assert all(t >= base for t in ir)      # 红外在日落后(燃烧时刻)
    assert all(t <= base for t in vis)     # 可见光在日落前(日光)
    assert all(t.minute % 10 == 0 for t, _ in times)
    assert max(ir) == base + timedelta(minutes=30)   # 覆盖到日落后30min


def test_case_frame_times_sunrise_mirrored():
    peak = datetime(2026, 1, 7, 23, 30, tzinfo=timezone.utc)  # 日出(UTC)
    times = case_frame_times(peak, "sunrise_glow")
    base = datetime(2026, 1, 7, 23, 30, tzinfo=timezone.utc)
    ir = [t for t, ch in times if ch == "ir"]
    vis = [t for t, ch in times if ch == "vis"]
    assert all(t <= base for t in ir)      # 红外在日出前(燃烧时刻)
    assert all(t >= base for t in vis)     # 可见光在日出后(日光)
    assert min(ir) == base - timedelta(minutes=30)
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/bin/pytest tests/test_himawari_hsd.py -v -k case_frame_times`
Expected: FAIL,`ImportError: cannot import name 'case_frame_times'`

- [ ] **Step 3: 实现**(在 himawari_hsd.py 中,替换现有 `IR_OFFSETS_MIN/VIS_OFFSETS_MIN/_BANDS` 定义为下述;`round_down_10min` 已存在)

```python
IR_BURN_MIN = (0, 10, 20, 30)   # 燃烧时刻窗:晚霞日落后 / 朝霞日出前
VIS_DAY_MIN = (20, 40)          # 日光侧读云型:晚霞日落前 / 朝霞日出后
_BAND_OF = {"ir": "B13", "vis": "B03"}


def case_frame_times(peak_utc: datetime, event: str) -> list[tuple[datetime, str]]:
    """按天象把取图时刻分到日落/日出正确一侧(knowledge §1)。

    晚霞:红外取日落后(燃烧),可见光取日落前(日光);朝霞相反。
    返回 [(ts, "ir"|"vis")],均对齐 10 分钟槽。
    """
    sunset = event == "sunset_glow"
    ir_sign = 1 if sunset else -1          # 燃烧侧
    out = [(round_down_10min(peak_utc + timedelta(minutes=ir_sign * m)), "ir")
           for m in IR_BURN_MIN]
    out += [(round_down_10min(peak_utc + timedelta(minutes=-ir_sign * m)), "vis")
            for m in VIS_DAY_MIN]
    return out
```

- [ ] **Step 4: 跑测试确认通过**

Run: `.venv/bin/pytest tests/test_himawari_hsd.py -v -k case_frame_times`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add skyfire/src/skyfire/himawari_hsd.py skyfire/tests/test_himawari_hsd.py
git commit -m "feat(skyfire): 取图时序对准燃烧时刻(晚霞日落后/朝霞日出前,红外可见光分两侧)"
```

---

### Task 2:云顶温度伪彩(bt_to_rgb,分高中低云)

**Files:** Modify `src/skyfire/render.py`;Test `tests/test_render.py`

按亮温锚点插值上色:暖顶(低云)偏棕、中云灰、冷顶(高云)偏蓝、极冷(深对流)白;NaN→黑。这样单张 B13 就能读出云高。

- [ ] **Step 1: 写失败测试**(追加)

```python
from skyfire.render import bt_to_rgb


def test_bt_to_rgb_height_by_temperature():
    import numpy as np
    rgb = bt_to_rgb(np.array([[300.0, 253.0, 223.0], [205.0, np.nan, 268.0]]))
    assert rgb.dtype == np.uint8 and rgb.shape == (2, 3, 3)
    warm = rgb[0, 0]     # 300K 暖地表/无云 → 近黑
    high = rgb[0, 2]     # 223K 高云冷顶 → 偏蓝(B 通道最大)
    coldest = rgb[1, 0]  # 205K 极冷 → 近白
    nan = rgb[1, 1]      # NaN → 黑
    assert int(warm.max()) <= 40
    assert high[2] > high[0] and high[2] > 150          # 蓝主导
    assert coldest.min() > 200                          # 近白
    assert tuple(int(v) for v in nan) == (0, 0, 0)
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/bin/pytest tests/test_render.py -v -k bt_to_rgb`
Expected: FAIL,`ImportError: cannot import name 'bt_to_rgb'`

- [ ] **Step 3: 实现**(追加到 render.py)

```python
# 云顶温度锚点 → RGB(暖=低云棕、中云灰、冷=高云蓝、极冷白);线性插值
_BT_ANCHORS = [
    (300.0, (10, 10, 10)),      # 暖地表/无云
    (283.0, (95, 70, 45)),      # 低云(暖顶)
    (268.0, (150, 150, 150)),   # 低/中云
    (253.0, (220, 220, 220)),   # 中云
    (238.0, (200, 225, 255)),   # 高云(冷顶,偏蓝)
    (223.0, (110, 175, 255)),   # 高云
    (205.0, (255, 255, 255)),   # 极冷云顶(深对流)
]


def bt_to_rgb(bt: "np.ndarray") -> "np.ndarray":
    """亮温(K)→ 伪彩 RGB uint8,按云顶温度区分云高。NaN→黑。"""
    temps = np.array([a[0] for a in _BT_ANCHORS])
    chans = np.array([a[1] for a in _BT_ANCHORS], dtype=float)   # (N,3),温度降序
    x = np.clip(bt, temps.min(), temps.max())
    out = np.zeros((*bt.shape, 3), dtype=np.uint8)
    for k in range(3):
        # temps 是降序,np.interp 需升序 → 反转
        out[..., k] = np.nan_to_num(
            np.interp(x, temps[::-1], chans[::-1, k]), nan=0.0
        ).astype(np.uint8)
    out[np.isnan(bt)] = 0
    return out
```

- [ ] **Step 4: 跑测试确认通过**

Run: `.venv/bin/pytest tests/test_render.py -v -k bt_to_rgb`
Expected: 1 passed

- [ ] **Step 5: Commit**

```bash
git add skyfire/src/skyfire/render.py skyfire/tests/test_render.py
git commit -m "feat(skyfire): B13 云顶温度伪彩(暖=低云/冷=高云),单波段区分云高"
```

---

### Task 3:地理标注 overlay(北京 + 通道线 + 距离环)

**Files:** Create `src/skyfire/overlay.py`;Test `tests/test_overlay.py`

几何(marker/corridor)是纯函数、可精确测;`draw_overlay` 只做 PIL 绘制。通道方向 = 传入的太阳方位角(晚霞≈西、朝霞≈东,由 backfill 的 `win.azimuth_deg` 提供)。

- [ ] **Step 1: 写失败测试**

```python
# tests/test_overlay.py
from PIL import Image

from skyfire.overlay import cjk_font, corridor_marks, draw_overlay, marker_xy


class _FakeArea:
    """经纬度→(col,row):col 随经度东增、row 随纬度北减(便于断言方向)。"""
    def get_array_indices_from_lonlat(self, lon, lat):
        return int(round((lon - 109.0) * 40)), int(round((45.0 - lat) * 40))


def test_marker_xy_maps_beijing():
    col, row = marker_xy(_FakeArea(), 39.9042, 116.4074)
    assert col == round((116.4074 - 109.0) * 40)
    assert row == round((45.0 - 39.9042) * 40)


def test_corridor_marks_go_west_for_sunset_azimuth():
    # 方位角 292.6°(西偏北):经度应比北京更小(更西)、纬度更高
    marks = corridor_marks(_FakeArea(), 39.9042, 116.4074, 292.6,
                           ranges_km=(100, 200, 300, 400, 500))
    assert [d for d, _, _ in marks] == [100, 200, 300, 400, 500]
    bx, _ = marker_xy(_FakeArea(), 39.9042, 116.4074)
    cols = [c for _, c, _ in marks]
    assert all(c < bx for c in cols)              # 全在北京以西(col 更小)
    assert cols == sorted(cols, reverse=True)      # 越远越西,单调


def test_corridor_marks_go_east_for_sunrise_azimuth():
    marks = corridor_marks(_FakeArea(), 39.9042, 116.4074, 65.0,
                           ranges_km=(100, 300))
    bx, _ = marker_xy(_FakeArea(), 39.9042, 116.4074)
    assert all(c > bx for _, c, _ in marks)        # 朝霞:通道朝东


def test_draw_overlay_changes_image_and_returns_it():
    img = Image.new("RGB", (600, 400), (0, 0, 0))
    before = img.tobytes()
    out = draw_overlay(img, _FakeArea(), 39.9042, 116.4074, 292.6, 1.0, 1.0,
                       ranges_km=(100, 200, 300))
    assert out is img and img.tobytes() != before   # 确有绘制


def test_cjk_font_loads():
    f = cjk_font(16)
    assert f is not None
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/bin/pytest tests/test_overlay.py -v`
Expected: FAIL,`ModuleNotFoundError: No module named 'skyfire.overlay'`

- [ ] **Step 3: 实现**

```python
# src/skyfire/overlay.py
"""云图地理标注(knowledge §2-A 通道方向性、§5 定位云洞)。

北京点标 + 太阳方位角通道线(晚霞朝西/朝霞朝东)+ 100–500km 距离环。
几何用 pyresample area 定位;纯几何函数独立可测,draw_overlay 只做绘制。
"""
from PIL import ImageDraw, ImageFont

from skyfire.geo import destination

_FONT_CANDIDATES = ("/System/Library/Fonts/STHeiti Medium.ttc",
                    "/System/Library/Fonts/Hiragino Sans GB.ttc")
_BEIJING = (255, 60, 60)
_CHANNEL = (80, 200, 255)


def cjk_font(size: int):
    """CJK 字体(标签用);找不到回退 PIL 默认。"""
    for path in _FONT_CANDIDATES:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


def marker_xy(area, lat: float, lon: float) -> tuple[int, int]:
    """经纬度 → 裁剪图内 (col, row) 像素索引。"""
    col, row = area.get_array_indices_from_lonlat(lon, lat)
    return int(col), int(row)


def corridor_marks(area, lat: float, lon: float, azimuth_deg: float,
                   ranges_km=(100, 200, 300, 400, 500)) -> list[tuple[int, int, int]]:
    """沿太阳方位角各距离处的 (dkm, col, row)。晚霞方位≈西→点在北京以西。"""
    out = []
    for dkm in ranges_km:
        plat, plon = destination(lat, lon, azimuth_deg, dkm)
        col, row = marker_xy(area, plat, plon)
        out.append((dkm, col, row))
    return out


def draw_overlay(img, area, lat: float, lon: float, azimuth_deg: float,
                 sx: float, sy: float, *,
                 ranges_km=(100, 200, 300, 400, 500), label: str = "北京"):
    """在 RGB 图上叠加北京十字+标签、通道线、距离环。sx/sy=输出/原生像素比。"""
    d = ImageDraw.Draw(img)
    f = cjk_font(16)
    bx, by = marker_xy(area, lat, lon)
    bx, by = bx * sx, by * sy
    marks = corridor_marks(area, lat, lon, azimuth_deg, ranges_km)
    # 通道线(北京 → 最远环再延一点)
    if marks:
        fx, fy = marks[-1][1] * sx, marks[-1][2] * sy
        d.line([(bx, by), (fx, fy)], fill=_CHANNEL, width=2)
    # 距离环 + 标签
    for dkm, col, row in marks:
        x, y = col * sx, row * sy
        d.ellipse([x - 5, y - 5, x + 5, y + 5], outline=_CHANNEL, width=2)
        d.text((x + 6, y + 3), f"{dkm}km", fill=_CHANNEL, font=f)
    # 北京十字 + 标签
    d.line([(bx - 14, by), (bx + 14, by)], fill=_BEIJING, width=3)
    d.line([(bx, by - 14), (bx, by + 14)], fill=_BEIJING, width=3)
    d.text((bx + 16, by - 20), label, fill=_BEIJING, font=f)
    return img
```

- [ ] **Step 4: 跑测试确认通过**

Run: `.venv/bin/pytest tests/test_overlay.py -v`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add skyfire/src/skyfire/overlay.py skyfire/tests/test_overlay.py
git commit -m "feat(skyfire): 云图地理标注(北京+方位角通道线+距离环,CJK 字体)"
```

---

### Task 4:render_annotated + fetch_case_frames/backfill 接线

**Files:** Modify `src/skyfire/render.py`、`src/skyfire/himawari_hsd.py`、`src/skyfire/backfill.py`;Test `tests/test_render.py`、`tests/test_himawari_hsd.py`

标注必须在渲染期做(saved PNG 不带 area)。`render_annotated` 持 area 完成"伪彩/灰度→resize→叠标注→存"。

- [ ] **Step 1: 写失败测试**(render 层,追加到 tests/test_render.py;复用 Task 4 已有的 `_FakeScene`/`_FakeArea`)

```python
def test_render_annotated_ir_is_rgb_with_overlay(tmp_path, monkeypatch):
    import numpy as np
    from PIL import Image

    import skyfire.render as render_mod
    from skyfire.render import render_annotated

    # 复用本文件既有 _FakeScene(load 返回 220K 常量 + _FakeArea)
    monkeypatch.setattr(render_mod, "_scene_cls", lambda: _FakeScene)
    out = tmp_path / "f.png"
    render_annotated([__import__("pathlib").Path("seg.DAT")], "B13",
                     (109, 35, 124, 45), out, lat=39.9, lon=116.4,
                     azimuth_deg=292.6, max_px=400)
    img = Image.open(out)
    assert img.mode == "RGB"                 # 伪彩输出
    assert max(img.size) <= 400
    # 叠了北京红标 → 存在明显偏红像素
    a = np.asarray(img).reshape(-1, 3)
    assert ((a[:, 0] > 150) & (a[:, 1] < 100) & (a[:, 2] < 100)).any()
```

`_FakeScene` 的 `__getitem__` 返回对象需带 `.attrs["area"]`(已有 `_FakeArea`)。若既有 `_FakeArea` 无 `get_array_indices_from_lonlat`,给它补一个返回 `(320, 240)` 的方法。

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/bin/pytest tests/test_render.py -v -k render_annotated`
Expected: FAIL,`ImportError: cannot import name 'render_annotated'`

- [ ] **Step 3: 实现 render_annotated**(追加到 render.py;import overlay)

```python
from skyfire.overlay import draw_overlay


def render_annotated(dat_paths: list[Path], band: str, bbox: tuple,
                     out_png: Path, *, lat: float, lon: float,
                     azimuth_deg: float, max_px: int = 1400) -> Path:
    """HSD 段 → 裁剪 → (B13 伪彩/B03 灰度) → 叠北京/通道/距离环 → PNG。"""
    data = _load_cropped(dat_paths, band, bbox)
    if band == "B13":
        arr = bt_to_rgb(data.values)
    else:
        g = refl_to_gray(data.values)
        arr = np.stack([g, g, g], axis=-1)
    img = Image.fromarray(arr, mode="RGB")
    nat_w, nat_h = img.size
    if max(img.size) > max_px:
        img.thumbnail((max_px, max_px))
    sx, sy = img.size[0] / nat_w, img.size[1] / nat_h
    draw_overlay(img, data.attrs["area"], lat, lon, azimuth_deg, sx, sy)
    out_png = Path(out_png)
    out_png.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_png)
    return out_png
```

- [ ] **Step 4: fetch_case_frames 透传 event/lat/lon/azimuth 并改用时序+标注**(himawari_hsd.py)

先写测试(追加到 tests/test_himawari_hsd.py,替换旧的 `test_fetch_case_frames_orchestration` 断言以适配新签名):

```python
def test_fetch_case_frames_uses_timing_and_annotation(tmp_path, monkeypatch):
    calls = {"render": []}

    def fake_download(client, ts, band, segments, cache_dir):
        return [Path(f"seg_{band}_{ts:%H%M}.DAT")]

    def fake_render_annotated(dat_paths, band, bbox, out_png, *, lat, lon,
                              azimuth_deg, max_px=1400):
        calls["render"].append((band, azimuth_deg, str(out_png)))
        Path(out_png).parent.mkdir(parents=True, exist_ok=True)
        Path(out_png).write_bytes(b"png")
        return Path(out_png)

    monkeypatch.setattr(hsd_mod, "download_segments", fake_download)
    monkeypatch.setattr(hsd_mod, "render_annotated", fake_render_annotated)

    peak = datetime(2026, 5, 6, 11, 13, tzinfo=timezone.utc)
    frames = fetch_case_frames(object(), peak, tmp_path,
                               prefix="beijing_2026-05-06_sunset_glow",
                               event="sunset_glow", lat=39.9, lon=116.4,
                               azimuth_deg=292.6)
    assert len(frames) == 6                     # ir×4 + vis×2
    base = datetime(2026, 5, 6, 11, 10, tzinfo=timezone.utc)
    ir_ts = [ts for ts, ch, _ in frames if ch == "ir"]
    assert all(ts >= base for ts in ir_ts)      # 红外在日落后
    assert calls["render"][0][1] == 292.6       # 方位角透传到渲染
```

实现:把 `fetch_case_frames` 改为

```python
def fetch_case_frames(client, peak_utc: datetime, frames_dir: Path, *,
                      prefix: str, event: str, lat: float, lon: float,
                      azimuth_deg: float, bbox: tuple = CROP_BBOX,
                      hsd_cache: Path | None = None,
                      ) -> list[tuple[datetime, str, Path]]:
    """案例学习帧:按燃烧时刻取时刻 → 下 HSD → 伪彩/灰度 + 地理标注。

    返回 [(ts, "ir"|"vis", png)];单帧缺档跳过(尽力)。
    """
    frames_dir = Path(frames_dir)
    cache = Path(hsd_cache) if hsd_cache else frames_dir / "hsd_cache"
    lon_mid = (bbox[0] + bbox[2]) / 2
    segs = segments_for(bbox[1], bbox[3], lon_mid)
    out: list[tuple[datetime, str, Path]] = []
    for ts, channel in case_frame_times(peak_utc, event):
        band = _BAND_OF[channel]
        dats = download_segments(client, ts, band, segs, cache)
        if not dats:
            continue
        png = frames_dir / f"{prefix}_{ts:%H%M}_{channel}.png"
        render_annotated(dats, band, bbox, png, lat=lat, lon=lon,
                         azimuth_deg=azimuth_deg)
        out.append((ts, channel, png))
    return out
```

顶部把 `from skyfire.render import render_band` 改为 `from skyfire.render import render_annotated`(render_band 若无其他引用可保留在 render.py 供 nowcast 之外场景;确认 nowcast 用的是 load_b13_region 不受影响)。

- [ ] **Step 5: backfill 传入 event/lat/lon/azimuth**(backfill.py:122 附近)

`fetch_case_frames` 调用改为:

```python
    eff_event = "sunrise_glow" if row.event == "cloud_sea" else row.event
    frames = fetch_case_frames(client, peak_utc, frames_dir, prefix=prefix,
                               event=eff_event, lat=city.lat, lon=city.lon,
                               azimuth_deg=win.azimuth_deg)
```

同步更新 tests/test_backfill.py 里对 `fetch_case_frames` 的 monkeypatch:其 fake 需接受 `event/lat/lon/azimuth_deg` 关键字(改成 `def fake_frames(client, peak_utc, frames_dir, *, prefix, **kw)` 即可吸收)。跑 test_backfill.py 确认仍绿。

- [ ] **Step 6: 跑相关测试 + 全量**

Run: `.venv/bin/pytest tests/test_render.py tests/test_himawari_hsd.py tests/test_backfill.py -v` 然后 `.venv/bin/pytest -q`
Expected: 全绿(新增用例通过;旧 orchestration 用例已被新用例替换或适配)

- [ ] **Step 7: Commit**

```bash
git add skyfire/src/skyfire/render.py skyfire/src/skyfire/himawari_hsd.py skyfire/src/skyfire/backfill.py skyfire/tests/
git commit -m "feat(skyfire): render_annotated 接线(伪彩+标注),backfill 传 event/方位角"
```

---

### Task 5:重回填 126 帧 + 目检

**Files:** 无代码;真数据 + 目检。

- [ ] **Step 1: 单案例先验(满分日)**

```bash
cd /Users/feitong/photo-app/skyfire
printf "date,city,event,score\n2026-05-06,beijing,sunset_glow,10\n" > /tmp/one.csv
.venv/bin/skyfire backfill --csv /tmp/one.csv 2>&1 | grep -v RuntimeWarning | tail -3
```
Expected: `✓ 2026-05-06 ...卫星帧 6`;打开 `data/frames/beijing_2026-05-06_sunset_glow_*_ir.png` 目检:红外应为**伪彩**(高云偏蓝/低云偏棕)、有**红色北京十字**、**朝西的蓝色通道线 + 100–500km 环**;红外帧时刻应为日落后(11:10/11:20/11:30/11:40),可见光为日落前(10:30/10:50)。

- [ ] **Step 2: 全量重回填(覆盖旧 126 帧)**

```bash
.venv/bin/skyfire backfill --csv data/coldstart.csv 2>&1 | grep -v RuntimeWarning | tail -5
```
Expected: 21 条 ✓;`data/frames/` 帧被新样式覆盖(同名文件名因时刻变化会新增,旧的可留可清:`ls data/frames | wc -l`)。

- [ ] **Step 3: 抽查朝霞案例方向相反**

打开一个 sunrise_glow 案例(如 `beijing_2026-01-07_sunrise_glow_*`):通道线应**朝东**、红外帧时刻在日出**前**、可见光在日出后。目检确认方向正确。

- [ ] **Step 4: 记录 + Commit(仅文档/记忆)**

更新记忆 `skyfire-coldstart-progress.md`:Plan D-2 完成、126 帧已按燃烧时刻重取并带高度伪彩+地理标注、用户目检结论。若有小样张问题(字体/配色/环距)记下待调。

```bash
git add -A && git commit -m "docs(skyfire): Plan D-2 重回填与目检记录"
```

---

## 后置增强(非本计划,验证核心可判读后再评估)

- **多波段真 RGB**(Airmass / Day Cloud Phase):更专业的云相/气团判读,但需额外下 WV/多可见光波段(himawari_hsd 增加波段集 + satpy composite);数据量翻数倍。
- **cartopy 海岸线/省界底图**:重依赖(GEOS/PROJ/shapely + 边界数据),叠加层已够用故后置。
- **SLIDER 最近日子彩色快照**:仅约 10 个月存档(覆盖不到 2020–2025 历史日),只能作"最近/向前"的成品彩图补充,不进历史主线。

## Self-Review 结果

- **Spec 覆盖**:①燃烧时刻时序=Task 1;②高中低云区分=Task 2(伪彩,替代多波段 RGB 的便宜方案,已在设计取舍说明);③北京+通道线+距离环=Task 3;接线重回填=Task 4/5。用户 4 块 scope 的 RGB/cartopy/SLIDER 显式列后置并说明原因。
- **占位符扫描**:无 TBD;唯一"适配旧测试"处(Task 4 Step 5)给了明确 monkeypatch 改法。
- **类型一致性**:`case_frame_times`→`[(datetime,str)]`(Task 1/4 一致);`render_annotated(...,*,lat,lon,azimuth_deg,max_px)` 签名 Task 4 内自洽;`fetch_case_frames` 新增 `event/lat/lon/azimuth_deg` 关键字,backfill 调用点同步(Task 4 Step 5);overlay 的 `marker_xy/corridor_marks/draw_overlay` 签名 Task 3 定义、Task 4 render_annotated 经 draw_overlay 使用一致;`bt_to_rgb` 返回 (H,W,3) uint8,render_annotated 按 RGB 用。
- **风险点**:pyresample `get_array_indices_from_lonlat` 真实返回顺序(col,row)需在 Task 5 目检北京十字是否落在画面中心确认;伪彩锚点配色可能需按目检微调(Task 5 记录待调)。
