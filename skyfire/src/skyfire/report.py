"""预测结果 → 推送标题/正文(纯函数,供 notify/tick 用)。"""
from skyfire.engine import PredictionResult

_CONF_ZH = {"high": "高", "medium": "中", "low": "低(模式打架)", "degraded": "降级(数据不全)"}


def format_report(r: PredictionResult) -> tuple[str, str]:
    event_zh = "晚霞" if r.event == "sunset_glow" else "朝霞"
    when_zh = "日落" if r.event == "sunset_glow" else "日出"
    title = f"{event_zh} {r.index}/10 — {r.city_name}"
    lines = [
        f"{r.day} {r.city_name}{event_zh}火烧云指数 {r.index}/10",
        f"置信度: {_CONF_ZH.get(r.confidence, r.confidence)}  模式分歧: {r.spread}",
        "  " + "  ".join(f"{m.split('_')[0].upper()} {s}" for m, s in r.per_model.items()),
        f"通道: {r.blocked_points} 点受阻(系数 {r.channel_factor})  AOD: {r.aod}",
        f"{when_zh}: {r.peak.strftime('%H:%M')}  方位 {r.azimuth:.0f}°",
    ]
    if r.channel_empty:
        lines.append("⚠️ 通道数据缺失,置信度参考价值打折")
    if r.llm is not None:
        lines.append(f"AI 修正分: {r.llm.llm_score}/10  {r.llm.analysis}")
        lines.append(f"风险: {r.llm.risks}")
    return title, "\n".join(lines)


def format_pct_report(rec: dict) -> tuple[str, str]:
    """百分数检查点 → 推送标题/正文(spec §3)。rec 为 run_checkpoint 返回。"""
    event_zh = "晚霞" if rec["event"] == "sunset_glow" else "朝霞"
    title = (f"{event_zh} 概率{rec['probability_pct']:.0f}%"
             f" 质量{rec['quality_pct']:.0f}% — {rec['city_name']}")
    lines = [
        f"{rec['date']} {rec['city_name']}{event_zh}"
        f"[{rec['checkpoint'].upper()}] 概率 {rec['probability_pct']:.0f}%"
        f" 质量 {rec['quality_pct']:.0f}%",
        f"置信: {_CONF_ZH.get(rec['confidence'], rec['confidence'])}"
        f"  规则分 {rec['rule_score']}",
    ]
    if rec.get("per_model_pct"):
        lines.append("各模式(概率/质量): " + "  ".join(
            f"{m.split('_')[0].upper()} {p:.0f}/{q:.0f}"
            for m, (p, q) in rec["per_model_pct"].items()))
    if rec.get("trend"):
        lines.append(f"云量趋势: {rec['trend']}")
    if rec.get("llm_status") == "done":
        lines.append(f"解读: {rec['reasoning']}")
        lines.append(f"风险: {rec['risks']}")
    else:
        lines.append("AI 解读待补(无凭证或调用失败),以上为免费层基线")
    return title, "\n".join(lines)
