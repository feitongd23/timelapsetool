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
