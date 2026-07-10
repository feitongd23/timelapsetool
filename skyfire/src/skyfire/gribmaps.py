"""GRIB 直采全国图管线(sunsetbot 式,零 Open-Meteo 配额)。

用户 2026-07-09 拍板:EC 与 GFS 两套全国预测图,各自跟随模式更新周期重刷。
- GFS:AWS 公开桶 noaa-gfs-bdp-pds,.idx 索引字节段下载 LCDC/MCDC/HCDC/PRATE,
  0.25°,逐小时步长,每日 4 轮(00/06/12/18z,约 3.5-5h 延迟)。
- EC:ECMWF 开放数据(CC-BY,ecmwf-opendata 客户端,自动走 ECMWF/AWS 镜像),
  开放集不含分层云量,按气压层相对湿度推算高/中/低云(Open-Meteo 同法);
  3 小时步长,每日 4 轮(约 7-8h 延迟)。
状态文件记录各模式已渲染的轮次,新轮次到达才重刷("随数据更新而更新")。
"""
import json
import tempfile
import warnings
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import numpy as np

from skyfire.gridmap import CHINA_BBOX
from skyfire.heatgrid import score_grids_physics
from skyfire.heatmap_map import render_map_png
from skyfire.suntimes import sun_window

GFS_BASE = "https://noaa-gfs-bdp-pds.s3.amazonaws.com"
# 中国区裁剪(与 CHINA_BBOX 一致):lon 100-135E, lat 17-45N
_LON0, _LAT0, _LON1, _LAT1 = CHINA_BBOX

# EC 湿度→云量推算的逐层临界 RH(高层卷云在低 RH 即成云)。
# 2026-07-09 北京单点对照 Open-Meteo EC 定标:高 97↔100 中 75↔74;
# 低层 crit 80 时 850hPa RH89.9 误报 50%(OM 低云=0)→ 提到 90。
_EC_LEVELS = {"low": (1000, 925, 850), "mid": (700, 500), "high": (300, 250, 200)}
_RH_CRIT = {"low": 90.0, "mid": 65.0, "high": 50.0}

MODELS = ("ec", "gfs")


# ---------- GFS ----------

def _gfs_urls(run: datetime, fh: int) -> tuple[str, str]:
    d = run.strftime("%Y%m%d")
    f = f"gfs.t{run.hour:02d}z.pgrb2.0p25.f{fh:03d}"
    base = f"{GFS_BASE}/gfs.{d}/{run.hour:02d}/atmos/{f}"
    return base, base + ".idx"


