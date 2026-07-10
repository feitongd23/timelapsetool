"""Claude 经验层解读(spec 5.5)。

- 模型 claude-opus-4-8,adaptive thinking,多模态直接看卫星帧
- 任何失败(无凭证/网络/解析)→ 返回 None,上层退回纯规则分(spec 8)
- 不要因 ANTHROPIC_API_KEY 未设而预先拒绝:零参 Anthropic() 还会解析
  ANTHROPIC_AUTH_TOKEN 与 `ant auth login` 档案,以实际调用结果为准
"""
import base64
import json
import re
import sys
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
    "利好。评分铁律:地平线附近一条橙色带+云剪影只是普通日落底色,不算烧(质量低于40);真正的烧=云底大面积被染成橙红,满分是整片云幕烧透。若预报与实际背离,点名哪一因子骗了预报。只输出这五段中文,"
    "每段一两句。"
)


MODEL_FAST = "claude-haiku-4-5-20251001"   # 日常检查点
MODEL_DEEP = "claude-sonnet-5"             # 疑难升级(spec §4)

_RULEBOOK_PATH = Path(__file__).parent / "rules" / "rulebook.md"
_rulebook_cache: str | None = None


def _rulebook() -> str:
    """规则表注入文本(2026-07-10 用户拍板:四类知识蒸馏成一张表,每次预测
    强制全表过堂,不再靠 RAG 抽相似案例碰运气)。

    注入时剔除"来源"行(出处审计留在文件里)与雾/彩虹两节(火烧云预测
    用不上,省 token)。缺文件降级为空串。
    """
    global _rulebook_cache
    if _rulebook_cache is None:
        try:
            full = _RULEBOOK_PATH.read_text(encoding="utf-8")
        except OSError:
            _rulebook_cache = ""
            return _rulebook_cache
        lines, skip = [], False
        for ln in full.splitlines():
            if ln.startswith("## "):
                skip = ln[3:].strip() in ("平流雾云海", "彩虹")
            if skip or ln.lstrip().startswith("来源:"):
                continue
            lines.append(ln)
        _rulebook_cache = "\n".join(lines)
    return _rulebook_cache


# 强制逐因子表态的七项(漏一项=输出无效重来;规则 llm-factor-roll)
FACTOR_KEYS = ("卫星实况", "画布", "透光通道", "气溶胶", "降水",
               "模式分歧", "外推可信度")


def _predict_system() -> str:
    return (
        "你是资深火烧云预报员。给你免费层数据(多模式预报/规则分/卫星实测与"
        "外推云量/趋势/因子过堂表 factor_sheet/实况元信息 sat_meta)、相似历史"
        "案例及经验笔记、当天判读云图(可能含红外与可见光两帧)。"
        "下面是必须全表过堂的预测规则表——每条相关规则都要核对,与输入矛盾时"
        "指出来;factor_sheet 里标'满盖修正/缺失/硬分歧/平流预警'的条目是"
        "代码层已触发的硬规则,禁止用被修正前的原始数字推理:\n\n"
        + _rulebook() +
        "\n补充口径:免费层数据中的 per_model_raw 是各气象模式对燃烧时刻"
        "高/中/低云量%与降水mm的原始预报——用它判断模式间分歧,任一模式报降水"
        "时提高雨险警惕。措辞面向大众,提及地点一律用城市名(如'北京上空'),"
        "不要说'红点/十字/标记处'等图上记号,不用专业缩写。"
        "baseline 数字仅是规则参考,与实况/形态矛盾时以你的判断为准,"
        "但对 factor_sheet 的硬规则结论(满盖修正后的云量、分歧仲裁后的"
        "有效规则分)只能引用不能推翻。"
        "只输出 JSON(factors 七项全部必填,每项一句中文,写明该因子今天"
        "利好/利空/缺失及依据):"
        '{"probability_pct": 0-100, "quality_pct": 0-100,'
        ' "factors": {"卫星实况": 一句, "画布": 一句, "透光通道": 一句,'
        ' "气溶胶": 一句, "降水": 一句, "模式分歧": 一句, "外推可信度": 一句},'
        ' "scenario_alt": 模式硬分歧时另一情景一句否则空串,'
        ' "rules_applied": [触发的规则id],'
        ' "reasoning": 两三句中文, "risks": 一句最大风险,'
        ' "confidence": "high|medium|low"}'
    )


