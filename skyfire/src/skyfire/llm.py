"""Claude 经验层解读(spec 5.5)。

- 模型 claude-opus-4-8,adaptive thinking,多模态直接看卫星帧
- 任何失败(无凭证/网络/解析)→ 返回 None,上层退回纯规则分(spec 8)
- 不要因 ANTHROPIC_API_KEY 未设而预先拒绝:零参 Anthropic() 还会解析
  ANTHROPIC_AUTH_TOKEN 与 `ant auth login` 档案,以实际调用结果为准
"""
import base64
import json
import re
from dataclasses import dataclass
from pathlib import Path

MODEL = "claude-opus-4-8"
MAX_IMAGES = 3

_SYSTEM = (
    "你是火烧云/云海预测助手的资深预报员。规则模型已给出基础分;"
    "你的职责是结合历史相似案例与卫星红外图,给出修正分与简短解读。"
    "只输出 JSON:{\"llm_score\": 0-10 的数字, \"analysis\": 两三句中文解读,"
    "引用最相似案例的日期与结果, \"risks\": 一句最大风险}。不要输出其他文字。"
)


@dataclass
class LlmResult:
    llm_score: float
    analysis: str
    risks: str


def build_content(today: dict, similar: list[dict], frame_paths: list[Path]) -> list[dict]:
    lines = [
        f"日期 {today['date']} 天象 {today['event']} 规则分 {today['rule_score']}"
        f"(置信度 {today['confidence']})",
        f"今日因子: {json.dumps(today['payload'], ensure_ascii=False)}",
        "历史相似案例(按相似度排序):",
    ]
    for c in similar:
        lines.append(f"- {c['date']} 实际 {c['actual_score']} 分 距离 {c['distance']}"
                     f" 因子 {json.dumps(c.get('payload', {}), ensure_ascii=False)}")
        if c.get("note"):
            lines.append(f"  经验笔记: {c['note'][:120]}")
    if not similar:
        lines.append("- (暂无闭环案例)")
    content: list[dict] = [{"type": "text", "text": "\n".join(lines)}]
    for p in frame_paths[:MAX_IMAGES]:
        data = base64.standard_b64encode(Path(p).read_bytes()).decode()
        content.append({"type": "image",
                        "source": {"type": "base64", "media_type": "image/png",
                                   "data": data}})
    if frame_paths:
        content.append({"type": "text",
                        "text": "以上为窗口前的红外卫星帧(时间从近到远),云顶越冷越亮。"})
    return content


def interpret(today: dict, similar: list[dict], frame_paths: list[Path],
              client=None) -> LlmResult | None:
    try:
        if client is None:
            import anthropic
            client = anthropic.Anthropic()
        resp = client.messages.create(
            model=MODEL,
            max_tokens=2000,
            thinking={"type": "adaptive"},
            system=_SYSTEM,
            messages=[{"role": "user",
                       "content": build_content(today, similar, frame_paths)}],
        )
        text = next((b.text for b in resp.content if b.type == "text"), "")
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if not m:
            return None
        data = json.loads(m.group(0))
        score = float(data["llm_score"])
        if not 0 <= score <= 10:
            return None
        return LlmResult(llm_score=score, analysis=str(data.get("analysis", "")),
                         risks=str(data.get("risks", "")))
    except Exception:
        return None


_EXPLAIN_SYSTEM = (
    "你是资深火烧云预报员。给你一条已知实际得分的历史案例卡与当天卫星云图"
    "(红外:云顶越冷越亮;可见光:看纹理)。请解释为什么这天是这个分,"
    "按五段输出:通道/云幕/大气/卫星形态/结论。判读口径:透光通道是否被"
    "低云堵、云幕是否中高云带破口、空气是否通透、正在降水否决但雨后初晴是"
    "利好。若预报与实际背离,点名哪一因子骗了预报。只输出这五段中文,"
    "每段一两句。"
)


