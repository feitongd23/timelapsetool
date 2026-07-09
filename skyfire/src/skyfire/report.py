"""预测结果 → 推送标题/正文(纯函数,供 notify/tick 用)。"""
from skyfire.checkpoints import GATE_PP
from skyfire.engine import PredictionResult

_CONF_ZH = {"high": "高", "medium": "中", "low": "低(模式打架)", "degraded": "降级(数据不全)"}


def format_report(r: PredictionResult) -> tuple[str, str]:
    event_zh = "晚霞" if r.event == "sunset_glow" else "朝霞"
    when_zh = "日落" if r.event == "sunset_glow" else "日出"
    title = f"{event_zh} {r.index}/10 — {r.city_name}"
    lines = [
        f"{r.day.year}年{r.day.month}月{r.day.day}日"
        f" {r.city_name}{event_zh}火烧云指数 {r.index}/10",
        f"置信度: {_CONF_ZH.get(r.confidence, r.confidence)}  模式分歧: {r.spread}",
        "  " + "  ".join(f"{m.split('_')[0].upper()} {s}" for m, s in r.per_model.items()),
        f"通道: {r.blocked_points} 点受阻(系数 {r.channel_factor})  AOD: {r.aod}",
        f"{when_zh}: {r.peak.strftime('%H:%M')}  方位 {r.azimuth:.0f}°",
    ]
    if r.channel_empty:
        lines.append("通道数据缺失,置信度参考价值打折")
    if r.llm is not None:
        lines.append(f"AI 修正分: {r.llm.llm_score}/10  {r.llm.analysis}")
        lines.append(f"风险: {r.llm.risks}")
    return title, "\n".join(lines)


def _prob_word(p: float) -> str:
    if p < 20: return "机会渺茫"
    if p < 40: return "机会不大"
    if p < 60: return "值得留意"
    if p < 80: return "机会较大"
    return "大概率有戏"


def _qual_word(q: float) -> str:
    if q < 20: return "即便烧也很弱"
    if q < 40: return "偏弱"
    if q < 60: return "中等"
    if q < 80: return "可观"
    return "可能大烧"


def _burn_level(q: float) -> str:
    """烧云等级,按质量%分档(llm 铁律口径:40 是真烧门槛,100 整片烧透)。"""
    if q < 20: return "不烧"
    if q < 40: return "微烧"
    if q < 60: return "小烧"
    if q < 80: return "中烧"
    if q < 90: return "大烧"
    return "爆烧"


def _fmt_mins(mins: float) -> str:
    return f"{mins / 60:.1f}小时" if mins >= 90 else f"{mins:.0f}分钟"


_CP_ZH = {"c1": "早间首报", "c2": "临近检查点", "c3": "冲刺检查点",
          "gated": "波动补报", "outlook": "明日展望", "manual": "手动"}


def _aod_word(aod) -> str:
    if aod is None: return "数据暂缺"
    if aod < 0.3: return "通透,利于出色"
    if aod < 0.6: return "略有浑浊"
    if aod < 1.0: return "浑浊,颜色会被压淡"
    return "重度浑浊,基本无戏"


_CONF_PLAIN = {"high": "高 — 各家气象模式结论一致",
               "medium": "中 — 模式大体一致",
               "low": "低 — 各家模式结论分歧大,谨慎参考",
               "degraded": "弱 — 数据不全,仅供参考"}


def _date_zh(rec: dict) -> str | None:
    """预测对象日期的年月日串;date 键(YYYY-MM-DD)优先,缺则回退 peak。"""
    d = rec.get("date")
    if d:
        y, m, day = d.split("-")
        return f"{int(y)}年{int(m)}月{int(day)}日"
    peak = rec.get("peak")
    if peak is not None:
        return f"{peak.year}年{peak.month}月{peak.day}日"
    return None


