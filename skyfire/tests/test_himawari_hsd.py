# tests/test_himawari_hsd.py
from datetime import datetime, timezone

from skyfire.himawari_hsd import (
    BAND_RES, CROP_BBOX, bucket_for, hsd_key, sat_code, segments_for, v_fraction,
)


def test_v_fraction_equator_center():
    assert abs(v_fraction(0.0, 140.7) - 0.5) < 0.002


def test_v_fraction_north_is_upper():
    assert v_fraction(40.0, 116.4) < v_fraction(36.0, 116.4) < 0.5


def test_beijing_crop_bbox_falls_in_segment_2():
    lon_min, lat_min, lon_max, lat_max = CROP_BBOX
    assert segments_for(lat_min, lat_max, (lon_min + lon_max) / 2) == [2]


def test_bucket_for_h9_h8_cutover():
    assert bucket_for(datetime(2023, 1, 1, tzinfo=timezone.utc)) == "noaa-himawari9"
    assert bucket_for(datetime(2021, 6, 18, tzinfo=timezone.utc)) == "noaa-himawari8"


def test_hsd_key_pattern():
    ts = datetime(2026, 5, 6, 10, 0, tzinfo=timezone.utc)
    key = hsd_key(ts, "B13", 2, sat="H09")
    assert key == ("AHI-L1b-FLDK/2026/05/06/1000/"
                   "HS_H09_20260506_1000_B13_FLDK_R20_S0210.DAT.bz2")
    assert BAND_RES["B03"] == "R05"
    assert sat_code("noaa-himawari8") == "H08"
