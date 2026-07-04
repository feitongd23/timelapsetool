"""skyfire CLI:predict / cloudsea / backtest / init-db / nowcast / backfill。"""
from datetime import date as date_type, datetime, timedelta, timezone
from pathlib import Path

import httpx
import typer
from PIL import Image

from skyfire import store
from skyfire.backfill import backfill_row, parse_csv
from skyfire.backtest import spearman
from skyfire.cloudiness import box_cloudiness
from skyfire.config import load_cities
from skyfire.drift import estimate_shift, extrapolated_corridor
from skyfire.engine import compute_prediction
from skyfire.himawari import (fetch_region, frame_age_minutes, km_per_px,
                              latest_frame_time, round_down_10min)
from skyfire.nowcast import fuse, obs_score
from skyfire.notifyconf import DEFAULT_LEAD_MINUTES, load_notify_config
from skyfire.openmeteo import fetch_point_forecast
from skyfire.push import push
from skyfire.report import format_report
from skyfire.schedule import due_events
from skyfire.scoring.cloudsea import CloudSeaInputs, cloud_sea_score
from skyfire.suntimes import sun_window

app = typer.Typer(help="火烧云/云海预测助手")

DEFAULT_CONFIG = Path(__file__).parent.parent.parent / "config" / "cities.yaml"
DEFAULT_DB = Path(__file__).parent.parent.parent / "data" / "skyfire.db"
DEFAULT_FRAMES = Path(__file__).parent.parent.parent / "data" / "frames"
DEFAULT_NOTIFY = Path(__file__).parent.parent.parent / "config" / "notify.local.yaml"

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
    no_llm: bool = typer.Option(False, "--no-llm", help="跳过 Claude 解读"),
):
    """火烧云指数:多模式评分 + 一致性置信度,并归档快照。"""
    cities = load_cities(config)
    if city not in cities:
        typer.echo(f"错误:未知城市 {city!r},可用: {', '.join(cities)}", err=True)
        raise typer.Exit(1)
    c = cities[city]
    day = _parse_date(date, date_type.today())
    conn = _open_db(db)
    client = _make_client()
    try:
        r = compute_prediction(conn, client, c, city, event, day, run_llm=not no_llm)
    except httpx.HTTPError as e:
        typer.echo(f"错误:Open-Meteo 请求失败({e.__class__.__name__}: {e}),请稍后重试", err=True)
        raise typer.Exit(1)
    except ValueError:
        typer.echo("错误:所有模式数据缺失,无法出分", err=True)
        raise typer.Exit(1)

    event_zh = "晚霞" if event == "sunset_glow" else "朝霞"
    typer.echo(f"⚡ {day} {event_zh} — {r.city_name}")
    typer.echo(f"火烧云指数: {r.index}/10  置信度: {CONF_ZH[r.confidence]}  分歧: {r.spread}")
    typer.echo("  " + "  ".join(f"{m.split('_')[0].upper()} {s}" for m, s in r.per_model.items()))
    if r.channel_empty:
        typer.echo("警告: 通道数据缺失,评分未含通道透光校验(置信度参考价值打折)")
    typer.echo(f"通道: {r.blocked_points} 点受阻 (系数 {r.channel_factor})  AOD: {r.aod}")
    typer.echo(f"{'日落' if event == 'sunset_glow' else '日出'}: {r.peak.strftime('%H:%M')}  方位 {r.azimuth:.0f}°")
    if not no_llm:
        if r.llm is not None:
            typer.echo(f"AI 修正分: {r.llm.llm_score}/10  {r.llm.analysis}")
            typer.echo(f"风险: {r.llm.risks}")
        else:
            typer.echo("AI 解读暂缺(无凭证或调用失败),以上为纯规则分")


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
        night_points = [fc.at(t) for t in night_hours]
        night_vals = [p.cloud_cover for p in night_points
                      if p and p.cloud_cover is not None]
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


