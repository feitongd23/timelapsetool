import numpy as np

from skyfire.cloudiness import box_cloudiness, corridor_centers, corridor_cloudiness


def test_box_cloudiness_bright_is_cloudy():
    img = np.zeros((400, 400), dtype=np.uint8)
    img[100:200, 100:200] = 255  # 一块亮云
    assert box_cloudiness(img, (150, 150), half=40) > 90
    assert box_cloudiness(img, (300, 300), half=40) < 5


def test_box_cloudiness_clips_at_edges():
    img = np.full((100, 100), 128, dtype=np.uint8)
    v = box_cloudiness(img, (0, 0), half=30)  # 超出边界不抛异常
    assert 45 <= v <= 55


def test_corridor_centers_direction():
    # 方位角 270°(正西):x 递减,y 不变
    pts = corridor_centers((500, 500), azimuth_deg=270, step_px=50, n=4)
    assert len(pts) == 4
    assert pts[0] == (450, 500) and pts[3] == (300, 500)
    # 方位角 0°(正北):y 递减(图像上方为北)
    pts_n = corridor_centers((500, 500), azimuth_deg=0, step_px=50, n=2)
    assert pts_n[0] == (500, 450)


def test_corridor_cloudiness_averages_boxes():
    img = np.zeros((600, 1200), dtype=np.uint8)
    img[:, 0:600] = 255  # 西半边全云
    vals = corridor_cloudiness(img, (760, 300), azimuth_deg=270, step_px=100, n=4, half=30)
    assert len(vals) == 4
    assert vals[0] < 10          # (660,300) 仍在暗区(分界 x=600 以东,框不跨界)
    assert vals[-1] > 90         # (360,300) 深入亮区


def test_box_stats_overcast_detection_summer():
    """满盖暖顶陷阱(2026-07-09 0分实锤):窗内无晴像元 → overcast=True。

    gray=(310-BT)/130*255:BT 265K 满盖中云 → gray≈88(线性读数仅~35%)。
    """
    from skyfire.cloudiness import box_stats
    bt265 = int(round((310 - 265) / 130 * 255))       # ≈88
    img = np.full((200, 200), bt265, dtype=np.uint8)
    s = box_stats(img, (100, 100), half=40, month=7)
    assert s["overcast"] is True
    assert 30 <= s["pct"] <= 40                        # 线性读数确实在"甜区"
    assert abs(s["max_bt"] - 265) < 2


def test_box_stats_clear_pixels_not_overcast():
    from skyfire.cloudiness import box_stats
    bt265 = int(round((310 - 265) / 130 * 255))
    img = np.full((200, 200), bt265, dtype=np.uint8)
    img[95:105, 95:105] = 10                           # 一小片 ~305K 真晴地表
    s = box_stats(img, (100, 100), half=40, month=7)
    assert s["overcast"] is False


def test_box_stats_winter_disabled():
    """冬季雪面/冻土地表本身 <275K,满盖判定失效 → 不误判。"""
    from skyfire.cloudiness import box_stats, clear_bt_floor
    assert clear_bt_floor(1) is None
    bt265 = int(round((310 - 265) / 130 * 255))
    img = np.full((200, 200), bt265, dtype=np.uint8)
    s = box_stats(img, (100, 100), half=40, month=1)
    assert s["overcast"] is False
