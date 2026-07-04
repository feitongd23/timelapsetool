"""从红外灰度图提取云量代理(spec 5.4 实况量)。

红外通道里云顶冷→亮:亮度均值/255*100 作为云量百分比代理。
这是有意的粗代理(无法分高低云),用于实况校验与外推,阈值可回测调。
坐标约定:图像 x 向东、y 向下(北在上);方位角自北顺时针。
"""
import math

import numpy as np


def box_cloudiness(gray: np.ndarray, center: tuple[int, int], half: int = 30) -> float:
    cx, cy = center
    x0, x1 = max(cx - half, 0), min(cx + half, gray.shape[1])
    y0, y1 = max(cy - half, 0), min(cy + half, gray.shape[0])
    if x0 >= x1 or y0 >= y1:
        return 0.0
    return float(gray[y0:y1, x0:x1].mean() / 255.0 * 100.0)


def corridor_centers(origin: tuple[int, int], azimuth_deg: float,
                     step_px: int, n: int) -> list[tuple[int, int]]:
    """沿方位角方向的采样中心序列(第 1 个点在 1*step 处)。"""
    rad = math.radians(azimuth_deg)
    dx, dy = math.sin(rad), -math.cos(rad)
    return [(round(origin[0] + dx * step_px * k), round(origin[1] + dy * step_px * k))
            for k in range(1, n + 1)]


def corridor_cloudiness(gray: np.ndarray, origin: tuple[int, int], azimuth_deg: float,
                        step_px: int, n: int, half: int = 30) -> list[float]:
    return [box_cloudiness(gray, c, half) for c in corridor_centers(origin, azimuth_deg, step_px, n)]
