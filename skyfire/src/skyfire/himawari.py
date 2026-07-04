"""Himawari-9 实况帧获取(NICT 公开瓦片服务,spec 5.4)。

投影用正射近似(星下点 140.7°E):对瓦片选择与区域裁剪足够精确
(中纬度中盘区域误差远小于一个瓦片);不用于精确逐像素定位。
"""
# 注意(2026-07):NICT INFRARED_FULL 产品已 404,红外一律走 himawari_hsd(AWS);
# 本模块仅 truecolor 快看与 latest.json 仍可用。
import io
import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import httpx
import numpy as np
from PIL import Image

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
