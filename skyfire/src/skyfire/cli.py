"""skyfire CLI:predict / cloudsea / backtest / init-db / nowcast / backfill。"""
import shutil
from datetime import date as date_type, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
import typer
from PIL import Image

from skyfire import store
from skyfire.analyze import build_case_card, format_trajectory
from skyfire.backfill import backfill_row, parse_csv
from skyfire.backtest import pct_report, spearman
from skyfire.checkpoints import due_checkpoint
from skyfire.cloudiness import box_cloudiness
from skyfire.config import load_cities
from skyfire.drift import estimate_shift, extrapolated_corridor
from skyfire.engine import compute_prediction, run_checkpoint
from skyfire.himawari import frame_age_minutes
from skyfire.himawari_hsd import (CROP_BBOX, download_segments, fetch_case_frames,
                                  latest_slot, observer_cloudiness,
                                  round_down_10min, segments_for)
from skyfire.llm import explain
from skyfire.nowcast import fuse, obs_score
from skyfire.notifyconf import load_notify_config
from skyfire.openmeteo import fetch_point_forecast
from skyfire.push import push
from skyfire.render import load_b13_region
from skyfire.report import format_outlook_report, format_pct_report, format_report
from skyfire.scoring.cloudsea import CloudSeaInputs, cloud_sea_score
from skyfire.skill import (MIN_N, per_model_errors, recomputed_consensus,
                           skill_table, weights_from_skill)
from skyfire.suntimes import nearest_iso_hour, sun_window

app = typer.Typer(help="火烧云/云海预测助手")

DEFAULT_CONFIG = Path(__file__).parent.parent.parent / "config" / "cities.yaml"
DEFAULT_DB = Path(__file__).parent.parent.parent / "data" / "skyfire.db"
DEFAULT_FRAMES = Path(__file__).parent.parent.parent / "data" / "frames"
DEFAULT_NOTIFY = Path(__file__).parent.parent.parent / "config" / "notify.local.yaml"
DEFAULT_WECHAT = Path(__file__).parent.parent.parent / "config" / "wechat.local.yaml"
DEFAULT_GRIDMAPS = Path(__file__).parent.parent.parent / "data" / "gridmaps"
DEFAULT_PHOTOS = Path(__file__).parent.parent.parent / "data" / "photos"

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
        iso_dawn = nearest_iso_hour(win.peak)
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
    pct: bool = typer.Option(False, "--pct", help="百分数回测(质量%/概率% vs 实际,spec 里程碑 4)"),
    recompute: bool = typer.Option(False, "--recompute",
                                   help="用当前打分器从快照重算规则分再回测(打分器改动后验证用)"),
):
    """规则分 vs 实际打分的 Spearman 相关性(spec 9 首要验收)。"""
    conn = _open_db(db)
    if recompute:
        rows = recomputed_consensus(store.scored_cases_with_snapshots(conn, city))
        if len(rows) < 3:
            typer.echo(f"可重算案例不足({len(rows)} 条,需 ≥3)", err=True)
            raise typer.Exit(1)
        try:
            rho = spearman([x["rule_score"] for x in rows],
                           [x["actual_score"] for x in rows])
        except ValueError:
            typer.echo("无法计算相关性:重算分数无区分度", err=True)
            raise typer.Exit(1)
        typer.echo(f"重算回测(当前打分器): {len(rows)} 条, Spearman ρ = {rho:.3f}")
        return
    if pct:
        rows = conn.execute(
            """SELECT p.quality_pct, p.probability_pct, c.actual_score
               FROM cases c JOIN predictions p
                 ON p.date=c.date AND p.city=c.city AND p.event=c.event
               WHERE c.city=? AND c.actual_score IS NOT NULL
                 AND p.id = (SELECT MAX(id) FROM predictions
                             WHERE date=c.date AND city=c.city AND event=c.event)
            """, (city,)).fetchall()
        r = pct_report([{"quality_pct": q, "probability_pct": pr,
                         "actual_score": a} for q, pr, a in rows])
        rho_disp = r["spearman_quality"] if r["spearman_quality"] is None else round(r["spearman_quality"], 3)
        typer.echo(f"百分数回测: {r['n']} 条  质量%↔实际 Spearman ρ={rho_disp}")
        typer.echo(f"命中率 {r['hit_rate']}  精确率 {r['precision']}"
                   f"  召回 {r['recall']}(报烧=概率≥50,真烧=实际≥6)")
        return
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


