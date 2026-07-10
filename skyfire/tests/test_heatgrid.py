from skyfire.heatgrid import render_heatmap_png, score_grids


def _cloud(v_high, v_mid, v_low, precip=0.0, rows=3, cols=3):
    mk = lambda v: [[v] * cols for _ in range(rows)]
    return {"high": mk(v_high), "mid": mk(v_mid), "low": mk(v_low),
            "precip": mk(precip)}


def test_score_grids_sweet_spot_beats_overcast():
    sweet = score_grids(_cloud(50, 10, 5), "high")
    overcast = score_grids(_cloud(100, 80, 60), "high")
    assert sweet["prob"][0][0] > overcast["prob"][0][0]
    assert sweet["quality"][0][0] > overcast["quality"][0][0]
    assert 0 <= sweet["prob"][0][0] <= 100


def test_score_grids_none_cell_scores_zero():
    cloud = _cloud(50, 10, 5)
    cloud["high"][1][1] = None
    g = score_grids(cloud, "medium")
    assert g["prob"][1][1] == 0 and g["quality"][1][1] == 0


def test_render_heatmap_png_smooth_bytes():
    values = [[10, 40, 80], [20, 60, 90], [10, 30, 50]]
    png = render_heatmap_png(values, "prob", marker_rc=(1.2, 1.5))
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    from io import BytesIO
    from PIL import Image
    img = Image.open(BytesIO(png))
    assert img.size == (144, 144) and img.mode == "RGB"
    # 平滑性抽查:紧贴瓦片边界(col0/col1 交界 x=48)两侧像素不应出现
    # 瓦片式硬跳变(双三次插值后应为渐变,而非阶跃)
    a, b = img.getpixel((47, 72)), img.getpixel((49, 72))
    assert max(abs(a[i] - b[i]) for i in range(3)) < 40


def test_render_heatmap_png_quality_uses_purple():
    values = [[90] * 3] * 3
    png_q = render_heatmap_png(values, "quality", marker_rc=None)
    png_p = render_heatmap_png(values, "prob", marker_rc=None)
    assert png_q != png_p


def test_lit_factor_uniform_deck_interior_dark():
    """受光带(2026-07-10 用户实锤):整片100%高云幕内部无光,西缘才亮。

    合成场:东半 100% 高云、西半晴。晚霞方位270°:幕内靠西缘的格子系数高,
    深处格子(边缘>800km)×0.2;晴区格子不受影响。
    """
    from skyfire.heatgrid import lit_factor, score_grids_physics
    bbox = (100.0, 17.0, 135.0, 45.0)
    rows, cols = 29, 36
    # 列 0-17(经度100-117)晴,列 18+(117.5-135)满盖高云
    high = [[100.0 if c >= 18 else 0.0 for c in range(cols)] for r in range(rows)]
    zeros = [[0.0] * cols for _ in range(rows)]
    lat = 31.0
    # 幕内贴近西缘(117.9E,距边≈40km):300km 采样已出幕 → 1.0
    assert lit_factor(high, zeros, bbox, 117.9, lat, 270.0) == 1.0
    # 幕深处(130E,西缘距离≈1150km):800km 内无边 → 0.2
    assert lit_factor(high, zeros, bbox, 130.0, lat, 270.0) == 0.2
    # 全链:同一片幕,西缘格质量应显著高于深处格
    cloud = {"high": high, "mid": zeros, "low": zeros, "precip": zeros}
    grids = score_grids_physics(cloud, None, "sunset_glow", bbox, "medium")
    r_mid = 14
    c_edge = 19   # 幕内近西缘
    c_deep = 33   # 幕深处
    assert grids["quality"][r_mid][c_edge] > grids["quality"][r_mid][c_deep] * 2
    assert grids["quality"][r_mid][c_deep] <= 25
