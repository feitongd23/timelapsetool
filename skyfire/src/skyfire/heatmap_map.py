"""sunsetbot 风格概率/质量地图:真实地理底图(海岸线+省界+城市)+ 分级填色
+ 图例色阶条 + 经纬网格(用户 2026-07-08 参照 sunsetbot 定的样式)。

纯 PIL 等经纬线性投影(热力图本就是规则经纬网格,无需 pyresample/cartopy)。
低值留白(不烧的地方不上色)是 sunsetbot 观感"干净"的关键。
"""
from io import BytesIO

import numpy as np
from PIL import Image, ImageDraw
from scipy.ndimage import gaussian_filter

from skyfire.geolines import load_geolines
from skyfire.overlay import cjk_font

# 空间平滑半径(格)。原始逐小时云量场在 50km 尺度是椒盐噪声(相邻格跳变~32),
# 加甜区打分的硬拐点会碎成散点+甜甜圈;对分数场高斯平滑,把"单格精确值"噪声
# 还原成"这一带成不成片"的区域信号(用户 2026-07-08 指出细碎问题)。纯可视化,
# 不影响北京点预测(那条路用本地实际云量,与本地图网格无关)。
_SMOOTH_SIGMA = 0.8

# 全国主要城市(经纬度),落在渲染框内的会被标注(全国图用)
_CITIES = [
    ("北京", 39.90, 116.41), ("天津", 39.13, 117.20), ("上海", 31.23, 121.47),
    ("广州", 23.13, 113.26), ("深圳", 22.54, 114.06), ("成都", 30.57, 104.07),
    ("重庆", 29.56, 106.55), ("西安", 34.34, 108.94), ("武汉", 30.59, 114.31),
    ("南京", 32.06, 118.80), ("杭州", 30.27, 120.15), ("沈阳", 41.80, 123.43),
    ("哈尔滨", 45.80, 126.53), ("郑州", 34.75, 113.62), ("济南", 36.67, 117.00),
    ("长沙", 28.23, 112.94), ("南昌", 28.68, 115.86), ("福州", 26.07, 119.30),
    ("昆明", 25.04, 102.71), ("贵阳", 26.65, 106.63), ("南宁", 22.82, 108.37),
    ("太原", 37.87, 112.55), ("石家庄", 38.04, 114.51), ("呼和浩特", 40.84, 111.75),
    ("兰州", 36.06, 103.83), ("银川", 38.49, 106.23), ("西宁", 36.62, 101.78),
    ("合肥", 31.82, 117.23), ("海口", 20.04, 110.32), ("大连", 38.91, 121.61),
    ("青岛", 36.07, 120.38), ("厦门", 24.48, 118.09),
]

# 分级色带(0-100)。<10 留白=不烧;越高越浓。低值透明是 sunsetbot 干净感的来源。
_BANDS = {
    "prob": [  # 概率:暖色(米→琥珀→橙→红)
        (10, 25, (250, 233, 207)), (25, 40, (250, 199, 117)),
        (40, 55, (239, 159, 39)), (55, 70, (224, 122, 46)),
        (70, 85, (214, 83, 58)), (85, 101, (192, 57, 43))],
    "quality": [  # 质量/鲜艳度:紫→品红→红(仿 sunsetbot 鲜艳度色阶)
        (10, 25, (222, 219, 245)), (25, 40, (201, 194, 238)),
        (40, 55, (183, 159, 214)), (55, 70, (199, 123, 176)),
        (70, 85, (214, 90, 122)), (85, 101, (192, 57, 43))],
}
_LEVELS = [10, 25, 40, 55, 70, 85, 100]   # 图例刻度

_WATER = (214, 232, 244)
_COAST = (120, 170, 210)
_PROVINCE = (150, 158, 168)
_GRID = (210, 214, 220)
_AXIS = (110, 120, 132)
_CITY_DOT = (232, 120, 60)
_CITY_TXT = (40, 50, 62)
_MARKER = (225, 55, 55)

_TARGET_PX = 880     # 地图长边目标像素;PPD 按框大小自适应(全国框自动缩小)
_PAD_L, _PAD_B, _PAD_T, _PAD_R = 46, 34, 10, 12   # 画布四周边距(留给轴/图例)
_LEGEND_H = 56


def _ppd(bbox):
    """按 bbox 反推每纬度像素,使地图长边≈_TARGET_PX(小框细、大框适配)。"""
    span_lat = bbox[3] - bbox[1]
    span_lon_eq = (bbox[2] - bbox[0]) * _cos_lat(bbox)
    return _TARGET_PX / max(span_lat, span_lon_eq)


def _cos_lat(bbox):
    lat0, lat1 = bbox[1], bbox[3]
    return float(np.cos(np.radians((lat0 + lat1) / 2)))


def _project(lon, lat, bbox, mw, mh):
    lon0, lat0, lon1, lat1 = bbox
    x = (lon - lon0) / (lon1 - lon0) * mw
    y = (lat1 - lat) / (lat1 - lat0) * mh
    return x, y


def _fill_bands(values, kind, mw, mh):
    """数值网格 → 分级填色 RGB(白底,低值留白),双三次放大到地图尺寸。

    先对分数场做高斯平滑,去掉逐格噪声,得到连续的区域favorability(见 _SMOOTH_SIGMA)。
    """
    arr = np.clip(np.asarray(values, dtype=np.float32), 0, 100)
    arr = gaussian_filter(arr, sigma=_SMOOTH_SIGMA, mode="nearest")
    small = Image.fromarray(arr.astype(np.uint8), mode="L")
    v = np.asarray(small.resize((mw, mh), Image.BICUBIC), dtype=np.float32)
    rgb = np.full((mh, mw, 3), 255, dtype=np.uint8)
    for lo, hi, color in _BANDS[kind]:
        rgb[(v >= lo) & (v < hi)] = color
    return Image.fromarray(rgb, mode="RGB")


