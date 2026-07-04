# src/skyfire/himawari_hsd.py
"""Himawari HSD 历史/准实时归档(AWS 公开桶,spec 5.4 数据源升级)。

NICT 瓦片服务无多年归档且 INFRARED_FULL 已 404(2026-07 实测);
AWS noaa-himawari8/9 桶存全盘 L1b,10 分钟一槽,按纬度横切 10 段。
北京裁剪框整框落在段 2 → 每帧只下 1 段(B13 约 2.8MB / B03 约 22MB)。
"""
import bz2
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

from skyfire.render import render_annotated

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
    """覆盖纬度带的 HSD 段号(1-10,自北向南)。margin 抵消投影近似误差。

    margin=0.008 经验值:覆盖 CGMS 椭球正算与实际段网格的对齐误差
    (北京框 v∈[0.11,0.19] 距段界 ≥0.01,0.008 不会误跨段)。
    """
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
    """在单个桶下齐所有段;任何段 404 → 返回 None(让上层换桶)。

    仅 404 视为"该桶无档";其他非 200(5xx/403/429 等)抛 HTTPStatusError,
    不静默换桶(与 himawari.py/openmeteo.py 的 raise_for_status 惯例一致)。
    """
    sat = sat_code(bucket)
    out: list[Path] = []
    for seg in segments:
        key = hsd_key(ts, band, seg, sat=sat)
        dat = cache_dir / Path(key).name.removesuffix(".bz2")
        if not dat.exists():
            resp = client.get(S3_BASE.format(bucket=bucket, key=key))
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
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


IR_BURN_MIN = (0, 10, 20, 30)   # 燃烧时刻窗:晚霞日落后 / 朝霞日出前
VIS_DAY_MIN = (20, 40)          # 晚霞:日落前 20/40min(白天读云型)
VIS_DAY_MIN_SUNRISE = (60, 90)  # 朝霞:日出后更晚,太阳升高才够亮读厚度
_BAND_OF = {"ir": "B13", "vis": "B03"}


def round_down_10min(ts: datetime) -> datetime:
    return ts.replace(minute=ts.minute - ts.minute % 10, second=0, microsecond=0)


def case_frame_times(peak_utc: datetime, event: str) -> list[tuple[datetime, str]]:
    """按天象把取图时刻分到日落/日出正确一侧(knowledge §1)。

    晚霞:红外取日落后(燃烧),可见光取日落前(日光);朝霞相反。
    返回 [(ts, "ir"|"vis")],均对齐 10 分钟槽。
    """
    sunset = event == "sunset_glow"
    ir_sign = 1 if sunset else -1
    out = [(round_down_10min(peak_utc + timedelta(minutes=ir_sign * m)), "ir")
           for m in IR_BURN_MIN]
    vis_offsets = VIS_DAY_MIN if sunset else VIS_DAY_MIN_SUNRISE
    out += [(round_down_10min(peak_utc + timedelta(minutes=-ir_sign * m)), "vis")
            for m in vis_offsets]
    return out


def latest_slot(client: httpx.Client, now: datetime,
                max_back: int = 6) -> datetime | None:
    """最近一个有 B13 数据的 10 分钟槽(AWS 落档延迟数分钟,向前回扫)。

    以 HEAD 试探段文件是否存在(命中后由 download_segments 复用/下载)。
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


def observer_cloudiness(client, peak_utc: datetime, event: str, lat: float,
                        lon: float, bbox: tuple = CROP_BBOX,
                        hsd_cache: Path | None = None) -> float | None:
    """燃烧时刻卫星实测:观测点上空云量(各红外帧 box_cloudiness 均值)。

    预报云量不可信(实证),此为可信的实际云量来源。全缺→None。
    """
    from statistics import mean
    from skyfire.render import load_b13_region
    from skyfire.cloudiness import box_cloudiness
    cache = Path(hsd_cache) if hsd_cache else Path("data/frames/hsd_cache")
    segs = segments_for(bbox[1], bbox[3], (bbox[0] + bbox[2]) / 2)
    vals = []
    for ts, ch in case_frame_times(peak_utc, event):
        if ch != "ir":
            continue
        dats = download_segments(client, ts, "B13", segs, cache)
        if not dats:
            continue
        f = load_b13_region(dats, bbox, lat, lon)
        vals.append(box_cloudiness(f.gray, f.center_px, half=40))
    return round(mean(vals), 1) if vals else None


def fetch_case_frames(client, peak_utc: datetime, frames_dir: Path, *,
                      prefix: str, event: str, lat: float, lon: float,
                      azimuth_deg: float, bbox: tuple = CROP_BBOX,
                      hsd_cache: Path | None = None,
                      ) -> list[tuple[datetime, str, Path]]:
    """一个案例的学习帧序列:下载 HSD 段 → 渲染带地理标注的 PNG。

    返回 [(ts, "ir"|"vis", png_path)];单帧缺档跳过不失败(尽力语义)。
    lat/lon/azimuth_deg 用于叠加北京点标与太阳方位角通道线。
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
