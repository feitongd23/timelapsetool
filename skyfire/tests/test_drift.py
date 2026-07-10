import numpy as np

from skyfire.drift import (estimate_shift, extrapolated_corridor,
                           projected_box_cloudiness)


def _cloud_field(seed=7):
    rng = np.random.default_rng(seed)
    base = rng.random((256, 256))
    # 平滑成云块状,避免纯噪声
    from numpy.fft import fft2, ifft2, fftfreq
    fy = fftfreq(256)[:, None]
    fx = fftfreq(256)[None, :]
    lowpass = np.exp(-((fx ** 2 + fy ** 2) * 800))
    smooth = np.real(ifft2(fft2(base) * lowpass))
    smooth = (smooth - smooth.min()) / (smooth.max() - smooth.min())
    return (smooth * 255).astype(np.uint8)


def test_estimate_shift_recovers_known_roll():
    prev = _cloud_field()
    curr = np.roll(prev, (5, 12), axis=(0, 1))  # 向下 5、向右 12
    dy, dx = estimate_shift(prev, curr)
    assert (dy, dx) == (5, 12)


def test_estimate_shift_negative():
    prev = _cloud_field()
    curr = np.roll(prev, (-8, -3), axis=(0, 1))
    assert estimate_shift(prev, curr) == (-8, -3)


def test_extrapolated_corridor_backtracks_upstream():
    # 云整体向东移(dx>0):走廊未来的云 = 现在走廊西侧(上游)的云
    img = np.zeros((400, 400), dtype=np.uint8)
    img[:, 0:120] = 255  # 西侧亮云带
    # 走廊向西(方位 270°),当前走廊在 x=200..80 → 部分亮
    now = extrapolated_corridor(img, (280, 200), azimuth_deg=270, step_px=40, n=4,
                                shift_per_frame=(0, 0), frames_ahead=0)
    fut = extrapolated_corridor(img, (280, 200), azimuth_deg=270, step_px=40, n=4,
                                shift_per_frame=(0, 20), frames_ahead=6)  # 每帧东移 20px
    # 回溯采样点整体西移 120px → 更深入亮云带 → 预测云量高于当前
    assert sum(fut) > sum(now)


def test_projected_box_cloudiness_samples_upstream():
    gray = np.zeros((100, 100), dtype=np.uint8)
    gray[40:60, 10:30] = 255          # 云块在西边(上游)
    center = (50, 50)
    # 云每帧向东移 dx=+10:3 帧后云到 center → 回溯采样 (50-30, 50)=(20,50) 命中云块
    val = projected_box_cloudiness(gray, center, (0, 10), 3, half=8)
    assert val > 80
    # 不外推(0 帧)→ center 现在没云
    assert projected_box_cloudiness(gray, center, (0, 10), 0, half=8) < 10


def test_estimate_shift_quality_subpixel_and_response():
    """正规化位移估计(2026-07-10 文献扩展):亚像素+峰质量。

    整像素 argmax 对 <1px/帧位移必返回 0(7/9 压境云系被量化成零位移的根因);
    亚像素质心至少要能在 1-2px 真位移下给出接近真值、单峰 response 显著。
    """
    import numpy as np
    from skyfire.drift import RESPONSE_FLOOR, estimate_shift_quality
    rng = np.random.default_rng(7)
    base = (rng.random((120, 160)) * 255).astype(np.uint8)
    import scipy.ndimage as ndi
    curr = np.roll(np.roll(base, 2, axis=0), -3, axis=1)
    dy, dx, resp = estimate_shift_quality(base, curr)
    assert abs(dy - 2) < 0.5 and abs(dx + 3) < 0.5
    assert resp > RESPONSE_FLOOR

    # 纯噪声两帧(无相关结构)→ 峰质量应显著低于强单峰情形
    other = (rng.random((120, 160)) * 255).astype(np.uint8)
    _, _, resp_noise = estimate_shift_quality(base, other)
    assert resp_noise < resp
