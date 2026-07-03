from pathlib import Path

from skyfire.config import load_cities

CONFIG = Path(__file__).parent.parent / "config" / "cities.yaml"


def test_load_beijing():
    cities = load_cities(CONFIG)
    bj = cities["beijing"]
    assert bj.name == "北京"
    assert abs(bj.lat - 39.9042) < 0.01
    assert bj.timezone == "Asia/Shanghai"


def test_beijing_spots():
    bj = load_cities(CONFIG)["beijing"]
    names = [s.name for s in bj.spots]
    assert "雾灵山" in names
    wuling = next(s for s in bj.spots if s.name == "雾灵山")
    assert wuling.elevation_m > 2000
