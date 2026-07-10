"""云区移动估计与外推(spec 5.4)。

estimate_shift:FFT 相位相关求两帧整体位移(dy, dx),curr ≈ roll(prev, (dy, dx))。
2026-07-10 文献扩展后按业务标准正规化(规则 REVISE-phasecorr-subpixel-and-zero-shift /
nowcast-phasecorr-hann-window / nowcast-phasecorr-response-gate):
- 加 Hann 窗:DFT 周期延拓假设使图像边界产生虚假相关能量(Foroosh 2002 误差分析;
  OpenCV phaseCorrelate 流程第一步)。
- 亚像素:主峰 5×5 加权质心(OpenCV weightedCentroid 同法)。整像素 argmax 对
  位移<1px/帧必然返回 0——2026-07-09 压境云系被 10min 帧距+2km 像素量化成
  零位移,是"外推恒 34%"的根因②:是"测不出"不是"没移动"。
- response 峰质量:主峰 5×5 邻域能量占总能量比。多层云各向异动/原地生消/纹理弱
  都会碎峰,response 低=矢量不可信,禁止外推当"届时不变"。
extrapolated_corridor:半拉格朗日回溯——窗口时刻将位于走廊上空的气块,
当前位于下风向上游 shift*frames 处;把采样点反向平移后在当前帧上采样。
"""
import numpy as np

from skyfire.cloudiness import box_cloudiness, corridor_centers

# response 低于此值 → 矢量不可信(单峰归一化≈1,业务经验碎峰<0.1;待回测校准)
RESPONSE_FLOOR = 0.03


def _hann2d(shape: tuple[int, int]) -> np.ndarray:
    hy = np.hanning(shape[0])
    hx = np.hanning(shape[1])
    return np.outer(hy, hx)


def estimate_shift_quality(prev: np.ndarray, curr: np.ndarray
                           ) -> tuple[float, float, float]:
    """相位相关位移估计(亚像素)+ 峰质量。返回 (dy, dx, response)。"""
    win = _hann2d(prev.shape)
    fa = np.fft.fft2(curr.astype(np.float64) * win)
    fb = np.fft.fft2(prev.astype(np.float64) * win)
    cross = fa * np.conj(fb)
    cross /= np.abs(cross) + 1e-12
    corr = np.abs(np.fft.ifft2(cross))
    py, px = np.unravel_index(int(np.argmax(corr)), corr.shape)
    # 主峰 5×5 加权质心(循环边界取模)
    h, w = corr.shape
    ys = [(py + o) % h for o in range(-2, 3)]
    xs = [(px + o) % w for o in range(-2, 3)]
    patch = corr[np.ix_(ys, xs)]
    total = float(patch.sum())
    if total <= 0:
        return 0.0, 0.0, 0.0
    oy = float((patch.sum(axis=1) * np.arange(-2, 3)).sum() / total)
    ox = float((patch.sum(axis=0) * np.arange(-2, 3)).sum() / total)
    dy = py + oy
    dx = px + ox
    if dy > h / 2:
        dy -= h
    if dx > w / 2:
        dx -= w
    response = total / float(corr.sum() + 1e-12)
    return dy, dx, response


def estimate_shift(prev: np.ndarray, curr: np.ndarray) -> tuple[int, int]:
    """旧接口(整数位移),内部走正规化估计;新代码请用 estimate_shift_quality。"""
    dy, dx, _ = estimate_shift_quality(prev, curr)
    return round(dy), round(dx)


def extrapolated_corridor(gray: np.ndarray, origin: tuple[int, int], azimuth_deg: float,
                          step_px: int, n: int, shift_per_frame: tuple[int, int],
                          frames_ahead: int, half: int = 30) -> list[float]:
    dy, dx = shift_per_frame
    offset_x = -dx * frames_ahead
    offset_y = -dy * frames_ahead
    centers = corridor_centers(origin, azimuth_deg, step_px, n)
    return [box_cloudiness(gray, (cx + offset_x, cy + offset_y), half)
            for cx, cy in centers]


def projected_box_cloudiness(gray: np.ndarray, center: tuple[int, int],
                             shift_per_frame: tuple[float, float],
                             frames_ahead: int, half: int = 40) -> float:
    """燃烧时刻观测点上空云量外推:半拉格朗日回溯上游采样(同 corridor 思路)。"""
    dy, dx = shift_per_frame
    cx, cy = center
    return box_cloudiness(gray, (round(cx - dx * frames_ahead),
                                 round(cy - dy * frames_ahead)), half)
