from pathlib import Path
from types import SimpleNamespace

import numpy as np
from PIL import Image

import skyfire.render as render_mod
from skyfire.render import bt_to_gray, bt_to_rgb, refl_to_gray, load_b13_region, render_band


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


def test_bt_to_rgb_height_by_temperature():
    rgb = bt_to_rgb(np.array([[300.0, 253.0, 223.0], [205.0, np.nan, 268.0]]))
    assert rgb.dtype == np.uint8 and rgb.shape == (2, 3, 3)
    warm = rgb[0, 0]
    high = rgb[0, 2]
    coldest = rgb[1, 0]
    nan = rgb[1, 1]
    assert int(warm.max()) <= 40
    assert high[2] > high[0] and high[2] > 150
    assert coldest.min() > 200
    assert tuple(int(v) for v in nan) == (0, 0, 0)


class _FakeArea:
    width = 640
    height = 480

    def get_xy_from_lonlat(self, lon, lat):
        return 320, 240                     # (col, row)

    def get_array_indices_from_lonlat(self, lon, lat):
        return 320, 240                     # (col, row)


class _FakeScene:
    created = []

    def __init__(self, reader=None, filenames=None):
        _FakeScene.created.append({"reader": reader, "filenames": filenames})
        self._data = {}

    def load(self, names, calibration=None):
        import numpy as np
        for n in names:
            values = (np.full((480, 640), 220.0) if n == "B13"
                      else np.full((480, 640), 36.0))
            self._data[n] = SimpleNamespace(values=values,
                                            attrs={"area": _FakeArea()})

    def crop(self, ll_bbox=None):
        return self

    def __getitem__(self, name):
        return self._data[name]


def test_render_band_writes_png(tmp_path, monkeypatch):
    monkeypatch.setattr(render_mod, "_scene_cls", lambda: _FakeScene)
    out = tmp_path / "frame.png"
    render_band([Path("seg.DAT")], "B13", (109, 35, 124, 45), out, max_px=400)
    img = Image.open(out)
    assert img.mode == "L"
    assert max(img.size) <= 400            # 下采样生效
    assert _FakeScene.created[-1]["reader"] == "ahi_hsd"


def test_load_b13_region_returns_gray_and_center(tmp_path, monkeypatch):
    monkeypatch.setattr(render_mod, "_scene_cls", lambda: _FakeScene)
    frame = load_b13_region([Path("seg.DAT")], (109, 35, 124, 45), 39.9, 116.4)
    assert frame.gray.shape == (480, 640)
    assert frame.gray[0, 0] == render_mod.bt_to_gray(
        __import__("numpy").array([[220.0]]))[0, 0]
    assert frame.center_px == (320, 240)
    assert frame.km_px == 2.0


def test_render_annotated_ir_is_rgb_with_overlay(tmp_path, monkeypatch):
    import numpy as np
    from pathlib import Path
    from PIL import Image

    import skyfire.render as render_mod
    from skyfire.render import render_annotated

    monkeypatch.setattr(render_mod, "_scene_cls", lambda: _FakeScene)
    out = tmp_path / "f.png"
    render_annotated([Path("seg.DAT")], "B13", (109, 35, 124, 45), out,
                     lat=39.9, lon=116.4, azimuth_deg=292.6, max_px=400)
    img = Image.open(out)
    assert img.mode == "RGB"
    assert max(img.size) <= 400
    a = np.asarray(img).reshape(-1, 3)
    # 北京红标 → 存在明显偏红像素
    assert ((a[:, 0] > 150) & (a[:, 1] < 100) & (a[:, 2] < 100)).any()