def format_pct_report(rec: dict) -> tuple[str, str]:
    """百分数检查点 → 推送标题/正文(大众化排版,一行一条信息)。

    rec 可选带 seq/minutes_to_peak/prev(engine.run_checkpoint 注入):
    标题标"第N报[等级]",正文标"日落前第N次推送"与较上次的变化;
    概率或质量较上次跳变 ≥GATE_PP 记重大变化(距峰值≤20分钟 → 临近突变)。
    缺这些键时退化为旧版纯数字报文(手工构造 rec 的调用方不受影响)。
    """
    sunset = rec["event"] == "sunset_glow"
    event_zh = "晚霞" if sunset else "朝霞"
    when = "日落" if sunset else "日出"
    level = _burn_level(rec["quality_pct"])
    seq = rec.get("seq")
    mins = rec.get("minutes_to_peak")
    prev = rec.get("prev")
    major = False
    if prev:
        dp = rec["probability_pct"] - prev["probability_pct"]
        dq = rec["quality_pct"] - prev["quality_pct"]
        major = abs(dp) >= GATE_PP or abs(dq) >= GATE_PP
    prefix = ""
    if major:
        prefix = ("🔥临近突变·" if mins is not None and 0 <= mins <= 20
                  else "⚡突变·")
    seq_s = f"第{seq}报" if seq is not None else ""
    title = (f"{prefix}{event_zh}{seq_s}[{level}]"
             f" 概率{rec['probability_pct']:.0f}%"
             f" 质量{rec['quality_pct']:.0f}% — {rec['city_name']}")
    lines = []
    date_zh = _date_zh(rec)
    if date_zh:
        lines.append(f"预测日期: {date_zh}")
    peak = rec.get("peak")
    if peak is not None:
        best = "其后约15分钟" if sunset else "其前约15分钟"
        lines.append(f"{when} {peak.strftime('%H:%M')}(最佳观赏在{best})")
    if seq is not None:
        cp = rec.get("checkpoint", "")
        cp_zh = _CP_ZH.get(cp, cp)
        gen = rec.get("generated_at")
        gen_s = f"({gen:%H:%M}生成)" if gen is not None else ""
        if mins is None:
            lines.append(f"{when}前第{seq}次推送{gen_s} · {cp_zh}")
        elif mins >= 0:
            lines.append(f"{when}前第{seq}次推送{gen_s} · {cp_zh}"
                         f" · 距{when}约{_fmt_mins(mins)}")
        else:
            lines.append(f"第{seq}次推送{gen_s}({when}已过{_fmt_mins(-mins)})"
                         f" · {cp_zh}")
    if prev:
        ref = "上次" + (prev.get("time_local") or "")
        if prev.get("minutes_ago") is not None:
            ref += f"({_fmt_mins(prev['minutes_ago'])}前)"
        delta = (f"概率{prev['probability_pct']:.0f}%"
                 f"→{rec['probability_pct']:.0f}%({dp:+.0f})"
                 f" · 质量{prev['quality_pct']:.0f}%"
                 f"→{rec['quality_pct']:.0f}%({dq:+.0f})")
        head = f"⚠️ 重大变化,较{ref}: " if major else f"较{ref}: "
        lines.append(head + delta)
    lines.append(f"概率 {rec['probability_pct']:.0f}%"
                 f"({_prob_word(rec['probability_pct'])})"
                 f" · 质量 {rec['quality_pct']:.0f}%"
                 f"({_qual_word(rec['quality_pct'])})"
                 f" · 等级 {level}")
    if rec.get("per_model_pct"):
        lines.append("各模式看法(概率/质量): " + "  ".join(
            f"{m.split('_')[0].upper()} {p:.0f}/{q:.0f}"
            for m, (p, q) in rec["per_model_pct"].items()))
    if rec.get("trend"):
        lines.append(f"{rec['city_name']}上空云量: {rec['trend']}")
    if "aod" in rec:
        aod = rec["aod"]
        aod_s = f"{aod}" if aod is not None else "—"
        lines.append(f"空气(气溶胶AOD {aod_s}): {_aod_word(aod)}")
    lines.append(f"可信度: "
                 f"{_CONF_PLAIN.get(rec['confidence'], rec['confidence'])}")
    lines.append(f"物理底分 {rec['rule_score']}/10"
                 f"(按云量·透光通道·降水等硬条件的打分)")
    # 因子过堂表:每个已知致错因子留痕,缺失/修正必须可见(2026-07-10 拍板)
    sheet = rec.get("factor_sheet") or []
    flagged = [f for f in sheet if f.get("status") not in (None, "正常")]
    if flagged:
        lines.append("因子过堂:")
        for f in flagged:
            lines.append(f"· {f['name']}[{f['status']}] {f['note']}")
    if rec.get("llm_status") == "done":
        lines.append(f"解读: {rec['reasoning']}")
        if rec.get("scenario_alt"):
            lines.append(f"另一情景: {rec['scenario_alt']}")
        lines.append(f"风险: {rec['risks']}")
    else:
        lines.append("AI 解读暂缺,以上为基础数据")
    return title, "\n".join(lines)