@app.command()
def modelskill(
    city: str = typer.Option("beijing"),
    db: Path = typer.Option(DEFAULT_DB),
):
    """四模式置信账本:按闭环案例重算各模式历史准确度,落 model_skill 表。

    零 API 调用;打分器改动后重跑即可全量刷新。每模式样本 ≥8 后,
    预测共识自动从中位数切换为按 1/(MAE+5) 加权平均。
    """
    conn = _open_db(db)
    cases = store.scored_cases_with_snapshots(conn, city)
    errors = per_model_errors(cases)
    if not errors:
        typer.echo("无可评估数据:需要闭环案例(actual_score)+ forecast_snapshots", err=True)
        raise typer.Exit(1)
    rows = skill_table(errors)
    store.replace_model_skill(conn, rows)
    typer.echo(f"模式置信账本(基于 {len(cases)} 条闭环案例;"
               f"MAE=|该模式单独预测质量% - 实际得分×10| 的均值):")
    for i, r in enumerate(rows, 1):
        lean = "常报高" if r["bias"] > 3 else ("常报低" if r["bias"] < -3 else "无明显偏向")
        typer.echo(f"  {i}. {r['model']}: 样本{r['n']}  MAE {r['mae']}"
                   f"  偏差 {r['bias']:+.1f}({lean})")
    weights = weights_from_skill(rows, [r["model"] for r in rows])
    if weights is not None:
        typer.echo("共识加权: 已启用(1/(MAE+5),最准的模式话语权最大)")
    else:
        least = min(r["n"] for r in rows)
        typer.echo(f"共识加权: 未启用(需每模式 ≥{MIN_N} 样本,当前最少 {least});"
                   f"启用前共识用中位数")


@app.command()
def cloudmap(
    city: str = typer.Option("beijing"),
    event: str = typer.Option("sunset_glow", help="sunset_glow | sunrise_glow"),
    date: str = typer.Option(None, help="YYYY-MM-DD,默认今天;过去日期走历史存档"),
    config: Path = typer.Option(DEFAULT_CONFIG),
    out_dir: Path = typer.Option(DEFAULT_GRIDMAPS),
):
    """预报云图:峰值小时高/中/低云三联热图(亮=云多,西=左)。"""
    from skyfire.gridmap import (DEFAULT_BBOX, DEFAULT_STEP, fetch_cloud_grid,
                                 grid_points, render_grid_png)
    cities = load_cities(config)
    if city not in cities:
        typer.echo(f"错误:未知城市 {city!r},可用: {', '.join(cities)}", err=True)
        raise typer.Exit(1)
    c = cities[city]
    day = _parse_date(date, date_type.today())
    win = sun_window(c.lat, c.lon, c.timezone, day, event)
    iso_hour = nearest_iso_hour(win.peak)
    pts = grid_points(DEFAULT_BBOX, DEFAULT_STEP)
    n_cols = len({lon for _, lon in pts})
    n_rows = len(pts) // n_cols
    client = _make_client()
    hist = day < date_type.today()
    try:
        grid = fetch_cloud_grid(client, pts, n_rows, n_cols, c.timezone, iso_hour,
                                date=str(day) if hist else None)
    except httpx.HTTPError as e:
        typer.echo(f"错误:Open-Meteo 请求失败({e.__class__.__name__}: {e})", err=True)
        raise typer.Exit(1)
    out = render_grid_png(grid, out_dir / f"{city}_{day}_{event}_clouds.png",
                          label=f"{day} {win.peak:%H:%M}")
    typer.echo(f"预报云图: {out}")


