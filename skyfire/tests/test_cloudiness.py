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
