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
