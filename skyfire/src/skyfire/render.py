"""HSD 波段 → 学习用灰度 PNG。

判读口径(knowledge §5):红外 BT 越冷越白(高云亮、低云暗灰);
可见光反射率 sqrt 拉伸看纹理。NaN(盘外/缺测)→ 黑。
"""
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image

BT_MIN, BT_MAX = 180.0, 310.0   # K:平展到 0-255


def bt_to_gray(bt: np.ndarray) -> np.ndarray:
    """亮温(K)→ uint8 灰度,冷=白。"""
    g = (BT_MAX - bt) / (BT_MAX - BT_MIN)
    g = np.nan_to_num(np.clip(g, 0.0, 1.0), nan=0.0)
    return (g * 255).astype(np.uint8)


def refl_to_gray(refl: np.ndarray) -> np.ndarray:
    """反射率(%)→ uint8 灰度,sqrt 拉伸增强暗部纹理(晨昏可见光弱光)。"""
    g = np.sqrt(np.clip(refl, 0.0, 100.0) / 100.0)
    g = np.nan_to_num(g, nan=0.0)
    return (g * 255).astype(np.uint8)


_CALIBRATION = {"B13": "brightness_temperature", "B03": "reflectance"}
_TO_GRAY = {"B13": bt_to_gray, "B03": refl_to_gray}


def _scene_cls():
    """延迟导入 satpy(重依赖);测试中被 monkeypatch。"""
    from satpy import Scene
    return Scene


def _load_cropped(dat_paths: list[Path], band: str, bbox: tuple) -> "object":
    scn = _scene_cls()(reader="ahi_hsd", filenames=[str(p) for p in dat_paths])
    scn.load([band], calibration=_CALIBRATION[band])
    return scn.crop(ll_bbox=bbox)[band]


def render_band(dat_paths: list[Path], band: str, bbox: tuple,
                 out_png: Path, max_px: int = 1400) -> Path:
    """HSD 段 → 裁剪 bbox → 灰度 PNG(超宽则等比下采样)。"""
    data = _load_cropped(dat_paths, band, bbox)
    img = Image.fromarray(_TO_GRAY[band](data.values), mode="L")
    if max(img.size) > max_px:
        img.thumbnail((max_px, max_px))
    out_png = Path(out_png)
    out_png.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_png)
    return out_png


@dataclass
class HsdFrame:
    gray: "object"               # np.ndarray uint8,云顶越冷越亮
    center_px: tuple[int, int]   # 目标点 (x, y) 像素坐标
    km_px: float                 # 名义分辨率 km/px(B13=2.0)


def load_b13_region(dat_paths: list[Path], bbox: tuple,
                     lat: float, lon: float) -> HsdFrame:
    """nowcast 用:B13 裁剪数组 + 目标点像素坐标(接 cloudiness/drift)。"""
    data = _load_cropped(dat_paths, "B13", bbox)
    x, y = data.attrs["area"].get_xy_from_lonlat(lon, lat)
    return HsdFrame(gray=bt_to_gray(data.values), center_px=(int(x), int(y)),
                     km_px=2.0)