@app.command()
def analyze(
    date: str = typer.Option(..., help="案例日期 YYYY-MM-DD"),
    city: str = typer.Option("beijing"),
    event: str = typer.Option("sunset_glow"),
    db: Path = typer.Option(DEFAULT_DB),
    no_llm: bool = typer.Option(False, "--no-llm"),
    save: bool = typer.Option(False, "--save", help="把 LLM 解读存为案例笔记"),
    note: str = typer.Option(None, "--note", help="追加一条用户笔记并退出"),
):
    """案例复盘:案例卡 + 云图 LLM 解读(为什么是这个分),沉淀经验笔记。"""
    conn = _open_db(db)
    case = store.case_by_key(conn, date, city, event)
    if case is None:
        typer.echo(f"错误:无案例 {date} {city} {event}(先 backfill/打分)", err=True)
        raise typer.Exit(1)
    if note:
        store.add_case_note(conn, case["id"], "user", note)
        typer.echo("✓ 已记用户笔记")
        return
    snaps = store.get_snapshots(conn, case["id"])
    frames = store.get_frames(conn, case["id"])
    notes = store.get_case_notes(conn, case["id"])
    card = build_case_card(case, snaps, frames, notes)
    typer.echo(card)
    if no_llm:
        return
    paths = [Path(f["path"]) for f in frames if Path(f["path"]).exists()]
    result = explain(card, paths)
    if result is None:
        typer.echo("\nAI 解读暂缺(无凭证或调用失败)", err=True)
        return
    typer.echo("\n===== AI 复盘 =====\n" + result)
    if save:
        store.add_case_note(conn, case["id"], "llm", result)
        typer.echo("✓ 已存为案例笔记")


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
    cache = frames_dir / "hsd_cache"
    lon_mid = (CROP_BBOX[0] + CROP_BBOX[2]) / 2
    segs = segments_for(CROP_BBOX[1], CROP_BBOX[3], lon_mid)
    try:
        ts1 = latest_slot(client, now)
        if ts1 is None:
            raise httpx.HTTPError("近 1 小时无卫星档")
        dats1 = download_segments(client, ts1, "B13", segs, cache)
        ts0 = round_down_10min(ts1 - timedelta(minutes=10))
        dats0 = download_segments(client, ts0, "B13", segs, cache)
    except httpx.HTTPError as e:
        typer.echo(f"错误:卫星数据请求失败({e.__class__.__name__}: {e}),"
                   f"以规则分为准", err=True)
        raise typer.Exit(1)
    if not dats1:
        typer.echo(f"🛰  {today} {event} 实况修正 — {c.name}")
        typer.echo("卫星帧全缺(归档未落/超出覆盖),不参与融合,以规则分为准", err=True)
        typer.echo(f"综合分: {rule_score}/10(规则分 {rule_score})")
        return
    frame1 = load_b13_region(dats1, CROP_BBOX, c.lat, c.lon)
    age = frame_age_minutes(ts1, now)
    local = box_cloudiness(frame1.gray, frame1.center_px, half=40)
    step_px = max(1, round(100 / frame1.km_px))
    if dats0:
        frame0 = load_b13_region(dats0, CROP_BBOX, c.lat, c.lon)
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
    store.add_satellite_frame(conn, case_id, ts1.isoformat(), "ir", str(path))

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
    """调度入口:检查点驱动的自动预测+推送(launchd 每 30 分钟调一次)。

    每个城市×天象×(今天/明天)判断是否到点(c1/c2/c3);到点未跑过则跑一版并推送;
    检查点之间(c1 已跑、峰值未到)用免费层门控,概率摆动超 15pp 才补跑一版。
    """
    ncfg = load_notify_config(notify_config)
    if ncfg is None:
        return  # 未配置推送:静默退出(launchd 频繁调用,不刷错误)
    cities = load_cities(config)
    conn = _open_db(db)
    now = datetime.now(timezone.utc)
    for city_key, c in cities.items():
        now_local = now.astimezone(ZoneInfo(c.timezone))
        for event in ("sunset_glow", "sunrise_glow"):
            for day_offset in (0, 1):
                day = (now_local + timedelta(days=day_offset)).date()
                win = sun_window(c.lat, c.lon, c.timezone, day, event)
                cp = due_checkpoint(now_local, win.peak, event)
                pred_date = str(win.peak.date())
                client = _make_client()
                try:
                    if cp is not None:
                        if store.has_checkpoint(conn, pred_date, city_key,
                                                event, cp):
                            break  # 该检查点已跑过:该 event 已处理,不看另一天
                        rec = run_checkpoint(conn, client, c, city_key, event,
                                             win.peak.date(), cp)
                        # 朝霞 C1 时刻 = 每晚明日展望:同跑明日晚霞 outlook,
                        # 合成一条推送(spec §2 双跑合推,用户拍板)
                        if cp == "c1" and event == "sunrise_glow":
                            rec_outlook = None
                            if not store.has_checkpoint(conn, pred_date,
                                                        city_key, "sunset_glow",
                                                        "outlook"):
                                try:
                                    rec_outlook = run_checkpoint(
                                        conn, client, c, city_key,
                                        "sunset_glow", win.peak.date(),
                                        "outlook")
                                except (httpx.HTTPError, ValueError):
                                    rec_outlook = None  # 缺一半照推;本晚不补跑,明日11:00晚霞C1自然补上
                            title, body = format_outlook_report(rec,
                                                                rec_outlook)
                            push(title, body, ncfg)
                            typer.echo(f"✓ {city_key} outlook {title}")
                            break
                    else:
                        # 检查点之间:c1 之后到峰值前,免费层门控
                        c1_done = store.has_checkpoint(conn, pred_date,
                                                       city_key, event, "c1")
                        to_peak = (win.peak - now_local).total_seconds() / 60
                        if not (c1_done and 0 < to_peak):
                            continue
                        rec = run_checkpoint(conn, client, c, city_key, event,
                                             win.peak.date(), "gated", gate=True)
                    if rec is None:
                        continue
                    title, body = format_pct_report(rec)
                    push(title, body, ncfg)
                    typer.echo(f"✓ {city_key} {event} [{rec['checkpoint']}]"
                               f" {title}")
                except (httpx.HTTPError, ValueError):
                    continue  # 单城失败不影响其他(spec 8)
                break  # 该 event 已按其中一天处理,不再看另一天