@app.command()
def backfill(
    csv: Path = typer.Option(..., help="清单 CSV: date,city,event,score"),
    config: Path = typer.Option(DEFAULT_CONFIG),
    db: Path = typer.Option(DEFAULT_DB),
    frames_dir: Path = typer.Option(DEFAULT_FRAMES),
):
    """冷启动:清单 → 历史预报快照 + 卫星帧 + 闭环案例(spec 6.1)。"""
    try:
        rows = parse_csv(csv)
    except (ValueError, OSError) as e:
        typer.echo(f"错误:{e}", err=True)
        raise typer.Exit(1)
    cities = load_cities(config)
    conn = _open_db(db)
    client = _make_client()
    ok = 0
    for row in rows:
        if row.city not in cities:
            typer.echo(f"跳过 {row.date}:未知城市 {row.city!r}", err=True)
            continue
        try:
            r = backfill_row(conn, client, row, cities[row.city],
                             frames_dir=frames_dir)
        except httpx.HTTPError as e:
            typer.echo(f"跳过 {row.date}:数据源请求失败({e.__class__.__name__})", err=True)
            continue
        typer.echo(f"✓ {row.date} {row.event} 实际 {row.score} 分"
                   f"(快照 {r.n_models} 模式,卫星帧 {r.n_frames})")
        ok += 1
    typer.echo(f"完成:{ok} 条案例入库(共 {len(rows)} 条)")


@app.command()
def nowcast(
    city: str = typer.Option("beijing"),
    event: str = typer.Option("sunset_glow", help="sunset_glow | sunrise_glow"),
    config: Path = typer.Option(DEFAULT_CONFIG),
    db: Path = typer.Option(DEFAULT_DB),
    frames_dir: Path = typer.Option(DEFAULT_FRAMES),
):
    """实况层:拉 Himawari 帧 → 云量/外推 → 与今日规则分融合(spec 5.4)。"""
    cities = load_cities(config)
    if city not in cities:
        typer.echo(f"错误:未知城市 {city!r},可用: {', '.join(cities)}", err=True)
        raise typer.Exit(1)
    c = cities[city]
    today = date_type.today()
    win = sun_window(c.lat, c.lon, c.timezone, today, event)
    now = datetime.now(timezone.utc)
    minutes_to = (win.peak.astimezone(timezone.utc) - now).total_seconds() / 60
    if minutes_to < -60:
        typer.echo("今日窗口已过,无需临近修正", err=True)
        raise typer.Exit(1)

    conn = _open_db(db)
    row = conn.execute(
        "SELECT id, rule_score FROM cases WHERE date=? AND city=? AND event=?",
        (str(today), city, event)).fetchone()
    if row is None or row[1] is None:
        typer.echo("错误:今日尚无规则分,先运行 skyfire predict", err=True)
        raise typer.Exit(1)
    case_id, rule_score = row

    client = _make_client()
    try:
        ts1 = latest_frame_time(client)
        frame1 = fetch_region(client, "infrared", ts1, c.lat, c.lon)
        ts0 = round_down_10min(ts1 - timedelta(minutes=10))
        frame0 = fetch_region(client, "infrared", ts0, c.lat, c.lon)
    except httpx.HTTPError as e:
        typer.echo(f"错误:卫星数据请求失败({e.__class__.__name__}: {e}),"
                   f"以规则分为准", err=True)
        raise typer.Exit(1)

    if frame1.gray.max() == 0:
        # 瓦片全缺(未发布/超出覆盖):不拿全零图冒充实况,退回纯规则分(spec 8)
        typer.echo(f"🛰  {today} {event} 实况修正 — {c.name}")
        typer.echo("卫星帧全缺(瓦片未发布或超出覆盖),不参与融合,以规则分为准", err=True)
        typer.echo(f"综合分: {rule_score}/10(规则分 {rule_score})")
        return

    age = frame_age_minutes(ts1, now)
    local = box_cloudiness(frame1.gray, frame1.center_px, half=40)
    step_px = max(1, round(100 / km_per_px(frame1.level)))
    if frame0.gray.max() > 0:
        shift = estimate_shift(frame0.gray, frame1.gray)
    else:
        shift = (0, 0)
    frames_ahead = max(0.0, minutes_to) / 10.0
    corridor_pred = extrapolated_corridor(frame1.gray, frame1.center_px,
                                          win.azimuth_deg, step_px, 4,
                                          shift, round(frames_ahead))
    observed = obs_score(local, corridor_pred)
    fused = fuse(rule_score, observed, minutes_to, age)

    frames_dir.mkdir(parents=True, exist_ok=True)
    path = frames_dir / f"{city}_{today}_{event}_{ts1:%H%M}.png"
    Image.fromarray(frame1.gray, mode="L").save(path)
    store.add_satellite_frame(conn, case_id, ts1.isoformat(), "infrared", str(path))

    typer.echo(f"🛰  {today} {event} 实况修正 — {c.name}")
    typer.echo(f"帧时刻: {ts1:%H:%M}Z  帧龄: {age:.0f} 分钟"
               + ("  ⚠️ 超龄,不参与融合" if fused.degraded else ""))
    typer.echo(f"本地云量代理: {local:.0f}%  走廊外推: "
               + " ".join(f"{v:.0f}%" for v in corridor_pred)
               + f"  位移/帧: {shift}")
    typer.echo(f"实况分: {fused.obs}  权重: {fused.weight:.2f}")
    typer.echo(f"综合分: {fused.score}/10(规则分 {rule_score})")
    store.upsert_case(conn, str(today), city, event,
                      rule_score=fused.score, confidence="nowcast", source="auto")


