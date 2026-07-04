# src/skyfire/overlay.py
"""云图地理标注(knowledge §2-A 通道方向性、§5 定位云洞)。

北京点标 + 太阳方位角通道线(晚霞朝西/朝霞朝东)+ 100–500km 距离环。
几何用 pyresample area 定位;纯几何函数独立可测,draw_overlay 只做绘制。
"""
from PIL import ImageDraw, ImageFont

from skyfire.geo import destination

_FONT_CANDIDATES = ("/System/Library/Fonts/STHeiti Medium.ttc",
                    "/System/Library/Fonts/Hiragino Sans GB.ttc")
_BEIJING = (255, 60, 60)
_CHANNEL = (80, 200, 255)


def cjk_font(size: int):
    """CJK 字体(标签用);找不到回退 PIL 默认。"""
    for path in _FONT_CANDIDATES:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


def marker_xy(area, lat: float, lon: float) -> tuple[int, int]:
    """经纬度 → 裁剪图内 (col, row) 像素索引。"""
    col, row = area.get_array_indices_from_lonlat(lon, lat)
    return int(col), int(row)


def corridor_marks(area, lat: float, lon: float, azimuth_deg: float,
                   ranges_km=(100, 200, 300, 400, 500)) -> list[tuple[int, int, int]]:
    """沿太阳方位角各距离处的 (dkm, col, row)。晚霞方位≈西→点在北京以西。"""
    out = []
    for dkm in ranges_km:
        plat, plon = destination(lat, lon, azimuth_deg, dkm)
        col, row = marker_xy(area, plat, plon)
        out.append((dkm, col, row))
    return out


def draw_overlay(img, area, lat: float, lon: float, azimuth_deg: float,
                 sx: float, sy: float, *,
                 ranges_km=(100, 200, 300, 400, 500), label: str = "北京"):
    """在 RGB 图上叠加北京十字+标签、通道线、距离环。sx/sy=输出/原生像素比。"""
    d = ImageDraw.Draw(img)
    f = cjk_font(16)
    bx, by = marker_xy(area, lat, lon)
    bx, by = bx * sx, by * sy
    marks = corridor_marks(area, lat, lon, azimuth_deg, ranges_km)
    if marks:
        fx, fy = marks[-1][1] * sx, marks[-1][2] * sy
        d.line([(bx, by), (fx, fy)], fill=_CHANNEL, width=2)
    for dkm, col, row in marks:
        x, y = col * sx, row * sy
        d.ellipse([x - 5, y - 5, x + 5, y + 5], outline=_CHANNEL, width=2)
        d.text((x + 6, y + 3), f"{dkm}km", fill=_CHANNEL, font=f)
    d.line([(bx - 14, by), (bx + 14, by)], fill=_BEIJING, width=3)
    d.line([(bx, by - 14), (bx, by + 14)], fill=_BEIJING, width=3)
    d.text((bx + 16, by - 20), label, fill=_BEIJING, font=f)
    return img