def _num(v) -> str:
    return "—" if v is None else f"{v:.0f}"


_MODEL_ABBR = {"ecmwf_ifs": "EC", "ecmwf_ifs025": "EC", "gfs_seamless": "GFS",
               "icon_seamless": "ICON", "cma_grapes_global": "CMA"}


def _model_lines(rec: dict) -> list[str]:
    lines = ["各模式(概率/质量 · 高中低云% · 降水):"]
    raw_all = rec.get("per_model_raw") or {}
    for m, (p, q) in rec["per_model_pct"].items():
        name = _MODEL_ABBR.get(m, m.split("_")[0].upper())
        parts = [f"{name} {p:.0f}/{q:.0f}"]
        raw = raw_all.get(m)
        if raw:
            parts.append(f"高{_num(raw.get('cloud_high'))}"
                         f" 中{_num(raw.get('cloud_mid'))}"
                         f" 低{_num(raw.get('cloud_low'))}")
            precip = raw.get("precipitation")
            parts.append(f"雨{precip:.1f}mm" if precip and precip >= 0.1 else "无雨")
        lines.append(" · ".join(parts))
    return lines


def _outlook_section(rec: dict) -> list[str]:
    """明日展望单节:只给质量和概率(用户 2026-07-08:晚9点次日展望只要质量概率)。

    去掉分模型明细/AOD/可信度/解读——那些留给次日到点检查点的详报。
    """
    sunset = rec["event"] == "sunset_glow"
    event_zh = "晚霞" if sunset else "朝霞"
    when = "日落" if sunset else "日出"
    lines = [f"明日{event_zh} {when} {rec['peak'].strftime('%H:%M')}"]
    lines.append(f"概率 {rec['probability_pct']:.0f}% · "
                 f"质量 {rec['quality_pct']:.0f}%({_burn_level(rec['quality_pct'])})")
    return lines


def format_outlook_report(rec_sunrise: dict | None,
                          rec_sunset: dict | None) -> tuple[str, str]:
    """每晚明日展望:朝霞+晚霞双节合推;任一边 None 标数据缺失(spec §4)。"""
    some = rec_sunrise or rec_sunset
    p_sr = f"{rec_sunrise['probability_pct']:.0f}%" if rec_sunrise else "—%"
    p_ss = f"{rec_sunset['probability_pct']:.0f}%" if rec_sunset else "—%"
    title = f"明日展望 朝霞{p_sr} 晚霞{p_ss} — {some['city_name']}"
    lines: list[str] = []
    date_zh = _date_zh(some)
    if date_zh:
        lines.append(f"预测日期: {date_zh}")
    gen = some.get("generated_at")
    if gen is not None:
        lines.append(f"生成时间 {gen:%H:%M}(各天象后续检查点自动更新)")
    for rec, label in ((rec_sunrise, "明日朝霞"), (rec_sunset, "明日晚霞")):
        if rec is None:
            lines.append(f"{label}: 数据缺失(后续检查点自动补上)")
        else:
            lines.extend(_outlook_section(rec))
        lines.append("")
    return title, "\n".join(lines).rstrip()
