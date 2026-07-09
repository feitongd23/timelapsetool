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


# gray 是 render.bt_to_gray 的线性刻度:gray = (310-BT)/130*255
_BT_MAX, _BT_SPAN = 310.0, 130.0


def gray_to_bt(gray_val: float) -> float:
    return _BT_MAX - gray_val / 255.0 * _BT_SPAN


def clear_bt_floor(month: int) -> float | None:
    """晴地表最暖像元的下限(K):窗内最暖像元低于它=无一真晴像元=满盖。

    2026-07-09 0分复盘实锤:满盖暖顶中云(窗内最暖仅294K、BT均值265K)被
    线性刻度读成34%,恰落30-70甜区反拿奖励。北京晴地表傍晚:夏≥300K,
    春秋≥290K;冬季雪面/冻土本身<275K,此法失效返回 None(靠其他因子)。
    """
    if month in (5, 6, 7, 8, 9):
        return 292.0
    if month in (3, 4, 10):
        return 283.0
    return None


def box_stats(gray: np.ndarray, center: tuple[int, int], half: int = 30,
              month: int | None = None) -> dict | None:
    """窗内实况统计:线性云量代理 + 满盖判定(红外暖顶陷阱的强制检查)。

    返回 {"pct","max_bt","mean_bt","overcast"};窗越界返回 None。
    overcast=True 表示窗内无一晴像元——此时 pct 语义已失真,调用方必须
    按 ≥90 满盖处理,禁止把 pct 当云量喂进打分(2026-06-26 教训的代码化)。
    """
    cx, cy = center
    x0, x1 = max(cx - half, 0), min(cx + half, gray.shape[1])
    y0, y1 = max(cy - half, 0), min(cy + half, gray.shape[0])
    if x0 >= x1 or y0 >= y1:
        return None
    box = gray[y0:y1, x0:x1].astype(float)
    pct = float(box.mean() / 255.0 * 100.0)
    max_bt = gray_to_bt(float(box.min()))    # gray 越小越暖
    mean_bt = gray_to_bt(float(box.mean()))
    overcast = False
    if month is not None:
        floor = clear_bt_floor(month)
        overcast = floor is not None and max_bt < floor
    # lid=满盖且暖顶(均温>252K=中低云盖子,规则 cloud-midlow-full-cover-is-lid);
    # 满盖但极冷(卷云幕)是画布不是盖子——冷幕若也强制按 92 闷盖处理,
    # 就会经卫星路径重演 7/7 的"高云满盖被当阴天"(规则 cloud-high-canvas-never-zero)
    lid = overcast and mean_bt > 252.0
    return {"pct": round(pct, 1), "max_bt": round(max_bt, 1),
            "mean_bt": round(mean_bt, 1), "overcast": overcast, "lid": lid}


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