MODEL_FAST = "claude-haiku-4-5-20251001"   # 日常检查点
MODEL_DEEP = "claude-sonnet-5"             # 疑难升级(spec §4)

_PREDICT_SYSTEM = (
    "你是资深火烧云预报员。给你免费层数据(多模式预报/规则分/卫星实测与"
    "外推云量/趋势)、相似历史案例及经验笔记、当天判读云图。判读口径:"
    "透光通道是否被低云堵(高云盖顶不算堵)、云幕是否连贯成片的中高云带破口"
    "(零碎小块不算画布)、临近时燃烧时刻云量以卫星实测/外推为准,但距燃烧"
    "还有数小时时(看 hours_to_peak)短时外推代表不了届时云况,以预报趋势"
    "为主;预报有降水时警惕:红外会低估暖顶雨云、雨系抵达会让当前实测失真,"
    "正在降水否决、雨后初晴利好;空气与湿度压色。只输出 JSON:"
    '{"probability_pct": 0-100, "quality_pct": 0-100,'
    ' "reasoning": 两三句中文, "risks": 一句最大风险,'
    ' "confidence": "high|medium|low"}'
)


def predict_pct(payload: dict, similar: list[dict], frame_paths: list[Path],
                model: str = MODEL_FAST, client=None) -> dict | None:
    """检查点预测:免费层+案例+云图 → 百分数 JSON。失败静默 None(spec 8)。"""
    try:
        if client is None:
            import anthropic
            client = anthropic.Anthropic()
        lines = [f"免费层数据: {json.dumps(payload, ensure_ascii=False)}",
                 "历史相似案例(含经验笔记):"]
        for c in similar:
            lines.append(f"- {c['date']} 实际 {c['actual_score']} 分"
                         f" 因子 {json.dumps(c.get('payload', {}), ensure_ascii=False)}")
            if c.get("note"):
                lines.append(f"  经验笔记: {c['note'][:120]}")
        if not similar:
            lines.append("- (暂无)")
        content: list[dict] = [{"type": "text", "text": "\n".join(lines)}]
        for p in frame_paths[:6]:
            data = base64.standard_b64encode(Path(p).read_bytes()).decode()
            content.append({"type": "image",
                            "source": {"type": "base64", "media_type": "image/png",
                                       "data": data}})
        kwargs = {}
        if not model.startswith("claude-haiku"):
            kwargs["thinking"] = {"type": "adaptive"}  # Haiku 4.5 不支持 adaptive
        resp = client.messages.create(
            model=model, max_tokens=1500, system=_PREDICT_SYSTEM,
            messages=[{"role": "user", "content": content}], **kwargs)
        text = next((b.text for b in resp.content if b.type == "text"), "")
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if not m:
            return None
        d = json.loads(m.group(0))
        prob, qual = float(d["probability_pct"]), float(d["quality_pct"])
        if not (0 <= prob <= 100 and 0 <= qual <= 100):
            return None
        return {"probability_pct": prob, "quality_pct": qual,
                "reasoning": str(d.get("reasoning", "")),
                "risks": str(d.get("risks", "")),
                "confidence": str(d.get("confidence", "medium"))}
    except Exception:
        return None


def explain(card_md: str, frame_paths: list[Path], client=None) -> str | None:
    """案例复盘解读(analyze 命令用);失败静默 → None(spec 8)。"""
    try:
        if client is None:
            import anthropic
            client = anthropic.Anthropic()
        content: list[dict] = [{"type": "text", "text": card_md}]
        for p in frame_paths[:6]:
            data = base64.standard_b64encode(Path(p).read_bytes()).decode()
            content.append({"type": "image",
                            "source": {"type": "base64", "media_type": "image/png",
                                       "data": data}})
        resp = client.messages.create(
            model=MODEL, max_tokens=2000, thinking={"type": "adaptive"},
            system=_EXPLAIN_SYSTEM,
            messages=[{"role": "user", "content": content}],
        )
        text = next((b.text for b in resp.content if b.type == "text"), "")
        return text.strip() or None
    except Exception:
        return None
