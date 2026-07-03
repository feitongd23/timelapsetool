# Skyfire 后端预测核心 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 火烧云/云海预测的后端核心:多模式预报采集 → 规则评分 + 置信度 → SQLite 经验库归档,以 CLI 形式出分和回测(北京验证)。

**Architecture:** 纯函数评分层(火烧云五因子/云海)与 IO 层(Open-Meteo 客户端、SQLite 存储)严格分离;CLI 只做编排。多模式(EC/GFS/ICON/CMA)各自打分后取共识,分歧宽度决定置信度。本计划不含卫星实况层、Claude 解读、HTTP 服务(分别是 Plan B/C)。

**Tech Stack:** Python 3.11+(系统 python3),httpx(HTTP,测试用 MockTransport 免额外依赖),astral(日出日落/方位角),PyYAML(配置),typer(CLI),sqlite3 标准库(无 ORM),pytest。

**Spec:** `docs/superpowers/specs/2026-07-03-skyfire-predictor-design.md`

## File Structure

```
skyfire/
├── pyproject.toml
├── config/cities.yaml          # 城市+云海机位配置(北京)
├── src/skyfire/
│   ├── __init__.py
│   ├── config.py               # 配置加载(City/Spot dataclass)
│   ├── suntimes.py             # 日出日落/晨昏蒙影/方位角(astral 封装)
│   ├── geo.py                  # 大圆目的地点计算 → 通道采样点
│   ├── models.py               # HourlyPoint/ModelForecast/ChannelPoint 数据类
│   ├── openmeteo.py            # Open-Meteo 多模式点预报 + 空气质量 + 通道批量查询
│   ├── scoring/
│   │   ├── __init__.py
│   │   ├── firecloud.py        # 火烧云五因子评分(纯函数)
│   │   └── cloudsea.py         # 云海评分(纯函数)
│   ├── consensus.py            # 多模式一致性 → 置信度
│   ├── store.py                # SQLite 经验库(建表/upsert/查询)
│   ├── backtest.py             # Spearman 相关性回测
│   └── cli.py                  # typer CLI: predict / cloudsea / backtest / init-db
└── tests/
    ├── test_config.py
    ├── test_suntimes.py
    ├── test_geo.py
    ├── test_openmeteo.py
    ├── test_firecloud.py
    ├── test_cloudsea.py
    ├── test_consensus.py
    ├── test_store.py
    └── test_backtest.py
```

---

### Task 1: 项目脚手架

**Files:**
- Create: `skyfire/pyproject.toml`
- Create: `skyfire/src/skyfire/__init__.py`
- Create: `skyfire/tests/test_smoke.py`
- Modify: `.gitignore`

- [ ] **Step 1: 写 pyproject 与包骨架**

`skyfire/pyproject.toml`:

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "skyfire"
version = "0.1.0"
description = "火烧云/云海预测助手 — 后端预测核心"
requires-python = ">=3.11"
dependencies = [
    "httpx>=0.27",
    "astral>=3.2",
    "PyYAML>=6.0",
    "typer>=0.12",
]

[project.optional-dependencies]
dev = ["pytest>=8.0"]

[project.scripts]
skyfire = "skyfire.cli:app"

