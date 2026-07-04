"""云区移动估计与外推(spec 5.4)。

estimate_shift:FFT 相位相关求两帧整体位移(dy, dx),curr ≈ roll(prev, (dy, dx))。
extrapolated_corridor:半拉格朗日回溯——窗口时刻将位于走廊上空的气块,
当前位于下风向上游 shift*frames 处;把采样点反向平移后在当前帧上采样。
"""
import numpy as np

from skyfire.cloudiness import box_cloudiness, corridor_centers


def estimate_shift(prev: np.ndarray, curr: np.ndarray) -> tuple[int, int]:
    fa = np.fft.fft2(curr.astype(np.float64))
    fb = np.fft.fft2(prev.astype(np.float64))
    cross = fa * np.conj(fb)
    cross /= np.abs(cross) + 1e-12
    corr = np.abs(np.fft.ifft2(cross))
    peak = np.unravel_index(int(np.argmax(corr)), corr.shape)
    shifts = []
    for p, size in zip(peak, corr.shape):
        shifts.append(p - size if p > size // 2 else p)
    return shifts[0], shifts[1]  # (dy, dx)


def extrapolated_corridor(gray: np.ndarray, origin: tuple[int, int], azimuth_deg: float,
                          step_px: int, n: int, shift_per_frame: tuple[int, int],
                          frames_ahead: int, half: int = 30) -> list[float]:
    dy, dx = shift_per_frame
    offset_x = -dx * frames_ahead
    offset_y = -dy * frames_ahead
    centers = corridor_centers(origin, azimuth_deg, step_px, n)
    return [box_cloudiness(gray, (cx + offset_x, cy + offset_y), half)
            for cx, cy in centers]