@app.command()
def checkpoint(
    cp: str = typer.Option("manual", help="c1|c2|c3|gated|manual|outlook"),
    city: str = typer.Option("beijing"),
    event: str = typer.Option("sunset_glow"),
    date: str = typer.Option(None, help="YYYY-MM-DD,默认今天"),
    config: Path = typer.Option(DEFAULT_CONFIG),
    db: Path = typer.Option(DEFAULT_DB),
):
    """手动跑一个预测检查点(调试/补跑)。"""
    cities = load_cities(config)
    if city not in cities:
        typer.echo(f"错误:未知城市 {city!r}", err=True)
        raise typer.Exit(1)
    day = _parse_date(date, date_type.today())
    conn = _open_db(db)
    rec = run_checkpoint(conn, _make_client(), cities[city], city, event,
                         day, cp)
    if rec is None:
        typer.echo("门控未触发,无更新")
        return
    title, body = format_pct_report(rec)
    typer.echo(title)
    typer.echo(body)


@app.command()
def latest(
    city: str = typer.Option("beijing"),
    db: Path = typer.Option(DEFAULT_DB),
    limit: int = typer.Option(6, help="显示最近几条"),
):
    """查看最近的预测记录(纯读库,零 API 调用)。"""
    conn = _open_db(db)
    rows = store.recent_predictions(conn, city, limit=limit)
    if not rows:
        typer.echo("暂无预测记录")
        return
    for r in rows:
        event_zh = "晚霞" if r["event"] == "sunset_glow" else "朝霞"
        line = (f"{r['date']} {event_zh} [{r['checkpoint']}]"
                f" 概率{r['probability_pct']:.0f}%"
                f" 质量{r['quality_pct']:.0f}%"
                f" ({r['llm_status']} {r['created_at']})")
        typer.echo(line)
        if r["llm_status"] == "done" and r["reasoning"]:
            typer.echo(f"  解读: {r['reasoning']}")


