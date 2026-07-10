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


def test_box_stats_dynamic_floor_catches_real_misses():
    """动态晴空地板回归:7/9(最暖294.4K)与7/10(293.2K)都被292K常数漏掉,
    动态地板=T2m−6K 两案例必须都拦住(用户两次目视全阴实锤)。"""
    from skyfire.cloudiness import box_stats
    # 7/9 型:满盖暖顶,最暖 294.4K;当时 T2m≈31°C=304.2K → 地板 298.2
    g294 = int(round((310 - 294.4) / 130 * 255))
    img = np.full((200, 200), g294, dtype=np.uint8)
    s = box_stats(img, (100, 100), half=40, month=7, clear_ref_k=304.2)
    assert s["overcast"] is True and s["floor"] == 298.2
    # 292K 固定常数确实拦不住(记录旧漏洞)
    s_old = box_stats(img, (100, 100), half=40, month=7)
    assert s_old["overcast"] is False


def test_box_stats_cold_rain_deck_is_lid_when_raining():
    """冷顶雨云盖(7/10:均温248K,刚下完大雨全阴):
    降水中 → lid=True;无降水 → 冷幕按卷云画布豁免(护7/7)。"""
    from skyfire.cloudiness import box_stats
    g248 = int(round((310 - 248) / 130 * 255))
    img = np.full((200, 200), g248, dtype=np.uint8)
    wet = box_stats(img, (100, 100), half=40, month=7,
                    clear_ref_k=300.0, raining=True)
    dry = box_stats(img, (100, 100), half=40, month=7,
                    clear_ref_k=300.0, raining=False)
    assert wet["overcast"] and wet["lid"] is True
    assert dry["overcast"] and dry["lid"] is False


def test_box_stats_dynamic_floor_snow_guard():
    """动态参照 <278K(雪面风险)时退回季节常数,不误判晴雪地为满盖。"""
    from skyfire.cloudiness import box_stats
    g260 = int(round((310 - 260) / 130 * 255))
    img = np.full((200, 200), g260, dtype=np.uint8)
    s = box_stats(img, (100, 100), half=40, month=1, clear_ref_k=270.0)
    assert s["overcast"] is False   # 冬季常数=None → 检测停用