@app.command()
def notify(
    city: str = typer.Option("beijing"),
    event: str = typer.Option("sunset_glow", help="sunset_glow | sunrise_glow"),
    config: Path = typer.Option(DEFAULT_CONFIG),
    db: Path = typer.Option(DEFAULT_DB),
    notify_config: Path = typer.Option(DEFAULT_NOTIFY),
):
    """算一次预测并推送到手机(手动触发一次)。"""
    ncfg = load_notify_config(notify_config)
    if ncfg is None:
        typer.echo(f"错误:推送未配置({notify_config});复制 config/notify.example.yaml "
                   f"为 notify.local.yaml 并填密钥", err=True)
        raise typer.Exit(1)
    cities = load_cities(config)
    if city not in cities:
        typer.echo(f"错误:未知城市 {city!r},可用: {', '.join(cities)}", err=True)
        raise typer.Exit(1)
    conn = _open_db(db)
    client = _make_client()
    try:
        r = compute_prediction(conn, client, cities[city], city, event,
                               date_type.today(), run_llm=True)
    except (httpx.HTTPError, ValueError) as e:
        typer.echo(f"错误:预测失败({e.__class__.__name__}),未推送", err=True)
        raise typer.Exit(1)
    title, body = format_report(r)
    ok = push(title, body, ncfg)
    store.mark_pushed(conn, str(date_type.today()), city, event)
    typer.echo(f"{'✓ 已推送' if ok else '✗ 推送失败(已记录预测)'}: {title}")


@app.command()
def tick(
    config: Path = typer.Option(DEFAULT_CONFIG),
    db: Path = typer.Option(DEFAULT_DB),
    notify_config: Path = typer.Option(DEFAULT_NOTIFY),
):
    """调度入口:到点的城市×天象自动预测+推送(launchd 每 30 分钟调一次)。"""
    ncfg = load_notify_config(notify_config)
    if ncfg is None:
        return  # 未配置推送:静默退出(launchd 频繁调用,不刷错误)
    cities = load_cities(config)
    conn = _open_db(db)
    now = datetime.now(timezone.utc)
    lead = ncfg.get("lead_minutes", DEFAULT_LEAD_MINUTES)
    for city, event in due_events(cities, now, lead_minutes=lead):
        today = str(now.astimezone().date())
        if store.was_pushed(conn, today, city, event):
            continue
        client = _make_client()
        try:
            r = compute_prediction(conn, client, cities[city], city, event,
                                   date_type.today(), run_llm=True)
        except (httpx.HTTPError, ValueError):
            continue  # 单城失败不影响其他(spec 8)
        title, body = format_report(r)
        push(title, body, ncfg)
        store.mark_pushed(conn, today, city, event)
        typer.echo(f"✓ {city} {event}: {title}")


if __name__ == "__main__":
    app()