@app.command()
def serve(
    host: str = typer.Option("0.0.0.0", help="0.0.0.0=局域网可访问"),
    port: int = typer.Option(8000),
    config: Path = typer.Option(DEFAULT_CONFIG),
    db: Path = typer.Option(DEFAULT_DB),
    wechat_config: Path = typer.Option(DEFAULT_WECHAT),
):
    """起小程序只读 API(uvicorn;自用局域网,鉴权=微信登录token)。"""
    import uvicorn

    from skyfire.api import create_app
    api = create_app(db_path=db, config_path=config, wechat_path=wechat_config)
    typer.echo(f"skyfire api → http://{host}:{port}(开发者工具用 127.0.0.1,"
               f"真机用本机局域网 IP)")
    uvicorn.run(api, host=host, port=port)


def _ensure_case_frames(conn, client, case_id: int, city, city_key: str,
                        event: str, day) -> int:
    """反馈闭环:该案例还没有卫星帧则回填(尽力),返回新增帧数。"""
    if store.get_frames(conn, case_id):
        return 0
    win = sun_window(city.lat, city.lon, city.timezone, day,
                     "sunrise_glow" if event == "cloud_sea" else event)
    peak_utc = win.peak.astimezone(timezone.utc)
    prefix = f"{city_key}_{day}_{event}"
    saved = 0
    for ts, ch, path in fetch_case_frames(
            client, peak_utc, DEFAULT_FRAMES, prefix=prefix, event=event,
            lat=city.lat, lon=city.lon, azimuth_deg=win.azimuth_deg):
        store.add_satellite_frame(conn, case_id, ts.isoformat(), ch, str(path))
        saved += 1
    pct = observer_cloudiness(client, peak_utc, event, city.lat, city.lon)
    if pct is not None:
        store.set_sat_cloud(conn, case_id, pct)
    return saved


