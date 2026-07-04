# src/skyfire/analyze.py
"""案例学习卡(knowledge §8):把一条闭环案例组装成可判读的 markdown。

五段固定骨架(通道/云幕/大气/卫星形态/结论)是经验笔记的口径,
LLM 或用户沿骨架填"为什么是这个分"。
"""


def _channel_line(payload: dict) -> str:
    ch = payload.get("channel") or []
    if not ch:
        return "(无剖面数据)"
    return "  ".join(f"{p['km']:.0f}km low={p['low']} total={p['total']}"
                     for p in ch if p.get("low") is not None)


def build_case_card(case: dict, snapshots: list[dict], frames: list[dict],
                    notes: list[dict]) -> str:
    payload = snapshots[-1]["payload"] if snapshots else {}
    lines = [
        f"# 案例 {case['date']} {case['city']} {case['event']}",
        f"实际 {case['actual_score']} 分 | 规则 {case['rule_score']}"
        f" | 置信 {case['confidence']}",
        "",
        f"## 通道(方位 {payload.get('azimuth', '?')}°)",
        _channel_line(payload),
        "",
        "## 云幕",
        f"点预报: 高云 {payload.get('cloud_high')}%  中云 {payload.get('cloud_mid')}%"
        f"  低云 {payload.get('cloud_low')}%",
        f"卫星实测北京上空云量: "
        + (f"{case['sat_cloud_pct']}%" if case.get('sat_cloud_pct') is not None
           else "(未测)"),
        "",
        "## 大气",
        f"AOD {payload.get('aod')}  地表RH {payload.get('rh_2m')}%"
        f"  降水 {payload.get('precipitation')}mm",
        "",
        "## 卫星形态",
    ]
    if frames:
        lines += [f"- {f['ts']} [{f['channel']}] {f['path']}" for f in frames]
    else:
        lines.append("(无卫星帧)")
    lines += ["", "## 结论(为什么是这个分)"]
    if notes:
        lines += [f"- [{n['author']}] {n['text']}" for n in notes]
    else:
        lines.append("(待分析)")
    return "\n".join(lines)
