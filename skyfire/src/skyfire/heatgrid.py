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
# 受光带扫描距离:高云画布必须在此范围内有西(日照方向)缘才被点亮
# (2026-07-10 用户实锤:整片铺到天边的100%高云幕内部无光,烧不了;
# 文献 channel-length-by-canvas-height:高云画布须查到500-829km)
_LIT_KM = (300, 450, 600, 800)
_LIT_FACTOR = {300: 1.0, 450: 1.0, 600: 0.6, 800: 0.35, None: 0.2}

_SCALE = 48                       # 13x9 格 → 624x432 px
# 莫兰迪色系(与 heatmap_map._BANDS 同族;用户 2026-07-10)
_STOPS = {
    "prob": [(243, 240, 234), (226, 213, 192), (203, 169, 135),
             (178, 124, 101), (143, 74, 68)],
    "quality": [(240, 238, 242), (214, 205, 220), (180, 155, 178),
                (141, 96, 111), (110, 58, 63)],
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
            canvas_cloud = min(100.0, (h or 0) + 0.5 * (m or 0))
            pr, qu = baseline_percent(score, confidence, None, canvas_cloud)
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


def _corridor_points(low, mid, precip, bbox, lon, lat, azimuth_deg: float):
    """从网格自身低/中云/降水场,沿真实太阳方位角采样透光通道点。

    2026-07-10 修正(与判读图 270° 硬编码同族的病):七月北京日落方位
    ≈300°(西北),正西采样把每格通道都查偏 30°;中云墙同步纳入
    (7/9:只采低云时中云墙隐形);光路降雨带同步纳入(用户实锤:
    呼市-吕梁-西安雨带横在济青一线光路上,该线应为 0)。
    """
    rad = math.radians(azimuth_deg)
    pts = []
    for dkm in _CORRIDOR_KM:
        slat = lat + dkm * math.cos(rad) / 111.0
        slon = lon + dkm * math.sin(rad) / (111.0 * max(0.2, math.cos(math.radians(lat))))
        cl = _sample_grid(low, bbox, slon, slat)
        cm = _sample_grid(mid, bbox, slon, slat) if mid else None
        pr = _sample_grid(precip, bbox, slon, slat) if precip else None
        if cl is not None:
            pts.append(ChannelPoint(dist_km=dkm, cloud_low=cl,
                                    cloud_total=None, cloud_mid=cm,
                                    precip=pr))
    return pts


def lit_factor(high, mid, bbox, lon, lat, azimuth_deg: float) -> float:
    """高云画布受光系数:沿太阳方位扫 300-800km,找云盖(高或中≥85%)的边缘。

    画布被点燃的光来自其日照侧边缘底下——边缘越近越亮,800km 内无边=内部
    无光(×0.2)。越界(扫出网格)按有边处理,不惩罚地图西边界。
    """
    rad = math.radians(azimuth_deg)
    for dkm in _LIT_KM:
        slat = lat + dkm * math.cos(rad) / 111.0
        slon = lon + dkm * math.sin(rad) / (111.0 * max(0.2, math.cos(math.radians(lat))))
        h = _sample_grid(high, bbox, slon, slat)
        if h is None:
            return _LIT_FACTOR[dkm]          # 扫出网格:按此处即有边处理
        m = _sample_grid(mid, bbox, slon, slat) if mid else 0
        if max(h or 0, m or 0) < 85:
            return _LIT_FACTOR[dkm]          # 找到边缘:据边距定亮度
    return _LIT_FACTOR[None]


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
                channel=_corridor_points(low, mid, precip, bbox,
                                         lon, lat, az))).score
            # 受光带:本格处于≥85%连续云盖之下时,画布必须在日照方向
            # 300-800km 内有边缘才被点亮(2026-07-10 上海100%高云幕质量64的
            # 反面教材——满盖是画布,但只有靠近西缘的画布会亮)
            if (h or 0) >= 85 or ((h or 0) + (mid[r][c] or 0)) >= 95:
                score *= lit_factor(high, mid, bbox, lon, lat, az)
            # 甜区耦合只认画布云(高+半中):低云不是画布是遮挡——
            # 2026-07-10 青岛实锤:高10中0低22 被凑成"总云32"拿甜区+15
            canvas_cloud = min(100.0, (h or 0) + 0.5 * (mid[r][c] or 0))
            prob[r][c], quality[r][c] = baseline_percent(score, confidence,
                                                         None, canvas_cloud)
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
    from skyfire.overlay import draw_watermark
    img = draw_watermark(img)   # afterglow·霞客 品牌水印
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