@app.command()
def feedback(
    date: str = typer.Option(..., help="案例日期 YYYY-MM-DD"),
    city: str = typer.Option("beijing"),
    event: str = typer.Option("sunset_glow"),
    score: float = typer.Option(None, help="实际得分 0-10"),
    photo: Path = typer.Option(None, help="实拍照片路径"),
    wrong: bool = typer.Option(False, "--wrong", help="仅标记'预报不准'"),
    config: Path = typer.Option(DEFAULT_CONFIG),
    db: Path = typer.Option(DEFAULT_DB),
    photos_dir: Path = typer.Option(DEFAULT_PHOTOS),
):
    """反馈闭环:落实际得分/照片 → 自动复盘写经验笔记(spec §5)。"""
    if score is None and photo is None and not wrong:
        typer.echo("错误:至少给 --score / --photo / --wrong 之一", err=True)
        raise typer.Exit(1)
    cities = load_cities(config)
    if city not in cities:
        typer.echo(f"错误:未知城市 {city!r}", err=True)
        raise typer.Exit(1)
    c = cities[city]
    day = _parse_date(date, None)
    conn = _open_db(db)
    case = store.case_by_key(conn, date, city, event)
    if case is None:
        cid = store.upsert_case(conn, date, city, event, rule_score=None,
                                confidence=None, source="feedback")
    else:
        cid = case["id"]
    if score is not None:
        store.set_actual_score(conn, cid, score)
    photo_saved = None
    if photo is not None:
        photos_dir.mkdir(parents=True, exist_ok=True)
        stem = f"{city}_{date}_{event}"
        photo_saved = photos_dir / f"{stem}{photo.suffix}"
        n = 2
        while photo_saved.exists():  # 同案例多张实拍:编号避免互相覆盖
            photo_saved = photos_dir / f"{stem}_{n}{photo.suffix}"
            n += 1
        shutil.copy(photo, photo_saved)
        conn.execute("INSERT INTO photos (case_id, score, path) VALUES (?,?,?)",
                     (cid, score, str(photo_saved)))
        conn.commit()
    typer.echo(f"✓ 已记录反馈: {date} {event}"
               + (f" 实际 {score} 分" if score is not None else " (预报不准)"))

    client = _make_client()
    n = _ensure_case_frames(conn, client, cid, c, city, event, day)
    if n:
        typer.echo(f"✓ 已补当日卫星帧 {n} 张")
    case = store.case_by_key(conn, date, city, event)
    card = build_case_card(case, store.get_snapshots(conn, cid),
                           store.get_frames(conn, cid),
                           store.get_case_notes(conn, cid))
    card += "\n\n" + format_trajectory(store.predictions_for(conn, date,
                                                             city, event))
    if wrong and score is None:
        card += "\n\n(用户反馈:预报不准,实际得分未知)"
    # 实拍照片(含本案例历史已存的)排在卫星帧前:explain 只取前 6 张,
    # 实拍是 ground truth 不能被帧挤掉
    photo_paths = [Path(p) for (p,) in conn.execute(
        "SELECT path FROM photos WHERE case_id=?", (cid,)).fetchall()
        if Path(p).exists()]
    frame_paths = [Path(f["path"]) for f in store.get_frames(conn, cid)
                   if Path(f["path"]).exists()]
    result = explain(card, photo_paths + frame_paths)
    if result is None:
        typer.echo("AI 复盘待补(无凭证或调用失败),稍后 skyfire catchup 补跑")
        return
    store.add_case_note(conn, cid, "llm", result)
    typer.echo("===== AI 复盘 =====\n" + result)


@app.command()
def catchup(
    config: Path = typer.Option(DEFAULT_CONFIG),
    db: Path = typer.Option(DEFAULT_DB),
):
    """补跑 pending:闭环案例的复盘笔记;过期 pending 预测标 skipped(spec §4)。"""
    conn = _open_db(db)
    done = 0
    for case in store.closed_cases_without_llm_note(conn):
        cid = case["id"]
        full = store.case_by_key(conn, case["date"], case["city"], case["event"])
        card = build_case_card(full, store.get_snapshots(conn, cid),
                               store.get_frames(conn, cid),
                               store.get_case_notes(conn, cid))
        card += "\n\n" + format_trajectory(
            store.predictions_for(conn, case["date"], case["city"], case["event"]))
        paths = [Path(f["path"]) for f in store.get_frames(conn, cid)
                 if Path(f["path"]).exists()]
        result = explain(card, paths)
        if result is None:
            typer.echo(f"跳过 {case['date']} {case['event']}(LLM 不可用)")
            continue
        store.add_case_note(conn, cid, "llm", result)
        done += 1
        typer.echo(f"✓ 复盘 {case['date']} {case['event']}")
    today = str(date_type.today())
    for p in store.pending_predictions(conn):
        if p["date"] < today:
            store.set_prediction_llm(conn, p["id"], "skipped")
            typer.echo(f"· {p['date']} {p['event']} [{p['checkpoint']}]"
                       f" 过期 pending → skipped")
    typer.echo(f"完成:补复盘 {done} 条")


if __name__ == "__main__":
    app()
