# src/skyfire/geolines.py
"""海岸线/省界底图(knowledge §5 地理参照:定位北京与云洞相对位置)。

打包的 assets/geolines.geojson(Natural Earth 裁北京周边)→ 用 pyresample
area 投影到裁剪图上画线;投影越界的点抛 ValueError,断线不崩。
"""
import json
from pathlib import Path

from PIL import ImageDraw

_ASSET = Path(__file__).parent / "assets" / "geolines.geojson"
_COLOR = {"coast": (0, 235, 120), "province": (255, 190, 70)}
_WIDTH = {"coast": 2, "province": 1}


def load_geolines(path: Path = _ASSET) -> list[dict]:
    """加载打包的海岸线/省界要素。"""
    return json.loads(Path(path).read_text(encoding="utf-8"))["features"]


def _project(area, lon: float, lat: float, sx: float, sy: float):
    try:
        col, row = area.get_array_indices_from_lonlat(lon, lat)
    except ValueError:
        return None
    if 0 <= col < area.width and 0 <= row < area.height:
        return (col * sx, row * sy)
    return None


def draw_geolines(img, area, sx: float, sy: float, *, features=None):
    """把海岸线/省界矢量投到 RGB 图上。越界点断线(尽力,不崩)。"""
    d = ImageDraw.Draw(img)
    for f in (features if features is not None else load_geolines()):
        kind = f["properties"].get("kind", "province")
        color, width = _COLOR.get(kind, _COLOR["province"]), _WIDTH.get(kind, 1)
        pts: list[tuple[float, float]] = []
        for lon, lat in f["geometry"]["coordinates"]:
            p = _project(area, lon, lat, sx, sy)
            if p is not None:
                pts.append(p)
            else:
                if len(pts) >= 2:
                    d.line(pts, fill=color, width=width)
                pts = []
        if len(pts) >= 2:
            d.line(pts, fill=color, width=width)
    return img
