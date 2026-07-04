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
