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
