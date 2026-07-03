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


def _parse_date(s: str | None, default: date_type) -> date_type:
    if s is None:
        return default
    try:
        return date_type.fromisoformat(s)
    except ValueError:
        typer.echo(f"错误:日期格式应为 YYYY-MM-DD,收到 {s!r}", err=True)
        raise typer.Exit(1)


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
    cities = load_cities(config)
    if city not in cities:
        typer.echo(f"错误:未知城市 {city!r},可用: {', '.join(cities)}", err=True)
        raise typer.Exit(1)
    c = cities[city]
    day = _parse_date(date, date_type.today())
    win = sun_window(c.lat, c.lon, c.timezone, day, event)
    iso_hour = win.peak.strftime("%Y-%m-%dT%H:00")

    client = _make_client()
    geo_pts = channel_points(c.lat, c.lon, win.azimuth_deg)
    try:
        forecasts = fetch_point_forecast(client, c.lat, c.lon, c.timezone)
        aod = fetch_aod_at(client, c.lat, c.lon, c.timezone, iso_hour)
        channel = fetch_channel_profile(client, geo_pts, c.timezone, iso_hour)
    except httpx.HTTPError as e:
        typer.echo(f"错误:Open-Meteo 请求失败({e.__class__.__name__}: {e}),请稍后重试", err=True)
        raise typer.Exit(1)
    channel_empty = all(p.cloud_low is None and p.cloud_total is None for p in channel)

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
    if channel_empty:
        typer.echo("警告: 通道数据缺失,评分未含通道透光校验(置信度参考价值打折)")
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
    cities = load_cities(config)
    if city not in cities:
        typer.echo(f"错误:未知城市 {city!r},可用: {', '.join(cities)}", err=True)
        raise typer.Exit(1)
    c = cities[city]
    day = _parse_date(date, date_type.today() + timedelta(days=1))
    client = _make_client()
    typer.echo(f"🌊 {day} 云海预报 — {c.name}")
    best = 0.0
    for spot in c.spots:
        win = sun_window(spot.lat, spot.lon, c.timezone, day, "sunrise_glow")
        iso_dawn = win.peak.strftime("%Y-%m-%dT%H:00")
        try:
            forecasts = fetch_point_forecast(client, spot.lat, spot.lon, c.timezone,
                                             models=("gfs_seamless",))
        except httpx.HTTPError as e:
            typer.echo(f"错误:Open-Meteo 请求失败({e.__class__.__name__}: {e}),请稍后重试", err=True)
            raise typer.Exit(1)
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
    try:
        rho = spearman([x["rule_score"] for x in cases], [x["actual_score"] for x in cases])
    except ValueError:
        typer.echo("无法计算相关性:所有分数相同(秩零方差),先积累更多有区分度的案例", err=True)
        raise typer.Exit(1)
    typer.echo(f"回测: {len(cases)} 条闭环案例, Spearman ρ = {rho:.3f}")


@app.command("init-db")
def init_db_cmd(db: Path = typer.Option(DEFAULT_DB)):
    """初始化经验库。"""
    _open_db(db)
    typer.echo(f"经验库就绪: {db}")


if __name__ == "__main__":
    app()
