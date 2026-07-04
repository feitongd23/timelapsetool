from PIL import Image

from skyfire.geolines import draw_geolines, load_geolines


class _FakeArea:
    width = 100
    height = 80

    def get_array_indices_from_lonlat(self, lon, lat):
        # 109..124 → col 0..100 ; 45..35 → row 0..80 ;区外抛 ValueError(仿真 pyresample)
        col = (lon - 109.0) / 15.0 * 100.0
        row = (45.0 - lat) / 10.0 * 80.0
        if not (0 <= col < 100 and 0 <= row < 80):
            raise ValueError("Point outside area")
        return int(col), int(row)


def test_load_geolines_bundled_asset():
    feats = load_geolines()
    assert len(feats) > 0
    kinds = {f["properties"]["kind"] for f in feats}
    assert kinds <= {"coast", "province"}
    assert all(f["geometry"]["type"] == "LineString" for f in feats)


def test_draw_geolines_draws_in_bounds_line_and_survives_out_of_bounds():
    img = Image.new("RGB", (100, 80), (0, 0, 0))
    before = img.tobytes()
    feats = [
        # 一条完全在框内的线(北京附近)→ 应画出
        {"properties": {"kind": "province"},
         "geometry": {"type": "LineString",
                      "coordinates": [[115.0, 40.0], [117.0, 40.0], [117.0, 39.0]]}},
        # 一条完全在框外的线 → 投影抛 ValueError,不能崩、不画
        {"properties": {"kind": "coast"},
         "geometry": {"type": "LineString",
                      "coordinates": [[200.0, 80.0], [201.0, 81.0]]}},
    ]
    out = draw_geolines(img, _FakeArea(), 1.0, 1.0, features=feats)
    assert out is img
    assert img.tobytes() != before          # 框内线画出来了


def test_draw_geolines_uses_bundled_features_by_default():
    # 不传 features 时用打包资源;北京框内应画出东西(不崩)
    img = Image.new("RGB", (100, 80), (0, 0, 0))
    before = img.tobytes()
    draw_geolines(img, _FakeArea(), 1.0, 1.0)
    assert img.tobytes() != before
