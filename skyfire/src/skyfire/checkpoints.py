"""检查点窗口判定与门控(spec §2)。纯函数,不碰网络/DB。

c1 早间展望(朝霞在前一晚)/ c2 日出日落前2小时终判 / c3 前1小时终判
(用户 2026-07-08:T-2h、T-1h 各结合实时卫星给终极判断);之间由门控
(概率摆动 > GATE_PP)决定是否加跑 LLM。窗口内是否已跑由调用方
用 store.has_checkpoint 判重。
"""
from datetime import datetime, timedelta

GATE_PP = 15.0
_C1_WINDOW_H = 2

# peak 前分钟数区间 (end, start]。tick 每30分钟一次,窗口须 ≥30分钟宽保证命中。
C2_START, C2_END = 150, 90    # ≈T-2h 终判
C3_START, C3_END = 90, 30     # ≈T-1h 终判


def _c1_start(peak_local: datetime, event: str) -> datetime:
    if event == "sunset_glow":
        return peak_local.replace(hour=11, minute=0, second=0, microsecond=0)
    prev = peak_local - timedelta(days=1)
    return prev.replace(hour=20, minute=0, second=0, microsecond=0)


def due_checkpoint(now_local: datetime, peak_local: datetime,
                   event: str) -> str | None:
    c1 = _c1_start(peak_local, event)
    if c1 <= now_local < c1 + timedelta(hours=_C1_WINDOW_H):
        return "c1"
    to_peak = (peak_local - now_local).total_seconds() / 60
    if C2_END < to_peak <= C2_START:
        return "c2"
    if C3_END < to_peak <= C3_START:
        return "c3"
    return None


def gate_exceeded(prev_prob: float | None, new_prob: float,
                  threshold: float = GATE_PP) -> bool:
    if prev_prob is None:
        return False
    return abs(new_prob - prev_prob) > threshold
