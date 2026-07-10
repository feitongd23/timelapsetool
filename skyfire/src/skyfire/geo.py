import math
from dataclasses import dataclass

EARTH_R_KM = 6371.0


@dataclass
class GeoPoint:
    lat: float
    lon: float
    dist_km: float


def destination(lat: float, lon: float, bearing_deg: float, distance_km: float) -> tuple[float, float]:
    """从 (lat, lon) 沿 bearing 方向走 distance_km 后的坐标(大圆)。"""
    phi1 = math.radians(lat)
    lam1 = math.radians(lon)
    theta = math.radians(bearing_deg)
    delta = distance_km / EARTH_R_KM
    phi2 = math.asin(
        math.sin(phi1) * math.cos(delta) + math.cos(phi1) * math.sin(delta) * math.cos(theta)
    )
    lam2 = lam1 + math.atan2(
        math.sin(theta) * math.sin(delta) * math.cos(phi1),
        math.cos(delta) - math.sin(phi1) * math.sin(phi2),
    )
    return math.degrees(phi2), math.degrees(lam2)


def channel_points(
    lat: float, lon: float, azimuth_deg: float,
    start_km: float = 25, end_km: float = 400, step_km: float = 25,
) -> list[GeoPoint]:
    """沿日落/日出方位角方向的光通道采样点。

    2026-07-11 F2:步长 50→25km(规则表口径),100km 缝隙曾让 80km 宽
    雨带整体隐形;16 点仍是一次逗号分隔请求,配额当量不变量级。
    """
    pts = []
    d = start_km
    while d <= end_km:
        plat, plon = destination(lat, lon, azimuth_deg, d)
        pts.append(GeoPoint(lat=plat, lon=plon, dist_km=d))
        d += step_km
    return pts