[tool.hatch.build.targets.wheel]
packages = ["src/skyfire"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

`skyfire/src/skyfire/__init__.py`:

```python
__version__ = "0.1.0"
```

`skyfire/tests/test_smoke.py`:

```python
import skyfire


def test_package_importable():
    assert skyfire.__version__ == "0.1.0"
```

- [ ] **Step 2: 建 venv 并安装**

```bash
cd /Users/feitong/photo-app/skyfire
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
```

Expected: 安装成功,无报错。

- [ ] **Step 3: 跑冒烟测试**

Run: `cd /Users/feitong/photo-app/skyfire && .venv/bin/pytest tests/test_smoke.py -v`
Expected: PASS (1 passed)

- [ ] **Step 4: 更新 .gitignore 并提交**

在仓库根 `.gitignore` 末尾追加:

```
skyfire/.venv/
skyfire/**/__pycache__/
skyfire/*.db
skyfire/data/
```

```bash
cd /Users/feitong/photo-app
git add .gitignore skyfire/pyproject.toml skyfire/src skyfire/tests
git commit -m "feat(skyfire): 项目脚手架(pyproject + venv + pytest)"
```

---

### Task 2: 配置加载(城市与云海机位)

**Files:**
- Create: `skyfire/config/cities.yaml`
- Create: `skyfire/src/skyfire/config.py`
- Test: `skyfire/tests/test_config.py`

- [ ] **Step 1: 写失败测试**

`skyfire/tests/test_config.py`:

```python
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
```

- [ ] **Step 2: 运行确认失败**

Run: `cd /Users/feitong/photo-app/skyfire && .venv/bin/pytest tests/test_config.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'skyfire.config'`

- [ ] **Step 3: 写配置文件与实现**

`skyfire/config/cities.yaml`:

```yaml
cities:
  beijing:
    name: 北京
    lat: 39.9042
    lon: 116.4074
    timezone: Asia/Shanghai
    spots:
      - { name: 雾灵山, lat: 40.606, lon: 117.478, elevation_m: 2118 }
      - { name: 百花山, lat: 39.835, lon: 115.580, elevation_m: 1991 }
      - { name: 妙峰山, lat: 40.060, lon: 116.055, elevation_m: 1291 }
```

`skyfire/src/skyfire/config.py`:

```python
from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class Spot:
    name: str
    lat: float
    lon: float
    elevation_m: float


@dataclass
class City:
    key: str
    name: str
    lat: float
    lon: float
    timezone: str
    spots: list[Spot] = field(default_factory=list)


def load_cities(path: Path) -> dict[str, City]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    cities: dict[str, City] = {}
    for key, c in data["cities"].items():
        spots = [Spot(**s) for s in c.get("spots", [])]
        cities[key] = City(
            key=key, name=c["name"], lat=c["lat"], lon=c["lon"],
            timezone=c["timezone"], spots=spots,
        )
    return cities
```

- [ ] **Step 4: 运行确认通过**

Run: `cd /Users/feitong/photo-app/skyfire && .venv/bin/pytest tests/test_config.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: 提交**

```bash
cd /Users/feitong/photo-app
git add skyfire/config skyfire/src/skyfire/config.py skyfire/tests/test_config.py
git commit -m "feat(skyfire): 城市/云海机位配置加载(北京+三机位)"
```

---

### Task 3: 天文计算(日出日落/晨昏蒙影/方位角)

**Files:**
- Create: `skyfire/src/skyfire/suntimes.py`
- Test: `skyfire/tests/test_suntimes.py`

- [ ] **Step 1: 写失败测试**

`skyfire/tests/test_suntimes.py`(北京 2026-06-21 夏至,日落约 19:46、方位角约 302°,给宽容差):

```python
from datetime import date

from skyfire.suntimes import sun_window


def test_beijing_summer_sunset():
    w = sun_window(39.9042, 116.4074, "Asia/Shanghai", date(2026, 6, 21), "sunset_glow")
    assert w.event == "sunset_glow"
    assert 19 <= w.peak.hour <= 20
    assert 290 <= w.azimuth_deg <= 315
    # 民用晨昏蒙影结束晚于日落
    assert w.window_end > w.peak


def test_beijing_summer_sunrise():
    w = sun_window(39.9042, 116.4074, "Asia/Shanghai", date(2026, 6, 21), "sunrise_glow")
    assert 4 <= w.peak.hour <= 6
    assert 45 <= w.azimuth_deg <= 70
    assert w.window_start < w.peak
```

- [ ] **Step 2: 运行确认失败**

Run: `cd /Users/feitong/photo-app/skyfire && .venv/bin/pytest tests/test_suntimes.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'skyfire.suntimes'`

- [ ] **Step 3: 实现**

`skyfire/src/skyfire/suntimes.py`:

```python
from dataclasses import dataclass
from datetime import date, datetime
from zoneinfo import ZoneInfo

from astral import Observer
from astral.sun import azimuth, dawn, dusk, sunrise, sunset


@dataclass
class SunWindow:
    event: str            # "sunrise_glow" | "sunset_glow"
    peak: datetime        # 日出/日落时刻(本地时区)
    window_start: datetime
    window_end: datetime
    azimuth_deg: float    # peak 时刻太阳方位角(光通道方向)


def sun_window(lat: float, lon: float, tz: str, day: date, event: str) -> SunWindow:
    obs = Observer(latitude=lat, longitude=lon)
    tzinfo = ZoneInfo(tz)
    if event == "sunset_glow":
        peak = sunset(obs, day, tzinfo=tzinfo)
        start, end = peak.replace(minute=0), dusk(obs, day, tzinfo=tzinfo)
    elif event == "sunrise_glow":
        peak = sunrise(obs, day, tzinfo=tzinfo)
        start, end = dawn(obs, day, tzinfo=tzinfo), peak
    else:
        raise ValueError(f"unknown event: {event}")
    return SunWindow(
        event=event, peak=peak, window_start=start, window_end=end,
        azimuth_deg=azimuth(obs, peak),
    )
```

- [ ] **Step 4: 运行确认通过**

Run: `cd /Users/feitong/photo-app/skyfire && .venv/bin/pytest tests/test_suntimes.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: 提交**

```bash
cd /Users/feitong/photo-app
git add skyfire/src/skyfire/suntimes.py skyfire/tests/test_suntimes.py
git commit -m "feat(skyfire): 日出日落/晨昏蒙影/方位角计算"
```

---

### Task 4: 通道采样点几何

**Files:**
- Create: `skyfire/src/skyfire/geo.py`
- Test: `skyfire/tests/test_geo.py`

- [ ] **Step 1: 写失败测试**

`skyfire/tests/test_geo.py`:

```python
import math

from skyfire.geo import channel_points, destination


def test_destination_due_north_100km():
    lat, lon = destination(39.9, 116.4, bearing_deg=0, distance_km=100)
    assert abs(lat - (39.9 + 100 / 111.2)) < 0.05  # 北向 ~0.9°/100km
    assert abs(lon - 116.4) < 0.01


def test_channel_points_spacing_and_count():
    pts = channel_points(39.9, 116.4, azimuth_deg=302, start_km=50, end_km=400, step_km=50)
    assert len(pts) == 8  # 50,100,...,400
    assert pts[0].dist_km == 50 and pts[-1].dist_km == 400
    # 302° = 西北偏西,经度应递减、纬度递增
    assert pts[-1].lon < 116.4 and pts[-1].lat > 39.9
```

- [ ] **Step 2: 运行确认失败**

Run: `cd /Users/feitong/photo-app/skyfire && .venv/bin/pytest tests/test_geo.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'skyfire.geo'`

- [ ] **Step 3: 实现(球面目的地公式)**

`skyfire/src/skyfire/geo.py`:

```python
import math
from dataclasses import dataclass

EARTH_R_KM = 6371.0


@dataclass
class GeoPoint:
    lat: float
    lon: float
    dist_km: float


def destination(lat: float, lon: float, bearing_deg: float, distance_km: float) -> tuple[float, float]:
    """从 (lat, lon) 沿 bearing 方向走 distance_km 后的坐标(大圆)。"""
    phi1 = math.radians(lat)
    lam1 = math.radians(lon)
    theta = math.radians(bearing_deg)
    delta = distance_km / EARTH_R_KM
    phi2 = math.asin(
        math.sin(phi1) * math.cos(delta) + math.cos(phi1) * math.sin(delta) * math.cos(theta)
    )
    lam2 = lam1 + math.atan2(
        math.sin(theta) * math.sin(delta) * math.cos(phi1),
        math.cos(delta) - math.sin(phi1) * math.sin(phi2),
    )
    return math.degrees(phi2), math.degrees(lam2)


def channel_points(
    lat: float, lon: float, azimuth_deg: float,
    start_km: float = 50, end_km: float = 400, step_km: float = 50,
) -> list[GeoPoint]:
    """沿日落/日出方位角方向的光通道采样点。"""
    pts = []
    d = start_km
    while d <= end_km:
        plat, plon = destination(lat, lon, azimuth_deg, d)
        pts.append(GeoPoint(lat=plat, lon=plon, dist_km=d))
        d += step_km
    return pts
```

- [ ] **Step 4: 运行确认通过**

Run: `cd /Users/feitong/photo-app/skyfire && .venv/bin/pytest tests/test_geo.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: 提交**

```bash
cd /Users/feitong/photo-app
git add skyfire/src/skyfire/geo.py skyfire/tests/test_geo.py
git commit -m "feat(skyfire): 光通道采样点几何计算"
```

---

### Task 5: 数据模型 + Open-Meteo 客户端(多模式/空气质量/通道批量)

**Files:**
- Create: `skyfire/src/skyfire/models.py`
- Create: `skyfire/src/skyfire/openmeteo.py`
- Test: `skyfire/tests/test_openmeteo.py`

- [ ] **Step 1: 写数据模型(无测试,纯声明)**

`skyfire/src/skyfire/models.py`:

```python
from dataclasses import dataclass


@dataclass
class HourlyPoint:
    time: str                     # "2026-07-03T19:00"(城市本地时区)
    cloud_cover: float | None
    cloud_low: float | None
    cloud_mid: float | None
    cloud_high: float | None
    rh_2m: float | None
    wind_speed: float | None      # m/s
    temperature: float | None     # °C
    dew_point: float | None       # °C
    precipitation: float | None   # mm


@dataclass
class ModelForecast:
    model: str
    hourly: list[HourlyPoint]

    def at(self, iso_hour: str) -> HourlyPoint | None:
        for h in self.hourly:
            if h.time == iso_hour:
                return h
        return None


@dataclass
class ChannelPoint:
    dist_km: float
    cloud_low: float | None
    cloud_total: float | None
```

- [ ] **Step 2: 写失败测试(httpx.MockTransport,不打真实网络)**

`skyfire/tests/test_openmeteo.py`:

```python
import json

import httpx

from skyfire.geo import GeoPoint
from skyfire.openmeteo import (
    MODELS,
    fetch_aod_at,
    fetch_channel_profile,
    fetch_point_forecast,
)


def _multi_model_payload():
    times = ["2026-07-03T19:00", "2026-07-03T20:00"]
    hourly = {"time": times}
    for m in MODELS:
        hourly[f"cloud_cover_{m}"] = [60, 55]
        hourly[f"cloud_cover_low_{m}"] = [10, 12]
        hourly[f"cloud_cover_mid_{m}"] = [15, 14]
        hourly[f"cloud_cover_high_{m}"] = [48, 45]
        hourly[f"relative_humidity_2m_{m}"] = [70, 72]
        hourly[f"wind_speed_10m_{m}"] = [2.5, 2.8]
        hourly[f"temperature_2m_{m}"] = [30, 29]
        hourly[f"dew_point_2m_{m}"] = [22, 22]
        hourly[f"precipitation_{m}"] = [0, 0]
    return {"hourly": hourly}


def _client(payload):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_fetch_point_forecast_parses_all_models():
    client = _client(_multi_model_payload())
    forecasts = fetch_point_forecast(client, 39.9, 116.4, "Asia/Shanghai")
    assert [f.model for f in forecasts] == list(MODELS)
    h = forecasts[0].at("2026-07-03T19:00")
    assert h.cloud_high == 48 and h.cloud_low == 10
    assert forecasts[0].at("2099-01-01T00:00") is None


def test_fetch_point_forecast_tolerates_missing_variable():
    payload = _multi_model_payload()
    del payload["hourly"][f"cloud_cover_high_{MODELS[0]}"]  # EC 缺某变量
    client = _client(payload)
    forecasts = fetch_point_forecast(client, 39.9, 116.4, "Asia/Shanghai")
    assert forecasts[0].at("2026-07-03T19:00").cloud_high is None


def test_fetch_aod_at():
    payload = {"hourly": {"time": ["2026-07-03T19:00"], "aerosol_optical_depth": [0.35]}}
    client = _client(payload)
    assert fetch_aod_at(client, 39.9, 116.4, "Asia/Shanghai", "2026-07-03T19:00") == 0.35


def test_fetch_channel_profile():
    # 多地点请求返回 list
    payload = [
        {"hourly": {"time": ["2026-07-03T19:00"], "cloud_cover": [80], "cloud_cover_low": [70]}},
        {"hourly": {"time": ["2026-07-03T19:00"], "cloud_cover": [20], "cloud_cover_low": [5]}},
    ]
    client = _client(payload)
    pts = [GeoPoint(40.0, 115.0, 100), GeoPoint(40.1, 114.0, 200)]
    profile = fetch_channel_profile(client, pts, "Asia/Shanghai", "2026-07-03T19:00")
    assert len(profile) == 2
    assert profile[0].dist_km == 100 and profile[0].cloud_low == 70
    assert profile[1].cloud_total == 20
```

- [ ] **Step 3: 运行确认失败**

Run: `cd /Users/feitong/photo-app/skyfire && .venv/bin/pytest tests/test_openmeteo.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'skyfire.openmeteo'`

- [ ] **Step 4: 实现**

`skyfire/src/skyfire/openmeteo.py`:

```python
"""Open-Meteo 数据采集:多模式点预报、AOD、通道剖面批量查询。"""
import httpx

from skyfire.geo import GeoPoint
from skyfire.models import ChannelPoint, HourlyPoint, ModelForecast

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
AIR_QUALITY_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"

MODELS = ("ecmwf_ifs025", "gfs_seamless", "icon_seamless", "cma_grapes_global")

HOURLY_VARS = (
    "cloud_cover", "cloud_cover_low", "cloud_cover_mid", "cloud_cover_high",
    "relative_humidity_2m", "wind_speed_10m", "temperature_2m", "dew_point_2m",
    "precipitation",
)

_FIELD_BY_VAR = {
    "cloud_cover": "cloud_cover", "cloud_cover_low": "cloud_low",
    "cloud_cover_mid": "cloud_mid", "cloud_cover_high": "cloud_high",
    "relative_humidity_2m": "rh_2m", "wind_speed_10m": "wind_speed",
    "temperature_2m": "temperature", "dew_point_2m": "dew_point",
    "precipitation": "precipitation",
}


def _series(hourly: dict, var: str, model_suffix: str, n: int) -> list:
    key = f"{var}{model_suffix}"
    values = hourly.get(key)
    if values is None:
        return [None] * n
    return values


def fetch_point_forecast(
    client: httpx.Client, lat: float, lon: float, tz: str,
    models: tuple[str, ...] = MODELS, forecast_days: int = 3,
) -> list[ModelForecast]:
    resp = client.get(FORECAST_URL, params={
        "latitude": lat, "longitude": lon, "timezone": tz,
        "hourly": ",".join(HOURLY_VARS), "models": ",".join(models),
        "wind_speed_unit": "ms", "forecast_days": forecast_days,
    })
    resp.raise_for_status()
    hourly = resp.json()["hourly"]
    times = hourly["time"]
    result = []
    for m in models:
        suffix = f"_{m}" if len(models) > 1 else ""
        columns = {
            field: _series(hourly, var, suffix, len(times))
            for var, field in _FIELD_BY_VAR.items()
        }
        points = [
            HourlyPoint(time=t, **{f: columns[f][i] for f in columns})
            for i, t in enumerate(times)
        ]
        result.append(ModelForecast(model=m, hourly=points))
    return result


def fetch_aod_at(client: httpx.Client, lat: float, lon: float, tz: str, iso_hour: str) -> float | None:
    resp = client.get(AIR_QUALITY_URL, params={
        "latitude": lat, "longitude": lon, "timezone": tz,
        "hourly": "aerosol_optical_depth",
    })
    resp.raise_for_status()
    hourly = resp.json()["hourly"]
    for t, v in zip(hourly["time"], hourly["aerosol_optical_depth"]):
        if t == iso_hour:
            return v
    return None


def fetch_channel_profile(
    client: httpx.Client, points: list[GeoPoint], tz: str, iso_hour: str,
    model: str = "gfs_seamless",
) -> list[ChannelPoint]:
    """通道剖面:多地点一次请求(逗号分隔),单模式(MVP 用 GFS)。"""
    resp = client.get(FORECAST_URL, params={
        "latitude": ",".join(str(round(p.lat, 3)) for p in points),
        "longitude": ",".join(str(round(p.lon, 3)) for p in points),
        "timezone": tz, "hourly": "cloud_cover,cloud_cover_low",
        "models": model, "forecast_days": 3,
    })
    resp.raise_for_status()
    data = resp.json()
    locations = data if isinstance(data, list) else [data]
    profile = []
    for geo, loc in zip(points, locations):
        hourly = loc["hourly"]
        low = total = None
        for i, t in enumerate(hourly["time"]):
            if t == iso_hour:
                total = hourly["cloud_cover"][i]
                low = hourly["cloud_cover_low"][i]
                break
        profile.append(ChannelPoint(dist_km=geo.dist_km, cloud_low=low, cloud_total=total))
    return profile
```

- [ ] **Step 5: 运行确认通过**

Run: `cd /Users/feitong/photo-app/skyfire && .venv/bin/pytest tests/test_openmeteo.py -v`
Expected: PASS (4 passed)

- [ ] **Step 6: 提交**

```bash
cd /Users/feitong/photo-app
git add skyfire/src/skyfire/models.py skyfire/src/skyfire/openmeteo.py skyfire/tests/test_openmeteo.py
git commit -m "feat(skyfire): Open-Meteo 多模式采集+AOD+通道剖面"
```

---

### Task 6: 火烧云规则评分(纯函数)

**Files:**
- Create: `skyfire/src/skyfire/scoring/__init__.py`(空文件)
- Create: `skyfire/src/skyfire/scoring/firecloud.py`
- Test: `skyfire/tests/test_firecloud.py`

- [ ] **Step 1: 写失败测试(spec 9 节要求的边界场景)**

`skyfire/tests/test_firecloud.py`:

```python
from skyfire.models import ChannelPoint
from skyfire.scoring.firecloud import FireCloudInputs, fire_cloud_score

CLEAN_CHANNEL = [ChannelPoint(dist_km=d, cloud_low=5, cloud_total=15) for d in range(50, 401, 50)]
BLOCKED_CHANNEL = [ChannelPoint(dist_km=d, cloud_low=90, cloud_total=95) for d in range(50, 401, 50)]


def _inputs(**kw):
    base = dict(cloud_high=50, cloud_mid=10, cloud_low=10,
                precipitation=0, aod=0.2, channel=CLEAN_CHANNEL)
    base.update(kw)
    return FireCloudInputs(**base)


def test_ideal_conditions_score_high():
    r = fire_cloud_score(_inputs())
    assert r.score >= 8.5


def test_clear_sky_scores_zero():
    r = fire_cloud_score(_inputs(cloud_high=0, cloud_mid=0))
    assert r.score == 0.0


def test_blocked_channel_is_veto():
    r = fire_cloud_score(_inputs(channel=BLOCKED_CHANNEL))
    assert r.score <= 1.5
    assert r.blocked_points == 7  # 100-400km 内 7 个点全堵


def test_local_overcast_low_cloud_penalized():
    r = fire_cloud_score(_inputs(cloud_low=95))
    assert r.score <= 3.0


def test_heavy_aerosol_penalized():
    clean = fire_cloud_score(_inputs(aod=0.2)).score
    hazy = fire_cloud_score(_inputs(aod=1.2)).score
    assert hazy < clean * 0.5


def test_rain_in_window_penalized():
    r = fire_cloud_score(_inputs(precipitation=2.0))
    assert r.score <= 2.5


def test_missing_aod_is_neutral():
    r = fire_cloud_score(_inputs(aod=None))
    assert r.score >= 8.5
```

- [ ] **Step 2: 运行确认失败**

Run: `cd /Users/feitong/photo-app/skyfire && .venv/bin/pytest tests/test_firecloud.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'skyfire.scoring'`

- [ ] **Step 3: 实现**

`skyfire/src/skyfire/scoring/__init__.py`: 空文件。

`skyfire/src/skyfire/scoring/firecloud.py`:

```python
"""火烧云规则评分。

因子(spec 5.1):画布云、通道透光(一票否决级)、本地低云遮挡、
气溶胶、降水。所有阈值为初版经验值,待回测校准(spec 9)。
"""
from dataclasses import dataclass

from skyfire.models import ChannelPoint


@dataclass
class FireCloudInputs:
    cloud_high: float
    cloud_mid: float
    cloud_low: float
    precipitation: float
    aod: float | None
    channel: list[ChannelPoint]


@dataclass
class FireCloudScore:
    score: float             # 0-10
    canvas: float            # 画布分量 0-10
    channel_factor: float    # 0-1
    blocked_points: int      # 100-400km 内被堵采样点数


def canvas_score(cloud_high: float, cloud_mid: float) -> float:
    """画布云:高云全权重、中云半权重;40-70% 覆盖最佳。"""
    canvas = cloud_high + 0.5 * cloud_mid
    if canvas < 5:
        return 0.0
    if canvas < 40:
        return round(10 * (canvas - 5) / 35, 2)
    if canvas <= 70:
        return 10.0
    return round(max(0.0, 10 * (100 - canvas) / 30), 2)


def channel_factor(channel: list[ChannelPoint]) -> tuple[float, int]:
    """通道透光:100-400km 采样点,低云>60% 或总云>85% 视为堵。
    半数以上堵 → 一票否决(0.1)。缺数据的点不计。"""
    scored = [p for p in channel if 100 <= p.dist_km <= 400
              and p.cloud_low is not None and p.cloud_total is not None]
    if not scored:
        return 1.0, 0
    blocked = sum(1 for p in scored if p.cloud_low > 60 or p.cloud_total > 85)
    frac = blocked / len(scored)
    return max(0.1, round(1 - 1.8 * frac, 2)), blocked


def local_low_factor(cloud_low: float) -> float:
    """本地低云遮挡:低云盖顶时地面看不到高云画布。"""
    if cloud_low <= 40:
        return 1.0
    if cloud_low <= 70:
        return 0.7
    return 0.25


def aerosol_factor(aod: float | None) -> float:
    if aod is None:
        return 1.0  # 缺数据不惩罚,置信度由上层降级
    if aod < 0.3:
        return 1.0
    if aod < 0.6:
        return 0.85
    if aod < 1.0:
        return 0.6
    return 0.3


def precip_factor(precipitation: float) -> float:
    return 0.2 if precipitation > 0.5 else 1.0


def fire_cloud_score(inp: FireCloudInputs) -> FireCloudScore:
    canvas = canvas_score(inp.cloud_high, inp.cloud_mid)
    ch_factor, blocked = channel_factor(inp.channel)
    score = (canvas * ch_factor * local_low_factor(inp.cloud_low)
             * aerosol_factor(inp.aod) * precip_factor(inp.precipitation))
    return FireCloudScore(
        score=round(score, 1), canvas=canvas,
        channel_factor=ch_factor, blocked_points=blocked,
    )
```

- [ ] **Step 4: 运行确认通过**

Run: `cd /Users/feitong/photo-app/skyfire && .venv/bin/pytest tests/test_firecloud.py -v`
Expected: PASS (7 passed)

- [ ] **Step 5: 提交**

```bash
cd /Users/feitong/photo-app
git add skyfire/src/skyfire/scoring skyfire/tests/test_firecloud.py
git commit -m "feat(skyfire): 火烧云五因子规则评分"
```

---

### Task 7: 多模式一致性 → 置信度

**Files:**
- Create: `skyfire/src/skyfire/consensus.py`
- Test: `skyfire/tests/test_consensus.py`

- [ ] **Step 1: 写失败测试**

`skyfire/tests/test_consensus.py`:

```python
from skyfire.consensus import consensus


def test_agreement_gives_high_confidence():
    c = consensus({"ecmwf_ifs025": 7.8, "gfs_seamless": 7.2, "icon_seamless": 7.6, "cma_grapes_global": 6.9})
    assert c.confidence == "high"
    assert 7.0 <= c.index <= 7.6
    assert c.spread == 0.9


def test_disagreement_gives_low_confidence():
    c = consensus({"ecmwf_ifs025": 9.0, "gfs_seamless": 2.0})
    assert c.confidence == "low"


def test_single_model_is_degraded():
    c = consensus({"gfs_seamless": 6.0})
    assert c.index == 6.0
    assert c.confidence == "degraded"  # 单模式:数据不全,置信度降级(spec 8)
```

- [ ] **Step 2: 运行确认失败**

Run: `cd /Users/feitong/photo-app/skyfire && .venv/bin/pytest tests/test_consensus.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'skyfire.consensus'`

- [ ] **Step 3: 实现**

`skyfire/src/skyfire/consensus.py`:

```python
"""多模式一致性:分歧宽度 → 置信度(spec 5.3)。"""
from dataclasses import dataclass


@dataclass
class Consensus:
    index: float                 # 共识指数(各模式均值)
    per_model: dict[str, float]
    spread: float                # max - min
    confidence: str              # high / medium / low / degraded


def consensus(per_model: dict[str, float]) -> Consensus:
    values = list(per_model.values())
    index = round(sum(values) / len(values), 1)
    spread = round(max(values) - min(values), 1)
    if len(values) < 2:
        confidence = "degraded"
    elif spread <= 1.5:
        confidence = "high"
    elif spread <= 3.0:
        confidence = "medium"
    else:
        confidence = "low"
    return Consensus(index=index, per_model=per_model, spread=spread, confidence=confidence)
```

- [ ] **Step 4: 运行确认通过**

Run: `cd /Users/feitong/photo-app/skyfire && .venv/bin/pytest tests/test_consensus.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: 提交**

```bash
cd /Users/feitong/photo-app
git add skyfire/src/skyfire/consensus.py skyfire/tests/test_consensus.py
git commit -m "feat(skyfire): 多模式一致性置信度"
```

---

### Task 8: 云海规则评分(纯函数)

**Files:**
- Create: `skyfire/src/skyfire/scoring/cloudsea.py`
- Test: `skyfire/tests/test_cloudsea.py`

**说明:** 点预报拿不到雾顶高度,MVP 以"辐射雾/低层云生成条件"打分(晴夜辐射降温、近饱和、静风、日出时低云存在);雾顶 vs 机位海拔的精确判断留给 Plan B 的卫星实况层。此简化已在 spec 5.2 范围内。

- [ ] **Step 1: 写失败测试**

`skyfire/tests/test_cloudsea.py`:

```python
from skyfire.scoring.cloudsea import CloudSeaInputs, cloud_sea_score


def _inputs(**kw):
    base = dict(night_cloud_avg=10, dawn_rh=97, dawn_wind=1.5,
                dawn_temp_dew_spread=1.0, dawn_cloud_low=50)
    base.update(kw)
    return CloudSeaInputs(**base)


def test_ideal_radiation_fog_night_scores_high():
    assert cloud_sea_score(_inputs()).score >= 8.5


def test_windy_night_scores_low():
    assert cloud_sea_score(_inputs(dawn_wind=8.0)).score <= 6.0


def test_dry_air_scores_low():
    r = cloud_sea_score(_inputs(dawn_rh=60, dawn_temp_dew_spread=8, dawn_cloud_low=0))
    assert r.score <= 3.5


def test_overcast_night_blocks_radiation_cooling():
    ideal = cloud_sea_score(_inputs()).score
    cloudy = cloud_sea_score(_inputs(night_cloud_avg=90)).score
    assert cloudy <= ideal - 3.0
```

- [ ] **Step 2: 运行确认失败**

Run: `cd /Users/feitong/photo-app/skyfire && .venv/bin/pytest tests/test_cloudsea.py -v`
Expected: FAIL — `ImportError: cannot import name 'CloudSeaInputs'`

- [ ] **Step 3: 实现**

`skyfire/src/skyfire/scoring/cloudsea.py`:

```python
"""云海规则评分(spec 5.2,MVP 简化:辐射雾/低层云生成条件)。

加分制,满分 10:晴夜辐射降温 3 + 近饱和 2.5 + 静风 2 +
温度露点差 1 + 日出时低云存在 1.5。
另有两条物理门槛(不加分,只清零):大风(≥5 m/s)吹散辐射雾 →
近饱和分清零;空气太干(RH<85%)雾无从生成 → 静风分清零。
阈值待回测校准。
"""
from dataclasses import dataclass


@dataclass
class CloudSeaInputs:
    night_cloud_avg: float        # 前夜 22:00-04:00 平均总云量 %
    dawn_rh: float                # 日出时 2m 相对湿度 %
    dawn_wind: float              # 日出时 10m 风速 m/s
    dawn_temp_dew_spread: float   # 日出时 T - Td (°C)
    dawn_cloud_low: float         # 日出时低云量 %


@dataclass
class CloudSeaScore:
    score: float
    parts: dict[str, float]


def cloud_sea_score(inp: CloudSeaInputs) -> CloudSeaScore:
    parts: dict[str, float] = {}
    if inp.night_cloud_avg < 30:
        parts["radiative_cooling"] = 3.0
    elif inp.night_cloud_avg < 60:
        parts["radiative_cooling"] = 1.5
    else:
        parts["radiative_cooling"] = 0.0
    if inp.dawn_rh >= 95:
        parts["saturation"] = 2.5
    elif inp.dawn_rh >= 90:
        parts["saturation"] = 1.5
    else:
        parts["saturation"] = 0.0
    if inp.dawn_wind < 3:
        parts["calm_wind"] = 2.0
    elif inp.dawn_wind < 5:
        parts["calm_wind"] = 1.0
    else:
        parts["calm_wind"] = 0.0
    parts["dew_spread"] = 1.0 if inp.dawn_temp_dew_spread <= 2 else 0.0
    parts["low_cloud_present"] = 1.5 if 20 <= inp.dawn_cloud_low <= 90 else 0.0
    # 物理门槛:大风搅散辐射雾;空气太干雾根本起不来
    if inp.dawn_wind >= 5:
        parts["saturation"] = 0.0
    if inp.dawn_rh < 85:
        parts["calm_wind"] = 0.0
    total = round(min(10.0, sum(parts.values())), 1)
    return CloudSeaScore(score=total, parts=parts)
```

- [ ] **Step 4: 运行确认通过**

Run: `cd /Users/feitong/photo-app/skyfire && .venv/bin/pytest tests/test_cloudsea.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: 提交**

```bash
cd /Users/feitong/photo-app
git add skyfire/src/skyfire/scoring/cloudsea.py skyfire/tests/test_cloudsea.py
git commit -m "feat(skyfire): 云海规则评分(辐射雾条件,MVP 简化)"
```

---

### Task 9: SQLite 经验库

**Files:**
- Create: `skyfire/src/skyfire/store.py`
- Test: `skyfire/tests/test_store.py`

- [ ] **Step 1: 写失败测试**

`skyfire/tests/test_store.py`:

```python
import json

from skyfire import store


def _db(tmp_path):
    conn = store.connect(tmp_path / "test.db")
    store.init_db(conn)
    return conn


def test_upsert_case_is_idempotent(tmp_path):
    conn = _db(tmp_path)
    id1 = store.upsert_case(conn, "2026-07-03", "beijing", "sunset_glow",
                            rule_score=7.5, confidence="high", source="auto")
    id2 = store.upsert_case(conn, "2026-07-03", "beijing", "sunset_glow",
                            rule_score=8.0, confidence="medium", source="auto")
    assert id1 == id2  # 同城同日同事件不重复建案例
    row = conn.execute("SELECT rule_score, confidence FROM cases WHERE id=?", (id1,)).fetchone()
    assert row == (8.0, "medium")  # 更新为最新预测


def test_snapshot_roundtrip(tmp_path):
    conn = _db(tmp_path)
    cid = store.upsert_case(conn, "2026-07-03", "beijing", "sunset_glow",
                            rule_score=7.5, confidence="high", source="auto")
    store.add_snapshot(conn, cid, "gfs_seamless", {"cloud_high": 48})
    snaps = store.get_snapshots(conn, cid)
    assert snaps[0]["model"] == "gfs_seamless"
    assert snaps[0]["payload"]["cloud_high"] == 48


def test_actual_score_and_scored_cases(tmp_path):
    conn = _db(tmp_path)
    cid = store.upsert_case(conn, "2026-07-01", "beijing", "sunset_glow",
                            rule_score=8.0, confidence="high", source="cold_start")
    store.upsert_case(conn, "2026-07-02", "beijing", "sunset_glow",
                      rule_score=3.0, confidence="high", source="auto")  # 未打分
    store.set_actual_score(conn, cid, 9.0)
    scored = store.scored_cases(conn, "beijing")
    assert len(scored) == 1
    assert scored[0]["rule_score"] == 8.0 and scored[0]["actual_score"] == 9.0
```

- [ ] **Step 2: 运行确认失败**

Run: `cd /Users/feitong/photo-app/skyfire && .venv/bin/pytest tests/test_store.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'skyfire.store'` (或 AttributeError)

- [ ] **Step 3: 实现(建全 spec 6 的六张表,本计划只写入 cases/forecast_snapshots)**

`skyfire/src/skyfire/store.py`:

```python
"""SQLite 经验库(spec 6)。satellite_frames/photos/users 由 Plan B/C 写入,表先建好。"""
import json
import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS cases (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  date TEXT NOT NULL,
  city TEXT NOT NULL,
  event TEXT NOT NULL CHECK(event IN ('sunrise_glow','sunset_glow','cloud_sea')),
  rule_score REAL,
  llm_score REAL,
  actual_score REAL,
  confidence TEXT,
  source TEXT NOT NULL DEFAULT 'auto',
  created_at TEXT DEFAULT (datetime('now')),
  UNIQUE(date, city, event)
);
CREATE TABLE IF NOT EXISTS forecast_snapshots (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  case_id INTEGER NOT NULL REFERENCES cases(id),
  model TEXT NOT NULL,
  run_time TEXT DEFAULT (datetime('now')),
  payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS satellite_frames (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  case_id INTEGER NOT NULL REFERENCES cases(id),
  ts TEXT NOT NULL,
  channel TEXT NOT NULL,
  path TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS photos (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  case_id INTEGER NOT NULL REFERENCES cases(id),
  user_id TEXT,
  score REAL,
  path TEXT,
  note TEXT
);
CREATE TABLE IF NOT EXISTS spots (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  city TEXT NOT NULL,
  name TEXT NOT NULL,
  lat REAL, lon REAL, elevation_m REAL,
  UNIQUE(city, name)
);
CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  openid TEXT UNIQUE,
  name TEXT
);
"""


def connect(path: Path | str) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()


def upsert_case(conn, date: str, city: str, event: str, *,
                rule_score: float | None, confidence: str | None, source: str) -> int:
    conn.execute(
        """INSERT INTO cases (date, city, event, rule_score, confidence, source)
           VALUES (?, ?, ?, ?, ?, ?)
           ON CONFLICT(date, city, event)
           DO UPDATE SET rule_score=excluded.rule_score, confidence=excluded.confidence""",
        (date, city, event, rule_score, confidence, source),
    )
    conn.commit()
    row = conn.execute(
        "SELECT id FROM cases WHERE date=? AND city=? AND event=?", (date, city, event)
    ).fetchone()
    return row[0]


def set_actual_score(conn, case_id: int, score: float) -> None:
    conn.execute("UPDATE cases SET actual_score=? WHERE id=?", (score, case_id))
    conn.commit()


def add_snapshot(conn, case_id: int, model: str, payload: dict) -> None:
    conn.execute(
        "INSERT INTO forecast_snapshots (case_id, model, payload) VALUES (?, ?, ?)",
        (case_id, model, json.dumps(payload, ensure_ascii=False)),
    )
    conn.commit()


def get_snapshots(conn, case_id: int) -> list[dict]:
    rows = conn.execute(
        "SELECT model, run_time, payload FROM forecast_snapshots WHERE case_id=?", (case_id,)
    ).fetchall()
    return [{"model": m, "run_time": rt, "payload": json.loads(p)} for m, rt, p in rows]


def scored_cases(conn, city: str) -> list[dict]:
    """已闭环案例(有实际打分),回测用。"""
    rows = conn.execute(
        """SELECT date, event, rule_score, actual_score FROM cases
           WHERE city=? AND actual_score IS NOT NULL AND rule_score IS NOT NULL
           ORDER BY date""",
        (city,),
    ).fetchall()
    return [{"date": d, "event": e, "rule_score": r, "actual_score": a}
            for d, e, r, a in rows]
```

- [ ] **Step 4: 运行确认通过**

Run: `cd /Users/feitong/photo-app/skyfire && .venv/bin/pytest tests/test_store.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: 提交**

```bash
cd /Users/feitong/photo-app
git add skyfire/src/skyfire/store.py skyfire/tests/test_store.py
git commit -m "feat(skyfire): SQLite 经验库(六表 schema + 案例/快照读写)"
```

---

### Task 10: 回测(Spearman 相关性)

**Files:**
- Create: `skyfire/src/skyfire/backtest.py`
- Test: `skyfire/tests/test_backtest.py`

- [ ] **Step 1: 写失败测试**

`skyfire/tests/test_backtest.py`:

```python
import pytest

from skyfire.backtest import spearman


def test_perfect_monotonic_correlation():
    assert spearman([1, 2, 3, 4], [10, 20, 30, 40]) == pytest.approx(1.0)


def test_perfect_inverse_correlation():
    assert spearman([1, 2, 3, 4], [40, 30, 20, 10]) == pytest.approx(-1.0)


def test_handles_ties_with_average_ranks():
    r = spearman([1, 2, 2, 3], [1, 2, 3, 4])
    assert 0.9 <= r <= 1.0


def test_requires_at_least_three_pairs():
    with pytest.raises(ValueError):
        spearman([1, 2], [1, 2])
```

- [ ] **Step 2: 运行确认失败**

Run: `cd /Users/feitong/photo-app/skyfire && .venv/bin/pytest tests/test_backtest.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'skyfire.backtest'`

- [ ] **Step 3: 实现(手写平均秩,免 scipy 依赖)**

`skyfire/src/skyfire/backtest.py`:

```python
"""回测:规则分 vs 实际打分的 Spearman 相关性(spec 9 首要验收)。"""


def _average_ranks(values: list[float]) -> list[float]:
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        avg_rank = (i + j) / 2 + 1
        for k in range(i, j + 1):
            ranks[order[k]] = avg_rank
        i = j + 1
    return ranks


def spearman(xs: list[float], ys: list[float]) -> float:
    if len(xs) != len(ys) or len(xs) < 3:
        raise ValueError("need at least 3 paired samples")
    rx, ry = _average_ranks(xs), _average_ranks(ys)
    n = len(xs)
    mx, my = sum(rx) / n, sum(ry) / n
    cov = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    vx = sum((a - mx) ** 2 for a in rx)
    vy = sum((b - my) ** 2 for b in ry)
    if vx == 0 or vy == 0:
        raise ValueError("zero variance in ranks")
    return cov / (vx * vy) ** 0.5
```

- [ ] **Step 4: 运行确认通过**

Run: `cd /Users/feitong/photo-app/skyfire && .venv/bin/pytest tests/test_backtest.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: 提交**

```bash
cd /Users/feitong/photo-app
git add skyfire/src/skyfire/backtest.py skyfire/tests/test_backtest.py
git commit -m "feat(skyfire): Spearman 回测(平均秩,零依赖)"
```

---

### Task 11: CLI 编排(predict / cloudsea / backtest / init-db)

**Files:**
- Create: `skyfire/src/skyfire/cli.py`
- Test: `skyfire/tests/test_cli.py`

- [ ] **Step 1: 写失败测试(只测编排逻辑,网络层注入 mock client)**

`skyfire/tests/test_cli.py`:

```python
import httpx
from typer.testing import CliRunner

from skyfire.cli import app
from skyfire.openmeteo import AIR_QUALITY_URL, MODELS

runner = CliRunner()


def _fake_transport():
    """按 URL 分发假响应;时间轴造 48h 覆盖任意窗口小时。"""
    def handler(request: httpx.Request) -> httpx.Response:
        times = [f"2026-07-03T{h:02d}:00" for h in range(24)] + \
                [f"2026-07-04T{h:02d}:00" for h in range(24)]
        n = len(times)
        if request.url.host == httpx.URL(AIR_QUALITY_URL).host:
            return httpx.Response(200, json={"hourly": {
                "time": times, "aerosol_optical_depth": [0.2] * n}})
        if "," in str(request.url.params.get("latitude", "")):  # 通道多点
            count = str(request.url.params["latitude"]).count(",") + 1
            loc = {"hourly": {"time": times, "cloud_cover": [15] * n,
                              "cloud_cover_low": [5] * n}}
            return httpx.Response(200, json=[loc] * count)
        hourly = {"time": times}
        for m in MODELS:  # 本地多模式
            for var, val in [("cloud_cover", 60), ("cloud_cover_low", 10),
                             ("cloud_cover_mid", 15), ("cloud_cover_high", 50),
                             ("relative_humidity_2m", 70), ("wind_speed_10m", 2.5),
                             ("temperature_2m", 30), ("dew_point_2m", 22),
                             ("precipitation", 0)]:
                hourly[f"{var}_{m}"] = [val] * n
        return httpx.Response(200, json={"hourly": hourly})

    return httpx.MockTransport(handler)


def test_predict_prints_card_and_saves_case(tmp_path, monkeypatch):
    import skyfire.cli as cli
    monkeypatch.setattr(cli, "_make_client", lambda: httpx.Client(transport=_fake_transport()))
    db = tmp_path / "sky.db"
    result = runner.invoke(app, ["predict", "--city", "beijing", "--event", "sunset_glow",
                                 "--date", "2026-07-03", "--db", str(db)])
    assert result.exit_code == 0, result.output
    assert "火烧云指数" in result.output
    assert "置信度" in result.output
    # 案例落库
    from skyfire import store
    conn = store.connect(db)
    row = conn.execute("SELECT city, event, rule_score FROM cases").fetchone()
    assert row[0] == "beijing" and row[1] == "sunset_glow" and row[2] is not None


def test_backtest_needs_scored_cases(tmp_path):
    db = tmp_path / "sky.db"
    result = runner.invoke(app, ["backtest", "--city", "beijing", "--db", str(db)])
    assert result.exit_code != 0
    assert "案例不足" in result.output
```

- [ ] **Step 2: 运行确认失败**

Run: `cd /Users/feitong/photo-app/skyfire && .venv/bin/pytest tests/test_cli.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'skyfire.cli'`

- [ ] **Step 3: 实现**

`skyfire/src/skyfire/cli.py`:

```python
"""skyfire CLI:predict / cloudsea / backtest / init-db。"""
from datetime import date as date_type, datetime, timedelta
from pathlib import Path

import httpx
import typer

from skyfire import store
from skyfire.backtest import spearman
from skyfire.config import load_cities
from skyfire.consensus import consensus
from skyfire.geo import channel_points
from skyfire.openmeteo import fetch_aod_at, fetch_channel_profile, fetch_point_forecast
from skyfire.scoring.cloudsea import CloudSeaInputs, cloud_sea_score
from skyfire.scoring.firecloud import FireCloudInputs, fire_cloud_score
from skyfire.suntimes import sun_window

app = typer.Typer(help="火烧云/云海预测助手")

DEFAULT_CONFIG = Path(__file__).parent.parent.parent / "config" / "cities.yaml"
DEFAULT_DB = Path(__file__).parent.parent.parent / "data" / "skyfire.db"

CONF_ZH = {"high": "高", "medium": "中", "low": "低(模式打架)", "degraded": "降级(数据不全)"}


def _make_client() -> httpx.Client:  # 测试中被 monkeypatch
    return httpx.Client(timeout=30)


def _open_db(db: Path):
    db.parent.mkdir(parents=True, exist_ok=True)
    conn = store.connect(db)
    store.init_db(conn)
    return conn


@app.command()
def predict(
    city: str = typer.Option("beijing"),
    event: str = typer.Option("sunset_glow", help="sunset_glow | sunrise_glow"),
    date: str = typer.Option(None, help="YYYY-MM-DD,默认今天"),
    config: Path = typer.Option(DEFAULT_CONFIG),
    db: Path = typer.Option(DEFAULT_DB),
):
    """火烧云指数:多模式评分 + 一致性置信度,并归档快照。"""
    c = load_cities(config)[city]
    day = date_type.fromisoformat(date) if date else date_type.today()
    win = sun_window(c.lat, c.lon, c.timezone, day, event)
    iso_hour = win.peak.strftime("%Y-%m-%dT%H:00")

    client = _make_client()
    forecasts = fetch_point_forecast(client, c.lat, c.lon, c.timezone)
    aod = fetch_aod_at(client, c.lat, c.lon, c.timezone, iso_hour)
    geo_pts = channel_points(c.lat, c.lon, win.azimuth_deg)
    channel = fetch_channel_profile(client, geo_pts, c.timezone, iso_hour)

    per_model: dict[str, float] = {}
    details = {}
    for fc in forecasts:
        h = fc.at(iso_hour)
        if h is None or h.cloud_high is None:
            continue  # 该模式缺数据,跳过(spec 8 降级)
        r = fire_cloud_score(FireCloudInputs(
            cloud_high=h.cloud_high, cloud_mid=h.cloud_mid or 0,
            cloud_low=h.cloud_low or 0, precipitation=h.precipitation or 0,
            aod=aod, channel=channel,
        ))
        per_model[fc.model] = r.score
        details[fc.model] = r
    if not per_model:
        typer.echo("错误:所有模式数据缺失,无法出分", err=True)
        raise typer.Exit(1)

    cons = consensus(per_model)
    first = next(iter(details.values()))
    event_zh = "晚霞" if event == "sunset_glow" else "朝霞"
    typer.echo(f"⚡ {day} {event_zh} — {c.name}")
    typer.echo(f"火烧云指数: {cons.index}/10  置信度: {CONF_ZH[cons.confidence]}  分歧: {cons.spread}")
    typer.echo("  " + "  ".join(f"{m.split('_')[0].upper()} {s}" for m, s in cons.per_model.items()))
    typer.echo(f"通道: {first.blocked_points} 点受阻 (系数 {first.channel_factor})  AOD: {aod}")
    typer.echo(f"{'日落' if event == 'sunset_glow' else '日出'}: {win.peak.strftime('%H:%M')}  方位 {win.azimuth_deg:.0f}°")

    conn = _open_db(db)
    case_id = store.upsert_case(conn, str(day), city, event,
                                rule_score=cons.index, confidence=cons.confidence, source="auto")
    for fc in forecasts:
        h = fc.at(iso_hour)
        if h is None:
            continue
        store.add_snapshot(conn, case_id, fc.model, {
            "hour": iso_hour, "cloud_high": h.cloud_high, "cloud_mid": h.cloud_mid,
            "cloud_low": h.cloud_low, "cloud_cover": h.cloud_cover,
            "rh_2m": h.rh_2m, "precipitation": h.precipitation, "aod": aod,
            "channel": [{"km": p.dist_km, "low": p.cloud_low, "total": p.cloud_total}
                        for p in channel],
            "azimuth": round(win.azimuth_deg, 1),
        })


@app.command()
def cloudsea(
    city: str = typer.Option("beijing"),
    date: str = typer.Option(None, help="目标日出日 YYYY-MM-DD,默认明天"),
    config: Path = typer.Option(DEFAULT_CONFIG),
    db: Path = typer.Option(DEFAULT_DB),
):
    """云海指数:按机位输出(前夜条件 + 日出时刻状态)。"""
    c = load_cities(config)[city]
    day = date_type.fromisoformat(date) if date else date_type.today() + timedelta(days=1)
    client = _make_client()
    typer.echo(f"🌊 {day} 云海预报 — {c.name}")
    best = 0.0
    for spot in c.spots:
        win = sun_window(spot.lat, spot.lon, c.timezone, day, "sunrise_glow")
        iso_dawn = win.peak.strftime("%Y-%m-%dT%H:00")
        forecasts = fetch_point_forecast(client, spot.lat, spot.lon, c.timezone,
                                         models=("gfs_seamless",))
        fc = forecasts[0]
        dawn = fc.at(iso_dawn)
        if dawn is None:
            typer.echo(f"  {spot.name}: 数据缺失,跳过")
            continue
        night_prev = day - timedelta(days=1)
        night_hours = [f"{night_prev}T{h:02d}:00" for h in (22, 23)] + \
                      [f"{day}T{h:02d}:00" for h in (0, 1, 2, 3, 4)]
        night_vals = [fc.at(t).cloud_cover for t in night_hours
                      if fc.at(t) and fc.at(t).cloud_cover is not None]
        night_avg = sum(night_vals) / len(night_vals) if night_vals else 50.0
        r = cloud_sea_score(CloudSeaInputs(
            night_cloud_avg=night_avg,
            dawn_rh=dawn.rh_2m or 0,
            dawn_wind=dawn.wind_speed or 0,
            dawn_temp_dew_spread=(dawn.temperature or 0) - (dawn.dew_point or 0),
            dawn_cloud_low=dawn.cloud_low or 0,
        ))
        best = max(best, r.score)
        typer.echo(f"  {spot.name} ({spot.elevation_m:.0f}m): {r.score}/10")
    conn = _open_db(db)
    store.upsert_case(conn, str(day), city, "cloud_sea",
                      rule_score=best, confidence="degraded", source="auto")


@app.command()
def backtest(
    city: str = typer.Option("beijing"),
    db: Path = typer.Option(DEFAULT_DB),
):
    """规则分 vs 实际打分的 Spearman 相关性(spec 9 首要验收)。"""
    conn = _open_db(db)
    cases = store.scored_cases(conn, city)
    if len(cases) < 3:
        typer.echo(f"案例不足({len(cases)} 条,需 ≥3):先积累打分或跑冷启动回填(Plan B)", err=True)
        raise typer.Exit(1)
    rho = spearman([x["rule_score"] for x in cases], [x["actual_score"] for x in cases])
    typer.echo(f"回测: {len(cases)} 条闭环案例, Spearman ρ = {rho:.3f}")


@app.command("init-db")
def init_db_cmd(db: Path = typer.Option(DEFAULT_DB)):
    """初始化经验库。"""
    _open_db(db)
    typer.echo(f"经验库就绪: {db}")


if __name__ == "__main__":
    app()
```

- [ ] **Step 4: 运行全部测试确认通过**

Run: `cd /Users/feitong/photo-app/skyfire && .venv/bin/pytest -v`
Expected: PASS(全部通过,约 27 条)

- [ ] **Step 5: 提交**

```bash
cd /Users/feitong/photo-app
git add skyfire/src/skyfire/cli.py skyfire/tests/test_cli.py
git commit -m "feat(skyfire): CLI 编排(predict/cloudsea/backtest/init-db)"
```

---

### Task 12: 端到端真实验证(北京今晚)

**Files:** 无新文件——真实 API 冒烟验证。

- [ ] **Step 1: 真实调用 predict**

Run: `cd /Users/feitong/photo-app/skyfire && .venv/bin/skyfire predict --city beijing --event sunset_glow`
Expected: 打印当天北京晚霞指数卡片(指数/置信度/各模式分/通道/日落时刻),无异常。若 Open-Meteo 网络失败,重试一次;仍失败则记录错误信息,不算任务失败(网络环境问题),改用 `--date` 指定日期重试。

- [ ] **Step 2: 真实调用 cloudsea 与 backtest**

Run: `.venv/bin/skyfire cloudsea --city beijing`
Expected: 三个机位(雾灵山/百花山/妙峰山)各出一行分数。

Run: `.venv/bin/skyfire backtest --city beijing`
Expected: 报"案例不足"退出码非 0(此时尚无打分案例——符合预期,冷启动在 Plan B)。

- [ ] **Step 3: 检查数据落库**

Run: `sqlite3 /Users/feitong/photo-app/skyfire/data/skyfire.db "SELECT date, city, event, rule_score, confidence FROM cases;"`
Expected: 至少 2 行(sunset_glow + cloud_sea),rule_score 非空。

- [ ] **Step 4: 提交收尾**

```bash
cd /Users/feitong/photo-app
git add -A skyfire
git commit -m "feat(skyfire): 后端预测核心完成(Plan A)——真实 API 端到端验证通过"
```

---

## Self-Review 记录

- **Spec 覆盖**:spec 4(数据源:Open-Meteo 多模式/AOD/通道采样/日出日落)→ Task 3/4/5;spec 5.1 → Task 6;5.2 → Task 8;5.3 → Task 7;6(六表 schema、自动归档)→ Task 9 + Task 11 predict 落库;8(单模式降级/缺数据跳过)→ Task 7 degraded + Task 11;9(回测/构造场景单测/端到端)→ Task 10/6/12。**不在本计划**(Plan B/C):spec 5.4 实况层、5.5 Claude 经验层、6.1 冷启动、7 客户端、推送。
- **占位符扫描**:无 TBD/TODO;所有代码步骤含完整代码。
- **类型一致性**:`ChannelPoint(dist_km, cloud_low, cloud_total)` 在 Task 5/6/11 一致;`fire_cloud_score(FireCloudInputs) -> FireCloudScore` 在 Task 6/11 一致;`store.upsert_case(..., rule_score=, confidence=, source=)` 在 Task 9/11 一致;`sun_window(...) -> SunWindow(peak, azimuth_deg)` 在 Task 3/11 一致。