def _validate_predict(d: dict) -> tuple[dict | None, str | None]:
    """预测 JSON 的完备性校验:七因子必填非空(llm-factor-roll)。

    返回 (结果, None) 或 (None, 缺陷说明) 供纠正重试。
    """
    try:
        prob, qual = float(d["probability_pct"]), float(d["quality_pct"])
    except (KeyError, TypeError, ValueError):
        return None, "缺 probability_pct/quality_pct 数字"
    if not (0 <= prob <= 100 and 0 <= qual <= 100):
        return None, "百分数越界"
    factors = d.get("factors")
    if not isinstance(factors, dict):
        return None, "缺 factors 对象(七因子必填)"
    missing = [k for k in FACTOR_KEYS
               if not str(factors.get(k, "")).strip()]
    if missing:
        return None, f"factors 缺项或为空: {','.join(missing)}"
    return {"probability_pct": prob, "quality_pct": qual,
            "factors": {k: str(factors[k]) for k in FACTOR_KEYS},
            "scenario_alt": str(d.get("scenario_alt", "")),
            "rules_applied": [str(x) for x in d.get("rules_applied", [])],
            "reasoning": str(d.get("reasoning", "")),
            "risks": str(d.get("risks", "")),
            "confidence": str(d.get("confidence", "medium"))}, None


def predict_pct(payload: dict, similar: list[dict], frame_paths: list[Path],
                model: str = MODEL_FAST, client=None) -> dict | None:
    """检查点预测:免费层+案例+云图 → 百分数 JSON。失败静默 None(spec 8)。

    输出必须逐因子表态(FACTOR_KEYS 七项),缺项给一次纠正重试——
    "请考虑周全"是愿望,"字段必填否则重来"才是强制(2026-07-10 用户拍板)。
    """
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
        messages = [{"role": "user", "content": content}]
        system = _predict_system()
        for attempt in range(2):
            # 8000:adaptive thinking 与七因子 JSON 共享此额度——规则表注入后
            # 思考变长,4000 曾被 thinking 吃光导致文本块为空(2026-07-10 c1)
            resp = client.messages.create(
                model=model, max_tokens=8000, system=system,
                messages=messages, **kwargs)
            text = next((b.text for b in resp.content if b.type == "text"), "")
            text = re.sub(r"```(?:json)?|```", "", text)   # 剥 markdown 围栏
            m = re.search(r"\{.*\}", text, re.DOTALL)
            if m:
                try:
                    d = json.loads(m.group(0))
                except ValueError:
                    d = {}
                result, defect = _validate_predict(d)
                if result is not None:
                    return result
            elif resp.stop_reason == "max_tokens":
                defect = "输出被截断(max_tokens),压缩篇幅重来"
            else:
                defect = "没有输出 JSON"
            if attempt == 0:
                messages = messages + [
                    {"role": "assistant", "content": text or "(空)"},
                    {"role": "user", "content":
                     f"输出无效: {defect}。重新输出完整 JSON,factors 七项"
                     f"({'/'.join(FACTOR_KEYS)})每项一句都不能少。"}]
        print(f"predict_pct 输出两次均不完备: {defect}", file=sys.stderr)
        return None
    except Exception as e:
        # 仍按 spec 8 落基线不阻塞,但把原因写进 stderr(launchd 收进 tick.err);
        # 7/7 中午 c1 静默失败落了 3%/3% 的误导推送,根因已不可考——不能再哑
        print(f"predict_pct LLM 失败: {e.__class__.__name__}: {e}",
              file=sys.stderr)
        return None


def explain(card_md: str, frame_paths: list[Path], client=None) -> str | None:
    """案例复盘解读(analyze 命令用);失败静默 → None(spec 8)。"""
    try:
        if client is None:
            import anthropic
            client = anthropic.Anthropic()
        content: list[dict] = [{"type": "text", "text": card_md}]
        media = {".png": "image/png", ".jpg": "image/jpeg",
                 ".jpeg": "image/jpeg", ".webp": "image/webp"}
        for p in frame_paths[:6]:
            data = base64.standard_b64encode(Path(p).read_bytes()).decode()
            content.append({"type": "image", "source": {
                "type": "base64",
                "media_type": media.get(Path(p).suffix.lower(), "image/png"),
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
