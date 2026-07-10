"""GRIB 直采双模式全国图管线(gribmaps):索引解析、湿度推云、轮次跟随。"""
import json
from datetime import datetime, timezone

import numpy as np
import pytest

from skyfire import gribmaps
from skyfire.config import City
from skyfire.maps import map_path

BJ = City(key="beijing", name="北京", lat=39.9042, lon=116.4074,
          timezone="Asia/Shanghai")

IDX_SAMPLE = """\
628:436000000:d=2026070818:TCDC:low cloud layer:12 hour fcst:
629:436100000:d=2026070818:LCDC:low cloud layer:12 hour fcst:
630:436282528:d=2026070818:MCDC:middle cloud layer:12 hour fcst:
631:436400000:d=2026070818:HCDC:high cloud layer:12 hour fcst:
632:436500000:d=2026070818:PRATE:surface:12 hour fcst:
"""


def test_parse_idx_selects_wanted_with_byte_ranges():
    wanted = {"LCDC:low cloud layer:12 hour fcst",
              "PRATE:surface:12 hour fcst"}
    segs = gribmaps.parse_idx(IDX_SAMPLE, wanted)
    assert [(k.split(":")[0], s, e) for k, s, e in segs] == [
        ("LCDC", 436100000, 436282527),
        ("PRATE", 436500000, None),     # 末条无下界 → 开区间
    ]


def test_parse_idx_key_disambiguates_tcdc_vs_lcdc():
    # 同名层不同变量(TCDC vs LCDC)靠变量名区分,不能只按层名匹配
    segs = gribmaps.parse_idx(IDX_SAMPLE, {"LCDC:low cloud layer:12 hour fcst"})
    assert len(segs) == 1 and segs[0][1] == 436100000


def test_rh_to_cloud_linear_ramp():
    rh = np.array([50.0, 90.0, 95.0, 100.0])
    out = gribmaps.rh_to_cloud(rh, 90.0)
    assert out.tolist() == [0.0, 0.0, 50.0, 100.0]


def test_burn_steps_quantized_and_bounded():
    # 北京 07-09 晚霞峰值约 11:45 UTC;00z 轮次 → GFS 整点 12,EC 3h 步长 12
    run = datetime(2026, 7, 9, 0, tzinfo=timezone.utc)
    day = datetime(2026, 7, 9).date()
    gfs = gribmaps._burn_steps(BJ, day, "sunset_glow", run, 1)
    ec = gribmaps._burn_steps(BJ, day, "sunset_glow", run, 3)
    assert gfs == 12 and ec == 12
    # 峰值早于轮次 → None(昨天的晚霞没法预测)
    past = datetime(2026, 7, 10, 0, tzinfo=timezone.utc)
    assert gribmaps._burn_steps(BJ, day, "sunset_glow", past, 1) is None


def test_map_path_model_suffix():
    from pathlib import Path
    legacy = map_path(Path("/x"), "beijing", "2026-07-09", "sunset_glow", "prob")
    ec = map_path(Path("/x"), "beijing", "2026-07-09", "sunset_glow", "prob", "ec")
    assert legacy.name == "beijing_2026-07-09_sunset_glow_prob.png"
    assert ec.name == "beijing_2026-07-09_sunset_glow_prob_ec.png"


@pytest.fixture
def fake_fields(monkeypatch):
    """打桩两模式取数与轮次探测:3×3 小网格,免网络。

    轮次取"今天 00z"(refresh 内部用真实 today 排步长,日期须相对而非写死)。
    """
    from datetime import date as date_type

    grid = {"high": np.full((3, 3), 80.0), "mid": np.full((3, 3), 10.0),
            "low": np.zeros((3, 3)), "precip": np.zeros((3, 3))}
    today = date_type.today()
    run = datetime(today.year, today.month, today.day, 0, tzinfo=timezone.utc)
    calls = {"gfs": 0, "ec": 0, "run": run}

    def fake_gfs(client, r, fh):
        calls["gfs"] += 1
        return dict(grid)

    def fake_ec(r, step):
        calls["ec"] += 1
        return dict(grid)

    monkeypatch.setattr(gribmaps, "latest_gfs_run", lambda c, now=None: run)
    monkeypatch.setattr(gribmaps, "_aod_grid_safe", lambda *a, **k: None)
    monkeypatch.setattr(gribmaps, "latest_ec_run", lambda: run)
    monkeypatch.setattr(gribmaps, "fetch_gfs_china", fake_gfs)
    monkeypatch.setattr(gribmaps, "fetch_ec_china", fake_ec)
    return calls


def test_refresh_writes_both_models_and_tracks_run(tmp_path, fake_fields):
    written = gribmaps.refresh_grib_maps(BJ, "beijing", tmp_path)
    # 每模式:2天×朝晚 中已过峰值的组被跳过,至少今晚+明天两天有图;×概率/质量
    assert set(written) == {"ec", "gfs"}
    assert all(n > 0 and n % 2 == 0 for n in written.values())
    pngs = sorted(p.name for p in tmp_path.glob("*.png"))
    assert any(n.endswith("_ec.png") for n in pngs)
    assert any(n.endswith("_gfs.png") for n in pngs)
    tag = fake_fields["run"].strftime("%Y%m%d%H")
    state = json.loads((tmp_path / "state.json").read_text())
    assert state == {"ec": tag, "gfs": tag}


def test_refresh_noop_when_run_unchanged(tmp_path, fake_fields):
    gribmaps.refresh_grib_maps(BJ, "beijing", tmp_path)
    n_before = dict(fake_fields)
    written = gribmaps.refresh_grib_maps(BJ, "beijing", tmp_path)
    # 无新轮次:返回 {model: 0}(区别于探测失败的缺席),且不再取数
    assert written == {"ec": 0, "gfs": 0}
    assert fake_fields == n_before


def test_refresh_probe_failure_reports_absent_model(tmp_path, fake_fields, monkeypatch):
    monkeypatch.setattr(gribmaps, "latest_ec_run", lambda: None)
    written = gribmaps.refresh_grib_maps(BJ, "beijing", tmp_path)
    assert "ec" not in written and written.get("gfs", 0) > 0
