"""热力图:网格逐格规则分 + 平滑(无分块无锯齿)PNG 渲染(spec §2 heatmap)。

概率图暖色(米→琥珀→红)、质量图紫色系;双三次插值放大,无瓦片边界。
"""
import math
from io import BytesIO

import numpy as np
from PIL import Image, ImageDraw

from skyfire.models import ChannelPoint
from skyfire.percent import baseline_percent
from skyfire.scoring.firecloud import FireCloudInputs, fire_cloud_score

_CORRIDOR_KM = (50, 100, 200, 300, 400)   # 通道采样距离(含近程点,与点预测一致)

_SCALE = 48                       # 13x9 格 → 624x432 px
_STOPS = {
    "prob": [(0xFA, 0xEE, 0xDA), (0xFA, 0xC7, 0x75), (0xEF, 0x9F, 0x27),
             (0xBA, 0x75, 0x17), (0xE2, 0x4B, 0x4A)],
    "quality": [(0xEE, 0xED, 0xFE), (0xCE, 0xCB, 0xF6), (0xAF, 0xA9, 0xEC),
                (0x7F, 0x77, 0xDD), (0x53, 0x4A, 0xB7)],
}


def score_grids(cloud: dict, confidence: str) -> dict[str, list[list[int]]]:
    """逐格 firecloud 规则分 → 概率%/质量% 两张数值网格。

    概率端经 baseline_percent(含格点云量甜区修正,cloud=该格总云近似
    high+mid+low 截断 100);channel/aod 无格点数据,置中性。缺数据格记 0。
    """
    rows, cols = len(cloud["high"]), len(cloud["high"][0])
    prob = [[0] * cols for _ in range(rows)]
    quality = [[0] * cols for _ in range(rows)]
    for r in range(rows):
        for c in range(cols):
            h, m, low = cloud["high"][r][c], cloud["mid"][r][c], cloud["low"][r][c]
            if h is None:
                continue
            p = (cloud.get("precip") or [[0] * cols] * rows)[r][c] or 0
            score = fire_cloud_score(FireCloudInputs(
                cloud_high=h, cloud_mid=m or 0, cloud_low=low or 0,
                precipitation=p, aod=None, channel=[])).score
            total = min(100.0, (h or 0) + (m or 0) + (low or 0))
            pr, qu = baseline_percent(score, confidence, None, total)
            prob[r][c], quality[r][c] = pr, qu
    return {"prob": prob, "quality": quality}


def _sample_grid(grid, bbox, lon, lat):
    """网格最近格取值(越界返回 None)。grid 为行主序北→南、西→东。"""
    lon0, lat0, lon1, lat1 = bbox
    rows, cols = len(grid), len(grid[0])
    if not (lon0 <= lon <= lon1 and lat0 <= lat <= lat1):
        return None
    c = round((lon - lon0) / (lon1 - lon0) * (cols - 1))
    r = round((lat1 - lat) / (lat1 - lat0) * (rows - 1))
    return grid[r][c]


def _corridor_points(low, mid, bbox, lon, lat, azimuth_deg: float):
    """从网格自身低/中云场,沿真实太阳方位角采样透光通道点。

    2026-07-10 修正(与判读图 270° 硬编码同族的病):七月北京日落方位
    ≈300°(西北),正西采样把每格通道都查偏 30°;中云墙同步纳入
    (7/9:只采低云时中云墙隐形,规则 channel-judge-low-plus-thick-mid)。
    """
    rad = math.radians(azimuth_deg)
    pts = []
    for dkm in _CORRIDOR_KM:
        slat = lat + dkm * math.cos(rad) / 111.0
        slon = lon + dkm * math.sin(rad) / (111.0 * max(0.2, math.cos(math.radians(lat))))
        cl = _sample_grid(low, bbox, slon, slat)
        cm = _sample_grid(mid, bbox, slon, slat) if mid else None
        if cl is not None:
            pts.append(ChannelPoint(dist_km=dkm, cloud_low=cl,
                                    cloud_total=None, cloud_mid=cm))
    return pts


def score_grids_physics(cloud: dict, aod_grid, event: str, bbox,
                        confidence: str,
                        azimuth_by_row: list[float] | None = None,
                        ) -> dict[str, list[list[int]]]:
    """全物理逐格打分:画布(云高分层)× 透光通道 × 本地低云 × 气溶胶 × 降水。

    比 score_grids 多算:①每格沿真实太阳方位角(azimuth_by_row 逐行,缺则
    退化为正西/正东旧口径)从网格采样低/中云→通道系数(含中云墙);
    ②每格 AOD→气溶胶系数(aod_grid 缺则 0.85 保守)。用户 2026-07-08 综合考量
    + 2026-07-10 强制过全口径。
    """
    high, mid, low = cloud["high"], cloud["mid"], cloud["low"]
    precip = cloud.get("precip")
    lon0, lat0, lon1, lat1 = bbox
    rows, cols = len(high), len(high[0])
    default_az = 270.0 if event == "sunset_glow" else 90.0
    prob = [[0] * cols for _ in range(rows)]
    quality = [[0] * cols for _ in range(rows)]
    for r in range(rows):
        lat = lat1 - (lat1 - lat0) * r / (rows - 1)
        az = azimuth_by_row[r] if azimuth_by_row else default_az
        for c in range(cols):
            h = high[r][c]
            if h is None:
                continue
            lon = lon0 + (lon1 - lon0) * c / (cols - 1)
            p = (precip[r][c] if precip else 0) or 0
            aod = aod_grid[r][c] if aod_grid else None
            score = fire_cloud_score(FireCloudInputs(
                cloud_high=h, cloud_mid=mid[r][c] or 0, cloud_low=low[r][c] or 0,
                precipitation=p, aod=aod,
                channel=_corridor_points(low, mid, bbox, lon, lat, az))).score
            total = min(100.0, (h or 0) + (mid[r][c] or 0) + (low[r][c] or 0))
            prob[r][c], quality[r][c] = baseline_percent(score, confidence, None, total)
    return {"prob": prob, "quality": quality}


def render_heatmap_png(values: list[list[int]], kind: str,
                       marker_rc: tuple[float, float] | None) -> bytes:
    """数值网格(0-100)→ 平滑渐变 PNG bytes。

    双三次插值放大(无分块无锯齿,用户 2026-07-07 拍板)→ 色带 LUT 上色
    → 可选城市点标(双圈,marker_rc 为小数行列坐标)。
    """
    arr = np.asarray(values, dtype=np.float32)
    rows, cols = arr.shape
    small = Image.fromarray(np.clip(arr, 0, 100).astype(np.uint8), mode="L")
    big = small.resize((cols * _SCALE, rows * _SCALE), Image.BICUBIC)
    v = np.asarray(big, dtype=np.float32) / 100.0
    stops = np.asarray(_STOPS[kind], dtype=np.float32)
    pos = np.linspace(0.0, 1.0, len(stops))
    rgb = np.stack([np.interp(v, pos, stops[:, i]) for i in range(3)], axis=-1)
    img = Image.fromarray(rgb.astype(np.uint8), mode="RGB")
    if marker_rc is not None:
        d = ImageDraw.Draw(img)
        # 采样点 r 的中心在 (r+0.5)*_SCALE(resize 语义),不加 0.5 会偏西北半格
        y, x = (marker_rc[0] + 0.5) * _SCALE, (marker_rc[1] + 0.5) * _SCALE
        d.ellipse([x - 7, y - 7, x + 7, y + 7], outline=(28, 39, 51), width=3)
        d.ellipse([x - 2, y - 2, x + 2, y + 2], fill=(28, 39, 51))
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
