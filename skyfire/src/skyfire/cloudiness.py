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
              month: int | None = None, clear_ref_k: float | None = None,
              raining: bool = False) -> dict | None:
    """窗内实况统计:线性云量代理 + 满盖判定(红外暖顶陷阱的强制检查)。

    返回 {"pct","max_bt","mean_bt","overcast","lid","floor"};窗越界返回 None。
    overcast=True 表示窗内无一晴像元——此时 pct 语义已失真;lid=True 时调用方
    必须按 ≥90 满盖处理,禁止把 pct 当云量喂进打分(2026-06-26 教训的代码化)。

    晴空地板优先用动态参照 clear_ref_k(模式 2 米气温 K)−6K:固定季节常数
    "从不全局成立"(GOES-R/JMA ATBD 口径)——292K 连 7/9(最暖 294.4K)和
    7/10(293.2K,用户目视全阴)都拦不住;−6K 由两案例标定(需 <6.8K)。
    动态参照仅在 ≥278K(无雪面风险)时启用,否则退回季节常数。
    lid 判定:满盖且(暖顶均温>252K 或 正在/刚降水)——冷顶满盖默认是卷云幕
    画布(护 7/7),但降水中的冷顶雨云盖同样是盖子(7/10 用户目视纠正)。
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
    if clear_ref_k is not None and clear_ref_k >= 278.0:
        floor = clear_ref_k - 6.0
    else:
        floor = clear_bt_floor(month) if month is not None else None
    overcast = floor is not None and max_bt < floor
    lid = overcast and (mean_bt > 252.0 or raining)
    return {"pct": round(pct, 1), "max_bt": round(max_bt, 1),
            "mean_bt": round(mean_bt, 1), "overcast": overcast, "lid": lid,
            "floor": None if floor is None else round(floor, 1)}


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
