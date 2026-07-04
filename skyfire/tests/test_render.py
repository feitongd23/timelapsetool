import numpy as np

from skyfire.render import bt_to_gray, refl_to_gray


def test_bt_to_gray_cold_is_white():
    bt = np.array([[180.0, 310.0], [245.0, np.nan]])
    g = bt_to_gray(bt)
    assert g.dtype == np.uint8
    assert g[0, 0] == 255          # 极冷云顶 → 白
    assert g[0, 1] == 0            # 暖地表 → 黑
    assert 100 <= g[1, 0] <= 155   # 中间温度 → 中灰
    assert g[1, 1] == 0            # NaN(缺测/盘外)→ 黑


def test_bt_to_gray_clips_outside_range():
    g = bt_to_gray(np.array([[150.0, 340.0]]))
    assert g[0, 0] == 255 and g[0, 1] == 0


def test_refl_to_gray_sqrt_stretch():
    r = np.array([[0.0, 25.0, 100.0, np.nan]])
    g = refl_to_gray(r)
    assert g.dtype == np.uint8
    assert g[0, 0] == 0
    assert g[0, 2] == 255
    assert abs(int(g[0, 1]) - 127) <= 2   # sqrt(0.25)=0.5 → ~127
    assert g[0, 3] == 0
