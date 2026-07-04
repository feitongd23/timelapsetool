# src/skyfire/himawari_hsd.py
"""Himawari HSD 历史/准实时归档(AWS 公开桶,spec 5.4 数据源升级)。

NICT 瓦片服务无多年归档且 INFRARED_FULL 已 404(2026-07 实测);
AWS noaa-himawari8/9 桶存全盘 L1b,10 分钟一槽,按纬度横切 10 段。
北京裁剪框整框落在段 2 → 每帧只下 1 段(B13 约 2.8MB / B03 约 22MB)。
"""
import bz2
import math
from datetime import datetime, timezone
from pathlib import Path

import httpx

# GEOS 投影常数(CGMS;单位 km,SAT_H 为地心距)
R_EQ, R_POL, SAT_H = 6378.137, 6356.7523, 42164.0
SUB_LON = 140.7
Y_MAX = 5_500_000.0 / 35_785_863.0   # 全盘半幅扫描角(rad)
N_SEGMENTS = 10
H9_START = datetime(2022, 12, 13, tzinfo=timezone.utc)  # H9 接替 H8 运行

BAND_RES = {"B03": "R05", "B13": "R20"}   # 可见光 0.5km / 红外 2km
# 北京学习框:西含 400km 通道走廊,整框位于段 2(见 Plan D Task 1 数学)
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
