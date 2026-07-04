"""HSD 波段 → 学习用灰度 PNG。

判读口径(knowledge §5):红外 BT 越冷越白(高云亮、低云暗灰);
可见光反射率 sqrt 拉伸看纹理。NaN(盘外/缺测)→ 黑。
"""
import numpy as np

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