def latest_gfs_run(client: httpx.Client, now: datetime | None = None) -> datetime | None:
    """最新已发布的 GFS 轮次(探 f012 的 idx 是否存在,从新到旧)。"""
    now = now or datetime.now(timezone.utc)
    for back in range(5):
        t = now - timedelta(hours=6 * back + 4)   # ~4h 发布延迟
        run = t.replace(hour=(t.hour // 6) * 6, minute=0, second=0, microsecond=0)
        try:
            r = client.head(_gfs_urls(run, 12)[1])
            if r.status_code == 200:
                return run
        except httpx.HTTPError:
            continue
    return None


def parse_idx(text: str, wanted: set[str]) -> list[tuple[str, int, int | None]]:
    """GRIB .idx → [(key, start, end)];key 形如 'HCDC:high cloud layer:12 hour fcst'。"""
    lines = text.splitlines()
    out = []
    for i, ln in enumerate(lines):
        p = ln.split(":")
        key = f"{p[3]}:{p[4]}:{p[5]}"
        if key in wanted:
            start = int(p[1])
            end = int(lines[i + 1].split(":")[1]) - 1 if i + 1 < len(lines) else None
            out.append((key, start, end))
    return out


def fetch_gfs_china(client: httpx.Client, run: datetime, fh: int) -> dict | None:
    """一个预报时次的中国区云场:{'high','mid','low','precip'} 0.25° 数组(北→南)。"""
    base, idx_url = _gfs_urls(run, fh)
    wanted = {f"LCDC:low cloud layer:{fh} hour fcst",
              f"MCDC:middle cloud layer:{fh} hour fcst",
              f"HCDC:high cloud layer:{fh} hour fcst",
              f"PRATE:surface:{fh} hour fcst"}
    r = client.get(idx_url)
    if r.status_code != 200:
        return None
    segs = parse_idx(r.text, wanted)
    if len(segs) < 4:
        return None
    buf = b""
    for _, s, e in segs:
        rng = f"bytes={s}-{e}" if e is not None else f"bytes={s}-"
        buf += client.get(base, headers={"Range": rng}).content
    with tempfile.NamedTemporaryFile(suffix=".grib2", delete=False) as f:
        f.write(buf)
        tmp = f.name
    try:
        fields = _decode_grib(tmp)
    finally:
        Path(tmp).unlink(missing_ok=True)
    if not {"hcc", "mcc", "lcc"} <= set(fields):
        return None
    out = {"high": fields["hcc"], "mid": fields["mcc"], "low": fields["lcc"],
           "precip": fields.get("prate")}
    if out["precip"] is not None:
        out["precip"] = out["precip"] * 3600.0   # kg/m²/s → mm/h
    return out


def _decode_grib(path: str) -> dict:
    """GRIB → {shortName: 中国区 ndarray(lat 北→南, lon 西→东)}。"""
    import cfgrib   # 重依赖,按需导入
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        dss = cfgrib.open_datasets(path, indexpath="")
    fields = {}
    for ds in dss:
        for v in ds.data_vars:
            da = ds[v]
            if float(da.latitude[0]) < float(da.latitude[-1]):
                da = da.isel(latitude=slice(None, None, -1))
            sub = da.sel(latitude=slice(_LAT1, _LAT0),
                         longitude=slice(_LON0, _LON1))
            fields[v] = np.asarray(sub.values, dtype=float)
    return fields


# ---------- ECMWF 开放数据 ----------

def _ec_client():
    from ecmwf.opendata import Client
    # 官方口限 500 并发且劝退,走 AWS 镜像(ECMWF 官方复制,免限流)
    return Client(source="aws", model="ifs", resol="0p25")


def latest_ec_run() -> datetime | None:
    try:
        c = _ec_client()
        dt = c.latest(type="fc", step=18, param="tp")
        return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt
    except Exception:
        return None


def rh_to_cloud(rh: np.ndarray, crit: float) -> np.ndarray:
    """相对湿度 → 云量%(线性,RH=crit 起云、100 满云;Open-Meteo 同思路)。"""
    return np.clip((rh - crit) / (100.0 - crit), 0.0, 1.0) * 100.0


def anchor_layers_to_tcc(out: dict, tcc_pct: np.ndarray) -> dict:
    """官方总云量锚定:RH 反演只管垂直分层,总量必须服从 ECMWF 自家 tcc。

    2026-07-10 用户拿 Windy 实锤:青岛/上海官方总云 1-2%,RH 反演却画出
    40-60% 假云带(湿层深厚≠成云;北京单点定标撑不住全国)。
    逐格缩放:ratio = tcc / max(高中低),上限 1.5(轻度低估允许放大),
    官方≈0 处一律归零。
    """
    total = np.maximum.reduce([out["high"], out["mid"], out["low"]])
    ratio = np.where(total > 1.0,
                     np.clip(tcc_pct / np.maximum(total, 1e-6), 0.0, 1.5),
                     1.0)
    for k in ("high", "mid", "low"):
        out[k] = np.clip(out[k] * ratio, 0.0, 100.0)
    return out


def fetch_ec_china(run: datetime, step: int) -> dict | None:
    """EC 开放数据一个步长的中国区云场。

    分层云由气压层 RH 推算,总量用官方 tcc 锚定(见 anchor_layers_to_tcc)。
    """
    c = _ec_client()
    levels = sorted({lv for lvs in _EC_LEVELS.values() for lv in lvs})
    with tempfile.TemporaryDirectory() as td:
        rh_path = f"{td}/r.grib2"
        tcc_path = f"{td}/tcc.grib2"
        try:
            c.retrieve(date=run.strftime("%Y-%m-%d"), time=run.hour,
                       type="fc", step=step, param="r",
                       levelist=levels, target=rh_path)
            c.retrieve(date=run.strftime("%Y-%m-%d"), time=run.hour,
                       type="fc", step=step, param="tcc", target=tcc_path)
        except Exception:
            return None
        rh_by_level = _rh_fields_by_level(rh_path)
        if not rh_by_level:
            return None
        out = {}
        for layer, lvs in _EC_LEVELS.items():
            clouds = [rh_to_cloud(rh_by_level[lv], _RH_CRIT[layer])
                      for lv in lvs if lv in rh_by_level]
            if not clouds:
                return None
            out[{"low": "low", "mid": "mid", "high": "high"}[layer]] = \
                np.maximum.reduce(clouds)
        tcc = _decode_grib(tcc_path).get("tcc")
        if tcc is None:
            return None   # 没有官方总量锚,宁缺毋滥(假云带教训)
        tcc_pct = tcc * 100.0 if np.nanmax(tcc) <= 1.001 else tcc
        out = anchor_layers_to_tcc(out, tcc_pct)
        out["precip"] = _ec_precip(c, run, step, td)
    return out


def _rh_fields_by_level(path: str) -> dict[int, np.ndarray]:
    import cfgrib
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        dss = cfgrib.open_datasets(path, indexpath="")
    out = {}
    for ds in dss:
        if "r" not in ds.data_vars:
            continue
        da = ds["r"]
        if float(da.latitude[0]) < float(da.latitude[-1]):
            da = da.isel(latitude=slice(None, None, -1))
        sub = da.sel(latitude=slice(_LAT1, _LAT0), longitude=slice(_LON0, _LON1))
        levs = np.atleast_1d(ds["isobaricInhPa"].values)
        vals = np.asarray(sub.values, dtype=float)
        if vals.ndim == 2:
            out[int(levs[0])] = vals
        else:
            for i, lv in enumerate(levs):
                out[int(lv)] = vals[i]
    return out


def _ec_precip(c, run: datetime, step: int, td: str) -> np.ndarray | None:
    """tp 累计差分 → 燃烧时段 mm/h(尽力,缺则 None=中性)。"""
    try:
        p1 = f"{td}/tp1.grib2"
        c.retrieve(date=run.strftime("%Y-%m-%d"), time=run.hour,
                   type="fc", step=step, param="tp", target=p1)
        f1 = _decode_grib(p1).get("tp")
        prev = step - 3
        if prev <= 0 or f1 is None:
            return f1 * 1000.0 / max(step, 1) if f1 is not None else None
        p0 = f"{td}/tp0.grib2"
        c.retrieve(date=run.strftime("%Y-%m-%d"), time=run.hour,
                   type="fc", step=prev, param="tp", target=p0)
        f0 = _decode_grib(p0).get("tp")
        if f0 is None:
            return None
        return np.clip(f1 - f0, 0, None) * 1000.0 / 3.0   # m 累计差 → mm/h
    except Exception:
        return None


# ---------- 编排 ----------

def _azimuths_by_row(n_rows: int, bbox, valid_utc: datetime) -> list[float]:
    """逐纬度行的太阳方位角(2026-07-10:全国图通道曾正西/正东硬编码,
    与判读图 270° 线同族病;方位角随纬度显著变化,按行取真值)。"""
    from astral import Observer
    from astral.sun import azimuth

    lon_mid = (bbox[0] + bbox[2]) / 2
    lat1, lat0 = bbox[3], bbox[1]
    out = []
    for r in range(n_rows):
        lat = lat1 - (lat1 - lat0) * r / max(1, n_rows - 1)
        try:
            out.append(azimuth(Observer(lat, lon_mid), valid_utc))
        except Exception:
            out.append(270.0)
    return out


def _aod_grid_safe(client, city, n_rows: int, n_cols: int,
                   valid_utc: datetime):
    """AOD 粗网格(CAMS,air-quality 子域独立配额),失败返回 None(0.85 保守)。

    2026-07-10 强制过全:全国图此前 aod=None 整图裸奔,与"你忘记把气溶胶
    考虑进去了"同病;粗采样 4° 一次请求,双线性放大。
    """
    try:
        from zoneinfo import ZoneInfo

        from skyfire.gridmap import CHINA_BBOX as _BB, fetch_aod_grid
        iso = valid_utc.astimezone(ZoneInfo(city.timezone)).strftime(
            "%Y-%m-%dT%H:00")
        return fetch_aod_grid(client, _BB, n_rows, n_cols, city.timezone,
                              iso, coarse_step=4.0)
    except Exception:
        return None


def _refresh_child(q, city_kw: dict, city_key: str, out_dir: str):
    """子进程入口(spawn 可导入):跑真刷新,结果进队列。"""
    from skyfire.config import City
    try:
        q.put(refresh_grib_maps(City(**city_kw), city_key, Path(out_dir)))
    except Exception:
        q.put(None)


def refresh_grib_maps_bounded(city, city_key: str, out_dir,
                              timeout_s: int = 1500) -> dict[str, int]:
    """带进程级硬超时的刷新。必须用这个入口对外服务:

    下载库 multiurl 默认重试 500 次×120 秒——2026-07-09 夜一次 DNS 抖动把
    tick 挂死数小时(launchd 不重入,晨间检查点链整段缺席)。库不透传重试
    参数,进程硬超时是唯一可靠的保险;超时/异常返回 {}(调用方按失败冷却)。
    """
    from multiprocessing import get_context

    ctx = get_context("spawn")
    q = ctx.Queue()
    kw = {"key": city.key, "name": city.name, "lat": city.lat,
          "lon": city.lon, "timezone": city.timezone, "spots": []}
    p = ctx.Process(target=_refresh_child, args=(q, kw, city_key, str(out_dir)),
                    daemon=True)
    p.start()
    p.join(timeout_s)
    if p.is_alive():
        p.terminate()
        p.join(10)
        return {}
    try:
        r = q.get(timeout=5)
    except Exception:
        r = None
    return r if r is not None else {}



def _grid_to_lists(arr: np.ndarray | None, like: np.ndarray) -> list:
    if arr is None:
        arr = np.zeros_like(like)
    return [[float(v) for v in row] for row in arr]


def _burn_steps(city, day, event, run: datetime, step_quantum: int) -> int | None:
    win = sun_window(city.lat, city.lon, city.timezone, day, event)
    peak_utc = win.peak.astimezone(timezone.utc)
    hours = (peak_utc - run).total_seconds() / 3600
    if hours < 0:
        return None
    step = round(hours / step_quantum) * step_quantum
    return step if 0 < step <= 120 else None


def refresh_grib_maps(city, city_key: str, out_dir: Path,
                      state_path: Path | None = None,
                      client: httpx.Client | None = None) -> dict[str, int]:
    """两模式全国图刷新:仅当该模式有新轮次时重渲染。返回 {model: 写出张数}。"""
    from datetime import date as date_type

    from skyfire.maps import map_path

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    state_path = state_path or out_dir / "state.json"
    state = {}
    if state_path.exists():
        try:
            state = json.loads(state_path.read_text())
        except ValueError:
            state = {}
    owns = client is None
    client = client or httpx.Client(timeout=120)
    written: dict[str, int] = {}
    today = date_type.today()
    days = [today, today + timedelta(days=1)]
    aod_cache: dict = {}   # AOD 网格按时次缓存,两模式共用(时间与配额都省半)
    try:
        runs = {"gfs": latest_gfs_run(client), "ec": latest_ec_run()}
        for model in MODELS:
            run = runs.get(model)
            if run is None:
                continue
            run_tag = run.strftime("%Y%m%d%H")
            if state.get(model) == run_tag:
                written[model] = 0   # 没有新轮次(区别于探测失败:model 缺席)
                continue
            n = 0
            quantum = 1 if model == "gfs" else 3
            for day in days:
                for event in ("sunrise_glow", "sunset_glow"):
                    step = _burn_steps(city, day, event, run, quantum)
                    if step is None:
                        continue
                    cloud_np = (fetch_gfs_china(client, run, step)
                                if model == "gfs" else fetch_ec_china(run, step))
                    if cloud_np is None:
                        continue
                    like = cloud_np["high"]
                    cloud = {k: _grid_to_lists(cloud_np.get(k), like)
                             for k in ("high", "mid", "low", "precip")}
                    valid_utc = run + timedelta(hours=step)
                    az_rows = _azimuths_by_row(len(like), CHINA_BBOX, valid_utc)
                    # AOD 网格按时次缓存:两模式/同时次共用,别把配额和时间翻倍
                    aod_key = valid_utc.strftime("%Y%m%d%H")
                    if aod_key not in aod_cache:
                        aod_cache[aod_key] = _aod_grid_safe(
                            client, city, len(like), len(like[0]), valid_utc)
                    aod_grid = aod_cache[aod_key]
                    grids = score_grids_physics(cloud, aod_grid, event,
                                                CHINA_BBOX, "medium",
                                                azimuth_by_row=az_rows)
                    event_zh = "朝霞" if event == "sunrise_glow" else "晚霞"
                    title = (f"{model.upper()} 轮次 {run:%m-%d %H}z · "
                             f"预测 {day:%m-%d} {event_zh}")
                    if model == "ec":
                        title += " · 云量由湿度场推算"
                    for kind in ("prob", "quality"):
                        png = render_map_png(grids[kind], kind, CHINA_BBOX,
                                             marker=(city.name, city.lat, city.lon),
                                             title=title)
                        map_path(out_dir, city_key, str(day), event, kind,
                                 model).write_bytes(png)
                        n += 1
            if n:
                state[model] = run_tag
                written[model] = n
        state_path.write_text(json.dumps(state))
    finally:
        if owns:
            client.close()
    return written
