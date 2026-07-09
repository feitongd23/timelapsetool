"""全国概率/质量地图的后台预生成(用户 2026-07-08 定的架构:不实时算,
跟随 GFS/EC/ICON 模式更新一天几次,渲染好存盘;API 直取,用户零等待)。

一次刷新 = 某城市 × 若干天 × 朝/晚 × 概率/质量,拉全国网格→全物理打分→渲染 PNG。
"""
from pathlib import Path

import httpx

from skyfire.config import City
from skyfire.gridmap import (CHINA_BBOX, CHINA_STEP, fetch_aod_grid,
                             fetch_cloud_grid, grid_points)
from skyfire.heatgrid import score_grids_physics
from skyfire.heatmap_map import render_map_png
from skyfire.suntimes import nearest_iso_hour, sun_window

DEFAULT_MAPS_DIR = Path(__file__).parent.parent.parent / "data" / "maps"
EVENTS = ("sunrise_glow", "sunset_glow")
KINDS = ("prob", "quality")


def map_path(out_dir, city_key: str, date: str, event: str, kind: str,
             model: str | None = None) -> Path:
    """model=ec|gfs 为 GRIB 直采双模式图(2026-07-09 拍板);None 为旧版合成图。"""
    tail = f"_{model}" if model else ""
    return Path(out_dir) / f"{city_key}_{date}_{event}_{kind}{tail}.png"


def refresh_maps(client: httpx.Client, city: City, city_key: str, days,
                 out_dir=DEFAULT_MAPS_DIR, confidence: str = "medium") -> list[Path]:
    """预生成 city × days × 朝晚 × 概率/质量 的全国地图,存盘。返回写出的文件。

    单个 (day,event) 拉取失败(HTTPError,如限流)→ 跳过该组,不中断其余。
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    pts = grid_points(CHINA_BBOX, CHINA_STEP)
    n_cols = len({lon for _, lon in pts})
    n_rows = len(pts) // n_cols
    written: list[Path] = []
    for day in days:
        for event in EVENTS:
            win = sun_window(city.lat, city.lon, city.timezone, day, event)
            iso = nearest_iso_hour(win.peak)
            try:
                cloud = fetch_cloud_grid(client, pts, n_rows, n_cols,
                                         city.timezone, iso, with_precip=True)
                aod = fetch_aod_grid(client, CHINA_BBOX, n_rows, n_cols,
                                     city.timezone, iso, coarse_step=4.0)
            except httpx.HTTPError:
                continue
            grids = score_grids_physics(cloud, aod, event, CHINA_BBOX, confidence)
            for kind in KINDS:
                png = render_map_png(grids[kind], kind, CHINA_BBOX,
                                     marker=(city.name, city.lat, city.lon))
                p = map_path(out_dir, city_key, str(day), event, kind)
                p.write_bytes(png)
                written.append(p)
    return written
