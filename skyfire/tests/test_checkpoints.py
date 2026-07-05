from datetime import datetime
from zoneinfo import ZoneInfo

from skyfire.checkpoints import due_checkpoint, gate_exceeded

TZ = ZoneInfo("Asia/Shanghai")


def _t(h, m, d=6):
    return datetime(2026, 7, d, h, m, tzinfo=TZ)


PEAK_SUNSET = _t(19, 40)            # 当日日落
PEAK_SUNRISE = _t(4, 50, d=7)       # 次日日出


def test_sunset_checkpoints():
    assert due_checkpoint(_t(11, 10), PEAK_SUNSET, "sunset_glow") == "c1"
    assert due_checkpoint(_t(13, 30), PEAK_SUNSET, "sunset_glow") is None
    assert due_checkpoint(_t(17, 40), PEAK_SUNSET, "sunset_glow") == "c2"   # peak-2h
    assert due_checkpoint(_t(19, 5), PEAK_SUNSET, "sunset_glow") == "c3"    # peak-35m
    assert due_checkpoint(_t(19, 30), PEAK_SUNSET, "sunset_glow") is None   # <20m
    assert due_checkpoint(_t(9, 0), PEAK_SUNSET, "sunset_glow") is None


def test_sunrise_c1_previous_evening():
    assert due_checkpoint(_t(20, 30, d=6), PEAK_SUNRISE, "sunrise_glow") == "c1"
    assert due_checkpoint(_t(19, 0, d=6), PEAK_SUNRISE, "sunrise_glow") is None
    assert due_checkpoint(_t(3, 0, d=7), PEAK_SUNRISE, "sunrise_glow") == "c2"
    assert due_checkpoint(_t(4, 10, d=7), PEAK_SUNRISE, "sunrise_glow") == "c3"


def test_gate_exceeded():
    assert gate_exceeded(60, 80)          # |Δ|=20 > 15
    assert not gate_exceeded(60, 70)
    assert not gate_exceeded(None, 70)    # 无历史 → 不门控(等检查点)