def _draw_geolines(draw, bbox, mw, mh):
    for f in load_geolines():
        kind = f["properties"].get("kind", "province")
        color = _COAST if kind == "coast" else _PROVINCE
        width = 2 if kind == "coast" else 1
        pts = [_project(lon, lat, bbox, mw, mh)
               for lon, lat in f["geometry"]["coordinates"]]
        # 只连相邻都在图内(含少量越界余量)的点,避免跨图长直线
        for a, b in zip(pts, pts[1:]):
            if all(-40 <= p[0] <= mw + 40 and -40 <= p[1] <= mh + 40
                   for p in (a, b)):
                draw.line([a, b], fill=color, width=width)


def _grid_step(bbox):
    return 5 if (bbox[2] - bbox[0]) > 20 else 2   # 全国框稀疏网格,华北框密


def _draw_grid(draw, bbox, mw, mh, font):
    lon0, lat0, lon1, lat1 = bbox
    step = _grid_step(bbox)
    for lon in range(int(np.ceil(lon0)), int(lon1) + 1, step):
        x, _ = _project(lon, lat0, bbox, mw, mh)
        for y in range(0, mh, 10):
            draw.line([(x, y), (x, y + 5)], fill=_GRID, width=1)
    for lat in range(int(np.ceil(lat0)), int(lat1) + 1, step):
        _, y = _project(lon0, lat, bbox, mw, mh)
        for x in range(0, mw, 10):
            draw.line([(x, y), (x + 5, y)], fill=_GRID, width=1)


def _draw_cities(draw, bbox, mw, mh, font, marker):
    lon0, lat0, lon1, lat1 = bbox
    for name, lat, lon in _CITIES:
        if not (lon0 <= lon <= lon1 and lat0 <= lat <= lat1):
            continue
        x, y = _project(lon, lat, bbox, mw, mh)
        is_home = marker and name == marker[0]
        r = 4 if is_home else 3
        dot = _MARKER if is_home else _CITY_DOT
        draw.ellipse([x - r, y - r, x + r, y + r], fill=dot,
                     outline=(255, 255, 255), width=1)
        draw.text((x + 6, y - 8), name,
                  fill=_MARKER if is_home else _CITY_TXT, font=font)


def render_map_png(values, kind: str, bbox, *,
                   marker=("北京", 39.9042, 116.4074)) -> bytes:
    """概率/质量数值网格 → sunsetbot 风格地图 PNG bytes。

    kind: 'prob' | 'quality'。bbox=(lon0,lat0,lon1,lat1)。
    """
    ppd = _ppd(bbox)
    mh = round((bbox[3] - bbox[1]) * ppd)
    mw = round((bbox[2] - bbox[0]) * ppd * _cos_lat(bbox))
    W = _PAD_L + mw + _PAD_R
    H = _PAD_T + mh + _PAD_B + _LEGEND_H

    canvas = Image.new("RGB", (W, H), (255, 255, 255))
    # 海域底色:整图先铺水色,再贴陆地填色图(陆地=白底+分级色)
    map_img = _fill_bands(values, kind, mw, mh)
    d = ImageDraw.Draw(map_img)
    _draw_geolines(d, bbox, mw, mh)
    fsmall = cjk_font(13)
    _draw_grid(d, bbox, mw, mh, fsmall)
    _draw_cities(d, bbox, mw, mh, fsmall, marker)
    # 地图边框
    d.rectangle([0, 0, mw - 1, mh - 1], outline=_AXIS, width=1)
    canvas.paste(map_img, (_PAD_L, _PAD_T))

    dc = ImageDraw.Draw(canvas)
    lon0, lat0, lon1, lat1 = bbox
    step = _grid_step(bbox)
    for lon in range(int(np.ceil(lon0)), int(lon1) + 1, step):
        x, _ = _project(lon, lat0, bbox, mw, mh)
        dc.text((_PAD_L + x - 8, _PAD_T + mh + 6), str(lon), fill=_AXIS, font=fsmall)
    for lat in range(int(np.ceil(lat0)), int(lat1) + 1, step):
        _, y = _project(lon0, lat, bbox, mw, mh)
        dc.text((6, _PAD_T + y - 8), str(lat), fill=_AXIS, font=fsmall)

    _draw_legend(dc, kind, _PAD_L, H - _LEGEND_H + 14, mw, fsmall)
    buf = BytesIO()
    canvas.save(buf, format="PNG")
    return buf.getvalue()


def _draw_legend(draw, kind, x0, y0, width, font):
    """底部图例色阶条:分级色块 + 刻度数值(0-100)。"""
    bands = _BANDS[kind]
    n = len(bands) + 1                       # +1 是留白档(<10)
    seg = min(46, (width - 40) // n)
    x = x0
    # 首档=留白(白块带边框)
    draw.rectangle([x, y0, x + seg, y0 + 16], fill=(255, 255, 255),
                   outline=(190, 195, 200), width=1)
    draw.text((x - 2, y0 + 20), "0", fill=_AXIS, font=font)
    x += seg
    for i, (lo, hi, color) in enumerate(bands):
        draw.rectangle([x, y0, x + seg, y0 + 16], fill=color,
                       outline=(190, 195, 200), width=1)
        draw.text((x - 4, y0 + 20), str(_LEVELS[i]), fill=_AXIS, font=font)
        x += seg
    label = "概率 %" if kind == "prob" else "鲜艳度(质量)%"
    draw.text((x + 8, y0 + 2), label, fill=_CITY_TXT, font=font)
