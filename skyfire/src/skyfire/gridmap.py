"""预报云图网格(knowledge §6:预报的空间形态,弥补点预报盲区)。

Open-Meteo 网格采样(多点一次请求)→ 高/中/低云三联灰度热图。
亮=云多。看图口径:高云板块+破口(画布)、西侧低云(堵通道)。
"""
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx
import numpy as np
from PIL import Image, ImageDraw

from skyfire.openmeteo import (AIR_QUALITY_URL, FORECAST_URL,
                               HISTORICAL_FORECAST_URL)

LAYERS = ("high", "mid", "low")
DEFAULT_BBOX = (110.0, 36.0, 122.0, 44.0)   # 华北(cloudmap CLI 用)
DEFAULT_STEP = 0.5
# 全国图(用户 2026-07-08 定:覆盖整个中国更有用):东中南部火烧云相关区,
# 1°≈111km/格——全国尺度下每格占比小、配合平滑观感够细;点数~1000,并行拉取。
CHINA_BBOX = (100.0, 17.0, 135.0, 45.0)
CHINA_STEP = 1.0
CELL_PX = 26
_CHUNK = 100          # 单请求坐标上限(保守)
_MAX_PARALLEL = 1     # 顺序拉(免费层并发限流严,后台任务不赶时间,稳优先)


def _get_retry(client, url, params, tries=4):
    """GET,遇 429 限流指数退避重试(免费层并发/分钟限流)。"""
    for i in range(tries):
        resp = client.get(url, params=params)
        if resp.status_code == 429 and i < tries - 1:
            time.sleep(1.5 * (i + 1))
            continue
        resp.raise_for_status()
        return resp
    resp.raise_for_status()
    return resp


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
                     with_precip: bool = False,
                     ) -> dict[str, list[list[float | None]]]:
    """峰值小时的高/中/低云网格。date=None 走预报端点,否则走历史存档。

    with_precip=True 时额外拉取降水层(spec §2 heatgrid 需要)。
    """
    layers = LAYERS + ("precip",) if with_precip else LAYERS
    chunks = [pts[i:i + _CHUNK] for i in range(0, len(pts), _CHUNK)]

    def _one(chunk):
        params = {
            "latitude": ",".join(str(p[0]) for p in chunk),
            "longitude": ",".join(str(p[1]) for p in chunk),
            "timezone": tz, "models": model,
            "hourly": "cloud_cover_high,cloud_cover_mid,cloud_cover_low"
                      + (",precipitation" if with_precip else ""),
        }
        if date is None:
            url = FORECAST_URL
            params["forecast_days"] = 3
        else:
            url = HISTORICAL_FORECAST_URL
            params.update(start_date=date, end_date=date)
        data = _get_retry(client, url, params).json()
        out = {k: [] for k in layers}
        for loc in (data if isinstance(data, list) else [data]):
            hourly = loc["hourly"]
            idx = next((j for j, t in enumerate(hourly["time"]) if t == iso_hour), None)
            for layer in LAYERS:
                col = hourly.get(f"cloud_cover_{layer}")
                out[layer].append(col[idx] if idx is not None and col else None)
            if with_precip:
                col = hourly.get("precipitation")
                out["precip"].append(col[idx] if idx is not None and col else None)
        return out

    # 并行拉各 chunk(全国~11 段,串行会几十秒);httpx.Client 线程安全,
    # ex.map 保序;任一 chunk 抛 HTTPError 会向上冒泡由调用方转 503
    values: dict[str, list] = {k: [] for k in layers}
    with ThreadPoolExecutor(max_workers=_MAX_PARALLEL) as ex:
        for res in ex.map(_one, chunks):
            for layer in layers:
                values[layer].extend(res[layer])
    return {layer: [values[layer][r * n_cols:(r + 1) * n_cols]
                    for r in range(n_rows)] for layer in layers}


def fetch_aod_grid(client: httpx.Client, bbox: tuple, n_rows: int, n_cols: int,
                   tz: str, iso_hour: str, coarse_step: float = 2.0,
                   ) -> list[list[float | None]] | None:
    """峰值小时 AOD 网格,插值放大到 n_rows×n_cols。

    AOD 是平滑场,按 coarse_step(默认 2°≈220km)粗采样一次请求即可,再双线性
    放大到细网格——避免 0.5° 逐格拉空气质量 API(慢)。整体失败 → None(中性)。
    """
    # 粗采样点数须 ≤ 单请求上限;不够粗就自动加大步长
    while len(grid_points(bbox, coarse_step)) > _CHUNK:
        coarse_step += 1.0
    cpts = grid_points(bbox, coarse_step)
    ccols = len({lon for _, lon in cpts})
    crows = len(cpts) // ccols
    try:
        data = _get_retry(client, AIR_QUALITY_URL, params={
            "latitude": ",".join(str(p[0]) for p in cpts),
            "longitude": ",".join(str(p[1]) for p in cpts),
            "timezone": tz, "hourly": "aerosol_optical_depth"}).json()
    except httpx.HTTPError:
        return None
    vals = []
    for loc in (data if isinstance(data, list) else [data]):
        hourly = loc.get("hourly", {})
        col = hourly.get("aerosol_optical_depth")
        idx = next((j for j, t in enumerate(hourly.get("time", []))
                    if t == iso_hour), None)
        vals.append(col[idx] if idx is not None and col else None)
    arr = np.array([[v if v is not None else np.nan for v in
                     vals[r * ccols:(r + 1) * ccols]] for r in range(crows)],
                   dtype=float)
    if np.all(np.isnan(arr)):
        return None
    arr[np.isnan(arr)] = np.nanmean(arr)          # 缺格用均值补,便于插值
    fine = np.asarray(Image.fromarray(arr).resize((n_cols, n_rows), Image.BILINEAR))
    return fine.tolist()


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
