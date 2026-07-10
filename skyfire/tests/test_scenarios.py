"""判定方法情景矩阵回归(2026-07-11 对抗审计固化)。

14 情景中 8 个曾失败——所有"硬门槛"在地图路径上都不是真门槛:否决被
比例稀释、被 0.1 地板托底、再被甜区加法复活(用户"判断火烧云的方式
有问题"实锤)。本文件把关键情景钉死:动打分链前必须全绿。
坐标系:bbox=(100,17,135,45),行=北→南;晚霞方位取 300°(七月西北)。
"""
import numpy as np
import pytest

from skyfire.heatgrid import score_grids_physics

BBOX = (100.0, 17.0, 135.0, 45.0)
ROWS, COLS = 29, 36          # 1° 粗网格(采样语义与生产 0.25° 相同)
AZ = [300.0] * ROWS          # 真实七月晚霞方位
R, C = 14, 20                # 观测格:约 31N, 120E(留足西向采样空间)


def g(v: float) -> list:
    return [[float(v)] * COLS for _ in range(ROWS)]


def west_band(base: float, v: float, km_from: float, km_to: float) -> list:
    """在观测格西北方位 km_from-km_to 距离带内置值 v(近似:按经度差)。"""
    grid = g(base)
    import math
    lat = BBOX[3] - (BBOX[3] - BBOX[1]) * R / (ROWS - 1)
    for c in range(COLS):
        lon = BBOX[0] + (BBOX[2] - BBOX[0]) * c / (COLS - 1)
        for r in range(ROWS):
            la = BBOX[3] - (BBOX[3] - BBOX[1]) * r / (ROWS - 1)
            # 沿 300° 方位的投影距离
            dlon_km = (lon - (BBOX[0] + (BBOX[2] - BBOX[0]) * C / (COLS - 1))) \
                * 111 * math.cos(math.radians(lat))
            dlat_km = (la - lat) * 111
            proj = dlon_km * math.sin(math.radians(300)) \
                + dlat_km * math.cos(math.radians(300))
            if km_from <= proj <= km_to:
                grid[r][c] = float(v)
    return grid


def run(cloud, rain_soft=0.5):
    return score_grids_physics(cloud, None, "sunset_glow", BBOX, "medium",
                               azimuth_by_row=AZ, rain_soft=rain_soft)


def test_s01_west_rain_wall_kills():
    """①日落时西侧 100-300km 降雨墙 → ≈0(2026-07-10 济青假色带情景)。"""
    cloud = {"high": g(50), "mid": west_band(10, 90, 100, 300),
             "low": west_band(5, 70, 100, 300),
             "precip": west_band(0, 2.0, 100, 300)}
    r = run(cloud)
    assert r["prob"][R][C] <= 10 and r["quality"][R][C] <= 20


def test_s02_east_rain_band_harmless():
    """②雨带在东侧(背光侧)→ 西侧晴则正常有分(彩虹配置不误伤)。"""
    cloud = {"high": g(50), "mid": west_band(10, 90, -300, -100),
             "low": west_band(5, 70, -300, -100),
             "precip": west_band(0, 2.0, -300, -100)}
    r = run(cloud)
    assert r["prob"][R][C] >= 50


def test_s03_rain_tail_west_clear():
    """③雨尾西晴:头顶中高云幕+西侧全晴 → 高分(北京官方头号剧本)。"""
    cloud = {"high": west_band(5, 60, -50, 120), "mid": g(15),
             "low": g(10), "precip": g(0)}
    r = run(cloud)
    assert r["prob"][R][C] >= 45


def test_s04_deck_interior_dark():
    """④均匀 100% 高云幕深处(西缘>800km)→ ≤25。"""
    cloud = {"high": g(100), "mid": g(0), "low": g(0), "precip": g(0)}
    r = run(cloud)
    assert r["quality"][R][C] <= 25


def test_s05_deck_near_west_edge_bright():
    """⑤高云幕西缘 100km 内 → 高分(经典大烧配置;曾被>90封顶按在20,F6)。"""
    # 幕从观测格西 100km 处向东铺开(西侧 100km 外全晴)
    cloud = {"high": west_band(100, 0, 120, 900), "mid": g(0),
             "low": g(0), "precip": g(0)}
    r = run(cloud)
    assert r["prob"][R][C] >= 45 and r["quality"][R][C] >= 60


def test_s06_self_rain_veto():
    """⑥观测点自身 2mm/h 降雨 → ≈0(precip_factor 归零档)。"""
    cloud = {"high": g(60), "mid": g(30), "low": g(20), "precip": g(2.0)}
    r = run(cloud)
    assert r["prob"][R][C] <= 10 and r["quality"][R][C] <= 10


def test_s08_textbook_sweet_zone():
    """⑧40-60% 连贯高云+西晴+无雨 → 高分(防过杀的锚)。"""
    cloud = {"high": g(50), "mid": g(10), "low": g(5), "precip": g(0)}
    r = run(cloud)
    assert r["prob"][R][C] >= 70


def test_s09_low_blanket_zero():
    """⑨100% 低云盖顶 → ≈0。"""
    cloud = {"high": g(0), "mid": g(0), "low": g(100), "precip": g(0)}
    r = run(cloud)
    assert r["prob"][R][C] <= 10


def test_s10_local_low_shroud():
    """⑩高云 50% 但本地低云 80% → 地面看不到画布,≤20。"""
    cloud = {"high": g(50), "mid": g(0), "low": g(80), "precip": g(0)}
    r = run(cloud)
    assert r["prob"][R][C] <= 20


def test_s11_narrow_band_cannot_hide():
    """⑪80km 宽雨带藏在 130-210km → 25km 采样必命中(曾整体隐形拿96)。"""
    cloud = {"high": g(50), "mid": west_band(10, 90, 130, 210),
             "low": west_band(5, 75, 130, 210),
             "precip": west_band(0, 2.0, 130, 210)}
    r = run(cloud)
    assert r["prob"][R][C] <= 10


def test_s12_drizzle_ec_threshold():
    """⑫0.3mm/h 真雨横光路:EC 口径(3h平均稀释)按 0.15 判堵 → 压低。"""
    cloud = {"high": g(50), "mid": g(10), "low": g(5),
             "precip": west_band(0, 0.3, 100, 300)}
    r = run(cloud, rain_soft=0.15)
    assert r["prob"][R][C] <= 25   # 封顶0.1通道系数(未到1.0mm/h不归零)


def test_s13_all_blocked_stays_dead():
    """⑬通道全堵 → 甜区禁止复活(曾被加法抬回30)。"""
    cloud = {"high": g(50), "mid": west_band(10, 95, 25, 400),
             "low": west_band(5, 90, 25, 400), "precip": g(0)}
    r = run(cloud)
    assert r["prob"][R][C] <= 12


def test_s14_boundary_blind_discounted():
    """⑭图西边界走廊全越界 → 缺数据≠畅通,按 0.6 盲区折扣(曾恒 1.0)。"""
    cloud = {"high": g(50), "mid": g(10), "low": g(5), "precip": g(0)}
    r = run(cloud)
    inner = r["prob"][R][C]
    edge = r["prob"][R][1]     # 西边界内一格,走廊大半越界
    assert edge < inner        # 盲区必须比通道确认畅通的内陆低
