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


BRAND = "afterglow · 霞客"   # 产品正式命名(用户 2026-07-10 拍板)


def draw_watermark(img, text: str = BRAND, *, alpha: int = 84,
                   angle: float = 30.0, step_x: int = 158, step_y: int = 82):
    """密集斜排半透明品牌水印(用户 2026-07-10:渲染图必须带)。

    独立 RGBA 层平铺→整层旋转→合成:密度靠 step 网格(隔行错位半格)。
    双色描边(浅衬+深字)保证在莫兰迪中间调色块上也可辨,又不遮数据。
    返回 RGB 图。
    """
    from PIL import Image

    base = img.convert("RGBA")
    w, h = base.size
    # 旋转后仍要盖满:先铺一个对角线尺寸的大层
    diag = int((w * w + h * h) ** 0.5) + step_x
    layer = Image.new("RGBA", (diag, diag), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    f = cjk_font(18)
    row = 0
    for y in range(0, diag, step_y):
        x0 = -(step_x // 2) if row % 2 else 0
        for x in range(x0, diag, step_x):
            d.text((x + 1, y + 1), text, fill=(255, 255, 255, alpha - 30), font=f)
            d.text((x, y), text, fill=(110, 58, 63, alpha), font=f)   # 品牌深酒红
        row += 1
    layer = layer.rotate(angle, expand=False)
    ox, oy = (diag - w) // 2, (diag - h) // 2
    layer = layer.crop((ox, oy, ox + w, oy + h))
    return Image.alpha_composite(base, layer).convert("RGB")


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
