import numpy as np

from skyfire.drift import estimate_shift, extrapolated_corridor


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
