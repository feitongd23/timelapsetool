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
