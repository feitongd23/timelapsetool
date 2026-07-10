from PIL import Image

from skyfire.overlay import cjk_font, corridor_marks, draw_overlay, marker_xy


class _FakeArea:
    """经纬度→(col,row):col 随经度东增、row 随纬度北减(便于断言方向)。"""
    def get_array_indices_from_lonlat(self, lon, lat):
        return int(round((lon - 109.0) * 40)), int(round((45.0 - lat) * 40))


def test_marker_xy_maps_beijing():
    col, row = marker_xy(_FakeArea(), 39.9042, 116.4074)
    assert col == round((116.4074 - 109.0) * 40)
    assert row == round((45.0 - 39.9042) * 40)


def test_corridor_marks_go_west_for_sunset_azimuth():
    marks = corridor_marks(_FakeArea(), 39.9042, 116.4074, 292.6,
                           ranges_km=(100, 200, 300, 400, 500))
    assert [d for d, _, _ in marks] == [100, 200, 300, 400, 500]
    bx, _ = marker_xy(_FakeArea(), 39.9042, 116.4074)
    cols = [c for _, c, _ in marks]
    assert all(c < bx for c in cols)
    assert cols == sorted(cols, reverse=True)


def test_corridor_marks_go_east_for_sunrise_azimuth():
    marks = corridor_marks(_FakeArea(), 39.9042, 116.4074, 65.0,
                           ranges_km=(100, 300))
    bx, _ = marker_xy(_FakeArea(), 39.9042, 116.4074)
    assert all(c > bx for _, c, _ in marks)


def test_draw_overlay_changes_image_and_returns_it():
    img = Image.new("RGB", (600, 400), (0, 0, 0))
    before = img.tobytes()
    out = draw_overlay(img, _FakeArea(), 39.9042, 116.4074, 292.6, 1.0, 1.0,
                       ranges_km=(100, 200, 300))
    assert out is img and img.tobytes() != before


def test_cjk_font_loads():
    f = cjk_font(16)
    assert f is not None


def test_draw_watermark_covers_and_preserves():
    """品牌水印(afterglow·霞客):密铺全图、半透明不遮数据。"""
    import numpy as np
    from PIL import Image
    from skyfire.overlay import BRAND, draw_watermark
    assert "afterglow" in BRAND and "霞客" in BRAND
    img = Image.new("RGB", (900, 700), (240, 236, 228))
    out = draw_watermark(img)
    arr = np.asarray(out, dtype=int)
    diff = np.abs(arr - np.array([240, 236, 228])).sum(axis=-1)
    changed = (diff > 6).mean()
    # 密:水印像素覆盖率显著;淡:单像素改变有限(不遮数据)
    assert changed > 0.02, f"覆盖率过低 {changed:.3%}"
    assert diff.max() < 230, "水印过重会遮数据"
    # 四个象限都有水印(整图密铺,不是只盖中间)
    h, w = diff.shape
    for sl in ((slice(0, h//2), slice(0, w//2)), (slice(0, h//2), slice(w//2, w)),
               (slice(h//2, h), slice(0, w//2)), (slice(h//2, h), slice(w//2, w))):
        assert (diff[sl] > 6).mean() > 0.01
